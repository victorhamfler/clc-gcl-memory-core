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


PORT = 8776
BASE_URL = f"http://127.0.0.1:{PORT}"
OUT_JSON = REPO_ROOT / "experiments" / "guarded_continual_live_endpoint_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "guarded_continual_live_endpoint_eval_report.md"
SERVER_STDOUT = REPO_ROOT / "experiments" / "guarded_continual_live_endpoint_eval_server.out"
SERVER_STDERR = REPO_ROOT / "experiments" / "guarded_continual_live_endpoint_eval_server.err"


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


def decision(payload: dict[str, Any]) -> dict[str, Any]:
    return request_json("POST", f"{BASE_URL}/selector_decide", payload)


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Guarded Continual Live Endpoint Eval",
        "",
        f"Overall status: **{'PASS' if report['ok'] else 'FAIL'}**",
        "",
        f"Server URL: `{BASE_URL}`",
        "",
        "## Selector Config",
        "",
        f"- Matrix report: `{report['config_selector'].get('matrix_report')}`",
        f"- Sample count: `{report['config_selector'].get('sample_count')}`",
        "",
        "## Decisions",
        "",
        "| Case | Policy | Reason | Confidence |",
        "|---|---|---|---:|",
    ]
    for name, row in report["decisions"].items():
        dec = row["decision"]
        lines.append(f"| `{name}` | `{dec['policy']}` | `{dec['reason']}` | {dec['confidence']} |")
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
        config = request_json("GET", f"{BASE_URL}/config")
        boundary = selector_features(3, "adversarial", "same_domain", "stale_biased")
        decisions = {
            "hard_budget144": decision({"condition_name": "hard_budget144"}),
            "standard_budget144": decision({"condition_name": "standard_budget144"}),
            "long2_hard_budget288": decision({"condition_name": "long2_hard_budget288"}),
            "v2_stale_boundary": decision(boundary),
            "high_label_cost_guard": decision({"condition_name": "hard_budget144", "label_cost": 0.0004}),
        }
        selector = config.get("selector", {})
        failures = []
        if "clc_selector_guarded_continual_training_report.json" not in str(selector.get("matrix_report", "")):
            failures.append(f"live server loaded wrong report: {selector.get('matrix_report')}")
        if int(selector.get("sample_count") or 0) < 34:
            failures.append(f"live server should load at least 34 samples, got {selector.get('sample_count')}")
        expected = {
            "hard_budget144": POLICY_PERIODIC,
            "standard_budget144": POLICY_LONG_SEVERE,
            "long2_hard_budget288": POLICY_PERIODIC,
            "v2_stale_boundary": POLICY_LONG_SEVERE,
            "high_label_cost_guard": POLICY_PERIODIC,
        }
        for name, policy in expected.items():
            got = decisions[name]["decision"]["policy"]
            if got != policy:
                failures.append(f"{name} expected {policy}, got {got}")
        report = {
            "ok": not failures,
            "base_url": BASE_URL,
            "config_selector": selector,
            "decisions": decisions,
            "failures": failures,
            "server_stdout": str(SERVER_STDOUT),
            "server_stderr": str(SERVER_STDERR),
        }
        OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
        write_markdown(report)
        print(json.dumps(report, indent=2), flush=True)
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
