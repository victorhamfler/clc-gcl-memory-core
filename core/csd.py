from __future__ import annotations

import math
import re

from core.math_utils import EPS, clamp, euclidean
from core.models import CSDDiagnostics, RecallResult, SignalPacket
from storage.db import MemoryDB


class CSDLayer:
    def __init__(self, db: MemoryDB):
        self.db = db

    def diagnose(self, signal: SignalPacket, recall: RecallResult) -> CSDDiagnostics:
        domain = recall.nearest_domain
        if domain and domain.anchor_vector:
            raw_drift = euclidean(signal.embedding, domain.anchor_vector)
            effective_dimension = max(1.0, float(domain.effective_dimension or 1.0))
            domain_shift = 1.0 - max(0.0, recall.nearest_domain_score)
            domain_id = domain.id
        else:
            raw_drift = 1.0
            effective_dimension = 1.0
            domain_shift = 1.0
            domain_id = ""

        if recall.items:
            distances = [max(0.0, 1.0 - item.score) for item in recall.items[:5]]
            local_density = sum(distances) / len(distances)
        else:
            local_density = 1.0

        csd_semantic = raw_drift / (math.sqrt(effective_dimension) + EPS)
        csd_density = raw_drift / (local_density + EPS)
        information_gain = clamp(
            0.35 * min(2.0, csd_density) / 2.0
            + 0.25 * signal.importance
            + 0.20 * signal.error_signal
            + 0.20 * signal.user_instruction
        )
        contradiction = self._estimate_contradiction(signal, recall, domain_id)
        return CSDDiagnostics(
            raw_drift=raw_drift,
            csd_semantic=csd_semantic,
            csd_density=csd_density,
            information_gain=information_gain,
            contradiction=contradiction,
            domain_shift=domain_shift,
            effective_dimension=effective_dimension,
            local_density=local_density,
        )

    def _estimate_contradiction(self, signal: SignalPacket, recall: RecallResult, domain_id: str) -> float:
        lower = signal.text.lower()
        correction_words = (
            "wrong",
            "correction",
            "corrected",
            "actually",
            "current rule",
            "current policy",
            "current preference",
            "updated rule",
            "updated policy",
            "updated preference",
            "now ",
            "no longer",
            "only when",
            "unless the user",
            "prefer ",
            "supersede",
            "supersedes",
            "contradict",
            "contradicts",
            "replace the previous",
            "instead of the previous",
        )
        correction_hint = any(word in lower for word in correction_words)
        contradiction_words = (
            "must not",
            "should not",
            "do not",
            "does not",
            "not always",
            "no longer",
            "never",
            "only when",
            "unless",
            "instead",
            "rather than",
            "not ",
        )
        contradiction_hint = any(word in lower for word in contradiction_words)
        additive_words = (
            "also",
            "include examples",
            "include an example",
            "add ",
            "additionally",
            "clarification",
            "correction note",
        )
        additive_hint = any(word in lower for word in additive_words)
        if not correction_hint or not recall.items:
            return 0.0
        if not contradiction_hint:
            return 0.0
        if additive_hint and not any(word in lower for word in ("must not", "should not", "not always", "no longer", "never")):
            return 0.0
        lexical_conflict = self._lexical_policy_conflict(signal.text, recall)
        if lexical_conflict >= 0.75:
            return lexical_conflict
        best = max((item.score for item in recall.items if not domain_id or item.domain_id == domain_id), default=0.0)
        if best < 0.62:
            return 0.0
        return clamp(0.35 + 0.65 * max(0.0, best))

    def _lexical_policy_conflict(self, text: str, recall: RecallResult) -> float:
        lower = str(text or "").lower()
        if not any(term in lower for term in ("only when", "unless", "must not", "should not", "not always", "never", "no longer")):
            return 0.0
        best = 0.0
        for item in recall.items[:5]:
            old = str(item.text or "").lower()
            overlap = self._topic_overlap(lower, old)
            if overlap < 0.16:
                continue
            if not self._has_opposing_policy_language(lower, old):
                continue
            best = max(best, 0.78 + 0.22 * min(1.0, overlap))
        return clamp(best)

    @staticmethod
    def _has_opposing_policy_language(new: str, old: str) -> bool:
        restrictive_new = any(term in new for term in ("only when", "unless", "must not", "should not", "not always", "never", "no longer"))
        permissive_old = any(term in old for term in ("always", "automatically", "may ", "by default", "every "))
        opposing_pairs = (
            ("short", "long"),
            ("explicit", "automatically"),
            ("only when", "always"),
            ("only when", "automatically"),
            ("only when", "every "),
            ("unless", "always"),
            ("unless", "by default"),
        )
        return (restrictive_new and permissive_old) or any(a in new and b in old for a, b in opposing_pairs)

    @staticmethod
    def _topic_overlap(a: str, b: str) -> float:
        stopwords = {
            "after",
            "also",
            "and",
            "are",
            "become",
            "for",
            "from",
            "should",
            "that",
            "the",
            "they",
            "this",
            "when",
            "with",
        }
        a_terms = {term for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", a) if term not in stopwords}
        b_terms = {term for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", b) if term not in stopwords}
        if not a_terms or not b_terms:
            return 0.0
        return len(a_terms & b_terms) / max(1, min(len(a_terms), len(b_terms)))
