from __future__ import annotations

from core.math_utils import clamp, sigmoid
from core.models import CLCDecision, CLCSignals, CSDDiagnostics, RecallResult, SignalPacket


STATE_UPDATE_STRENGTH = {
    "IGNORE": 0.00,
    "LIGHT_UPDATE": 0.05,
    "RECALL": 0.10,
    "FOCUS": 0.25,
    "EXPLORE": 0.15,
    "CONSOLIDATE": 0.35,
    "PROTECT": 0.00,
    "SPLIT_DOMAIN": 0.00,
}


class CLCController:
    def __init__(self, thresholds: dict[str, float] | None = None):
        self.thresholds = {
            "new": 1.5,
            "recall_low": 0.45,
            "recall_mid": 0.65,
            "recall_high": 0.82,
            "contradiction": 0.75,
            "domain_shift": 0.60,
            "focus": 0.68,
            "information_gain": 0.45,
        }
        for key, value in (thresholds or {}).items():
            if key in self.thresholds:
                self.thresholds[key] = float(value)

    def compute_signals(self, signal: SignalPacket, diagnostics: CSDDiagnostics, recall: RecallResult) -> CLCSignals:
        surprise = sigmoid(
            1.25 * diagnostics.csd_semantic
            + 0.85 * diagnostics.csd_density
            + 1.50 * diagnostics.contradiction
            + 0.90 * diagnostics.domain_shift
            - 1.65
        )
        recall_score = clamp(recall.best_score)
        curiosity = clamp(surprise * (1.0 - recall_score) * (1.0 - diagnostics.contradiction))
        focus = sigmoid(
            1.10 * surprise
            + 1.50 * diagnostics.contradiction
            + 1.00 * signal.importance
            + 0.70 * signal.user_instruction
            + 0.60 * signal.error_signal
            - 1.25
        )
        return CLCSignals(surprise=surprise, recall=recall_score, curiosity=curiosity, focus=focus)

    def decide(self, diagnostics: CSDDiagnostics, signals: CLCSignals) -> CLCDecision:
        t = self.thresholds
        if diagnostics.contradiction > t["contradiction"]:
            return self._decision("PROTECT", "contradiction_above_threshold")
        if diagnostics.domain_shift > t["domain_shift"] and signals.recall < t["recall_low"]:
            return self._decision("SPLIT_DOMAIN", "domain_shift_with_low_recall")
        if diagnostics.csd_semantic > t["new"] and signals.recall < t["recall_low"]:
            return self._decision("EXPLORE", "high_novelty_low_recall")
        if diagnostics.csd_semantic > t["new"] and signals.recall >= t["recall_mid"]:
            return self._decision("FOCUS", "high_novelty_with_known_memory")
        if signals.recall > t["recall_high"] and diagnostics.csd_semantic < 0.5:
            return self._decision("RECALL", "strong_recall_low_novelty")
        if signals.focus > t["focus"]:
            return self._decision("FOCUS", "high_focus")
        if diagnostics.information_gain > t["information_gain"]:
            return self._decision("LIGHT_UPDATE", "moderate_information_gain")
        return self._decision("IGNORE", "low_signal")

    def _decision(self, state: str, reason: str) -> CLCDecision:
        return CLCDecision(
            state=state,
            update_strength=STATE_UPDATE_STRENGTH[state],
            reason=reason,
        )
