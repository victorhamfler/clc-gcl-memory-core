from __future__ import annotations

import http.client
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.clc_policy_selector import POLICY_LONG_SEVERE, POLICY_PERIODIC  # noqa: E402
from hermes_hard_stale_escalation_v2 import selector_features  # noqa: E402
from selector_retrieval_feature_eval import STALE_CONTEXT  # noqa: E402


PORT = 8777
BASE_URL = f"http://127.0.0.1:{PORT}"
OUT_JSON = REPO_ROOT / "experiments" / "selector_explain_endpoint_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "selector_explain_endpoint_eval_report.md"
SERVER_STDOUT = REPO_ROOT / "experiments" / "selector_explain_endpoint_eval_server.out"
SERVER_STDERR = REPO_ROOT / "experiments" / "selector_explain_endpoint_eval_server.err"


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 10) -> dict[str, Any]:
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    try:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        conn.request(method, parsed.path or "/", body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        if resp.status >= 400:
            raise RuntimeError(f"{method} {url} failed with HTTP {resp.status}: {raw}")
        return json.loads(raw)
    finally:
        conn.close()


def wait_for_server() -> None:
    deadline = time.time() + 30
    last_error = ""
    while time.time() < deadline:
        try:
            health = request_json("GET", f"{BASE_URL}/health", timeout=3)
            if health.get("ok"):
                return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"server did not become healthy: {last_error}")


def explain(payload: dict[str, Any]) -> dict[str, Any]:
    return request_json("POST", f"{BASE_URL}/selector_explain", payload)


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Selector Explain Endpoint Eval",
        "",
        f"Overall status: **{'PASS' if report['ok'] else 'FAIL'}**",
        "",
        f"Server URL: `{BASE_URL}`",
        "",
        "## Boundary Explanation",
        "",
        f"- Policy: `{report['boundary']['explanation']['decision']['policy']}`",
        f"- Confidence: `{report['boundary']['explanation']['decision']['confidence']}`",
        f"- Sample count: `{report['boundary']['explanation']['sample_count']}`",
        f"- Nearest samples returned: `{len(report['boundary']['explanation']['nearest_samples'])}`",
        "",
        "## Boundary Votes",
        "",
        "| Policy | Vote |",
        "|---|---:|",
    ]
    for policy, vote in report["boundary"]["explanation"]["votes"].items():
        lines.append(f"| `{policy}` | {vote} |")
    lines.extend(
        ["", "## Nearest Samples", "", "| Source | Policy | Distance | Vote | Counted |", "|---|---|---:|---:|---|"]
    )
    for row in report["boundary"]["explanation"]["nearest_samples"][:5]:
        lines.append(
            f"| `{row['source']}` | `{row['policy']}` | {row['distance']} | {row['vote']} | `{row['vote_counted']}` |"
        )
    lines.extend(["", "## Guard Explanation", ""])
    guard = report["high_label_cost_guard"]["explanation"]
    lines.append(f"- Policy: `{guard['decision']['policy']}`")
    lines.append(f"- Reason: `{guard['decision']['reason']}`")
    lines.extend(["", "## Failures", ""])
    if report["failures"]:
        lines.extend(f"- {failure}" for failure in report["failures"])
    else:
        lines.append("- None")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    stdout = SERVER_STDOUT.open("w", encoding="utf-8")
    stderr = SERVER_STDERR.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "serve.py"), "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(REPO_ROOT),
        stdout=stdout,
        stderr=stderr,
    )
    try:
        wait_for_server()
        boundary_payload = selector_features(3, "adversarial", "same_domain", "stale_biased")
        boundary_payload["top_k"] = 5
        boundary = explain(boundary_payload)
        retrieval_boundary = explain(
            {"condition_name": "hard_budget144", "retrieval_context": STALE_CONTEXT, "top_k": 5}
        )
        guard = explain({"condition_name": "hard_budget144", "label_cost": 0.0004, "top_k": 5})
        failures = []
        boundary_exp = boundary.get("explanation", {})
        guard_exp = guard.get("explanation", {})
        if boundary_exp.get("decision", {}).get("policy") != POLICY_LONG_SEVERE:
            failures.append(f"boundary explanation expected {POLICY_LONG_SEVERE}")
        if int(boundary_exp.get("sample_count") or 0) < 34:
            failures.append(f"boundary explanation should load at least 34 samples, got {boundary_exp.get('sample_count')}")
        if len(boundary_exp.get("nearest_samples") or []) < 5:
            failures.append("boundary explanation should return at least 5 nearest samples")
        if sum(1 for row in boundary_exp.get("nearest_samples") or [] if row.get("vote_counted")) != 3:
            failures.append("boundary explanation should mark exactly k=3 counted neighbors")
        if float(boundary_exp.get("votes", {}).get(POLICY_LONG_SEVERE) or 0.0) <= float(
            boundary_exp.get("votes", {}).get(POLICY_PERIODIC) or 0.0
        ):
            failures.append("boundary long-severe vote should beat periodic vote")
        if guard_exp.get("decision", {}).get("policy") != POLICY_PERIODIC:
            failures.append("high label cost guard should explain periodic decision")
        if "label_cost" not in str(guard_exp.get("decision", {}).get("reason") or ""):
            failures.append("high label cost guard explanation should identify label cost")
        retrieval_exp = retrieval_boundary.get("explanation", {})
        retrieval_context = retrieval_boundary.get("selector_context", {}).get("diagnostics", {})
        if retrieval_exp.get("decision", {}).get("policy") != POLICY_LONG_SEVERE:
            failures.append("retrieval-context explanation should select long severe")
        if retrieval_context.get("stale_ratio", 0.0) < 0.5:
            failures.append("retrieval-context explanation should expose stale ratio")
        report = {
            "ok": not failures,
            "base_url": BASE_URL,
            "boundary": boundary,
            "retrieval_boundary": retrieval_boundary,
            "high_label_cost_guard": guard,
            "failures": failures,
            "server_stdout": str(SERVER_STDOUT),
            "server_stderr": str(SERVER_STDERR),
        }
        OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
        write_markdown(report)
        print(json.dumps({"ok": report["ok"], "failures": failures, "report": str(OUT_JSON)}, indent=2), flush=True)
        return 0 if report["ok"] else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        stdout.close()
        stderr.close()


if __name__ == "__main__":
    raise SystemExit(main())
