from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.math_utils import normalize


TOKEN_RE = re.compile(r"[A-Za-z0-9_#./:+-]+")


class EmbeddingRuntimeError(RuntimeError):
    pass


class DiskEmbeddingCache:
    def __init__(self, path: str | os.PathLike[str], namespace: str):
        self.path = Path(path)
        self.namespace = str(namespace)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_cache (
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                hits INTEGER DEFAULT 0,
                PRIMARY KEY(namespace, key)
            )
            """
        )
        self._conn.commit()

    def get(self, key: str) -> list[float] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT vector FROM embedding_cache WHERE namespace = ? AND key = ?",
                (self.namespace, key),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                """
                UPDATE embedding_cache
                SET last_used_at = ?, hits = COALESCE(hits, 0) + 1
                WHERE namespace = ? AND key = ?
                """,
                (utc_timestamp(), self.namespace, key),
            )
            self._conn.commit()
        return [float(x) for x in json.loads(row[0])]

    def set(self, key: str, vector: list[float]) -> None:
        now = utc_timestamp()
        payload = json.dumps([float(x) for x in vector], separators=(",", ":"))
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO embedding_cache(namespace, key, dim, vector, created_at, last_used_at, hits)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(namespace, key) DO UPDATE SET
                    dim = excluded.dim,
                    vector = excluded.vector,
                    last_used_at = excluded.last_used_at
                """,
                (self.namespace, key, len(vector), payload, now, now),
            )
            self._conn.commit()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS entries, COALESCE(SUM(hits), 0) AS hits
                FROM embedding_cache
                WHERE namespace = ?
                """,
                (self.namespace,),
            ).fetchone()
        return {
            "path": str(self.path),
            "namespace": self.namespace,
            "entries": int(row[0] or 0),
            "hits": int(row[1] or 0),
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def embedding_cache_key(*parts: Any) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=32).hexdigest()


class HashEmbeddingEncoder:
    """Deterministic bag-of-token encoder for local smoke tests.

    It is not a semantic model, but it is stable, dependency-free, and good
    enough to validate storage, scoring, and control flow.
    """

    def __init__(self, dim: int = 128):
        self.dim = int(dim)

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = TOKEN_RE.findall(str(text).lower())
        if not tokens:
            return vec
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if (digest[4] % 2 == 0) else -1.0
            weight = 1.0 + (len(token) % 7) / 10.0
            vec[bucket] += sign * weight
        return normalize(vec)

    @property
    def embedding_dim(self) -> int:
        return self.dim

    def descriptor(self) -> dict[str, Any]:
        return {
            "backend": "hash",
            "model_name": f"hash-bow-{self.dim}",
            "embedding_dim": self.dim,
            "model_path": None,
        }


class LlamaCppEmbeddingEncoder:
    """Local GGUF embedding encoder using llama-cpp-python."""

    def __init__(
        self,
        model_path: str,
        model_name: str | None = None,
        n_ctx: int = 2048,
        n_threads: int | None = None,
        normalize_embeddings: bool = True,
        max_text_chars: int = 1000,
        cache_path: str | None = None,
    ):
        self.model_path = str(model_path)
        self.model_name = str(model_name or Path(model_path).name)
        self.n_ctx = max(256, int(n_ctx))
        self.n_threads = int(n_threads) if n_threads is not None else None
        self.normalize_embeddings = bool(normalize_embeddings)
        self.max_text_chars = max(32, int(max_text_chars))
        self._model = None
        self._lock = threading.Lock()
        self._cache: dict[str, list[float]] = {}
        self._disk_cache = self._build_disk_cache(cache_path)
        self._embedding_dim: int | None = None

    def embed(self, text: str) -> list[float]:
        safe_text = str(text or "")[: self.max_text_chars]
        key = self._cache_key(safe_text)
        if key in self._cache:
            return self._cache[key]
        if self._disk_cache is not None:
            cached = self._disk_cache.get(key)
            if cached is not None:
                self._cache[key] = cached
                self._embedding_dim = len(cached)
                return cached
        self._load()
        result = self._embed_with_model([safe_text])[0]
        self._cache[key] = result
        if self._disk_cache is not None:
            self._disk_cache.set(key, result)
        self._embedding_dim = len(result)
        return result

    @property
    def embedding_dim(self) -> int:
        if self._embedding_dim is None:
            self._embedding_dim = len(self.embed("embedding-dim-probe"))
        return self._embedding_dim

    def descriptor(self) -> dict[str, Any]:
        return {
            "backend": "llama_cpp",
            "model_name": Path(self.model_path).name,
            "embedding_dim": self.embedding_dim,
            "model_path": os.path.abspath(os.path.expanduser(self.model_path)),
        }

    def close(self) -> None:
        if self._disk_cache is not None:
            self._disk_cache.close()

    def cache_stats(self) -> dict[str, Any] | None:
        if self._disk_cache is None:
            return None
        return self._disk_cache.stats()

    def _cache_namespace(self) -> str:
        return embedding_cache_key(
            "llama_cpp",
            os.path.abspath(os.path.expanduser(self.model_path)),
            self.model_name,
            self.normalize_embeddings,
            self.max_text_chars,
        )

    def _cache_key(self, safe_text: str) -> str:
        return embedding_cache_key(self._cache_namespace(), safe_text)

    def _build_disk_cache(self, cache_path: str | None) -> DiskEmbeddingCache | None:
        if not cache_path:
            return None
        return DiskEmbeddingCache(cache_path, self._cache_namespace())

    def _load(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                from llama_cpp import Llama
            except Exception as exc:
                raise EmbeddingRuntimeError(
                    "llama-cpp-python is not installed in this Python runtime"
                ) from exc
            kwargs: dict[str, Any] = {
                "model_path": os.path.abspath(os.path.expanduser(self.model_path)),
                "embedding": True,
                "n_ctx": self.n_ctx,
            }
            if self.n_threads is not None and self.n_threads > 0:
                kwargs["n_threads"] = self.n_threads
            self._model = Llama(**kwargs)

    def _embed_with_model(self, texts: list[str]) -> list[list[float]]:
        rows: list[list[float]] = []
        if hasattr(self._model, "embed"):
            try:
                raw = self._model.embed(texts)
                if isinstance(raw, list) and len(raw) == len(texts):
                    return [self._normalize_vector(v) for v in raw]
            except Exception:
                pass
        if hasattr(self._model, "create_embedding"):
            try:
                resp = self._model.create_embedding(texts if len(texts) > 1 else texts[0])
                data = resp.get("data") if isinstance(resp, dict) else None
                if isinstance(data, list):
                    for row in data:
                        emb = row.get("embedding") if isinstance(row, dict) else None
                        if emb is None:
                            raise EmbeddingRuntimeError("llama_cpp returned an embedding row without embedding")
                        rows.append(self._normalize_vector(emb))
                    if len(rows) == len(texts):
                        return rows
            except Exception:
                rows = []
                for text in texts:
                    resp = self._model.create_embedding(text)
                    data = resp.get("data") if isinstance(resp, dict) else None
                    if not isinstance(data, list) or not data:
                        raise EmbeddingRuntimeError("llama_cpp returned an invalid embedding response")
                    emb = data[0].get("embedding") if isinstance(data[0], dict) else None
                    if emb is None:
                        raise EmbeddingRuntimeError("llama_cpp returned an embedding row without embedding")
                    rows.append(self._normalize_vector(emb))
                if len(rows) == len(texts):
                    return rows
        raise EmbeddingRuntimeError("Unable to obtain embeddings from llama_cpp backend")

    def _normalize_vector(self, row: Any) -> list[float]:
        values = [float(x) for x in row]
        if self.normalize_embeddings:
            return normalize(values)
        return values


class WslLlamaCppEmbeddingEncoder:
    """Bridge to llama-cpp-python inside WSL for GGUF files stored there.

    The default path keeps one WSL Python sidecar alive so the GGUF model is
    loaded once per client process rather than once per embedding call.
    """

    def __init__(
        self,
        model_path: str,
        model_name: str | None = None,
        n_ctx: int = 2048,
        n_threads: int | None = None,
        normalize_embeddings: bool = True,
        max_text_chars: int = 1000,
        python_executable: str = "python3",
        timeout_sec: float = 120.0,
        expected_dim: int | None = 768,
        use_sidecar: bool = True,
        cache_path: str | None = None,
    ):
        self.model_path = str(model_path)
        self.model_name = str(model_name or Path(model_path).name)
        self.n_ctx = max(256, int(n_ctx))
        self.n_threads = int(n_threads) if n_threads is not None else None
        self.normalize_embeddings = bool(normalize_embeddings)
        self.max_text_chars = max(32, int(max_text_chars))
        self.python_executable = str(python_executable or "python3")
        self.timeout_sec = max(5.0, float(timeout_sec))
        self.expected_dim = int(expected_dim) if expected_dim else None
        self.use_sidecar = bool(use_sidecar)
        self._cache: dict[str, list[float]] = {}
        self._disk_cache = self._build_disk_cache(cache_path)
        self._embedding_dim: int | None = self.expected_dim
        self._sidecar_lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[str] | None = None
        self._stderr_tail: list[str] = []

    def embed(self, text: str) -> list[float]:
        safe_text = str(text or "")[: self.max_text_chars]
        key = self._cache_key(safe_text)
        if key in self._cache:
            return self._cache[key]
        if self._disk_cache is not None:
            cached = self._disk_cache.get(key)
            if cached is not None:
                self._cache[key] = cached
                self._embedding_dim = len(cached)
                return cached
        payload = {
            "texts": [safe_text],
        }
        if self.use_sidecar:
            result = self._run_sidecar_embedding(payload)[0]
        else:
            one_shot = {
                "model_path": self.model_path,
                "texts": [safe_text],
                "n_ctx": self.n_ctx,
                "n_threads": self.n_threads,
                "normalize": self.normalize_embeddings,
            }
            result = self._run_wsl_embedding(one_shot)[0]
        self._cache[key] = result
        if self._disk_cache is not None:
            self._disk_cache.set(key, result)
        self._embedding_dim = len(result)
        return result

    @property
    def embedding_dim(self) -> int:
        if self._embedding_dim is None:
            self._embedding_dim = len(self.embed("embedding-dim-probe"))
        return self._embedding_dim

    def descriptor(self) -> dict[str, Any]:
        return {
            "backend": "wsl_llama_cpp",
            "model_name": Path(self.model_path).name,
            "embedding_dim": self.embedding_dim,
            "model_path": self.model_path,
        }

    def close(self) -> None:
        with self._sidecar_lock:
            self._stop_sidecar_locked()
        if self._disk_cache is not None:
            self._disk_cache.close()

    def cache_stats(self) -> dict[str, Any] | None:
        if self._disk_cache is None:
            return None
        return self._disk_cache.stats()

    def _cache_namespace(self) -> str:
        return embedding_cache_key(
            "wsl_llama_cpp",
            self.model_path,
            self.model_name,
            self.normalize_embeddings,
            self.max_text_chars,
        )

    def _cache_key(self, safe_text: str) -> str:
        return embedding_cache_key(self._cache_namespace(), safe_text)

    def _build_disk_cache(self, cache_path: str | None) -> DiskEmbeddingCache | None:
        if not cache_path:
            return None
        return DiskEmbeddingCache(cache_path, self._cache_namespace())

    def _run_sidecar_embedding(self, payload: dict[str, Any]) -> list[list[float]]:
        with self._sidecar_lock:
            self._start_sidecar_locked()
            assert self._proc is not None
            proc = self._proc
            if proc.stdin is None:
                raise EmbeddingRuntimeError("WSL embedding sidecar stdin is unavailable")
            try:
                proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                self._stop_sidecar_locked()
                raise EmbeddingRuntimeError(f"Failed to write to WSL embedding sidecar: {exc}") from exc
            obj = self._read_sidecar_json_locked()
        if isinstance(obj, dict) and obj.get("error"):
            raise EmbeddingRuntimeError(str(obj.get("error")))
        rows = obj.get("embeddings") if isinstance(obj, dict) else None
        if not isinstance(rows, list) or not rows:
            raise EmbeddingRuntimeError("WSL sidecar response missing embeddings")
        return [[float(x) for x in row] for row in rows]

    def _start_sidecar_locked(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        self._stderr_tail = []
        self._stdout_queue = queue.Queue()
        cmd = ["wsl", "-e", self.python_executable, "-u", "-c", _WSL_EMBED_SIDECAR_SCRIPT]
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert self._proc.stdout is not None
        assert self._proc.stderr is not None
        threading.Thread(target=self._drain_stdout, args=(self._proc.stdout, self._stdout_queue), daemon=True).start()
        threading.Thread(target=self._drain_stderr, args=(self._proc.stderr,), daemon=True).start()
        init = {
            "model_path": self.model_path,
            "n_ctx": self.n_ctx,
            "n_threads": self.n_threads,
            "normalize": self.normalize_embeddings,
        }
        try:
            assert self._proc.stdin is not None
            self._proc.stdin.write(json.dumps(init, separators=(",", ":")) + "\n")
            self._proc.stdin.flush()
            ready = self._read_sidecar_json_locked()
        except Exception:
            self._stop_sidecar_locked()
            raise
        if not isinstance(ready, dict) or not ready.get("ready"):
            self._stop_sidecar_locked()
            raise EmbeddingRuntimeError(f"WSL embedding sidecar did not become ready: {ready}")

    def _stop_sidecar_locked(self) -> None:
        proc = self._proc
        self._proc = None
        self._stdout_queue = None
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin:
                proc.stdin.write(json.dumps({"close": True}) + "\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _read_sidecar_json_locked(self) -> dict[str, Any]:
        if self._stdout_queue is None:
            raise EmbeddingRuntimeError("WSL embedding sidecar output queue is unavailable")
        deadline = time.monotonic() + self.timeout_sec
        while True:
            if self._proc is not None and self._proc.poll() is not None:
                tail = "\n".join(self._stderr_tail[-12:])
                raise EmbeddingRuntimeError(f"WSL embedding sidecar exited early with code {self._proc.returncode}: {tail}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                tail = "\n".join(self._stderr_tail[-12:])
                raise EmbeddingRuntimeError(f"Timed out waiting for WSL embedding sidecar: {tail}")
            try:
                line = self._stdout_queue.get(timeout=min(0.5, remaining)).strip()
            except queue.Empty:
                continue
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                self._stderr_tail.append(f"stdout: {line[:300]}")
                continue
            if isinstance(obj, dict):
                return obj
            self._stderr_tail.append(f"stdout-json: {line[:300]}")

    def _drain_stdout(self, pipe, out_queue: queue.Queue[str]) -> None:
        try:
            for line in pipe:
                out_queue.put(line)
        except Exception:
            return

    def _drain_stderr(self, pipe) -> None:
        try:
            for line in pipe:
                text = line.rstrip()
                if text:
                    self._stderr_tail.append(text)
                    if len(self._stderr_tail) > 50:
                        del self._stderr_tail[: len(self._stderr_tail) - 50]
        except Exception:
            return

    def _run_wsl_embedding(self, payload: dict[str, Any]) -> list[list[float]]:
        code = _WSL_EMBED_SCRIPT
        cmd = ["wsl", "-e", self.python_executable, "-c", code]
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=self.timeout_sec,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise EmbeddingRuntimeError(f"WSL llama_cpp embedding failed: {detail}")
        try:
            obj = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise EmbeddingRuntimeError(f"WSL embedding response was not JSON: {proc.stdout[:500]}") from exc
        rows = obj.get("embeddings") if isinstance(obj, dict) else None
        if not isinstance(rows, list) or not rows:
            raise EmbeddingRuntimeError("WSL embedding response missing embeddings")
        return [[float(x) for x in row] for row in rows]


def build_encoder(config: dict[str, Any] | None = None, default_dim: int = 128):
    cfg = dict(config or {})
    backend = str(cfg.get("backend") or "hash").strip().lower().replace("-", "_")
    if backend in ("hash", "test"):
        return HashEmbeddingEncoder(int(cfg.get("dim") or default_dim))

    model_name = str(cfg.get("model_name") or cfg.get("model") or "")
    n_ctx = int(cfg.get("gguf_n_ctx") or cfg.get("n_ctx") or 2048)
    n_threads = cfg.get("gguf_n_threads", cfg.get("n_threads"))
    n_threads = int(n_threads) if n_threads is not None else None
    normalize_embeddings = bool(cfg.get("normalize", True))
    max_text_chars = int(cfg.get("max_text_chars") or 1000)
    cache_path = str(cfg.get("cache_path") or "") or None

    if backend in ("llama_cpp", "gguf", "llama"):
        return LlamaCppEmbeddingEncoder(
            model_path=str(cfg.get("gguf_path") or cfg.get("model_path") or model_name),
            model_name=model_name,
            n_ctx=n_ctx,
            n_threads=n_threads,
            normalize_embeddings=normalize_embeddings,
            max_text_chars=max_text_chars,
            cache_path=cache_path,
        )
    if backend in ("wsl_llama_cpp", "wsl_gguf"):
        return WslLlamaCppEmbeddingEncoder(
            model_path=str(cfg.get("wsl_model_path") or cfg.get("gguf_path") or cfg.get("model_path") or model_name),
            model_name=model_name,
            n_ctx=n_ctx,
            n_threads=n_threads,
            normalize_embeddings=normalize_embeddings,
            max_text_chars=max_text_chars,
            python_executable=str(cfg.get("wsl_python") or "python3"),
            expected_dim=int(cfg.get("dim") or 768),
            use_sidecar=bool(cfg.get("sidecar", True)),
            cache_path=cache_path,
        )
    raise ValueError(f"Unsupported embedding backend: {backend}")


_WSL_EMBED_SCRIPT = r"""
import json
import math
import sys

try:
    from llama_cpp import Llama
except Exception as exc:
    print(json.dumps({"error": f"llama-cpp-python is not installed in WSL Python: {exc}"}), file=sys.stderr)
    raise SystemExit(2)

payload = json.loads(sys.stdin.read())
texts = [str(t or "") for t in payload.get("texts") or []]
kwargs = {
    "model_path": str(payload["model_path"]),
    "embedding": True,
    "n_ctx": int(payload.get("n_ctx") or 2048),
}
n_threads = payload.get("n_threads")
if n_threads:
    kwargs["n_threads"] = int(n_threads)
model = Llama(**kwargs)

def normalize(row):
    values = [float(x) for x in row]
    if payload.get("normalize", True):
        n = math.sqrt(sum(x * x for x in values))
        if n > 1e-12:
            values = [x / n for x in values]
    return values

def embed_rows(batch):
    if hasattr(model, "embed"):
        try:
            raw = model.embed(batch)
            if isinstance(raw, list) and len(raw) == len(batch):
                return [normalize(v) for v in raw]
        except Exception:
            pass
    resp = model.create_embedding(batch if len(batch) > 1 else batch[0])
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("create_embedding returned invalid response")
    rows = []
    for item in data:
        emb = item.get("embedding") if isinstance(item, dict) else None
        if emb is None:
            raise RuntimeError("create_embedding returned row without embedding")
        rows.append(normalize(emb))
    return rows

print(json.dumps({"embeddings": embed_rows(texts)}, separators=(",", ":")))
"""


_WSL_EMBED_SIDECAR_SCRIPT = r"""
import json
import math
import sys
import traceback

try:
    from llama_cpp import Llama
except Exception as exc:
    print(json.dumps({"error": f"llama-cpp-python is not installed in WSL Python: {exc}"}), flush=True)
    raise SystemExit(2)


def write(obj):
    print(json.dumps(obj, separators=(",", ":")), flush=True)


def normalize(row, enabled=True):
    values = [float(x) for x in row]
    if enabled:
        n = math.sqrt(sum(x * x for x in values))
        if n > 1e-12:
            values = [x / n for x in values]
    return values


def embed_rows(model, batch, normalize_enabled=True):
    if hasattr(model, "embed"):
        try:
            raw = model.embed(batch)
            if isinstance(raw, list) and len(raw) == len(batch):
                return [normalize(v, normalize_enabled) for v in raw]
        except Exception:
            pass
    resp = model.create_embedding(batch if len(batch) > 1 else batch[0])
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("create_embedding returned invalid response")
    rows = []
    for item in data:
        emb = item.get("embedding") if isinstance(item, dict) else None
        if emb is None:
            raise RuntimeError("create_embedding returned row without embedding")
        rows.append(normalize(emb, normalize_enabled))
    return rows


try:
    init_line = sys.stdin.readline()
    if not init_line:
        raise RuntimeError("missing sidecar init payload")
    init = json.loads(init_line)
    kwargs = {
        "model_path": str(init["model_path"]),
        "embedding": True,
        "n_ctx": int(init.get("n_ctx") or 2048),
    }
    n_threads = init.get("n_threads")
    if n_threads:
        kwargs["n_threads"] = int(n_threads)
    normalize_enabled = bool(init.get("normalize", True))
    model = Llama(**kwargs)
    write({"ready": True})
except Exception as exc:
    write({"error": f"failed to initialize WSL embedding sidecar: {exc}"})
    traceback.print_exc(file=sys.stderr)
    raise SystemExit(3)

for line in sys.stdin:
    try:
        payload = json.loads(line)
        if payload.get("close"):
            write({"closed": True})
            break
        texts = [str(t or "") for t in payload.get("texts") or []]
        if not texts:
            write({"error": "embedding request missing texts"})
            continue
        write({"embeddings": embed_rows(model, texts, normalize_enabled)})
    except Exception as exc:
        write({"error": str(exc)})
        traceback.print_exc(file=sys.stderr)
"""
