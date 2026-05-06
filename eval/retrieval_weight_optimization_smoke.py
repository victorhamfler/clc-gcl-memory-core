from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.retrieval_weight_optimization import run


def main() -> None:
    with TemporaryDirectory() as tmp:
        payload = run(Path(tmp) / "retrieval_weight_optimization_smoke.db", fast_hash=True)

    assert payload["ok"] is True
    assert payload["results"]
    assert payload["best_profile"]
    assert payload["best_score"] >= 0.75
    assert payload["baseline_score"] >= 0.75
    assert "retrieval_weights:" in payload["best_config"]
    assert len(payload["results"]) >= 3

    print(
        json.dumps(
            {
                "ok": True,
                "best_profile": payload["best_profile"],
                "best_score": payload["best_score"],
                "baseline_score": payload["baseline_score"],
                "score_delta": payload["score_delta"],
                "profile_count": len(payload["results"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
