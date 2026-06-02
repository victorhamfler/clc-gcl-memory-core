from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.answer_behavior_shadow import normalize_resolver_shadow_config  # noqa: E402
from core.config import load_config  # noqa: E402
from serve import MemoryApi  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "resolver_shadow_runtime_view_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "resolver_shadow_runtime_view_regression_report.md"


def local_runtime_config() -> dict:
    config = load_config(ROOT)
    config["embedding"] = {
        "backend": "hash",
        "dim": int(config.get("embedding_dim") or 768),
    }
    return config


def main() -> int:
    override_config = local_runtime_config()
    override_config["resolver_shadow"] = {
        "enabled": True,
        "include_in_outcome_log": True,
        "bridge_warning_score_threshold": 0.83,
        "bridge_warning_effective_ratio_threshold": 0.61,
        "refusal_markers": "no support,cannot answer safely",
    }
    expected_config = normalize_resolver_shadow_config(override_config.get("resolver_shadow"))
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "resolver_shadow_runtime_view.db"
        api = MemoryApi(ROOT, db_path=db_path, config_override=override_config)
        try:
            view = api.config()
        finally:
            api.close()

    runtime_config = view.get("resolver_shadow")
    checks = {
        "config_view_has_resolver_shadow": isinstance(runtime_config, dict),
        "runtime_view_matches_normalized_override": runtime_config == expected_config,
        "threshold_overrides_visible": runtime_config.get("bridge_warning_score_threshold") == 0.83
        and runtime_config.get("bridge_warning_effective_ratio_threshold") == 0.61,
        "logging_override_visible": runtime_config.get("enabled") is True
        and runtime_config.get("include_in_outcome_log") is True,
        "refusal_markers_normalized": tuple(runtime_config.get("refusal_markers") or ()) == (
            "no support",
            "cannot answer safely",
        ),
        "report_only_and_non_mutating": runtime_config.get("report_only") is True
        and runtime_config.get("mutates_runtime") is False
        and runtime_config.get("mutates_answer") is False
        and runtime_config.get("mutates_selector_policy") is False
        and runtime_config.get("mutates_memory") is False
        and runtime_config.get("mutates_config") is False,
    }
    report = {
        "schema": "resolver_shadow_runtime_view_regression/v1",
        "description": "Runtime config-view guard for resolver shadow policy exposure.",
        "ok": all(checks.values()),
        "checks": checks,
        "runtime_config": runtime_config,
        "expected_config": expected_config,
        "json": str(OUT_JSON),
        "markdown": str(OUT_MD),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Resolver Shadow Runtime View Regression",
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
    lines.extend(["", "## Runtime Config", "", "```json", json.dumps(runtime_config, indent=2), "```"])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
