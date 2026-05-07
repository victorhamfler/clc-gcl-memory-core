from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.pipeline import MemoryPipeline
from core.runtime import runtime_embedding_config


def main() -> None:
    config = {
        "embedding": {
            "backend": "wsl_llama_cpp",
            "model_name": "embeddinggemma-300M-Q8_0.gguf",
            "gguf_path": r"\\wsl.localhost\Ubuntu\home\victo\models\embeddinggemma-300M-Q8_0.gguf",
            "wsl_model_path": "/home/victo/models/embeddinggemma-300M-Q8_0.gguf",
            "dim": 768,
        }
    }
    previous = os.environ.get("WSL_DISTRO_NAME")
    os.environ["WSL_DISTRO_NAME"] = "Ubuntu"
    try:
        embedding = runtime_embedding_config(config)
    finally:
        if previous is None:
            os.environ.pop("WSL_DISTRO_NAME", None)
        else:
            os.environ["WSL_DISTRO_NAME"] = previous

    existing = MemoryPipeline._canonical_embedding_signature(
        {
            "backend": "wsl_llama_cpp",
            "model_name": "embeddinggemma-300M-Q8_0.gguf",
            "embedding_dim": 768,
            "model_path": r"\\wsl.localhost\Ubuntu\home\victo\models\embeddinggemma-300M-Q8_0.gguf",
        }
    )
    current = MemoryPipeline._canonical_embedding_signature(
        {
            "backend": "llama_cpp",
            "model_name": "embeddinggemma-300M-Q8_0.gguf",
            "embedding_dim": 768,
            "model_path": "/home/victo/models/embeddinggemma-300M-Q8_0.gguf",
        }
    )
    different_model = dict(current)
    different_model["model_name"] = "other-model.gguf"
    different_dim = dict(current)
    different_dim["embedding_dim"] = 384

    checks = {
        "wsl_runtime_uses_native_backend": embedding and embedding.get("backend") == "llama_cpp",
        "wsl_runtime_uses_wsl_model_path": embedding and embedding.get("gguf_path") == "/home/victo/models/embeddinggemma-300M-Q8_0.gguf",
        "windows_wsl_signature_compatible": MemoryPipeline._embedding_signatures_compatible(existing, current),
        "different_model_rejected": not MemoryPipeline._embedding_signatures_compatible(existing, different_model),
        "different_dim_rejected": not MemoryPipeline._embedding_signatures_compatible(existing, different_dim),
    }
    print(json.dumps({"ok": all(checks.values()), "checks": checks, "embedding": embedding}, indent=2))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
