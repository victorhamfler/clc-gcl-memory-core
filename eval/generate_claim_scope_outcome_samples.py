from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_config, resolve_project_path  # noqa: E402


DEFAULT_BATCH = "claim-scope-hard-cases-v3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def default_log_path() -> Path:
    config = load_config(ROOT)
    cfg = config.get("outcome_log") if isinstance(config.get("outcome_log"), dict) else {}
    return resolve_project_path(ROOT, cfg.get("path"), "logs/memory_outcomes.jsonl")


def row(batch: str, case_id: str, source: str, text: str, score: float, *, rank: int | None = None) -> dict[str, Any]:
    memory_id = stable_id("mem", batch, case_id, source, text)
    return {
        "memory_id": memory_id,
        "rank": rank,
        "namespace": f"agent:{batch}",
        "source": source,
        "domain_name": "agent_memory",
        "memory_type": "semantic_note",
        "score": score,
        "cosine": None,
        "authority_state": "standalone",
        "claim_scope_score": None,
        "correction_relevance_score": None,
        "correction_chain_score": None,
        "supersession_score": None,
        "relation_supersession_score": None,
        "text": text,
    }


def owner_relation_cases(batch: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "owner_relation_assignee_selector_report",
            "query": "Who handles the selector feedback report?",
            "answer": "Current memory indicates: Assignee: Mina for the selector feedback report.",
            "rows": [
                row(batch, "owner_relation_assignee_selector_report", "v4/assignee_selector_feedback_report.md", "Assignee: Mina for the selector feedback report.", 0.93, rank=1),
                row(batch, "owner_relation_assignee_selector_report", "v4/deadline_selector_feedback_report.md", "Selector feedback report is due Friday.", 0.73, rank=2),
                row(batch, "owner_relation_assignee_selector_report", "v4/filename_selector_feedback_report.md", "Selector feedback report filename should be selector_feedback_report.md.", 0.64, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "owner_relation_responsible_calendar",
            "query": "Who handles calendar change approvals?",
            "answer": "Current memory indicates: Responsible agent: Operations agent for calendar change approvals.",
            "rows": [
                row(batch, "owner_relation_responsible_calendar", "v4/responsible_calendar_approvals.md", "Responsible agent: Operations agent for calendar change approvals.", 0.92, rank=1),
                row(batch, "owner_relation_responsible_calendar", "v4/calendar_change_policy.md", "Calendar change policy requires manual approval before moving events.", 0.76, rank=2),
                row(batch, "owner_relation_responsible_calendar", "v4/github_upload_policy.md", "GitHub upload policy requires explicit current-conversation approval.", 0.5, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "owner_relation_assignment_archive",
            "query": "Who handles archive migration?",
            "answer": "Current memory indicates: Assignment: Iris for archive migration.",
            "rows": [
                row(batch, "owner_relation_assignment_archive", "v4/assignment_archive_migration.md", "Assignment: Iris for archive migration.", 0.91, rank=1),
                row(batch, "owner_relation_assignment_archive", "v4/codename_archive_migration.md", "Archive migration codename is Redwood Lantern.", 0.75, rank=2),
                row(batch, "owner_relation_assignment_archive", "v4/deadline_archive_migration.md", "Archive migration checkpoint is due Monday.", 0.66, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "owner_relation_assigned_release_notes",
            "query": "Who handles release notes?",
            "answer": "Current memory indicates: Release notes are assigned to Documentation agent.",
            "rows": [
                row(batch, "owner_relation_assigned_release_notes", "v4/assigned_release_notes.md", "Release notes are assigned to Documentation agent.", 0.9, rank=1),
                row(batch, "owner_relation_assigned_release_notes", "v4/deadline_release_notes.md", "Release notes deadline is Thursday.", 0.72, rank=2),
                row(batch, "owner_relation_assigned_release_notes", "v4/filename_release_notes.md", "Release notes filename should be release_notes.md.", 0.62, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "owner_relation_accountable_api",
            "query": "Who handles memory API uptime?",
            "answer": "Current memory indicates: Platform agent is accountable for memory API uptime.",
            "rows": [
                row(batch, "owner_relation_accountable_api", "v4/accountable_memory_api_uptime.md", "Platform agent is accountable for memory API uptime.", 0.9, rank=1),
                row(batch, "owner_relation_accountable_api", "v4/backend_port_v2.md", "Memory API backend port should be 8765.", 0.72, rank=2),
                row(batch, "owner_relation_accountable_api", "v4/backend_host.md", "Memory API backend host should remain 127.0.0.1 for local testing.", 0.68, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "owner_relation_responsibility_docs",
            "query": "Who handles the agent manual?",
            "answer": "Current memory indicates: Responsibility: Documentation agent for the agent manual.",
            "rows": [
                row(batch, "owner_relation_responsibility_docs", "v4/responsibility_agent_manual.md", "Responsibility: Documentation agent for the agent manual.", 0.9, rank=1),
                row(batch, "owner_relation_responsibility_docs", "v4/manual_filename.md", "Agent manual filename should be AGENT_USER_MANUAL.md.", 0.73, rank=2),
                row(batch, "owner_relation_responsibility_docs", "v4/manual_status.md", "Agent manual status is ready for testing.", 0.65, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
    ]


def answer_type_boundary_cases(batch: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "answer_type_radar_method",
            "query": "What radar method should Victor use?",
            "answer": "Current memory indicates: Radar method should use the AccuWeather radar URL.",
            "rows": [
                row(batch, "answer_type_radar_method", "v5/radar_method.md", "Radar method should use the AccuWeather radar URL.", 0.94, rank=1),
                row(batch, "answer_type_radar_method", "v5/radar_filename.md", "Radar report filename should be accuweather_radar_report.md.", 0.79, rank=2),
                row(batch, "answer_type_radar_method", "v5/radar_theme.md", "Radar report color theme should be blue and gray.", 0.63, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_radar_tool",
            "query": "Which radar tool is required?",
            "answer": "Current memory indicates: Radar tool choice is AccuWeather.",
            "rows": [
                row(batch, "answer_type_radar_tool", "v5/radar_tool.md", "Radar tool choice is AccuWeather.", 0.93, rank=1),
                row(batch, "answer_type_radar_tool", "v5/radar_filename.md", "Radar report filename should be accuweather_radar_report.md.", 0.77, rank=2),
                row(batch, "answer_type_radar_tool", "v5/radar_theme.md", "Radar report color theme should be blue and gray.", 0.62, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_radar_filename",
            "query": "What radar report filename should be used?",
            "answer": "Current memory indicates: Radar report filename should be accuweather_radar_report.md.",
            "rows": [
                row(batch, "answer_type_radar_filename", "v5/radar_filename.md", "Radar report filename should be accuweather_radar_report.md.", 0.94, rank=1),
                row(batch, "answer_type_radar_filename", "v5/radar_method.md", "Radar method should use the AccuWeather radar URL.", 0.76, rank=2),
                row(batch, "answer_type_radar_filename", "v5/radar_theme.md", "Radar report color theme should be blue and gray.", 0.68, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_radar_file_name",
            "query": "What file name should the radar report have?",
            "answer": "Current memory indicates: Radar report file name should be accuweather_radar_report.md.",
            "rows": [
                row(batch, "answer_type_radar_file_name", "v5/radar_file_name.md", "Radar report file name should be accuweather_radar_report.md.", 0.94, rank=1),
                row(batch, "answer_type_radar_file_name", "v5/radar_method.md", "Radar method should use the AccuWeather radar URL.", 0.75, rank=2),
                row(batch, "answer_type_radar_file_name", "v5/radar_theme.md", "Radar report color theme should be blue and gray.", 0.68, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_radar_theme",
            "query": "What radar report color theme should be used?",
            "answer": "Current memory indicates: Radar report color theme should be blue and gray.",
            "rows": [
                row(batch, "answer_type_radar_theme", "v5/radar_theme.md", "Radar report color theme should be blue and gray.", 0.93, rank=1),
                row(batch, "answer_type_radar_theme", "v5/radar_filename.md", "Radar report filename should be accuweather_radar_report.md.", 0.72, rank=2),
                row(batch, "answer_type_radar_theme", "v5/radar_method.md", "Radar method should use the AccuWeather radar URL.", 0.69, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_report_owner",
            "query": "Who owns the selector feedback report?",
            "answer": "Current memory indicates: Mina owns the selector feedback report.",
            "rows": [
                row(batch, "answer_type_report_owner", "v5/feedback_report_owner.md", "Mina owns the selector feedback report.", 0.94, rank=1),
                row(batch, "answer_type_report_owner", "v5/feedback_report_deadline.md", "Selector feedback report is due Friday.", 0.78, rank=2),
                row(batch, "answer_type_report_owner", "v5/feedback_report_filename.md", "Selector feedback report filename should be selector_feedback_report.md.", 0.67, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_report_responsible",
            "query": "Who is responsible for the report?",
            "answer": "Current memory indicates: Mina is responsible for the selector feedback report.",
            "rows": [
                row(batch, "answer_type_report_responsible", "v5/feedback_report_responsible.md", "Mina is responsible for the selector feedback report.", 0.93, rank=1),
                row(batch, "answer_type_report_responsible", "v5/feedback_report_deadline.md", "Selector feedback report is due Friday.", 0.77, rank=2),
                row(batch, "answer_type_report_responsible", "v5/feedback_report_filename.md", "Selector feedback report filename should be selector_feedback_report.md.", 0.66, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_report_deadline",
            "query": "When is the selector feedback report due?",
            "answer": "Current memory indicates: Selector feedback report is due Friday.",
            "rows": [
                row(batch, "answer_type_report_deadline", "v5/feedback_report_deadline.md", "Selector feedback report is due Friday.", 0.94, rank=1),
                row(batch, "answer_type_report_deadline", "v5/feedback_report_owner.md", "Mina owns the selector feedback report.", 0.76, rank=2),
                row(batch, "answer_type_report_deadline", "v5/feedback_report_filename.md", "Selector feedback report filename should be selector_feedback_report.md.", 0.66, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_report_deadline_generic",
            "query": "What deadline should Hermes remember?",
            "answer": "Current memory indicates: Selector feedback report deadline is Friday.",
            "rows": [
                row(batch, "answer_type_report_deadline_generic", "v5/feedback_report_deadline.md", "Selector feedback report deadline is Friday.", 0.92, rank=1),
                row(batch, "answer_type_report_deadline_generic", "v5/feedback_report_owner.md", "Mina owns the selector feedback report.", 0.74, rank=2),
                row(batch, "answer_type_report_deadline_generic", "v5/feedback_report_filename.md", "Selector feedback report filename should be selector_feedback_report.md.", 0.67, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_report_filename",
            "query": "What filename should the feedback report use?",
            "answer": "Current memory indicates: Feedback report filename should be selector_feedback_report.md.",
            "rows": [
                row(batch, "answer_type_report_filename", "v5/feedback_report_filename.md", "Feedback report filename should be selector_feedback_report.md.", 0.94, rank=1),
                row(batch, "answer_type_report_filename", "v5/feedback_report_owner.md", "Mina owns the selector feedback report.", 0.75, rank=2),
                row(batch, "answer_type_report_filename", "v5/feedback_report_deadline.md", "Selector feedback report is due Friday.", 0.72, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_github_upload_policy",
            "query": "What GitHub upload policy should Hermes follow?",
            "answer": "Current memory indicates: GitHub upload policy requires an explicit request in the current conversation.",
            "rows": [
                row(batch, "answer_type_github_upload_policy", "v5/github_upload_policy.md", "GitHub upload policy requires an explicit request in the current conversation.", 0.94, rank=1),
                row(batch, "answer_type_github_upload_policy", "v5/calendar_change_policy.md", "Calendar change policy requires manual approval before moving events.", 0.77, rank=2),
                row(batch, "answer_type_github_upload_policy", "v5/broad_policy_note.md", "Broad policy note: approvals should be documented.", 0.59, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "answer_type_calendar_change_policy",
            "query": "What calendar change policy should Hermes follow?",
            "answer": "Current memory indicates: Calendar change policy requires manual approval before moving events.",
            "rows": [
                row(batch, "answer_type_calendar_change_policy", "v5/calendar_change_policy.md", "Calendar change policy requires manual approval before moving events.", 0.94, rank=1),
                row(batch, "answer_type_calendar_change_policy", "v5/github_upload_policy.md", "GitHub upload policy requires an explicit request in the current conversation.", 0.76, rank=2),
                row(batch, "answer_type_calendar_change_policy", "v5/broad_policy_note.md", "Broad policy note: approvals should be documented.", 0.59, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
    ]


def policy_split_cases(batch: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "policy_split_github_upload_policy_vs_filename",
            "query": "What GitHub upload policy should Hermes follow?",
            "answer": "Current memory indicates: GitHub uploads require explicit confirmation in the current conversation.",
            "rows": [
                row(batch, "policy_split_github_upload_policy_vs_filename", "v6/github_upload_policy.md", "GitHub uploads require explicit confirmation in the current conversation.", 0.9, rank=1),
                row(batch, "policy_split_github_upload_policy_vs_filename", "v6/github_upload_filename.md", "GitHub upload report filename should be github_upload_report.md.", 0.89, rank=2),
                row(batch, "policy_split_github_upload_policy_vs_filename", "v6/broad_policy_note.md", "Broad policy note: approvals should be documented.", 0.84, rank=3),
                row(batch, "policy_split_github_upload_policy_vs_filename", "v6/calendar_change_policy.md", "Calendar schedule changes require manual approval before changing meeting events.", 0.77, rank=4),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8), (3, "wrong_domain", -0.8)],
        },
        {
            "id": "policy_split_github_uploading_vs_filename",
            "query": "What should happen before uploading to GitHub?",
            "answer": "Current memory indicates: GitHub uploads require explicit confirmation in the current conversation.",
            "rows": [
                row(batch, "policy_split_github_uploading_vs_filename", "v6/github_upload_policy.md", "GitHub uploads require explicit confirmation in the current conversation.", 0.88, rank=1),
                row(batch, "policy_split_github_uploading_vs_filename", "v6/github_upload_filename.md", "GitHub upload report filename should be github_upload_report.md.", 0.87, rank=2),
                row(batch, "policy_split_github_uploading_vs_filename", "v6/broad_policy_note.md", "Broad policy note: approvals should be documented.", 0.82, rank=3),
                row(batch, "policy_split_github_uploading_vs_filename", "v6/calendar_change_policy.md", "Calendar schedule changes require manual approval before changing meeting events.", 0.78, rank=4),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8), (3, "wrong_domain", -0.8)],
        },
        {
            "id": "policy_split_calendar_change_vs_broad",
            "query": "What calendar change policy should Hermes follow?",
            "answer": "Current memory indicates: Calendar schedule changes require manual approval before changing meeting events.",
            "rows": [
                row(batch, "policy_split_calendar_change_vs_broad", "v6/calendar_change_policy.md", "Calendar schedule changes require manual approval before changing meeting events.", 0.9, rank=1),
                row(batch, "policy_split_calendar_change_vs_broad", "v6/broad_policy_note.md", "Broad policy note: approvals should be documented.", 0.89, rank=2),
                row(batch, "policy_split_calendar_change_vs_broad", "v6/github_upload_policy.md", "GitHub uploads require explicit confirmation in the current conversation.", 0.78, rank=3),
                row(batch, "policy_split_calendar_change_vs_broad", "v6/github_upload_filename.md", "GitHub upload report filename should be github_upload_report.md.", 0.76, rank=4),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8), (3, "wrong_domain", -0.8)],
        },
        {
            "id": "policy_split_calendar_events_vs_broad",
            "query": "What should happen before changing calendar events?",
            "answer": "Current memory indicates: Calendar schedule changes require manual approval before changing meeting events.",
            "rows": [
                row(batch, "policy_split_calendar_events_vs_broad", "v6/calendar_change_policy.md", "Calendar schedule changes require manual approval before changing meeting events.", 0.88, rank=1),
                row(batch, "policy_split_calendar_events_vs_broad", "v6/broad_policy_note.md", "Broad policy note: approvals should be documented.", 0.87, rank=2),
                row(batch, "policy_split_calendar_events_vs_broad", "v6/github_upload_policy.md", "GitHub uploads require explicit confirmation in the current conversation.", 0.78, rank=3),
                row(batch, "policy_split_calendar_events_vs_broad", "v6/github_upload_filename.md", "GitHub upload report filename should be github_upload_report.md.", 0.76, rank=4),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8), (3, "wrong_domain", -0.8)],
        },
    ]


def cases(batch: str) -> list[dict[str, Any]]:
    if "policy-split" in batch:
        return policy_split_cases(batch)
    if "answer-type" in batch:
        return answer_type_boundary_cases(batch)
    if "owner-relation" in batch:
        return owner_relation_cases(batch)
    return [
        {
            "id": "owner_selector_feedback_report",
            "query": "Who owns the selector feedback report?",
            "answer": "Current memory indicates: Mina owns the selector feedback report draft.",
            "rows": [
                row(batch, "owner_selector_feedback_report", "v3/owner_selector_feedback_report.md", "Mina owns the selector feedback report draft.", 0.91, rank=1),
                row(batch, "owner_selector_feedback_report", "v3/deadline_selector_feedback_report.md", "Selector feedback report is due Friday.", 0.74, rank=2),
                row(batch, "owner_selector_feedback_report", "v3/report_filename_feedback.md", "Selector feedback report filename should be feedback_gate_report.md.", 0.66, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "deadline_selector_feedback_report",
            "query": "When is the selector feedback report due?",
            "answer": "Current memory indicates: Selector feedback report is due Friday.",
            "rows": [
                row(batch, "deadline_selector_feedback_report", "v3/deadline_selector_feedback_report.md", "Selector feedback report is due Friday.", 0.9, rank=1),
                row(batch, "deadline_selector_feedback_report", "v3/owner_selector_feedback_report.md", "Mina owns the selector feedback report draft.", 0.76, rank=2),
                row(batch, "deadline_selector_feedback_report", "v3/report_filename_feedback.md", "Selector feedback report filename should be feedback_gate_report.md.", 0.65, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "owner_redwood_lantern",
            "query": "Who owns Redwood Lantern?",
            "answer": "Current memory indicates: Iris owns the Redwood Lantern project.",
            "rows": [
                row(batch, "owner_redwood_lantern", "v3/owner_redwood_lantern.md", "Iris owns the Redwood Lantern project.", 0.88, rank=1),
                row(batch, "owner_redwood_lantern", "v3/codename_redwood_lantern.md", "Redwood Lantern is the archive migration codename.", 0.72, rank=2),
                row(batch, "owner_redwood_lantern", "v3/deadline_redwood_lantern.md", "Redwood Lantern checkpoint is due Monday.", 0.61, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "codename_redwood_lantern",
            "query": "Which codename belongs to the archive migration?",
            "answer": "Current memory indicates: Redwood Lantern is the archive migration codename.",
            "rows": [
                row(batch, "codename_redwood_lantern", "v3/codename_redwood_lantern.md", "Redwood Lantern is the archive migration codename.", 0.89, rank=1),
                row(batch, "codename_redwood_lantern", "v3/owner_redwood_lantern.md", "Iris owns the Redwood Lantern project.", 0.68, rank=2),
                row(batch, "codename_redwood_lantern", "v3/deadline_redwood_lantern.md", "Redwood Lantern checkpoint is due Monday.", 0.6, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "filename_deadline_status_report",
            "query": "What filename should the deadline status report use?",
            "answer": "Current memory indicates: Deadline status report filename should be deadline_status_report.md.",
            "rows": [
                row(batch, "filename_deadline_status_report", "v3/filename_deadline_status_report.md", "Deadline status report filename should be deadline_status_report.md.", 0.92, rank=1),
                row(batch, "filename_deadline_status_report", "v3/deadline_selector_feedback_report.md", "Selector feedback report is due Friday.", 0.7, rank=2),
                row(batch, "filename_deadline_status_report", "v3/owner_selector_feedback_report.md", "Mina owns the selector feedback report draft.", 0.58, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "method_vs_report_filename",
            "query": "What radar method should Victor use?",
            "answer": "Current memory indicates: Weather radar method should use the AccuWeather radar URL.",
            "rows": [
                row(batch, "method_vs_report_filename", "v3/radar_method.md", "Weather radar method should use the AccuWeather radar URL.", 0.9, rank=1),
                row(batch, "method_vs_report_filename", "v3/radar_report_filename.md", "Radar report filename should be accuweather_radar_report.md.", 0.77, rank=2),
                row(batch, "method_vs_report_filename", "v3/radar_color.md", "Radar report color theme should be blue and gray.", 0.53, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "report_filename_vs_method",
            "query": "What radar report filename should be used?",
            "answer": "Current memory indicates: Radar report filename should be accuweather_radar_report.md.",
            "rows": [
                row(batch, "report_filename_vs_method", "v3/radar_report_filename.md", "Radar report filename should be accuweather_radar_report.md.", 0.91, rank=1),
                row(batch, "report_filename_vs_method", "v3/radar_method.md", "Weather radar method should use the AccuWeather radar URL.", 0.75, rank=2),
                row(batch, "report_filename_vs_method", "v3/radar_color.md", "Radar report color theme should be blue and gray.", 0.55, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "drink_preference_correction",
            "query": "What drink does Victor currently prefer?",
            "answer": "Current memory indicates: Correction: Victor currently prefers mint tea, not sparkling water.",
            "rows": [
                row(batch, "drink_preference_correction", "v3/drink_preference_v4.md", "Correction: Victor currently prefers mint tea, not sparkling water.", 0.93, rank=1),
                row(batch, "drink_preference_correction", "v3/drink_preference_v3.md", "Victor currently prefers sparkling water.", 0.58, rank=2),
                row(batch, "drink_preference_correction", "v3/pizza_preference.md", "Victor currently prefers cheese pizza.", 0.48, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "stale", -1.0), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "pizza_preference_correction",
            "query": "What pizza does Victor currently prefer?",
            "answer": "Current memory indicates: Correction: Victor currently prefers margherita pizza, not cheese pizza.",
            "rows": [
                row(batch, "pizza_preference_correction", "v3/pizza_preference_v3.md", "Correction: Victor currently prefers margherita pizza, not cheese pizza.", 0.92, rank=1),
                row(batch, "pizza_preference_correction", "v3/pizza_preference_v2.md", "Victor currently prefers cheese pizza.", 0.57, rank=2),
                row(batch, "pizza_preference_correction", "v3/drink_preference_v4.md", "Victor currently prefers mint tea.", 0.46, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "stale", -1.0), (2, "wrong_domain", -0.8)],
        },
        {
            "id": "owner_calendar_approvals",
            "query": "Who owns calendar change approvals?",
            "answer": "Current memory indicates: Operations agent owns calendar change approvals.",
            "rows": [
                row(batch, "owner_calendar_approvals", "v3/owner_calendar_approvals.md", "Operations agent owns calendar change approvals.", 0.9, rank=1),
                row(batch, "owner_calendar_approvals", "v3/calendar_change_policy.md", "Calendar change policy requires manual approval before moving events.", 0.78, rank=2),
                row(batch, "owner_calendar_approvals", "v3/github_upload_policy.md", "GitHub upload policy requires explicit current-conversation approval.", 0.5, rank=3),
            ],
            "feedback": [(0, "useful", 1.0), (1, "wrong_domain", -0.8), (2, "wrong_domain", -0.8)],
        },
    ]


def existing_batches(path: Path) -> set[str]:
    if not path.exists():
        return set()
    batches = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        batch = request.get("sample_batch")
        if batch:
            batches.add(str(batch))
    return batches


def build_events(batch: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in cases(batch):
        operation_id = stable_id("op", batch, item["id"], "ask")
        created_at = utc_now()
        rows = item["rows"]
        ask_event = {
            "schema_version": 1,
            "operation_id": operation_id,
            "linked_operation_id": None,
            "event_type": "ask",
            "created_at": created_at,
            "payload": {
                "request": {
                    "query": item["query"],
                    "top_k": 10,
                    "namespace": f"agent:{batch}",
                    "include_global": False,
                    "agent_id": "claim-scope-sample-agent",
                    "session_id": batch,
                    "store_session": True,
                    "condition_name": batch,
                    "sample_batch": batch,
                    "sample_case": item["id"],
                },
                "response": {
                    "answer": item["answer"],
                    "confidence": 0.8,
                    "conflict": any(label == "stale" for _index, label, _rating in item["feedback"]),
                    "session_id": batch,
                    "agent_id": "claim-scope-sample-agent",
                    "namespace": f"agent:{batch}",
                    "evidence": [row for row in rows if row.get("rank") == 1],
                    "raw_results": rows,
                    "source_context": [],
                    "stale_context": [row for row in rows if "stale" in row.get("source", "")],
                },
                "selector_snapshot": {
                    "ok": True,
                    "decision": {
                        "policy": "sample_generation",
                        "action": "LOG_TRAINING_EXAMPLE",
                        "reason": "memory_session_claim_scope_sample",
                        "confidence": 1.0,
                    },
                    "diagnostics": {"sample_batch": batch, "sample_case": item["id"]},
                },
            },
        }
        events.append(ask_event)
        for index, label, rating in item["feedback"]:
            target = rows[index]
            feedback_operation_id = stable_id("op", batch, item["id"], target["memory_id"], label)
            feedback_event = {
                "schema_version": 1,
                "operation_id": feedback_operation_id,
                "linked_operation_id": operation_id,
                "event_type": "feedback",
                "created_at": utc_now(),
                "payload": {
                    "request": {
                        "memory_id": target["memory_id"],
                        "label": label,
                        "rating": rating,
                        "query": item["query"],
                        "rank": target.get("rank"),
                        "retrieval_score": target.get("score"),
                        "notes": f"{batch}: {item['id']} synthetic hard-case feedback",
                        "linked_operation_id": operation_id,
                        "sample_batch": batch,
                        "sample_case": item["id"],
                    },
                    "feedback": {
                        "id": stable_id("fb", batch, item["id"], target["memory_id"], label),
                        "memory_id": target["memory_id"],
                        "label": label,
                        "rating": rating,
                        "metadata": {"linked_operation_id": operation_id, "sample_batch": batch},
                        "created_at": utc_now(),
                    },
                },
            }
            events.append(feedback_event)
    return events


def append_events(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Append realistic claim-scope outcome samples to the memory outcome log.")
    parser.add_argument("--batch", default=DEFAULT_BATCH)
    parser.add_argument("--log", default=str(default_log_path()))
    parser.add_argument("--force", action="store_true", help="Append even if this sample batch is already present.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    log_path = Path(args.log)
    batch = str(args.batch)
    if not args.force and batch in existing_batches(log_path):
        print(
            json.dumps(
                {
                    "ok": True,
                    "skipped": True,
                    "reason": "batch_already_present",
                    "batch": batch,
                    "log": str(log_path),
                },
                indent=2,
            )
        )
        return 0

    events = build_events(batch)
    if not args.dry_run:
        append_events(log_path, events)
    print(
        json.dumps(
            {
                "ok": True,
                "skipped": False,
                "dry_run": bool(args.dry_run),
                "batch": batch,
                "log": str(log_path),
                "events": len(events),
                "ask_events": sum(1 for event in events if event["event_type"] == "ask"),
                "feedback_events": sum(1 for event in events if event["event_type"] == "feedback"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
