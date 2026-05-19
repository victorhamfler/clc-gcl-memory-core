from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.clc_policy_selector import POLICY_LONG_SEVERE  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from core.selector_runtime import build_policy_selector, selector_features_from_retrieval_context  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
OUT_JSON = REPO_ROOT / "experiments" / "selector_live_retrieval_pipeline_eval_results.json"


def main() -> int:
    query = "What is Victor's current drink preference?"
    old_memory = "Victor likes espresso in the morning and green tea in the afternoon."
    correction = "Victor currently drinks water, not espresso or green tea."

    config = load_config(ROOT)
    selector = build_policy_selector(ROOT, config)
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "selector_live_retrieval.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()
        pipeline = MemoryPipeline(
            root=ROOT,
            db_path=db_path,
            embedding_config={"backend": "hash", "dim": 128},
        )
        try:
            taught = pipeline.teach(
                old_memory,
                source="agent_memory_v1/preferences.md",
                namespace="selector_live",
                agent_id="selector_eval",
                store_session=False,
                domain="food_drink",
                memory_type="preference",
            )
            corrected = pipeline.correct(
                correction,
                target_memory_ids=[taught["memory"]["memory_id"]],
                target_query=query,
                top_k=5,
                source="agent_memory_v2/corrections.md",
                namespace="selector_live",
                agent_id="selector_eval",
                store_session=False,
                relation_type="corrects",
                domain="food_drink",
                memory_type="preference",
            )
            retrieval_rows = pipeline.retrieve(query, top_k=5, namespace="selector_live", include_global=False)
        finally:
            pipeline.close()

    features, diagnostics = selector_features_from_retrieval_context(
        retrieval_rows,
        condition_name="hard_budget144",
    )
    explanation = selector.explain(features, top_k=5)
    retrieved_ids = [row.get("memory_id") for row in retrieval_rows]
    failures = []
    if taught["memory"]["memory_id"] not in retrieved_ids:
        failures.append("retrieval should include the old corrected memory")
    if corrected["correction_memory"]["memory_id"] not in retrieved_ids:
        failures.append("retrieval should include the correction memory")
    if diagnostics["stale_rows"] < 1:
        failures.append("live retrieval diagnostics should find at least one stale row")
    if diagnostics["current_rows"] < 1:
        failures.append("live retrieval diagnostics should find at least one current row")
    if diagnostics["stale_ratio"] <= 0.0:
        failures.append("live retrieval diagnostics should expose stale pressure")
    if not features.hard:
        failures.append("live stale/current conflict should produce hard selector features")
    if explanation["decision"]["policy"] != POLICY_LONG_SEVERE:
        failures.append(f"live stale/current conflict should select long severe, got {explanation['decision']['policy']}")

    report = {
        "ok": not failures,
        "query": query,
        "taught_memory_id": taught["memory"]["memory_id"],
        "correction_memory_id": corrected["correction_memory"]["memory_id"],
        "retrieval_rows": retrieval_rows,
        "features": features.__dict__,
        "diagnostics": diagnostics,
        "decision": explanation["decision"],
        "votes": explanation["votes"],
        "nearest_samples": explanation["nearest_samples"][:5],
        "failures": failures,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
