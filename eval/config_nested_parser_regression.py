from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import _parse_simple_yaml, load_config  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "config_nested_parser_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "config_nested_parser_regression_report.md"


SYNTHETIC_YAML = """
top:
  child:
    grandchild:
      value: 7
      flag: true
  sibling: text
answer_type:
  rules:
    synthetic_rule:
      query_terms: alpha,beta
      positive_terms: gamma,delta
      negative_requires_absent: epsilon,zeta
claim_scope:
  slot_aliases:
    synthetic_slot: compact,alias
  excluded_terms:
    synthetic_slot: distractor
"""


def main() -> int:
    synthetic = _parse_simple_yaml(SYNTHETIC_YAML)
    actual = load_config(ROOT)
    failures = []

    checks = {
        "synthetic_deep_value": nested_get(synthetic, "top", "child", "grandchild", "value") == 7,
        "synthetic_deep_flag": nested_get(synthetic, "top", "child", "grandchild", "flag") is True,
        "synthetic_answer_rule_nested": nested_get(
            synthetic,
            "answer_type",
            "rules",
            "synthetic_rule",
            "query_terms",
        )
        == "alpha,beta",
        "synthetic_claim_scope_nested": nested_get(
            synthetic,
            "claim_scope",
            "slot_aliases",
            "synthetic_slot",
        )
        == "compact,alias",
        "actual_claim_scope_slot_aliases_nested": isinstance(
            nested_get(actual, "claim_scope", "slot_aliases"),
            dict,
        )
        and "backend_port" in nested_get(actual, "claim_scope", "slot_aliases"),
        "actual_claim_scope_not_flattened": "slot_aliases" not in actual and "excluded_terms" not in actual,
        "actual_answer_type_rules_nested": isinstance(nested_get(actual, "answer_type", "rules"), dict)
        and {
            "owner_relation",
            "deadline",
            "method_choice",
            "report_filename",
            "github_upload_policy",
            "calendar_change_policy",
        }.issubset(
            set(nested_get(actual, "answer_type", "rules") or {})
        ),
        "actual_answer_type_not_flattened": "rules" not in actual and "owner_relation" not in actual,
    }
    for name, ok in checks.items():
        if not ok:
            failures.append(name)

    report = {
        "ok": not failures,
        "checks": checks,
        "failures": failures,
        "actual_claim_scope_keys": sorted((actual.get("claim_scope") or {}).keys()),
        "actual_answer_type_rules": sorted(((actual.get("answer_type") or {}).get("rules") or {}).keys()),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "failures": report["failures"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


def nested_get(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Config Nested Parser Regression",
        "",
        f"Passed: **{report['ok']}**",
        f"Failures: `{', '.join(report['failures']) or 'none'}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in report["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Actual Config Summary",
            "",
            f"- Claim-scope keys: `{', '.join(report['actual_claim_scope_keys'])}`",
            f"- Answer-type rules: `{', '.join(report['actual_answer_type_rules'])}`",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
