from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.answer_behavior_shadow import resolver_shadow_actions


DEFAULT_LOGS = [
    REPO_ROOT / "experiments" / "answer_behavior_ogcf_bridge_worklog.jsonl",
    REPO_ROOT / "agent_logs_collection" / "neural_symbolic_outcome_holdout_workflow.jsonl",
    REPO_ROOT / "agent_logs_collection" / "answer_behavior_real_log_missing_cases.jsonl",
]
DEFAULT_DATASET = REPO_ROOT / "experiments" / "resolver_shadow_outcome_dataset_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "resolver_shadow_threshold_calibration_results.json"
OUT_MD = REPO_ROOT / "experiments" / "resolver_shadow_threshold_calibration_report.md"


BRIDGE_USEFUL = {"answer_bridge_warning_useful"}
BRIDGE_NOISE = {"answer_bridge_warning_noise"}
SUPPORTED = {"answer_correct", "answer_good_citation"}
MISSING_SUPPORT = {"answer_missing_support", "answer_overconfident"}
STALE = {"answer_stale", "answer_conflict_not_disclosed"}
ANSWER_LABELS = BRIDGE_USEFUL | BRIDGE_NOISE | SUPPORTED | MISSING_SUPPORT | STALE | {"answer_bad_citation", "answer_wrong_scope"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def nested(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def payload(event: dict[str, Any]) -> dict[str, Any]:
    return nested(event, "payload")


def label(event: dict[str, Any]) -> str:
    req = nested(payload(event), "request")
    fb = nested(payload(event), "feedback")
    return str(req.get("label") or fb.get("label") or "").strip().lower()


def scope(event: dict[str, Any]) -> str:
    req = nested(payload(event), "request")
    fb = nested(payload(event), "feedback")
    return str(req.get("feedback_scope") or fb.get("feedback_scope") or "").strip().lower()


def linked_id(event: dict[str, Any]) -> str:
    req = nested(payload(event), "request")
    return str(event.get("linked_operation_id") or req.get("linked_operation_id") or "").strip()


def ask_request(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "request")


def ask_response(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "response")


def selector_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    adaptive = adaptive_memory_context(event)
    snapshot = adaptive.get("selector_snapshot")
    if isinstance(snapshot, dict):
        return snapshot
    return nested(payload(event), "selector_snapshot")


def adaptive_memory_context(event: dict[str, Any]) -> dict[str, Any]:
    return nested(payload(event), "adaptive_memory_context")


def diagnostics(event: dict[str, Any]) -> dict[str, Any]:
    adaptive = adaptive_memory_context(event)
    diag = adaptive.get("diagnostics")
    if isinstance(diag, dict):
        return diag
    return nested(selector_snapshot(event), "diagnostics")


def parse_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths


def collect_cases(log_paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for log_path in log_paths:
        rows = read_jsonl(log_path)
        asks = {
            str(row.get("operation_id")): row
            for row in rows
            if str(row.get("event_type") or "").lower() == "ask" and row.get("operation_id")
        }
        for event in rows:
            if str(event.get("event_type") or "").lower() != "feedback":
                continue
            label_value = label(event)
            if scope(event) != "answer" and not label_value.startswith("answer_"):
                continue
            if label_value not in ANSWER_LABELS:
                skipped.append({"source_log": str(log_path), "id": event.get("operation_id"), "reason": "unsupported_label", "label": label_value})
                continue
            ask = asks.get(linked_id(event))
            if not ask:
                skipped.append({"source_log": str(log_path), "id": event.get("operation_id"), "reason": "missing_linked_ask", "label": label_value})
                continue
            diag = diagnostics(ask)
            cases.append(
                {
                    "id": event.get("operation_id"),
                    "source_log": str(log_path),
                    "linked_operation_id": linked_id(event),
                    "label": label_value,
                    "query": ask_request(ask).get("query"),
                    "ask": ask,
                    "ogcf_bridge_overload_score": _float(diag.get("ogcf_bridge_overload_score"), 0.0),
                    "ogcf_effective_affected_memory_ratio": _float(
                        diag.get("ogcf_effective_affected_memory_ratio"),
                        0.0,
                    ),
                    "ogcf_intent": diag.get("ogcf_intent"),
                }
            )
    return cases, skipped


def collect_cases_from_dataset(dataset_paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for dataset_path in dataset_paths:
        dataset = read_json(dataset_path)
        if dataset.get("schema") != "resolver_shadow_outcome_dataset/v1":
            skipped.append({"source_dataset": str(dataset_path), "reason": "unsupported_schema", "schema": dataset.get("schema")})
            continue
        examples = dataset.get("examples")
        if not isinstance(examples, list):
            skipped.append({"source_dataset": str(dataset_path), "reason": "missing_examples"})
            continue
        for example in examples:
            if not isinstance(example, dict):
                skipped.append({"source_dataset": str(dataset_path), "reason": "invalid_example"})
                continue
            label_value = str(example.get("label") or "").strip().lower()
            if label_value not in ANSWER_LABELS:
                skipped.append({"source_dataset": str(dataset_path), "id": example.get("id"), "reason": "unsupported_label", "label": label_value})
                continue
            cases.append(
                {
                    "id": example.get("id"),
                    "source_dataset": str(dataset_path),
                    "source_log": example.get("source_log"),
                    "linked_operation_id": example.get("linked_operation_id"),
                    "label": label_value,
                    "query": example.get("query"),
                    "selected_evidence_count": int(_float(example.get("selected_evidence_count"), 0)),
                    "stale_context_count": int(_float(example.get("stale_context_count"), 0)),
                    "ogcf_meta_present": bool(example.get("ogcf_meta_present")),
                    "ogcf_bridge_overload_score": _float(example.get("ogcf_bridge_overload_score"), 0.0),
                    "ogcf_effective_affected_memory_ratio": _float(
                        example.get("ogcf_effective_affected_memory_ratio"),
                        0.0,
                    ),
                    "ogcf_intent": example.get("ogcf_intent"),
                    "ordinary_fact_lookup": bool(example.get("ordinary_fact_lookup")),
                    "stale_conflict": bool(example.get("stale_conflict")),
                }
            )
    return cases, skipped


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def expected_for(label_value: str, shadow: dict[str, Any]) -> tuple[set[str], set[str]]:
    expected: set[str] = set()
    forbidden: set[str] = set()
    if label_value in SUPPORTED:
        expected.add("require_evidence_backed_answer")
    if label_value in BRIDGE_USEFUL:
        expected.add("emit_ogcf_bridge_warning")
        expected.add("require_evidence_backed_answer")
    if label_value in BRIDGE_NOISE:
        forbidden.add("emit_ogcf_bridge_warning")
    if label_value in MISSING_SUPPORT:
        expected.add("preserve_missing_support_refusal")
        forbidden.add("emit_ogcf_bridge_warning")
    if label_value in STALE or shadow.get("diagnostics", {}).get("stale_conflict"):
        expected.add("disclose_stale_conflict")
    if label_value in {"answer_bad_citation", "answer_wrong_scope"}:
        expected.add("require_evidence_backed_answer")
    return expected, forbidden


def run_shadow(case: dict[str, Any], score_threshold: float, effective_threshold: float) -> dict[str, Any]:
    if "ask" not in case:
        return run_shadow_from_dataset_case(case, score_threshold, effective_threshold)
    ask = case["ask"]
    response = ask_response(ask)
    return resolver_shadow_actions(
        query=str(ask_request(ask).get("query") or ""),
        answer=str(response.get("answer") or ""),
        evidence=response.get("evidence") or [],
        stale_context=response.get("stale_context") or [],
        selector_snapshot=selector_snapshot(ask),
        conflict=bool(response.get("conflict")),
        config={
            "enabled": True,
            "bridge_warning_score_threshold": score_threshold,
            "bridge_warning_effective_ratio_threshold": effective_threshold,
        },
    )


def run_shadow_from_dataset_case(case: dict[str, Any], score_threshold: float, effective_threshold: float) -> dict[str, Any]:
    actions: list[str] = []
    selected_evidence_count = int(case.get("selected_evidence_count") or 0)
    stale_context_count = int(case.get("stale_context_count") or 0)
    stale_conflict = bool(case.get("stale_conflict")) or stale_context_count > 0
    bridge_score = _float(case.get("ogcf_bridge_overload_score"), 0.0)
    effective_ratio = _float(case.get("ogcf_effective_affected_memory_ratio"), 0.0)
    ogcf_meta_present = bool(case.get("ogcf_meta_present"))
    ordinary_fact_lookup = bool(case.get("ordinary_fact_lookup"))

    if selected_evidence_count > 0:
        actions.append("require_evidence_backed_answer")
    else:
        actions.append("preserve_missing_support_refusal")

    if stale_conflict:
        actions.append("disclose_stale_conflict")

    if (
        selected_evidence_count > 0
        and ogcf_meta_present
        and not ordinary_fact_lookup
        and (bridge_score >= score_threshold or effective_ratio >= effective_threshold)
    ):
        actions.append("emit_ogcf_bridge_warning")

    return {
        "actions": actions,
        "diagnostics": {
            "selected_evidence_count": selected_evidence_count,
            "stale_context_count": stale_context_count,
            "stale_conflict": stale_conflict,
            "ogcf_bridge_overload_score": bridge_score,
            "ogcf_effective_affected_memory_ratio": effective_ratio,
            "ogcf_meta_present": ogcf_meta_present,
            "ordinary_fact_lookup": ordinary_fact_lookup,
        },
        "mutates_answer": False,
        "mutates_config": False,
    }


def evaluate_thresholds(cases: list[dict[str, Any]], score_threshold: float, effective_threshold: float) -> dict[str, Any]:
    evaluated = []
    fp_bridge = 0
    fn_bridge = 0
    total_bridge_useful = 0
    total_bridge_noise = 0
    for case in cases:
        shadow = run_shadow(case, score_threshold, effective_threshold)
        expected, forbidden = expected_for(case["label"], shadow)
        actual = set(shadow.get("actions") or [])
        missing = sorted(expected - actual)
        forbidden_hits = sorted(forbidden & actual)
        if case["label"] in BRIDGE_USEFUL:
            total_bridge_useful += 1
            if "emit_ogcf_bridge_warning" in missing:
                fn_bridge += 1
        if case["label"] in BRIDGE_NOISE:
            total_bridge_noise += 1
            if "emit_ogcf_bridge_warning" in forbidden_hits:
                fp_bridge += 1
        evaluated.append(
            {
                "id": case["id"],
                "label": case["label"],
                "query": case["query"],
                "actions": shadow.get("actions") or [],
                "missing_expected": missing,
                "forbidden_hits": forbidden_hits,
                "passed": not missing and not forbidden_hits,
            }
        )
    passed = sum(1 for item in evaluated if item["passed"])
    return {
        "score_threshold": score_threshold,
        "effective_ratio_threshold": effective_threshold,
        "case_count": len(cases),
        "passed_count": passed,
        "failed_count": len(cases) - passed,
        "bridge_false_positive_count": fp_bridge,
        "bridge_false_negative_count": fn_bridge,
        "bridge_useful_count": total_bridge_useful,
        "bridge_noise_count": total_bridge_noise,
        "ok": bool(cases) and passed == len(cases),
        "cases": evaluated,
    }


def threshold_grid(values: list[str] | None, default: list[float]) -> list[float]:
    if not values:
        return default
    out: list[float] = []
    for value in values:
        for part in str(value).split(","):
            if part.strip():
                out.append(float(part.strip()))
    return sorted(set(out))


def choose_candidate(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None
    sorted_results = sorted(
        results,
        key=lambda item: (
            item["failed_count"],
            item["bridge_false_positive_count"] * 4 + item["bridge_false_negative_count"] * 3,
            item["bridge_false_positive_count"],
            item["bridge_false_negative_count"],
            -(item["score_threshold"] + item["effective_ratio_threshold"]),
        ),
    )
    return sorted_results[0]


def build_report(
    log_paths: list[Path],
    score_values: list[float],
    effective_values: list[float],
    *,
    input_mode: str = "raw_logs",
    dataset_paths: list[Path] | None = None,
) -> dict[str, Any]:
    cases, skipped = collect_cases(log_paths)
    return build_report_from_cases(
        cases,
        skipped,
        score_values,
        effective_values,
        input_mode=input_mode,
        log_paths=log_paths,
        dataset_paths=dataset_paths or [],
    )


def build_report_from_dataset(dataset_paths: list[Path], score_values: list[float], effective_values: list[float]) -> dict[str, Any]:
    cases, skipped = collect_cases_from_dataset(dataset_paths)
    source_logs = sorted({str(case.get("source_log")) for case in cases if case.get("source_log")})
    return build_report_from_cases(
        cases,
        skipped,
        score_values,
        effective_values,
        input_mode="dataset",
        log_paths=[Path(path) for path in source_logs],
        dataset_paths=dataset_paths,
    )


def build_report_from_cases(
    cases: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    score_values: list[float],
    effective_values: list[float],
    *,
    input_mode: str,
    log_paths: list[Path],
    dataset_paths: list[Path],
) -> dict[str, Any]:
    results = [
        evaluate_thresholds(cases, score, effective)
        for score in score_values
        for effective in effective_values
    ]
    candidate = choose_candidate(results)
    perfect = [item for item in results if item["ok"]]
    label_counts: dict[str, int] = {}
    for case in cases:
        label_counts[case["label"]] = label_counts.get(case["label"], 0) + 1
    return {
        "schema": "resolver_shadow_threshold_calibration/v1",
        "description": "Report-only threshold sweep for resolver-shadow OGCF bridge warning actions.",
        "ok": bool(candidate) and candidate["ok"],
        "input_mode": input_mode,
        "dataset_paths": [str(path) for path in dataset_paths],
        "log_paths": [str(path) for path in log_paths],
        "case_count": len(cases),
        "skipped_count": len(skipped),
        "label_counts": dict(sorted(label_counts.items())),
        "score_values": score_values,
        "effective_ratio_values": effective_values,
        "candidate": candidate,
        "perfect_candidate_count": len(perfect),
        "top_results": sorted(results, key=lambda item: (item["failed_count"], item["bridge_false_positive_count"], item["bridge_false_negative_count"]))[:10],
        "skipped": skipped[:50],
        "mutates_config": False,
        "mutates_runtime": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    candidate = report.get("candidate") or {}
    lines = [
        "# Resolver Shadow Threshold Calibration",
        "",
        "This calibration is advisory only. It does not modify runtime config or resolver behavior.",
        "",
        f"Passed: **{report['ok']}**",
        f"Input mode: `{report.get('input_mode') or 'raw_logs'}`",
        f"Cases: `{report['case_count']}`",
        f"Skipped: `{report['skipped_count']}`",
        f"Perfect candidates: `{report['perfect_candidate_count']}`",
        "",
        "## Recommended Candidate",
        "",
        f"- Bridge score threshold: `{candidate.get('score_threshold')}`",
        f"- Effective affected-ratio threshold: `{candidate.get('effective_ratio_threshold')}`",
        f"- Failed cases: `{candidate.get('failed_count')}`",
        f"- Bridge false positives: `{candidate.get('bridge_false_positive_count')}`",
        f"- Bridge false negatives: `{candidate.get('bridge_false_negative_count')}`",
        "",
        "## Label Counts",
        "",
        "```json",
        json.dumps(report.get("label_counts") or {}, indent=2),
        "```",
        "",
        "## Top Thresholds",
        "",
        "| score | effective | pass | failed | bridge FP | bridge FN |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report.get("top_results") or []:
        lines.append(
            f"| {item['score_threshold']} | {item['effective_ratio_threshold']} | {item['passed_count']} | "
            f"{item['failed_count']} | {item['bridge_false_positive_count']} | {item['bridge_false_negative_count']} |"
        )
    if candidate.get("cases"):
        lines.extend(["", "## Candidate Case Results", "", "| case | label | pass | actions | missing | forbidden | query |", "| --- | --- | --- | --- | --- | --- | --- |"])
        for case in candidate["cases"]:
            query = str(case.get("query") or "").replace("|", "\\|")
            lines.append(
                f"| `{case['id']}` | `{case['label']}` | `{case['passed']}` | "
                f"`{', '.join(case.get('actions') or [])}` | `{', '.join(case.get('missing_expected') or [])}` | "
                f"`{', '.join(case.get('forbidden_hits') or [])}` | {query[:120]} |"
            )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate resolver-shadow OGCF bridge warning thresholds.")
    parser.add_argument("--dataset", action="append", default=None)
    parser.add_argument("--log", action="append", default=None)
    parser.add_argument("--score-thresholds", action="append", default=None)
    parser.add_argument("--effective-thresholds", action="append", default=None)
    parser.add_argument("--out-json", default=str(OUT_JSON))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    datasets = parse_paths(args.dataset)
    logs = parse_paths(args.log)
    score_values = threshold_grid(args.score_thresholds, [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95])
    effective_values = threshold_grid(args.effective_thresholds, [0.10, 0.25, 0.35, 0.50, 0.65, 0.75, 0.90, 0.95])
    if datasets:
        report = build_report_from_dataset(datasets, score_values, effective_values)
    elif not logs and DEFAULT_DATASET.exists():
        report = build_report_from_dataset([DEFAULT_DATASET], score_values, effective_values)
    else:
        logs = logs or [path for path in DEFAULT_LOGS if path.exists()]
        report = build_report(logs, score_values, effective_values)
    write_report(report, Path(args.out_json), Path(args.out_md))
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "case_count": report["case_count"],
                "perfect_candidate_count": report["perfect_candidate_count"],
                "candidate": {
                    key: (report.get("candidate") or {}).get(key)
                    for key in (
                        "score_threshold",
                        "effective_ratio_threshold",
                        "failed_count",
                        "bridge_false_positive_count",
                        "bridge_false_negative_count",
                    )
                },
                "json": str(Path(args.out_json)),
                "markdown": str(Path(args.out_md)),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
