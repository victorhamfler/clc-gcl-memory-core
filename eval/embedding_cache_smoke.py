from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.encoder import DiskEmbeddingCache, embedding_cache_key


def main() -> None:
    with TemporaryDirectory() as tmp:
        cache_path = Path(tmp) / "embedding_cache.sqlite"
        namespace = embedding_cache_key("test-backend", "test-model", 128)
        key = embedding_cache_key(namespace, "hello cached memory")
        vector = [0.1, 0.2, 0.3]

        cache = DiskEmbeddingCache(cache_path, namespace)
        try:
            empty = cache.get(key)
            cache.set(key, vector)
            first = cache.get(key)
            second = cache.get(key)
            stats = cache.stats()
        finally:
            cache.close()

    checks = {
        "missing_key_returns_none": empty is None,
        "first_read_matches_vector": first == vector,
        "second_read_matches_vector": second == vector,
        "stats_count_entry": stats["entries"] == 1,
        "stats_count_hits": stats["hits"] == 2,
    }
    payload = {"ok": all(checks.values()), "checks": checks, "stats": stats}
    print(json.dumps(payload, indent=2))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
