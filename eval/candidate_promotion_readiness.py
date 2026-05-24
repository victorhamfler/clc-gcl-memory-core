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


OUT_JSON = REPO_ROOT / "experiments" / "candidate_promotion_readiness_results.json"
OUT_MD = REPO_ROOT / "experiments" / "candidate_promotion_readiness_report.md"
NOISY_TERMS = {
    "about",
    "could",
    "does",
    "exact",
    "general",
    "have",
    "has",
    "had",
    "live",
    "lives",
    "located",
    "location",
    "must",
    "need",
    "needs",
    "should",
    "this",
    "what",
    "where",
    "which",
    "will",
    "would",
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read candidate artifact {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Candidate artifact must be a JSON object: {path}")
    return loaded


def clean_cell(value: Any, limit: int = 120) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def normalize_term(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def support_value(artifact: dict[str, Any], support_family: str, term: str, fallback: int = 1) -> int:
    support = artifact.get("support") if isinstance(artifact.get("support"), dict) else {}
    family = support.get(support_family) if isinstance(support.get(support_family), dict) else {}
    value = family.get(term)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(1, int(fallback))


def example_key(schema: str, field: str, term: str) -> str:
    if schema == "retrieval_signal_candidates/v1":
        return {
            "source_contains": f"broad_source:{term}",
            "text_prefixes": f"broad_prefix:{term}",
            "query_terms": f"scope_query:{term}",
            "text_markers": f"scope_marker:{term}",
        }.get(field, f"{field}:{term}")
    return {
        "terms:stale_language": f"stale_language:{term}",
        "terms:correction_language": f"correction_language:{term}",
        "terms:sensitive_lookup": f"sensitive_lookup:{term}",
        "terms:held_out_sensitive_lookup": f"held_out_sensitive_lookup:{term}",
    }.get(field, f"{field}:{term}")


def artifact_terms(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    schema = str(artifact.get("schema") or "")
    output: list[dict[str, Any]] = []
    candidates = [item for item in artifact.get("candidates") or [] if isinstance(item, dict)]

    if schema == "retrieval_signal_candidates/v1":
        support_families = {
            "source_contains": "broad_sources",
            "text_prefixes": "broad_prefixes",
            "query_terms": "scope_query_terms",
            "text_markers": "scope_markers",
        }
        for candidate in candidates:
            section = str(candidate.get("section") or "unknown")
            for field, support_family in support_families.items():
                for term in candidate.get(field) or []:
                    normalized = normalize_term(term)
                    if not normalized:
                        continue
                    output.append(
                        {
                            "kind": "retrieval",
                            "section": section,
                            "field": field,
                            "term": normalized,
                            "support_family": support_family,
                            "example_key": example_key(schema, field, normalized),
                            "held_out": False,
                            "support": support_value(artifact, support_family, normalized),
                        }
                    )
        return output

    if schema == "evidence_state_candidates/v1":
        for candidate in candidates:
            section = str(candidate.get("section") or "unknown")
            if isinstance(candidate.get("terms"), list):
                support_family = section
                for term in candidate.get("terms") or []:
                    normalized = normalize_term(term)
                    if not normalized:
                        continue
                    output.append(
                        {
                            "kind": "evidence",
                            "section": section,
                            "field": "terms",
                            "term": normalized,
                            "support_family": support_family,
                            "example_key": example_key(schema, f"terms:{section}", normalized),
                            "held_out": False,
                            "support": support_value(artifact, support_family, normalized),
                        }
                    )
        support = artifact.get("support") if isinstance(artifact.get("support"), dict) else {}
        held_out = support.get("held_out_sensitive_lookup")
        if isinstance(held_out, dict):
            for term, count in held_out.items():
                normalized = normalize_term(term)
                if not normalized:
                    continue
                output.append(
                    {
                        "kind": "evidence",
                        "section": "held_out_sensitive_lookup",
                        "field": "terms",
                        "term": normalized,
                        "support_family": "held_out_sensitive_lookup",
                        "example_key": example_key(schema, "terms:held_out_sensitive_lookup", normalized),
                        "held_out": True,
                        "support": support_value(artifact, "held_out_sensitive_lookup", normalized),
                    }
                )
        return output

    raise ValueError(f"Unsupported candidate schema: {schema}")


def add_candidate(
    aggregate: dict[str, dict[str, Any]],
    artifact: dict[str, Any],
    path: Path,
    row: dict[str, Any],
) -> None:
    key = f"{row['kind']}:{row['section']}:{row['field']}:{row['term']}"
    item = aggregate.setdefault(
        key,
        {
            "key": key,
            "kind": row["kind"],
            "section": row["section"],
            "field": row["field"],
            "term": row["term"],
            "support": 0,
            "source_logs": set(),
            "artifact_paths": set(),
            "queries": set(),
            "labels": set(),
            "examples": [],
            "held_out": False,
        },
    )
    item["support"] += int(row.get("support") or 0)
    item["artifact_paths"].add(str(path))
    item["held_out"] = bool(item["held_out"] or row.get("held_out"))
    if artifact.get("source_log"):
        item["source_logs"].add(str(artifact.get("source_log")))

    examples = artifact.get("examples") if isinstance(artifact.get("examples"), dict) else {}
    for example in examples.get(str(row.get("example_key"))) or []:
        if not isinstance(example, dict):
            continue
        query = str(example.get("query") or "")
        label = str(example.get("label") or "")
        if query:
            item["queries"].add(query)
        if label:
            item["labels"].add(label)
        if len(item["examples"]) < 5:
            item["examples"].append(example)


def classify_candidate(item: dict[str, Any], *, ready_support: int, ready_logs: int, ready_queries: int) -> str:
    term = normalize_term(item.get("term"))
    if item.get("held_out") or item.get("section") == "held_out_sensitive_lookup":
        return "held_out"
    if term in NOISY_TERMS:
        return "reject"
    if (
        int(item.get("support") or 0) >= ready_support
        and len(item.get("source_logs") or []) >= ready_logs
        and len(item.get("queries") or []) >= ready_queries
    ):
        return "ready"
    return "hold"


def flags_for(item: dict[str, Any], *, ready_support: int, ready_logs: int, ready_queries: int) -> list[str]:
    flags = []
    if item.get("held_out"):
        flags.append("held_out")
    if normalize_term(item.get("term")) in NOISY_TERMS:
        flags.append("noisy_term")
    if int(item.get("support") or 0) < ready_support:
        flags.append("low_support")
    if len(item.get("source_logs") or []) < ready_logs:
        flags.append("low_log_diversity")
    if len(item.get("queries") or []) < ready_queries:
        flags.append("low_query_diversity")
    if not item.get("examples"):
        flags.append("no_examples")
    return flags


def freeze_candidate(item: dict[str, Any], *, ready_support: int, ready_logs: int, ready_queries: int) -> dict[str, Any]:
    recommendation = classify_candidate(
        item,
        ready_support=ready_support,
        ready_logs=ready_logs,
        ready_queries=ready_queries,
    )
    return {
        "key": item["key"],
        "kind": item["kind"],
        "section": item["section"],
        "field": item["field"],
        "term": item["term"],
        "recommendation": recommendation,
        "support": item["support"],
        "distinct_source_logs": len(item["source_logs"]),
        "distinct_queries": len(item["queries"]),
        "labels": sorted(item["labels"]),
        "source_logs": sorted(item["source_logs"]),
        "artifact_paths": sorted(item["artifact_paths"]),
        "quality_flags": flags_for(
            item,
            ready_support=ready_support,
            ready_logs=ready_logs,
            ready_queries=ready_queries,
        ),
        "examples": item["examples"],
    }


def build_report(
    candidate_paths: list[Path],
    *,
    ready_support: int = 3,
    ready_logs: int = 2,
    ready_queries: int = 2,
) -> dict[str, Any]:
    aggregate: dict[str, dict[str, Any]] = {}
    artifacts = []
    for path in candidate_paths:
        artifact = read_json(path)
        artifacts.append(
            {
                "path": str(path),
                "schema": artifact.get("schema"),
                "source_log": artifact.get("source_log"),
                "candidate_count": artifact.get("candidate_count"),
            }
        )
        for row in artifact_terms(artifact):
            add_candidate(aggregate, artifact, path, row)

    candidates = [
        freeze_candidate(
            item,
            ready_support=max(1, int(ready_support)),
            ready_logs=max(1, int(ready_logs)),
            ready_queries=max(1, int(ready_queries)),
        )
        for item in aggregate.values()
    ]
    candidates.sort(key=lambda item: (item["recommendation"], item["kind"], item["section"], item["term"]))
    counts = Counter(item["recommendation"] for item in candidates)
    return {
        "schema": "candidate_promotion_readiness/v1",
        "description": "Aggregates selector candidate artifacts and classifies promotion readiness.",
        "thresholds": {
            "ready_support": max(1, int(ready_support)),
            "ready_source_logs": max(1, int(ready_logs)),
            "ready_distinct_queries": max(1, int(ready_queries)),
        },
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "candidate_count": len(candidates),
        "recommendation_counts": dict(sorted(counts.items())),
        "candidates": candidates,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Candidate Promotion Readiness",
        "",
        "This report is advisory only. It does not promote candidates into runtime config.",
        "",
        f"Candidate count: **{report['candidate_count']}**",
        f"Artifact count: `{report['artifact_count']}`",
        "",
        "## Thresholds",
        "",
        "```json",
        json.dumps(report["thresholds"], indent=2),
        "```",
        "",
        "## Recommendation Counts",
        "",
        "```json",
        json.dumps(report["recommendation_counts"], indent=2),
        "```",
        "",
        "## Candidates",
        "",
        "| recommendation | key | support | logs | queries | flags |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    if not report["candidates"]:
        lines.append("| hold | no candidates | 0 | 0 | 0 | no_candidates |")
    for candidate in report["candidates"]:
        lines.append(
            "| `{recommendation}` | `{key}` | {support} | {logs} | {queries} | `{flags}` |".format(
                recommendation=candidate["recommendation"],
                key=clean_cell(candidate["key"]),
                support=candidate["support"],
                logs=candidate["distinct_source_logs"],
                queries=candidate["distinct_queries"],
                flags=", ".join(candidate["quality_flags"]),
            )
        )
    lines.extend(["", "## Artifacts", ""])
    for artifact in report["artifacts"]:
        lines.append(f"- `{artifact['schema']}`: `{artifact['path']}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify selector candidate promotion readiness.")
    parser.add_argument("--candidate", action="append", help="Candidate artifact JSON path. May be repeated.")
    parser.add_argument("--ready-support", type=int, default=3)
    parser.add_argument("--ready-logs", type=int, default=2)
    parser.add_argument("--ready-queries", type=int, default=2)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    paths = parse_paths(args.candidate)
    if not paths:
        print(json.dumps({"ok": False, "error": "At least one --candidate artifact is required."}, indent=2))
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
                "ok": True,
                "candidate_count": report["candidate_count"],
                "recommendation_counts": report["recommendation_counts"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
