from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.resolver import resolve_answer


def row(memory_id: str, text: str, source: str = "test.md", score: float = 0.8) -> dict:
    return {
        "memory_id": memory_id,
        "score": score,
        "cosine": score,
        "source": source,
        "domain_name": "agent_memory",
        "memory_type": "design_rule",
        "feedback_score": 0.0,
        "supersession_score": 1.0,
        "relation_supersession_score": 0.5,
        "text": text,
    }


def main() -> None:
    correction_only = resolve_answer(
        "What is the current agent name?",
        [
            row(
                "mem_correction_name",
                "Correction: the current agent name is LoomGuide, not NovaDesk.",
                "corrections_v2.md",
            )
        ],
    )
    stable_preference = resolve_answer(
        "What are Mira's preferences for Git commits and GitHub uploads?",
        [
            row(
                "mem_stable_preference",
                "Current GitHub upload preference: GitHub uploads happen only when Mira explicitly asks. The assistant must not push automatically after documentation edits.",
                "user_preferences_v2.md",
            )
        ],
    )
    adaptation_note = resolve_answer(
        "How should the memory system test adaptation after instructions change?",
        [
            row(
                "mem_adaptation",
                "The expected result is not deletion. The expected result is adaptive ranking: current v2 knowledge should be retrieved above stale v1 knowledge for corrected facts.",
                "adaptation_protocol_v2.md",
            )
        ],
    )

    assert correction_only["conflict"] is True
    assert "corrected memory evidence" in correction_only["answer"].lower()
    assert stable_preference["conflict"] is False
    assert adaptation_note["conflict"] is False

    print(
        json.dumps(
            {
                "ok": True,
                "correction_only": {
                    "conflict": correction_only["conflict"],
                    "answer": correction_only["answer"],
                },
                "stable_preference": {
                    "conflict": stable_preference["conflict"],
                    "answer": stable_preference["answer"],
                },
                "adaptation_note": {
                    "conflict": adaptation_note["conflict"],
                    "answer": adaptation_note["answer"],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
