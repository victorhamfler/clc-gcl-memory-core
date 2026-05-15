from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.llm_client import LLMClientError, OpenAICompatibleLLMClient


def main() -> None:
    calls: list[str] = []
    client = OpenAICompatibleLLMClient(
        {
            "base_url": "https://example.invalid/v1",
            "model": "primary-model",
            "fallback_models": "fallback-model",
            "max_retries": 0,
        }
    )

    def fake_post(url, body, headers, timeout, max_retries, retry_backoff):
        import json

        model = json.loads(body.decode("utf-8"))["model"]
        calls.append(model)
        if model == "primary-model":
            raise LLMClientError("LLM request failed: HTTP 429: quota exceeded")
        return {"choices": [{"message": {"content": '[{"fact":"fallback worked","type":"semantic_note","confidence":0.9}]'}}]}

    client._post_with_retries = fake_post  # type: ignore[method-assign]
    facts = client.extract_facts("fallback worked", "Extract fallback worked")
    assert calls == ["primary-model", "fallback-model"], calls
    assert client.last_model == "fallback-model", client.last_model
    assert facts[0]["fact"] == "fallback worked", facts
    print("llm_fallback_regression: PASS")


if __name__ == "__main__":
    main()
