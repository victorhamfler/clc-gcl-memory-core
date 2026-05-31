from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_residual_shadow import (  # noqa: E402
    PROTECTED_LEARNED_RISK_LABELS,
    _train_risk_model,
    load_policy,
    suppression_reasons,
)
from eval.adaptive_residual_risk_scorer_eval import make_sample, predict  # noqa: E402


DEFAULT_HERMES_EVAL = REPO_ROOT / "experiments" / "hermes_learned_risk_residual_logged_eval_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_learned_risk_external_failure_replay_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_learned_risk_external_failure_replay_report.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def build_report(path: Path = DEFAULT_HERMES_EVAL) -> dict[str, Any]:
    source = read_json(path)
    policy = load_policy(ROOT)
    threshold = float(policy.get("learned_risk_confidence_threshold", 0.5))
    learned_veto_enabled = bool(policy.get("learned_risk_suppressor_enabled", True))
    model, sample_count, logged_sample_count = _train_risk_model(ROOT)
    harmful = [row for row in source.get("harmful_examples") or [] if isinstance(row, dict)]
    replay_rows = []
    for row in harmful:
        query = str(row.get("query") or "")
        reasons = suppression_reasons(query, policy)
        sample = make_sample(
            query,
            "other_symbolic_fallback",
            behavior_family=row.get("behavior_family"),
            feedback_label=row.get("feedback_label"),
            symbolic_advisory=row.get("symbolic_advisory"),
            report_only_advisory=row.get("report_only_advisory"),
            override_outcome=row.get("override_outcome"),
            would_override=False,
            source="hermes_external_failure_replay",
        )
        learned_risk_label, learned_risk_confidence = predict(model, sample)
        learned_risk_veto_now = (
            learned_veto_enabled
            and learned_risk_label in PROTECTED_LEARNED_RISK_LABELS
            and learned_risk_confidence >= threshold
        )
        replay_rows.append(
            {
                "query": query,
                "feedback_label": row.get("feedback_label"),
                "behavior_family": row.get("behavior_family"),
                "old_symbolic_advisory": row.get("symbolic_advisory"),
                "old_report_only_advisory": row.get("report_only_advisory"),
                "old_override_outcome": row.get("override_outcome"),
                "old_suppression_reasons": row.get("suppression_reasons"),
                "current_term_suppression_reasons": reasons,
                "learned_risk_label": learned_risk_label,
                "learned_risk_confidence": learned_risk_confidence,
                "learned_risk_veto_now": learned_risk_veto_now,
                "would_be_suppressed_now": bool(reasons) or learned_risk_veto_now,
            }
        )
    checks = {
        "source_eval_found": bool(source),
        "harmful_examples_found": bool(harmful),
        "risk_model_available": bool(model),
        "has_training_samples": sample_count > 0,
        "has_logged_samples": logged_sample_count > 0,
        "all_harmful_examples_suppressed_now": bool(replay_rows)
        and all(row["would_be_suppressed_now"] for row in replay_rows),
        "learned_risk_veto_used_for_at_least_one": any(row["learned_risk_veto_now"] for row in replay_rows),
        "report_only": True,
        "no_runtime_mutation": True,
        "no_config_mutation": True,
    }
    return {
        "schema": "adaptive_residual_learned_risk_external_failure_replay/v1",
        "description": "Replay Hermes harmful residual authority decisions against the current learned-risk veto.",
        "ok": all(checks.values()),
        "source_eval": str(path),
        "sample_count": sample_count,
        "logged_sample_count": logged_sample_count,
        "threshold": threshold,
        "protected_labels": sorted(PROTECTED_LEARNED_RISK_LABELS),
        "checks": checks,
        "replay_rows": replay_rows,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
        "promotion_ready": False,
    }


def write_report(report: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Adaptive Residual Learned Risk External Failure Replay\n\n"
        + f"Passed: **{report['ok']}**\n"
        + f"Samples: `{report['sample_count']}` logged `{report['logged_sample_count']}`\n"
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
