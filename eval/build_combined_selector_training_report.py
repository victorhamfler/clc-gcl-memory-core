from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.clc_policy_selector import CLCPolicyFeatures  # noqa: E402
from hermes_hard_stale_escalation_v2 import selector_features  # noqa: E402


MATRIX = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_live_results.json"
V2 = REPO_ROOT / "experiments" / "hermes_hard_stale_escalation_v2_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "clc_selector_combined_training_report.json"
OUT_MD = REPO_ROOT / "experiments" / "clc_selector_combined_training_report.md"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def matrix_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in data.get("scenarios", []):
        features = row.get("features")
        oracle_policy = row.get("oracle_policy")
        if not isinstance(features, dict) or not oracle_policy:
            continue
        policy_results = row.get("policy_results", {})
        rows.append(
            {
                "id": str(row.get("id") or f"matrix_{len(rows)}"),
                "family": str(row.get("family") or "policy_matrix"),
                "condition_name": str(row.get("condition_name") or ""),
                "source": "clc_policy_matrix_eval_live",
                "features": features,
                "oracle_policy": str(oracle_policy),
                "oracle_utility": policy_results.get(str(oracle_policy), {}).get("utility"),
            }
        )
    return rows


def v2_groups(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.get("results", []):
        groups[str(row["scenario_key"])].append(row)
    return dict(groups)


def boundary_features(row: dict[str, Any]) -> dict[str, Any]:
    dynamic = selector_features(
        int(row["stale_count"]),
        str(row["semantic_similarity"]),
        str(row["domain_noise"]),
        str(row["query_specificity"]),
    )
    return asdict(
        CLCPolicyFeatures.from_condition_name(
            str(dynamic.get("condition_name") or "hard_budget144"),
            **{key: value for key, value in dynamic.items() if key != "condition_name"},
        )
    )


def boundary_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, group in sorted(v2_groups(data).items()):
        first = group[0]
        oracle_policy = str(first.get("oracle_policy") or "")
        oracle_row = next((row for row in group if row.get("selected_policy") == oracle_policy), None)
        rows.append(
            {
                "id": f"boundary_v2_{key}",
                "family": "hard_stale_boundary_v2",
                "condition_name": "hard_budget144",
                "source": "hermes_hard_stale_escalation_v2",
                "features": boundary_features(first),
                "oracle_policy": oracle_policy,
                "oracle_utility": None if oracle_row is None else oracle_row.get("utility"),
                "metadata": {
                    "scenario_key": key,
                    "stale_count": first.get("stale_count"),
                    "semantic_similarity": first.get("semantic_similarity"),
                    "domain_noise": first.get("domain_noise"),
                    "query_specificity": first.get("query_specificity"),
                    "current_style": first.get("current_style"),
                },
            }
        )
    return rows


def write_markdown(report: dict[str, Any]) -> None:
    counts = report["sample_counts"]
    lines = [
        "# CLC Selector Combined Training Report",
        "",
        "This report is the default learned-selector training source. It combines the broad live policy matrix with",
        "the focused Hermes v2 stale-boundary cases that exposed the matrix-only selector failure.",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Samples",
        "",
        f"- Matrix samples: `{counts['matrix']}`",
        f"- Boundary v2 samples: `{counts['boundary_v2']}`",
        f"- Total samples: `{counts['total']}`",
        "",
        "## Oracle Policy Distribution",
        "",
        "| Policy | Samples |",
        "|---|---:|",
    ]
    for policy, count in report["oracle_policy_counts"].items():
        lines.append(f"| `{policy}` | {count} |")
    lines.extend(
        [
            "",
            "## Boundary Samples",
            "",
            "| Scenario | Oracle policy | stale_count | similarity | query | current style |",
            "|---|---|---:|---|---|---|",
        ]
    )
    for row in report["scenarios"]:
        if row.get("source") != "hermes_hard_stale_escalation_v2":
            continue
        meta = row["metadata"]
        lines.append(
            "| "
            f"`{meta['scenario_key']}` | `{row['oracle_policy']}` | {meta['stale_count']} | "
            f"{meta['semantic_similarity']} | {meta['query_specificity']} | {meta['current_style']} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    matrix = load_json(MATRIX)
    v2 = load_json(V2)
    matrix_training_rows = matrix_rows(matrix)
    boundary_training_rows = boundary_rows(v2)
    scenarios = matrix_training_rows + boundary_training_rows
    policy_counts = Counter(str(row["oracle_policy"]) for row in scenarios)
    report = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "combined learned-policy selector training report",
        "source_reports": {
            "matrix": str(MATRIX),
            "boundary_v2": str(V2),
        },
        "sample_counts": {
            "matrix": len(matrix_training_rows),
            "boundary_v2": len(boundary_training_rows),
            "total": len(scenarios),
        },
        "oracle_policy_counts": dict(sorted(policy_counts.items())),
        "scenarios": scenarios,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(
        json.dumps(
            {
                "ok": True,
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
                "sample_counts": report["sample_counts"],
                "oracle_policy_counts": report["oracle_policy_counts"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
