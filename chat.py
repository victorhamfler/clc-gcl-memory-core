from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from core.config import load_config, resolve_project_path
from core.consolidation import consolidation_plan, create_consolidation_summaries
from core.maintenance import improvement_plan, memory_review, record_memory_improvement, weak_memories
from core.pipeline import MemoryPipeline
from core.runtime import configured_db_path, init_db, pipeline_stats, runtime_embedding_config


ROOT = Path(__file__).resolve().parent
FEEDBACK_RATINGS = {
    "excellent": 2.0,
    "useful": 1.0,
    "good": 1.0,
    "ok": 0.25,
    "neutral": 0.0,
    "missing_source": -0.5,
    "wrong_domain": -0.75,
    "stale": -0.75,
    "wrong": -1.0,
    "bad": -1.0,
}


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
        embedding_config = runtime_embedding_config(config)
        dim = int(config.get("embedding_dim") or embedding_dim)
    return MemoryPipeline(
        root=root,
        db_path=resolved_db_path,
        embedding_dim=dim,
        top_k=int(config.get("top_k") or 8),
        embedding_config=embedding_config,
        retrieval_weights=config.get("retrieval_weights"),
        clc_thresholds=config.get("thresholds"),
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
        namespace: str = "global",
    ):
        self.pipeline = pipeline
        self.agent_id = agent_id
        self.top_k = int(top_k)
        self.source = source
        self.store_session = bool(store_session)
        self.namespace = str(namespace or "global").strip() or "global"
        self.last_evidence: list[str] = []
        self.last_result: dict[str, Any] | None = None
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
            return self.format_session()
        if cleaned == "/new":
            return self.new_session()
        if cleaned == "/stats":
            return self.format_stats()
        if cleaned == "/history":
            return self.format_history()
        if cleaned == "/sources":
            return self.format_sources()
        if cleaned == "/why":
            return self.format_why()
        if cleaned.startswith("/consolidate"):
            return self.consolidate(cleaned[len("/consolidate") :])
        if cleaned.startswith("/memory"):
            return self.memory_maintenance(cleaned[len("/memory") :])
        if cleaned.startswith("/feedback "):
            return self.feedback(cleaned[len("/feedback ") :])
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
            namespace=self.namespace,
        )
        self.session_id = result.get("session_id") or self.session_id
        self.last_evidence = [
            str(item.get("memory_id"))
            for item in result.get("evidence", [])
            if item.get("memory_id")
        ]
        self.last_result = result
        session_context_used = bool(result.get("session_context_used"))
        lines = [
            result["answer"],
            (
                f"confidence: {result['confidence']:.3f} | conflict: {bool(result['conflict'])} "
                f"| session_context: {'yes' if session_context_used else 'no'}"
            ),
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
        source_context = result.get("source_context", [])[: self.top_k]
        if source_context:
            lines.append("source context:")
            for index, item in enumerate(source_context, start=1):
                source = item.get("source") or item.get("domain_name") or "memory"
                memory_id = item.get("memory_id")
                score = float(item.get("score") or 0.0)
                text = str(item.get("text") or item.get("text_preview") or "").replace("\n", " ").strip()
                lines.append(f"{index}. {memory_id} score={score:.3f} source={source}")
                lines.append(f"   {text[:220]}")
        stale_context = result.get("stale_context", [])[: self.top_k]
        if stale_context:
            lines.append("superseded context:")
            for index, item in enumerate(stale_context, start=1):
                source = item.get("source") or item.get("domain_name") or "memory"
                memory_id = item.get("memory_id")
                relation = item.get("relation_type") or "supersedes"
                text = str(item.get("text") or item.get("text_preview") or "").replace("\n", " ").strip()
                lines.append(f"{index}. {memory_id} relation={relation} source={source}")
                lines.append(f"   {text[:220]}")
        return "\n".join(lines)

    def teach(self, text: str) -> str:
        controls, cleaned = self._extract_memory_controls(text)
        result = self.pipeline.teach(
            cleaned,
            source=self.source or f"chat:{self.agent_id}",
            session_id=self.session_id,
            agent_id=self.agent_id,
            store_session=True,
            metadata={"client": "chat.py"},
            namespace=self.namespace,
            priority=controls.get("priority"),
            force_clc_state=controls.get("force_clc_state"),
        )
        self.session_id = result.get("session_id") or self.session_id
        memory = result["memory"]
        self.last_evidence = [memory["memory_id"]]
        self.last_result = None
        return (
            f"taught memory: {memory['memory_id']}\n"
            f"domain: {memory.get('domain_name')} | clc: {memory.get('clc_state')}"
        )

    def correct(self, text: str) -> str:
        controls, cleaned = self._extract_memory_controls(text)
        result = self.pipeline.correct(
            cleaned,
            target_memory_ids=self.last_evidence,
            target_query=cleaned,
            top_k=self.top_k,
            source=self.source or f"chat:{self.agent_id}:correction",
            session_id=self.session_id,
            agent_id=self.agent_id,
            store_session=True,
            metadata={"client": "chat.py"},
            namespace=self.namespace,
            priority=controls.get("priority") or "high",
            force_clc_state=controls.get("force_clc_state"),
        )
        self.session_id = result.get("session_id") or self.session_id
        memory = result["correction_memory"]
        self.last_evidence = [memory["memory_id"]]
        self.last_result = None
        targets = ", ".join(result.get("target_memory_ids") or []) or "none"
        return f"corrected memory: {memory['memory_id']}\ntargets: {targets}"

    @staticmethod
    def _extract_memory_controls(text: str) -> tuple[dict[str, str], str]:
        controls: dict[str, str] = {}
        parts = str(text or "").strip().split()
        consumed = 0
        for part in parts:
            lower = part.lower()
            if lower.startswith("priority="):
                controls["priority"] = lower.split("=", 1)[1]
                consumed += 1
                continue
            if lower.startswith("clc=") or lower.startswith("force=") or lower.startswith("force_clc_state="):
                controls["force_clc_state"] = part.split("=", 1)[1].upper()
                consumed += 1
                continue
            break
        cleaned = " ".join(parts[consumed:]).strip()
        if not cleaned:
            cleaned = str(text or "").strip()
        return controls, cleaned

    def feedback(self, text: str) -> str:
        parts = str(text or "").strip().split()
        if not parts:
            return "usage: /feedback <label> [evidence-number|memory-id|all] [notes]"
        if not self.last_result or not self.last_evidence:
            return "ask something first so feedback can attach to evidence."
        label = parts[0].strip().lower()
        rating = FEEDBACK_RATINGS.get(label, 0.0)
        target = parts[1].strip() if len(parts) > 1 else ""
        notes_start = 1
        targets = self._feedback_targets(target)
        if target and (target.isdigit() or target.startswith("mem_") or target in {"all", "evidence"}):
            notes_start = 2
        notes = " ".join(parts[notes_start:]).strip() or None
        query = str(self.last_result.get("query") or "")
        feedback_rows = []
        evidence_by_id = {
            str(item.get("memory_id")): item
            for item in self.last_result.get("evidence", [])
            if item.get("memory_id")
        }
        for memory_id in targets:
            item = evidence_by_id.get(memory_id, {})
            feedback_rows.append(
                self.pipeline.db.add_retrieval_feedback(
                    memory_id,
                    label,
                    query=query,
                    rating=rating,
                    rank=item.get("rank"),
                    retrieval_score=item.get("score"),
                    notes=notes,
                    metadata={"client": "chat.py", "agent_id": self.agent_id, "session_id": self.session_id},
                )
            )
        ids = ", ".join(row["memory_id"] for row in feedback_rows)
        return f"feedback stored: {label} rating={rating:g} targets={ids}"

    def _feedback_targets(self, target: str) -> list[str]:
        cleaned = str(target or "").strip()
        if not cleaned:
            return self.last_evidence[:1]
        if cleaned in {"all", "evidence"}:
            return list(self.last_evidence)
        if cleaned.isdigit():
            index = int(cleaned) - 1
            if index < 0 or index >= len(self.last_evidence):
                raise ValueError(f"evidence number out of range: {cleaned}")
            return [self.last_evidence[index]]
        if cleaned.startswith("mem_"):
            return [cleaned]
        return self.last_evidence[:1]

    def format_sources(self) -> str:
        if not self.last_result:
            return "ask something first to inspect sources."
        lines = ["sources:"]
        self._append_source_lines(lines, "evidence", self.last_result.get("evidence", []))
        self._append_source_lines(lines, "source context", self.last_result.get("source_context", []))
        self._append_source_lines(lines, "superseded context", self.last_result.get("stale_context", []))
        return "\n".join(lines)

    def format_why(self) -> str:
        if not self.last_result:
            return "ask something first to inspect why."
        lines = [
            f"query: {self.last_result.get('query')}",
            f"retrieval_query: {str(self.last_result.get('retrieval_query') or '').replace(chr(10), ' ')[:360]}",
            f"confidence: {float(self.last_result.get('confidence') or 0.0):.3f} | conflict: {bool(self.last_result.get('conflict'))}",
            (
                f"counts: evidence={len(self.last_result.get('evidence', []))} "
                f"summary={len(self.last_result.get('summary', []))} "
                f"source_context={len(self.last_result.get('source_context', []))} "
                f"current={len(self.last_result.get('current', []))} "
                f"stale={len(self.last_result.get('stale', []))} "
                f"superseded={len(self.last_result.get('stale_context', []))}"
            ),
        ]
        raw = self.last_result.get("raw_results", [])[: self.top_k]
        if raw:
            lines.append("top scoring memories:")
            for index, item in enumerate(raw, start=1):
                source = item.get("source") or item.get("domain_name") or "memory"
                lines.append(
                    f"{index}. {item.get('memory_id')} score={float(item.get('score') or 0.0):.3f} "
                    f"cos={float(item.get('cosine') or 0.0):.3f} text={float(item.get('text_match_score') or 0.0):.3f} "
                    f"feedback={float(item.get('feedback_score') or 0.0):.3f} "
                    f"sup={float(item.get('supersession_score') or 0.0):.3f} "
                    f"rel={float(item.get('relation_supersession_score') or 0.0):.3f} "
                    f"sum={float(item.get('summary_relation_score') or 0.0):.3f} source={source}"
                )
        return "\n".join(lines)

    def consolidate(self, text: str) -> str:
        parts = str(text or "").strip().split()
        action = parts[0].lower() if parts else "plan"
        options = self._parse_consolidation_options(parts[1:])
        if action in {"plan", ""}:
            plan = consolidation_plan(
                self.pipeline.db,
                min_domain_memories=options["min_domain_memories"],
                max_candidates_per_domain=options["max_candidates_per_domain"],
                namespace=self.namespace,
            )
            return self._format_consolidation_plan(plan)
        if action in {"create", "run"}:
            result = create_consolidation_summaries(
                self.pipeline,
                min_domain_memories=options["min_domain_memories"],
                max_candidates_per_domain=options["max_candidates_per_domain"],
                max_groups=options["max_groups"],
                namespace=self.namespace,
            )
            lines = [
                f"created summaries: {result['created']}",
                self._format_consolidation_plan(result["plan"]),
            ]
            for item in result.get("created_summaries", []):
                lines.append(
                    f"summary: {item['summary_memory_id']} domain={item['domain_name']} "
                    f"sources={len(item.get('source_memory_ids') or [])}"
                )
            return "\n".join(lines)
        if action == "sources":
            if len(parts) < 2:
                return "usage: /consolidate sources <summary-memory-id>"
            rows = self.pipeline.db.summarized_memories_for_sources([parts[1]], limit=20)
            if not rows:
                return f"summary sources: none for {parts[1]}"
            lines = [f"summary sources for {parts[1]}:"]
            for index, row in enumerate(rows, start=1):
                text_preview = str(row.get("text") or "").replace("\n", " ").strip()[:220]
                source = row.get("source") or row.get("domain_name") or "memory"
                lines.append(f"{index}. {row['memory_id']} source={source}")
                lines.append(f"   {text_preview}")
            return "\n".join(lines)
        return "usage: /consolidate plan|create|sources [options]"

    def memory_maintenance(self, text: str) -> str:
        parts = str(text or "").strip().split()
        action = parts[0].lower() if parts else "review"
        if action in {"review", ""}:
            payload = memory_review(self.pipeline.db, weak_limit=self.top_k, namespace=self.namespace)
            return self._format_memory_review(payload)
        if action == "weak":
            include_resolved = len(parts) > 1 and parts[1].lower() in {"resolved", "all"}
            limit_part = parts[2] if include_resolved and len(parts) > 2 else (parts[1] if len(parts) > 1 else "")
            limit = int(limit_part) if str(limit_part).isdigit() else self.top_k
            rows = weak_memories(self.pipeline.db, limit=limit, include_resolved=include_resolved, namespace=self.namespace)
            return self._format_weak_memories(rows, title="weak memories")
        if action == "resolved":
            limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else self.top_k
            rows = [
                item
                for item in weak_memories(self.pipeline.db, limit=limit, include_resolved=True, namespace=self.namespace)
                if item.get("resolved")
            ]
            return self._format_weak_memories(rows, title="resolved weak memories")
        if action == "improve":
            if len(parts) < 2:
                plan = improvement_plan(self.pipeline.db, limit=self.top_k, namespace=self.namespace)
                return self._format_improvement_plan(plan)
            memory_id = parts[1]
            note = " ".join(parts[2:]).strip()
            if not note:
                plan = improvement_plan(self.pipeline.db, memory_id=memory_id, limit=1, namespace=self.namespace)
                return self._format_improvement_plan(plan)
            result = record_memory_improvement(
                self.pipeline,
                memory_id,
                note,
                agent_id=self.agent_id,
                session_id=self.session_id,
                namespace=self.namespace,
            )
            improvement_id = result["improvement_memory"]["memory_id"]
            self.last_evidence = [improvement_id]
            self.last_result = None
            return f"improvement stored: {improvement_id}\ntarget: {memory_id}\nrelation: updates"
        return "usage: /memory review|weak|resolved|improve [memory-id] [note]"

    def _format_memory_review(self, payload: dict[str, Any]) -> str:
        stats = payload["stats"]
        lines = [
            f"memory review: memories={stats['memories']} domains={stats['domains']} relations={stats['relations']} feedback={stats['retrieval_feedback']}",
            "recommendations: " + ", ".join(payload.get("recommendations", [])),
        ]
        flagged_domains = [domain for domain in payload.get("domains", []) if domain.get("health_flags")]
        if flagged_domains:
            lines.append("domain flags:")
            for domain in flagged_domains[: self.top_k]:
                lines.append(f"- {domain['name']} ({domain.get('namespace')}): {', '.join(domain['health_flags'])}")
        weak = payload.get("weak_memories", [])
        if weak:
            lines.append("weak memories:")
            lines.extend(self._weak_memory_lines(weak[: self.top_k]))
        consolidation = payload.get("consolidation", {})
        if consolidation.get("candidate_group_count"):
            lines.append(
                f"consolidation candidates: {consolidation['candidate_group_count']} groups, "
                f"protected={consolidation.get('protected_count', 0)}"
            )
        return "\n".join(lines)

    def _format_weak_memories(self, rows: list[dict[str, Any]], title: str = "weak memories") -> str:
        if not rows:
            return f"{title}: none"
        return "\n".join([f"{title}:", *self._weak_memory_lines(rows)])

    @staticmethod
    def _weak_memory_lines(rows: list[dict[str, Any]]) -> list[str]:
        lines = []
        for index, item in enumerate(rows, start=1):
            reasons = ",".join(item.get("reasons") or [])
            source = item.get("source") or item.get("domain_name") or "memory"
            lines.append(
                f"{index}. {item['memory_id']} weak={float(item.get('weakness_score') or 0.0):.2f} "
                f"action={item.get('recommended_action')} resolved={bool(item.get('resolved'))} "
                f"namespace={item.get('namespace')} source={source}"
            )
            lines.append(f"   reasons={reasons or 'none'}")
            lines.append(f"   {str(item.get('text_preview') or '')[:220]}")
        return lines

    @staticmethod
    def _format_improvement_plan(plan: dict[str, Any]) -> str:
        steps = plan.get("suggested_next_steps", [])
        if not steps:
            return "improvement plan: no weak memory items found"
        lines = ["improvement plan:"]
        for step in steps:
            lines.append(f"- {step}")
        return "\n".join(lines)

    @staticmethod
    def _parse_consolidation_options(parts: list[str]) -> dict[str, int | None]:
        options: dict[str, int | None] = {
            "min_domain_memories": 4,
            "max_candidates_per_domain": 8,
            "max_groups": None,
        }
        positional = []
        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                key = key.strip().lower().replace("-", "_")
                if key in {"min", "min_domain_memories"}:
                    options["min_domain_memories"] = max(1, int(value))
                elif key in {"max", "max_candidates", "max_candidates_per_domain"}:
                    options["max_candidates_per_domain"] = max(1, int(value))
                elif key in {"groups", "max_groups"}:
                    options["max_groups"] = max(0, int(value))
            else:
                positional.append(part)
        if positional:
            options["min_domain_memories"] = max(1, int(positional[0]))
        if len(positional) > 1:
            options["max_candidates_per_domain"] = max(1, int(positional[1]))
        if len(positional) > 2:
            options["max_groups"] = max(0, int(positional[2]))
        return options

    @staticmethod
    def _format_consolidation_plan(plan: dict[str, Any]) -> str:
        lines = [
            (
                f"plan: groups={plan.get('candidate_group_count', 0)} "
                f"protected={plan.get('protected_count', 0)}"
            )
        ]
        for group in plan.get("candidate_groups", [])[:8]:
            lines.append(
                f"- {group['domain_name']} ({group.get('namespace')}): candidates={group['candidate_count']} "
                f"action={group.get('action')}"
            )
        return "\n".join(lines)

    @staticmethod
    def _append_source_lines(lines: list[str], label: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        lines.append(f"{label}:")
        for index, item in enumerate(rows, start=1):
            source = item.get("source") or item.get("domain_name") or "memory"
            memory_id = item.get("memory_id")
            state = item.get("memory_state") or "context"
            text = str(item.get("text") or item.get("text_preview") or "").replace("\n", " ").strip()
            lines.append(f"{index}. {memory_id} state={state} source={source}")
            lines.append(f"   {text[:220]}")

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

    def format_session(self) -> str:
        lines = [f"session: {self.session_id}", f"agent: {self.agent_id}", f"namespace: {self.namespace}"]
        memories = self.pipeline.db.list_session_memory(self.session_id)
        for item in memories:
            if item.get("key") != "active_topic":
                continue
            value = str(item.get("value") or "").replace("\n", " ").strip()
            metadata = item.get("metadata") or {}
            evidence = metadata.get("evidence_memory_ids") or []
            lines.append(f"active: {value[:260]}")
            lines.append(f"active evidence: {', '.join(evidence) if evidence else 'none'}")
            break
        return "\n".join(lines)

    def format_stats(self) -> str:
        stats = pipeline_stats(self.pipeline)
        return (
            f"database: {stats['database']}\n"
            f"memories: {stats['memories']} | domains: {stats['domains']} | "
            f"relations: {stats['relations']} | sessions: {stats['sessions']} | "
            f"session memories: {stats.get('session_memory', 0)} | "
            f"uses: {stats.get('retrieval_uses', 0)}"
        )

    @staticmethod
    def help_text() -> str:
        return "\n".join(
            [
                "commands:",
                "/ask <question>       ask memory and show evidence",
                "/teach <text>         store durable knowledge; optional prefix priority=high or clc=PROTECT",
                "/remember <text>      alias for /teach",
                "/correct <text>       store a correction for the last evidence; optional prefix priority=high or clc=FOCUS",
                "/feedback <label>     train last evidence; optional target: number, memory id, all",
                "/sources              show evidence, source context, and superseded context",
                "/why                  show retrieval scoring details for the last answer",
                "/consolidate plan     preview safe summary groups",
                "/consolidate create   create summary memories; options: min=4 max=8 groups=1",
                "/consolidate sources  show source memories behind a summary",
                "/memory review        inspect weak memories, domain flags, and recommendations",
                "/memory weak          list weak memory candidates",
                "/memory resolved      list repaired weak memories",
                "/memory improve       plan or store a clarifying update for a memory",
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
    parser.add_argument("--namespace", default="global", help="Memory namespace to read/write.")
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
        namespace=args.namespace,
    )
    print(f"Memory chat ready. session={chat.session_id} agent={chat.agent_id} namespace={chat.namespace}")
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
