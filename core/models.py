from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SignalPacket:
    text: str
    embedding: list[float]
    memory_type: str
    domains: list[str]
    entities: list[str] = field(default_factory=list)
    relations: list[tuple[str, str, str]] = field(default_factory=list)
    importance: float = 0.5
    confidence: float = 0.5
    error_signal: float = 0.0
    user_instruction: float = 0.0


@dataclass
class MemoryNode:
    id: str
    text: str
    embedding: list[float]
    domain_id: str | None
    memory_type: str
    importance: float
    stability: float
    confidence: float
    csd_score: float
    surprise: float
    recall_score: float
    curiosity: float
    focus: float
    clc_state: str
    created_at: str
    updated_at: str
    namespace: str = "global"
    deprecated: int = 0


@dataclass
class DomainState:
    id: str
    name: str
    anchor_vector: list[float]
    namespace: str = "global"
    effective_dimension: float = 1.0
    drift_ema: float = 0.0
    drift_var: float = 0.0
    curvature_ema: float = 0.0
    stability: float = 0.0
    memory_count: int = 0
    previous_update_direction: list[float] | None = None


@dataclass
class RecallItem:
    memory_id: str
    domain_id: str | None
    text: str
    memory_type: str
    score: float
    importance: float
    stability: float
    csd_score: float = 0.0
    clc_state: str | None = None
    namespace: str = "global"
    deprecated: bool = False


@dataclass
class RecallResult:
    items: list[RecallItem]
    best_score: float
    nearest_domain: DomainState | None
    nearest_domain_score: float


@dataclass
class CSDDiagnostics:
    raw_drift: float
    csd_semantic: float
    csd_density: float
    information_gain: float
    contradiction: float
    domain_shift: float
    effective_dimension: float
    local_density: float


@dataclass
class CLCSignals:
    surprise: float
    recall: float
    curiosity: float
    focus: float


@dataclass
class CLCDecision:
    state: str
    update_strength: float
    reason: str


@dataclass
class GCLUpdateResult:
    action: str
    domain_id: str
    angular_drift: float
    radial_drift: float
    orthogonal_drift: float
    combined_drift: float
    curvature: float
    anchor_update_strength: float


@dataclass
class RetrievalResult:
    memory_id: str
    text: str
    domain_id: str | None
    memory_type: str
    score: float
    components: dict[str, Any]
