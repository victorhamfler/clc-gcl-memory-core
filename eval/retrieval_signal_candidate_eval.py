from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.retrieval_signals import RetrievalSignalScorer, normalize_retrieval_signal_config, parse_term_sequence  # noqa: E402


DEFAULT_CANDIDATES = ROOT / "test_corpora" / "retrieval_signal_candidates_v1.json"
OUT_JSON = REPO_ROOT / "experiments" / "retrieval_signal_candidate_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "retrieval_signal_candidate_eval_report.md"


def term_list(value: Any) -> list[str]:
    return list(parse_term_sequence(value))


def append_terms(current: Any, additions: Any) -> list[str]:
    out = term_list(current)
    for term in term_list(additions):
        if term not in out:
            out.append(term)
    return out


def build_candidate_config(base_config: dict[str, Any], candidate_report: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base_config or {})
    out.setdefault("broad_generic", {})
    out.setdefault("scope_deflection", {})
    out.setdefault("correction_relevance", {})

    for candidate in candidate_report.get("candidates") or []:
        section = str(candidate.get("section") or "").strip().lower()
        if section == "broad_generic":
            target = out["broad_generic"]
            target["source_contains"] = append_terms(target.get("source_contains"), candidate.get("source_contains"))
            target["text_prefixes"] = append_terms(target.get("text_prefixes"), candidate.get("text_prefixes"))
            if "penalty" in candidate:
                target["penalty"] = candidate["penalty"]
        elif section == "scope_deflection":
            target = out["scope_deflection"]
            target["query_terms"] = append_terms(target.get("query_terms"), candidate.get("query_terms"))
            target["correction_prefixes"] = append_terms(
                target.get("correction_prefixes"),
                candidate.get("correction_prefixes"),
            )
            target["text_markers"] = append_terms(target.get("text_markers"), candidate.get("text_markers"))
            if "penalty" in candidate:
                target["penalty"] = candidate["penalty"]
        elif section == "correction_relevance":
            target = out["correction_relevance"]
            for key in ("match_threshold", "min_relevance"):
                if key in candidate:
                    target[key] = candidate[key]
    return normalize_retrieval_signal_config(out)


def validate_config(config: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    broad_penalty = float(config["broad_generic"]["penalty"])
    scope_penalty = float(config["scope_deflection"]["penalty"])
    match_threshold = float(config["correction_relevance"]["match_threshold"])
    min_relevance = float(config["correction_relevance"]["min_relevance"])
    if not 0.0 <= broad_penalty <= 1.0:
        failures.append("broad_generic.penalty_out_of_range")
    if not 0.0 <= scope_penalty <= 1.0:
        failures.append("scope_deflection.penalty_out_of_range")
    if not 0.0 <= match_threshold <= 1.0:
        failures.append("correction_relevance.match_threshold_out_of_range")
    if not 0.0 <= min_relevance <= 1.0:
        failures.append("correction_relevance.min_relevance_out_of_range")
    if not config["scope_deflection"]["query_terms"]:
        failures.append("scope_deflection.query_terms_empty")
    if not config["scope_deflection"]["text_markers"]:
        failures.append("scope_deflection.text_markers_empty")
    return failures


def run_checks(base_scorer: RetrievalSignalScorer, candidate_scorer: RetrievalSignalScorer) -> list[dict[str, Any]]:
    checks = [
        {
            "id": "default_broad_generic_preserved",
            "passed": candidate_scorer.broad_generic_note(
                "Broad policy note: approvals should be documented.",
                "notes/broad_policy.md",
            ),
            "kind": "preserve",
        },
        {
            "id": "default_scope_deflection_preserved",
            "passed": candidate_scorer.scope_deflection_note(
                "Can I upload this repository to GitHub?",
                "Correction: this is not upload permission. It is a separate policy note.",
                "correction/github.md",
            ),
            "kind": "preserve",
        },
        {
            "id": "default_correction_relevance_preserved",
            "passed": candidate_scorer.correction_relevance(
                {"authority_state": "current"},
                0.7,
                0.0,
                0.2,
                0.3,
            )
            == 0.3,
            "kind": "preserve",
        },
    ]
    checks.extend(dynamic_candidate_checks(base_scorer, candidate_scorer))
    return checks


def added_terms(base_terms: Any, candidate_terms: Any) -> list[str]:
    base = set(term_list(base_terms))
    return [term for term in term_list(candidate_terms) if term not in base]


def dynamic_candidate_checks(
    base_scorer: RetrievalSignalScorer,
    candidate_scorer: RetrievalSignalScorer,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    base_cfg = base_scorer.signal_config
    candidate_cfg = candidate_scorer.signal_config

    for marker in added_terms(
        base_cfg["broad_generic"]["source_contains"],
        candidate_cfg["broad_generic"]["source_contains"],
    ):
        source = f"notes/{marker}.md"
        checks.append(
            {
                "id": f"candidate_broad_generic_source_activates:{marker}",
                "passed": (
                    not base_scorer.broad_generic_note("Operational note.", source)
                    and candidate_scorer.broad_generic_note("Operational note.", source)
                ),
                "kind": "candidate_activation",
            }
        )

    for prefix in added_terms(
        base_cfg["broad_generic"]["text_prefixes"],
        candidate_cfg["broad_generic"]["text_prefixes"],
    ):
        text = f"{prefix}: approvals are logged."
        checks.append(
            {
                "id": f"candidate_broad_generic_prefix_activates:{prefix}",
                "passed": (
                    not base_scorer.broad_generic_note(text, "notes/candidate.md")
                    and candidate_scorer.broad_generic_note(text, "notes/candidate.md")
                ),
                "kind": "candidate_activation",
            }
        )

    added_query_terms = added_terms(
        base_cfg["scope_deflection"]["query_terms"],
        candidate_cfg["scope_deflection"]["query_terms"],
    )
    added_markers = added_terms(
        base_cfg["scope_deflection"]["text_markers"],
        candidate_cfg["scope_deflection"]["text_markers"],
    )
    for query_term in added_query_terms:
        for marker in added_markers or list(candidate_cfg["scope_deflection"]["text_markers"])[:1]:
            query = f"Can I {query_term} the repository?"
            text = f"Correction: this is {marker}."
            checks.append(
                {
                    "id": f"candidate_scope_deflection_activates:{query_term}:{marker}",
                    "passed": (
                        not base_scorer.scope_deflection_note(query, text, "correction/candidate.md")
                        and candidate_scorer.scope_deflection_note(query, text, "correction/candidate.md")
                    ),
                    "kind": "candidate_activation",
                }
            )
            checks.append(
                {
                    "id": f"candidate_scope_deflection_does_not_overactivate:{query_term}",
                    "passed": not candidate_scorer.scope_deflection_note(
                        query,
                        f"Correction: {query_term} is approved after explicit confirmation.",
                        "correction/candidate.md",
                    ),
                    "kind": "safety",
                }
            )
            break

    if not any(check["kind"] == "candidate_activation" for check in checks):
        checks.append(
            {
                "id": "candidate_has_no_new_activation_terms",
                "passed": True,
                "kind": "informational",
            }
        )
    return checks


def evaluate(candidate_path: Path) -> dict[str, Any]:
    config = load_config(ROOT)
    base_signal_config = normalize_retrieval_signal_config(config.get("retrieval_signals") or {})
    candidate_report = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate_signal_config = build_candidate_config(base_signal_config, candidate_report)
    validation_failures = validate_config(candidate_signal_config)

    base_scorer = RetrievalSignalScorer(signal_config=base_signal_config)
    candidate_scorer = RetrievalSignalScorer(signal_config=candidate_signal_config)
    checks = run_checks(base_scorer, candidate_scorer)
    failures = [check["id"] for check in checks if not check["passed"]]
    return {
        "ok": not validation_failures and not failures,
        "candidate_path": str(candidate_path),
        "schema": candidate_report.get("schema"),
        "validation_failures": validation_failures,
        "failures": failures,
        "check_count": len(checks),
        "checks": checks,
        "base_config": base_signal_config,
        "candidate_config": candidate_signal_config,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Retrieval Signal Candidate Eval",
        "",
        f"Passed: **{report['ok']}**",
        f"Candidate file: `{report['candidate_path']}`",
        f"Schema: `{report['schema']}`",
        f"Validation failures: `{', '.join(report['validation_failures']) or 'none'}`",
        f"Check failures: `{', '.join(report['failures']) or 'none'}`",
        "",
        "| check | kind | pass |",
        "| --- | --- | --- |",
    ]
    for check in report["checks"]:
        lines.append(f"| `{check['id']}` | `{check['kind']}` | `{check['passed']}` |")
    lines.extend(
        [
            "",
            "## Candidate Config",
            "",
            "```json",
            json.dumps(report["candidate_config"], indent=2),
            "```",
        ]
    )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate retrieval-signal config candidate artifacts.")
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = evaluate(Path(args.candidates))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "check_count": report["check_count"],
                "validation_failures": report["validation_failures"],
                "failures": report["failures"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
