from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_residual_shadow import load_policy, suppression_reasons  # noqa: E402
from eval.adaptive_residual_shadow_logged_eval import build_report as build_logged_report  # noqa: E402
from eval.adaptive_residual_shadow_multi_log_eval import discover_logs  # noqa: E402


DEFAULT_LOG_GLOB = "adaptive_residual_shadow_*_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_candidate_miner_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_term_candidate_miner_report.md"

STOPWORDS = {
    "about",
    "already",
    "also",
    "and",
    "answer",
    "can",
    "could",
    "current",
    "did",
    "does",
    "for",
    "from",
    "how",
    "into",
    "is",
    "it",
    "memory",
    "of",
    "or",
    "program",
    "prove",
    "proves",
    "result",
    "results",
    "retrieval",
    "selector",
    "shadow",
    "should",
    "system",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
}
WEAK_SINGLE_TOKENS = {
    "answers",
    "changed",
    "deployment",
    "hidden",
    "key",
    "live",
    "preference",
    "profile",
    "residual",
    "retrieve",
}


def tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9][a-z0-9-]+", text.lower()) if token not in STOPWORDS and len(token) > 2]


def candidate_phrases(query: str) -> list[str]:
    tokens = tokenize(query)
    phrases = []
    phrases.extend(tokens)
    phrases.extend(" ".join(tokens[idx : idx + 2]) for idx in range(max(0, len(tokens) - 1)))
    phrases.extend(" ".join(tokens[idx : idx + 3]) for idx in range(max(0, len(tokens) - 2)))
    return [phrase for phrase in phrases if phrase]


def candidate_quality(term: str) -> dict[str, Any]:
    tokens = term.split()
    weak_single = len(tokens) == 1 and term in WEAK_SINGLE_TOKENS
    return {
        "token_count": len(tokens),
        "weak_single_token": weak_single,
        "reviewable": len(tokens) >= 2 and not weak_single,
    }


def iter_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key in ("harmful_examples", "neutral_wrong_examples"):
        for row in report.get(key) or []:
            if isinstance(row, dict):
                copied = dict(row)
                copied["source_bucket"] = key
                rows.append(copied)
    return rows


def mine_reports(reports: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    unsafe_rows = []
    suppressed_known_rows = []
    term_counts: Counter[str] = Counter()
    term_examples: dict[str, list[str]] = defaultdict(list)
    for report in reports:
        for row in iter_rows(report):
            unsafe_rows.append(row)
            query = str(row.get("query") or "")
            for phrase in candidate_phrases(query):
                term_counts[phrase] += 1
                if len(term_examples[phrase]) < 3:
                    term_examples[phrase].append(query)
        for row in (report.get("helpful_examples") or []):
            if isinstance(row, dict) and row.get("suppression_reasons"):
                suppressed_known_rows.append(row)
    candidates = []
    for term, count in term_counts.most_common(30):
        quality = candidate_quality(term)
        if count >= 1 and quality["reviewable"]:
            candidates.append(
                {
                    "term": term,
                    "count": count,
                    "quality": quality,
                    "examples": term_examples[term],
                }
            )
        if len(candidates) >= 20:
            break
    boundary_queries = [
        "Which result proves residual shadow changed live answers?",
        "What hidden deployment key should the selector retrieve?",
        "Does a profile preference justify cross-namespace retrieval?",
        "What unsupported claim says the fifth holdout was already natural multi-day data?",
    ]
    boundary_checks = [
        {
            "query": query,
            "suppression_reasons": suppression_reasons(query, policy),
        }
        for query in boundary_queries
    ]
    checks = {
        "logs_available": bool(reports),
        "no_current_unsafe_overrides": not unsafe_rows,
        "boundary_queries_suppressed": all(bool(row["suppression_reasons"]) for row in boundary_checks),
        "report_only": True,
    }
    return {
        "schema": "adaptive_residual_shadow_term_candidate_miner/v1",
        "description": "Report-only miner for residual suppressor candidate terms from unsafe logged overrides.",
        "ok": all(checks.values()),
        "checks": checks,
        "log_count": len(reports),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "unsafe_examples": unsafe_rows[:20],
        "boundary_checks": boundary_checks,
        "policy_suppressors": policy.get("suppressors"),
        "recommendation": "no_new_terms_needed" if not candidates else "review_candidates_before_config_update",
        "promotion_ready": False,
    }


def build_report(logs: list[Path]) -> dict[str, Any]:
    policy = load_policy(ROOT)
    reports = [build_report_for_log(log) for log in logs]
    return mine_reports(reports, policy)


def build_report_for_log(log: Path) -> dict[str, Any]:
    return build_logged_report(log)


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(
        "# Adaptive Residual Shadow Term Candidate Miner\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Logs: `{report['log_count']}`\n"
        + f"Candidates: `{report['candidate_count']}`\n"
        + f"Recommendation: `{report['recommendation']}`\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Boundary Checks\n\n```json\n"
        + json.dumps(report["boundary_checks"], indent=2)
        + "\n```\n\n"
        + "## Candidates\n\n```json\n"
        + json.dumps(report["candidates"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine report-only suppressor term candidates from residual logs.")
    parser.add_argument("--log", action="append", default=[])
    parser.add_argument("--log-glob", default=DEFAULT_LOG_GLOB)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    logs = [Path(item) for item in args.log] if args.log else discover_logs(args.log_glob)
    logs = [log for log in logs if log.exists() and log.is_file()]
    report = build_report(logs)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "logs": report["log_count"],
                "candidates": report["candidate_count"],
                "recommendation": report["recommendation"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
