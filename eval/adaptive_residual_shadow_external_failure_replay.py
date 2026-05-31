from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_residual_shadow import load_policy, suppression_reasons  # noqa: E402


DEFAULT_HERMES_EVAL = REPO_ROOT / "experiments" / "hermes_adaptive_residual_shadow_external_logged_eval_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_external_failure_replay_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_external_failure_replay_report.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def build_report(path: Path = DEFAULT_HERMES_EVAL) -> dict[str, Any]:
    source = read_json(path)
    policy = load_policy(ROOT)
    harmful = [row for row in source.get("harmful_examples") or [] if isinstance(row, dict)]
    replay_rows = []
    for row in harmful:
        query = str(row.get("query") or "")
        reasons = suppression_reasons(query, policy)
        replay_rows.append(
            {
                "query": query,
                "feedback_label": row.get("feedback_label"),
                "behavior_family": row.get("behavior_family"),
                "old_report_only_advisory": row.get("report_only_advisory"),
                "old_override_outcome": row.get("override_outcome"),
                "current_suppression_reasons": reasons,
                "would_be_suppressed_now": bool(reasons),
            }
        )
    checks = {
        "source_eval_found": bool(source),
        "harmful_examples_found": bool(harmful),
        "all_harmful_examples_suppressed_now": bool(replay_rows) and all(row["would_be_suppressed_now"] for row in replay_rows),
        "report_only": True,
        "no_config_mutation": True,
        "no_runtime_mutation": True,
    }
    return {
        "schema": "adaptive_residual_shadow_external_failure_replay/v1",
        "description": "Replay known external harmful residual overrides against the current suppressor policy.",
        "ok": all(checks.values()),
        "source_eval": str(path),
        "checks": checks,
        "replay_rows": replay_rows,
        "promotion_ready": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Shadow External Failure Replay\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Promotion ready: `{report['promotion_ready']}`\n"
        + f"Source eval: `{report['source_eval']}`\n\n"
        + "## Checks\n\n```json\n"
        + json.dumps(report["checks"], indent=2)
        + "\n```\n\n"
        + "## Replay Rows\n\n```json\n"
        + json.dumps(report["replay_rows"], indent=2)
        + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    report = build_report()
    write_report(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "replayed": len(report["replay_rows"]),
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
