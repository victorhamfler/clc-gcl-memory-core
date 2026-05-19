from __future__ import annotations

import argparse
import http.client
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
EVAL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(EVAL_ROOT))

from clc_policy_matrix_eval import (  # noqa: E402
    POLICIES,
    POLICY_ACTIONS,
    build_scenarios,
    oracle_policy,
    policy_utility,
    strategy_policy,
)


OUT_JSON = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_live_results.json"
OUT_MD = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_live_report.md"
OUT_JSONL = REPO_ROOT / "experiments" / "hermes_clc_selector_outcome_labels.jsonl"
AGENT_ID = "hermes_policy_matrix_live"


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


class HttpMemoryClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def teach(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return request_json("POST", f"{self.base_url}/teach", {"text": text, **kwargs})

    def correct(self, correction: str, **kwargs: Any) -> dict[str, Any]:
        return request_json("POST", f"{self.base_url}/correct", {"correction": correction, **kwargs})

    def ask(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return request_json("POST", f"{self.base_url}/ask", {"query": query, **kwargs})


def run_policy(base_url: str, run_id: str, scenario: Any, policy: str) -> dict[str, Any]:
    client = HttpMemoryClient(base_url)
    namespace = f"agent:policy_matrix_live:{run_id}:{scenario.scenario_id}:{policy}"
    result = scenario.runner(client, policy, namespace)
    return {
        **result,
        "utility": round(policy_utility(bool(result["passed"]), policy, scenario.features), 6),
        "stats": {"note": "live-server mode; namespace isolated, global stats skipped"},
    }


def summarize_strategies(rows: list[dict[str, Any]]) -> dict[str, Any]:
    strategies = [
        "periodic_only",
        "always_long_severe",
        "always_xseq_memory",
        "current_clc_selector",
        "learned_knn_selector",
    ]
    summary: dict[str, Any] = {}
    for strategy in strategies:
        total_utility = 0.0
        pass_count = 0
        oracle_matches = 0
        policy_counts: Counter[str] = Counter()
        for idx, row in enumerate(rows):
            train_rows = rows[:idx] + rows[idx + 1 :]
            policy = strategy_policy(strategy, row["scenario"], train_rows)
            policy_counts[policy] += 1
            result = row["policy_results"][policy]
            total_utility += float(result["utility"])
            pass_count += 1 if result["passed"] else 0
            oracle_matches += 1 if policy == row["oracle_policy"] else 0
        summary[strategy] = {
            "utility": round(total_utility, 6),
            "pass_rate": round(pass_count / len(rows), 6),
            "oracle_match_rate": round(oracle_matches / len(rows), 6),
            "policy_counts": dict(policy_counts),
        }
    return summary


def write_outcome_labels(report: dict[str, Any]) -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    embedding = report.get("embedding", {})
    with OUT_JSONL.open("a", encoding="utf-8") as f:
        for row in report["scenarios"]:
            chosen = row["strategies"]["current_clc_selector"]["policy"]
            result = row["policy_results"][chosen]
            if result["passed"] and chosen == row["oracle_policy"]:
                label = "oracle_match_passed"
            elif result["passed"]:
                label = "passed_non_oracle"
            else:
                label = "failed"
            f.write(
                json.dumps(
                    {
                        "run_id": run_id,
                        "source": "policy_matrix_live_gemma_eval",
                        "scenario_id": row["id"],
                        "family": row["family"],
                        "condition_name": row["condition_name"],
                        "selected_policy": chosen,
                        "selected_action": POLICY_ACTIONS[chosen],
                        "oracle_policy": row["oracle_policy"],
                        "outcome_label": label,
                        "selector_passed": bool(result["passed"]),
                        "selector_utility": float(result["utility"]),
                        "embedding_backend": embedding.get("backend"),
                        "embedding_model": embedding.get("model_name"),
                        "embedding_dim": embedding.get("embedding_dim"),
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# CLC Policy Matrix Eval - Live Gemma",
        "",
        "This experiment repeats the policy matrix against the live memory server with real embeddings.",
        "",
        f"Overall status: **{'PASS' if report['ok'] else 'REVIEW'}**",
        "",
        f"**Embedding backend:** {report.get('embedding', {}).get('backend', 'unknown')}",
        f"**Model:** {report.get('embedding', {}).get('model_name', 'unknown')}",
        f"**Dimension:** {report.get('embedding', {}).get('embedding_dim', 'unknown')}",
        "",
        "| Strategy | Utility | Pass rate | Oracle match | Policy counts |",
        "|---|---:|---:|---:|---|",
    ]
    for name, stats in report["strategy_summary"].items():
        lines.append(
            f"| {name} | {stats['utility']} | {stats['pass_rate']} | {stats['oracle_match_rate']} | {stats['policy_counts']} |"
        )
    lines.extend(["", "## Oracle Policies", "", "| Family | Scenario | Oracle | Current CLC | Outcome |", "|---|---|---|---|---|"])
    for row in report["scenarios"]:
        current = row["strategies"]["current_clc_selector"]
        lines.append(
            f"| {row['family']} | {row['id']} | {row['oracle_policy']} | {current['policy']} | {current['outcome']} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Gemma policy-matrix evaluation for CLC selector development.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8772")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    health = request_json("GET", f"{base_url}/health", timeout=15)
    if not health.get("ok"):
        raise RuntimeError(f"server is not healthy: {health}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rows: list[dict[str, Any]] = []
    for scenario in build_scenarios():
        policy_results = {policy: run_policy(base_url, run_id, scenario, policy) for policy in POLICIES}
        rows.append(
            {
                "scenario": scenario,
                "id": scenario.scenario_id,
                "family": scenario.family,
                "condition_name": scenario.condition_name,
                "features": scenario.features,
                "policy_results": policy_results,
                "oracle_policy": oracle_policy(policy_results),
            }
        )

    strategy_summary = summarize_strategies(rows)
    serialized_rows = []
    for idx, row in enumerate(rows):
        strategies = {}
        for strategy in strategy_summary:
            train_rows = rows[:idx] + rows[idx + 1 :]
            policy = strategy_policy(strategy, row["scenario"], train_rows)
            result = row["policy_results"][policy]
            strategies[strategy] = {
                "policy": policy,
                "passed": bool(result["passed"]),
                "utility": float(result["utility"]),
                "outcome": "oracle" if policy == row["oracle_policy"] else ("passed" if result["passed"] else "failed"),
            }
        serialized_rows.append(
            {
                "id": row["id"],
                "family": row["family"],
                "condition_name": row["condition_name"],
                "features": row["features"].__dict__,
                "oracle_policy": row["oracle_policy"],
                "policy_results": row["policy_results"],
                "strategies": strategies,
            }
        )

    report = {
        "ok": strategy_summary["current_clc_selector"]["pass_rate"] >= 0.95
        and strategy_summary["current_clc_selector"]["utility"] >= strategy_summary["periodic_only"]["utility"],
        "purpose": "Live Gemma policy-matrix evaluation for CSD/G-CL/CLC memory selector development",
        "server": {"base_url": base_url},
        "embedding": health.get("embedding", {}),
        "num_scenarios": len(serialized_rows),
        "policies": POLICIES,
        "strategy_summary": strategy_summary,
        "scenarios": serialized_rows,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    write_outcome_labels(report)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
                "outcome_labels": str(OUT_JSONL),
                "num_scenarios": report["num_scenarios"],
                "embedding": report["embedding"],
                "strategy_summary": strategy_summary,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
