from __future__ import annotations

import argparse
import http.client
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.clc_policy_selector import (  # noqa: E402
    CLCLearnedPolicySelector,
    CLCPolicyFeatures,
    CLCPolicySelector,
    POLICY_LONG_SEVERE,
    POLICY_PERIODIC,
    POLICY_XSEQ_MEMORY,
)
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
PYTHON_EXE = REPO_ROOT / ".venv-torch" / "Scripts" / "python.exe"
SERVE_SCRIPT = ROOT / "serve.py"
OUT_JSON = REPO_ROOT / "experiments" / "hermes_clc_selector_ab_eval_live_results.json"
OUT_MD = REPO_ROOT / "experiments" / "hermes_clc_selector_ab_eval_live_report.md"
OUT_JSONL = REPO_ROOT / "experiments" / "hermes_clc_selector_outcome_labels.jsonl"
LEARNED_MATRIX = REPO_ROOT / "experiments" / "clc_policy_matrix_eval_live_results.json"

DEFAULT_PORT = 8772


def get_json(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=15)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status >= 400:
            raise RuntimeError(f"GET {url} failed with HTTP {resp.status}: {body}")
        return json.loads(body)
    finally:
        conn.close()


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    parsed = urlparse(url)
    body = json.dumps(payload).encode("utf-8")
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=60)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp_body = resp.read().decode("utf-8")
        if resp.status >= 400:
            raise RuntimeError(f"POST {url} failed with HTTP {resp.status}: {resp_body}")
        return json.loads(resp_body)
    finally:
        conn.close()


def start_server(db_path: Path, port: int) -> subprocess.Popen[Any]:
    out_file = db_path.with_suffix(".server.out")
    err_file = db_path.with_suffix(".server.err")
    proc = subprocess.Popen(
        [str(PYTHON_EXE), "-u", str(SERVE_SCRIPT), "--port", str(port), "--db-path", str(db_path)],
        cwd=str(ROOT),
        stdout=open(str(out_file), "w"),
        stderr=open(str(err_file), "w"),
    )
    health_url = f"http://127.0.0.1:{port}/health"
    for attempt in range(30):
        if proc.poll() is not None:
            raise RuntimeError(f"Server exited early with code {proc.returncode}")
        try:
            health = get_json(health_url)
            if health.get("ok"):
                return proc
        except Exception:
            pass
        time.sleep(1)
    proc.kill()
    raise RuntimeError("Server did not become ready within 30 seconds")


def stop_server(proc: subprocess.Popen[Any]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait()


def text_blob(result: dict[str, Any]) -> str:
    parts = [str(result.get("answer") or "")]
    for key in ("evidence", "current", "stale", "disputed", "historical"):
        for item in result.get(key) or []:
            parts.append(str(item.get("text") or ""))
    return " ".join(parts).lower()


def evidence_states(result: dict[str, Any]) -> list[str]:
    return [str(item.get("memory_state") or "") for item in result.get("evidence") or []]


def evidence_ids(result: dict[str, Any]) -> list[str]:
    return [
        str(item.get("memory_id") or "")
        for item in result.get("evidence") or []
        if item.get("memory_id")
    ]


def ask_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": result.get("answer"),
        "confidence": result.get("confidence"),
        "conflict": result.get("conflict"),
        "evidence_states": evidence_states(result),
        "evidence_ids": evidence_ids(result),
        "evidence_text": [item.get("text") for item in result.get("evidence") or []],
        "stale_count": len(result.get("stale") or []),
        "current_count": len(result.get("current") or []),
        "disputed_count": len(result.get("disputed") or []),
    }


def has_any(blob: str, terms: list[str]) -> bool:
    return any(term.lower() in blob for term in terms)


def has_all(blob: str, terms: list[str]) -> bool:
    return all(term.lower() in blob for term in terms)


def score_preference_current(result: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    blob = text_blob(result)
    has_current = has_any(blob, ["espresso", "green tea"])
    stale_dominates = has_any(
        str(result.get("answer") or "").lower(), ["hates all forms", "never drinks"]
    )
    return has_current and not stale_dominates, {
        "has_current": has_current,
        "stale_dominates": stale_dominates,
    }


def score_project_update(result: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    blob = text_blob(result)
    has_current = has_all(blob, ["cedar map", "selector"])
    stale_only = (
        "without selector" in str(result.get("answer") or "").lower()
        and "selector" not in blob
    )
    return has_current and not stale_only, {
        "has_current": has_current,
        "stale_only": stale_only,
    }


def score_topic_isolation(result: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    answer = str(result.get("answer") or "").lower()
    mentions_target = "accuweather" in answer
    contamination = any(term in answer for term in ["pizza", "espresso", "cedar map"])
    return mentions_target and not contamination, {
        "mentions_target": mentions_target,
        "contamination": contamination,
    }


def score_session_boundary(
    first: dict[str, Any], second: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    first_answer = str(first.get("answer") or "").lower()
    second_answer = str(second.get("answer") or "").lower()
    first_ok = "source clarity" in first_answer or "transparency" in first_answer
    second_ok = (
        "g-cl" in second_answer
        or "domain geometry" in second_answer
        or "anchor" in second_answer
    )
    leak = "source clarity" in second_answer and not second_ok
    return first_ok and second_ok and not leak, {
        "first_ok": first_ok,
        "second_ok": second_ok,
        "topic_leak": leak,
    }


def output_paths(selector_mode: str) -> tuple[Path, Path]:
    if selector_mode == "current":
        return OUT_JSON, OUT_MD
    return (
        REPO_ROOT / "experiments" / f"hermes_clc_{selector_mode}_selector_ab_eval_live_results.json",
        REPO_ROOT / "experiments" / f"hermes_clc_{selector_mode}_selector_ab_eval_live_report.md",
    )


def build_selector(selector_mode: str) -> CLCPolicySelector | CLCLearnedPolicySelector:
    if selector_mode == "learned":
        if LEARNED_MATRIX.exists():
            return CLCLearnedPolicySelector.from_matrix_report(LEARNED_MATRIX, k=3)
        return CLCLearnedPolicySelector.from_outcome_log(OUT_JSONL, k=3)
    return CLCPolicySelector()


def selector_decision(condition_name: str, selector: CLCPolicySelector | CLCLearnedPolicySelector) -> dict[str, Any]:
    features_kwargs: dict[str, Any] = {}
    if condition_name == "hard_budget144":
        features_kwargs = {"memory_bad_rate": 0.75, "probe_drop": 0.18, "csd_ratio": 1.4}
    elif condition_name == "standard_budget144":
        features_kwargs = {"memory_bad_rate": 0.25, "probe_drop": 0.08, "csd_ratio": 0.9}
    elif condition_name == "long2_hard_budget288":
        features_kwargs = {"memory_bad_rate": 0.35, "probe_drop": 0.04, "csd_ratio": 0.7}
    elif condition_name == "long2_standard_budget288":
        features_kwargs = {"memory_bad_rate": 0.2, "probe_drop": 0.03, "csd_ratio": 0.6}
    decision = selector.select(CLCPolicyFeatures.from_condition_name(condition_name, **features_kwargs))
    return {
        "policy": decision.policy,
        "action": decision.action,
        "reason": decision.reason,
        "confidence": decision.confidence,
    }


def selector_update_payload(decision: dict[str, Any]) -> dict[str, Any]:
    if decision["policy"] == POLICY_PERIODIC:
        return {}
    if decision["policy"] in {POLICY_LONG_SEVERE, POLICY_XSEQ_MEMORY}:
        return {"force_clc_state": "FOCUS"}
    return {}


def scenario_short_hard(base_url: str, mode: str, ns: str, agent_id: str, decision: dict[str, Any] | None = None) -> dict[str, Any]:
    old = post_json(
        f"{base_url}/teach",
        {
            "text": "Victor likes coffee in the morning and tea in the afternoon.",
            "namespace": ns,
            "agent_id": agent_id,
            "store_session": False,
            "domain": "agent_memory",
            "memory_type": "preference",
        },
    )
    old_mem_id = old.get("memory", {}).get("memory_id")
    if mode == "selector":
        update_text = "Victor likes espresso in the morning and green tea in the afternoon."
        if decision and decision["policy"] == POLICY_PERIODIC:
            update = post_json(
                f"{base_url}/teach",
                {
                    "text": update_text,
                    "namespace": ns,
                    "agent_id": agent_id,
                    "store_session": False,
                    "domain": "agent_memory",
                    "memory_type": "preference",
                },
            )
        else:
            update = post_json(
                f"{base_url}/correct",
                {
                    "correction": update_text,
                    "target_memory_ids": [old_mem_id],
                    "target_query": "Victor drink preference",
                    "namespace": ns,
                    "agent_id": agent_id,
                    "store_session": False,
                    **selector_update_payload(decision or {"policy": POLICY_XSEQ_MEMORY}),
                    "domain": "agent_memory",
                    "memory_type": "preference",
                },
            )
    else:
        update = post_json(
            f"{base_url}/teach",
            {
                "text": "Victor hates all forms of tea and never drinks it.",
                "namespace": ns,
                "agent_id": agent_id,
                "store_session": False,
                "domain": "agent_memory",
                "memory_type": "preference",
            },
        )
    asked = post_json(
        f"{base_url}/ask",
        {
            "query": "What is Victor's current drink preference?",
            "namespace": ns,
            "include_global": False,
            "top_k": 5,
            "store_session": False,
            "agent_id": agent_id,
        },
    )
    passed, metrics = score_preference_current(asked)
    return {
        "passed": passed,
        "metrics": metrics,
        "writes": {"old": old.get("memory"), "update": update.get("memory") or update.get("correction_memory")},
        "ask": ask_summary(asked),
    }


def scenario_short_standard(base_url: str, mode: str, ns: str, agent_id: str, decision: dict[str, Any] | None = None) -> dict[str, Any]:
    old = post_json(
        f"{base_url}/teach",
        {
            "text": "Hermes project codename is Cedar Map without selector routing.",
            "namespace": ns,
            "agent_id": agent_id,
            "store_session": False,
            "domain": "agent_memory",
            "memory_type": "semantic_note",
        },
    )
    old_mem_id = old.get("memory", {}).get("memory_id")
    if mode == "selector":
        update_text = "Hermes project codename is Cedar Map with the CLC selector enabled."
        if decision and decision["policy"] == POLICY_PERIODIC:
            update = post_json(
                f"{base_url}/teach",
                {
                    "text": update_text,
                    "namespace": ns,
                    "agent_id": agent_id,
                    "store_session": False,
                    "domain": "agent_memory",
                    "memory_type": "semantic_note",
                },
            )
        else:
            update = post_json(
                f"{base_url}/correct",
                {
                    "correction": update_text,
                    "target_memory_ids": [old_mem_id],
                    "target_query": "Hermes project codename",
                    "namespace": ns,
                    "agent_id": agent_id,
                    "store_session": False,
                    **selector_update_payload(decision or {"policy": POLICY_LONG_SEVERE}),
                    "domain": "agent_memory",
                    "memory_type": "semantic_note",
                },
            )
    else:
        update = post_json(
            f"{base_url}/teach",
            {
                "text": "Hermes project codename is Cedar Map with the CLC selector enabled.",
                "namespace": ns,
                "agent_id": agent_id,
                "store_session": False,
                "domain": "agent_memory",
                "memory_type": "semantic_note",
            },
        )
    asked = post_json(
        f"{base_url}/ask",
        {
            "query": "What is the current Hermes project codename?",
            "namespace": ns,
            "include_global": False,
            "top_k": 5,
            "store_session": False,
            "agent_id": agent_id,
        },
    )
    passed, metrics = score_project_update(asked)
    return {
        "passed": passed,
        "metrics": metrics,
        "writes": {"old": old.get("memory"), "update": update.get("memory") or update.get("correction_memory")},
        "ask": ask_summary(asked),
    }


def scenario_long_hard(base_url: str, mode: str, ns: str, agent_id: str, decision: dict[str, Any] | None = None) -> dict[str, Any]:
    facts = [
        ("Victor pizza preference: he likes mushroom pizza.", "food_drink", "preference"),
        ("Weather radar method for Victor: use AccuWeather URL for radar checks.", "agent_memory", "procedure"),
        ("Hermes project codename is Cedar Map.", "agent_memory", "semantic_note"),
        ("Victor espresso preference: he likes espresso in the morning.", "food_drink", "preference"),
        ("Weather radar correction: AccuWeather remains preferred over visual radar canvas guessing.", "agent_memory", "procedure"),
    ]
    writes = []
    for text, domain, memory_type in facts:
        force_state = None
        if mode == "selector" and decision and decision["policy"] != POLICY_PERIODIC:
            force_state = "RECALL"
        writes.append(
            post_json(
                f"{base_url}/teach",
                {
                    "text": text,
                    "namespace": ns,
                    "agent_id": agent_id,
                    "store_session": False,
                    "domain": domain,
                    "memory_type": memory_type,
                    "force_clc_state": force_state,
                },
            ).get("memory")
        )
    asked = post_json(
        f"{base_url}/ask",
        {
            "query": "What weather radar method should Victor use?",
            "namespace": ns,
            "include_global": False,
            "top_k": 5,
            "store_session": False,
            "agent_id": agent_id,
        },
    )
    passed, metrics = score_topic_isolation(asked)
    return {"passed": passed, "metrics": metrics, "writes": writes, "ask": ask_summary(asked)}


def scenario_long_standard(base_url: str, mode: str, ns: str, agent_id: str, decision: dict[str, Any] | None = None) -> dict[str, Any]:
    force_state = None
    if mode == "selector" and decision and decision["policy"] != POLICY_PERIODIC:
        force_state = "RECALL"
    post_json(
        f"{base_url}/teach",
        {
            "text": "Victor values source clarity and transparency when information is presented.",
            "namespace": ns,
            "agent_id": agent_id,
            "store_session": False,
            "domain": "agent_memory",
            "memory_type": "preference",
            "force_clc_state": force_state,
        },
    )
    post_json(
        f"{base_url}/teach",
        {
            "text": "G-CL maintains domain geometry, anchor drift, curvature, and stability.",
            "namespace": ns,
            "agent_id": agent_id,
            "store_session": False,
            "domain": "G-CL",
            "memory_type": "semantic_note",
            "force_clc_state": force_state,
        },
    )
    first = post_json(
        f"{base_url}/ask",
        {
            "query": "What does Victor value when information is presented?",
            "namespace": ns,
            "include_global": False,
            "top_k": 5,
            "store_session": True,
            "agent_id": agent_id,
        },
    )
    session_id = first.get("session_id")
    second = post_json(
        f"{base_url}/ask",
        {
            "query": "What does G-CL maintain?",
            "namespace": ns,
            "include_global": False,
            "top_k": 5,
            "store_session": True,
            "agent_id": agent_id,
            "session_id": session_id,
        },
    )
    passed, metrics = score_session_boundary(first, second)
    return {
        "passed": passed,
        "metrics": metrics,
        "ask_first": ask_summary(first),
        "ask_second": ask_summary(second),
        "session_id": session_id,
    }


SCENARIOS = [
    {
        "id": "short_hard_preference_conflict",
        "condition_name": "hard_budget144",
        "runner": scenario_short_hard,
    },
    {
        "id": "short_standard_agent_fact_update",
        "condition_name": "standard_budget144",
        "runner": scenario_short_standard,
    },
    {
        "id": "long_hard_multi_topic_stream",
        "condition_name": "long2_hard_budget288",
        "runner": scenario_long_hard,
    },
    {
        "id": "long_standard_session_recall",
        "condition_name": "long2_standard_budget288",
        "runner": scenario_long_standard,
    },
]


def run_one(base_url: str, scenario: dict[str, Any], mode: str, selector_mode: str, decision: dict[str, Any] | None = None) -> dict[str, Any]:
    ns = f"agent:hermes_ab_eval_{selector_mode}_{mode}_{scenario['id']}"
    agent_id = f"hermes_{selector_mode}_{mode}_{scenario['id']}"
    result = scenario["runner"](base_url, mode, ns, agent_id, decision)
    # Server stats endpoint is global, not namespace-scoped, so we skip per-run stats
    result["stats"] = {"note": "live-server mode; stats are global and not isolated per namespace"}
    return result


def compare_result(baseline: dict[str, Any], selector: dict[str, Any]) -> str:
    if selector["passed"] and not baseline["passed"]:
        return "helped"
    if baseline["passed"] and not selector["passed"]:
        return "hurt"
    if selector["passed"] and baseline["passed"]:
        return "both_passed"
    return "both_failed"


def write_markdown(report: dict[str, Any], embedding_info: dict[str, Any], out_md: Path) -> None:
    lines = [
        "# Hermes CLC Selector A/B Eval - Live Server",
        "",
        "This eval compares normal memory-core behavior against selector-advised memory operations",
        "running against the live HTTP server with real Gemma embeddings.",
        "",
        f"**Selector mode:** {report.get('selector_mode', 'current')}",
        "",
        f"Overall status: **{'PASS' if report['ok'] else 'FAIL'}**",
        "",
        f"**Embedding backend:** {embedding_info.get('backend', 'unknown')}",
        f"**Model:** {embedding_info.get('model_name', 'unknown')}",
        f"**Dimension:** {embedding_info.get('embedding_dim', 'unknown')}",
        "",
        "| Scenario | Policy | Baseline | Selector | Outcome |",
        "|---|---|---:|---:|---|",
    ]
    for row in report["scenarios"]:
        lines.append(
            "| {id} | {policy} | {baseline} | {selector} | {outcome} |".format(
                id=row["id"],
                policy=row["selector_decision"]["policy"],
                baseline="PASS" if row["baseline"]["passed"] else "FAIL",
                selector="PASS" if row["selector"]["passed"] else "FAIL",
                outcome=row["comparison"],
            )
        )
    lines.extend(["", "## Notes", ""])
    lines.append("- Live server test uses namespace isolation to separate baseline and selector runs.")
    lines.append("- The `/correct` endpoint now preserves `domain` and `memory_type` when supplied.")
    lines.append("- Selector-advised mode maps policies into concrete memory operations:")
    lines.append("  - `XSEQ_MEMORY_REFRESH`: use correction workflow for hard contradictions.")
    lines.append("  - `LONG_SEVERE_VERIFIED_REFRESH`: use correction/FOCUS workflow for compatible updates.")
    lines.append("  - `PROTECT_PERIODIC`: keep normal periodic/protect memory behavior.")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outcome_labels(report: dict[str, Any]) -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = []
    for row in report["scenarios"]:
        lines.append(
            json.dumps(
                {
                    "run_id": run_id,
                    "source": "live_gemma_ab_eval",
                    "selector_mode": report.get("selector_mode", "current"),
                    "scenario_id": row["id"],
                    "condition_name": row["condition_name"],
                    "selected_policy": row["selector_decision"]["policy"],
                    "selected_action": row["selector_decision"]["action"],
                    "outcome_label": row["comparison"],
                    "baseline_passed": bool(row["baseline"]["passed"]),
                    "selector_passed": bool(row["selector"]["passed"]),
                    "selector_confidence": float(row["selector_decision"]["confidence"]),
                    "embedding_backend": report.get("embedding", {}).get("backend"),
                    "embedding_model": report.get("embedding", {}).get("model_name"),
                    "embedding_dim": report.get("embedding", {}).get("embedding_dim"),
                },
                sort_keys=True,
            )
        )
    with OUT_JSONL.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B outcome eval for Hermes CLC selector against live server.")
    parser.add_argument("--base-url", default="", help="Optional running server base URL. If omitted, a fresh server is started.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port for fresh server (default: 8772)")
    parser.add_argument("--selector-mode", choices=["current", "learned"], default="current")
    args = parser.parse_args()
    out_json, out_md = output_paths(args.selector_mode)
    selector_model = build_selector(args.selector_mode)

    base_url = args.base_url
    proc = None
    db_path = None
    tmp_dir = None

    if not base_url:
        tmp_dir = Path(tempfile.mkdtemp(prefix="clc_ab_eval_"))
        db_path = tmp_dir / "ab_eval_live.db"
        db = MemoryDB(db_path)
        db.init_schema(SCHEMA_PATH)
        db.close()
        proc = start_server(db_path, args.port)
        base_url = f"http://127.0.0.1:{args.port}"
        print(f"Started fresh server at {base_url} with db {db_path}", flush=True)
    else:
        base_url = base_url.rstrip("/")
        health = get_json(f"{base_url}/health")
        if not health.get("ok"):
            raise RuntimeError("Provided server is not healthy")
        print(f"Using existing server at {base_url}", flush=True)

    try:
        health = get_json(f"{base_url}/health")
        embedding_info = health.get("embedding", {})

        scenarios = []
        for scenario in SCENARIOS:
            decision = selector_decision(scenario["condition_name"], selector_model)
            baseline = run_one(base_url, scenario, "baseline", args.selector_mode)
            selector = run_one(base_url, scenario, "selector", args.selector_mode, decision)
            scenarios.append(
                {
                    "id": scenario["id"],
                    "condition_name": scenario["condition_name"],
                    "selector_decision": decision,
                    "baseline": baseline,
                    "selector": selector,
                    "comparison": compare_result(baseline, selector),
                }
            )

        report = {
            "ok": all(row["selector"]["passed"] for row in scenarios),
            "purpose": "A/B outcome eval for Hermes CLC selector against live server with real Gemma embeddings",
            "selector_mode": args.selector_mode,
            "selector_source": str(LEARNED_MATRIX if args.selector_mode == "learned" and LEARNED_MATRIX.exists() else OUT_JSONL if args.selector_mode == "learned" else "CLCPolicySelector"),
            "server": {"base_url": base_url, "db_path": str(db_path) if db_path else None},
            "embedding": embedding_info,
            "scenarios": scenarios,
        }
        out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        write_markdown(report, embedding_info, out_md)
        write_outcome_labels(report)
        print(
            json.dumps(
                {
                    "ok": report["ok"],
                    "selector_mode": args.selector_mode,
                    "json": str(out_json),
                    "markdown": str(out_md),
                    "summary": [
                        {
                            "id": row["id"],
                            "baseline_passed": row["baseline"]["passed"],
                            "selector_passed": row["selector"]["passed"],
                            "comparison": row["comparison"],
                            "policy": row["selector_decision"]["policy"],
                        }
                        for row in scenarios
                    ],
                    "outcome_labels": str(OUT_JSONL),
                },
                indent=2,
            ),
            flush=True,
        )
    finally:
        if proc is not None:
            stop_server(proc)
            print("Server stopped.", flush=True)
            if tmp_dir and tmp_dir.exists():
                shutil.rmtree(str(tmp_dir), ignore_errors=True)
                print(f"Cleaned up temp dir {tmp_dir}", flush=True)

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
