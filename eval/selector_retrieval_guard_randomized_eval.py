from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from selector_retrieval_calibration_eval import CalibrationCase, MemoryWrite, run_case  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "selector_retrieval_guard_randomized_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "selector_retrieval_guard_randomized_eval_report.md"


TARGET_FACTS = [
    (
        "gcl",
        "What does G-CL maintain?",
        "G-CL maintains domain geometry, anchor drift, curvature, and stability.",
        "G-CL",
        "semantic_note",
    ),
    (
        "csd",
        "What does CSD help detect?",
        "CSD helps detect novelty, contradiction pressure, semantic density, and domain shift.",
        "CSD",
        "semantic_note",
    ),
    (
        "weather",
        "What radar method should Victor use?",
        "Weather radar method for Victor: use the AccuWeather URL for radar checks.",
        "agent_memory",
        "procedure",
    ),
    (
        "presentation",
        "What does Victor value when information is presented?",
        "Victor values source clarity and transparency when information is presented.",
        "agent_memory",
        "preference",
    ),
    (
        "project",
        "What is the Hermes project codename?",
        "Hermes project codename is Cedar Map.",
        "agent_memory",
        "semantic_note",
    ),
]

TARGET_TOPIC_EXCLUSIONS = {
    "project": {"codename"},
    "weather": {"radar"},
}

CORRECTION_TOPICS = [
    (
        "drink",
        "What drink does Victor currently prefer?",
        "Victor currently prefers espresso.",
        "Victor currently prefers water, not espresso.",
        "food_drink",
        "preference",
    ),
    (
        "pizza",
        "What pizza does Victor currently prefer?",
        "Victor currently prefers mushroom pizza.",
        "Victor currently prefers cheese pizza, not mushroom pizza.",
        "food_drink",
        "preference",
    ),
    (
        "radar",
        "What radar tool should Victor use?",
        "For radar checks, Victor should use a visual canvas guessing method.",
        "For radar checks, Victor should use the AccuWeather URL, not visual canvas guessing.",
        "agent_memory",
        "procedure",
    ),
    (
        "codename",
        "What is the current Hermes project codename?",
        "Hermes project codename is Alpha Loom.",
        "Hermes project codename is Cedar Map, not Alpha Loom.",
        "agent_memory",
        "semantic_note",
    ),
    (
        "backend",
        "What embedding backend should Hermes use?",
        "Hermes should use a toy random embedding backend for production memory.",
        "Hermes should use the configured Gemma embedding backend, not a toy random backend.",
        "agent_memory",
        "procedure",
    ),
]

MILD_ADDITIONS = [
    (
        "profile",
        "What does Victor value when information is presented?",
        [
            "Victor values source clarity and transparency when information is presented.",
            "Victor also values concise summaries with clear citations.",
        ],
        "agent_memory",
        "preference",
    ),
    (
        "project_status",
        "What is the Hermes project status?",
        [
            "Hermes project status: selector calibration is in progress.",
            "Hermes project status update: retrieval guard pressure testing is being added.",
        ],
        "agent_memory",
        "semantic_note",
    ),
    (
        "csd_summary",
        "What does CSD help detect?",
        [
            "CSD helps detect novelty, contradiction pressure, semantic density, and domain shift.",
            "CSD diagnostics can also expose stale/current evidence pressure.",
        ],
        "CSD",
        "semantic_note",
    ),
]


def output_paths(embedding_backend: str, seed: int, cases: int) -> tuple[Path, Path]:
    suffix = "" if embedding_backend == "hash" else f"_{embedding_backend}"
    stem = f"selector_retrieval_guard_randomized_eval{suffix}_seed{seed}_n{cases}"
    return REPO_ROOT / "experiments" / f"{stem}_results.json", REPO_ROOT / "experiments" / f"{stem}_report.md"


def safe_id(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_")


def make_direct_case(index: int, rng: random.Random) -> CalibrationCase:
    topic, query, old, new, domain, memory_type = rng.choice(CORRECTION_TOPICS)
    return CalibrationCase(
        case_id=f"random_direct_{index:02d}_{topic}",
        query=query,
        condition_name="hard_budget144",
        target_behavior="aggressive",
        expected_hard=True,
        notes="Random direct stale/current correction.",
        teaches=[
            MemoryWrite(
                ref="old",
                text=old,
                source=f"agent_memory_v1/{topic}.md",
                domain=domain,
                memory_type=memory_type,
            )
        ],
        corrections=[
            MemoryWrite(
                target_ref="old",
                text=new,
                source=f"agent_memory_v2/{topic}.md",
                domain=domain,
                memory_type=memory_type,
            )
        ],
    )


def make_chain_case(index: int, rng: random.Random) -> CalibrationCase:
    topic, query, old, first_new, domain, memory_type = rng.choice(CORRECTION_TOPICS)
    middle = first_new
    final = first_new
    if topic == "drink":
        middle = "Victor currently prefers green tea, not espresso."
        final = "Victor currently prefers sparkling water, not green tea."
    elif topic == "pizza":
        middle = "Victor currently prefers pepperoni pizza, not mushroom pizza."
        final = "Victor currently prefers cheese pizza, not pepperoni pizza."
    elif topic == "codename":
        middle = "Hermes project codename is Cedar Map, not Alpha Loom."
        final = "Hermes project codename is Cedar Map with retrieval guards enabled."
    elif topic == "radar":
        middle = "For radar checks, Victor should use a browser search workflow, not canvas guessing."
        final = "For radar checks, Victor should use the AccuWeather URL, not a generic browser search workflow."
    elif topic == "backend":
        middle = "Hermes should use the configured Gemma embedding backend, not a toy random backend."
        final = "Hermes should use the configured Gemma embedding backend with retrieval guards enabled."
    return CalibrationCase(
        case_id=f"random_chain_{index:02d}_{topic}",
        query=query,
        condition_name="hard_budget144",
        target_behavior="aggressive",
        expected_hard=True,
        notes="Random correction chain.",
        teaches=[
            MemoryWrite(ref="old", text=old, source=f"agent_memory_v1/{topic}.md", domain=domain, memory_type=memory_type)
        ],
        corrections=[
            MemoryWrite(
                ref="mid",
                target_ref="old",
                text=middle,
                source=f"agent_memory_v2/{topic}.md",
                domain=domain,
                memory_type=memory_type,
            ),
            MemoryWrite(
                target_ref="mid",
                text=final,
                source=f"agent_memory_v3/{topic}.md",
                domain=domain,
                memory_type=memory_type,
            ),
        ],
    )


def make_mild_case(index: int, rng: random.Random) -> CalibrationCase:
    topic, query, texts, domain, memory_type = rng.choice(MILD_ADDITIONS)
    shuffled = list(texts)
    rng.shuffle(shuffled)
    return CalibrationCase(
        case_id=f"random_mild_{index:02d}_{topic}",
        query=query,
        condition_name=rng.choice(["standard_budget144", "long2_standard_budget288"]),
        target_behavior="protect",
        expected_hard=False,
        notes="Random compatible same-domain addition.",
        teaches=[
            MemoryWrite(
                text=text,
                source=f"agent_memory_v{n + 1}/{topic}.md",
                domain=domain,
                memory_type=memory_type,
            )
            for n, text in enumerate(shuffled)
        ],
    )


def make_irrelevant_stale_case(index: int, rng: random.Random) -> CalibrationCase:
    target_id, query, target_text, target_domain, target_type = rng.choice(TARGET_FACTS)
    exclusions = TARGET_TOPIC_EXCLUSIONS.get(target_id, set())
    candidate_topics = [topic for topic in CORRECTION_TOPICS if topic[0] not in exclusions]
    stale_topics = rng.sample(candidate_topics, k=rng.randint(1, min(4, len(candidate_topics))))
    teaches = [
        MemoryWrite(
            text=target_text,
            source=f"agent_memory_v1/{target_id}.md",
            domain=target_domain,
            memory_type=target_type,
        )
    ]
    corrections = []
    for topic, _topic_query, old, new, domain, memory_type in stale_topics:
        ref = f"old_{safe_id(topic)}"
        teaches.append(
            MemoryWrite(
                ref=ref,
                text=old,
                source=f"agent_memory_v1/{topic}.md",
                domain=domain,
                memory_type=memory_type,
            )
        )
        corrections.append(
            MemoryWrite(
                target_ref=ref,
                text=new,
                source=f"agent_memory_v2/{topic}.md",
                domain=domain,
                memory_type=memory_type,
            )
        )
    return CalibrationCase(
        case_id=f"random_irrelevant_{index:02d}_{target_id}_{len(stale_topics)}stale",
        query=query,
        condition_name=rng.choice(["standard_budget144", "long2_standard_budget288"]),
        target_behavior="protect",
        expected_hard=False,
        notes="Random clean target with unrelated stale correction clutter.",
        teaches=teaches,
        corrections=corrections,
    )


def generate_cases(seed: int, case_count: int) -> list[CalibrationCase]:
    rng = random.Random(seed)
    makers = [make_direct_case, make_chain_case, make_mild_case, make_irrelevant_stale_case]
    cases = []
    for index in range(case_count):
        maker = makers[index % len(makers)]
        cases.append(maker(index, rng))
    rng.shuffle(cases)
    return cases


def write_markdown(report: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Selector Retrieval Guard Randomized Eval",
        "",
        f"Seed: `{report['seed']}`",
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
    mismatches = [row for row in report["cases"] if not row["aligned"]]
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
    parser = argparse.ArgumentParser(description="Randomized pressure test for retrieval-aware selector guards.")
    parser.add_argument("--seed", type=int, default=20260519)
    parser.add_argument("--cases", type=int, default=32)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--embedding-backend", choices=["hash", "config"], default="hash")
    args = parser.parse_args()

    out_json, out_md = output_paths(args.embedding_backend, args.seed, args.cases)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    generated = generate_cases(args.seed, args.cases)
    case_reports = [run_case(case, top_k=args.top_k, embedding_backend=args.embedding_backend) for case in generated]
    aligned_cases = sum(1 for row in case_reports if row["aligned"])
    report = {
        "ok": True,
        "purpose": "Randomized retrieval guard pressure test across corrections, chains, mild updates, and stale clutter.",
        "seed": args.seed,
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
                "seed": report["seed"],
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
