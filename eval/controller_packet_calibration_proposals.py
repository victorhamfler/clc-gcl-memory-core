from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


DEFAULT_BANK = REPO_ROOT / "experiments" / "controller_packet_memory_bank_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "controller_packet_calibration_proposals_results.json"
OUT_MD = REPO_ROOT / "experiments" / "controller_packet_calibration_proposals_report.md"


def read_bank(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read controller packet memory bank {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Controller packet memory bank must be a JSON object: {path}")
    if value.get("schema") != "controller_packet_memory_bank/v1":
        raise ValueError(f"Unsupported controller packet memory bank schema: {value.get('schema')}")
    return value


def clean_cell(value: Any, limit: int = 150) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def proposal_kind(cluster: dict[str, Any]) -> tuple[str, str]:
    readiness = str(cluster.get("readiness") or "")
    residual_families = cluster.get("residual_families") if isinstance(cluster.get("residual_families"), dict) else {}
    labels = cluster.get("feedback_labels") if isinstance(cluster.get("feedback_labels"), dict) else {}
    selector = cluster.get("selector_policies") if isinstance(cluster.get("selector_policies"), dict) else {}
    if cluster.get("bridge_label_without_ogcf"):
        return (
            "bridge_metadata_gap_review",
            "Bridge-warning feedback appeared without OGCF metadata; review the test harness or runtime call path before using this as bridge calibration evidence.",
        )
    if any("answer_bridge_warning_useful" in str(label) for label in labels) and int(cluster.get("ogcf_meta_count") or 0) > 0:
        return (
            "ogcf_bridge_behavior_candidate",
            "Repeated positive bridge-warning feedback appears with OGCF metadata; collect independent logs before calibrating bridge warning behavior.",
        )
    if readiness == "calibration_candidate":
        if int(cluster.get("support") or 0) >= 2 and int(residual_families.get("supported_evidence") or 0) > 0:
            return (
                "resolver_residual_benefit_candidate",
                "Repeated positive feedback appears on supported-evidence residual opportunities; consider collecting more packets for resolver residual calibration.",
            )
        return (
            "positive_behavior_candidate",
            "Repeated positive feedback appears in one controller cluster; hold as calibration evidence.",
        )
    if readiness == "review_negative_feedback":
        if any("missing" in str(label) for label in labels):
            return (
                "missing_support_review",
                "Negative missing-support feedback recurs; review retrieval admission and resolver refusal thresholds before any promotion.",
            )
        if any("stale" in str(label) for label in labels):
            return (
                "stale_answer_review",
                "Negative stale-answer feedback recurs; review evidence-state arbitration and current/stale conflict handling.",
            )
        return (
            "negative_feedback_review",
            "Negative feedback recurs; preserve as guard evidence, not as a positive calibration candidate.",
        )
    if readiness == "review_mixed_feedback":
        return (
            "mixed_feedback_holdout",
            "Mixed positive and negative feedback requires a holdout review before calibration.",
        )
    if selector:
        return (
            "collect_more",
            "Cluster is structured but lacks enough support or clean feedback for calibration.",
        )
    return ("ignore_unstructured", "Cluster lacks enough controller structure for calibration.")


def build_proposal(cluster: dict[str, Any], index: int) -> dict[str, Any]:
    kind, recommendation = proposal_kind(cluster)
    labels = cluster.get("feedback_labels") if isinstance(cluster.get("feedback_labels"), dict) else {}
    residual = cluster.get("residual_families") if isinstance(cluster.get("residual_families"), dict) else {}
    examples = cluster.get("examples") if isinstance(cluster.get("examples"), list) else []
    return {
        "id": f"proposal_{index:03d}",
        "kind": kind,
        "readiness": cluster.get("readiness"),
        "support": int(cluster.get("support") or 0),
        "source_log_count": int(cluster.get("source_log_count") or 0),
        "feedback_labels": labels,
        "bridge_label_without_ogcf": bool(cluster.get("bridge_label_without_ogcf")),
        "ogcf_meta_count": int(cluster.get("ogcf_meta_count") or 0),
        "selector_policies": cluster.get("selector_policies") if isinstance(cluster.get("selector_policies"), dict) else {},
        "ogcf_intents": cluster.get("ogcf_intents") if isinstance(cluster.get("ogcf_intents"), dict) else {},
        "resolver_actions": cluster.get("resolver_actions") if isinstance(cluster.get("resolver_actions"), dict) else {},
        "residual_families": residual,
        "recommendation": recommendation,
        "next_test": next_test_for_kind(kind),
        "examples": examples[:5],
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def next_test_for_kind(kind: str) -> str:
    if kind == "ogcf_bridge_behavior_candidate":
        return "Collect at least one more independent OGCF bridge run and compare bridge-warning-useful/noise separation before proposing any bridge-behavior calibration."
    if kind == "resolver_residual_benefit_candidate":
        return "Replay the same packet family across at least two independent logs and compare residual-benefit helpful/harmful counts before proposing resolver calibration."
    if kind == "missing_support_review":
        return "Create or collect near-topic unsupported queries and verify the resolver refuses or lowers confidence instead of answering from weak evidence."
    if kind == "stale_answer_review":
        return "Replay current-vs-stale correction chains and verify current evidence wins unless the query explicitly asks for history."
    if kind == "mixed_feedback_holdout":
        return "Split examples by query shape and build a small holdout before any threshold proposal."
    if kind == "bridge_metadata_gap_review":
        return "Rerun bridge-warning cases with explicit ogcf_meta and verify controller packets report ogcf_meta_packets greater than zero."
    return "Collect more controller packets with linked answer and memory feedback."


def build_report(bank_path: Path) -> dict[str, Any]:
    bank = read_bank(bank_path)
    clusters = [item for item in bank.get("clusters") or [] if isinstance(item, dict)]
    proposals = [build_proposal(cluster, idx) for idx, cluster in enumerate(clusters, start=1)]
    promotion_candidates = [
        item
        for item in proposals
        if item["kind"] in {"resolver_residual_benefit_candidate", "positive_behavior_candidate", "ogcf_bridge_behavior_candidate"}
    ]
    review_items = [item for item in proposals if "review" in item["kind"] or "holdout" in item["kind"]]
    return {
        "schema": "controller_packet_calibration_proposals/v1",
        "description": "Report-only calibration proposals derived from controller packet memory-bank clusters.",
        "ok": bool(proposals),
        "source_bank": str(bank_path),
        "cluster_count": len(clusters),
        "proposal_count": len(proposals),
        "promotion_candidate_count": len(promotion_candidates),
        "review_item_count": len(review_items),
        "proposals": proposals,
        "report_only": True,
        "mutates_runtime": False,
        "mutates_config": False,
    }


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Controller Packet Calibration Proposals",
        "",
        "This report is advisory only. It does not mutate runtime behavior or config.",
        "",
        f"Passed: **{report['ok']}**",
        f"Source bank: `{report['source_bank']}`",
        f"Proposals: `{report['proposal_count']}`",
        f"Promotion candidates: `{report['promotion_candidate_count']}`",
        f"Review items: `{report['review_item_count']}`",
        "",
        "| id | kind | readiness | support | logs | labels | next test |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for proposal in report["proposals"]:
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} | `{}` | {} |".format(
                proposal["id"],
                proposal["kind"],
                proposal["readiness"],
                proposal["support"],
                proposal["source_log_count"],
                clean_cell(", ".join(proposal["feedback_labels"].keys())),
                clean_cell(proposal["next_test"]),
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build report-only calibration proposals from a controller packet memory bank.")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    report = build_report(args.bank)
    write_report(report, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "proposal_count": report["proposal_count"],
                "promotion_candidate_count": report["promotion_candidate_count"],
                "review_item_count": report["review_item_count"],
                "json": str(args.out_json),
                "markdown": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
