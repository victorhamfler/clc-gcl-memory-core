from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from core.retrieval_signals import RetrievalSignalScorer  # noqa: E402


OUT_JSON = REPO_ROOT / "experiments" / "retrieval_signals_module_smoke_results.json"
OUT_MD = REPO_ROOT / "experiments" / "retrieval_signals_module_smoke_report.md"


def main() -> int:
    scorer = RetrievalSignalScorer()
    custom_scorer = RetrievalSignalScorer(
        signal_config={
            "broad_generic": {
                "source_contains": "mission_control",
                "text_prefixes": "global operations note",
                "penalty": 0.21,
            },
            "scope_deflection": {
                "query_terms": "transfer",
                "correction_prefixes": "correction:",
                "text_markers": "not transfer approval",
                "penalty": 0.42,
            },
            "correction_relevance": {
                "match_threshold": 0.9,
                "min_relevance": 0.22,
            },
        }
    )
    checks = [
        {
            "id": "claim_scope_deadline_matches_deadline_source",
            "ok": scorer.claim_scope_affinity(
                "What is the deadline for deadline_report?",
                "The deadline report is due Friday.",
                "project/deadline_report.md",
            )
            >= 0.75,
        },
        {
            "id": "answer_type_owner_positive",
            "ok": scorer.answer_type_affinity(
                "Who owns the report?",
                "Mina is the owner of the report.",
            )
            == 1.0,
        },
        {
            "id": "answer_type_deadline_blocks_owner_answer",
            "ok": scorer.answer_type_affinity(
                "What is the deadline?",
                "Mina owns the report.",
            )
            == -1.0,
        },
        {
            "id": "scope_deflection_detects_negative_permission",
            "ok": scorer.scope_deflection_note(
                "Can you upload the repository to GitHub?",
                "Correction: this is not permission to upload. It is a separate policy note.",
                "correction/policy.md",
            ),
        },
        {
            "id": "correction_relevance_damps_near_topic_miss",
            "ok": scorer.correction_relevance(
                {"authority_state": "current"},
                0.7,
                0.0,
                0.2,
                0.3,
            )
            == 0.3,
        },
        {
            "id": "custom_broad_generic_source_marker",
            "ok": custom_scorer.broad_generic_note(
                "Operational note for all systems.",
                "notes/mission_control.md",
            ),
        },
        {
            "id": "custom_scope_deflection_marker",
            "ok": custom_scorer.scope_deflection_note(
                "Can I transfer the repository?",
                "Correction: this is not transfer approval.",
                "correction/transfer_policy.md",
            ),
        },
        {
            "id": "custom_correction_relevance_minimum",
            "ok": custom_scorer.correction_relevance(
                {"authority_state": "current"},
                0.7,
                0.0,
                0.2,
                0.1,
            )
            == 0.22,
        },
    ]
    ok = all(check["ok"] for check in checks)
    payload = {"ok": ok, "checks": checks}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    OUT_MD.write_text(
        "# Retrieval Signals Module Smoke\n\n"
        + f"Result: {'PASS' if ok else 'FAIL'}\n\n"
        + "\n".join(f"- {check['id']}: {'PASS' if check['ok'] else 'FAIL'}" for check in checks)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({**payload, "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
