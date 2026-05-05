from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from core.config import load_config, resolve_project_path
from core.pipeline import MemoryPipeline
from core.runtime import configured_db_path, init_db, pipeline_stats


ROOT = Path(__file__).resolve().parent


def build_pipeline(
    root: Path,
    db_path: Path | None,
    fast_hash: bool = False,
    embedding_dim: int = 128,
) -> MemoryPipeline:
    config = load_config(root)
    resolved_db_path = db_path or configured_db_path(root, config)
    init_db(root, resolved_db_path)
    if fast_hash:
        embedding_config: dict[str, Any] | None = {"backend": "hash", "dim": int(embedding_dim)}
        dim = int(embedding_dim)
    else:
        embedding_config = config.get("embedding")
        dim = int(config.get("embedding_dim") or embedding_dim)
    return MemoryPipeline(
        root=root,
        db_path=resolved_db_path,
        embedding_dim=dim,
        top_k=int(config.get("top_k") or 8),
        embedding_config=embedding_config,
    )


class MemoryChat:
    def __init__(
        self,
        pipeline: MemoryPipeline,
        agent_id: str = "default",
        session_id: str | None = None,
        top_k: int = 5,
        source: str | None = None,
        store_session: bool = True,
    ):
        self.pipeline = pipeline
        self.agent_id = agent_id
        self.top_k = int(top_k)
        self.source = source
        self.store_session = bool(store_session)
        self.last_evidence: list[str] = []
        self.session_id = self._ensure_session(session_id)

    def _ensure_session(self, session_id: str | None = None) -> str:
        session = self.pipeline.db.ensure_session(
            session_id=session_id,
            agent_id=self.agent_id,
            title="memory chat",
            metadata={"client": "chat.py"},
        )
        return str(session["id"])

    def new_session(self) -> str:
        self.session_id = self._ensure_session(None)
        self.last_evidence = []
        return f"new session: {self.session_id}"

    def handle_line(self, line: str) -> str:
        cleaned = str(line or "").strip()
        if not cleaned:
            return ""
        if cleaned in {"/q", "/quit", "/exit"}:
            return "__quit__"
        if cleaned in {"/h", "/help"}:
            return self.help_text()
        if cleaned == "/session":
            return f"session: {self.session_id}\nagent: {self.agent_id}"
        if cleaned == "/new":
            return self.new_session()
        if cleaned == "/stats":
            return self.format_stats()
        if cleaned == "/history":
            return self.format_history()
        if cleaned.startswith("/teach "):
            return self.teach(cleaned[len("/teach ") :])
        if cleaned.startswith("/remember "):
            return self.teach(cleaned[len("/remember ") :])
        if cleaned.startswith("/correct "):
            return self.correct(cleaned[len("/correct ") :])
        if cleaned.startswith("/ask "):
            return self.ask(cleaned[len("/ask ") :])
        if cleaned.startswith("/"):
            return "unknown command. Type /help for commands."
        return self.ask(cleaned)

    def ask(self, query: str) -> str:
        result = self.pipeline.ask(
            query,
            top_k=self.top_k,
            session_id=self.session_id,
            agent_id=self.agent_id,
            store_session=self.store_session,
        )
        self.session_id = result.get("session_id") or self.session_id
        self.last_evidence = [
            str(item.get("memory_id"))
            for item in result.get("evidence", [])
            if item.get("memory_id")
        ]
        lines = [
            result["answer"],
            f"confidence: {result['confidence']:.3f} | conflict: {bool(result['conflict'])}",
        ]
        evidence = result.get("evidence", [])[: self.top_k]
        if evidence:
            lines.append("evidence:")
            for index, item in enumerate(evidence, start=1):
                source = item.get("source") or item.get("domain_name") or "memory"
                memory_id = item.get("memory_id")
                score = float(item.get("score") or 0.0)
                text = str(item.get("text") or item.get("text_preview") or "").replace("\n", " ").strip()
                lines.append(f"{index}. {memory_id} score={score:.3f} source={source}")
                lines.append(f"   {text[:220]}")
        return "\n".join(lines)

    def teach(self, text: str) -> str:
        result = self.pipeline.teach(
            text,
            source=self.source or f"chat:{self.agent_id}",
            session_id=self.session_id,
            agent_id=self.agent_id,
            store_session=True,
            metadata={"client": "chat.py"},
        )
        self.session_id = result.get("session_id") or self.session_id
        memory = result["memory"]
        self.last_evidence = [memory["memory_id"]]
        return (
            f"taught memory: {memory['memory_id']}\n"
            f"domain: {memory.get('domain_name')} | clc: {memory.get('clc_state')}"
        )

    def correct(self, text: str) -> str:
        result = self.pipeline.correct(
            text,
            target_memory_ids=self.last_evidence,
            target_query=text,
            top_k=self.top_k,
            source=self.source or f"chat:{self.agent_id}:correction",
            session_id=self.session_id,
            agent_id=self.agent_id,
            store_session=True,
            metadata={"client": "chat.py"},
        )
        self.session_id = result.get("session_id") or self.session_id
        memory = result["correction_memory"]
        self.last_evidence = [memory["memory_id"]]
        targets = ", ".join(result.get("target_memory_ids") or []) or "none"
        return f"corrected memory: {memory['memory_id']}\ntargets: {targets}"

    def format_history(self) -> str:
        rows = self.pipeline.db.session_history(self.session_id)
        if not rows:
            return "turns: 0"
        lines = [f"turns: {len(rows)}"]
        for row in rows[-12:]:
            role = row.get("role")
            content = str(row.get("content") or "").replace("\n", " ").strip()
            lines.append(f"{role}: {content[:220]}")
        return "\n".join(lines)

    def format_stats(self) -> str:
        stats = pipeline_stats(self.pipeline)
        return (
            f"database: {stats['database']}\n"
            f"memories: {stats['memories']} | domains: {stats['domains']} | "
            f"relations: {stats['relations']} | sessions: {stats['sessions']}"
        )

    @staticmethod
    def help_text() -> str:
        return "\n".join(
            [
                "commands:",
                "/ask <question>       ask memory and show evidence",
                "/teach <text>         store durable knowledge",
                "/remember <text>      alias for /teach",
                "/correct <text>       store a correction for the last evidence",
                "/history              show recent session turns",
                "/session              show active session",
                "/new                  start a new session",
                "/stats                show memory database stats",
                "/quit                 exit",
            ]
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive CLC-GCL memory chat client.")
    parser.add_argument("--db-path", default=None, help="SQLite database path. Defaults to config.yaml.")
    parser.add_argument("--agent-id", default="default", help="Agent identity stored with session turns.")
    parser.add_argument("--session-id", default=None, help="Continue an existing memory chat session.")
    parser.add_argument("--top-k", type=int, default=5, help="Evidence count to retrieve for answers.")
    parser.add_argument("--source", default=None, help="Source label for taught and corrected memories.")
    parser.add_argument("--no-store-session", action="store_true", help="Do not store ask turns.")
    parser.add_argument("--fast-hash", action="store_true", help="Use deterministic hash embeddings for fast tests.")
    parser.add_argument("--embedding-dim", type=int, default=128, help="Hash embedding dimension when --fast-hash is used.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = resolve_project_path(ROOT, args.db_path, "memory.db") if args.db_path else None
    pipeline = build_pipeline(ROOT, db_path, fast_hash=args.fast_hash, embedding_dim=args.embedding_dim)
    chat = MemoryChat(
        pipeline=pipeline,
        agent_id=args.agent_id,
        session_id=args.session_id,
        top_k=args.top_k,
        source=args.source,
        store_session=not args.no_store_session,
    )
    print(f"Memory chat ready. session={chat.session_id} agent={chat.agent_id}")
    print("Type /help for commands, /quit to exit.")
    try:
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            try:
                output = chat.handle_line(line)
            except Exception as exc:
                output = f"error: {exc}"
            if output == "__quit__":
                break
            if output:
                print(output)
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
