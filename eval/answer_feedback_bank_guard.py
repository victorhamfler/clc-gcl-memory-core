from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_BANK = REPO_ROOT / "experiments" / "answer_feedback_memory_bank_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "answer_feedback_bank_guard_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_feedback_bank_guard_report.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read answer-feedback memory bank {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Answer-feedback memory bank must be a JSON object: {path}")
    return loaded


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def cluster_key(cluster: dict[str, Any]) -> str:
    return normalize_text(cluster.get("key") or f"{cluster.get('family')}:{','.join(cluster.get('labels') or [])}")


def cluster_examples_text(cluster: dict[str, Any]) -> str:
    parts = []
    for example in cluster.get("examples") or []:
        if not isinstance(example, dict):
            continue
        parts.append(str(example.get("answer_preview") or ""))
        parts.append(str(example.get("query") or ""))
    return normalize_text(" ".join(parts))


def refusal_language_present(cluster: dict[str, Any]) -> bool:
    text = cluster_examples_text(cluster)
    if not text:
        return False
    markers = (
        "not have enough",
        "no memory support",
        "no support",
        "insufficient support",
        "refuse",
        "refused",
        "cannot answer",
    )
    return any(marker in text for marker in markers)


def contains_runtime_mutation(bank: dict[str, Any]) -> bool:
    text = json.dumps(bank, sort_keys=True).lower()
    mutation_markers = (
        '"mutates_config": true',
        '"mutates_db": true',
        '"promoted": true',
        '"auto_promote": true',
        '"config_patch"',
        '"resolver_weight_patch"',
        '"selector_policy_patch"',
    )
    return any(marker in text for marker in mutation_markers)


def check_cluster(cluster: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    key = cluster_key(cluster)
    family = normalize_text(cluster.get("family"))
    readiness = normalize_text(cluster.get("readiness"))
    support = int(cluster.get("support") or 0)
    selected_memory_count = int(cluster.get("selected_memory_count") or 0)
    ogcf_signal_count = int(cluster.get("ogcf_signal_count") or 0)
    positive_count = int(cluster.get("positive_count") or 0)
    negative_count = int(cluster.get("negative_count") or 0)

    if readiness in {"ready", "ready_mixed_outcome"} and support <= 0:
        issues.append({"severity": "error", "key": key, "reason": "ready_cluster_has_no_support"})
    if family == "bridge_warning_quality" and readiness.startswith("ready") and ogcf_signal_count < support:
        issues.append({"severity": "error", "key": key, "reason": "bridge_warning_ready_without_ogcf_on_all_examples"})
    if family == "answer_quality" and readiness.startswith("ready") and selected_memory_count < support:
        issues.append({"severity": "error", "key": key, "reason": "supported_answer_ready_without_selected_evidence"})
    if family == "missing_support_refusal" and readiness.startswith("ready"):
        if selected_memory_count != 0:
            issues.append({"severity": "error", "key": key, "reason": "missing_support_ready_has_selected_memory"})
        if positive_count > 0:
            issues.append({"severity": "error", "key": key, "reason": "missing_support_ready_has_positive_feedback"})
        if negative_count <= 0:
            issues.append({"severity": "error", "key": key, "reason": "missing_support_ready_has_no_negative_feedback"})
        if not refusal_language_present(cluster):
            issues.append({"severity": "warning", "key": key, "reason": "missing_support_examples_lack_refusal_language"})
    if positive_count > 0 and negative_count > 0 and readiness == "ready":
        issues.append({"severity": "error", "key": key, "reason": "mixed_outcome_cluster_marked_plain_ready"})
    if readiness == "reject":
        issues.append({"severity": "warning", "key": key, "reason": "rejected_cluster_present"})
    return issues


def build_report(bank_path: Path) -> dict[str, Any]:
    bank = read_json(bank_path)
    if bank.get("schema") != "answer_feedback_memory_bank/v1":
        return {
            "schema": "answer_feedback_bank_guard/v1",
            "ok": False,
            "bank_path": str(bank_path),
            "error": f"Unsupported schema: {bank.get('schema')}",
            "checks": {},
            "issues": [],
        }
    clusters = [item for item in bank.get("clusters") or [] if isinstance(item, dict)]
    issues = [issue for cluster in clusters for issue in check_cluster(cluster)]
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [issue for issue in issues if issue.get("severity") == "warning"]
    ready_clusters = [cluster for cluster in clusters if normalize_text(cluster.get("readiness")).startswith("ready")]
    checks = {
        "schema_ok": bank.get("schema") == "answer_feedback_memory_bank/v1",
        "report_only_no_runtime_mutation": not contains_runtime_mutation(bank),
        "has_clusters": bool(clusters),
        "has_ready_cluster": bool(ready_clusters),
        "bridge_ready_requires_ogcf": not any(
            normalize_text(cluster.get("family")) == "bridge_warning_quality"
            and normalize_text(cluster.get("readiness")).startswith("ready")
            and int(cluster.get("ogcf_signal_count") or 0) < int(cluster.get("support") or 0)
            for cluster in clusters
        ),
        "supported_answer_ready_requires_evidence": not any(
            normalize_text(cluster.get("family")) == "answer_quality"
            and normalize_text(cluster.get("readiness")).startswith("ready")
            and int(cluster.get("selected_memory_count") or 0) < int(cluster.get("support") or 0)
            for cluster in clusters
        ),
        "missing_support_refusal_guarded": not any(
            normalize_text(cluster.get("family")) == "missing_support_refusal"
            and normalize_text(cluster.get("readiness")).startswith("ready")
            and (
                int(cluster.get("selected_memory_count") or 0) != 0
                or int(cluster.get("positive_count") or 0) > 0
                or int(cluster.get("negative_count") or 0) <= 0
            )
            for cluster in clusters
        ),
        "mixed_outcomes_not_plain_ready": not any(
            int(cluster.get("positive_count") or 0) > 0
            and int(cluster.get("negative_count") or 0) > 0
            and normalize_text(cluster.get("readiness")) == "ready"
            for cluster in clusters
        ),
        "no_error_issues": not errors,
    }
    return {
        "schema": "answer_feedback_bank_guard/v1",
        "description": "Report-only guard for answer-feedback memory-bank readiness.",
        "ok": all(checks.values()),
        "bank_path": str(bank_path),
        "cluster_count": len(clusters),
        "ready_cluster_count": len(ready_clusters),
        "checks": checks,
        "issue_count": len(issues),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": issues,
        "ready_clusters": [
            {
                "key": cluster.get("key"),
                "family": cluster.get("family"),
                "labels": cluster.get("labels"),
                "readiness": cluster.get("readiness"),
                "support": cluster.get("support"),
                "distinct_source_logs": cluster.get("distinct_source_logs"),
                "distinct_queries": cluster.get("distinct_queries"),
            }
            for cluster in ready_clusters
        ],
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Answer Feedback Bank Guard",
        "",
        "This guard is advisory only. It does not promote resolver weights, selector policy, or runtime config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Bank: `{report['bank_path']}`",
        f"Clusters: `{report.get('cluster_count', 0)}`",
        f"Ready clusters: `{report.get('ready_cluster_count', 0)}`",
        f"Issues: `{report.get('issue_count', 0)}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in (report.get("checks") or {}).items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## Ready Clusters", "", "| key | family | readiness | support | logs | queries |", "| --- | --- | --- | ---: | ---: | ---: |"])
    for cluster in report.get("ready_clusters") or []:
        lines.append(
            f"| `{cluster.get('key')}` | `{cluster.get('family')}` | `{cluster.get('readiness')}` | "
            f"{cluster.get('support')} | {cluster.get('distinct_source_logs')} | {cluster.get('distinct_queries')} |"
        )
    lines.extend(["", "## Issues", ""])
    if not report.get("issues"):
        lines.append("- None")
    for issue in report.get("issues") or []:
        lines.append(f"- `{issue.get('severity')}` `{issue.get('key')}`: `{issue.get('reason')}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard answer-feedback memory-bank readiness before behavior changes.")
    parser.add_argument("--bank", default=str(DEFAULT_BANK))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    report = build_report(Path(args.bank))
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "cluster_count": report.get("cluster_count"),
                "ready_cluster_count": report.get("ready_cluster_count"),
                "issue_count": report.get("issue_count"),
                "checks": report.get("checks"),
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
