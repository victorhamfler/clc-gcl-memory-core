from __future__ import annotations

import argparse
import http.client
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import CLCLearnedPolicySelector, CLCPolicyFeatures, CLCPolicySelector  # noqa: E402


OUTCOME_LOG = REPO_ROOT / "experiments" / "hermes_clc_selector_outcome_labels.jsonl"
LEARNED_MATRIX = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_live_results.json"


SCENARIOS = [
    {
        "id": "short_hard_preference_conflict",
        "condition_name": "hard_budget144",
        "agent_task": (
            "Teach a stable preference, introduce a direct contradictory correction, "
            "then ask which memory should be treated as current."
        ),
        "expected_policy": "xseq_memory_r45_badmajority",
        "expected_action": "XSEQ_MEMORY_REFRESH",
    },
    {
        "id": "short_standard_agent_fact_update",
        "condition_name": "standard_budget144",
        "agent_task": (
            "Teach a normal agent-memory fact, update it once with compatible evidence, "
            "then ask for the current fact."
        ),
        "expected_policy": "long_severe_r16_overwrite",
        "expected_action": "LONG_SEVERE_VERIFIED_REFRESH",
    },
    {
        "id": "long_hard_multi_topic_stream",
        "condition_name": "long2_hard_budget288",
        "agent_task": (
            "Run a longer mixed-topic memory stream with corrections and unrelated topics; "
            "verify that Hermes does not over-adapt the memory state."
        ),
        "expected_policy": "periodic_baseline",
        "expected_action": "PROTECT_PERIODIC",
    },
    {
        "id": "long_standard_session_recall",
        "condition_name": "long2_standard_budget288",
        "agent_task": (
            "Run a longer ordinary session recall task and verify periodic/protect behavior "
            "keeps retrieval stable."
        ),
        "expected_policy": "periodic_baseline",
        "expected_action": "PROTECT_PERIODIC",
    },
]


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict:
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    try:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        resp_body = resp.read().decode("utf-8")
        if resp.status >= 400:
            raise RuntimeError(f"{method} {url} failed with HTTP {resp.status}: {resp_body}")
        return json.loads(resp_body)
    finally:
        conn.close()


def get_json(url: str) -> dict:
    return request_json("GET", url, timeout=15)


def post_json(url: str, payload: dict) -> dict:
    return request_json("POST", url, payload, timeout=30)


def build_selector(selector_mode: str) -> CLCPolicySelector | CLCLearnedPolicySelector:
    if selector_mode == "learned":
        if LEARNED_MATRIX.exists():
            return CLCLearnedPolicySelector.from_matrix_report(LEARNED_MATRIX, k=3)
        return CLCLearnedPolicySelector.from_outcome_log(OUTCOME_LOG, k=3)
    return CLCPolicySelector()


def features_for_condition(condition_name: str) -> CLCPolicyFeatures:
    if condition_name == "hard_budget144":
        return CLCPolicyFeatures.from_condition_name(condition_name, memory_bad_rate=0.75, probe_drop=0.18, csd_ratio=1.4)
    if condition_name == "standard_budget144":
        return CLCPolicyFeatures.from_condition_name(condition_name, memory_bad_rate=0.25, probe_drop=0.08, csd_ratio=0.9)
    if condition_name == "long2_hard_budget288":
        return CLCPolicyFeatures.from_condition_name(condition_name, memory_bad_rate=0.35, probe_drop=0.04, csd_ratio=0.7)
    if condition_name == "long2_standard_budget288":
        return CLCPolicyFeatures.from_condition_name(condition_name, memory_bad_rate=0.2, probe_drop=0.03, csd_ratio=0.6)
    return CLCPolicyFeatures.from_condition_name(condition_name)


def build_plan(selector_mode: str) -> dict:
    selector = build_selector(selector_mode)
    scenario_reports = []
    failures = []
    for scenario in SCENARIOS:
        decision = selector.select(features_for_condition(scenario["condition_name"]))
        expected_policy = decision.policy if selector_mode == "learned" else scenario["expected_policy"]
        expected_action = decision.action if selector_mode == "learned" else scenario["expected_action"]
        ok = decision.policy == expected_policy and decision.action == expected_action
        if not ok:
            failures.append(scenario["id"])
        scenario_reports.append(
            {
                **scenario,
                "expected_policy": expected_policy,
                "expected_action": expected_action,
                "selector_policy": decision.policy,
                "selector_action": decision.action,
                "selector_reason": decision.reason,
                "selector_confidence": decision.confidence,
                "ok": ok,
            }
        )
    return {
        "ok": not failures,
        "purpose": "Hermes-facing CLC selector smoke plan",
        "namespace": "agent:hermes",
        "agent_id": "hermes",
        "selector": "CLCLearnedPolicySelector" if selector_mode == "learned" else "CLCPolicySelector",
        "selector_mode": selector_mode,
        "selector_source": str(LEARNED_MATRIX if selector_mode == "learned" and LEARNED_MATRIX.exists() else OUTCOME_LOG if selector_mode == "learned" else "built_in_rules"),
        "scenarios": scenario_reports,
        "failures": failures,
    }


def maybe_probe_hermes(base_url: str, plan: dict) -> dict:
    health = get_json(f"{base_url.rstrip('/')}/health")
    taught = post_json(
        f"{base_url.rstrip('/')}/teach",
        {
            "text": "Hermes CLC selector smoke: CSD detects drift, CLC chooses policy, and G-CL protects geometry.",
            "namespace": "agent:hermes",
            "agent_id": "hermes",
            "source": "hermes_clc_selector_smoke",
            "memory_type": "design_rule",
            "domain": "agent_memory",
            "metadata": {"selector_plan": plan["selector"]},
        },
    )
    return {"health": health, "teach": taught}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and optionally probe a Hermes CLC selector test plan.")
    parser.add_argument("--base-url", default="", help="Optional running Hermes memory-core base URL, e.g. http://127.0.0.1:8765")
    parser.add_argument("--selector-mode", choices=["current", "learned"], default="current")
    args = parser.parse_args()

    plan = build_plan(args.selector_mode)
    suffix = "" if args.selector_mode == "current" else f"_{args.selector_mode}"
    output = REPO_ROOT / "experiments" / f"hermes_clc_selector{suffix}_test_plan.json"
    output.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    result = {"plan_path": str(output), **plan}
    if args.base_url:
        result["hermes_probe"] = maybe_probe_hermes(args.base_url, plan)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
