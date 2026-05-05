from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import resolve_project_path
from core.runtime import create_pipeline


RATINGS = {
    "excellent": 2.0,
    "useful": 1.0,
    "ok": 0.25,
    "neutral": 0.0,
    "missing_source": -0.5,
    "wrong_domain": -0.75,
    "stale": -0.75,
    "wrong": -1.0,
}


def preview(text: str, limit: int = 360) -> str:
    one_line = " ".join(str(text or "").split())
    return one_line if len(one_line) <= limit else one_line[: limit - 3] + "..."


def main() -> None:
    parser = argparse.ArgumentParser(description="Run manual retrieval probes and store feedback")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--db-path", default=None, help="Override configured database path")
    args = parser.parse_args()

    db_path = resolve_project_path(ROOT, args.db_path, "memory.db") if args.db_path else None
    pipeline = create_pipeline(ROOT, db_path=db_path)
    labels = ", ".join(RATINGS)
    print("Interactive retrieval test ready. Empty query exits.")
    print(f"Feedback labels: {labels}")
    try:
        while True:
            query = input("\nquery> ").strip()
            if not query:
                break
            results = pipeline.retrieve(query, top_k=max(1, args.top_k))
            if not results:
                print("No results.")
                continue
            for idx, item in enumerate(results, start=1):
                print(
                    f"\n[{idx}] {item['memory_id']} score={item['score']} "
                    f"domain={item.get('domain_name')} source={item.get('source')}"
                )
                print(preview(item["text"]))
            raw = input("\nrate as '<rank> <label> [notes]' or Enter to skip> ").strip()
            if not raw:
                continue
            rank_text, _, rest = raw.partition(" ")
            if not rank_text.isdigit():
                print("Rank must be a number.")
                continue
            rank = int(rank_text)
            if rank < 1 or rank > len(results):
                print("Rank is outside the result list.")
                continue
            label, _, notes = rest.strip().partition(" ")
            label = label.strip().lower()
            if label not in RATINGS:
                print(f"Unknown label. Use one of: {labels}")
                continue
            item = results[rank - 1]
            feedback = pipeline.db.add_retrieval_feedback(
                memory_id=item["memory_id"],
                label=label,
                query=query,
                rating=RATINGS[label],
                rank=rank,
                retrieval_score=item["score"],
                notes=notes.strip() or None,
                metadata={
                    "domain_name": item.get("domain_name"),
                    "source": item.get("source"),
                    "chunk_index": item.get("chunk_index"),
                    "cosine": item.get("cosine"),
                },
            )
            print(json.dumps({"stored": feedback}, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
