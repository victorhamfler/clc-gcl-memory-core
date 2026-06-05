from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GUARD = REPO_ROOT / "experiments" / "memory_maintenance_rehearsal_candidate_guard_results.json"
DEFAULT_RPG_LABEL_QUALITY = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_quality_report_results.json"
DEFAULT_RPG_LABEL_SCORER = REPO_ROOT / "experiments" / "memory_maintenance_rpg_label_scorer_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_operator_review_packet_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_operator_review_packet_report.md"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def load_guard(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Guard artifact must be a JSON object: {path}")
    if value.get("schema") != "memory_maintenance_rehearsal_candidate_guard/v1":
        raise ValueError(f"Unsupported guard schema: {value.get('schema')}")
    return value


def load_optional_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def rpg_learning_context(*, quality_path: Path, scorer_path: Path) -> dict[str, Any]:
    quality = load_optional_json_object(quality_path)
    scorer = load_optional_json_object(scorer_path)
    return {
        "schema": "memory_maintenance_operator_rpg_learning_context/v1",
        "description": "Report-only RPG supervised-learning readiness context for operator review.",
        "label_quality_schema": quality.get("schema"),
        "label_quality_ready_for_shadow_scorer_training": bool(quality.get("ready_for_shadow_scorer_training")),
        "label_quality_labeled_count": int(quality.get("labeled_count") or 0),
        "label_quality_label_counts": quality.get("label_counts") or {},
        "label_quality_promotion_blockers": quality.get("promotion_blockers") or [],
        "scorer_schema": scorer.get("schema"),
        "scorer_ready_for_shadow": bool(scorer.get("ready_for_shadow_scorer")),
        "scorer_ready_for_policy": bool(scorer.get("ready_for_policy_use")),
        "scorer_label_counts": scorer.get("label_counts") or {},
        "scorer_promotion_blockers": scorer.get("promotion_blockers") or [],
        "operator_use": "explanation_only_do_not_auto_apply",
        "ready_for_policy_use": False,
        "mutation_allowed": False,
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def target_previews(candidate: dict[str, Any]) -> dict[str, str]:
    previews: dict[str, str] = {}
    for example in candidate.get("examples") or []:
        if not isinstance(example, dict):
            continue
        text_previews = example.get("target_text_preview")
        if isinstance(text_previews, dict):
            for memory_id, text in text_previews.items():
                previews[str(memory_id)] = str(text)[:180]
        for memory_id in example.get("target_ids") or []:
            previews.setdefault(str(memory_id), "")
    return previews


def target_ids(candidate: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for example in candidate.get("examples") or []:
        if not isinstance(example, dict):
            continue
        for memory_id in example.get("target_ids") or []:
            value = str(memory_id or "").strip()
            if value and value not in ids:
                ids.append(value)
    return ids


def safe_rehearsal_command(*, source_db: str, apply_plan: str, work_dir: str, operator_id: str) -> str:
    return (
        "py -3 eval/memory_maintenance_copied_db_rehearsal.py "
        f"--source-db \"{source_db}\" "
        f"--apply-plan \"{apply_plan}\" "
        f"--work-dir \"{work_dir}\" "
        f"--operator-id \"{operator_id}\""
    )


def packet_item(
    candidate: dict[str, Any],
    *,
    status: str,
    command: str,
    learning_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "memory_maintenance_operator_review_packet_item/v1",
        "id": candidate.get("id"),
        "status": status,
        "operation_kind": candidate.get("operation_kind"),
        "source_cluster_key": candidate.get("source_cluster_key"),
        "recommended_action": candidate.get("recommended_action"),
        "run_count": candidate.get("run_count"),
        "support": candidate.get("support"),
        "runs": candidate.get("runs") or [],
        "safe_count": candidate.get("safe_count"),
        "blocked_count": candidate.get("blocked_count"),
        "blocked_reasons": candidate.get("blocked_reasons") or [],
        "rpg_summary": candidate.get("rpg_summary") or {},
        "rpg_learning_context": learning_context,
        "target_ids": target_ids(candidate),
        "target_text_preview": target_previews(candidate),
        "safe_copied_db_rehearsal_command": command,
        "operator_questions": [
            "Do the target rows still represent exact duplicate content?",
            "Is the keeper row the correct row to preserve?",
            "Are there stale, semantic, bridge, conflict, or cross-namespace risks?",
            "Should this remain blocked pending more copied-DB rehearsals?",
        ],
        "mutation_allowed": False,
        "report_only": True,
    }


def build_packet(
    guard_path: Path,
    *,
    source_db: str = "<source-memory.db>",
    apply_plan: str = "<memory_maintenance_apply_plan.json>",
    work_dir: str = "E:\\projcod2_artifacts_archive\\current_rehearsals\\operator_review",
    operator_id: str = "operator_review",
    rpg_label_quality: Path = DEFAULT_RPG_LABEL_QUALITY,
    rpg_label_scorer: Path = DEFAULT_RPG_LABEL_SCORER,
) -> dict[str, Any]:
    guard = load_guard(guard_path)
    learning_context = rpg_learning_context(quality_path=rpg_label_quality, scorer_path=rpg_label_scorer)
    command = safe_rehearsal_command(
        source_db=source_db,
        apply_plan=apply_plan,
        work_dir=work_dir,
        operator_id=operator_id,
    )
    ready_items = [
        packet_item(
            candidate,
            status="ready_for_operator_review",
            command=command,
            learning_context=learning_context,
        )
        for candidate in guard.get("guarded_candidates") or []
        if isinstance(candidate, dict)
    ]
    blocked_items = [
        packet_item(
            candidate,
            status="blocked_before_operator_review",
            command=command,
            learning_context=learning_context,
        )
        for candidate in guard.get("blocked_candidates") or []
        if isinstance(candidate, dict)
    ]
    return {
        "schema": "memory_maintenance_operator_review_packet/v1",
        "source_guard": str(guard_path),
        "source_guard_schema": guard.get("schema"),
        "ready_count": len(ready_items),
        "blocked_count": len(blocked_items),
        "risky_operation_kinds": guard.get("risky_operation_kinds") or [],
        "rpg_learning_context": learning_context,
        "ready_items": ready_items,
        "blocked_items": blocked_items,
        "safe_copied_db_rehearsal_command": command,
        "next_action": "operator_review_ready_candidates"
        if ready_items
        else "resolve_blockers_or_collect_more_rehearsals",
        "mutation_allowed": False,
        "promotion_ready": False,
        "promotion_blockers": ["operator_review_required", "real_db_mutation_not_allowed"],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(packet: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Operator Review Packet",
        "",
        "Human/Hermes-readable packet for guarded copied-DB rehearsal candidates.",
        "",
        f"Ready items: `{packet['ready_count']}`",
        f"Blocked items: `{packet['blocked_count']}`",
        f"Next action: `{packet['next_action']}`",
        f"RPG label quality ready: `{(packet.get('rpg_learning_context') or {}).get('label_quality_ready_for_shadow_scorer_training')}`",
        f"RPG scorer policy ready: `{(packet.get('rpg_learning_context') or {}).get('scorer_ready_for_policy')}`",
        "",
        "## Safe Rehearsal Command",
        "",
        "```powershell",
        packet["safe_copied_db_rehearsal_command"],
        "```",
        "",
        "## Ready Items",
        "",
        "| id | operation | runs | targets |",
        "| --- | --- | ---: | --- |",
    ]
    if not packet.get("ready_items"):
        lines.append("| none | none | 0 | none |")
    for item in packet.get("ready_items") or []:
        lines.append(
            f"| `{clean_cell(item.get('id'), 90)}` | `{clean_cell(item.get('operation_kind'), 60)}` | "
            f"{len(item.get('runs') or [])} | `{clean_cell(', '.join(item.get('target_ids') or []), 120)}` |"
        )
    lines.extend(["", "## Blocked Items", "", "| id | operation | blockers |", "| --- | --- | --- |"])
    if not packet.get("blocked_items"):
        lines.append("| none | none | none |")
    for item in packet.get("blocked_items") or []:
        lines.append(
            f"| `{clean_cell(item.get('id'), 90)}` | `{clean_cell(item.get('operation_kind'), 60)}` | "
            f"`{clean_cell(', '.join(item.get('blocked_reasons') or []), 140)}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an operator review packet from guarded rehearsal candidates.")
    parser.add_argument("--guard", default=str(DEFAULT_GUARD))
    parser.add_argument("--source-db", default="<source-memory.db>")
    parser.add_argument("--apply-plan", default="<memory_maintenance_apply_plan.json>")
    parser.add_argument("--work-dir", default="E:\\projcod2_artifacts_archive\\current_rehearsals\\operator_review")
    parser.add_argument("--operator-id", default="operator_review")
    parser.add_argument("--rpg-label-quality", default=str(DEFAULT_RPG_LABEL_QUALITY))
    parser.add_argument("--rpg-label-scorer", default=str(DEFAULT_RPG_LABEL_SCORER))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    packet = build_packet(
        Path(args.guard),
        source_db=args.source_db,
        apply_plan=args.apply_plan,
        work_dir=args.work_dir,
        operator_id=args.operator_id,
        rpg_label_quality=Path(args.rpg_label_quality),
        rpg_label_scorer=Path(args.rpg_label_scorer),
    )
    write_report(packet, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "schema": packet["schema"],
                "ready_count": packet["ready_count"],
                "blocked_count": packet["blocked_count"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
