from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serve import MemoryApi


def main() -> None:
    with TemporaryDirectory() as tmp:
        api = MemoryApi(ROOT, db_path=Path(tmp) / "agent_plan_regression.db")
        try:
            plan = api.agent_plan(
                {
                    "instruction": "Remember that Victor prefers qwen for memory planning.",
                    "namespace": "agent:planner",
                    "mock_plan": {
                        "summary": "Store a durable preference.",
                        "actions": [
                            {
                                "endpoint": "/teach",
                                "payload": {
                                    "text": "Victor prefers qwen for memory planning.",
                                    "memory_type": "preference",
                                },
                                "reason": "The instruction is a durable user preference.",
                            },
                            {
                                "endpoint": "/query",
                                "payload": {"query": "Victor qwen memory planning"},
                                "reason": "Inspect similar memories before storing if desired.",
                            },
                            {
                                "endpoint": "/shutdown",
                                "payload": {},
                                "reason": "Invalid and should be ignored.",
                            },
                        ],
                        "warnings": [],
                    },
                }
            )
            assert plan["ok"] is True, plan
            assert plan["requires_confirmation"] is True, plan
            assert len(plan["actions"]) == 2, plan
            assert plan["actions"][0]["endpoint"] == "/teach", plan
            assert plan["actions"][0]["payload"]["namespace"] == "agent:planner", plan
            assert plan["actions"][1]["endpoint"] == "/retrieve", plan
            assert any("unsupported endpoint" in warning for warning in plan["warnings"]), plan
        finally:
            api.close()
    print("agent_plan_regression: PASS")


if __name__ == "__main__":
    main()
