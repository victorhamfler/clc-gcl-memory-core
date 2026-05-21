from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_INTENT_LABELS = {
    "work": ("working on", "work on", "project", "building", "developing", "development"),
    "presentation": (
        "information presented",
        "presented",
        "presentation",
        "transparency",
        "honesty",
        "source clarity",
        "sources",
        "vague authority",
        "conclusions without source",
    ),
    "food_drink": ("drink", "drinks", "coffee", "espresso", "tea", "eat", "eats", "pizza", "food"),
    "preference": ("preference", "prefer", "likes", "loves", "hates", "dislikes", "values", "wants"),
}

DEFAULT_CLAIM_SCOPE_STOPWORDS = (
    "about",
    "check",
    "checks",
    "current",
    "currently",
    "does",
    "for",
    "from",
    "help",
    "helps",
    "latest",
    "prefer",
    "prefers",
    "preference",
    "remember",
    "should",
    "that",
    "the",
    "use",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "victor",
    "hermes",
    "project",
)

DEFAULT_CLAIM_SCOPE_ALIASES = {
    "drink": ("drink", "water", "sparkling", "espresso", "tea", "coffee", "beverage"),
    "pizza": ("pizza", "cheese", "mushroom", "pepperoni"),
    "method": ("method", "tool", "url", "accuweather", "radar", "checks"),
    "codename": ("codename", "cedar", "alpha"),
    "status": ("status", "stable", "blocked", "ready"),
    "backend_port": ("backend", "port", "8765"),
    "github_upload": ("github", "upload", "uploads", "confirmation", "explicitly", "requested", "requests"),
    "calendar_change": ("calendar", "schedule", "change", "changing", "meeting", "events", "manual", "approval"),
    "gcl_curvature": ("gcl", "g-cl", "domain", "geometry", "anchor", "drift", "curvature", "stability"),
    "csd": ("csd", "novelty", "contradiction", "semantic", "density", "domain shift", "detect"),
    "deadline": ("deadline", "due", "friday", "deadline_report"),
}

DEFAULT_CLAIM_SCOPE_EXCLUDED_TERMS = {
    "method": ("filename",),
    "backend_port": ("host", "remain", "127", "local", "testing"),
    "github_upload": ("calendar", "schedule", "meeting"),
    "calendar_change": ("github", "upload", "uploads"),
    "gcl_curvature": ("csd", "backend", "port", "filename", "report"),
    "csd": ("gcl", "g-cl", "backend", "port", "filename", "report"),
    "deadline": ("owner", "owns", "mina", "filename", "file"),
}

DEFAULT_ANSWER_TYPE_RULES = {
    "owner_relation": {
        "query_terms": (
            "owner",
            "owners",
            "owns",
            "assignee",
            "assigned",
            "assignment",
            "responsible",
            "accountable",
            "responsibility",
        ),
        "positive_terms": (
            "owner",
            "owners",
            "owns",
            "owned",
            "assignee",
            "assigned",
            "assignment",
            "responsible",
            "accountable",
            "responsibility",
        ),
        "negative_terms": (
            "deadline",
            "due",
            "friday",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "saturday",
            "sunday",
            "today",
            "tomorrow",
        ),
        "query_requires_any": (),
        "positive_requires_any": (),
        "negative_requires_absent": (),
        "positive_score": 1.0,
        "negative_score": -1.0,
    },
    "deadline": {
        "query_terms": ("deadline", "due"),
        "positive_terms": (
            "due",
            "friday",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "saturday",
            "sunday",
            "today",
            "tomorrow",
        ),
        "negative_terms": (
            "owner",
            "owners",
            "owns",
            "owned",
            "assignee",
            "assigned",
            "assignment",
            "responsible",
            "accountable",
            "responsibility",
        ),
        "query_requires_any": (),
        "positive_requires_any": (),
        "negative_requires_absent": (
            "due",
            "friday",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "saturday",
            "sunday",
            "today",
            "tomorrow",
        ),
        "positive_score": 1.0,
        "negative_score": -1.0,
    },
}

DEFAULT_RETRIEVAL_SIGNAL_CONFIG = {
    "broad_generic": {
        "source_contains": ("broad_policy", "general_policy"),
        "text_prefixes": ("broad policy note", "general policy note"),
        "penalty": 0.18,
    },
    "scope_deflection": {
        "query_terms": (
            "policy",
            "permission",
            "approval",
            "approve",
            "upload",
            "github",
            "repo",
            "publish",
            "calendar",
            "meeting",
            "event",
            "change",
            "changing",
            "reschedule",
        ),
        "correction_prefixes": ("correction:",),
        "text_markers": (
            "not permission",
            "not upload permission",
            "not authorized",
            "not authorize",
            "do not authorize",
            "does not authorize",
            "separate policy",
            "separate calendar policy",
            "still follows the separate",
        ),
        "penalty": 0.55,
    },
    "correction_relevance": {
        "match_threshold": 0.75,
        "min_relevance": 0.15,
    },
}


def configured_intent_terms(symbolic_config: dict[str, Any] | None = None) -> dict[str, tuple[str, ...]]:
    configured = parse_intent_labels((symbolic_config or {}).get("intent_labels"))
    out = dict(DEFAULT_INTENT_LABELS)
    out.update(configured)
    return out


def parse_intent_labels(value: Any) -> dict[str, tuple[str, ...]]:
    if isinstance(value, dict):
        return {
            str(label).strip(): tuple(str(term).strip().lower() for term in terms if str(term).strip())
            for label, terms in value.items()
            if str(label).strip() and isinstance(terms, (list, tuple, set))
        }
    out: dict[str, tuple[str, ...]] = {}
    for group in str(value or "").split(";"):
        if "=" not in group:
            continue
        label, raw_terms = group.split("=", 1)
        terms = tuple(term.strip().lower() for term in raw_terms.split("|") if term.strip())
        if label.strip() and terms:
            out[label.strip()] = terms
    return out


def parse_term_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(term).strip().lower() for term in value if str(term).strip())
    raw = str(value or "")
    for separator in ("|", ";"):
        raw = raw.replace(separator, ",")
    return tuple(term.strip().lower() for term in raw.split(",") if term.strip())


def parse_term_map(value: Any) -> dict[str, tuple[str, ...]]:
    if isinstance(value, dict):
        return {
            str(label).strip().lower(): parse_term_sequence(terms)
            for label, terms in value.items()
            if str(label).strip() and parse_term_sequence(terms)
        }
    out: dict[str, tuple[str, ...]] = {}
    for group in str(value or "").split(";"):
        if "=" not in group:
            continue
        label, raw_terms = group.split("=", 1)
        terms = parse_term_sequence(raw_terms.replace("|", ","))
        if label.strip() and terms:
            out[label.strip().lower()] = terms
    return out


def normalize_claim_scope_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})
    stopwords = set(DEFAULT_CLAIM_SCOPE_STOPWORDS)
    stopwords.update(parse_term_sequence(cfg.get("stopwords")))

    aliases = {key: tuple(values) for key, values in DEFAULT_CLAIM_SCOPE_ALIASES.items()}
    aliases.update(parse_term_map(cfg.get("slot_aliases") or cfg.get("aliases")))

    excluded = {key: tuple(values) for key, values in DEFAULT_CLAIM_SCOPE_EXCLUDED_TERMS.items()}
    excluded.update(parse_term_map(cfg.get("excluded_terms") or cfg.get("exclusions")))

    return {
        "stopwords": stopwords,
        "slot_aliases": aliases,
        "excluded_terms": excluded,
    }


def parse_answer_type_rule_map(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for label, raw_rule in value.items():
        if not isinstance(raw_rule, dict) or not str(label).strip():
            continue
        out[str(label).strip().lower()] = raw_rule
    return out


def normalize_answer_type_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})
    configured_rules = parse_answer_type_rule_map(cfg.get("rules") or cfg)
    rules: dict[str, dict[str, Any]] = {}
    for label, defaults in DEFAULT_ANSWER_TYPE_RULES.items():
        raw_rule = dict(defaults)
        raw_rule.update(configured_rules.pop(label, {}))
        rules[label] = normalize_answer_type_rule(raw_rule)
    for label, raw_rule in configured_rules.items():
        normalized = normalize_answer_type_rule(raw_rule)
        if normalized["query_terms"] and (normalized["positive_terms"] or normalized["negative_terms"]):
            rules[label] = normalized
    return {"rules": rules}


def normalize_answer_type_rule(raw_rule: dict[str, Any]) -> dict[str, Any]:
    positive_score = raw_rule.get("positive_score", 1.0)
    negative_score = raw_rule.get("negative_score", -1.0)
    try:
        positive_score = float(positive_score)
    except (TypeError, ValueError):
        positive_score = 1.0
    try:
        negative_score = float(negative_score)
    except (TypeError, ValueError):
        negative_score = -1.0
    return {
        "query_terms": parse_term_sequence(raw_rule.get("query_terms")),
        "positive_terms": parse_term_sequence(raw_rule.get("positive_terms")),
        "negative_terms": parse_term_sequence(raw_rule.get("negative_terms")),
        "query_requires_any": parse_term_sequence(raw_rule.get("query_requires_any")),
        "query_excludes_any": parse_term_sequence(raw_rule.get("query_excludes_any")),
        "query_excludes_unless_any": parse_term_sequence(raw_rule.get("query_excludes_unless_any")),
        "positive_requires_any": parse_term_sequence(raw_rule.get("positive_requires_any")),
        "negative_requires_absent": parse_term_sequence(raw_rule.get("negative_requires_absent")),
        "positive_score": positive_score,
        "negative_score": negative_score,
    }


def normalize_retrieval_signal_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})
    broad_cfg = dict(DEFAULT_RETRIEVAL_SIGNAL_CONFIG["broad_generic"])
    broad_cfg.update(_dict_value(cfg.get("broad_generic")))
    scope_cfg = dict(DEFAULT_RETRIEVAL_SIGNAL_CONFIG["scope_deflection"])
    scope_cfg.update(_dict_value(cfg.get("scope_deflection")))
    relevance_cfg = dict(DEFAULT_RETRIEVAL_SIGNAL_CONFIG["correction_relevance"])
    relevance_cfg.update(_dict_value(cfg.get("correction_relevance")))

    return {
        "broad_generic": {
            "source_contains": parse_term_sequence(broad_cfg.get("source_contains")),
            "text_prefixes": parse_term_sequence(broad_cfg.get("text_prefixes")),
            "penalty": _float_value(broad_cfg.get("penalty"), 0.18),
        },
        "scope_deflection": {
            "query_terms": parse_term_sequence(scope_cfg.get("query_terms")),
            "correction_prefixes": parse_term_sequence(scope_cfg.get("correction_prefixes")),
            "text_markers": parse_term_sequence(scope_cfg.get("text_markers")),
            "penalty": _float_value(scope_cfg.get("penalty"), 0.55),
        },
        "correction_relevance": {
            "match_threshold": _float_value(relevance_cfg.get("match_threshold"), 0.75),
            "min_relevance": _float_value(relevance_cfg.get("min_relevance"), 0.15),
        },
    }


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def tokens(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(text or ""))
    return {token for token in cleaned.split() if len(token) > 1}


def stem_token(token: str) -> str:
    token = str(token or "").lower().strip()
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def expanded_tokens(text: str) -> set[str]:
    lower = str(text or "").lower()
    out = {stem_token(token) for token in tokens(lower)}
    if "who am i" in lower or "what am i" in lower or "my identity" in lower or "my name" in lower:
        out.update({"identity", "name", "user", "primary", "called", "agent", "hermes", "victor"})
    if out & {"contradict", "contradiction", "conflict"} or "facts contradict" in lower:
        out.update({"contradict", "contradiction", "conflict", "protect", "protective", "correction", "stale", "csd"})
    if out & {"consolidation", "consolidate"} or "consolidation work" in lower:
        out.update({"consolidation", "consolidate", "summary", "summarize", "summarizes", "original", "preserve", "source"})
    if "previous question" in lower or "remember previous" in lower:
        out.update({"session", "history", "turn", "context", "previous", "question", "remember"})
    if out & {"maintain", "maintains"}:
        out.update({"maintain", "maintains"})
    return out


class RetrievalSignalScorer:
    def __init__(
        self,
        symbolic_config: dict[str, Any] | None = None,
        claim_scope_config: dict[str, Any] | None = None,
        answer_type_config: dict[str, Any] | None = None,
        signal_config: dict[str, Any] | None = None,
    ) -> None:
        self.symbolic_config = dict(symbolic_config or {})
        self.claim_scope_config = claim_scope_config or normalize_claim_scope_config(None)
        self.answer_type_config = answer_type_config or normalize_answer_type_config(None)
        self.signal_config = normalize_retrieval_signal_config(signal_config)

    def claim_scope_affinity(self, query: str, text: str, source: str | None = None) -> float:
        stopwords = set(self.claim_scope_config["stopwords"])
        query_l = str(query or "").lower()
        text_l = str(text or "").lower()
        query_terms = {
            token
            for token in expanded_tokens(query_l)
            if len(token) > 2 and token not in stopwords
        }
        if not query_terms:
            return 0.0
        text_terms = expanded_tokens(text_l)
        source_terms = expanded_tokens(Path(str(source or "")).stem)
        combined_terms = set(text_terms) | set(source_terms)
        for slot, aliases in self.claim_scope_config["slot_aliases"].items():
            slot_terms = expanded_tokens(slot)
            if not slot_terms or not (query_terms & slot_terms):
                continue
            alias_terms = set(slot_terms)
            for alias in aliases:
                alias_terms.update(expanded_tokens(alias))
            excluded_terms: set[str] = set()
            for excluded in self.claim_scope_config["excluded_terms"].get(slot, ()):
                excluded_terms.update(expanded_tokens(excluded))
            if combined_terms & alias_terms and not (combined_terms & excluded_terms):
                combined_terms.update(slot_terms)
        hits = len(query_terms & combined_terms)
        return min(1.0, hits / max(1, len(query_terms)))

    def answer_type_affinity(self, query: str, text: str, source: str | None = None) -> float:
        del source
        query_terms = set(expanded_tokens(query))
        text_terms = set(expanded_tokens(text))
        if not query_terms or not text_terms:
            return 0.0

        score = 0.0
        for rule in self.answer_type_config["rules"].values():
            query_rule_terms = self.answer_type_rule_terms(rule["query_terms"])
            if not query_rule_terms or not (query_terms & query_rule_terms):
                continue
            required_query_terms = self.answer_type_rule_terms(rule["query_requires_any"])
            if required_query_terms and not (query_terms & required_query_terms):
                continue
            excluded_query_terms = self.answer_type_rule_terms(rule["query_excludes_any"])
            excluded_unless_terms = self.answer_type_rule_terms(rule["query_excludes_unless_any"])
            if excluded_query_terms and query_terms & excluded_query_terms:
                if not excluded_unless_terms or not (query_terms & excluded_unless_terms):
                    continue

            positive_terms = self.answer_type_rule_terms(rule["positive_terms"])
            positive_required = self.answer_type_rule_terms(rule["positive_requires_any"])
            if positive_terms and text_terms & positive_terms:
                if not positive_required or text_terms & positive_required:
                    score = max(score, float(rule["positive_score"]))

            negative_terms = self.answer_type_rule_terms(rule["negative_terms"])
            negative_absent = self.answer_type_rule_terms(rule["negative_requires_absent"])
            if negative_terms and text_terms & negative_terms:
                if not negative_absent or not (text_terms & negative_absent):
                    score = min(score, float(rule["negative_score"]))
        return max(-1.0, min(1.0, score))

    @staticmethod
    def answer_type_rule_terms(values: tuple[str, ...]) -> set[str]:
        out: set[str] = set()
        for value in values:
            out.update(expanded_tokens(value))
        return out

    def broad_generic_note(self, text: str | None, source: str | None) -> bool:
        cfg = self.signal_config["broad_generic"]
        text_l = str(text or "").strip().lower()
        source_l = str(source or "").strip().lower()
        return (
            any(marker in source_l for marker in cfg["source_contains"])
            or any(text_l.startswith(prefix) for prefix in cfg["text_prefixes"])
        )

    def scope_deflection_note(self, query: str, text: str | None, source: str | None) -> bool:
        cfg = self.signal_config["scope_deflection"]
        query_terms = expanded_tokens(query)
        policy_terms: set[str] = set()
        for term in cfg["query_terms"]:
            policy_terms.update(expanded_tokens(term))
        if not (query_terms & policy_terms):
            return False
        text_l = str(text or "").strip().lower()
        source_l = str(source or "").strip().lower()
        correction_prefixes = cfg["correction_prefixes"]
        if not (
            any(text_l.startswith(prefix) for prefix in correction_prefixes)
            or any(source_l.startswith(prefix) for prefix in correction_prefixes)
        ):
            return False
        return any(marker in text_l for marker in cfg["text_markers"])

    def correction_relevance(
        self,
        authority_status: dict[str, Any],
        relation_supersession_score: float,
        correction_chain_score: float,
        text_match: float,
        claim_scope_match: float,
    ) -> float:
        state = str(authority_status.get("authority_state") or "").lower()
        has_correction_signal = (
            state in {"current", "superseded", "stale"}
            or abs(float(relation_supersession_score or 0.0)) > 0.0
            or abs(float(correction_chain_score or 0.0)) > 0.0
        )
        if not has_correction_signal:
            return 1.0
        cfg = self.signal_config["correction_relevance"]
        threshold = float(cfg["match_threshold"])
        if claim_scope_match >= threshold or text_match >= threshold:
            return 1.0
        return max(float(cfg["min_relevance"]), min(1.0, claim_scope_match))

    def intent_labels(self, text: str, memory_type: str | None = None) -> set[str]:
        lower = str(text or "").lower()
        labels: set[str] = set()
        for label, terms in configured_intent_terms(self.symbolic_config).items():
            if any(term in lower for term in terms):
                labels.add(label)
        if memory_type == "preference":
            labels.add("preference")
        return labels

    @staticmethod
    def query_entity_miss(query: str, text: str) -> bool:
        query_tokens = tokens(query)
        text_tokens = set(tokens(text))
        named_queries = {"victor", "hermes", "agent", "assistant"} & set(query_tokens)
        if not named_queries:
            return False
        return not bool(named_queries & text_tokens)

    def claim_scope_matches(self, query: str, text: str, text_affinity: float) -> bool:
        query_intents = self.intent_labels(query, None)
        if not query_intents:
            return True
        text_intents = self.intent_labels(text, None)
        if query_intents & text_intents:
            return True
        return not self.query_entity_miss(query, text) and text_affinity >= 0.45
