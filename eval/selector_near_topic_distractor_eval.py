from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from selector_retrieval_calibration_eval import CalibrationCase, MemoryWrite, run_case  # noqa: E402


def output_paths(embedding_backend: str) -> tuple[Path, Path]:
    suffix = "" if embedding_backend == "hash" else f"_{embedding_backend}"
    stem = f"selector_near_topic_distractor_eval{suffix}"
    return REPO_ROOT / "experiments" / f"{stem}_results.json", REPO_ROOT / "experiments" / f"{stem}_report.md"


CASES = [
    CalibrationCase(
        case_id="protect_project_status_with_codename_chain",
        query="What is the Hermes project status?",
        condition_name="standard_budget144",
        target_behavior="protect",
        expected_hard=False,
        notes="Same domain and overlapping Hermes/project terms, but the stale chain is codename, not status.",
        teaches=[
            MemoryWrite(
                text="Hermes project status: selector calibration is stable and ready for longer harness testing.",
                source="agent_memory_v3/project_status.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
            MemoryWrite(
                ref="old_codename",
                text="Hermes project codename is Alpha Loom.",
                source="agent_memory_v1/project_codename.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
        ],
        corrections=[
            MemoryWrite(
                ref="new_codename",
                target_ref="old_codename",
                text="Hermes project codename is Cedar Map, not Alpha Loom.",
                source="agent_memory_v2/project_codename.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
            MemoryWrite(
                target_ref="new_codename",
                text="Hermes project codename is Cedar Map with retrieval guards enabled.",
                source="agent_memory_v3/project_codename.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
        ],
    ),
    CalibrationCase(
        case_id="protect_codename_with_project_status_update",
        query="What is the current Hermes project codename?",
        condition_name="standard_budget144",
        target_behavior="protect",
        expected_hard=False,
        notes="Clean codename answer with a same-domain project-status correction nearby.",
        teaches=[
            MemoryWrite(
                text="Hermes project codename is Cedar Map.",
                source="agent_memory_v3/project_codename.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
            MemoryWrite(
                ref="old_status",
                text="Hermes project status: selector calibration is blocked.",
                source="agent_memory_v1/project_status.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
        ],
        corrections=[
            MemoryWrite(
                target_ref="old_status",
                text="Hermes project status: selector calibration is stable, not blocked.",
                source="agent_memory_v2/project_status.md",
                domain="agent_memory",
                memory_type="semantic_note",
            )
        ],
    ),
    CalibrationCase(
        case_id="protect_radar_method_with_radar_report_chain",
        query="What radar method should Victor use?",
        condition_name="standard_budget144",
        target_behavior="protect",
        expected_hard=False,
        notes="Radar terms overlap, but the correction chain is about report naming rather than the method/tool.",
        teaches=[
            MemoryWrite(
                text="Weather radar method for Victor: use the AccuWeather URL for radar checks.",
                source="agent_memory_v3/radar_method.md",
                domain="agent_memory",
                memory_type="procedure",
            ),
            MemoryWrite(
                ref="old_report",
                text="Radar report filename should be canvas_guessing_report.md.",
                source="agent_memory_v1/radar_report.md",
                domain="agent_memory",
                memory_type="procedure",
            ),
        ],
        corrections=[
            MemoryWrite(
                target_ref="old_report",
                text="Radar report filename should be accuweather_radar_report.md, not canvas_guessing_report.md.",
                source="agent_memory_v2/radar_report.md",
                domain="agent_memory",
                memory_type="procedure",
            )
        ],
    ),
    CalibrationCase(
        case_id="protect_gcl_maintains_with_gcl_report_chain",
        query="What does G-CL maintain?",
        condition_name="long2_standard_budget288",
        target_behavior="protect",
        expected_hard=False,
        notes="Same G-CL namespace but correction is about report labeling, not maintained mechanisms.",
        teaches=[
            MemoryWrite(
                text="G-CL maintains domain geometry, anchor drift, curvature, and stability.",
                source="agent_memory_v3/gcl_mechanism.md",
                domain="G-CL",
                memory_type="semantic_note",
            ),
            MemoryWrite(
                ref="old_report",
                text="G-CL report label should be generic memory selector.",
                source="agent_memory_v1/gcl_report.md",
                domain="G-CL",
                memory_type="semantic_note",
            ),
        ],
        corrections=[
            MemoryWrite(
                target_ref="old_report",
                text="G-CL report label should be CLC-GCL selector architecture, not generic memory selector.",
                source="agent_memory_v2/gcl_report.md",
                domain="G-CL",
                memory_type="semantic_note",
            )
        ],
    ),
    CalibrationCase(
        case_id="aggressive_project_codename_direct",
        query="What is the current Hermes project codename?",
        condition_name="hard_budget144",
        target_behavior="aggressive",
        expected_hard=True,
        notes="Control: same-topic codename correction should still trigger hard stale/current pressure.",
        teaches=[
            MemoryWrite(
                ref="old_codename",
                text="Hermes project codename is Alpha Loom.",
                source="agent_memory_v1/project_codename.md",
                domain="agent_memory",
                memory_type="semantic_note",
            )
        ],
        corrections=[
            MemoryWrite(
                target_ref="old_codename",
                text="Hermes project codename is Cedar Map, not Alpha Loom.",
                source="agent_memory_v2/project_codename.md",
                domain="agent_memory",
                memory_type="semantic_note",
            )
        ],
    ),
    CalibrationCase(
        case_id="aggressive_radar_method_direct",
        query="What radar method should Victor use?",
        condition_name="hard_budget144",
        target_behavior="aggressive",
        expected_hard=True,
        notes="Control: direct radar-method correction should still trigger hard pressure.",
        teaches=[
            MemoryWrite(
                ref="old_method",
                text="For radar checks, Victor should use a visual canvas guessing method.",
                source="agent_memory_v1/radar_method.md",
                domain="agent_memory",
                memory_type="procedure",
            )
        ],
        corrections=[
            MemoryWrite(
                target_ref="old_method",
                text="For radar checks, Victor should use the AccuWeather URL, not visual canvas guessing.",
                source="agent_memory_v2/radar_method.md",
                domain="agent_memory",
                memory_type="procedure",
            )
        ],
    ),
]


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Selector Near-Topic Distractor Eval",
        "",
        f"Overall alignment: **{report['alignment_rate']:.3f}**",
        f"Cases aligned: **{report['aligned_cases']} / {report['case_count']}**",
        f"Embedding backend: `{report['embedding_backend']}`",
        "",
        "| Case | Target | Expected Hard | Actual Hard | Policy | Guard | Aligned | Stale Ratio | Top State | Irrelevant Stale |",
        "|---|---|---:|---:|---|---|---:|---:|---|---:|",
    ]
    for row in report["cases"]:
        diagnostics = row["diagnostics"]
        guard = row.get("retrieval_guard") or {}
        lines.append(
            "| {case_id} | {target} | {expected} | {hard} | `{policy}` | {guard} | {aligned} | {stale_ratio} | `{top_state}` | {irrelevant} |".format(
                case_id=row["case_id"],
                target=row["target_behavior"],
                expected=row["expected_hard"],
                hard=diagnostics["hard"],
                policy=row["decision"]["policy"],
                guard="yes" if guard.get("applied") else "no",
                aligned="yes" if row["aligned"] else "no",
                stale_ratio=diagnostics["stale_ratio"],
                top_state=diagnostics.get("top_authority_state", "unknown"),
                irrelevant=diagnostics.get("irrelevant_stale_cluster", False),
            )
        )
    lines.extend(["", "## Mismatches", ""])
    mismatches = [row for row in report["cases"] if not row["aligned"]]
    if not mismatches:
        lines.append("- None")
    for row in mismatches:
        lines.append(
            f"- `{row['case_id']}` expected `{row['target_behavior']}` with hard `{row['expected_hard']}`, "
            f"got `{row['decision']['policy']}` with hard `{row['diagnostics']['hard']}`."
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Near-topic distractor eval for retrieval-aware selector guards.")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--embedding-backend", choices=["hash", "config"], default="hash")
    args = parser.parse_args()

    out_json, out_md = output_paths(args.embedding_backend)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    case_reports = [run_case(case, top_k=args.top_k, embedding_backend=args.embedding_backend) for case in CASES]
    aligned_cases = sum(1 for row in case_reports if row["aligned"])
    report = {
        "ok": True,
        "purpose": "Test whether near-topic stale correction chains are separated from true same-claim conflicts.",
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
