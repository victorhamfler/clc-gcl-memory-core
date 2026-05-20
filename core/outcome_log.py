from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import resolve_project_path
from storage.db import new_id, utc_now


DEFAULT_OUTCOME_LOG = "logs/memory_outcomes.jsonl"


class OutcomeLogger:
    """Append-only JSONL log for memory operation outcomes.

    The log is intentionally outside the SQLite memory graph. It is training
    material for later selector and memory-policy analysis, so write failures
    should never break normal memory operations.
    """

    def __init__(self, root: Path, config: dict[str, Any] | None = None):
        cfg = (config or {}).get("outcome_log")
        if not isinstance(cfg, dict):
            cfg = {}
        self.enabled = bool(cfg.get("enabled", True))
        self.path = resolve_project_path(root, cfg.get("path"), DEFAULT_OUTCOME_LOG)
        self.max_text_chars = max(80, int(cfg.get("max_text_chars") or 600))
        self.max_list_items = max(1, int(cfg.get("max_list_items") or 20))

    def record(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        operation_id: str | None = None,
        linked_operation_id: str | None = None,
    ) -> dict[str, Any]:
        op_id = str(operation_id or "").strip() or new_id("op")
        event = {
            "schema_version": 1,
            "operation_id": op_id,
            "linked_operation_id": str(linked_operation_id or "").strip() or None,
            "event_type": str(event_type or "memory_operation").strip() or "memory_operation",
            "created_at": utc_now(),
            "payload": self._clean(payload),
        }
        status = {"operation_id": op_id, "logged": False, "path": str(self.path), "error": None}
        if not self.enabled:
            return status
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            status["logged"] = True
        except OSError as exc:
            status["error"] = str(exc)
        return status

    def _clean(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._clean(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            items = [self._clean(item) for item in list(value)[: self.max_list_items]]
            if len(value) > self.max_list_items:
                items.append({"truncated_items": len(value) - self.max_list_items})
            return items
        if isinstance(value, str):
            if len(value) > self.max_text_chars:
                return value[: self.max_text_chars] + f"...[truncated {len(value) - self.max_text_chars} chars]"
            return value
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return str(value)
