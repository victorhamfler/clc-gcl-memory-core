from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import (  # noqa: E402
    POLICY_LONG_SEVERE,
    POLICY_PERIODIC,
    POLICY_XSEQ_MEMORY,
)
from core.config import load_config  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from core.selector_runtime import (  # noqa: E402
    apply_retrieval_explanation_guard,
    build_policy_selector,
    selector_features_from_retrieval_context,
)
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "selector_retrieval_calibration_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "selector_retrieval_calibration_eval_report.md"

AGGRESSIVE_POLICIES = {POLICY_LONG_SEVERE, POLICY_XSEQ_MEMORY}
PROTECT_POLICIES = {POLICY_PERIODIC}


def output_paths(embedding_backend: str) -> tuple[Path, Path]:
    if embedding_backend == "hash":
        return OUT_JSON, OUT_MD
    suffix = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in embedding_backend)
    return (
        REPO_ROOT / "experiments" / f"selector_retrieval_calibration_eval_{suffix}_results.json",
        REPO_ROOT / "experiments" / f"selector_retrieval_calibration_eval_{suffix}_report.md",
    )


@dataclass(frozen=True)
class MemoryWrite:
    text: str
    source: str
    domain: str = "agent_memory"
    memory_type: str = "semantic_note"
    target_ref: str | None = None
    ref: str | None = None


@dataclass(frozen=True)
class CalibrationCase:
    case_id: str
    query: str
    condition_name: str
    target_behavior: str
    teaches: list[MemoryWrite] = field(default_factory=list)
    corrections: list[MemoryWrite] = field(default_factory=list)
    expected_hard: bool | None = None
    notes: str = ""


CASES = [
    CalibrationCase(
        case_id="direct_preference_correction",
        query="What is Victor's current drink preference?",
        condition_name="hard_budget144",
        target_behavior="aggressive",
        expected_hard=True,
        notes="Single stale memory corrected by a current preference.",
        teaches=[
            MemoryWrite(
                ref="old_drink",
                text="Victor likes espresso in the morning and green tea in the afternoon.",
                source="agent_memory_v1/preferences.md",
                domain="food_drink",
                memory_type="preference",
            )
        ],
        corrections=[
            MemoryWrite(
                target_ref="old_drink",
                text="Victor currently drinks water, not espresso or green tea.",
                source="agent_memory_v2/corrections.md",
                domain="food_drink",
                memory_type="preference",
            )
        ],
    ),
    CalibrationCase(
        case_id="chained_project_codename_correction",
        query="What is the current Hermes project codename?",
        condition_name="hard_budget144",
        target_behavior="aggressive",
        expected_hard=True,
        notes="Two-step correction chain should make stale pressure obvious.",
        teaches=[
            MemoryWrite(
                ref="old_code",
                text="Hermes project codename is Alpha Loom.",
                source="agent_memory_v1/project.md",
                domain="agent_memory",
                memory_type="semantic_note",
            )
        ],
        corrections=[
            MemoryWrite(
                ref="mid_code",
                target_ref="old_code",
                text="Hermes project codename is Cedar Map, not Alpha Loom.",
                source="agent_memory_v2/project.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
            MemoryWrite(
                target_ref="mid_code",
                text="Hermes project codename is Cedar Map with the CLC selector enabled.",
                source="agent_memory_v3/project.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
        ],
    ),
    CalibrationCase(
        case_id="clean_weather_procedure",
        query="What weather radar method should Victor use?",
        condition_name="standard_budget144",
        target_behavior="protect",
        expected_hard=False,
        notes="Clean current procedural memory should avoid stale-conflict escalation.",
        teaches=[
            MemoryWrite(
                text="Weather radar method for Victor: use the AccuWeather URL for radar checks.",
                source="agent_memory_v1/weather.md",
                domain="agent_memory",
                memory_type="procedure",
            ),
            MemoryWrite(
                text="Victor values source clarity and transparency when information is presented.",
                source="agent_memory_v1/user_profile.md",
                domain="agent_memory",
                memory_type="preference",
            ),
        ],
    ),
    CalibrationCase(
        case_id="clean_multi_topic_clutter",
        query="What does G-CL maintain?",
        condition_name="long2_standard_budget288",
        target_behavior="protect",
        expected_hard=False,
        notes="Clean target memory with unrelated clutter tests false-positive stale pressure.",
        teaches=[
            MemoryWrite(
                text="Victor pizza preference: he likes mushroom pizza.",
                source="agent_memory_v1/food.md",
                domain="food_drink",
                memory_type="preference",
            ),
            MemoryWrite(
                text="Hermes project codename is Cedar Map.",
                source="agent_memory_v1/project.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
            MemoryWrite(
                text="G-CL maintains domain geometry, anchor drift, curvature, and stability.",
                source="agent_memory_v1/gcl.md",
                domain="G-CL",
                memory_type="semantic_note",
            ),
        ],
    ),
    CalibrationCase(
        case_id="food_preference_correction_with_clutter",
        query="What pizza does Victor currently prefer?",
        condition_name="hard_budget144",
        target_behavior="aggressive",
        expected_hard=True,
        notes="Stale/current food preference with nearby same-domain clutter.",
        teaches=[
            MemoryWrite(
                ref="old_pizza",
                text="Victor currently prefers mushroom pizza.",
                source="agent_memory_v1/food.md",
                domain="food_drink",
                memory_type="preference",
            ),
            MemoryWrite(
                text="Victor likes espresso in the morning.",
                source="agent_memory_v1/food.md",
                domain="food_drink",
                memory_type="preference",
            ),
        ],
        corrections=[
            MemoryWrite(
                target_ref="old_pizza",
                text="Victor currently prefers cheese pizza, not mushroom pizza.",
                source="agent_memory_v2/food_corrections.md",
                domain="food_drink",
                memory_type="preference",
            )
        ],
    ),
    CalibrationCase(
        case_id="unrelated_stale_memory_should_not_escalate",
        query="What does G-CL maintain?",
        condition_name="standard_budget144",
        target_behavior="protect",
        expected_hard=False,
        notes="A stale drink correction exists, but the query targets clean G-CL knowledge.",
        teaches=[
            MemoryWrite(
                ref="old_drink",
                text="Victor likes espresso in the morning and green tea in the afternoon.",
                source="agent_memory_v1/preferences.md",
                domain="food_drink",
                memory_type="preference",
            ),
            MemoryWrite(
                text="G-CL maintains domain geometry, anchor drift, curvature, and stability.",
                source="agent_memory_v1/gcl.md",
                domain="G-CL",
                memory_type="semantic_note",
            ),
        ],
        corrections=[
            MemoryWrite(
                target_ref="old_drink",
                text="Victor currently drinks water, not espresso or green tea.",
                source="agent_memory_v2/corrections.md",
                domain="food_drink",
                memory_type="preference",
            )
        ],
    ),
]


def target_matches(policy: str, target_behavior: str) -> bool:
    if target_behavior == "aggressive":
        return policy in AGGRESSIVE_POLICIES
    if target_behavior == "protect":
        return policy in PROTECT_POLICIES
    raise ValueError(f"Unknown target behavior: {target_behavior}")


def init_pipeline(tmp: Path, case_id: str, embedding_backend: str) -> MemoryPipeline:
    db_path = tmp / f"{case_id}.db"
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    if embedding_backend == "config":
        config = load_config(ROOT)
        embedding_config = dict(config.get("embedding") or {})
    else:
        embedding_config = {"backend": "hash", "dim": 128}
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_config=embedding_config,
    )


def run_case(case: CalibrationCase, *, top_k: int, embedding_backend: str) -> dict[str, Any]:
    refs: dict[str, str] = {}
    namespace = f"selector_calibration_{case.case_id}"
    agent_id = f"selector_calibration_{case.case_id}"

    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp), case.case_id, embedding_backend)
        try:
            writes: list[dict[str, Any]] = []
            for write in case.teaches:
                taught = pipeline.teach(
                    write.text,
                    source=write.source,
                    namespace=namespace,
                    agent_id=agent_id,
                    store_session=False,
                    domain=write.domain,
                    memory_type=write.memory_type,
                )
                memory_id = taught["memory"]["memory_id"]
                if write.ref:
                    refs[write.ref] = memory_id
                writes.append({"mode": "teach", "ref": write.ref, "memory_id": memory_id, "text": write.text})

            for write in case.corrections:
                target_ids = [refs[write.target_ref]] if write.target_ref and write.target_ref in refs else []
                corrected = pipeline.correct(
                    write.text,
                    target_memory_ids=target_ids,
                    target_query=case.query,
                    top_k=top_k,
                    source=write.source,
                    namespace=namespace,
                    agent_id=agent_id,
                    store_session=False,
                    relation_type="corrects",
                    domain=write.domain,
                    memory_type=write.memory_type,
                )
                memory_id = corrected["correction_memory"]["memory_id"]
                if write.ref:
                    refs[write.ref] = memory_id
                writes.append(
                    {
                        "mode": "correct",
                        "ref": write.ref,
                        "target_ref": write.target_ref,
                        "target_memory_ids": target_ids,
                        "memory_id": memory_id,
                        "text": write.text,
                    }
                )

            retrieval_rows = pipeline.retrieve(case.query, top_k=top_k, namespace=namespace, include_global=False)
        finally:
            pipeline.close()

    selector = build_policy_selector(ROOT, load_config(ROOT))
    features, diagnostics = selector_features_from_retrieval_context(
        retrieval_rows,
        condition_name=case.condition_name,
    )
    explanation = apply_retrieval_explanation_guard(selector.explain(features, top_k=5), features, diagnostics)
    policy = explanation["decision"]["policy"]
    hard_matches = case.expected_hard is None or bool(diagnostics["hard"]) == bool(case.expected_hard)
    policy_matches = target_matches(policy, case.target_behavior)
    retrieved_brief = [
        {
            "memory_id": row.get("memory_id"),
            "authority_state": row.get("authority_state"),
            "source": row.get("source"),
            "domain_name": row.get("domain_name"),
            "score": row.get("score"),
            "text_match_score": row.get("text_match_score"),
            "intent_match_score": row.get("intent_match_score"),
            "supersession_score": row.get("supersession_score"),
            "relation_supersession_score": row.get("relation_supersession_score"),
            "stored_contradiction_score": row.get("stored_contradiction_score"),
            "text": row.get("text"),
        }
        for row in retrieval_rows
    ]
    return {
        "case_id": case.case_id,
        "query": case.query,
        "condition_name": case.condition_name,
        "target_behavior": case.target_behavior,
        "expected_hard": case.expected_hard,
        "notes": case.notes,
        "writes": writes,
        "retrieval_rows": retrieved_brief,
        "features": features.__dict__,
        "diagnostics": diagnostics,
        "decision": explanation["decision"],
        "base_decision": explanation.get("base_decision"),
        "retrieval_guard": explanation.get("retrieval_guard"),
        "votes": explanation["votes"],
        "nearest_samples": explanation["nearest_samples"][:5],
        "policy_matches_target": policy_matches,
        "hard_matches_target": hard_matches,
        "aligned": policy_matches and hard_matches,
    }


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Selector Retrieval Calibration Eval",
        "",
        f"Overall alignment: **{report['alignment_rate']:.3f}**",
        f"Cases aligned: **{report['aligned_cases']} / {report['case_count']}**",
        f"Embedding backend: `{report['embedding_backend']}`",
        "",
        "## Case Summary",
        "",
        "| Case | Target | Expected Hard | Actual Hard | Policy | Guard | Aligned | Stale Ratio | CSD Ratio |",
        "|---|---|---:|---:|---|---|---:|---:|---:|",
    ]
    for row in report["cases"]:
        lines.append(
            "| {case_id} | {target} | {expected} | {hard} | `{policy}` | {guard} | {aligned} | {stale_ratio} | {csd_ratio} |".format(
                case_id=row["case_id"],
                target=row["target_behavior"],
                expected=row["expected_hard"],
                hard=row["diagnostics"]["hard"],
                policy=row["decision"]["policy"],
                guard="yes" if (row.get("retrieval_guard") or {}).get("applied") else "no",
                aligned="yes" if row["aligned"] else "no",
                stale_ratio=row["diagnostics"]["stale_ratio"],
                csd_ratio=row["diagnostics"]["csd_ratio"],
            )
        )

    lines.extend(["", "## Mismatches", ""])
    mismatches = [row for row in report["cases"] if not row["aligned"]]
    if not mismatches:
        lines.append("- None")
    for row in mismatches:
        lines.append(
            "- `{case_id}` targeted `{target}` and expected hard `{expected}`, but got policy `{policy}` and hard `{hard}`.".format(
                case_id=row["case_id"],
                target=row["target_behavior"],
                expected=row["expected_hard"],
                policy=row["decision"]["policy"],
                hard=row["diagnostics"]["hard"],
            )
        )

    lines.extend(["", "## Development Reading", ""])
    if mismatches:
        lines.append("- Remaining aggressive-case failures suggest under-detected stale/current conflict or a missing hard-conflict guard.")
        lines.append("- Remaining protect-case failures suggest over-escalation on clean or query-irrelevant stale contexts.")
        lines.append("- Review mismatched retrieval rows before tuning formulas or selector weights.")
    else:
        lines.append("- Retrieval-aware guards aligned all calibration cases while preserving the learned selector vote trace.")
        lines.append("- Next pressure tests should add more query-irrelevant stale contexts and mild same-domain updates.")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibration eval for retrieval-derived CLC selector features.")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument(
        "--embedding-backend",
        choices=["hash", "config"],
        default="hash",
        help="Use hash for portable CI/Hermes testing, or config for the local Gemma sidecar setup.",
    )
    args = parser.parse_args()

    out_json, out_md = output_paths(args.embedding_backend)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    selected_cases = CASES
    case_reports = [run_case(case, top_k=args.top_k, embedding_backend=args.embedding_backend) for case in selected_cases]
    aligned_cases = sum(1 for row in case_reports if row["aligned"])
    report = {
        "ok": True,
        "purpose": "Calibrate retrieval-derived selector features across stale, clean, chained, and cluttered memory cases.",
        "embedding_backend": args.embedding_backend,
        "top_k": args.top_k,
        "case_count": len(case_reports),
        "aligned_cases": aligned_cases,
        "alignment_rate": aligned_cases / max(1, len(case_reports)),
        "cases": case_reports,
        "outputs": {"json": str(out_json), "markdown": str(out_md)},
    }
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "alignment_rate": report["alignment_rate"],
                "aligned_cases": report["aligned_cases"],
                "case_count": report["case_count"],
                "json": str(out_json),
                "markdown": str(out_md),
                "mismatches": [
                    {
                        "case_id": row["case_id"],
                        "target_behavior": row["target_behavior"],
                        "expected_hard": row["expected_hard"],
                        "actual_hard": row["diagnostics"]["hard"],
                        "policy": row["decision"]["policy"],
                    }
                    for row in case_reports
                    if not row["aligned"]
                ],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
