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
from core.evidence_states import (  # noqa: E402
    classify_memory_state,
    evidence_is_too_weak,
    normalize_evidence_state_config,
    parse_term_sequence,
    requires_sensitive_evidence,
)


DEFAULT_CANDIDATES = ROOT / "test_corpora" / "evidence_state_candidates_v1.json"
OUT_JSON = REPO_ROOT / "experiments" / "evidence_state_candidate_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "evidence_state_candidate_eval_report.md"


def term_list(value: Any) -> list[str]:
    return list(parse_term_sequence(value))


def append_terms(current: Any, additions: Any) -> list[str]:
    out = term_list(current)
    for term in term_list(additions):
        if term not in out:
            out.append(term)
    return out


def row(**kwargs: Any) -> dict[str, Any]:
    out = {
        "score": 0.5,
        "text_match_score": 0.5,
        "intent_match_score": 0.0,
        "supersession_score": 0.0,
        "relation_supersession_score": 0.0,
        "summary_relation_score": 0.0,
        "feedback_score": 0.0,
        "text": "Historical note.",
        "authority_state": "",
    }
    out.update(kwargs)
    return out


def build_candidate_config(base_config: dict[str, Any], candidate_report: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base_config or {})
    out.setdefault("weak_evidence", {})

    for candidate in candidate_report.get("candidates") or []:
        section = str(candidate.get("section") or "").strip().lower()
        if section == "stale_language":
            out["stale_language_terms"] = append_terms(out.get("stale_language_terms"), candidate.get("terms"))
            if "stale_regex" in candidate:
                out["stale_regex"] = candidate["stale_regex"]
        elif section == "correction_language":
            out["correction_language_terms"] = append_terms(
                out.get("correction_language_terms"),
                candidate.get("terms"),
            )
        elif section == "sensitive_lookup":
            out["sensitive_lookup_terms"] = append_terms(out.get("sensitive_lookup_terms"), candidate.get("terms"))
        elif section == "thresholds":
            for key in (
                "current_threshold",
                "stale_threshold",
                "stale_feedback_threshold",
                "disputed_feedback_threshold",
            ):
                if key in candidate:
                    out[key] = candidate[key]
        elif section == "weak_evidence":
            weak = out.setdefault("weak_evidence", {})
            for key in (
                "score_threshold",
                "text_match_threshold",
                "intent_match_threshold",
                "intent_text_match_threshold",
            ):
                if key in candidate:
                    weak[key] = candidate[key]
    return normalize_evidence_state_config(out)


def validate_config(config: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key in ("current_threshold", "stale_threshold", "stale_feedback_threshold", "disputed_feedback_threshold"):
        value = float(config[key])
        if not -1.0 <= value <= 1.0:
            failures.append(f"{key}_out_of_range")
    weak = config["weak_evidence"]
    for key in ("score_threshold", "text_match_threshold", "intent_match_threshold", "intent_text_match_threshold"):
        value = float(weak[key])
        if not 0.0 <= value <= 1.0:
            failures.append(f"weak_evidence.{key}_out_of_range")
    if not config["stale_language_terms"]:
        failures.append("stale_language_terms_empty")
    if not config["correction_language_terms"]:
        failures.append("correction_language_terms_empty")
    if not config["sensitive_lookup_terms"]:
        failures.append("sensitive_lookup_terms_empty")
    return failures


def added_terms(base_terms: Any, candidate_terms: Any) -> list[str]:
    base = set(term_list(base_terms))
    return [term for term in term_list(candidate_terms) if term not in base]


def run_checks(base_config: dict[str, Any], candidate_config: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [
        {
            "id": "default_authority_current_preserved",
            "passed": classify_memory_state(row(authority_state="current"), candidate_config) == "current",
            "kind": "preserve",
        },
        {
            "id": "default_superseded_preserved",
            "passed": classify_memory_state(row(authority_state="superseded"), candidate_config) == "stale",
            "kind": "preserve",
        },
        {
            "id": "default_correction_language_preserved",
            "passed": classify_memory_state(row(text="Correction: use the current policy."), candidate_config)
            == "current",
            "kind": "preserve",
        },
        {
            "id": "default_sensitive_lookup_preserved",
            "passed": requires_sensitive_evidence("What is the private routing key?", config=candidate_config),
            "kind": "preserve",
        },
    ]

    for term in added_terms(base_config["stale_language_terms"], candidate_config["stale_language_terms"]):
        text = f"This note is {term} for the deployment rule."
        checks.append(
            {
                "id": f"candidate_stale_language_activates:{term}",
                "passed": (
                    classify_memory_state(row(text=text), base_config) != "stale"
                    and classify_memory_state(row(text=text), candidate_config) == "stale"
                ),
                "kind": "candidate_activation",
            }
        )

    for term in added_terms(base_config["correction_language_terms"], candidate_config["correction_language_terms"]):
        text = f"{term} use the new deployment rule."
        checks.append(
            {
                "id": f"candidate_correction_language_activates:{term}",
                "passed": (
                    classify_memory_state(row(text=text), base_config) != "current"
                    and classify_memory_state(row(text=text), candidate_config) == "current"
                ),
                "kind": "candidate_activation",
            }
        )

    for term in added_terms(base_config["sensitive_lookup_terms"], candidate_config["sensitive_lookup_terms"]):
        checks.append(
            {
                "id": f"candidate_sensitive_lookup_activates:{term}",
                "passed": (
                    not requires_sensitive_evidence(f"What is the {term} value?", config=base_config)
                    and requires_sensitive_evidence(f"What is the {term} value?", config=candidate_config)
                ),
                "kind": "candidate_activation",
            }
        )

    base_weak = base_config["weak_evidence"]
    candidate_weak = candidate_config["weak_evidence"]
    if float(candidate_weak["score_threshold"]) > float(base_weak["score_threshold"]):
        probe_score = (float(candidate_weak["score_threshold"]) + float(base_weak["score_threshold"])) / 2.0
        evidence = [row(score=probe_score, text_match_score=0.1)]
        checks.append(
            {
                "id": "candidate_weak_score_threshold_activates",
                "passed": (
                    not evidence_is_too_weak(evidence, base_config)
                    and evidence_is_too_weak(evidence, candidate_config)
                ),
                "kind": "candidate_activation",
            }
        )

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
    base_config = normalize_evidence_state_config(config.get("evidence_states") or {})
    candidate_report = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate_config = build_candidate_config(base_config, candidate_report)
    validation_failures = validate_config(candidate_config)
    checks = run_checks(base_config, candidate_config)
    failures = [check["id"] for check in checks if not check["passed"]]
    return {
        "ok": not validation_failures and not failures,
        "candidate_path": str(candidate_path),
        "schema": candidate_report.get("schema"),
        "validation_failures": validation_failures,
        "failures": failures,
        "check_count": len(checks),
        "checks": checks,
        "base_config": base_config,
        "candidate_config": candidate_config,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Evidence State Candidate Eval",
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
    lines.extend(["", "## Candidate Config", "", "```json", json.dumps(report["candidate_config"], indent=2), "```"])
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate evidence-state config candidate artifacts.")
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
