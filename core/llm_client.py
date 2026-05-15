from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


class LLMClientError(RuntimeError):
    pass


class OpenAICompatibleLLMClient:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = dict(config or {})
        self.last_usage: dict[str, Any] = {}
        self.last_model: str | None = None

    def extract_facts(self, text: str, prompt: str) -> list[dict[str, Any]]:
        provider = str(self.config.get("provider") or "custom").strip().lower()
        if provider == "mock":
            return self._mock_facts()
        raw = self._chat_completion(prompt)
        return parse_json_facts(raw)

    def _mock_facts(self) -> list[dict[str, Any]]:
        value = self.config.get("mock_facts") or self.config.get("mock_response") or []
        if isinstance(value, str):
            return parse_json_facts(value)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    def _chat_completion(self, prompt: str) -> str:
        base_url = str(self.config.get("base_url") or "").rstrip("/")
        if not base_url:
            raise LLMClientError("llm.base_url is required for non-mock providers")
        models = self._models()
        if not models:
            raise LLMClientError("llm.model is required for non-mock providers")
        api_key = self._api_key()
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": str(self.config.get("user_agent") or "CLC-GCL-Memory/1.0"),
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        timeout = float(self.config.get("timeout") or 30)
        max_retries = max(0, int(self.config.get("max_retries") if self.config.get("max_retries") is not None else 2))
        retry_backoff = max(0.0, float(self.config.get("retry_backoff") if self.config.get("retry_backoff") is not None else 1.5))
        errors: list[str] = []
        data: dict[str, Any] | None = None
        for idx, model in enumerate(models):
            payload = {
                "model": model,
                "temperature": float(self.config.get("temperature") or 0.1),
                "max_tokens": int(self.config.get("max_tokens") or 2048),
                "messages": [
                    {
                        "role": "system",
                        "content": "Return only valid JSON for the requested extraction task.",
                    },
                    {"role": "user", "content": prompt},
                ],
            }
            body = json.dumps(payload).encode("utf-8")
            try:
                data = self._post_with_retries(url, body, headers, timeout, max_retries, retry_backoff)
                self.last_model = model
                break
            except LLMClientError as exc:
                errors.append(f"{model}: {exc}")
                if idx >= len(models) - 1 or not self._should_fallback(exc):
                    raise
        if data is None:
            raise LLMClientError(f"LLM request failed for all configured models: {'; '.join(errors)}")
        try:
            self.last_usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError("LLM response did not contain choices[0].message.content") from exc

    def _post_with_retries(
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
        timeout: float,
        max_retries: int,
        retry_backoff: float,
    ) -> dict[str, Any]:
        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                body_preview = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code in retryable_statuses and attempt < max_retries:
                    time.sleep(self._retry_delay(exc, attempt, retry_backoff))
                    continue
                detail = f"HTTP {exc.code}"
                if body_preview:
                    detail = f"{detail}: {body_preview}"
                raise LLMClientError(f"LLM request failed: {detail}") from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(retry_backoff * (2**attempt))
                    continue
                raise LLMClientError(f"LLM request failed: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise LLMClientError(f"LLM response was not valid JSON: {exc}") from exc
        raise LLMClientError(f"LLM request failed after retries: {last_error}")

    def _retry_delay(self, exc: urllib.error.HTTPError, attempt: int, retry_backoff: float) -> float:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return retry_backoff * (2**attempt)

    def _api_key(self) -> str | None:
        env_name = str(self.config.get("api_key_env") or "").strip()
        if env_name:
            return os.environ.get(env_name)
        raw = str(self.config.get("api_key") or "").strip()
        if raw.startswith("${") and raw.endswith("}"):
            return os.environ.get(raw[2:-1])
        return raw or None

    def _models(self) -> list[str]:
        primary = str(self.config.get("model") or "").strip()
        out = [primary] if primary else []
        fallback = self.config.get("fallback_models")
        if isinstance(fallback, str):
            candidates = [item.strip() for item in fallback.split(",") if item.strip().lower() not in {"none", "null", "false"}]
        elif isinstance(fallback, list):
            candidates = [str(item).strip() for item in fallback]
        else:
            candidates = []
        for model in candidates:
            if model and model not in out:
                out.append(model)
        return out

    @staticmethod
    def _should_fallback(exc: Exception) -> bool:
        text = str(exc).lower()
        retryable = ("http 402", "http 403", "http 408", "http 409", "http 429", "http 500", "http 502", "http 503", "http 504")
        quota_terms = ("quota", "rate limit", "rate_limit", "insufficient", "overloaded", "temporarily unavailable")
        return any(term in text for term in retryable) or any(term in text for term in quota_terms)


def parse_json_facts(raw: str) -> list[dict[str, Any]]:
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMClientError(f"LLM extraction response was not valid JSON: {exc}") from exc
    if isinstance(data, dict) and isinstance(data.get("facts"), list):
        data = data["facts"]
    if not isinstance(data, list):
        raise LLMClientError("LLM extraction JSON must be a list or an object with a facts list")
    return [item for item in data if isinstance(item, dict)]
