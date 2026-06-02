from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.controller_packet_calibration import normalize_bridge_scorer_policy  # noqa: E402
from eval.controller_packet_bridge_separator_holdout import expected_label, rule_prediction  # noqa: E402
from eval.controller_packet_memory_bank import read_jsonl  # noqa: E402


DEFAULT_PACKETS = REPO_ROOT / "experiments" / "controller_packet_bridge_two_log_separator_holdout_packets.jsonl"
DEFAULT_SEPARATOR = REPO_ROOT / "experiments" / "controller_packet_bridge_two_log_separator_holdout_bridge_separator.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_ogcf_bridge_scorer_report.md"

INTENTS = (
    "bridge_geometry_query",
    "cross_domain_bridge_synthesis",
    "ordinary_context",
    "unknown",
)
FEATURE_KEYS = (
    "bias",
    "ogcf_meta_present",
    "bridge_overload_score",
    "affected_memory_ratio",
    "maintenance_pressure",
    "answer_confidence",
    "answer_conflict",
    "evidence_count",
    "canonical_support_count",
    "canonical_duplicate_pressure",
    "state_has_current",
    "state_has_stale",
    "top_retrieval_score",
    "avg_claim_scope_score",
    "avg_text_match_score",
    "query_bridge_term_score",
    "query_geometry_term_score",
    "query_ordinary_term_score",
    "evidence_bridge_term_score",
    "evidence_geometry_term_score",
    "evidence_noise_term_score",
    "intent_bridge_geometry_query",
    "intent_cross_domain_bridge_synthesis",
    "intent_ordinary_context",
    "intent_unknown",
)

BRIDGE_TERMS = ("bridge", "connect", "connection", "cross-domain", "cross domain", "link", "between")
GEOMETRY_TERMS = ("geometry", "loop", "cluster", "domain", "overlap", "curvature", "topology")
ORDINARY_TERMS = ("status", "preference", "todo", "ordinary", "lookup", "simple", "single")
NOISE_TERMS = ("unrelated", "random", "ordinary", "single-topic", "single topic", "status", "lookup")


def scorer_candidate_decision(
    *,
    learned: dict[str, Any],
    symbolic: dict[str, Any],
    test_count: int,
    policy: dict[str, Any],
) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    min_test = int(policy.get("min_test_samples_for_candidate") or 4)
    if test_count < min_test:
        blockers.append(f"test_count_below_minimum:{test_count}<{min_test}")
    if policy.get("require_not_worse_than_symbolic") and learned.get("match_rate", 0.0) < symbolic.get("match_rate", 0.0):
        blockers.append("learned_match_rate_below_symbolic")
    if policy.get("require_zero_false_positives") and int(learned.get("false_positive_count") or 0) > 0:
        blockers.append("learned_false_positive_count_nonzero")
    if policy.get("require_zero_false_negatives") and int(learned.get("false_negative_count") or 0) > 0:
        blockers.append("learned_false_negative_count_nonzero")
    return not blockers, blockers


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def intent(packet: dict[str, Any]) -> str:
    ogcf = packet.get("ogcf") if isinstance(packet.get("ogcf"), dict) else {}
    raw = str(ogcf.get("intent") or "unknown").strip().lower()
    return raw if raw in INTENTS else "unknown"


def term_score(text: str, terms: tuple[str, ...]) -> float:
    normalized = " ".join(str(text or "").lower().split())
    if not normalized:
        return 0.0
    hits = sum(1 for term in terms if term in normalized)
    return min(1.0, hits / max(1, min(3, len(terms))))


def evidence_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), dict) else {}
    rows = evidence.get("selected")
    if not isinstance(rows, list) or not rows:
        rows = evidence.get("retrieval_context")
    return [row for row in rows or [] if isinstance(row, dict)]


def avg_row_value(rows: list[dict[str, Any]], key: str) -> float:
    values = [float_value(row.get(key), 0.0) for row in rows if row.get(key) is not None]
    return sum(values) / len(values) if values else 0.0


def vector_for(packet: dict[str, Any]) -> list[float]:
    ogcf = packet.get("ogcf") if isinstance(packet.get("ogcf"), dict) else {}
    answer = packet.get("answer") if isinstance(packet.get("answer"), dict) else {}
    canonical = packet.get("canonical") if isinstance(packet.get("canonical"), dict) else {}
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), dict) else {}
    state = evidence.get("state_summary") if isinstance(evidence.get("state_summary"), dict) else {}
    rows = evidence_rows(packet)
    query = ((packet.get("request") if isinstance(packet.get("request"), dict) else {}) or {}).get("query") or ""
    evidence_text = " ".join(str(row.get("text_preview") or "") for row in rows)
    item_intent = intent(packet)
    return [
        1.0,
        1.0 if ogcf.get("meta_present") else 0.0,
        float_value(ogcf.get("bridge_overload_score"), 0.0),
        float_value(ogcf.get("effective_affected_memory_ratio") or ogcf.get("affected_memory_ratio"), 0.0),
        float_value(ogcf.get("maintenance_pressure"), 0.0),
        float_value(answer.get("confidence"), 0.0),
        1.0 if answer.get("conflict") else 0.0,
        float_value(answer.get("evidence_count"), 0.0),
        float_value(canonical.get("max_support_count"), 0.0),
        float_value(canonical.get("duplicate_pressure"), 0.0),
        1.0 if state.get("has_current") else 0.0,
        1.0 if state.get("has_stale") else 0.0,
        max([float_value(row.get("score"), 0.0) for row in rows] or [0.0]),
        avg_row_value(rows, "claim_scope_score"),
        avg_row_value(rows, "text_match_score"),
        term_score(str(query), BRIDGE_TERMS),
        term_score(str(query), GEOMETRY_TERMS),
        term_score(str(query), ORDINARY_TERMS),
        term_score(evidence_text, BRIDGE_TERMS),
        term_score(evidence_text, GEOMETRY_TERMS),
        term_score(evidence_text, NOISE_TERMS),
        *[1.0 if item_intent == choice else 0.0 for choice in INTENTS],
    ]


def bridge_samples(packet_paths: list[Path]) -> list[dict[str, Any]]:
    samples = []
    for path in packet_paths:
        for packet in read_jsonl(path):
            expected = expected_label(packet)
            if expected not in {"positive", "negative"}:
                continue
            samples.append(
                {
                    "source_packet_path": str(path),
                    "operation_id": packet.get("operation_id"),
                    "expected": expected,
                    "packet": packet,
                    "features": vector_for(packet),
                }
            )
    return samples


def split_samples(samples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train = []
    test = []
    for idx, sample in enumerate(samples):
        op_id = str(sample.get("operation_id") or idx)
        bucket = sum(ord(ch) for ch in op_id) % 4
        if bucket == 0:
            test.append(sample)
        else:
            train.append(sample)
    if not test and samples:
        test = samples[::4] or samples[-1:]
        test_ids = {id(item) for item in test}
        train = [item for item in samples if id(item) not in test_ids]
    return train, test


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, value))))


def train_logistic(samples: list[dict[str, Any]], *, epochs: int = 700, lr: float = 0.08, l2: float = 0.001) -> list[float]:
    if not samples:
        return []
    weights = [0.0 for _ in samples[0]["features"]]
    for _epoch in range(epochs):
        for sample in samples:
            x = sample["features"]
            y = 1.0 if sample["expected"] == "positive" else 0.0
            pred = sigmoid(sum(w * v for w, v in zip(weights, x)))
            error = pred - y
            for idx, value in enumerate(x):
                penalty = l2 * weights[idx] if idx else 0.0
                weights[idx] -= lr * (error * value + penalty)
    return weights


def learned_prediction(weights: list[float], sample: dict[str, Any]) -> tuple[str, float]:
    probability = sigmoid(sum(w * v for w, v in zip(weights, sample["features"])))
    return ("positive" if probability >= 0.5 else "negative", round(probability, 6))


def symbolic_prediction(separator: dict[str, Any], sample: dict[str, Any]) -> str:
    separators = [item for item in separator.get("separators") or [] if isinstance(item, dict)]
    if not separators:
        return "abstain"
    return rule_prediction(separators[0], sample["packet"])


def score_rows(rows: list[dict[str, Any]], prediction_key: str) -> dict[str, Any]:
    scored = [row for row in rows if row.get(prediction_key) in {"positive", "negative"}]
    matches = [row for row in scored if row.get(prediction_key) == row.get("expected")]
    false_positive = [row for row in scored if row.get("expected") == "negative" and row.get(prediction_key) == "positive"]
    false_negative = [row for row in scored if row.get("expected") == "positive" and row.get(prediction_key) == "negative"]
    return {
        "scored_count": len(scored),
        "match_rate": round(len(matches) / len(scored), 6) if scored else 0.0,
        "false_positive_count": len(false_positive),
        "false_negative_count": len(false_negative),
    }


def build_report(
    packet_paths: list[Path],
    separator_path: Path | None = None,
    *,
    policy_config: dict[str, Any] | None = None,
    min_test_samples: int | None = None,
) -> dict[str, Any]:
    policy = normalize_bridge_scorer_policy(policy_config, min_test_samples=min_test_samples)
    samples = bridge_samples(packet_paths)
    train, test = split_samples(samples)
    weights = train_logistic(train)
    separator = read_json(separator_path) if separator_path else {}
    rows = []
    for split_name, split_rows in (("train", train), ("test", test)):
        for sample in split_rows:
            learned, probability = learned_prediction(weights, sample)
            symbolic = symbolic_prediction(separator, sample) if separator else "not_available"
            packet = sample["packet"]
            ogcf = packet.get("ogcf") if isinstance(packet.get("ogcf"), dict) else {}
            rows.append(
                {
                    "split": split_name,
                    "operation_id": sample.get("operation_id"),
                    "expected": sample.get("expected"),
                    "learned_prediction": learned,
                    "learned_positive_probability": probability,
                    "symbolic_prediction": symbolic,
                    "intent": intent(packet),
                    "ogcf_meta_present": bool(ogcf.get("meta_present")),
                }
            )
    train_rows = [row for row in rows if row["split"] == "train"]
    test_rows = [row for row in rows if row["split"] == "test"]
    learned_test = score_rows(test_rows, "learned_prediction")
    symbolic_test = score_rows(test_rows, "symbolic_prediction") if separator else {"scored_count": 0, "match_rate": 0.0}
    learned_candidate, readiness_blockers = scorer_candidate_decision(
        learned=learned_test,
        symbolic=symbolic_test,
        test_count=len(test_rows),
        policy=policy,
    )
    candidate_reason = (
        "learned scorer satisfied held-out candidate policy"
        if learned_candidate
        else "learned scorer failed held-out candidate policy"
    )
    return {
        "schema": "controller_packet_ogcf_bridge_scorer/v1",
        "description": "Report-only tiny local learned scorer for useful-vs-noisy OGCF bridge warnings.",
        "ok": bool(train_rows and test_rows),
        "packet_paths": [str(path) for path in packet_paths],
        "separator_path": str(separator_path) if separator_path else None,
        "sample_count": len(samples),
        "train_count": len(train_rows),
        "test_count": len(test_rows),
        "policy": policy,
        "feature_keys": list(FEATURE_KEYS),
        "weights": {key: round(weight, 6) for key, weight in zip(FEATURE_KEYS, weights)},
        "train_learned": score_rows(train_rows, "learned_prediction"),
        "test_learned": learned_test,
        "test_symbolic": symbolic_test,
        "learned_scorer_candidate": learned_candidate,
        "learned_scorer_candidate_reason": candidate_reason,
        "readiness_blockers": readiness_blockers,
        "promotion_ready": False,
        "promotion_blocker": "report-only learned scorer prototype; requires broader unseen multi-run holdout and manual approval before runtime use",
        "examples": rows[:30],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet OGCF Bridge Scorer",
        "",
        "This scorer is advisory only. It does not mutate runtime behavior or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Samples: `{report['sample_count']}`",
        f"Train/test: `{report['train_count']}` / `{report['test_count']}`",
        f"Learned scorer candidate: `{report['learned_scorer_candidate']}`",
        f"Candidate reason: `{report['learned_scorer_candidate_reason']}`",
        f"Readiness blockers: `{json.dumps(report['readiness_blockers'])}`",
        f"Promotion ready: `{report['promotion_ready']}`",
        "",
        "## Test Learned",
        "",
        "```json",
        json.dumps(report["test_learned"], indent=2),
        "```",
        "",
        "## Test Symbolic",
        "",
        "```json",
        json.dumps(report["test_symbolic"], indent=2),
        "```",
        "",
        "## Weights",
        "",
        "```json",
        json.dumps(report["weights"], indent=2),
        "```",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train/evaluate a report-only OGCF bridge useful-vs-noisy scorer.")
    parser.add_argument("--packets", type=Path, action="append", default=None)
    parser.add_argument("--separator", type=Path, default=DEFAULT_SEPARATOR)
    parser.add_argument("--min-test-samples", type=int, default=None)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(
        args.packets or [DEFAULT_PACKETS],
        args.separator,
        policy_config=load_config(ROOT),
        min_test_samples=args.min_test_samples,
    )
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "sample_count": report["sample_count"],
                "test_learned": report["test_learned"],
                "test_symbolic": report["test_symbolic"],
                "learned_scorer_candidate": report["learned_scorer_candidate"],
                "readiness_blockers": report["readiness_blockers"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
