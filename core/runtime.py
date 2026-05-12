from __future__ import annotations

import os
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


def running_inside_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


def runtime_embedding_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return an embedding config appropriate for the current OS runtime.

    The committed config is Windows-first because Windows needs the
    `wsl_llama_cpp` bridge to reach the GGUF model inside WSL. When the same
    project runs inside WSL, the bridge cannot call `wsl`, so use native
    `llama_cpp` against `wsl_model_path` instead.
    """

    embedding = dict((config or {}).get("embedding") or {})
    if not embedding:
        return None
    backend = str(embedding.get("backend") or "").strip().lower().replace("-", "_")
    if running_inside_wsl() and backend in {"wsl_llama_cpp", "wsl_gguf"}:
        embedding["backend"] = "llama_cpp"
        if embedding.get("wsl_model_path"):
            embedding["gguf_path"] = embedding["wsl_model_path"]
    return embedding


def resolve_embedding_cache_path(root: Path, embedding: dict[str, Any] | None) -> dict[str, Any] | None:
    if not embedding:
        return embedding
    out = dict(embedding)
    cache_path = out.get("cache_path")
    if cache_path:
        out["cache_path"] = str(resolve_project_path(root, cache_path, "logs/embedding_cache.sqlite"))
    return out


def create_pipeline(root: Path, db_path: Path | None = None) -> MemoryPipeline:
    config = load_config(root)
    resolved_db_path = db_path or configured_db_path(root, config)
    init_db(root, resolved_db_path)
    embedding_config = resolve_embedding_cache_path(root, runtime_embedding_config(config))
    return MemoryPipeline(
        root=root,
        db_path=resolved_db_path,
        embedding_dim=int(config.get("embedding_dim") or 128),
        top_k=int(config.get("top_k") or 8),
        embedding_config=embedding_config,
        retrieval_weights=config.get("retrieval_weights"),
        clc_thresholds=config.get("thresholds"),
    )


def pipeline_stats(pipeline: MemoryPipeline) -> dict[str, Any]:
    stats = pipeline.db.stats()
    domains = [
        {
            "id": d.id,
            "name": d.name,
            "namespace": d.namespace,
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
        "retrieval_weights": pipeline.retrieval_weights,
        "sources_detail": pipeline.db.source_counts(),
        "namespaces_detail": pipeline.db.namespace_counts(),
        "feedback_detail": pipeline.db.feedback_counts(),
        "usage_detail": pipeline.db.memory_usage(limit=10),
        "relations_detail": pipeline.db.relation_counts(),
        "sessions_detail": pipeline.db.list_sessions(limit=10),
    }
