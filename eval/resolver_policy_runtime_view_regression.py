from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.resolver_policy import DEFAULT_RESOLVER_POLICY, normalize_resolver_policy  # noqa: E402
from serve import MemoryApi  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "resolver_policy_runtime_view_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "resolver_policy_runtime_view_regression_report.md"


def local_runtime_config() -> dict:
    config = load_config(ROOT)
    config["embedding"] = {
        "backend": "hash",
        "dim": int(config.get("embedding_dim") or 768),
    }
    return config


def main() -> int:
    base_config = local_runtime_config()
    expected_policy = normalize_resolver_policy(base_config.get("resolver_policy"))
    override_config = dict(base_config)
    override_config["resolver_policy"] = {
        **expected_policy,
        "query_relevance": {
            **expected_policy["query_relevance"],
            "text_match_accept_threshold": 0.27,
        },
        "answer_snippets": {
            **expected_policy["answer_snippets"],
            "snippet_max_chars": 72,
        },
    }
    expected_override_policy = normalize_resolver_policy(override_config.get("resolver_policy"))
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "resolver_policy_runtime_view.db"
        api = MemoryApi(ROOT, db_path=db_path, config_override=override_config)
        try:
            view = api.config()
        finally:
            api.close()

    resolver_policy = view.get("resolver_policy")
    checks = {
        "config_view_has_resolver_policy": isinstance(resolver_policy, dict),
        "runtime_view_matches_normalized_override": resolver_policy == expected_override_policy,
        "query_relevance_override_visible": (
            isinstance(resolver_policy, dict)
            and resolver_policy.get("query_relevance", {}).get("text_match_accept_threshold") == 0.27
        ),
        "snippet_override_visible": (
            isinstance(resolver_policy, dict)
            and resolver_policy.get("answer_snippets", {}).get("snippet_max_chars") == 72
        ),
        "all_default_sections_present": all(
            key in resolver_policy
            for key in normalize_resolver_policy(DEFAULT_RESOLVER_POLICY).keys()
        )
        if isinstance(resolver_policy, dict)
        else False,
    }
    report = {
        "schema": "resolver_policy_runtime_view_regression/v1",
        "ok": all(checks.values()),
        "checks": checks,
        "resolver_policy_sections": sorted(resolver_policy.keys()) if isinstance(resolver_policy, dict) else [],
        "json": str(OUT_JSON),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Resolver Policy Runtime View Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
