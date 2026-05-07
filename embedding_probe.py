from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from core.config import load_config
from core.encoder import build_encoder
from core.runtime import runtime_embedding_config


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe the configured embedding backend")
    parser.add_argument("text", nargs="*", default=["memory", "geometry", "probe"])
    parser.add_argument("--repeat", type=int, default=1, help="Embed the same text multiple times in one process")
    parser.add_argument("--vary", action="store_true", help="Append the repeat index to avoid client-cache hits")
    args = parser.parse_args()

    config = load_config(ROOT)
    encoder = build_encoder(runtime_embedding_config(config), default_dim=int(config.get("embedding_dim") or 128))
    try:
        text = " ".join(args.text)
        elapsed: list[float] = []
        vec: list[float] = []
        for idx in range(max(1, args.repeat)):
            current_text = f"{text} #{idx}" if args.vary else text
            start = time.perf_counter()
            vec = encoder.embed(current_text)
            elapsed.append(time.perf_counter() - start)
        payload = {
            "ok": True,
            "descriptor": encoder.descriptor(),
            "dim": len(vec),
            "preview": [round(x, 6) for x in vec[:8]],
            "elapsed_sec": [round(x, 6) for x in elapsed],
        }
        print(json.dumps(payload, indent=2))
    finally:
        close = getattr(encoder, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    main()
