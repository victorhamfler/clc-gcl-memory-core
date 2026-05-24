from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_DB = ROOT / "memory_experiment_180_best.db"
OUT_JSON = REPO_ROOT / "experiments" / "canonical_memory_view_results.json"
OUT_MD = REPO_ROOT / "experiments" / "canonical_memory_view_report.md"
sys.path.insert(0, str(ROOT))

from core.canonical_memory import build_canonical_view  # noqa: E402


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def compact_report(view: dict[str, Any]) -> dict[str, Any]:
    top_claims = sorted(
        view["canonical_claims"],
        key=lambda claim: (-int(claim.get("support_count") or 0), str(claim.get("canonical_text") or "")),
    )[:20]
    top_edges = sorted(
        view["semantic_edges"],
        key=lambda edge: (not bool(edge.get("possible_conflict_or_update")), -float(edge.get("cosine") or 0.0)),
    )[:20]
    return {
        "schema": view["schema"],
        "mutates_db": view["mutates_db"],
        "db_path": view["db_path"],
        "row_count": view["row_count"],
        "canonical_claim_count": view["canonical_claim_count"],
        "exact_duplicate_claim_count": view["exact_duplicate_claim_count"],
        "exact_duplicate_extra_row_count": view["exact_duplicate_extra_row_count"],
        "semantic_edge_count": view["semantic_edge_count"],
        "semantic_edge_counts": view["semantic_edge_counts"],
        "config": view["config"],
        "top_claims": top_claims,
        "top_semantic_edges": top_edges,
        "architecture_interpretation": {
            "canonical_layer_role": "turn repeated memory rows into one claim with support/provenance metadata",
            "selector_effect": "retrieval can later down-rank duplicate pressure while still using support_count as confidence evidence",
            "ogcf_effect": "geometry can run on canonical claims or exact-unique shadows to avoid duplicate-dominated bridge clusters",
            "safety_rule": "semantic conflict/update edges must not be auto-merged; they are review/correction signals",
        },
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Canonical Memory View Evaluation",
        "",
        "This is a non-destructive canonical claim view. It does not mutate the source DB.",
        "",
        f"DB: `{report['db_path']}`",
        f"Rows: `{report['row_count']}`",
        f"Canonical claims: `{report['canonical_claim_count']}`",
        f"Exact duplicate claims: `{report['exact_duplicate_claim_count']}`",
        f"Exact duplicate extra rows: `{report['exact_duplicate_extra_row_count']}`",
        f"Semantic edges: `{report['semantic_edge_count']}`",
        "",
        "Semantic edge counts:",
        "",
        "```json",
        json.dumps(report["semantic_edge_counts"], indent=2),
        "```",
        "",
        "## Interpretation",
        "",
        "```json",
        json.dumps(report["architecture_interpretation"], indent=2),
        "```",
        "",
        "## Top Canonical Claims",
        "",
        "| support | duplicates | domains | namespaces | warnings | text |",
        "| ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for claim in report["top_claims"][:15]:
        lines.append(
            "| {support} | {dups} | {domains} | {namespaces} | `{warnings}` | {text} |".format(
                support=claim["support_count"],
                dups=len(claim["duplicate_memory_ids"]),
                domains=len(claim["domain_counts"]),
                namespaces=len(claim["namespace_counts"]),
                warnings=",".join(claim["warnings"]),
                text=clean_cell(claim["canonical_text"]),
            )
        )
    lines.extend(
        [
            "",
            "## Top Semantic Edges",
            "",
            "| kind | cosine | jaccard | left | right |",
            "| --- | ---: | ---: | --- | --- |",
        ]
    )
    for edge in report["top_semantic_edges"][:15]:
        kind = "conflict/update" if edge["possible_conflict_or_update"] else "clean paraphrase"
        lines.append(
            f"| `{kind}` | {edge['cosine']:.4f} | {edge['jaccard']:.4f} | {clean_cell(edge['left_text'], 90)} | {clean_cell(edge['right_text'], 90)} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a non-destructive canonical claim view from a memory DB.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--similarity-threshold", type=float, default=0.90)
    parser.add_argument("--jaccard-min", type=float, default=0.35)
    parser.add_argument("--max-pairs", type=int, default=50000)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()
    view = build_canonical_view(
        Path(args.db),
        limit=args.limit,
        similarity_threshold=max(0.0, min(1.0, float(args.similarity_threshold))),
        jaccard_min=max(0.0, min(1.0, float(args.jaccard_min))),
        max_pairs=max(1, int(args.max_pairs)),
    )
    report = compact_report(view)
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": True,
                "row_count": report["row_count"],
                "canonical_claim_count": report["canonical_claim_count"],
                "exact_duplicate_extra_row_count": report["exact_duplicate_extra_row_count"],
                "semantic_edge_counts": report["semantic_edge_counts"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
