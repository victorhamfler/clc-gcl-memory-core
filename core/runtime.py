from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import load_config, resolve_project_path
from core.pipeline import MemoryPipeline
from storage.db import MemoryDB


def schema_path(root: Path) -> Path:
    return root / "storage" / "schema.sql"


def configured_db_path(root: Path, config: dict[str, Any] | None = None) -> Path:
    cfg = config if config is not None else load_config(root)
    return resolve_project_path(root, cfg.get("database_path"), "memory.db")


def init_db(root: Path, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = MemoryDB(db_path)
    try:
        db.init_schema(schema_path(root))
    finally:
        db.close()


def create_pipeline(root: Path, db_path: Path | None = None) -> MemoryPipeline:
    config = load_config(root)
    resolved_db_path = db_path or configured_db_path(root, config)
    init_db(root, resolved_db_path)
    return MemoryPipeline(
        root=root,
        db_path=resolved_db_path,
        embedding_dim=int(config.get("embedding_dim") or 128),
        top_k=int(config.get("top_k") or 8),
        embedding_config=config.get("embedding"),
    )


def pipeline_stats(pipeline: MemoryPipeline) -> dict[str, Any]:
    stats = pipeline.db.stats()
    domains = [
        {
            "id": d.id,
            "name": d.name,
            "memory_count": d.memory_count,
            "effective_dimension": round(d.effective_dimension, 4),
            "drift_ema": round(d.drift_ema, 6),
            "curvature_ema": round(d.curvature_ema, 6),
            "stability": round(d.stability, 4),
        }
        for d in pipeline.db.list_domains()
    ]
    return {
        "database": str(pipeline.db.db_path),
        **stats,
        "domains_detail": domains,
        "sources_detail": pipeline.db.source_counts(),
        "feedback_detail": pipeline.db.feedback_counts(),
        "relations_detail": pipeline.db.relation_counts(),
        "sessions_detail": pipeline.db.list_sessions(limit=10),
    }
