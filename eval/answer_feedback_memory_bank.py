from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


OUT_JSON = REPO_ROOT / "experiments" / "answer_feedback_memory_bank_results.json"
OUT_MD = REPO_ROOT / "experiments" / "answer_feedback_memory_bank_report.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read answer-feedback signal artifact {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Answer-feedback signal artifact must be a JSON object: {path}")
    if loaded.get("schema") != "answer_feedback_controller_signals/v1":
        raise ValueError(f"Unsupported answer-feedback signal schema in {path}: {loaded.get('schema')}")
    return loaded


def parse_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def signal_key(signal: dict[str, Any]) -> str:
    family = normalize_text(signal.get("family"))
    label = normalize_text(signal.get("label"))
    return f"{family}:{label}"


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def signal_ready_state(
    signals: list[dict[str, Any]],
    *,
    ready_support: int,
    ready_logs: int,
    ready_queries: int,
) -> str:
    recommendations = {normalize_text(item.get("recommendation")) for item in signals}
    if "reject_missing_link" in recommendations:
        return "reject"
    if recommendations and recommendations <= {"hold_unknown_label", "hold_bridge_without_ogcf", "hold_neutral"}:
        return "hold"
    source_logs = {str(item.get("_artifact_source")) for item in signals if item.get("_artifact_source")}
    queries = {normalize_text(item.get("query")) for item in signals if normalize_text(item.get("query"))}
    positive = sum(1 for item in signals if float(item.get("rating") or 0.0) > 0.0)
    negative = sum(1 for item in signals if float(item.get("rating") or 0.0) < 0.0)
    has_bridge_without_ogcf = any(
        item.get("family") == "bridge_warning_quality" and not item.get("ogcf_meta_present")
        for item in signals
    )
    if has_bridge_without_ogcf:
        return "hold"
    if len(signals) >= ready_support and len(source_logs) >= ready_logs and len(queries) >= ready_queries:
        if positive and negative:
            return "ready_mixed_outcome"
        return "ready"
    return "hold"


def freeze_cluster(
    key: str,
    signals: list[dict[str, Any]],
    *,
    ready_support: int,
    ready_logs: int,
    ready_queries: int,
) -> dict[str, Any]:
    source_logs = sorted({str(item.get("_artifact_source")) for item in signals if item.get("_artifact_source")})
    queries = sorted({normalize_text(item.get("query")) for item in signals if normalize_text(item.get("query"))})
    labels = sorted({normalize_text(item.get("label")) for item in signals if normalize_text(item.get("label"))})
    families = sorted({normalize_text(item.get("family")) for item in signals if normalize_text(item.get("family"))})
    ratings = [float(item.get("rating") or 0.0) for item in signals]
    ogcf_count = sum(1 for item in signals if item.get("ogcf_meta_present"))
    selected_memory_count = sum(len(item.get("selected_memory_ids") or []) for item in signals)
    examples = [
        {
            "source_log": item.get("_artifact_source"),
            "query": item.get("query"),
            "label": item.get("label"),
            "rating": item.get("rating"),
            "recommendation": item.get("recommendation"),
            "ogcf_meta_present": item.get("ogcf_meta_present"),
            "selector_policy": item.get("selector_policy"),
            "answer_preview": item.get("answer_preview"),
        }
        for item in signals[:5]
    ]
    return {
        "key": key,
        "family": families[0] if len(families) == 1 else "mixed",
        "labels": labels,
        "support": len(signals),
        "distinct_source_logs": len(source_logs),
        "distinct_queries": len(queries),
        "positive_count": sum(1 for rating in ratings if rating > 0.0),
        "negative_count": sum(1 for rating in ratings if rating < 0.0),
        "mean_rating": round(sum(ratings) / len(ratings), 6) if ratings else 0.0,
        "ogcf_signal_count": ogcf_count,
        "selected_memory_count": selected_memory_count,
        "readiness": signal_ready_state(
            signals,
            ready_support=ready_support,
            ready_logs=ready_logs,
            ready_queries=ready_queries,
        ),
        "source_logs": source_logs,
        "queries": queries,
        "examples": examples,
    }


def load_signals(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    signals: list[dict[str, Any]] = []
    artifacts = []
    for path in paths:
        artifact = read_json(path)
        artifact_signals = [item for item in artifact.get("signals") or [] if isinstance(item, dict)]
        artifacts.append(
            {
                "path": str(path),
                "source_log": artifact.get("source_log"),
                "signal_count": len(artifact_signals),
                "label_counts": artifact.get("label_counts"),
                "family_counts": artifact.get("family_counts"),
                "recommendation_counts": artifact.get("recommendation_counts"),
            }
        )
        for signal in artifact_signals:
            item = dict(signal)
            item["_artifact_source"] = str(path)
            item["_source_log"] = artifact.get("source_log")
            signals.append(item)
    return signals, artifacts


def build_report(
    signal_paths: list[Path],
    *,
    ready_support: int = 2,
    ready_logs: int = 2,
    ready_queries: int = 1,
) -> dict[str, Any]:
    signals, artifacts = load_signals(signal_paths)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        grouped[signal_key(signal)].append(signal)
    clusters = [
        freeze_cluster(
            key,
            items,
            ready_support=max(1, int(ready_support)),
            ready_logs=max(1, int(ready_logs)),
            ready_queries=max(1, int(ready_queries)),
        )
        for key, items in sorted(grouped.items())
    ]
    readiness_counts = Counter(cluster["readiness"] for cluster in clusters)
    family_counts = Counter(signal.get("family") for signal in signals)
    label_counts = Counter(signal.get("label") for signal in signals)
    return {
        "schema": "answer_feedback_memory_bank/v1",
        "description": "Report-only multi-run memory bank for answer-level feedback controller signals.",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "signal_count": len(signals),
        "cluster_count": len(clusters),
        "ready_thresholds": {
            "support": max(1, int(ready_support)),
            "source_logs": max(1, int(ready_logs)),
            "distinct_queries": max(1, int(ready_queries)),
        },
        "label_counts": dict(sorted(label_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "clusters": clusters,
        "ok": bool(signals) and bool(clusters),
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Answer Feedback Memory Bank",
        "",
        "This report is advisory only. It does not promote resolver weights, selector policy, or runtime config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Signal artifacts: `{report['artifact_count']}`",
        f"Signals: `{report['signal_count']}`",
        f"Clusters: `{report['cluster_count']}`",
        "",
        "## Readiness Counts",
        "",
        "```json",
        json.dumps(report["readiness_counts"], indent=2),
        "```",
        "",
        "## Label Counts",
        "",
        "```json",
        json.dumps(report["label_counts"], indent=2),
        "```",
        "",
        "## Clusters",
        "",
        "| readiness | family | labels | support | logs | queries | mean rating | ogcf | examples |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for cluster in report["clusters"]:
        example_queries = "; ".join(example.get("query") or "" for example in cluster["examples"][:2])
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} | {} | {} | {} | {} |".format(
                cluster["readiness"],
                cluster["family"],
                clean_cell(", ".join(cluster["labels"])),
                cluster["support"],
                cluster["distinct_source_logs"],
                cluster["distinct_queries"],
                cluster["mean_rating"],
                cluster["ogcf_signal_count"],
                clean_cell(example_queries),
            )
        )
    lines.extend(["", "## Artifacts", ""])
    for artifact in report["artifacts"]:
        lines.append(f"- `{artifact['path']}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate answer-feedback signal artifacts into a report-only memory bank.")
    parser.add_argument("--signals", action="append", help="answer_feedback_controller_signals/v1 JSON path. May repeat.")
    parser.add_argument("--ready-support", type=int, default=2)
    parser.add_argument("--ready-logs", type=int, default=2)
    parser.add_argument("--ready-queries", type=int, default=1)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    paths = parse_paths(args.signals)
    if not paths:
        print(json.dumps({"ok": False, "error": "At least one --signals artifact is required."}, indent=2))
        return 2

    report = build_report(
        paths,
        ready_support=args.ready_support,
        ready_logs=args.ready_logs,
        ready_queries=args.ready_queries,
    )
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "artifact_count": report["artifact_count"],
                "signal_count": report["signal_count"],
                "cluster_count": report["cluster_count"],
                "readiness_counts": report["readiness_counts"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
