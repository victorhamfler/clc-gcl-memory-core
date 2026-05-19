from __future__ import annotations

from typing import Any

from core.learning import normalize_llm_config
from core.llm_client import OpenAICompatibleLLMClient
from storage.db import normalize_namespace


ALLOWED_PLAN_ENDPOINTS = {
    "/ask",
    "/retrieve",
    "/query",
    "/teach",
    "/correct",
    "/learn",
    "/learn/document",
    "/authority",
    "/consolidation_plan",
    "/memory_review",
    "/feedback",
}


def plan_memory_actions(
    instruction: str,
    llm_config: dict[str, Any] | None,
    stats: dict[str, Any],
    namespace: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = normalize_llm_config(llm_config)
    if not cfg.get("enabled"):
        return {"ok": False, "error": "LLM backend disabled", "mode": "agent_plan"}
    cleaned = str(instruction or "").strip()
    if not cleaned:
        raise ValueError("POST /agent_plan requires JSON field 'instruction'")
    memory_namespace = normalize_namespace(namespace)
    prompt = build_agent_plan_prompt(cleaned, memory_namespace, stats, context or {})
    client = OpenAICompatibleLLMClient(cfg)
    raw_plan = client.complete_json(
        prompt,
        system="You plan safe memory API actions. Return only valid JSON and never execute actions.",
    )
    plan = normalize_agent_plan(raw_plan, default_namespace=memory_namespace)
    return {
        "ok": True,
        "mode": "agent_plan",
        "namespace": memory_namespace,
        "instruction": cleaned,
        "requires_confirmation": True,
        "llm_usage": client.last_usage,
        "llm_model": client.last_model,
        **plan,
    }


def build_agent_plan_prompt(instruction: str, namespace: str, stats: dict[str, Any], context: dict[str, Any]) -> str:
    namespace_counts = stats.get("namespaces_detail") or []
    return (
        "You are a planner for an AI agent memory program. Decide which memory API actions should be proposed.\n"
        "Do not execute anything. Do not invent memory ids. Use target_query when a correction target is not known.\n"
        "Allowed endpoints: /ask, /retrieve, /teach, /correct, /learn, /learn/document, /authority, "
        "/consolidation_plan, /memory_review, /feedback.\n"
        "Prefer /teach for one clear durable fact. Prefer /learn for longer text needing extraction. "
        "Prefer /correct when the instruction changes a prior fact. Prefer /ask for questions.\n"
        "Return only JSON in this exact shape:\n"
        "{\"summary\":\"...\",\"actions\":[{\"endpoint\":\"/teach\",\"payload\":{...},\"reason\":\"...\"}],"
        "\"warnings\":[\"...\"]}\n\n"
        f"Default namespace: {namespace}\n"
        f"Memory count: {stats.get('memories')}\n"
        f"Namespace counts: {namespace_counts}\n"
        f"Optional context: {context}\n\n"
        f"Instruction: {instruction}"
    )


def normalize_agent_plan(raw_plan: Any, default_namespace: str) -> dict[str, Any]:
    if not isinstance(raw_plan, dict):
        raise ValueError("LLM agent plan must be a JSON object")
    raw_actions = raw_plan.get("actions") or []
    if not isinstance(raw_actions, list):
        raise ValueError("LLM agent plan 'actions' must be a list")
    actions = []
    warnings = [str(item) for item in raw_plan.get("warnings") or []]
    for idx, action in enumerate(raw_actions):
        if not isinstance(action, dict):
            warnings.append(f"ignored action {idx}: not an object")
            continue
        endpoint = str(action.get("endpoint") or "").strip()
        if endpoint == "/query":
            endpoint = "/retrieve"
        if endpoint not in ALLOWED_PLAN_ENDPOINTS:
            warnings.append(f"ignored action {idx}: unsupported endpoint {endpoint or '<empty>'}")
            continue
        payload = action.get("payload") or {}
        if not isinstance(payload, dict):
            warnings.append(f"ignored action {idx}: payload is not an object")
            continue
        payload = dict(payload)
        payload.setdefault("namespace", default_namespace)
        actions.append(
            {
                "endpoint": endpoint,
                "payload": payload,
                "reason": str(action.get("reason") or "").strip() or None,
            }
        )
    return {
        "summary": str(raw_plan.get("summary") or "").strip() or None,
        "actions": actions,
        "warnings": warnings,
    }
