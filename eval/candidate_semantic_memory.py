from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config, resolve_project_path  # noqa: E402
from core.encoder import build_encoder  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "candidate_semantic_memory_results.json"
OUT_MD = REPO_ROOT / "experiments" / "candidate_semantic_memory_report.md"


def read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read readiness artifact {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Readiness artifact must be a JSON object: {path}")
    return loaded


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def tokens(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text or ""))
    return {part for part in cleaned.split() if part}


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return dot / (na * nb)


def lexical_similarity(a: str, b: str) -> float:
    if a == b and a:
        return 1.0
    ta = tokens(a)
    tb = tokens(b)
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb) / len(ta | tb)
    substring = 0.0
    if a in b or b in a:
        substring = min(len(a), len(b)) / max(len(a), len(b))
    return max(overlap, substring)


def clean_cell(value: Any, limit: int = 120) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def embedding_config(backend: str) -> dict[str, Any]:
    if backend == "hash":
        return {"backend": "hash", "dim": 128}
    config = load_config(ROOT)
    embedding = dict(config.get("embedding") or {})
    if embedding.get("cache_path"):
        embedding["cache_path"] = str(resolve_project_path(ROOT, embedding.get("cache_path"), "logs/embedding_cache.sqlite"))
    return embedding


def candidate_text(candidate: dict[str, Any]) -> str:
    labels = " ".join(str(label) for label in candidate.get("labels") or [])
    return " ".join(
        part
        for part in [
            str(candidate.get("kind") or ""),
            str(candidate.get("section") or ""),
            str(candidate.get("field") or ""),
            str(candidate.get("term") or ""),
            labels,
        ]
        if part
    )


def load_candidates(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for path in paths:
        artifact = read_json(path)
        if artifact.get("schema") != "candidate_promotion_readiness/v1":
            raise ValueError(f"Unsupported readiness schema in {path}: {artifact.get('schema')}")
        artifacts.append(
            {
                "path": str(path),
                "candidate_count": artifact.get("candidate_count"),
                "recommendation_counts": artifact.get("recommendation_counts"),
            }
        )
        for candidate in artifact.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            item = dict(candidate)
            item["_readiness_artifact"] = str(path)
            item["_cluster_text"] = candidate_text(candidate)
            candidates.append(item)
    return candidates, artifacts


def compatible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a.get("kind") == b.get("kind")
        and a.get("section") == b.get("section")
        and a.get("field") == b.get("field")
        and a.get("recommendation") not in {"reject", "held_out"}
        and b.get("recommendation") not in {"reject", "held_out"}
    )


def pair_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    lexical = lexical_similarity(str(a.get("term") or ""), str(b.get("term") or ""))
    embedding = cosine(a.get("_embedding") or [], b.get("_embedding") or [])
    if lexical <= 0.0:
        return embedding if embedding >= 0.86 else 0.0
    return max(lexical, embedding)


def cluster_candidates(candidates: list[dict[str, Any]], threshold: float) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for candidate in sorted(candidates, key=lambda item: (item.get("kind"), item.get("section"), item.get("term"))):
        placed = False
        for cluster in clusters:
            if not compatible(candidate, cluster[0]):
                continue
            if max(pair_similarity(candidate, member) for member in cluster) >= threshold:
                cluster.append(candidate)
                placed = True
                break
        if not placed:
            clusters.append([candidate])
    return clusters


def cluster_recommendation(cluster: list[dict[str, Any]], *, ready_support: int, ready_logs: int, ready_queries: int) -> str:
    recommendations = {str(item.get("recommendation") or "") for item in cluster}
    if "held_out" in recommendations:
        return "held_out"
    if recommendations and recommendations <= {"reject"}:
        return "reject"
    source_logs = {log for item in cluster for log in item.get("source_logs") or []}
    queries = {example.get("query") for item in cluster for example in item.get("examples") or [] if example.get("query")}
    support = sum(int(item.get("support") or 0) for item in cluster)
    if support >= ready_support and len(source_logs) >= ready_logs and len(queries) >= ready_queries:
        return "semantic_ready"
    return "semantic_hold"


def freeze_cluster(index: int, cluster: list[dict[str, Any]], *, ready_support: int, ready_logs: int, ready_queries: int) -> dict[str, Any]:
    support = sum(int(item.get("support") or 0) for item in cluster)
    source_logs = sorted({log for item in cluster for log in item.get("source_logs") or []})
    queries = sorted({example.get("query") for item in cluster for example in item.get("examples") or [] if example.get("query")})
    recommendations = sorted({str(item.get("recommendation") or "") for item in cluster})
    terms = sorted({normalize_text(item.get("term")) for item in cluster if normalize_text(item.get("term"))})
    representative = max(cluster, key=lambda item: (int(item.get("support") or 0), len(str(item.get("term") or ""))))
    return {
        "id": f"cluster_{index:03d}",
        "kind": representative.get("kind"),
        "section": representative.get("section"),
        "field": representative.get("field"),
        "representative_term": representative.get("term"),
        "cluster_recommendation": cluster_recommendation(
            cluster,
            ready_support=ready_support,
            ready_logs=ready_logs,
            ready_queries=ready_queries,
        ),
        "member_count": len(cluster),
        "terms": terms,
        "support": support,
        "distinct_source_logs": len(source_logs),
        "distinct_queries": len(queries),
        "source_logs": source_logs,
        "recommendations": recommendations,
        "members": [
            {
                "key": item.get("key"),
                "term": item.get("term"),
                "recommendation": item.get("recommendation"),
                "support": item.get("support"),
                "readiness_artifact": item.get("_readiness_artifact"),
            }
            for item in sorted(cluster, key=lambda member: str(member.get("key") or ""))
        ],
    }


def build_report(
    readiness_paths: list[Path],
    *,
    embedding_backend: str = "hash",
    similarity_threshold: float = 0.72,
    ready_support: int = 3,
    ready_logs: int = 2,
    ready_queries: int = 2,
) -> dict[str, Any]:
    candidates, artifacts = load_candidates(readiness_paths)
    encoder = build_encoder(embedding_config(embedding_backend), default_dim=128)
    try:
        descriptor = encoder.descriptor()
        for candidate in candidates:
            candidate["_embedding"] = encoder.embed(candidate["_cluster_text"])
    finally:
        close = getattr(encoder, "close", None)
        if callable(close):
            close()

    clusters = cluster_candidates(candidates, max(0.0, min(1.0, float(similarity_threshold))))
    frozen = [
        freeze_cluster(
            index + 1,
            cluster,
            ready_support=max(1, int(ready_support)),
            ready_logs=max(1, int(ready_logs)),
            ready_queries=max(1, int(ready_queries)),
        )
        for index, cluster in enumerate(clusters)
    ]
    counts = Counter(item["cluster_recommendation"] for item in frozen)
    return {
        "schema": "candidate_semantic_memory/v1",
        "description": "Report-only cross-session semantic memory for selector candidates.",
        "embedding_backend": embedding_backend,
        "embedding_descriptor": descriptor,
        "similarity_threshold": max(0.0, min(1.0, float(similarity_threshold))),
        "ready_thresholds": {
            "support": max(1, int(ready_support)),
            "source_logs": max(1, int(ready_logs)),
            "distinct_queries": max(1, int(ready_queries)),
        },
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "candidate_count": len(candidates),
        "cluster_count": len(frozen),
        "cluster_recommendation_counts": dict(sorted(counts.items())),
        "clusters": frozen,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Candidate Semantic Memory",
        "",
        "This report is advisory only. It does not promote runtime config.",
        "",
        f"Candidate count: **{report['candidate_count']}**",
        f"Cluster count: **{report['cluster_count']}**",
        f"Embedding backend: `{report['embedding_backend']}`",
        f"Similarity threshold: `{report['similarity_threshold']}`",
        "",
        "## Cluster Recommendation Counts",
        "",
        "```json",
        json.dumps(report["cluster_recommendation_counts"], indent=2),
        "```",
        "",
        "## Clusters",
        "",
        "| recommendation | representative | members | support | logs | queries | terms |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    if not report["clusters"]:
        lines.append("| semantic_hold | no candidates | 0 | 0 | 0 | 0 |  |")
    for cluster in report["clusters"]:
        lines.append(
            "| `{rec}` | `{rep}` | {members} | {support} | {logs} | {queries} | `{terms}` |".format(
                rec=cluster["cluster_recommendation"],
                rep=clean_cell(cluster["representative_term"]),
                members=cluster["member_count"],
                support=cluster["support"],
                logs=cluster["distinct_source_logs"],
                queries=cluster["distinct_queries"],
                terms=clean_cell(", ".join(cluster["terms"])),
            )
        )
    lines.extend(["", "## Artifacts", ""])
    for artifact in report["artifacts"]:
        lines.append(f"- `{artifact['path']}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a report-only semantic memory over candidate readiness artifacts.")
    parser.add_argument("--readiness", action="append", help="Candidate promotion-readiness JSON path. May be repeated.")
    parser.add_argument("--embedding-backend", choices=["hash", "config"], default="hash")
    parser.add_argument("--similarity-threshold", type=float, default=0.72)
    parser.add_argument("--ready-support", type=int, default=3)
    parser.add_argument("--ready-logs", type=int, default=2)
    parser.add_argument("--ready-queries", type=int, default=2)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    paths = parse_paths(args.readiness)
    if not paths:
        print(json.dumps({"ok": False, "error": "At least one --readiness artifact is required."}, indent=2))
        return 2

    report = build_report(
        paths,
        embedding_backend=args.embedding_backend,
        similarity_threshold=args.similarity_threshold,
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
                "cluster_count": report["cluster_count"],
                "cluster_recommendation_counts": report["cluster_recommendation_counts"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
