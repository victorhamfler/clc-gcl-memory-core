from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from selector_retrieval_calibration_eval import CalibrationCase, MemoryWrite, run_case  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "selector_retrieval_guard_pressure_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "selector_retrieval_guard_pressure_eval_report.md"


def output_paths(embedding_backend: str) -> tuple[Path, Path]:
    if embedding_backend == "hash":
        return OUT_JSON, OUT_MD
    suffix = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in embedding_backend)
    return (
        REPO_ROOT / "experiments" / f"selector_retrieval_guard_pressure_eval_{suffix}_results.json",
        REPO_ROOT / "experiments" / f"selector_retrieval_guard_pressure_eval_{suffix}_report.md",
    )


PRESSURE_CASES = [
    CalibrationCase(
        case_id="unrelated_stale_cluster_gcl_clean",
        query="What does G-CL maintain?",
        condition_name="standard_budget144",
        target_behavior="protect",
        expected_hard=False,
        notes="Multiple unrelated stale memories exist, but the target G-CL memory is clean and topically direct.",
        teaches=[
            MemoryWrite(
                text="G-CL maintains domain geometry, anchor drift, curvature, and stability.",
                source="agent_memory_v1/gcl.md",
                domain="G-CL",
                memory_type="semantic_note",
            ),
            MemoryWrite(
                ref="old_drink",
                text="Victor likes espresso in the morning and green tea in the afternoon.",
                source="agent_memory_v1/preferences.md",
                domain="food_drink",
                memory_type="preference",
            ),
            MemoryWrite(
                ref="old_pizza",
                text="Victor currently prefers mushroom pizza.",
                source="agent_memory_v1/food.md",
                domain="food_drink",
                memory_type="preference",
            ),
            MemoryWrite(
                ref="old_code",
                text="Hermes project codename is Alpha Loom.",
                source="agent_memory_v1/project.md",
                domain="agent_memory",
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
            ),
            MemoryWrite(
                target_ref="old_pizza",
                text="Victor currently prefers cheese pizza, not mushroom pizza.",
                source="agent_memory_v2/food_corrections.md",
                domain="food_drink",
                memory_type="preference",
            ),
            MemoryWrite(
                target_ref="old_code",
                text="Hermes project codename is Cedar Map, not Alpha Loom.",
                source="agent_memory_v2/project.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
        ],
    ),
    CalibrationCase(
        case_id="mild_same_domain_profile_addition",
        query="What does Victor value when information is presented?",
        condition_name="standard_budget144",
        target_behavior="protect",
        expected_hard=False,
        notes="Compatible same-domain additions should not be treated like stale correction pressure.",
        teaches=[
            MemoryWrite(
                text="Victor values source clarity and transparency when information is presented.",
                source="agent_memory_v1/user_profile.md",
                domain="agent_memory",
                memory_type="preference",
            ),
            MemoryWrite(
                text="Victor also values concise summaries with clear citations.",
                source="agent_memory_v2/user_profile.md",
                domain="agent_memory",
                memory_type="preference",
            ),
        ],
    ),
    CalibrationCase(
        case_id="same_domain_project_mild_update_no_correction",
        query="What is the Hermes project status?",
        condition_name="standard_budget144",
        target_behavior="protect",
        expected_hard=False,
        notes="Same-domain project updates without explicit supersession should remain protected.",
        teaches=[
            MemoryWrite(
                text="Hermes project status: selector calibration is in progress.",
                source="agent_memory_v1/project.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
            MemoryWrite(
                text="Hermes project status update: retrieval guard pressure testing is now being added.",
                source="agent_memory_v2/project.md",
                domain="agent_memory",
                memory_type="semantic_note",
            ),
        ],
    ),
    CalibrationCase(
        case_id="direct_tool_rule_correction",
        query="What radar tool should Victor use?",
        condition_name="hard_budget144",
        target_behavior="aggressive",
        expected_hard=True,
        notes="A direct procedure correction should still force verified refresh.",
        teaches=[
            MemoryWrite(
                ref="old_tool",
                text="For radar checks, Victor should use a visual canvas guessing method.",
                source="agent_memory_v1/tool_rules.md",
                domain="agent_memory",
                memory_type="procedure",
            )
        ],
        corrections=[
            MemoryWrite(
                target_ref="old_tool",
                text="For radar checks, Victor should use the AccuWeather URL, not visual canvas guessing.",
                source="agent_memory_v2/tool_rules.md",
                domain="agent_memory",
                memory_type="procedure",
            )
        ],
    ),
    CalibrationCase(
        case_id="deep_chain_preference_correction",
        query="What drink does Victor currently prefer?",
        condition_name="hard_budget144",
        target_behavior="aggressive",
        expected_hard=True,
        notes="A deeper correction chain should not be pulled back to periodic by sparse learned votes.",
        teaches=[
            MemoryWrite(
                ref="drink_v1",
                text="Victor currently prefers espresso.",
                source="agent_memory_v1/preferences.md",
                domain="food_drink",
                memory_type="preference",
            )
        ],
        corrections=[
            MemoryWrite(
                ref="drink_v2",
                target_ref="drink_v1",
                text="Victor currently prefers green tea, not espresso.",
                source="agent_memory_v2/preferences.md",
                domain="food_drink",
                memory_type="preference",
            ),
            MemoryWrite(
                ref="drink_v3",
                target_ref="drink_v2",
                text="Victor currently prefers water, not green tea.",
                source="agent_memory_v3/preferences.md",
                domain="food_drink",
                memory_type="preference",
            ),
            MemoryWrite(
                target_ref="drink_v3",
                text="Victor currently prefers sparkling water, not plain water.",
                source="agent_memory_v4/preferences.md",
                domain="food_drink",
                memory_type="preference",
            ),
        ],
    ),
    CalibrationCase(
        case_id="clean_long_context_with_many_unrelated_notes",
        query="What does CSD help detect?",
        condition_name="long2_standard_budget288",
        target_behavior="protect",
        expected_hard=False,
        notes="Long clean context with unrelated notes should avoid aggressive refresh.",
        teaches=[
            MemoryWrite(
                text="CSD helps detect novelty, contradiction pressure, semantic density, and domain shift.",
                source="agent_memory_v1/csd.md",
                domain="CSD",
                memory_type="semantic_note",
            ),
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
]


def write_markdown(report: dict[str, object], out_md: Path) -> None:
    rows = report["cases"]
    lines = [
        "# Selector Retrieval Guard Pressure Eval",
        "",
        f"Overall alignment: **{report['alignment_rate']:.3f}**",
        f"Cases aligned: **{report['aligned_cases']} / {report['case_count']}**",
        f"Embedding backend: `{report['embedding_backend']}`",
        "",
        "| Case | Target | Expected Hard | Actual Hard | Policy | Guard | Aligned | Stale Ratio | Top State | Stale Gap |",
        "|---|---|---:|---:|---|---|---:|---:|---|---:|",
    ]
    for row in rows:
        diagnostics = row["diagnostics"]
        guard = row.get("retrieval_guard") or {}
        lines.append(
            "| {case_id} | {target} | {expected} | {hard} | `{policy}` | {guard} | {aligned} | {stale_ratio} | `{top_state}` | {stale_gap} |".format(
                case_id=row["case_id"],
                target=row["target_behavior"],
                expected=row["expected_hard"],
                hard=diagnostics["hard"],
                policy=row["decision"]["policy"],
                guard="yes" if guard.get("applied") else "no",
                aligned="yes" if row["aligned"] else "no",
                stale_ratio=diagnostics["stale_ratio"],
                top_state=diagnostics.get("top_authority_state", "unknown"),
                stale_gap=diagnostics.get("stale_score_gap", 0.0),
            )
        )
    mismatches = [row for row in rows if not row["aligned"]]
    lines.extend(["", "## Mismatches", ""])
    if not mismatches:
        lines.append("- None")
    for row in mismatches:
        lines.append(
            f"- `{row['case_id']}` expected `{row['target_behavior']}` with hard `{row['expected_hard']}`, "
            f"got `{row['decision']['policy']}` with hard `{row['diagnostics']['hard']}`."
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pressure test retrieval-aware selector guards.")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--embedding-backend", choices=["hash", "config"], default="hash")
    args = parser.parse_args()

    out_json, out_md = output_paths(args.embedding_backend)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    case_reports = [
        run_case(case, top_k=args.top_k, embedding_backend=args.embedding_backend)
        for case in PRESSURE_CASES
    ]
    aligned_cases = sum(1 for row in case_reports if row["aligned"])
    report = {
        "ok": True,
        "purpose": "Pressure test retrieval-aware guards on irrelevant stale clutter, mild updates, and deep corrections.",
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
