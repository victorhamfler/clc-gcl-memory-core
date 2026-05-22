from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.mine_retrieval_signal_candidates import build_report  # noqa: E402


FIXTURE = ROOT / "test_corpora" / "retrieval_signal_redundant_marker_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "retrieval_signal_miner_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "retrieval_signal_miner_regression_report.md"


def main() -> int:
    report = build_report(FIXTURE)
    support = report.get("support") or {}
    checks = {
        "existing_broad_policy_source_not_mined": "broad_policy_note" not in (support.get("broad_sources") or {}),
        "existing_broad_policy_prefix_not_mined": "broad policy note" not in (support.get("broad_prefixes") or {}),
        "no_candidate_sections": report.get("candidate_count") == 0,
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "fixture": str(FIXTURE),
        "candidate_count": report.get("candidate_count"),
        "support": support,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Retrieval Signal Miner Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "\n".join(f"- {name}: `{ok}`" for name, ok in checks.items())
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
