from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import CLCPolicyFeatures, CLCPolicySelector  # noqa: E402
from core.selector_runtime import build_policy_selector, selector_features_for_condition  # noqa: E402
from core.config import load_config  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "hermes_hard_stale_escalation_results.json"
OUT_MD = REPO_ROOT / "experiments" / "hermes_hard_stale_escalation_report.md"
OUT_JSONL = REPO_ROOT / "experiments" / "hermes_clc_selector_outcome_labels.jsonl"

POLICY_COST = {
    "periodic_baseline": 0.0,
    "long_severe_r16_overwrite": 0.015,
    "xseq_memory_r45_badmajority": 0.025,
}


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def text_blob(result: dict[str, Any]) -> str:
    parts = [str(result.get("answer") or "")]
    for key in ("evidence", "current", "stale", "disputed", "historical"):
        for item in result.get(key) or []:
            parts.append(str(item.get("text") or ""))
    return " ".join(parts).lower()


def has_all(blob: str, terms: list[str]) -> bool:
    return all(term.lower() in blob for term in terms)


def has_any(blob: str, terms: list[str]) -> bool:
    return any(term.lower() in blob for term in terms)


CURRENT_TERMS = ["espresso", "green tea"]
STALE_TERMS = ["hates tea", "never drinks tea", "avoids espresso"]
QUESTION = "What is Victor's current drink preference?"


def stale_variants(stale_count: int, similarity: str) -> list[str]:
    base_facts = [
        "Victor only drinks water and avoids all caffeine.",
        "Victor hates coffee and refuses to drink it under any circumstances.",
        "Victor never consumes tea, especially not green tea.",
        "Victor's strict policy: no hot beverages in the morning.",
        "Victor is allergic to espresso and all dark-roasted coffee.",
        "Victor prefers herbal infusions and avoids all traditional tea.",
        "Victor gave up caffeine entirely last year.",
        "Victor believes coffee is unhealthy and avoids it completely.",
        "Victor only drinks cold beverages, never hot coffee or tea.",
        "Victor had a bad experience with espresso and swore it off forever.",
        "Victor's doctor recommended avoiding all caffeinated drinks.",
        "Victor thinks green tea tastes bitter and refuses to drink it.",
        "Victor switched to decaf only and avoids regular coffee.",
        "Victor prefers juice over any form of coffee or tea.",
        "Victor never developed a taste for espresso.",
        "Victor finds coffee too acidic for his stomach.",
        "Victor only drinks bottled water at work.",
        "Victor avoids tea shops and coffee houses entirely.",
        "Victor's morning routine excludes all caffeinated beverages.",
        "Victor considers espresso too strong and unpleasant.",
        "Victor prefers smoothies over traditional morning drinks.",
    ]
    paraphrases = {
        "low": [
            "Victor's beverage choices are limited to non-caffeinated options.",
            "When it comes to drinks, Victor stays away from anything with caffeine.",
            "Victor does not include coffee or tea in his diet.",
            "For Victor, caffeinated drinks are off the menu.",
            "Victor's drink repertoire excludes all forms of coffee and tea.",
        ],
        "medium": [
            "Victor avoids coffee and does not drink tea either.",
            "Victor does not drink coffee and stays away from tea.",
            "Victor has no interest in coffee or tea beverages.",
            "Neither coffee nor tea is part of Victor's routine.",
            "Victor skips both coffee and tea in favor of other drinks.",
        ],
        "high": [
            "Victor hates coffee and refuses to drink it under any circumstances.",
            "Victor never consumes tea, especially not green tea.",
            "Victor only drinks water and avoids all caffeine.",
            "Victor is allergic to espresso and all dark-roasted coffee.",
            "Victor gave up caffeine entirely last year.",
        ],
    }
    variants = []
    pool = paraphrases.get(similarity, base_facts)
    for i in range(stale_count):
        variants.append(pool[i % len(pool)])
    return variants


def run_escalation(
    base_url: str,
    stale_count: int,
    similarity: str,
    domain_noise: str,
    query_specificity: str,
    policy_mode: str,
    run_id: str,
) -> dict[str, Any]:
    ns = f"agent:escalation:{run_id}:{stale_count}:{similarity}:{domain_noise}:{query_specificity}:{policy_mode}"
    agent_id = "hermes_escalation"

    # Teach current fact
    current_fact = post_json(
        f"{base_url}/teach",
        {
            "text": "Victor current preference: Victor likes espresso in the morning and green tea in the afternoon.",
            "namespace": ns,
            "agent_id": agent_id,
            "store_session": False,
            "domain": "agent_memory",
            "memory_type": "preference",
        },
    )
    current_mem_id = current_fact.get("memory", {}).get("memory_id")

    # Teach stale contradictory memories
    stale_ids = []
    for stale_text in stale_variants(stale_count, similarity):
        stale = post_json(
            f"{base_url}/teach",
            {
                "text": stale_text,
                "namespace": ns,
                "agent_id": agent_id,
                "store_session": False,
                "domain": "agent_memory" if domain_noise in ("none", "same_domain") else "food_drink",
                "memory_type": "preference",
            },
        )
        stale_ids.append(stale.get("memory", {}).get("memory_id"))

    # Add cross-domain noise if requested
    if domain_noise == "cross_domain":
        for noise_text in [
            "Weather radar method: use AccuWeather for Victor's location.",
            "Hermes project codename is Cedar Map.",
        ]:
            post_json(
                f"{base_url}/teach",
                {
                    "text": noise_text,
                    "namespace": ns,
                    "agent_id": agent_id,
                    "store_session": False,
                    "domain": "agent_memory",
                    "memory_type": "semantic_note",
                },
            )

    # Get selector decision for selector modes
    selected_policy = policy_mode
    selected_action = {
        "periodic_baseline": "PROTECT_PERIODIC",
        "xseq_memory": "XSEQ_MEMORY_REFRESH",
        "long_severe": "LONG_SEVERE_VERIFIED_REFRESH",
    }.get(policy_mode, "PROTECT_PERIODIC")
    selector_reason = f"forced_{policy_mode}"

    if policy_mode in ("current_selector", "learned_selector"):
        selector_features = {
            "condition_name": "hard_budget144",
            "memory_bad_rate": min(0.95, 0.3 + stale_count * 0.05),
            "probe_drop": min(0.95, 0.1 + stale_count * 0.03),
            "csd_ratio": min(3.0, 1.0 + stale_count * 0.1),
            "label_cost": 0.0002,
            "budget_pressure": 0.2,
        }
        try:
            server_decision = post_json(
                f"{base_url}/selector_decide",
                selector_features,
            )
            selected_policy = server_decision.get("decision", {}).get("policy", "periodic_baseline")
            selected_action = server_decision.get("decision", {}).get("action", "PROTECT_PERIODIC")
            selector_reason = server_decision.get("decision", {}).get("reason", "unknown")
        except Exception:
            selected_policy = "periodic_baseline"
            selected_action = "PROTECT_PERIODIC"
            selector_reason = "server_decide_failed"

    # Apply correction based on selected policy
    if selected_policy in ("xseq_memory_r45_badmajority", "xseq_memory"):
        post_json(
            f"{base_url}/correct",
            {
                "correction": "Victor current preference: Victor likes espresso in the morning and green tea in the afternoon.",
                "target_memory_ids": stale_ids,
                "target_query": QUESTION,
                "namespace": ns,
                "agent_id": agent_id,
                "store_session": False,
            },
        )
    elif selected_policy in ("long_severe_r16_overwrite", "long_severe"):
        post_json(
            f"{base_url}/correct",
            {
                "correction": "Victor current preference: Victor likes espresso in the morning and green tea in the afternoon.",
                "target_memory_ids": stale_ids[:1] if stale_ids else [],
                "target_query": QUESTION,
                "namespace": ns,
                "agent_id": agent_id,
                "store_session": False,
            },
        )
    # periodic: no correction

    # Query
    queries = {
        "exact": QUESTION,
        "paraphrase": "What does Victor prefer to drink nowadays?",
        "ambiguous": "What about Victor and drinks?",
    }
    query = queries.get(query_specificity, QUESTION)

    asked = post_json(
        f"{base_url}/ask",
        {
            "query": query,
            "namespace": ns,
            "include_global": False,
            "top_k": min(5 + stale_count, 15),
            "store_session": False,
            "agent_id": agent_id,
        },
    )

    blob = text_blob(asked)
    stale_dominates = has_any(str(asked.get("answer") or "").lower(), STALE_TERMS)
    passed = has_all(blob, CURRENT_TERMS) and not stale_dominates

    evidence_states_list = [str(item.get("memory_state") or "") for item in asked.get("evidence") or []]
    evidence_ids_list = [str(item.get("memory_id") or "") for item in asked.get("evidence") or [] if item.get("memory_id")]

    return {
        "scenario_id": f"escalation_s{stale_count}_{similarity}_{domain_noise}_{query_specificity}_{policy_mode}",
        "stale_count": stale_count,
        "semantic_similarity": similarity,
        "domain_noise": domain_noise,
        "query_specificity": query_specificity,
        "policy_mode": policy_mode,
        "selected_policy": selected_policy,
        "selected_action": selected_action,
        "selector_reason": selector_reason,
        "answer_passed": passed,
        "stale_dominated": stale_dominates,
        "policy_cost": POLICY_COST.get(selected_policy, 0.0),
        "oracle_policy": "xseq_memory_r45_badmajority" if stale_count >= 3 else "periodic_baseline",
        "selected_memory_ids": evidence_ids_list,
        "evidence_states": evidence_states_list,
        "answer": asked.get("answer"),
        "confidence": asked.get("confidence"),
        "conflict": asked.get("conflict"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Hard stale-memory escalation benchmark for CLC selector.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--stale-counts", default="1,2,3,5,8,13", help="Comma-separated stale counts")
    parser.add_argument("--similarities", default="low,medium,high")
    parser.add_argument("--domain-noises", default="none,same_domain,cross_domain")
    parser.add_argument("--query-specificities", default="exact,paraphrase,ambiguous")
    parser.add_argument("--policy-modes", default="periodic_baseline,current_selector,learned_selector,xseq_memory,long_severe")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    health = get_json(f"{base_url}/health")
    if not health.get("ok"):
        raise RuntimeError("Server not healthy")

    embedding = health.get("embedding", {})
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    stale_counts = [int(x.strip()) for x in args.stale_counts.split(",")]
    similarities = [x.strip() for x in args.similarities.split(",")]
    domain_noises = [x.strip() for x in args.domain_noises.split(",")]
    query_specificities = [x.strip() for x in args.query_specificities.split(",")]
    policy_modes = [x.strip() for x in args.policy_modes.split(",")]

    results = []
    total = len(stale_counts) * len(similarities) * len(domain_noises) * len(query_specificities) * len(policy_modes)
    done = 0

    for stale_count in stale_counts:
        for similarity in similarities:
            for domain_noise in domain_noises:
                for query_specificity in query_specificities:
                    for policy_mode in policy_modes:
                        done += 1
                        print(f"[{done}/{total}] stale={stale_count} sim={similarity} noise={domain_noise} query={query_specificity} mode={policy_mode}", flush=True)
                        try:
                            row = run_escalation(
                                base_url, stale_count, similarity, domain_noise,
                                query_specificity, policy_mode, run_id
                            )
                            row["embedding_backend"] = embedding.get("backend")
                            row["embedding_model"] = embedding.get("model_name")
                            row["embedding_dim"] = embedding.get("embedding_dim")
                            results.append(row)
                        except Exception as e:
                            print(f"  FAILED: {e}", flush=True)
                            results.append({
                                "scenario_id": f"escalation_s{stale_count}_{similarity}_{domain_noise}_{query_specificity}_{policy_mode}",
                                "error": str(e),
                                "stale_count": stale_count,
                                "semantic_similarity": similarity,
                                "domain_noise": domain_noise,
                                "query_specificity": query_specificity,
                                "policy_mode": policy_mode,
                            })

    # Summary stats
    by_mode = {}
    for row in results:
        if "error" in row:
            continue
        mode = row["policy_mode"]
        if mode not in by_mode:
            by_mode[mode] = {"passed": 0, "total": 0, "stale_dominated": 0, "total_cost": 0.0}
        by_mode[mode]["total"] += 1
        if row["answer_passed"]:
            by_mode[mode]["passed"] += 1
        if row["stale_dominated"]:
            by_mode[mode]["stale_dominated"] += 1
        by_mode[mode]["total_cost"] += row["policy_cost"]

    summary = {}
    for mode, stats in by_mode.items():
        summary[mode] = {
            "pass_rate": round(stats["passed"] / max(1, stats["total"]), 4),
            "stale_domination_rate": round(stats["stale_dominated"] / max(1, stats["total"]), 4),
            "total_cost": round(stats["total_cost"], 4),
            "utility": round(stats["passed"] - stats["total_cost"], 4),
            "total_runs": stats["total"],
        }

    report = {
        "ok": True,
        "run_id": run_id,
        "server": {"base_url": base_url},
        "embedding": embedding,
        "total_scenarios": total,
        "completed": len([r for r in results if "error" not in r]),
        "failed": len([r for r in results if "error" in r]),
        "summary": summary,
        "results": results,
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Append outcome labels
    with OUT_JSONL.open("a", encoding="utf-8") as f:
        for row in results:
            if "error" in row:
                continue
            f.write(
                json.dumps(
                    {
                        "run_id": run_id,
                        "source": "hard_stale_escalation_benchmark",
                        "scenario_id": row["scenario_id"],
                        "stale_count": row["stale_count"],
                        "semantic_similarity": row["semantic_similarity"],
                        "domain_noise": row["domain_noise"],
                        "query_specificity": row["query_specificity"],
                        "selected_policy": row["selected_policy"],
                        "selected_action": row["selected_action"],
                        "outcome_label": "passed" if row["answer_passed"] else "failed",
                        "stale_dominated": row["stale_dominated"],
                        "selector_passed": row["answer_passed"],
                        "selector_utility": row["policy_cost"],
                        "embedding_backend": row.get("embedding_backend"),
                        "embedding_model": row.get("embedding_model"),
                        "embedding_dim": row.get("embedding_dim"),
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    # Markdown report
    lines = [
        "# Hermes Hard Stale-Memory Escalation Benchmark",
        "",
        f"Run ID: `{run_id}`",
        f"Server: `{base_url}`",
        f"Embedding: {embedding.get('backend')} / {embedding.get('model_name')} ({embedding.get('embedding_dim')}d)",
        "",
        "## Summary by Policy Mode",
        "",
        "| Mode | Pass rate | Stale domination | Total cost | Utility | Runs |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, stats in summary.items():
        lines.append(
            f"| {mode} | {stats['pass_rate']} | {stats['stale_domination_rate']} | {stats['total_cost']} | {stats['utility']} | {stats['total_runs']} |"
        )
    lines.extend(["", "## Key Findings", ""])

    # Find switching boundary
    periodic_by_stale = {}
    for row in results:
        if row.get("policy_mode") == "periodic_baseline" and "error" not in row:
            sc = row["stale_count"]
            if sc not in periodic_by_stale:
                periodic_by_stale[sc] = {"passed": 0, "total": 0}
            periodic_by_stale[sc]["total"] += 1
            if row["answer_passed"]:
                periodic_by_stale[sc]["passed"] += 1

    switch_boundary = None
    for sc in sorted(periodic_by_stale.keys()):
        rate = periodic_by_stale[sc]["passed"] / max(1, periodic_by_stale[sc]["total"])
        if rate < 0.8:
            switch_boundary = sc
            break

    if switch_boundary:
        lines.append(f"- **Switching boundary:** `periodic_baseline` fails at `{switch_boundary}` stale memories")
    else:
        lines.append("- **Switching boundary:** `periodic_baseline` remained sufficient across all tested stale counts")

    lines.append(f"- **Total scenarios:** {total}")
    lines.append(f"- **Completed:** {report['completed']}")
    lines.append(f"- **Failed:** {report['failed']}")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"ok": True, "json": str(OUT_JSON), "markdown": str(OUT_MD), "summary": summary}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
