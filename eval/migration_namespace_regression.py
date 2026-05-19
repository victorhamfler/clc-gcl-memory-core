from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serve import MemoryApi


def main() -> None:
    with TemporaryDirectory() as tmp:
        api = MemoryApi(ROOT, db_path=Path(tmp) / "migration_namespace_regression.db")
        try:
            batch = api.ingest_batch(
                {
                    "items": [
                        {
                            "text": "Migration namespace fact: Redwood Lantern belongs to Hermes.",
                            "namespace": "agent:hermes",
                            "source": "migration/hermes.md",
                            "memory_type": "semantic_note",
                        },
                        {
                            "text": "Migration namespace fact: Blue Harbor is a global migration marker.",
                            "namespace": "global",
                            "source": "migration/global.md",
                            "memory_type": "semantic_note",
                        },
                    ],
                    "namespace": "agent:wrong-default",
                }
            )
            assert batch["stored"] == 2, batch
            assert batch["namespaces"] == {"agent:hermes": 1, "global": 1}, batch
            counts = {item["namespace"]: item["count"] for item in api.stats()["namespaces_detail"]}
            assert counts.get("agent:hermes") == 1, counts
            assert counts.get("global") == 1, counts

            hermes = api.ask(
                {
                    "query": "Who owns Redwood Lantern?",
                    "namespace": "agent:hermes",
                    "include_global": False,
                    "store_session": False,
                }
            )
            assert hermes["evidence"], hermes
            assert hermes["evidence"][0]["namespace"] == "agent:hermes", hermes

            isolated = MemoryApi(ROOT, db_path=Path(tmp) / "isolated_namespace_warning.db")
            try:
                isolated.ingest_batch(
                    {
                        "items": [
                            {
                                "text": "Hermes-only migration marker: Silver Delta lives outside global.",
                                "namespace": "agent:hermes",
                            }
                        ]
                    }
                )
                missing = isolated.ask(
                    {
                        "query": "What is Silver Delta?",
                        "namespace": "global",
                        "include_global": True,
                        "store_session": False,
                    }
                )
                assert not missing["evidence"], missing
                assert missing["namespace_warning"], missing
                validation = isolated.migration_validate({"query": "What is Silver Delta?", "namespace": "global"})
                assert validation["smoke"]["namespace_warning"], validation
            finally:
                isolated.close()
        finally:
            api.close()
    print("migration_namespace_regression: PASS")


if __name__ == "__main__":
    main()
