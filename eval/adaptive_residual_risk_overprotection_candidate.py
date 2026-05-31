from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.adaptive_residual_risk_logged_eval import build_report as build_logged_risk_report  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_risk_overprotection_candidate_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_risk_overprotection_candidate_report.md"
DEFAULT_LOG = REPO_ROOT / "experiments" / "adaptive_residual_shadow_seventh_agent_style_outcomes.jsonl"


STOPWORDS = {
    "about",
    "after",
    "current",
    "does",
    "from",
    "handles",
    "hermes",
    "how",
    "one",
    "query",
    "replay",
    "should",
    "suppressed",
    "suppressor",
    "the",
    "this",
    "what",
    "which",
    "with",
}


def tokens(text: str) -> list[str]:
    return [tok for tok in re.findall(r"[a-z0-9][a-z0-9-]+", text.lower()) if tok not in STOPWORDS and len(tok) > 2]


def phrase_candidates(query: str) -> list[str]:
    parts = tokens(query)
    phrases = []
    phrases.extend(parts)
    phrases.extend(" ".join(parts[idx : idx + 2]) for idx in range(max(0, len(parts) - 1)))
    phrases.extend(" ".join(parts[idx : idx + 3]) for idx in range(max(0, len(parts) - 2)))
    return [phrase for phrase in phrases if phrase]


def build_candidate(log_path: Path = DEFAULT_LOG) -> dict[str, Any]:
    logged = build_logged_risk_report(log_path)
    examples = logged.get("term_overprotection_examples") if isinstance(logged.get("term_overprotection_examples"), list) else []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    phrase_counts: Counter[str] = Counter()
    for row in examples:
        if not isinstance(row, dict):
            continue
        term_label = str(row.get("term_risk_label") or "")
        grouped[term_label].append(row)
        for phrase in phrase_candidates(str(row.get("query") or "")):
            phrase_counts[phrase] += 1
    candidate_groups = []
    for term_label, rows in sorted(grouped.items()):
        shared_phrases = [
            {"phrase": phrase, "count": count}
            for phrase, count in phrase_counts.most_common(12)
            if count > 1 or len(rows) == 1
        ][:8]
        candidate_groups.append(
            {
                "term_risk_label": term_label,
                "example_count": len(rows),
                "candidate_context": "safe_meta_development_query",
                "candidate_action": "learned_contextual_exception_candidate",
                "shared_phrases": shared_phrases,
                "examples": rows[:8],
            }
        )
    checks = {
        "logged_risk_eval_ok": bool(logged.get("ok")),
        "has_or_cleanly_absent_candidates": bool(candidate_groups) or int(logged.get("term_overprotection_count") or 0) == 0,
        "report_only": True,
        "no_runtime_mutation": True,
        "no_config_mutation": True,
        "auto_apply_blocked": True,
        "requires_recurrence_before_promotion": True,
    }
    return {
        "schema": "adaptive_residual_risk_overprotection_candidate/v1",
        "description": "Review-only candidates for replacing broad term suppressor overprotection with learned contextual exceptions.",
        "ok": all(checks.values()),
        "checks": checks,
        "source_log": str(log_path),
        "term_overprotection_count": int(logged.get("term_overprotection_count") or 0),
        "candidate_group_count": len(candidate_groups),
        "candidate_groups": candidate_groups,
        "recommendation": "collect_recurrence_before_config_or_runtime_change" if candidate_groups else "no_overprotection_candidates",
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "promotion_ready": False,
        "promotion_blocker": "requires recurring safe-overprotected patterns across independent logs",
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Risk Overprotection Candidate\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Term overprotection count: `{report['term_overprotection_count']}`\n"
        + f"Candidate groups: `{report['candidate_group_count']}`\n"
        + f"Recommendation: `{report['recommendation']}`\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Candidate Groups\n\n```json\n"
        + json.dumps(report["candidate_groups"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    report = build_candidate()
    write_report(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "term_overprotection": report["term_overprotection_count"],
                "candidate_groups": report["candidate_group_count"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
