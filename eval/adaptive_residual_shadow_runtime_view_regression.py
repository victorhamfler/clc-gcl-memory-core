from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_residual_shadow import normalize_adaptive_residual_shadow_policy  # noqa: E402
from core.config import load_config  # noqa: E402
from serve import MemoryApi  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "adaptive_residual_shadow_runtime_view_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_residual_shadow_runtime_view_regression_report.md"


def local_runtime_config() -> dict:
    config = load_config(ROOT)
    config["embedding"] = {
        "backend": "hash",
        "dim": int(config.get("embedding_dim") or 768),
    }
    return config


def main() -> int:
    override_config = local_runtime_config()
    override_config["adaptive_residual_shadow"] = {
        "residual_threshold": 0.91,
        "family_confidence_threshold": 0.42,
        "learned_risk_suppressor_enabled": False,
        "learned_risk_confidence_threshold": 0.73,
        "allowed_families": ["supported_evidence", "stale_conflict"],
        "allowed_target": "likely_helpful",
        "suppressors": ["sensitive_private", "unsupported_proof"],
        "terms": {
            "sensitive_private": ["test token", "test secret"],
            "unsupported_proof": ["unsupported test claim"],
        },
    }
    expected_policy = normalize_adaptive_residual_shadow_policy(override_config)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "adaptive_residual_shadow_runtime_view.db"
        api = MemoryApi(ROOT, db_path=db_path, config_override=override_config)
        try:
            view = api.config()
        finally:
            api.close()

    runtime_policy = view.get("adaptive_residual_shadow")
    terms = runtime_policy.get("terms") if isinstance(runtime_policy, dict) else {}
    checks = {
        "config_view_has_adaptive_residual_shadow": isinstance(runtime_policy, dict),
        "runtime_view_matches_normalized_override": runtime_policy == expected_policy,
        "threshold_overrides_visible": runtime_policy.get("residual_threshold") == 0.91
        and runtime_policy.get("family_confidence_threshold") == 0.42
        and runtime_policy.get("learned_risk_confidence_threshold") == 0.73,
        "suppressor_override_visible": runtime_policy.get("learned_risk_suppressor_enabled") is False
        and runtime_policy.get("suppressors") == ["sensitive_private", "unsupported_proof"],
        "term_override_visible": isinstance(terms, dict)
        and terms.get("sensitive_private") == ["test token", "test secret"]
        and terms.get("unsupported_proof") == ["unsupported test claim"],
        "report_only_and_non_mutating": runtime_policy.get("report_only") is True
        and runtime_policy.get("mutates_runtime") is False
        and runtime_policy.get("mutates_answer") is False
        and runtime_policy.get("mutates_selector_policy") is False
        and runtime_policy.get("mutates_memory") is False
        and runtime_policy.get("mutates_config") is False,
    }
    report = {
        "schema": "adaptive_residual_shadow_runtime_view_regression/v1",
        "description": "Runtime config-view guard for adaptive residual shadow policy exposure.",
        "ok": all(checks.values()),
        "checks": checks,
        "runtime_policy": runtime_policy,
        "expected_policy": expected_policy,
        "json": str(OUT_JSON),
        "markdown": str(OUT_MD),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Residual Shadow Runtime View Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Runtime Policy",
            "",
            "```json",
            json.dumps(runtime_policy, indent=2),
            "```",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
