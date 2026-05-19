from __future__ import annotations

import argparse
import http.client
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import (  # noqa: E402
    CLCPolicySelector,
    POLICY_LONG_SEVERE,
    POLICY_PERIODIC,
    POLICY_XSEQ_MEMORY,
)
from core.config import load_config  # noqa: E402
from core.selector_runtime import build_policy_selector, selector_features_for_condition  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "hermes_hard_stale_escalation_v2_results.json"
OUT_MD = REPO_ROOT / "experiments" / "hermes_hard_stale_escalation_v2_report.md"
OUT_JSONL = REPO_ROOT / "experiments" / "hermes_clc_selector_outcome_labels.jsonl"

AGENT_ID = "hermes_escalation_v2"
CURRENT_TERMS = ["espresso", "green tea"]
POLICY_COST = {
    POLICY_PERIODIC: 0.0,
    POLICY_LONG_SEVERE: 0.015,
    POLICY_XSEQ_MEMORY: 0.025,
}
POLICY_ACTION = {
    POLICY_PERIODIC: "PROTECT_PERIODIC",
    POLICY_LONG_SEVERE: "LONG_SEVERE_VERIFIED_REFRESH",
    POLICY_XSEQ_MEMORY: "XSEQ_MEMORY_REFRESH",
}
FORCED_MODES = {
    "periodic_baseline": POLICY_PERIODIC,
    "long_severe": POLICY_LONG_SEVERE,
    "xseq_memory": POLICY_XSEQ_MEMORY,
}


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        resp_body = resp.read().decode("utf-8")
        if resp.status >= 400:
            raise RuntimeError(f"{method} {url} failed with HTTP {resp.status}: {resp_body}")
        return json.loads(resp_body)
    finally:
        conn.close()


def get_json(url: str) -> dict[str, Any]:
    return request_json("GET", url, timeout=15)


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    return request_json("POST", url, payload, timeout=60)


def has_all(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return all(term in low for term in terms)


def has_any(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(term in low for term in terms)


def stale_variants(stale_count: int, similarity: str) -> list[str]:
    high = [
        "Victor used to like espresso, but he stopped drinking espresso and no longer drinks green tea.",
        "Victor's current drink preference is water, not espresso, and he avoids green tea.",
        "Victor replaced espresso with decaf and stopped drinking green tea in the afternoon.",
        "Victor previously liked espresso and green tea, but the latest note says he avoids both.",
        "Victor does not drink espresso anymore and says green tea should be removed from his preferences.",
        "Victor's drink preference changed away from espresso; he now rejects green tea.",
        "Victor used to drink espresso in the morning, but now he drinks water instead of espresso.",
        "Victor no longer wants green tea in the afternoon and does not want espresso in the morning.",
        "Victor's updated beverage rule says not espresso and not green tea.",
        "Victor considers espresso and green tea old preferences that should not be used.",
        "Victor's profile says espresso is stale and green tea is stale.",
        "Victor stopped ordering espresso and green tea after changing his drink routine.",
        "Victor's latest stale note says he avoids espresso and avoids green tea.",
    ]
    adversarial = [
        "Victor current preference: Victor likes espresso in the morning but stopped; current drink is water, not green tea.",
        "Victor current preference correction: espresso and green tea are outdated; use water and decaf instead.",
        "Victor likes espresso in the morning and green tea in the afternoon is false; Victor avoids both now.",
        "Current Victor drink preference: no espresso in the morning, no green tea in the afternoon.",
        "Victor current drink preference says espresso was previous and green tea was previous; neither is current.",
        "Victor current preference: replace espresso with water and replace green tea with mint infusion.",
        "Victor likes espresso and green tea only as historical preferences, not current preferences.",
        "Victor's current memory should say he stopped espresso and stopped green tea.",
        "Victor current preference changed: espresso is wrong, green tea is wrong, water is right.",
        "Victor current beverage update: do not answer espresso or green tea.",
        "Victor current preference is water in the morning and water in the afternoon, not espresso or green tea.",
        "Victor current profile: espresso and green tea are stale memories.",
        "Victor current drink preference excludes espresso and excludes green tea.",
    ]
    ambiguous = [
        "Victor has conflicting notes about espresso and green tea; some say these are no longer current.",
        "Victor drink notes mention espresso, green tea, water, and decaf with unclear current status.",
        "Victor beverage profile is disputed: espresso and green tea may be old preferences.",
        "Victor's drink preference has changed several times around espresso and green tea.",
        "Victor's current and historical drink memories disagree about espresso and green tea.",
    ]
    pools = {"high": high, "adversarial": adversarial, "ambiguous": ambiguous}
    pool = pools.get(similarity, high)
    return [pool[i % len(pool)] for i in range(stale_count)]


def query_for(specificity: str) -> str:
    queries = {
        "exact": "What is Victor's current drink preference?",
        "paraphrase": "What does Victor prefer to drink nowadays?",
        "ambiguous": "What about Victor and drinks?",
        "stale_biased": "Did Victor stop drinking espresso and green tea, or are those still current?",
    }
    return queries.get(specificity, queries["exact"])


def selector_features(stale_count: int, similarity: str, domain_noise: str, query_specificity: str) -> dict[str, Any]:
    similarity_boost = {"high": 0.12, "adversarial": 0.22, "ambiguous": 0.16}.get(similarity, 0.12)
    query_boost = {"exact": 0.0, "paraphrase": 0.05, "ambiguous": 0.12, "stale_biased": 0.18}.get(query_specificity, 0.0)
    domain_boost = {"none": 0.0, "same_domain": 0.08, "cross_domain": 0.04}.get(domain_noise, 0.0)
    return {
        "condition_name": "hard_budget144",
        "memory_bad_rate": min(0.98, 0.24 + stale_count * 0.055 + similarity_boost + query_boost),
        "probe_drop": min(0.98, 0.08 + stale_count * 0.028 + query_boost),
        "csd_ratio": min(3.5, 0.9 + stale_count * 0.1 + similarity_boost + domain_boost),
        "label_cost": 0.0002,
        "budget_pressure": 0.2,
    }


def decide_policy(policy_mode: str, stale_count: int, similarity: str, domain_noise: str, query_specificity: str) -> tuple[str, str, str, float]:
    if policy_mode in FORCED_MODES:
        policy = FORCED_MODES[policy_mode]
        return policy, POLICY_ACTION[policy], f"forced_{policy_mode}", 1.0
    features = selector_features(stale_count, similarity, domain_noise, query_specificity)
    if policy_mode == "current_selector":
        decision = CLCPolicySelector().select(features)
    elif policy_mode == "learned_selector":
        decision = build_policy_selector(ROOT, load_config(ROOT)).select(features)
    else:
        raise ValueError(f"unknown policy mode: {policy_mode}")
    return decision.policy, decision.action, decision.reason, float(decision.confidence)


def teach_memory(base_url: str, namespace: str, text: str, domain: str, memory_type: str) -> dict[str, Any]:
    return post_json(
        f"{base_url}/teach",
        {
            "text": text,
            "namespace": namespace,
            "agent_id": AGENT_ID,
            "store_session": False,
            "domain": domain,
            "memory_type": memory_type,
        },
    )


def current_update_text(current_style: str) -> str:
    if current_style == "terse":
        return "Espresso in the morning. Green tea in the afternoon."
    if current_style == "implicit":
        return "Morning espresso; afternoon green tea."
    return "Victor current preference: Victor likes espresso in the morning and green tea in the afternoon."


def apply_current_update(base_url: str, namespace: str, selected_policy: str, stale_ids: list[str], current_style: str) -> dict[str, Any]:
    current_text = current_update_text(current_style)
    if selected_policy == POLICY_PERIODIC:
        return teach_memory(base_url, namespace, current_text, "agent_memory", "preference")
    targets = stale_ids if selected_policy == POLICY_XSEQ_MEMORY else stale_ids[:1]
    return post_json(
        f"{base_url}/correct",
        {
            "correction": current_text,
            "target_memory_ids": targets,
            "target_query": "Victor current drink preference espresso green tea",
            "namespace": namespace,
            "agent_id": AGENT_ID,
            "store_session": False,
            "domain": "agent_memory",
            "memory_type": "preference",
            "force_clc_state": "FOCUS",
        },
    )


def score_answer(asked: dict[str, Any]) -> tuple[bool, bool, dict[str, Any]]:
    answer = str(asked.get("answer") or "").lower()
    current_present = has_all(answer, CURRENT_TERMS)
    correction_preferred = "current/corrected evidence should be preferred" in answer
    stale_phrases = [
        "stopped drinking espresso",
        "but stopped",
        "no longer drinks green tea",
        "water, not espresso",
        "water, not green tea",
        "not espresso",
        "not green tea",
        "outdated",
        "is false",
        "avoids both",
        "do not answer espresso",
        "old preferences",
        "stale memories",
        "neither is current",
    ]
    stale_in_answer = has_any(answer, stale_phrases)
    stale_dominated = stale_in_answer and not correction_preferred
    passed = current_present and not stale_dominated
    return passed, stale_dominated, {
        "current_present": current_present,
        "correction_preferred": correction_preferred,
        "stale_in_answer": stale_in_answer,
    }


def run_case(
    base_url: str,
    run_id: str,
    stale_count: int,
    similarity: str,
    domain_noise: str,
    query_specificity: str,
    current_style: str,
    policy_mode: str,
    embedding: dict[str, Any],
) -> dict[str, Any]:
    namespace = f"agent:escalation_v2:{run_id}:{stale_count}:{similarity}:{domain_noise}:{query_specificity}:{current_style}:{policy_mode}"
    teach_memory(
        base_url,
        namespace,
        "Victor baseline profile: Victor likes coffee and tea, but this old note may be incomplete.",
        "agent_memory",
        "preference",
    )
    stale_ids = []
    for stale_text in stale_variants(stale_count, similarity):
        domain = "agent_memory" if domain_noise in {"none", "same_domain"} else "food_drink"
        stale = teach_memory(base_url, namespace, stale_text, domain, "preference")
        stale_ids.append(str(stale.get("memory", {}).get("memory_id") or ""))
    if domain_noise == "same_domain":
        for noise_text in [
            "Victor weather memory: use AccuWeather for radar checks.",
            "Hermes project memory: Cedar Map uses selector outcome logs.",
        ]:
            teach_memory(base_url, namespace, noise_text, "agent_memory", "semantic_note")
    elif domain_noise == "cross_domain":
        for noise_text in [
            "Food memory: mushroom pizza is preferred for dinner.",
            "Project memory: Cedar Map uses selector outcome logs.",
        ]:
            teach_memory(base_url, namespace, noise_text, "food_drink", "semantic_note")

    selected_policy, selected_action, selector_reason, selector_confidence = decide_policy(
        policy_mode, stale_count, similarity, domain_noise, query_specificity
    )
    update = apply_current_update(base_url, namespace, selected_policy, stale_ids, current_style)
    asked = post_json(
        f"{base_url}/ask",
        {
            "query": query_for(query_specificity),
            "namespace": namespace,
            "include_global": False,
            "top_k": min(20, max(8, stale_count + 4)),
            "store_session": False,
            "agent_id": AGENT_ID,
        },
    )
    passed, stale_dominated, score_metrics = score_answer(asked)
    evidence = asked.get("evidence") or []
    return {
        "scenario_key": f"s{stale_count}_{similarity}_{domain_noise}_{query_specificity}_{current_style}",
        "scenario_id": f"escalation_v2_s{stale_count}_{similarity}_{domain_noise}_{query_specificity}_{current_style}_{policy_mode}",
        "stale_count": stale_count,
        "semantic_similarity": similarity,
        "domain_noise": domain_noise,
        "query_specificity": query_specificity,
        "current_style": current_style,
        "policy_mode": policy_mode,
        "selected_policy": selected_policy,
        "selected_action": selected_action,
        "selector_reason": selector_reason,
        "selector_confidence": selector_confidence,
        "answer_passed": passed,
        "stale_dominated": stale_dominated,
        "score_metrics": score_metrics,
        "policy_cost": POLICY_COST[selected_policy],
        "utility": round((1.0 if passed else 0.0) - POLICY_COST[selected_policy], 6),
        "selected_memory_ids": [str(item.get("memory_id") or "") for item in evidence if item.get("memory_id")],
        "evidence_states": [str(item.get("memory_state") or "") for item in evidence],
        "evidence_text": [str(item.get("text") or "") for item in evidence],
        "update_memory": update.get("memory") or update.get("correction_memory"),
        "answer": asked.get("answer"),
        "confidence": asked.get("confidence"),
        "conflict": asked.get("conflict"),
        "embedding_backend": embedding.get("backend"),
        "embedding_model": embedding.get("model_name"),
        "embedding_dim": embedding.get("embedding_dim"),
    }


def cheapest_passing_policy(rows: list[dict[str, Any]]) -> str | None:
    forced = [row for row in rows if row["policy_mode"] in FORCED_MODES and row["answer_passed"]]
    if not forced:
        return None
    return min(forced, key=lambda row: (POLICY_COST[row["selected_policy"]], row["selected_policy"]))["selected_policy"]


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, dict[str, Any]] = defaultdict(lambda: {"passed": 0, "total": 0, "stale_dominated": 0, "total_cost": 0.0, "oracle_matches": 0})
    for row in results:
        mode = row["policy_mode"]
        by_mode[mode]["total"] += 1
        by_mode[mode]["passed"] += 1 if row["answer_passed"] else 0
        by_mode[mode]["stale_dominated"] += 1 if row["stale_dominated"] else 0
        by_mode[mode]["total_cost"] += row["policy_cost"]
        by_mode[mode]["oracle_matches"] += 1 if row.get("oracle_policy") == row["selected_policy"] else 0
    summary = {}
    for mode, stats in by_mode.items():
        total = max(1, stats["total"])
        summary[mode] = {
            "pass_rate": round(stats["passed"] / total, 6),
            "stale_domination_rate": round(stats["stale_dominated"] / total, 6),
            "total_cost": round(stats["total_cost"], 6),
            "utility": round(stats["passed"] - stats["total_cost"], 6),
            "oracle_match_rate": round(stats["oracle_matches"] / total, 6),
            "total_runs": stats["total"],
        }
    return summary


def write_outcome_labels(run_id: str, results: list[dict[str, Any]]) -> None:
    with OUT_JSONL.open("a", encoding="utf-8") as f:
        for row in results:
            label = "oracle_match_passed" if row["answer_passed"] and row["selected_policy"] == row.get("oracle_policy") else "passed_non_oracle" if row["answer_passed"] else "failed"
            f.write(
                json.dumps(
                    {
                        "run_id": run_id,
                        "source": "hard_stale_escalation_v2",
                        "scenario_id": row["scenario_id"],
                        "stale_count": row["stale_count"],
                        "semantic_similarity": row["semantic_similarity"],
                        "domain_noise": row["domain_noise"],
                        "query_specificity": row["query_specificity"],
                        "current_style": row["current_style"],
                        "selected_policy": row["selected_policy"],
                        "selected_action": row["selected_action"],
                        "oracle_policy": row.get("oracle_policy"),
                        "outcome_label": label,
                        "stale_dominated": row["stale_dominated"],
                        "selector_passed": row["answer_passed"],
                        "selector_utility": row["utility"],
                        "embedding_backend": row.get("embedding_backend"),
                        "embedding_model": row.get("embedding_model"),
                        "embedding_dim": row.get("embedding_dim"),
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Hermes Hard Stale-Memory Escalation V2",
        "",
        f"Run ID: `{report['run_id']}`",
        f"Server: `{report['server']['base_url']}`",
        f"Embedding: {report['embedding'].get('backend')} / {report['embedding'].get('model_name')} ({report['embedding'].get('embedding_dim')}d)",
        "",
        "## Summary By Policy Mode",
        "",
        "| Mode | Pass rate | Stale domination | Total cost | Utility | Oracle match | Runs |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, stats in report["summary"].items():
        lines.append(
            f"| {mode} | {stats['pass_rate']} | {stats['stale_domination_rate']} | {stats['total_cost']} | {stats['utility']} | {stats['oracle_match_rate']} | {stats['total_runs']} |"
        )
    lines.extend(["", "## Boundary", ""])
    if report["boundary"]["periodic_failure"]:
        lines.append(f"- Periodic first failed at: `{report['boundary']['periodic_failure']}`")
    else:
        lines.append("- Periodic did not fail in this v2 run.")
    if report["boundary"]["refresh_needed"]:
        lines.append(f"- Refresh first became oracle at: `{report['boundary']['refresh_needed']}`")
    else:
        lines.append("- Refresh did not become oracle in this v2 run.")
    lines.extend(["", "## Notes", ""])
    lines.append("- Oracle policy is computed from the cheapest forced policy that passed for each scenario key.")
    lines.append("- Current selector is local `CLCPolicySelector`; learned selector is loaded from active config.")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def scenario_sort_key(key: str) -> tuple[int, str]:
    parts = key.split("_", 1)
    if parts and parts[0].startswith("s"):
        try:
            return int(parts[0][1:]), key
        except ValueError:
            pass
    return 999999, key


def main() -> int:
    parser = argparse.ArgumentParser(description="Hard stale-memory escalation v2 benchmark.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--stale-counts", default="1,2,3,5,8,13")
    parser.add_argument("--similarities", default="high,adversarial")
    parser.add_argument("--domain-noises", default="same_domain")
    parser.add_argument("--query-specificities", default="exact,stale_biased")
    parser.add_argument("--current-styles", default="explicit")
    parser.add_argument("--policy-modes", default="periodic_baseline,current_selector,learned_selector,xseq_memory,long_severe")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    health = get_json(f"{base_url}/health")
    if not health.get("ok"):
        raise RuntimeError(f"server is not healthy: {health}")
    embedding = health.get("embedding", {})
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stale_counts = [int(item.strip()) for item in args.stale_counts.split(",") if item.strip()]
    similarities = [item.strip() for item in args.similarities.split(",") if item.strip()]
    domain_noises = [item.strip() for item in args.domain_noises.split(",") if item.strip()]
    query_specificities = [item.strip() for item in args.query_specificities.split(",") if item.strip()]
    current_styles = [item.strip() for item in args.current_styles.split(",") if item.strip()]
    policy_modes = [item.strip() for item in args.policy_modes.split(",") if item.strip()]

    total = len(stale_counts) * len(similarities) * len(domain_noises) * len(query_specificities) * len(current_styles) * len(policy_modes)
    results: list[dict[str, Any]] = []
    done = 0
    for stale_count in stale_counts:
        for similarity in similarities:
            for domain_noise in domain_noises:
                for query_specificity in query_specificities:
                    for current_style in current_styles:
                        for policy_mode in policy_modes:
                            done += 1
                            print(
                                f"[{done}/{total}] stale={stale_count} sim={similarity} noise={domain_noise} query={query_specificity} current={current_style} mode={policy_mode}",
                                flush=True,
                            )
                            results.append(
                                run_case(
                                    base_url,
                                    run_id,
                                    stale_count,
                                    similarity,
                                    domain_noise,
                                    query_specificity,
                                    current_style,
                                    policy_mode,
                                    embedding,
                                )
                            )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[row["scenario_key"]].append(row)
    for rows in grouped.values():
        oracle = cheapest_passing_policy(rows)
        for row in rows:
            row["oracle_policy"] = oracle

    summary = summarize(results)
    periodic_failure = None
    refresh_needed = None
    for key in sorted(grouped, key=scenario_sort_key):
        rows = grouped[key]
        periodic = next((row for row in rows if row["policy_mode"] == "periodic_baseline"), None)
        oracle = rows[0].get("oracle_policy")
        if periodic_failure is None and periodic and not periodic["answer_passed"]:
            periodic_failure = key
        if refresh_needed is None and oracle in {POLICY_LONG_SEVERE, POLICY_XSEQ_MEMORY}:
            refresh_needed = key

    report = {
        "ok": True,
        "run_id": run_id,
        "server": {"base_url": base_url},
        "embedding": embedding,
        "total_scenarios": total,
        "completed": len(results),
        "failed": 0,
        "parameters": {
            "stale_counts": stale_counts,
            "similarities": similarities,
            "domain_noises": domain_noises,
            "query_specificities": query_specificities,
            "current_styles": current_styles,
            "policy_modes": policy_modes,
        },
        "summary": summary,
        "boundary": {"periodic_failure": periodic_failure, "refresh_needed": refresh_needed},
        "results": results,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    write_outcome_labels(run_id, results)
    print(
        json.dumps(
            {
                "ok": True,
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
                "outcome_labels": str(OUT_JSONL),
                "summary": summary,
                "boundary": report["boundary"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
