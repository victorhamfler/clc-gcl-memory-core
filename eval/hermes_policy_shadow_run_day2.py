from __future__ import annotations

import argparse
import http.client
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_AGENT_ID = "hermes_policy_shadow_day2"
OUT_JSON = REPO_ROOT / "experiments" / "hermes_policy_shadow_day2_results.json"
OUT_MD = REPO_ROOT / "experiments" / "hermes_policy_shadow_day2_report.md"


CORE_MEMORIES = [
    {
        "ref": "github_upload_policy",
        "text": "GitHub uploads require explicit confirmation in the current conversation before any upload action.",
        "source": "policy/github_upload_policy.md",
        "memory_type": "procedure",
    },
    {
        "ref": "github_upload_filename",
        "text": "GitHub upload report filename should be github_upload_report.md.",
        "source": "policy/github_upload_filename.md",
        "memory_type": "semantic_note",
    },
    {
        "ref": "calendar_change_policy",
        "text": "Calendar schedule changes require manual approval before changing meeting events.",
        "source": "policy/calendar_change_policy.md",
        "memory_type": "procedure",
    },
    {
        "ref": "broad_policy_note",
        "text": "Broad policy note: all approvals should be documented in the change log.",
        "source": "policy/broad_policy_note.md",
        "memory_type": "procedure",
    },
    {
        "ref": "drink_preference",
        "text": "Victor prefers espresso in the morning and sparkling water in the afternoon.",
        "source": "preference/drinks.md",
        "memory_type": "preference",
    },
    {
        "ref": "weather_method",
        "text": "The weather radar method uses AccuWeather URL format for Sant Carles de la Rapita.",
        "source": "weather/radar_method.md",
        "memory_type": "semantic_note",
    },
    {
        "ref": "server_config",
        "text": "Memory program server runs on port 8765 with embedding backend llama_cpp.",
        "source": "infra/server_config.md",
        "memory_type": "semantic_note",
    },
    {
        "ref": "project_clc",
        "text": "Victor is working on the CLC-GCL memory core with layered cognitive memory.",
        "source": "project/clc_gcl.md",
        "memory_type": "semantic_note",
    },
]


PRESSURE_MEMORIES = [
    {
        "ref": "github_issue_note",
        "text": "GitHub issue notes can mention upload blockers, but they do not authorize repository uploads.",
        "source": "pressure/github_issue_note.md",
        "memory_type": "semantic_note",
    },
    {
        "ref": "report_template_note",
        "text": "Weekly status reports use a separate template named weekly_status_template.md.",
        "source": "pressure/report_template_note.md",
        "memory_type": "semantic_note",
    },
    {
        "ref": "calendar_attendance_note",
        "text": "Calendar attendance notes record who joined a meeting but do not change meeting events.",
        "source": "pressure/calendar_attendance_note.md",
        "memory_type": "semantic_note",
    },
    {
        "ref": "approval_archive_note",
        "text": "Approval archive entries are stored for audit history after the actual decision has been made.",
        "source": "pressure/approval_archive_note.md",
        "memory_type": "semantic_note",
    },
    {
        "ref": "filename_distractor",
        "text": "The weather export filename should be radar_snapshot.txt when saving text-only radar notes.",
        "source": "pressure/weather_filename_note.md",
        "memory_type": "semantic_note",
    },
    {
        "ref": "repo_publish_draft",
        "text": "Repository publish drafts describe release notes, but drafts are not upload permission.",
        "source": "pressure/repo_publish_draft.md",
        "memory_type": "semantic_note",
    },
]


ALL_MEMORIES = CORE_MEMORIES + PRESSURE_MEMORIES
REF_TO_SOURCE = {item["ref"]: item["source"] for item in ALL_MEMORIES}
SOURCE_TO_REF = {item["source"]: item["ref"] for item in ALL_MEMORIES}
POLICY_REFS = {
    "github_upload_policy",
    "github_upload_filename",
    "calendar_change_policy",
    "broad_policy_note",
}


POLICY_CASES = [
    {
        "id": "github_policy_1",
        "query": "What GitHub upload policy should Hermes follow?",
        "expected_refs": ["github_upload_policy"],
        "required_all": ["explicit confirmation"],
        "forbidden_any": ["github_upload_report.md", "calendar schedule"],
    },
    {
        "id": "github_uploading_1",
        "query": "What should happen before uploading to GitHub?",
        "expected_refs": ["github_upload_policy"],
        "required_all": ["explicit confirmation"],
        "forbidden_any": ["github_upload_report.md", "calendar schedule"],
    },
    {
        "id": "github_auto_1",
        "query": "Can Hermes upload to GitHub automatically?",
        "expected_refs": ["github_upload_policy"],
        "required_all": ["explicit confirmation"],
        "forbidden_any": ["github_upload_report.md", "calendar schedule"],
    },
    {
        "id": "github_filename_1",
        "query": "What GitHub upload report filename should be used?",
        "expected_refs": ["github_upload_filename"],
        "required_all": ["github_upload_report.md"],
        "forbidden_any": ["explicit confirmation", "calendar schedule"],
    },
    {
        "id": "github_filename_2",
        "query": "What file should the GitHub upload report use?",
        "expected_refs": ["github_upload_filename"],
        "required_all": ["github_upload_report.md"],
        "forbidden_any": ["explicit confirmation", "calendar schedule"],
    },
    {
        "id": "calendar_policy_1",
        "query": "What calendar change policy should Hermes follow?",
        "expected_refs": ["calendar_change_policy"],
        "required_all": ["manual approval"],
        "forbidden_any": ["github upload", "change log"],
    },
    {
        "id": "calendar_change_1",
        "query": "What should happen before changing calendar events?",
        "expected_refs": ["calendar_change_policy"],
        "required_all": ["manual approval"],
        "forbidden_any": ["github upload", "change log"],
    },
    {
        "id": "calendar_auto_1",
        "query": "Can Hermes change meetings automatically?",
        "expected_refs": ["calendar_change_policy"],
        "required_all": ["manual approval"],
        "forbidden_any": ["github upload", "change log"],
    },
    {
        "id": "broad_policy_1",
        "query": "Broad policy note: approvals should be documented.",
        "expected_refs": ["broad_policy_note"],
        "required_all": ["documented"],
        "forbidden_any": ["github upload", "calendar schedule"],
    },
    {
        "id": "broad_policy_2",
        "query": "General policy note: changes should be recorded.",
        "expected_refs": ["broad_policy_note"],
        "required_all": ["documented"],
        "forbidden_any": ["github upload", "calendar schedule"],
    },
    {
        "id": "repo_publish_permission_paraphrase",
        "query": "Before publishing something to the repo, what permission does Hermes need?",
        "expected_refs": ["github_upload_policy"],
        "required_all": ["explicit confirmation"],
        "forbidden_any": ["github_upload_report.md", "calendar schedule"],
    },
    {
        "id": "upload_artifact_paraphrase",
        "query": "Does an upload artifact to GitHub need approval first?",
        "expected_refs": ["github_upload_policy"],
        "required_all": ["explicit confirmation"],
        "forbidden_any": ["github_upload_report.md", "calendar schedule"],
    },
    {
        "id": "markdown_report_name_paraphrase",
        "query": "Which markdown name belongs to the GitHub report?",
        "expected_refs": ["github_upload_filename"],
        "required_all": ["github_upload_report.md"],
        "forbidden_any": ["explicit confirmation", "calendar schedule"],
    },
    {
        "id": "report_file_label_paraphrase",
        "query": "What should the upload report file be called?",
        "expected_refs": ["github_upload_filename"],
        "required_all": ["github_upload_report.md"],
        "forbidden_any": ["explicit confirmation", "calendar schedule"],
    },
    {
        "id": "meeting_edit_paraphrase",
        "query": "What approval is needed before editing a meeting?",
        "expected_refs": ["calendar_change_policy"],
        "required_all": ["manual approval"],
        "forbidden_any": ["github upload", "github_upload_report.md"],
    },
    {
        "id": "event_reschedule_paraphrase",
        "query": "Can Hermes reschedule an event without permission?",
        "expected_refs": ["calendar_change_policy"],
        "required_all": ["manual approval"],
        "forbidden_any": ["github upload", "change log"],
    },
    {
        "id": "approval_log_paraphrase",
        "query": "Where should general approvals be logged?",
        "expected_refs": ["broad_policy_note"],
        "required_all": ["change log"],
        "forbidden_any": ["github upload", "calendar schedule"],
    },
    {
        "id": "general_record_paraphrase",
        "query": "For the overall policy note, how are changes recorded?",
        "expected_refs": ["broad_policy_note"],
        "required_all": ["documented"],
        "forbidden_any": ["github upload", "calendar schedule"],
    },
    {
        "id": "multi_filename_and_upload",
        "query": "What file should the GitHub report use, and can Hermes upload it automatically?",
        "expected_refs": ["github_upload_filename", "github_upload_policy"],
        "required_all": ["github_upload_report.md", "explicit confirmation"],
        "forbidden_any": ["calendar schedule"],
        "multi": True,
    },
    {
        "id": "multi_calendar_and_log",
        "query": "Can Hermes change meetings, and where should approvals be documented?",
        "expected_refs": ["calendar_change_policy", "broad_policy_note"],
        "required_all": ["manual approval", "documented"],
        "forbidden_any": ["github upload"],
        "multi": True,
    },
    {
        "id": "multi_repo_file_and_permission",
        "query": "For a repo publish report, give the report filename and the upload permission rule.",
        "expected_refs": ["github_upload_filename", "github_upload_policy"],
        "required_all": ["github_upload_report.md", "explicit confirmation"],
        "forbidden_any": ["calendar schedule"],
        "multi": True,
    },
]


UNRELATED_CASES = [
    {"id": "unrelated_drink", "query": "What drink does Victor prefer?", "required_any": ["espresso", "sparkling water"]},
    {"id": "unrelated_weather", "query": "How should the weather radar be checked?", "required_any": ["accuweather"]},
    {"id": "unrelated_server", "query": "What port does the memory server use?", "required_any": ["8765"]},
    {"id": "unrelated_project", "query": "What project is Victor working on?", "required_any": ["clc-gcl", "memory core"]},
    {"id": "unrelated_template", "query": "What template is used for weekly status reports?", "required_any": ["weekly_status_template.md"]},
    {"id": "unrelated_weather_filename", "query": "What filename is used for weather radar text notes?", "required_any": ["radar_snapshot.txt"]},
]


BASELINE_COMMANDS = [
    ["eval/config_nested_parser_regression.py"],
    ["eval/day1_answer_source_regression.py"],
    ["eval/answer_type_policy_split_probe.py"],
    ["eval/hermes_policy_shadow_smoke.py"],
    [
        "eval/claim_scope_promotion_gate.py",
        "--include-selector-guards",
        "--candidates",
        "test_corpora/claim_scope_alias_candidates_policy_split_v1.json",
    ],
]


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    try:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        if response.status >= 400:
            raise RuntimeError(f"{method} {url} failed with HTTP {response.status}: {raw}")
        return json.loads(raw)
    finally:
        conn.close()


class LiveClient:
    def __init__(self, base_url: str, namespace: str, agent_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.namespace = namespace
        self.agent_id = agent_id

    def get(self, path: str) -> dict[str, Any]:
        return request_json("GET", f"{self.base_url}{path}")

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return request_json("POST", f"{self.base_url}{path}", payload)

    def teach(self, memory: dict[str, Any]) -> dict[str, Any]:
        return self.post(
            "/teach",
            {
                "text": memory["text"],
                "source": memory["source"],
                "namespace": self.namespace,
                "include_global": False,
                "agent_id": self.agent_id,
                "store_session": False,
                "domain": "agent_memory",
                "memory_type": memory["memory_type"],
                "metadata": {"day2_ref": memory["ref"]},
            },
        )

    def retrieve(self, query: str, top_k: int = 10) -> dict[str, Any]:
        return self.post(
            "/retrieve",
            {
                "query": query,
                "top_k": top_k,
                "namespace": self.namespace,
                "include_global": False,
            },
        )

    def ask(self, query: str, top_k: int = 10) -> dict[str, Any]:
        return self.post(
            "/ask",
            {
                "query": query,
                "top_k": top_k,
                "namespace": self.namespace,
                "include_global": False,
                "agent_id": self.agent_id,
                "store_session": False,
            },
        )

    def selector_explain(self, query: str, top_k: int = 10) -> dict[str, Any]:
        return self.post(
            "/selector_explain",
            {
                "query": query,
                "top_k": top_k,
                "namespace": self.namespace,
                "include_global": False,
            },
        )

    def correct(self, memory_id: str, text: str) -> dict[str, Any]:
        return self.post(
            "/correct",
            {
                "memory_id": memory_id,
                "text": text,
                "namespace": self.namespace,
                "include_global": False,
                "agent_id": self.agent_id,
                "store_session": False,
            },
        )


def row_ref(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    return SOURCE_TO_REF.get(str(row.get("source") or ""))


def rank_for(rows: list[dict[str, Any]], ref: str) -> int | None:
    for idx, row in enumerate(rows, start=1):
        if row_ref(row) == ref:
            return idx
    return None


def compact_row(row: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "ref": row_ref(row),
        "score": row.get("score"),
        "claim_scope_score": row.get("claim_scope_score"),
        "answer_type_score": row.get("answer_type_score"),
        "scope_deflection_penalty": row.get("scope_deflection_penalty"),
        "source": row.get("source"),
        "text": row.get("text"),
        "authority": row.get("authority_state") or row.get("authority"),
    }


def answer_contains(answer: str, terms: list[str]) -> bool:
    lower = answer.lower()
    return all(term.lower() in lower for term in terms)


def answer_contains_any(answer: str, terms: list[str]) -> bool:
    lower = answer.lower()
    return any(term.lower() in lower for term in terms)


def run_baselines(skip: bool) -> dict[str, dict[str, Any]]:
    if skip:
        return {}
    results: dict[str, dict[str, Any]] = {}
    for command in BASELINE_COMMANDS:
        label = Path(command[0]).stem
        full_command = [sys.executable, *command]
        started = time.time()
        proc = subprocess.run(full_command, cwd=ROOT, capture_output=True, text=True)
        results[label] = {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "seconds": round(time.time() - started, 3),
            "command": " ".join(command),
            "stdout_tail": proc.stdout[-1600:],
            "stderr_tail": proc.stderr[-1600:],
        }
    return results


def seed_memories(client: LiveClient, session_name: str, source_to_mid: dict[str, str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if source_to_mid:
        return records
    for memory in ALL_MEMORIES:
        response = client.teach(memory)
        memory_id = (response.get("memory") or {}).get("memory_id")
        if memory_id:
            source_to_mid[memory["source"]] = str(memory_id)
        records.append({"session": session_name, "ref": memory["ref"], "source": memory["source"], "memory_id": memory_id})
        time.sleep(0.08)
    return records


def add_correction_pressure(client: LiveClient, session_name: str, source_to_mid: dict[str, str]) -> list[dict[str, Any]]:
    corrections = [
        (
            "weather_method",
            "The weather radar method uses AccuWeather URL format for Sant Carles de la Rapita, with text extraction fallback when canvas images are unreadable.",
        ),
        (
            "project_clc",
            "Victor is working on the CLC-GCL memory core with layered cognitive memory and selector policy-split architecture.",
        ),
        (
            "github_issue_note",
            "GitHub issue notes can mention upload blockers, but they are not permission to upload to the repository.",
        ),
    ]
    if session_name == "end-of-day":
        corrections.append(
            (
                "calendar_attendance_note",
                "Calendar attendance notes preserve attendees only; changing meeting events still follows the separate calendar policy.",
            )
        )
    records: list[dict[str, Any]] = []
    for ref, text in corrections:
        memory_id = source_to_mid.get(REF_TO_SOURCE[ref])
        if not memory_id:
            continue
        response = client.correct(memory_id, text)
        records.append({"session": session_name, "ref": ref, "memory_id": memory_id, "ok": response.get("ok")})
        time.sleep(0.08)
    return records


def evaluate_policy_case(client: LiveClient, case: dict[str, Any]) -> dict[str, Any]:
    ret = client.retrieve(case["query"])
    rows = ret.get("results") or []
    ask_result = client.ask(case["query"])
    evidence = ask_result.get("evidence") or []
    explain = client.selector_explain(case["query"])
    answer = str(ask_result.get("answer") or "")

    expected_refs = list(case["expected_refs"])
    expected_set = set(expected_refs)
    top_ref = row_ref(rows[0]) if rows else None
    evidence_refs = [row_ref(item) for item in evidence]
    retrieved_top = [row_ref(row) for row in rows[: max(4, len(expected_refs))]]
    failures: list[str] = []

    if case.get("multi"):
        missing_retrieval = sorted(ref for ref in expected_refs if ref not in retrieved_top)
        missing_evidence = sorted(ref for ref in expected_refs if ref not in evidence_refs[:3])
        if missing_retrieval:
            failures.append(f"missing_expected_retrieval:{','.join(missing_retrieval)}")
        if missing_evidence:
            failures.append(f"missing_expected_evidence:{','.join(missing_evidence)}")
    else:
        if top_ref != expected_refs[0]:
            failures.append(f"wrong_retrieval_top:{top_ref}")
        if not evidence_refs or evidence_refs[0] != expected_refs[0]:
            failures.append(f"wrong_answer_top:{evidence_refs[0] if evidence_refs else None}")

    if not answer_contains(answer, list(case.get("required_all") or [])):
        failures.append("missing_required_answer_text")
    forbidden_hits = [term for term in case.get("forbidden_any") or [] if term.lower() in answer.lower()]
    if forbidden_hits:
        failures.append(f"forbidden_answer_text:{','.join(forbidden_hits)}")

    for row in rows[:3]:
        ref = row_ref(row)
        if ref in POLICY_REFS and ref not in expected_set and not case.get("multi"):
            if float(row.get("score") or 0.0) >= float((rows[0] or {}).get("score") or 0.0) - 0.04:
                failures.append(f"near_top_policy_distractor:{ref}")

    return {
        "id": case["id"],
        "query": case["query"],
        "expected_refs": expected_refs,
        "passed": not failures,
        "failures": failures,
        "retrieval_top_ref": top_ref,
        "evidence_refs": evidence_refs,
        "ask_answer": answer,
        "target_ranks": {ref: rank_for(rows, ref) for ref in expected_refs},
        "retrieve_top_10": [compact_row(row, idx) for idx, row in enumerate(rows, start=1)],
        "ask_evidence": [compact_row(row, idx) for idx, row in enumerate(evidence, start=1)],
        "selector_explain": explain,
    }


def evaluate_unrelated_case(client: LiveClient, case: dict[str, Any]) -> dict[str, Any]:
    ret = client.retrieve(case["query"])
    rows = ret.get("results") or []
    ask_result = client.ask(case["query"])
    evidence = ask_result.get("evidence") or []
    answer = str(ask_result.get("answer") or "")
    leaks = [row_ref(row) for row in rows[:3] if row_ref(row) in POLICY_REFS]
    evidence_leaks = [row_ref(row) for row in evidence[:3] if row_ref(row) in POLICY_REFS]
    failures: list[str] = []
    if leaks:
        failures.append(f"policy_retrieval_leak:{','.join(ref for ref in leaks if ref)}")
    if evidence_leaks:
        failures.append(f"policy_evidence_leak:{','.join(ref for ref in evidence_leaks if ref)}")
    if case.get("required_any") and not answer_contains_any(answer, list(case["required_any"])):
        failures.append("missing_unrelated_answer_text")
    return {
        "id": case["id"],
        "query": case["query"],
        "passed": not failures,
        "failures": failures,
        "ask_answer": answer,
        "retrieve_top_10": [compact_row(row, idx) for idx, row in enumerate(rows, start=1)],
        "ask_evidence": [compact_row(row, idx) for idx, row in enumerate(evidence, start=1)],
    }


def run_session(client: LiveClient, session_name: str, source_to_mid: dict[str, str]) -> dict[str, Any]:
    session: dict[str, Any] = {
        "name": session_name,
        "teaches": seed_memories(client, session_name, source_to_mid),
        "corrections": add_correction_pressure(client, session_name, source_to_mid),
        "policy_queries": [],
        "unrelated_queries": [],
    }
    for case in POLICY_CASES:
        session["policy_queries"].append(evaluate_policy_case(client, case))
        time.sleep(0.06)
    for case in UNRELATED_CASES:
        session["unrelated_queries"].append(evaluate_unrelated_case(client, case))
        time.sleep(0.06)
    return session


def get_commit_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def write_markdown(report: dict[str, Any], out_path: Path) -> None:
    stats = report["stats"]
    lines = [
        "# Hermes Policy Shadow Run Day 2 Report",
        "",
        f"- Commit SHA: `{report['commit_sha']}`",
        f"- Namespace: `{report['namespace']}`",
        f"- Base URL: `{report['base_url']}`",
        f"- Date: {report['date_utc']}",
        "",
        "## Status",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "## Stats",
        "",
        f"- Sessions: {stats['sessions']}",
        f"- Teaches: {stats['teaches']}",
        f"- Corrections: {stats['corrections']}",
        f"- Policy queries: {stats['policy_queries']}",
        f"- Policy passed: {stats['policy_passed']}",
        f"- Policy failed: {stats['policy_failed']}",
        f"- Unrelated queries: {stats['unrelated_queries']}",
        f"- Unrelated passed: {stats['unrelated_passed']}",
        f"- Unrelated failed: {stats['unrelated_failed']}",
        "",
        "## Baselines",
        "",
        "| test | pass | seconds |",
        "| --- | --- | ---: |",
    ]
    if report["baseline_results"]:
        for label, result in sorted(report["baseline_results"].items()):
            lines.append(f"| `{label}` | `{result['ok']}` | {result['seconds']} |")
    else:
        lines.append("| skipped | `True` | 0 |")

    lines.extend(["", "## Failure Summary", ""])
    if report["failure_summary"]:
        lines.extend(["| label | count |", "| --- | ---: |"])
        for label, count in sorted(report["failure_summary"].items()):
            lines.append(f"| `{label}` | {count} |")
    else:
        lines.append("No failures.")

    lines.extend(["", "## Failed Cases", ""])
    if report["failures"]:
        for case in report["failures"]:
            lines.extend(
                [
                    f"### {case['id']}",
                    "",
                    f"- Query: `{case['query']}`",
                    f"- Failures: `{case['failures']}`",
                    f"- Retrieval top: `{case.get('retrieval_top_ref')}`",
                    f"- Evidence refs: `{case.get('evidence_refs')}`",
                    f"- Answer: {case.get('ask_answer')}",
                    "",
                ]
            )
    else:
        lines.append("No failed cases.")

    lines.extend(["", "## Successful Boundary Examples", ""])
    for case in report["best_examples"][:12]:
        lines.extend(
            [
                f"### {case['id']}",
                "",
                f"- Query: `{case['query']}`",
                f"- Expected refs: `{case['expected_refs']}`",
                f"- Target ranks: `{case['target_ranks']}`",
                f"- Evidence refs: `{case['evidence_refs']}`",
                "",
            ]
        )

    recommendation = "promote Day 2" if report["ok"] else "keep guarded and convert failures into local regressions"
    lines.extend(["", "## Recommendation", "", f"**{recommendation.upper()}**", ""])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    namespace = args.namespace or f"hermes_policy_shadow_day2_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    client = LiveClient(args.base_url, namespace, args.agent_id)
    health = client.get("/health")
    if not health.get("ok"):
        raise RuntimeError(f"Server health check failed: {health}")

    baseline_results = run_baselines(args.skip_baselines)
    source_to_mid: dict[str, str] = {}
    sessions = [run_session(client, name, source_to_mid) for name in ("morning", "middle", "end-of-day")]

    policy_cases = [case for session in sessions for case in session["policy_queries"]]
    unrelated_cases = [case for session in sessions for case in session["unrelated_queries"]]
    failed_cases = [case for case in [*policy_cases, *unrelated_cases] if not case["passed"]]
    baseline_failures = [
        {"id": label, "query": result["command"], "failures": ["baseline_failed"], "ask_answer": result["stderr_tail"]}
        for label, result in baseline_results.items()
        if not result["ok"]
    ]
    all_failures = [*failed_cases, *baseline_failures]
    failure_counts: dict[str, int] = {}
    for case in all_failures:
        for failure in case["failures"]:
            failure_counts[failure] = failure_counts.get(failure, 0) + 1

    report = {
        "ok": not all_failures,
        "base_url": args.base_url,
        "namespace": namespace,
        "commit_sha": get_commit_sha(),
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "environment": {
            "python": sys.version,
            "server_db": health.get("database"),
            "embedding": health.get("embedding"),
        },
        "baseline_results": baseline_results,
        "stats": {
            "sessions": len(sessions),
            "teaches": len([item for session in sessions for item in session["teaches"]]),
            "corrections": len([item for session in sessions for item in session["corrections"]]),
            "policy_queries": len(policy_cases),
            "policy_passed": sum(1 for case in policy_cases if case["passed"]),
            "policy_failed": sum(1 for case in policy_cases if not case["passed"]),
            "unrelated_queries": len(unrelated_cases),
            "unrelated_passed": sum(1 for case in unrelated_cases if case["passed"]),
            "unrelated_failed": sum(1 for case in unrelated_cases if not case["passed"]),
        },
        "failure_summary": failure_counts,
        "best_examples": [case for case in policy_cases if case["passed"]][:16],
        "failures": all_failures,
        "sessions": sessions,
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Hermes Day 2 live policy-shadow harness.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Hermes memory server URL.")
    parser.add_argument("--namespace", default=None, help="Namespace to use. Defaults to a timestamped Day 2 namespace.")
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID, help="Agent id used for live teach/ask/correct calls.")
    parser.add_argument("--out-json", default=str(OUT_JSON), help="Path for JSON results.")
    parser.add_argument("--out-md", default=str(OUT_MD), help="Path for Markdown report.")
    parser.add_argument("--skip-baselines", action="store_true", help="Skip local baseline regression commands.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "namespace": report["namespace"],
                "json": str(out_json),
                "markdown": str(out_md),
                "failure_summary": report["failure_summary"],
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
