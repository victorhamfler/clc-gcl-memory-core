from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.adaptive_behavior_shadow import adaptive_behavior_shadow_advisories  # noqa: E402
from core.config import load_config  # noqa: E402


DEFAULT_LOG = REPO_ROOT / "experiments" / "hermes_adaptive_shadow_outcomes.jsonl"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_real_log_calibration_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_shadow_real_log_calibration_report.md"


POSITIVE_ANSWER_LABELS = {
    "answer_correct",
    "answer_good_citation",
    "answer_bridge_warning_useful",
}
NEGATIVE_ANSWER_LABELS = {
    "answer_missing_support",
    "answer_stale",
    "answer_wrong_scope",
    "answer_overconfident",
    "answer_bad_citation",
    "answer_conflict_not_disclosed",
    "answer_bridge_warning_noise",
}
REFUSAL_MARKERS = (
    "do not have enough",
    "not enough memory evidence",
    "insufficient",
    "cannot answer",
    "no memory evidence",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def payload(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("payload")
    return value if isinstance(value, dict) else {}


def request(event: dict[str, Any]) -> dict[str, Any]:
    value = payload(event).get("request")
    return value if isinstance(value, dict) else {}


def response(event: dict[str, Any]) -> dict[str, Any]:
    value = payload(event).get("response")
    return value if isinstance(value, dict) else {}


def feedback_payload(event: dict[str, Any]) -> dict[str, Any]:
    value = payload(event).get("feedback")
    return value if isinstance(value, dict) else {}


def feedback_label(event: dict[str, Any]) -> str:
    return str(
        payload(event).get("label")
        or request(event).get("label")
        or feedback_payload(event).get("label")
        or ""
    ).strip().lower()


def feedback_scope(event: dict[str, Any]) -> str:
    value = str(
        payload(event).get("feedback_scope")
        or request(event).get("feedback_scope")
        or feedback_payload(event).get("feedback_scope")
        or request(event).get("target_type")
        or request(event).get("scope")
        or ""
    ).strip().lower()
    if value:
        return value
    return "memory"


def feedback_metadata(event: dict[str, Any]) -> dict[str, Any]:
    value = feedback_payload(event).get("metadata")
    return value if isinstance(value, dict) else {}


def linked_operation_id(event: dict[str, Any]) -> str:
    return str(
        event.get("linked_operation_id")
        or payload(event).get("linked_operation_id")
        or request(event).get("linked_operation_id")
        or feedback_metadata(event).get("linked_operation_id")
        or payload(event).get("operation_id")
        or event.get("operation_id")
        or ""
    ).strip()


def answer_has_refusal(answer: str) -> bool:
    text = " ".join(str(answer or "").lower().split())
    return any(marker in text for marker in REFUSAL_MARKERS)


def shadow(event: dict[str, Any]) -> dict[str, Any]:
    direct = payload(event).get("adaptive_behavior_shadow")
    if isinstance(direct, dict):
        return direct
    nested = response(event).get("adaptive_behavior_shadow")
    return nested if isinstance(nested, dict) else {}


@dataclass
class ReplayContext:
    diagnostics: dict[str, Any]
    retrieval_context: list[dict[str, Any]]
    ogcf_meta_present: bool
    ok: bool = True

    def feature_dict(self) -> dict[str, Any]:
        snapshot = self.diagnostics
        return {
            "memory_bad_rate": snapshot.get("memory_bad_rate", 0.18),
            "probe_drop": snapshot.get("probe_drop", 0.04),
            "csd_ratio": snapshot.get("csd_ratio", 0.75),
        }


def replay_shadow(event: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    pay = payload(event)
    resp = response(event)
    snapshot = pay.get("selector_snapshot") if isinstance(pay.get("selector_snapshot"), dict) else {}
    if not snapshot:
        snapshot = resp.get("selector_snapshot") if isinstance(resp.get("selector_snapshot"), dict) else {}
    diagnostics = snapshot.get("diagnostics") if isinstance(snapshot.get("diagnostics"), dict) else {}
    context = ReplayContext(
        diagnostics=diagnostics,
        retrieval_context=resp.get("raw_results") if isinstance(resp.get("raw_results"), list) else [],
        ogcf_meta_present=bool(snapshot.get("ogcf_meta_present")),
    )
    return adaptive_behavior_shadow_advisories(
        query=str(request(event).get("query") or resp.get("query") or ""),
        answer=str(resp.get("answer") or ""),
        evidence=resp.get("evidence") if isinstance(resp.get("evidence"), list) else [],
        stale_context=resp.get("stale_context") if isinstance(resp.get("stale_context"), list) else [],
        adaptive_context=context,
        resolver_shadow=resp.get("resolver_shadow") if isinstance(resp.get("resolver_shadow"), dict) else None,
        config=config,
    )


def selected_count(ask_event: dict[str, Any], shadow_payload: dict[str, Any]) -> int:
    diagnostics = shadow_payload.get("diagnostics") if isinstance(shadow_payload.get("diagnostics"), dict) else {}
    if "selected_evidence_count" in diagnostics:
        try:
            return int(diagnostics.get("selected_evidence_count") or 0)
        except (TypeError, ValueError):
            pass
    evidence = response(ask_event).get("evidence")
    return len(evidence) if isinstance(evidence, list) else 0


def expected_advisory(
    *,
    label: str,
    behavior_family: str,
    ask_event: dict[str, Any],
    shadow_payload: dict[str, Any],
) -> str:
    count = selected_count(ask_event, shadow_payload)
    answer = str(response(ask_event).get("answer") or "")
    refusal = answer_has_refusal(answer)
    stale = bool((shadow_payload.get("diagnostics") or {}).get("stale_context_count")) or "stale" in label

    if behavior_family == "supported_evidence":
        if count <= 0:
            return "likely_harmful"
        if label in POSITIVE_ANSWER_LABELS:
            return "likely_helpful"
        if label in NEGATIVE_ANSWER_LABELS:
            return "likely_harmful"
    if behavior_family == "missing_support":
        if count <= 0 and (refusal or label in {"answer_correct", "answer_missing_support"}):
            return "likely_helpful"
        if count > 0 and label in POSITIVE_ANSWER_LABELS:
            return "uncertain_keep_symbolic"
        if label in {"answer_missing_support", "answer_overconfident"}:
            return "likely_helpful"
    if behavior_family == "stale_conflict":
        if stale or label in {"answer_stale", "answer_conflict_not_disclosed"}:
            return "likely_helpful"
        return "uncertain_keep_symbolic"
    if behavior_family == "wrong_scope":
        if label == "answer_wrong_scope":
            return "likely_helpful"
        return "uncertain_keep_symbolic"
    if behavior_family == "ogcf_bridge_warning":
        if label == "answer_bridge_warning_useful":
            return "likely_helpful"
        if label == "answer_bridge_warning_noise":
            return "likely_harmful"
    return "uncertain_keep_symbolic"


def evaluate_decisions(log_path: Path, *, replay_current: bool) -> dict[str, Any]:
    rows = read_jsonl(log_path)
    asks = {
        str(row.get("operation_id")): row
        for row in rows
        if row.get("event_type") == "ask" and row.get("operation_id")
    }
    answer_feedback = [
        row
        for row in rows
        if row.get("event_type") == "feedback"
        and feedback_scope(row) == "answer"
        and linked_operation_id(row) in asks
    ]
    config = load_config(ROOT).get("adaptive_behavior")
    decision_rows = []
    skipped = []
    for feedback in answer_feedback:
        op_id = linked_operation_id(feedback)
        ask = asks.get(op_id)
        shadow_payload = replay_shadow(ask or {}, config) if replay_current else shadow(ask or {})
        if not shadow_payload:
            skipped.append({"operation_id": op_id, "reason": "missing_shadow"})
            continue
        label = feedback_label(feedback)
        for decision in shadow_payload.get("decisions") or []:
            if not isinstance(decision, dict):
                continue
            expected = expected_advisory(
                label=label,
                behavior_family=str(decision.get("behavior_family") or ""),
                ask_event=ask,
                shadow_payload=shadow_payload,
            )
            actual = str(decision.get("advisory") or "")
            decision_rows.append(
                {
                    "operation_id": op_id,
                    "query": request(ask).get("query") or response(ask).get("query"),
                    "label": label,
                    "behavior_family": decision.get("behavior_family"),
                    "actual_advisory": actual,
                    "expected_advisory": expected,
                    "matches_expected": actual == expected,
                    "shadow_probability": decision.get("shadow_probability"),
                    "selected_evidence_count": selected_count(ask, shadow_payload),
                    "answer_has_refusal": answer_has_refusal(str(response(ask).get("answer") or "")),
                    "reasons": decision.get("reasons") or [],
                }
            )
    by_family: dict[str, Counter[str]] = defaultdict(Counter)
    by_label: dict[str, Counter[str]] = defaultdict(Counter)
    mismatch_examples = []
    for row in decision_rows:
        family = str(row.get("behavior_family") or "unknown")
        label = str(row.get("label") or "unknown")
        by_family[family]["total"] += 1
        by_family[family]["matches"] += int(bool(row["matches_expected"]))
        by_family[family][f"actual:{row['actual_advisory']}"] += 1
        by_family[family][f"expected:{row['expected_advisory']}"] += 1
        by_label[label]["total"] += 1
        by_label[label]["matches"] += int(bool(row["matches_expected"]))
        by_label[label][f"actual:{row['actual_advisory']}"] += 1
        if not row["matches_expected"]:
            mismatch_examples.append(row)

    def summarize(counter: Counter[str]) -> dict[str, Any]:
        total = int(counter.get("total", 0))
        matches = int(counter.get("matches", 0))
        return {
            **dict(sorted(counter.items())),
            "match_rate": round(matches / total, 6) if total else 0.0,
        }

    family_summary = {key: summarize(value) for key, value in sorted(by_family.items())}
    label_summary = {key: summarize(value) for key, value in sorted(by_label.items())}
    total = len(decision_rows)
    matches = sum(1 for row in decision_rows if row["matches_expected"])
    return {
        "schema": "adaptive_behavior_shadow_real_log_calibration/v1",
        "ok": bool(decision_rows),
        "mode": "replay_current_runtime_logic" if replay_current else "logged_runtime_shadow",
        "log_path": str(log_path),
        "ask_count": len(asks),
        "answer_feedback_count": len(answer_feedback),
        "decision_count": total,
        "skipped_count": len(skipped),
        "overall_match_rate": round(matches / total, 6) if total else 0.0,
        "advisory_counts": dict(Counter(row["actual_advisory"] for row in decision_rows).most_common()),
        "expected_counts": dict(Counter(row["expected_advisory"] for row in decision_rows).most_common()),
        "family_summary": family_summary,
        "label_summary": label_summary,
        "mismatch_count": len(mismatch_examples),
        "mismatch_examples": mismatch_examples[:40],
        "skipped": skipped[:40],
        "mutates_runtime": False,
        "mutates_config": False,
    }


def build_report(log_path: Path) -> dict[str, Any]:
    logged = evaluate_decisions(log_path, replay_current=False)
    replayed = evaluate_decisions(log_path, replay_current=True)
    return {
        "schema": "adaptive_behavior_shadow_real_log_calibration/v1",
        "ok": logged.get("ok") is True and replayed.get("ok") is True,
        "log_path": str(log_path),
        "logged_runtime_shadow": logged,
        "replayed_current_runtime_logic": replayed,
        "improvement": {
            "logged_match_rate": logged.get("overall_match_rate"),
            "replayed_match_rate": replayed.get("overall_match_rate"),
            "logged_likely_harmful": (logged.get("advisory_counts") or {}).get("likely_harmful", 0),
            "replayed_likely_harmful": (replayed.get("advisory_counts") or {}).get("likely_harmful", 0),
            "logged_uncertain": (logged.get("advisory_counts") or {}).get("uncertain_keep_symbolic", 0),
            "replayed_uncertain": (replayed.get("advisory_counts") or {}).get("uncertain_keep_symbolic", 0),
        },
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Shadow Real-Log Calibration",
        "",
        f"Passed: **{report['ok']}**",
        f"Logged match rate: `{report['improvement']['logged_match_rate']}`",
        f"Replayed current match rate: `{report['improvement']['replayed_match_rate']}`",
        f"Logged likely harmful: `{report['improvement']['logged_likely_harmful']}`",
        f"Replayed likely harmful: `{report['improvement']['replayed_likely_harmful']}`",
        "",
        "## Improvement",
        "",
        "```json",
        json.dumps(report["improvement"], indent=2),
        "```",
        "",
        "## Logged Family Summary",
        "",
        "```json",
        json.dumps(report["logged_runtime_shadow"]["family_summary"], indent=2),
        "```",
        "",
        "## Replayed Current Family Summary",
        "",
        "```json",
        json.dumps(report["replayed_current_runtime_logic"]["family_summary"], indent=2),
        "```",
        "",
        "## Replayed Current Mismatch Examples",
        "",
        "| label | family | actual | expected | query |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["replayed_current_runtime_logic"].get("mismatch_examples") or []:
        query = str(row.get("query") or "").replace("|", "\\|")[:120]
        lines.append(
            f"| `{row['label']}` | `{row['behavior_family']}` | `{row['actual_advisory']}` | "
            f"`{row['expected_advisory']}` | {query} |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate adaptive behavior shadow advisories against linked real-log feedback.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.log)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "improvement": report["improvement"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
