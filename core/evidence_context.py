from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def selected_evidence(evidence: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [row for row in (evidence or []) if isinstance(row, dict)]


def resolver_actions(resolver_shadow: dict[str, Any] | None) -> set[str]:
    if not isinstance(resolver_shadow, dict):
        return set()
    return {str(item or "").strip() for item in resolver_shadow.get("actions") or [] if str(item or "").strip()}


def contains_any(text: str, terms: list[str] | tuple[str, ...]) -> bool:
    normalized = normalize_text(text)
    return any(term and term in normalized for term in terms)


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def max_row_signal(rows: list[dict[str, Any]], key: str) -> float:
    return max((float_value(row.get(key), 0.0) for row in rows if isinstance(row, dict)), default=0.0)


@dataclass(frozen=True)
class EvidenceRowState:
    """Shared interpretation of one retrieval/evidence row."""

    authority_state: str
    score: float
    supersession_score: float
    relation_supersession_score: float
    text_match_score: float
    claim_scope_score: float
    answer_type_score: float
    intent_match_score: float
    correction_relevance_score: float
    feedback_score: float
    summary_relation_score: float
    explicit_current: bool
    is_stale: bool
    is_current: bool

    @property
    def is_standalone(self) -> bool:
        return not self.is_stale and not self.is_current

    @property
    def is_topical_anchor(self) -> bool:
        return self.authority_state in {"standalone", "unknown", ""}


def retrieval_row_state(row: dict[str, Any]) -> EvidenceRowState:
    authority_state = normalize_text(row.get("authority_state"))
    score = float_value(row.get("score", row.get("cosine")), 0.0)
    supersession = float_value(row.get("supersession_score"), 0.0)
    relation = float_value(row.get("relation_supersession_score"), 0.0)
    text_match = float_value(row.get("text_match_score"), 0.0)
    claim_match = float_value(row.get("claim_scope_score", row.get("text_match_score")), 0.0)
    answer_type = float_value(row.get("answer_type_score"), 0.0)
    intent_match = float_value(row.get("intent_match_score"), 0.0)
    correction_relevance = float_value(row.get("correction_relevance_score"), 1.0)
    feedback = float_value(row.get("feedback_score"), 0.0)
    summary_relation = float_value(row.get("summary_relation_score"), 0.0)
    explicit_current = authority_state in {"authoritative", "current"} or bool(row.get("supersedes_memory_ids"))
    is_stale = (
        authority_state in {"superseded", "stale"}
        or bool(row.get("superseded_by_memory_ids"))
        or supersession < -0.05
        or relation < -0.05
    )
    is_current = explicit_current or supersession > 0.05 or relation > 0.05
    return EvidenceRowState(
        authority_state=authority_state,
        score=score,
        supersession_score=supersession,
        relation_supersession_score=relation,
        text_match_score=text_match,
        claim_scope_score=claim_match,
        answer_type_score=answer_type,
        intent_match_score=intent_match,
        correction_relevance_score=correction_relevance,
        feedback_score=feedback,
        summary_relation_score=summary_relation,
        explicit_current=explicit_current,
        is_stale=is_stale,
        is_current=is_current,
    )


def diagnostics_from_selector_snapshot(selector_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = selector_snapshot if isinstance(selector_snapshot, dict) else {}
    value = snapshot.get("diagnostics")
    return value if isinstance(value, dict) else {}


def ordinary_fact_lookup(
    query: str,
    *,
    diagnostics: dict[str, Any] | None = None,
    resolver_shadow: dict[str, Any] | None = None,
    selector_snapshot: dict[str, Any] | None = None,
) -> bool:
    resolver_diagnostics = resolver_shadow.get("diagnostics") if isinstance(resolver_shadow, dict) else {}
    if isinstance(resolver_diagnostics, dict) and resolver_diagnostics.get("ordinary_fact_lookup") is True:
        return True

    diag = diagnostics if isinstance(diagnostics, dict) else diagnostics_from_selector_snapshot(selector_snapshot)
    if normalize_text(diag.get("ogcf_intent")) == "ordinary_fact_lookup":
        return True

    text = normalize_text(query)
    ordinary_terms = (
        "when is",
        "what is",
        "what was",
        "what is the calendar",
        "where is",
        "where does",
        "calendar",
        "scheduled",
        "meeting",
        "location",
    )
    return any(term in text for term in ordinary_terms)


def authority_states(evidence: list[dict[str, Any]] | None) -> set[str]:
    return {normalize_text(row.get("authority_state") or row.get("memory_state")) for row in selected_evidence(evidence)}


def stale_conflict_present(
    *,
    evidence: list[dict[str, Any]] | None,
    stale_context: list[dict[str, Any]] | None = None,
    diagnostics: dict[str, Any] | None = None,
    selector_snapshot: dict[str, Any] | None = None,
    conflict: bool = False,
) -> bool:
    diag = diagnostics if isinstance(diagnostics, dict) else diagnostics_from_selector_snapshot(selector_snapshot)
    if float_value(diag.get("stale_current_conflict"), 0.0) > 0.0:
        return True
    if conflict and stale_context:
        return True
    states = authority_states(evidence)
    return "current" in states and "stale" in states


@dataclass(frozen=True)
class EvidenceContextSummary:
    """Shared compact evidence view for report-only controllers and future learned scorers."""

    query: str
    answer: str
    query_text: str
    answer_text: str
    selected_evidence: list[dict[str, Any]]
    stale_context: list[dict[str, Any]]
    retrieval_context: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    resolver_actions: set[str]
    ordinary_fact_lookup: bool
    stale_conflict_present: bool

    @property
    def selected_count(self) -> int:
        return len(self.selected_evidence)

    @property
    def stale_context_count(self) -> int:
        return len(self.stale_context)

    def max_retrieval_signal(self, key: str) -> float:
        return max_row_signal(self.retrieval_context, key)

    def max_selected_signal(self, key: str) -> float:
        return max_row_signal(self.selected_evidence, key)

    def contains_query_term(self, terms: list[str] | tuple[str, ...]) -> bool:
        return contains_any(self.query_text, terms)


@dataclass(frozen=True)
class EvidenceContextFeatures:
    """Compact derived evidence features for symbolic and future learned controllers."""

    retrieval_count: int
    selected_count: int
    stale_context_count: int
    top_score: float
    claim_scope_score: float
    answer_type_score: float
    scope_deflection_penalty: float
    selected_top_score: float
    selected_claim_scope_score: float
    selected_answer_type_score: float
    selected_text_match_score: float
    selected_intent_match_score: float
    memory_bad_rate: float
    stale_current_conflict: float
    contradiction_peak: float
    ogcf_bridge_overload_score: float
    ogcf_effective_affected_memory_ratio: float
    ogcf_structural_pressure: float
    ogcf_omega_norm: float
    ogcf_core_halo_score: float
    ogcf_core_halo_slope: float
    ogcf_projector_graph_anomaly: float


def build_evidence_context_features(
    summary: EvidenceContextSummary,
    *,
    fallback_features: dict[str, Any] | None = None,
) -> EvidenceContextFeatures:
    diagnostics = summary.diagnostics if isinstance(summary.diagnostics, dict) else {}
    fallback = fallback_features if isinstance(fallback_features, dict) else {}
    return EvidenceContextFeatures(
        retrieval_count=len(summary.retrieval_context),
        selected_count=summary.selected_count,
        stale_context_count=summary.stale_context_count,
        top_score=summary.max_retrieval_signal("score"),
        claim_scope_score=summary.max_retrieval_signal("claim_scope_score"),
        answer_type_score=summary.max_retrieval_signal("answer_type_score"),
        scope_deflection_penalty=summary.max_retrieval_signal("scope_deflection_penalty"),
        selected_top_score=summary.max_selected_signal("score"),
        selected_claim_scope_score=summary.max_selected_signal("claim_scope_score"),
        selected_answer_type_score=summary.max_selected_signal("answer_type_score"),
        selected_text_match_score=summary.max_selected_signal("text_match_score"),
        selected_intent_match_score=summary.max_selected_signal("intent_match_score"),
        memory_bad_rate=float_value(diagnostics.get("memory_bad_rate"), float_value(fallback.get("memory_bad_rate"), 0.18)),
        stale_current_conflict=float_value(diagnostics.get("stale_current_conflict"), 0.0),
        contradiction_peak=float_value(diagnostics.get("contradiction_peak"), 0.0),
        ogcf_bridge_overload_score=float_value(diagnostics.get("ogcf_bridge_overload_score"), 0.0),
        ogcf_effective_affected_memory_ratio=float_value(
            diagnostics.get("ogcf_effective_affected_memory_ratio"),
            0.0,
        ),
        ogcf_structural_pressure=float_value(
            diagnostics.get("ogcf_structural_pressure"),
            float_value(diagnostics.get("ogcf_bridge_overload_score"), 0.0)
            * float_value(diagnostics.get("ogcf_effective_affected_memory_ratio"), 0.0),
        ),
        ogcf_omega_norm=float_value(diagnostics.get("ogcf_omega_norm"), 0.0),
        ogcf_core_halo_score=float_value(diagnostics.get("ogcf_core_halo_score"), 0.0),
        ogcf_core_halo_slope=float_value(diagnostics.get("ogcf_core_halo_slope"), 0.0),
        ogcf_projector_graph_anomaly=float_value(diagnostics.get("ogcf_projector_graph_anomaly"), 0.0),
    )


def evidence_context_features_dict(features: EvidenceContextFeatures) -> dict[str, Any]:
    return asdict(features)


def build_evidence_context_summary(
    *,
    query: str,
    answer: str = "",
    evidence: list[dict[str, Any]] | None = None,
    stale_context: list[dict[str, Any]] | None = None,
    retrieval_context: list[dict[str, Any]] | None = None,
    diagnostics: dict[str, Any] | None = None,
    resolver_shadow: dict[str, Any] | None = None,
    selector_snapshot: dict[str, Any] | None = None,
    conflict: bool = False,
) -> EvidenceContextSummary:
    diag = diagnostics if isinstance(diagnostics, dict) else diagnostics_from_selector_snapshot(selector_snapshot)
    selected = selected_evidence(evidence)
    stale_rows = selected_evidence(stale_context)
    retrieval_rows = selected_evidence(retrieval_context)
    ordinary = ordinary_fact_lookup(
        query,
        diagnostics=diag,
        resolver_shadow=resolver_shadow,
        selector_snapshot=selector_snapshot,
    )
    stale_present = stale_conflict_present(
        evidence=selected,
        stale_context=stale_rows,
        diagnostics=diag,
        selector_snapshot=selector_snapshot,
        conflict=conflict,
    )
    return EvidenceContextSummary(
        query=str(query or ""),
        answer=str(answer or ""),
        query_text=normalize_text(query),
        answer_text=normalize_text(answer),
        selected_evidence=selected,
        stale_context=stale_rows,
        retrieval_context=retrieval_rows,
        diagnostics=dict(diag),
        resolver_actions=resolver_actions(resolver_shadow),
        ordinary_fact_lookup=ordinary,
        stale_conflict_present=stale_present,
    )
