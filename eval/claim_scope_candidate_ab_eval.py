from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.pipeline import MemoryPipeline  # noqa: E402
from storage.db import MemoryDB  # noqa: E402


SCHEMA_PATH = ROOT / "storage" / "schema.sql"
DEFAULT_CANDIDATES = REPO_ROOT / "experiments" / "claim_scope_alias_candidates.json"
OUT_JSON = REPO_ROOT / "experiments" / "claim_scope_candidate_ab_eval_results.json"
OUT_MD = REPO_ROOT / "experiments" / "claim_scope_candidate_ab_eval_report.md"
CONSERVATIVE_SLOTS = {"backend_port", "filename", "method"}
RISK_PROBE_SLOTS = {"policy"}
SPLIT_OVERLAY_ALIASES = {
    "report_filename": ("filename", "file", "report", "accuweather_radar_report"),
    "github_upload": ("github", "upload", "uploads", "confirmation", "explicitly", "requested", "requests"),
    "calendar_change": ("calendar", "schedule", "change", "changing", "meeting", "events", "manual", "approval"),
    "gcl_curvature": ("gcl", "g-cl", "domain", "geometry", "anchor", "drift", "curvature", "stability"),
    "csd": ("csd", "novelty", "contradiction", "semantic", "density", "domain shift", "detect"),
    "csd_signal": ("csd", "novelty", "contradiction", "semantic", "density", "domain shift", "detect"),
    "deadline": ("deadline", "due", "friday", "deadline_report"),
    "own": ("owner", "owns", "assignment", "assignee", "responsible", "assigned", "accountable", "responsibility"),
    "owner": ("owner", "owns", "assignment", "assignee", "responsible", "assigned", "accountable", "responsibility"),
}
SPLIT_OVERLAY_EXCLUDED_TERMS = {
    "report_filename": ("method", "tool", "weather"),
    "github_upload": ("calendar", "schedule", "meeting"),
    "calendar_change": ("github", "upload", "uploads"),
    "gcl_curvature": ("csd", "backend", "port", "filename", "report"),
    "csd": ("gcl", "g-cl", "backend", "port", "filename", "report"),
    "csd_signal": ("gcl", "g-cl", "backend", "port", "filename", "report"),
    "deadline": ("owner", "owns", "assignee", "assigned", "responsible", "responsibility"),
    "own": ("deadline", "due", "friday"),
    "owner": ("deadline", "due", "friday"),
}


@dataclass(frozen=True)
class MemoryWrite:
    text: str
    source: str
    domain: str = "agent_memory"
    memory_type: str = "semantic_note"
    ref: str | None = None
    target_ref: str | None = None


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    query: str
    target_ref: str
    distractor_refs: tuple[str, ...] = ()
    teaches: list[MemoryWrite] = field(default_factory=list)
    corrections: list[MemoryWrite] = field(default_factory=list)
    should_improve_or_preserve: bool = True
    min_split_target_claim_lift: float = 0.0
    required: bool = True
    notes: str = ""


CASES = [
    EvalCase(
        case_id="method_vs_filename",
        query="What radar method should Victor use?",
        target_ref="radar_method",
        distractor_refs=("radar_filename",),
        notes="Candidate method aliases should not let a report-filename correction overtake the method memory.",
        teaches=[
            MemoryWrite(
                ref="radar_method",
                text="Weather radar method for Victor: use the AccuWeather URL for radar checks.",
                source="sample/radar_method.md",
                memory_type="procedure",
            ),
            MemoryWrite(
                ref="old_filename",
                text="Radar report filename should be canvas_guessing_report.md.",
                source="sample/radar_report_v1.md",
                memory_type="procedure",
            ),
        ],
        corrections=[
            MemoryWrite(
                ref="radar_filename",
                target_ref="old_filename",
                text="Radar report filename should be accuweather_radar_report.md, not canvas_guessing_report.md.",
                source="sample/radar_report_v2.md",
                memory_type="procedure",
            )
        ],
    ),
    EvalCase(
        case_id="filename_vs_method",
        query="What radar report filename should be used?",
        target_ref="radar_filename",
        distractor_refs=("radar_method",),
        notes="A filename slot should keep the filename correction above the general radar method memory.",
        teaches=[
            MemoryWrite(
                ref="radar_method",
                text="Weather radar method for Victor: use the AccuWeather URL for radar checks.",
                source="sample/radar_method.md",
                memory_type="procedure",
            ),
            MemoryWrite(
                ref="old_filename",
                text="Radar report filename should be canvas_guessing_report.md.",
                source="sample/radar_report_v1.md",
                memory_type="procedure",
            ),
        ],
        corrections=[
            MemoryWrite(
                ref="radar_filename",
                target_ref="old_filename",
                text="Radar report filename should be accuweather_radar_report.md, not canvas_guessing_report.md.",
                source="sample/radar_report_v2.md",
                memory_type="procedure",
            )
        ],
    ),
    EvalCase(
        case_id="backend_port_numeric_alias",
        query="What backend port should the memory API use?",
        target_ref="backend_port",
        distractor_refs=("project_status", "radar_filename"),
        notes="The backend_port candidate should help a compact numeric-port memory without pulling in unrelated status or filename memories.",
        teaches=[
            MemoryWrite(
                ref="backend_port",
                text="Memory API should use 8765.",
                source="sample/backend_v2.md",
                memory_type="procedure",
            ),
            MemoryWrite(
                ref="project_status",
                text="Hermes memory project status: outcome logging is ready for linked feedback tests.",
                source="sample/project_status_v3.md",
            ),
            MemoryWrite(
                ref="old_filename",
                text="Radar report filename should be canvas_guessing_report.md.",
                source="sample/radar_report_v1.md",
                memory_type="procedure",
            ),
        ],
        corrections=[
            MemoryWrite(
                ref="radar_filename",
                target_ref="old_filename",
                text="Radar report filename should be accuweather_radar_report.md, not canvas_guessing_report.md.",
                source="sample/radar_report_v2.md",
                memory_type="procedure",
            )
        ],
    ),
    EvalCase(
        case_id="policy_noise_probe",
        query="What calendar policy should Hermes use?",
        target_ref="calendar_policy",
        distractor_refs=("github_upload_rule",),
        should_improve_or_preserve=False,
        notes="Broad policy aliases mined from one GitHub-upload example should be treated as risky for unrelated policy queries.",
        teaches=[
            MemoryWrite(
                ref="calendar_policy",
                text="Hermes calendar policy should use manual approval for schedule changes.",
                source="sample/calendar_policy.md",
                memory_type="procedure",
            ),
            MemoryWrite(
                ref="github_upload_rule",
                text="Victor wants GitHub uploads only when explicitly requested in the current conversation.",
                source="sample/user_rules.md",
                memory_type="preference",
            ),
        ],
    ),
    EvalCase(
        case_id="github_upload_policy_vs_calendar_change",
        query="What is the GitHub upload policy?",
        target_ref="github_upload_rule",
        distractor_refs=("calendar_policy",),
        notes="Split policy keys should let GitHub-upload policy match without lifting calendar-change policy.",
        teaches=[
            MemoryWrite(
                ref="github_upload_rule",
                text="Victor wants GitHub uploads only when explicitly requested in the current conversation.",
                source="sample/github_upload_policy.md",
                memory_type="preference",
            ),
            MemoryWrite(
                ref="calendar_policy",
                text="Hermes calendar change policy requires manual approval before changing schedule events.",
                source="sample/calendar_change_policy.md",
                memory_type="procedure",
            ),
        ],
    ),
    EvalCase(
        case_id="calendar_change_policy_vs_github_upload",
        query="What is the calendar change policy?",
        target_ref="calendar_policy",
        distractor_refs=("github_upload_rule",),
        notes="Split policy keys should let calendar-change policy match without lifting GitHub-upload policy.",
        teaches=[
            MemoryWrite(
                ref="github_upload_rule",
                text="Victor wants GitHub uploads only when explicitly requested in the current conversation.",
                source="sample/github_upload_policy.md",
                memory_type="preference",
            ),
            MemoryWrite(
                ref="calendar_policy",
                text="Hermes calendar change policy requires manual approval before changing schedule events.",
                source="sample/calendar_change_policy.md",
                memory_type="procedure",
            ),
        ],
    ),
    EvalCase(
        case_id="gcl_curvature_vs_csd_signal",
        query="Which GCL curvature mechanism maintains stability?",
        target_ref="gcl_mechanism",
        distractor_refs=("csd_signal",),
        notes="A narrow GCL mechanism key should not pull in CSD signal memories.",
        teaches=[
            MemoryWrite(
                ref="gcl_mechanism",
                text="G-CL maintains domain geometry, anchor drift, curvature, and stability.",
                source="sample/gcl_mechanism.md",
                domain="G-CL",
            ),
            MemoryWrite(
                ref="csd_signal",
                text="CSD helps detect novelty, contradiction pressure, semantic density, and domain shift.",
                source="sample/csd_signal.md",
                domain="CSD",
            ),
        ],
    ),
    EvalCase(
        case_id="csd_signal_vs_gcl_curvature",
        query="Which CSD signal helps detect semantic density?",
        target_ref="csd_signal",
        distractor_refs=("gcl_mechanism",),
        notes="A narrow CSD signal key should not pull in GCL mechanism memories.",
        teaches=[
            MemoryWrite(
                ref="gcl_mechanism",
                text="G-CL maintains domain geometry, anchor drift, curvature, and stability.",
                source="sample/gcl_mechanism.md",
                domain="G-CL",
            ),
            MemoryWrite(
                ref="csd_signal",
                text="CSD helps detect novelty, contradiction pressure, semantic density, and domain shift.",
                source="sample/csd_signal.md",
                domain="CSD",
            ),
        ],
    ),
    EvalCase(
        case_id="deadline_vs_owner",
        query="When is the selector feedback report due?",
        target_ref="deadline",
        distractor_refs=("owner",),
        notes="Deadline aliases should not lift report-owner memories.",
        teaches=[
            MemoryWrite(
                ref="deadline",
                text="The selector feedback report is due Friday.",
                source="sample/deadline_report.md",
            ),
            MemoryWrite(
                ref="owner",
                text="Mina owns the selector feedback report draft.",
                source="sample/report_owner.md",
            ),
        ],
    ),
    EvalCase(
        case_id="owner_vs_deadline",
        query="Who owns the selector feedback report?",
        target_ref="owner",
        distractor_refs=("deadline",),
        notes="Owner aliases should not lift deadline memories.",
        teaches=[
            MemoryWrite(
                ref="deadline",
                text="The selector feedback report is due Friday.",
                source="sample/deadline_report.md",
            ),
            MemoryWrite(
                ref="owner",
                text="Mina owns the selector feedback report draft.",
                source="sample/report_owner.md",
            ),
        ],
    ),
    EvalCase(
        case_id="github_upload_alias_rescue",
        query="What GitHub upload rule should Hermes follow?",
        target_ref="github_upload_rule",
        distractor_refs=("calendar_policy",),
        min_split_target_claim_lift=0.25,
        notes="Target omits GitHub/upload wording; split aliases should rescue it through requested/confirmation terms.",
        teaches=[
            MemoryWrite(
                ref="github_upload_rule",
                text="Only proceed after explicit confirmation in the current conversation.",
                source="sample/user_rules.md",
                memory_type="preference",
            ),
            MemoryWrite(
                ref="calendar_policy",
                text="Calendar upload schedule changes require manual approval before changing events.",
                source="sample/calendar_change_policy.md",
                memory_type="procedure",
            ),
        ],
    ),
    EvalCase(
        case_id="calendar_change_alias_rescue",
        query="What calendar change rule should Hermes follow?",
        target_ref="calendar_policy",
        distractor_refs=("github_upload_rule",),
        min_split_target_claim_lift=0.25,
        notes="Target omits calendar/change wording; split aliases should rescue it through manual approval and meeting-event terms.",
        teaches=[
            MemoryWrite(
                ref="calendar_policy",
                text="Manual approval is required before adjusting meeting events.",
                source="sample/schedule_rules.md",
                memory_type="procedure",
            ),
            MemoryWrite(
                ref="github_upload_rule",
                text="GitHub upload requests require explicit confirmation in the current conversation.",
                source="sample/github_upload_policy.md",
                memory_type="preference",
            ),
        ],
    ),
    EvalCase(
        case_id="gcl_curvature_alias_rescue",
        query="Which GCL curvature mechanism should Hermes remember?",
        target_ref="gcl_mechanism",
        distractor_refs=("csd_signal",),
        min_split_target_claim_lift=0.25,
        notes="Target omits GCL/curvature wording; split aliases should rescue it through geometry/drift/stability terms.",
        teaches=[
            MemoryWrite(
                ref="gcl_mechanism",
                text="Domain geometry, anchor drift, and stability are maintained together.",
                source="sample/mechanism_memory.md",
                domain="G-CL",
            ),
            MemoryWrite(
                ref="csd_signal",
                text="CSD detects novelty, contradiction pressure, and semantic density.",
                source="sample/csd_signal.md",
                domain="CSD",
            ),
        ],
    ),
    EvalCase(
        case_id="csd_signal_alias_rescue",
        query="Which CSD signal?",
        target_ref="csd_signal",
        distractor_refs=("gcl_mechanism",),
        min_split_target_claim_lift=0.25,
        notes="Target omits CSD/signal wording; split aliases should rescue it through novelty/contradiction/density terms.",
        teaches=[
            MemoryWrite(
                ref="gcl_mechanism",
                text="G-CL maintains domain geometry, anchor drift, curvature, and stability.",
                source="sample/gcl_mechanism.md",
                domain="G-CL",
            ),
            MemoryWrite(
                ref="csd_signal",
                text="Novelty pressure, density, and domain shift diagnostics.",
                source="sample/diagnostics.md",
                domain="CSD",
            ),
        ],
    ),
    EvalCase(
        case_id="deadline_alias_rescue",
        query="What deadline should Hermes remember?",
        target_ref="deadline",
        distractor_refs=("owner",),
        min_split_target_claim_lift=0.25,
        notes="Target omits deadline wording; split aliases should rescue it through due/Friday/report terms.",
        teaches=[
            MemoryWrite(
                ref="deadline",
                text="The selector feedback report is due Friday.",
                source="sample/feedback_report.md",
            ),
            MemoryWrite(
                ref="owner",
                text="Mina owns the selector feedback report draft.",
                source="sample/report_owner.md",
            ),
        ],
    ),
    EvalCase(
        case_id="owner_alias_rescue",
        query="Who is the owner of the report?",
        target_ref="owner",
        distractor_refs=("deadline",),
        min_split_target_claim_lift=0.25,
        notes="Target omits owns/owner wording; split aliases should rescue it through relation-style assignment terms.",
        teaches=[
            MemoryWrite(
                ref="deadline",
                text="The report is due Friday.",
                source="sample/report_deadline.md",
            ),
            MemoryWrite(
                ref="owner",
                text="Mina has the assignment.",
                source="sample/report_assignment.md",
            ),
        ],
    ),
]


def init_pipeline(tmp: Path, case_id: str, claim_scope_config: dict[str, Any]) -> MemoryPipeline:
    db_path = tmp / f"{case_id}.db"
    db = MemoryDB(db_path)
    db.init_schema(SCHEMA_PATH)
    db.close()
    return MemoryPipeline(
        root=ROOT,
        db_path=db_path,
        embedding_config={"backend": "hash", "dim": 128},
        claim_scope_config=claim_scope_config,
    )


def term_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    raw = str(value or "")
    for separator in ("|", ";"):
        raw = raw.replace(separator, ",")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def merge_candidate_overlay(
    base: dict[str, Any],
    candidate_report: dict[str, Any],
    *,
    slots: set[str],
) -> dict[str, Any]:
    out = json.loads(json.dumps(base or {}))
    aliases = dict(out.get("slot_aliases") or out.get("aliases") or {})
    excluded = dict(out.get("excluded_terms") or out.get("exclusions") or {})
    for candidate in candidate_report.get("candidates") or []:
        slot = str(candidate.get("slot") or "").strip().lower()
        if slot not in slots:
            continue
        existing_aliases = term_list(aliases.get(slot))
        for alias in term_list(candidate.get("aliases")):
            if alias not in existing_aliases:
                existing_aliases.append(alias)
        if existing_aliases:
            aliases[slot] = existing_aliases
        existing_excluded = term_list(excluded.get(slot))
        for term in term_list(candidate.get("excluded_terms")):
            if term not in existing_excluded:
                existing_excluded.append(term)
        if existing_excluded:
            excluded[slot] = existing_excluded
    out["slot_aliases"] = aliases
    out["excluded_terms"] = excluded
    return out


def merge_static_overlay(
    base: dict[str, Any],
    *,
    aliases_overlay: dict[str, tuple[str, ...]],
    excluded_overlay: dict[str, tuple[str, ...]],
) -> dict[str, Any]:
    out = json.loads(json.dumps(base or {}))
    aliases = dict(out.get("slot_aliases") or out.get("aliases") or {})
    excluded = dict(out.get("excluded_terms") or out.get("exclusions") or {})
    for slot, terms in aliases_overlay.items():
        existing_aliases = term_list(aliases.get(slot))
        for term in terms:
            normalized = str(term).strip().lower()
            if normalized and normalized not in existing_aliases:
                existing_aliases.append(normalized)
        if existing_aliases:
            aliases[slot] = existing_aliases
    for slot, terms in excluded_overlay.items():
        existing_excluded = term_list(excluded.get(slot))
        for term in terms:
            normalized = str(term).strip().lower()
            if normalized and normalized not in existing_excluded:
                existing_excluded.append(normalized)
        if existing_excluded:
            excluded[slot] = existing_excluded
    out["slot_aliases"] = aliases
    out["excluded_terms"] = excluded
    return out


def run_case(case: EvalCase, claim_scope_config: dict[str, Any], label: str) -> dict[str, Any]:
    namespace = f"claim_scope_candidate_ab_{case.case_id}_{label}"
    refs: dict[str, str] = {}
    with TemporaryDirectory() as raw_tmp:
        pipeline = init_pipeline(Path(raw_tmp), f"{case.case_id}_{label}", claim_scope_config)
        try:
            for write in case.teaches:
                result = pipeline.teach(
                    write.text,
                    source=write.source,
                    namespace=namespace,
                    agent_id="claim_scope_candidate_ab_eval",
                    store_session=False,
                    domain=write.domain,
                    memory_type=write.memory_type,
                )
                if write.ref:
                    refs[write.ref] = result["memory"]["memory_id"]
            for write in case.corrections:
                target_ids = [refs[write.target_ref]] if write.target_ref and write.target_ref in refs else []
                result = pipeline.correct(
                    write.text,
                    target_memory_ids=target_ids,
                    target_query=case.query,
                    top_k=8,
                    source=write.source,
                    namespace=namespace,
                    agent_id="claim_scope_candidate_ab_eval",
                    store_session=False,
                    relation_type="corrects",
                    domain=write.domain,
                    memory_type=write.memory_type,
                )
                if write.ref:
                    refs[write.ref] = result["correction_memory"]["memory_id"]
            rows = pipeline.retrieve(case.query, top_k=8, namespace=namespace, include_global=False)
        finally:
            pipeline.close()

    rank_by_ref = {}
    row_by_ref = {}
    id_to_ref = {memory_id: ref for ref, memory_id in refs.items()}
    for index, row in enumerate(rows, start=1):
        ref = id_to_ref.get(row["memory_id"])
        if ref:
            rank_by_ref[ref] = index
            row_by_ref[ref] = row
    target_rank = rank_by_ref.get(case.target_ref, 999)
    distractor_ranks = {ref: rank_by_ref.get(ref, 999) for ref in case.distractor_refs}
    nearest_distractor_rank = min(distror_rank for distror_rank in distractor_ranks.values()) if distractor_ranks else 999
    margin = nearest_distractor_rank - target_rank
    return {
        "label": label,
        "target_rank": target_rank,
        "nearest_distractor_rank": nearest_distractor_rank,
        "rank_margin": margin,
        "target_claim_scope_score": row_by_ref.get(case.target_ref, {}).get("claim_scope_score"),
        "distractor_claim_scope_scores": {
            ref: row_by_ref.get(ref, {}).get("claim_scope_score") for ref in case.distractor_refs
        },
        "distractor_ranks": distractor_ranks,
        "retrieved": [
            {
                "rank": idx,
                "ref": id_to_ref.get(row["memory_id"]),
                "source": row["source"],
                "score": row["score"],
                "claim_scope_score": row["claim_scope_score"],
                "authority_state": row["authority_state"],
                "text": row["text"],
            }
            for idx, row in enumerate(rows, start=1)
        ],
    }


def distractor_claim_lift(before: dict[str, Any], after: dict[str, Any], refs: tuple[str, ...]) -> float:
    return max(
        (
            float(after["distractor_claim_scope_scores"].get(ref) or 0.0)
            - float(before["distractor_claim_scope_scores"].get(ref) or 0.0)
            for ref in refs
        ),
        default=0.0,
    )


def candidate_for_slot(candidate_report: dict[str, Any], slot: str) -> dict[str, Any] | None:
    wanted = slot.strip().lower()
    for candidate in candidate_report.get("candidates") or []:
        if str(candidate.get("slot") or "").strip().lower() == wanted:
            return candidate
    return None


def active_split_overlay(
    candidate_report: dict[str, Any],
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    aliases = dict(SPLIT_OVERLAY_ALIASES)
    excluded = dict(SPLIT_OVERLAY_EXCLUDED_TERMS)
    method_candidate = candidate_for_slot(candidate_report, "method")
    method_exclusions = set(term_list((method_candidate or {}).get("excluded_terms")))
    if not (method_exclusions & {"filename", "report", "accuweather_radar_report"}):
        aliases.pop("report_filename", None)
        excluded.pop("report_filename", None)
    return aliases, excluded


def active_conservative_slots(candidate_report: dict[str, Any]) -> set[str]:
    active = {"backend_port"}
    method_candidate = candidate_for_slot(candidate_report, "method")
    method_exclusions = set(term_list((method_candidate or {}).get("excluded_terms")))
    if method_exclusions & {"filename", "report", "accuweather_radar_report"}:
        active.add("method")
    filename_candidate = candidate_for_slot(candidate_report, "filename")
    filename_exclusions = set(term_list((filename_candidate or {}).get("excluded_terms")))
    if filename_exclusions & {"method", "tool", "weather", "accuweather"}:
        active.add("filename")
    return active


def evaluate(candidate_path: Path) -> dict[str, Any]:
    config = load_config(ROOT)
    baseline_config = dict(config.get("claim_scope") or {})
    candidate_report = json.loads(candidate_path.read_text(encoding="utf-8"))
    conservative_slots = active_conservative_slots(candidate_report)
    conservative_config = merge_candidate_overlay(
        baseline_config,
        candidate_report,
        slots=conservative_slots,
    )
    broad_config = merge_candidate_overlay(
        baseline_config,
        candidate_report,
        slots=conservative_slots | RISK_PROBE_SLOTS,
    )
    split_aliases, split_excluded = active_split_overlay(candidate_report)
    split_config = merge_static_overlay(
        conservative_config,
        aliases_overlay=split_aliases,
        excluded_overlay=split_excluded,
    )

    cases = []
    failures = []
    for case in CASES:
        baseline = run_case(case, baseline_config, "baseline")
        conservative = run_case(case, conservative_config, "conservative")
        split = run_case(case, split_config, "split_narrow")
        broad = run_case(case, broad_config, "broad_risk_probe")
        preserved = conservative["rank_margin"] >= baseline["rank_margin"]
        target_first = conservative["target_rank"] < conservative["nearest_distractor_rank"]
        split_preserved = split["rank_margin"] >= baseline["rank_margin"]
        split_target_first = split["target_rank"] < split["nearest_distractor_rank"]
        split_target_claim_lift = float(split["target_claim_scope_score"] or 0.0) - float(
            baseline["target_claim_scope_score"] or 0.0
        )
        split_distractor_claim_lift = distractor_claim_lift(baseline, split, case.distractor_refs)
        broad_distractor_claim_lift = distractor_claim_lift(baseline, broad, case.distractor_refs)
        broad_degraded = broad["rank_margin"] < baseline["rank_margin"] or broad_distractor_claim_lift >= 0.25
        if case.should_improve_or_preserve:
            if case.min_split_target_claim_lift > 0.0:
                passed = (
                    split_target_first
                    and (
                        split_target_claim_lift >= case.min_split_target_claim_lift
                        or float(split["target_claim_scope_score"] or 0.0) >= case.min_split_target_claim_lift
                    )
                    and split_distractor_claim_lift < 0.25
                )
            else:
                passed = (
                    preserved
                    and target_first
                    and split_preserved
                    and split_target_first
                    and split_distractor_claim_lift < 0.25
                )
            if not passed:
                if case.required:
                    failures.append(case.case_id)
        else:
            passed = True
        cases.append(
            {
                "case_id": case.case_id,
                "query": case.query,
                "notes": case.notes,
                "target_ref": case.target_ref,
                "distractor_refs": list(case.distractor_refs),
                "should_improve_or_preserve": case.should_improve_or_preserve,
                "required": case.required,
                "passed": passed,
                "conservative_preserved_or_improved": preserved,
                "conservative_target_first": target_first,
                "split_preserved_or_improved": split_preserved,
                "split_target_first": split_target_first,
                "min_split_target_claim_lift": case.min_split_target_claim_lift,
                "split_target_claim_lift": round(split_target_claim_lift, 6),
                "split_distractor_claim_lift": round(split_distractor_claim_lift, 6),
                "broad_distractor_claim_lift": round(broad_distractor_claim_lift, 6),
                "broad_degraded": broad_degraded,
                "baseline": baseline,
                "conservative": conservative,
                "split_narrow": split,
                "broad_risk_probe": broad,
            }
        )

    useful_slots = sorted(conservative_slots)
    risky_slots = sorted(
        {
            slot
            for slot in RISK_PROBE_SLOTS
            if any(case["broad_degraded"] and case["case_id"] == "policy_noise_probe" for case in cases)
        }
    )
    return {
        "ok": not failures,
        "candidate_path": str(candidate_path),
        "conservative_slots": useful_slots,
        "split_overlay_slots": sorted(split_aliases),
        "risk_probe_slots": sorted(RISK_PROBE_SLOTS),
        "risky_slots_detected": risky_slots,
        "case_count": len(cases),
        "failures": failures,
        "cases": cases,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Claim Scope Candidate A/B Eval",
        "",
        f"Passed: **{report['ok']}**",
        f"Candidate file: `{report['candidate_path']}`",
        f"Conservative slots: `{', '.join(report['conservative_slots'])}`",
        f"Split-overlay slots: `{', '.join(report['split_overlay_slots'])}`",
        f"Risk-probe slots: `{', '.join(report['risk_probe_slots'])}`",
        f"Risky slots detected: `{', '.join(report['risky_slots_detected']) or 'none'}`",
        "",
        "| case | baseline margin | conservative margin | split margin | split target lift | split distractor lift | broad margin | broad claim lift | pass |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for case in report["cases"]:
        lines.append(
            f"| `{case['case_id']}` | {case['baseline']['rank_margin']} | "
            f"{case['conservative']['rank_margin']} | {case['split_narrow']['rank_margin']} | "
            f"{case['split_target_claim_lift']:.6f} | {case['split_distractor_claim_lift']:.6f} | "
            f"{case['broad_risk_probe']['rank_margin']} | "
            f"{case['broad_distractor_claim_lift']:.6f} | {case['passed']} |"
        )
    lines.extend(["", "## Case Details", ""])
    for case in report["cases"]:
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"Query: `{case['query']}`",
                f"Notes: {case['notes']}",
                "",
                "| variant | target rank | nearest distractor rank | margin | target claim-scope |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for key in ("baseline", "conservative", "split_narrow", "broad_risk_probe"):
            variant = case[key]
            claim_score = variant["target_claim_scope_score"]
            claim_text = "n/a" if claim_score is None else f"{claim_score:.6f}"
            lines.append(
                f"| `{key}` | {variant['target_rank']} | {variant['nearest_distractor_rank']} | "
                f"{variant['rank_margin']} | {claim_text} |"
            )
        lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B validate mined claim-scope alias candidates.")
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    candidate_path = Path(args.candidates)
    if not candidate_path.exists():
        raise FileNotFoundError(f"Candidate file not found: {candidate_path}")
    report = evaluate(candidate_path)
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "case_count": report["case_count"],
                "conservative_slots": report["conservative_slots"],
                "split_overlay_slots": report["split_overlay_slots"],
                "risk_probe_slots": report["risk_probe_slots"],
                "risky_slots_detected": report["risky_slots_detected"],
                "failures": report["failures"],
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
