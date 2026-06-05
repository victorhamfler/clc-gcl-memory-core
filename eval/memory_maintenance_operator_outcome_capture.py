from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKET = REPO_ROOT / "experiments" / "memory_maintenance_operator_review_packet_results.json"
DEFAULT_OUTCOMES = REPO_ROOT / "experiments" / "memory_maintenance_operator_review_outcomes_template.json"
OUT_JSON = REPO_ROOT / "experiments" / "memory_maintenance_operator_outcome_capture_results.json"
OUT_MD = REPO_ROOT / "experiments" / "memory_maintenance_operator_outcome_capture_report.md"

OUTCOME_SCHEMA = "memory_maintenance_operator_review_outcomes/v1"
CAPTURE_SCHEMA = "memory_maintenance_operator_outcome_capture/v1"
ALLOWED_OUTCOMES = {
    "accept",
    "reject",
    "needs_more_evidence",
    "unsafe_to_apply",
    "already_resolved",
    "relabel_for_rpg_training",
}
ALLOWED_RPG_LABELS = {
    "safe_duplicate",
    "stale_or_update_conflict",
    "bridge_contamination",
    "semantic_near_duplicate",
    "harmless_related_memory",
    "uncertain_needs_more_context",
    "",
}


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def packet_items(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key in ("ready_items", "blocked_items"):
        for item in packet.get(key) or []:
            if isinstance(item, dict):
                rows.append(item)
    return rows


def item_status(item: dict[str, Any]) -> str:
    return str(item.get("status") or "").strip()


def operation_from_item(item: dict[str, Any]) -> str:
    return str(item.get("operation_kind") or "unknown").strip()


def inferred_rpg_label(item: dict[str, Any], outcome: str, explicit_label: str) -> str:
    if explicit_label:
        return explicit_label
    operation = operation_from_item(item)
    status = item_status(item)
    if outcome == "accept" and operation == "duplicate_deprecation":
        return "safe_duplicate"
    if outcome in {"reject", "unsafe_to_apply"} and status == "blocked_before_operator_review":
        return "uncertain_needs_more_context"
    if outcome == "needs_more_evidence":
        return "uncertain_needs_more_context"
    if outcome == "already_resolved":
        return "harmless_related_memory"
    return ""


def build_outcome_template(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": OUTCOME_SCHEMA,
        "source_packet_schema": packet.get("schema"),
        "allowed_outcomes": sorted(ALLOWED_OUTCOMES),
        "allowed_rpg_training_labels": sorted(label for label in ALLOWED_RPG_LABELS if label),
        "outcomes": [
            {
                "packet_item_id": item.get("id"),
                "status": item.get("status"),
                "operation_kind": item.get("operation_kind"),
                "outcome": "",
                "reviewer": "",
                "reason": "",
                "rpg_training_label": "",
                "rpg_training_note": "",
                "operator_apply_note": "",
            }
            for item in packet_items(packet)
        ],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def normalize_outcomes(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        values = raw.get("outcomes")
        if isinstance(values, list):
            return [item for item in values if isinstance(item, dict)]
        if raw.get("packet_item_id"):
            return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def build_capture(packet: dict[str, Any], outcomes_raw: Any) -> dict[str, Any]:
    items = packet_items(packet)
    by_id = {str(item.get("id") or ""): item for item in items}
    outcomes = normalize_outcomes(outcomes_raw)
    normalized = []
    outcome_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    rpg_label_counts: Counter[str] = Counter()
    unknown_item_ids = []
    invalid_outcomes = []
    invalid_rpg_labels = []
    for row in outcomes:
        item_id = str(row.get("packet_item_id") or "").strip()
        outcome = str(row.get("outcome") or "").strip().lower()
        explicit_label = str(row.get("rpg_training_label") or "").strip()
        item = by_id.get(item_id) or {}
        known = item_id in by_id
        valid_outcome = outcome in ALLOWED_OUTCOMES
        valid_rpg_label = explicit_label in ALLOWED_RPG_LABELS
        if not known:
            unknown_item_ids.append(item_id)
        if not valid_outcome:
            invalid_outcomes.append({"packet_item_id": item_id, "outcome": outcome})
        if not valid_rpg_label:
            invalid_rpg_labels.append({"packet_item_id": item_id, "rpg_training_label": explicit_label})
        inferred_label = inferred_rpg_label(item, outcome, explicit_label if valid_rpg_label else "")
        outcome_counts[outcome or "missing"] += 1
        status_counts[item_status(item) or "unknown"] += 1
        if inferred_label:
            rpg_label_counts[inferred_label] += 1
        normalized.append(
            {
                "schema": "memory_maintenance_operator_outcome_capture_item/v1",
                "packet_item_id": item_id,
                "known_packet_item": known,
                "valid_outcome": valid_outcome,
                "valid_rpg_training_label": valid_rpg_label,
                "status": item_status(item),
                "operation_kind": operation_from_item(item),
                "outcome": outcome,
                "reviewer": str(row.get("reviewer") or "").strip(),
                "reason": str(row.get("reason") or "").strip(),
                "operator_apply_note": str(row.get("operator_apply_note") or "").strip(),
                "rpg_training_label": inferred_label,
                "rpg_training_label_source": "operator_explicit" if explicit_label else "derived_from_outcome",
                "rpg_training_note": str(row.get("rpg_training_note") or "").strip(),
                "target_ids": item.get("target_ids") or [],
                "blocked_reasons": item.get("blocked_reasons") or [],
                "rpg_summary": item.get("rpg_summary") or {},
                "rpg_learning_context": item.get("rpg_learning_context") or {},
                "report_only": True,
                "mutates_db": False,
            }
        )
    accepted = outcome_counts.get("accept", 0)
    rejected = outcome_counts.get("reject", 0) + outcome_counts.get("unsafe_to_apply", 0)
    valid = not unknown_item_ids and not invalid_outcomes and not invalid_rpg_labels
    readiness = "capture_valid_for_rpg_label_feedback" if valid and outcomes else "capture_needs_review"
    if not outcomes:
        readiness = "collect_operator_packet_outcomes"
    return {
        "schema": CAPTURE_SCHEMA,
        "description": "Report-only capture of operator decisions for maintenance operator-review packets.",
        "source_packet_schema": packet.get("schema"),
        "packet_item_count": len(items),
        "outcome_count": len(outcomes),
        "known_outcome_count": sum(1 for item in normalized if item["known_packet_item"]),
        "unknown_packet_item_ids": unknown_item_ids,
        "invalid_outcomes": invalid_outcomes,
        "invalid_rpg_training_labels": invalid_rpg_labels,
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "status_outcome_counts": dict(sorted(status_counts.items())),
        "rpg_training_label_counts": dict(sorted(rpg_label_counts.items())),
        "accepted_count": accepted,
        "blocked_or_rejected_count": rejected,
        "outcomes": normalized,
        "readiness": readiness,
        "next_action": "feed_operator_outcomes_to_rpg_label_bank"
        if readiness == "capture_valid_for_rpg_label_feedback"
        else "collect_or_review_operator_packet_outcomes",
        "ready_for_policy_use": False,
        "promotion_ready": False,
        "promotion_blockers": [
            "rpg_label_bank_feedback_integration_required",
            "real_maintenance_outcome_validation_required",
            "database_mutation_not_allowed",
        ],
        "report_only": True,
        "mutates_db": False,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(capture: dict[str, Any], template: dict[str, Any], out_json: Path, out_md: Path, template_out: Path | None) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(capture, indent=2), encoding="utf-8")
    if template_out is not None:
        template_out.write_text(json.dumps(template, indent=2), encoding="utf-8")
    lines = [
        "# Memory Maintenance Operator Outcome Capture",
        "",
        "Report-only capture of operator decisions for maintenance operator-review packets.",
        "",
        f"Outcome count: `{capture['outcome_count']}`",
        f"Known outcomes: `{capture['known_outcome_count']}`",
        f"Readiness: `{capture['readiness']}`",
        f"Next action: `{capture['next_action']}`",
        f"Ready for policy use: `{capture['ready_for_policy_use']}`",
        "",
        "## Outcome Counts",
        "",
        "```json",
        json.dumps(capture.get("outcome_counts"), indent=2),
        "```",
        "",
        "## RPG Training Label Counts",
        "",
        "```json",
        json.dumps(capture.get("rpg_training_label_counts"), indent=2),
        "```",
        "",
        "## Captured Outcomes",
        "",
        "| item | status | outcome | rpg label | targets |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not capture.get("outcomes"):
        lines.append("| none | none | none | none | none |")
    for item in capture.get("outcomes") or []:
        lines.append(
            f"| `{clean_cell(item.get('packet_item_id'), 80)}` | `{clean_cell(item.get('status'), 50)}` | "
            f"`{clean_cell(item.get('outcome'), 40)}` | `{clean_cell(item.get('rpg_training_label'), 60)}` | "
            f"`{clean_cell(', '.join(item.get('target_ids') or []), 100)}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture operator-review packet outcomes without mutation.")
    parser.add_argument("--packet", default=str(DEFAULT_PACKET))
    parser.add_argument("--outcomes", default=str(DEFAULT_OUTCOMES))
    parser.add_argument("--write-template", action="store_true")
    parser.add_argument("--template-out", default=str(DEFAULT_OUTCOMES))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    packet = load_json(Path(args.packet))
    template = build_outcome_template(packet)
    outcomes_path = Path(args.outcomes)
    outcomes = load_json(outcomes_path) if outcomes_path.exists() and not args.write_template else template
    capture = build_capture(packet, outcomes)
    write_report(
        capture,
        template,
        Path(args.out_json),
        Path(args.out_md),
        Path(args.template_out) if args.write_template else None,
    )
    print(
        json.dumps(
            {
                "ok": capture.get("schema") == CAPTURE_SCHEMA,
                "schema": capture.get("schema"),
                "outcome_count": capture.get("outcome_count"),
                "readiness": capture.get("readiness"),
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
                "template": str(Path(args.template_out)) if args.write_template else None,
                "report_only": True,
                "mutates_db": False,
            },
            indent=2,
        )
    )
    return 0 if capture.get("schema") == CAPTURE_SCHEMA else 1


if __name__ == "__main__":
    raise SystemExit(main())
