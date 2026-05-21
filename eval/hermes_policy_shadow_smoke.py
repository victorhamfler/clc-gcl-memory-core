from __future__ import annotations

import argparse
import http.client
import json
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


PORT = 8786
BASE_URL = f"http://127.0.0.1:{PORT}"
OUT_JSON = REPO_ROOT / "experiments" / "hermes_policy_shadow_smoke_results.json"
OUT_MD = REPO_ROOT / "experiments" / "hermes_policy_shadow_smoke_report.md"
SERVER_STDOUT = REPO_ROOT / "experiments" / "hermes_policy_shadow_smoke_server.out"
SERVER_STDERR = REPO_ROOT / "experiments" / "hermes_policy_shadow_smoke_server.err"


FIXTURES = {
    "github_upload_policy": {
        "text": "GitHub uploads require explicit confirmation in the current conversation.",
        "source": "shadow/github_upload_policy.md",
    },
    "github_upload_filename": {
        "text": "GitHub upload report filename should be github_upload_report.md.",
        "source": "shadow/github_upload_filename.md",
    },
    "calendar_change_policy": {
        "text": "Calendar schedule changes require manual approval before changing meeting events.",
        "source": "shadow/calendar_change_policy.md",
    },
    "broad_policy_note": {
        "text": "Broad policy note: approvals should be documented.",
        "source": "shadow/broad_policy_note.md",
    },
}


CASES = [
    {
        "id": "github_policy",
        "query": "What GitHub upload policy should Hermes follow?",
        "target": "github_upload_policy",
        "suppressed": ("github_upload_filename", "calendar_change_policy", "broad_policy_note"),
    },
    {
        "id": "github_uploading",
        "query": "What should happen before uploading to GitHub?",
        "target": "github_upload_policy",
        "suppressed": ("github_upload_filename", "calendar_change_policy", "broad_policy_note"),
    },
    {
        "id": "calendar_policy",
        "query": "What calendar change policy should Hermes follow?",
        "target": "calendar_change_policy",
        "suppressed": ("github_upload_policy", "github_upload_filename", "broad_policy_note"),
    },
    {
        "id": "calendar_events",
        "query": "What should happen before changing calendar events?",
        "target": "calendar_change_policy",
        "suppressed": ("github_upload_policy", "github_upload_filename", "broad_policy_note"),
    },
]


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
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
        raw = resp.read().decode("utf-8")
        if resp.status >= 400:
            raise RuntimeError(f"{method} {url} failed with HTTP {resp.status}: {raw}")
        return json.loads(raw)
    finally:
        conn.close()


def post_json(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return request_json("POST", f"{base_url.rstrip('/')}{path}", payload)


def wait_for_server(base_url: str) -> None:
    deadline = time.time() + 30
    last_error = ""
    while time.time() < deadline:
        try:
            health = request_json("GET", f"{base_url.rstrip('/')}/health", timeout=3)
            if health.get("ok"):
                return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"server did not become healthy: {last_error}")


def start_server(db_path: Path) -> tuple[subprocess.Popen, Any, Any]:
    SERVER_STDOUT.parent.mkdir(parents=True, exist_ok=True)
    stdout = SERVER_STDOUT.open("w", encoding="utf-8")
    stderr = SERVER_STDERR.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "serve.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--db-path",
            str(db_path),
        ],
        cwd=str(ROOT),
        stdout=stdout,
        stderr=stderr,
    )
    return proc, stdout, stderr


def teach_fixtures(base_url: str, namespace: str) -> dict[str, dict[str, Any]]:
    taught = {}
    for ref, fixture in FIXTURES.items():
        response = post_json(
            base_url,
            "/teach",
            {
                "text": fixture["text"],
                "source": fixture["source"],
                "namespace": namespace,
                "include_global": False,
                "agent_id": "hermes_policy_shadow_smoke",
                "store_session": False,
                "domain": "agent_memory",
                "memory_type": "procedure",
                "metadata": {"shadow_ref": ref},
            },
        )
        taught[ref] = response
    return taught


def row_ref(row: dict[str, Any]) -> str | None:
    source = str(row.get("source") or "")
    for ref, fixture in FIXTURES.items():
        if source == fixture["source"]:
            return ref
    text = str(row.get("text") or "")
    for ref, fixture in FIXTURES.items():
        if text == fixture["text"]:
            return ref
    return None


def rank_for(rows: list[dict[str, Any]], ref: str) -> int | None:
    for idx, row in enumerate(rows, start=1):
        if row_ref(row) == ref:
            return idx
    return None


def run_case(base_url: str, namespace: str, case: dict[str, Any]) -> dict[str, Any]:
    retrieved = post_json(
        base_url,
        "/retrieve",
        {
            "query": case["query"],
            "top_k": 8,
            "namespace": namespace,
            "include_global": False,
        },
    )
    rows = retrieved.get("results") or []
    target_rank = rank_for(rows, case["target"])
    target_row = next((row for row in rows if row_ref(row) == case["target"]), None)
    suppressed = []
    for ref in case["suppressed"]:
        row = next((item for item in rows if row_ref(item) == ref), None)
        suppressed.append(
            {
                "ref": ref,
                "rank": rank_for(rows, ref),
                "answer_type_score": None if row is None else row.get("answer_type_score"),
                "claim_scope_score": None if row is None else row.get("claim_scope_score"),
                "score": None if row is None else row.get("score"),
            }
        )
    asked = post_json(
        base_url,
        "/ask",
        {
            "query": case["query"],
            "top_k": 8,
            "namespace": namespace,
            "include_global": False,
            "agent_id": "hermes_policy_shadow_smoke",
            "store_session": False,
        },
    )
    evidence = asked.get("evidence") or []
    ask_top_ref = row_ref(evidence[0]) if evidence else None
    passed = target_rank == 1 and target_row is not None and float(target_row.get("answer_type_score") or 0.0) > 0.0
    if ask_top_ref != case["target"]:
        passed = False
    for item in suppressed:
        if item["rank"] is None or target_rank is None:
            passed = False
        elif item["rank"] <= target_rank:
            passed = False
        if item["answer_type_score"] is not None and float(item["answer_type_score"]) > 0.0:
            passed = False
    return {
        "id": case["id"],
        "query": case["query"],
        "passed": passed,
        "target": case["target"],
        "target_rank": target_rank,
        "target_answer_type_score": None if target_row is None else target_row.get("answer_type_score"),
        "ask_top_ref": ask_top_ref,
        "suppressed": suppressed,
        "retrieved": [
            {
                "rank": idx,
                "ref": row_ref(row),
                "score": row.get("score"),
                "claim_scope_score": row.get("claim_scope_score"),
                "answer_type_score": row.get("answer_type_score"),
                "source": row.get("source"),
                "text": row.get("text"),
            }
            for idx, row in enumerate(rows, start=1)
        ],
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Hermes Policy Shadow Smoke",
        "",
        f"Passed: **{report['ok']}**",
        f"Base URL: `{report['base_url']}`",
        f"Namespace: `{report['namespace']}`",
        f"Cases: `{len(report['cases'])}`",
        "",
        "| case | pass | target | target rank | answer-type | ask top | suppressed |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for case in report["cases"]:
        suppressed = ", ".join(
            f"{item['ref']} rank={item['rank']} answer={item['answer_type_score']}"
            for item in case["suppressed"]
        )
        lines.append(
            f"| `{case['id']}` | `{case['passed']}` | `{case['target']}` | {case['target_rank']} | "
            f"{case['target_answer_type_score']} | `{case['ask_top_ref']}` | {suppressed} |"
        )
    lines.extend(["", "## Details", ""])
    for case in report["cases"]:
        lines.extend(
            [
                f"### {case['id']}",
                "",
                f"Query: `{case['query']}`",
                "",
                "| rank | ref | score | claim-scope | answer-type | source | text |",
                "| ---: | --- | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for row in case["retrieved"]:
            text = str(row.get("text") or "").replace("|", "\\|")
            lines.append(
                f"| {row['rank']} | `{row['ref']}` | {row['score']} | {row['claim_scope_score']} | "
                f"{row['answer_type_score']} | `{row['source']}` | {text} |"
            )
        lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(base_url: str, namespace: str) -> dict[str, Any]:
    wait_for_server(base_url)
    taught = teach_fixtures(base_url, namespace)
    cases = [run_case(base_url, namespace, case) for case in CASES]
    report = {
        "ok": all(case["passed"] for case in cases),
        "base_url": base_url,
        "namespace": namespace,
        "taught_refs": sorted(taught),
        "cases": cases,
        "server_stdout": str(SERVER_STDOUT),
        "server_stderr": str(SERVER_STDERR),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Hermes-facing policy shadow smoke test.")
    parser.add_argument("--base-url", default="", help="Use an existing server instead of launching a temporary one.")
    parser.add_argument("--namespace", default="hermes_policy_shadow_smoke")
    args = parser.parse_args()

    if args.base_url:
        report = run(args.base_url, args.namespace)
    else:
        with TemporaryDirectory(ignore_cleanup_errors=True) as raw_tmp:
            proc, stdout, stderr = start_server(Path(raw_tmp) / "hermes_policy_shadow_smoke.db")
            try:
                report = run(BASE_URL, args.namespace)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                stdout.close()
                stderr.close()
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "json": str(OUT_JSON),
                "markdown": str(OUT_MD),
                "namespace": report["namespace"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
