from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from eval.mine_evidence_state_candidates import build_report  # noqa: E402


FIXTURE = ROOT / "test_corpora" / "evidence_state_sensitive_stop_terms_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "evidence_state_miner_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "evidence_state_miner_regression_report.md"


def main() -> int:
    report = build_report(FIXTURE)
    support = report.get("support") or {}
    sensitive_terms = set((support.get("sensitive_lookup") or {}).keys())
    held_out_terms = set((support.get("held_out_sensitive_lookup") or {}).keys())
    checks = {
        "auxiliary_does_not_mined": "does" not in sensitive_terms,
        "ambiguous_live_not_mined": "live" not in sensitive_terms,
        "ambiguous_live_held_out": "live" in held_out_terms,
        "drink_still_mined": "drink" in sensitive_terms,
        "prefer_still_mined": "prefer" in sensitive_terms,
        "candidate_section_present": report.get("candidate_count") == 1,
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
        "# Evidence State Miner Regression\n\n"
        + f"Passed: **{result['ok']}**\n\n"
        + "\n".join(f"- {name}: `{ok}`" for name, ok in checks.items())
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
