"""The SQL writer: the only part of the engine that talks to an AI model.

    writer = GeminiWriter()
    writer.write(prompt, n=8) -> list of 8 reply texts

Everything else in the engine works with any object that has a
``write(prompt, n)`` method (the SQLWriter protocol). That is what lets Gemini
be swapped for base Qwen or trained Qwen without touching the rest of the
engine. Qwen is reached through OpenAICompatWriter (vLLM or Ollama).

The writer only writes. It never decides whether an answer is right; the
verifier and trust.py do that, whichever model wrote the SQL.

Caching: pass ``cache_dir`` and every reply is saved to disk, keyed by model,
temperature, prompt and attempt number. Running the same evaluation twice
then costs nothing and is not slowed by API rate limits. The product leaves
the cache off, so users always get fresh attempts.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol

from verdict.config import REPO_ROOT

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

#: Seconds to wait before each retry when the API says "too many requests"
#: (free-tier limits are per minute) or "busy". Then the call counts as failed.
RETRY_WAITS_S = (5, 20, 40)

#: Above 0 so the 8 attempts can differ. If every attempt were identical,
#: agreement would always be 8/8 and would say nothing about trust.
DEFAULT_TEMPERATURE = 0.8


class LLMError(RuntimeError):
    """Every attempt failed, e.g. a missing API key or no network."""


class SQLWriter(Protocol):
    def write(self, prompt: str, n: int) -> list[str]:
        """Return ``n`` independent replies to ``prompt``. A failed reply is ""."""
        ...


class GeminiWriter:
    """Writes SQL with Google's Gemini API.

    The key and model come from the environment (GEMINI_API_KEY,
    GEMINI_MODEL), read from the repo's .env file if not already set.
    """

    def __init__(
        self,
        model: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        cache_dir: str | Path | None = None,
        max_parallel: int = 8,
    ):
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set. Add it to the .env file.")

        from google import genai  # imported here so tests never need the SDK

        self._client = genai.Client(api_key=api_key)
        self.model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        self.temperature = temperature
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_parallel = max_parallel

    # -- cache -------------------------------------------------------------

    def _cache_file(self, prompt: str, i: int) -> Path | None:
        if self.cache_dir is None:
            return None
        key = f"{self.model}|{self.temperature}|{i}|{prompt}"
        return self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"

    # -- one call ----------------------------------------------------------

    def _one(self, prompt: str, i: int) -> tuple[str, str | None]:
        """Return (reply, error). Never raises."""
        cache = self._cache_file(prompt, i)
        if cache is not None and cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))["reply"], None

        from google.genai import types

        for wait in (*RETRY_WAITS_S, None):
            try:
                resp = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=self.temperature),
                )
                reply = resp.text or ""
                break
            except Exception as e:  # network, quota, safety block
                err = f"{type(e).__name__}: {e}"
                # Only "too many requests" and "server busy" are worth waiting for.
                if wait is None or not any(code in err for code in ("429", "503")):
                    return "", err
                time.sleep(wait)

        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"model": self.model, "reply": reply}), encoding="utf-8")
        return reply, None

    def write(self, prompt: str, n: int) -> list[str]:
        # The n calls are independent, so they run at the same time.
        with ThreadPoolExecutor(max_workers=min(n, self.max_parallel)) as pool:
            results = list(pool.map(lambda i: self._one(prompt, i), range(n)))

        errors = [err for _, err in results if err]
        # A failed call counts against agreement. If most calls failed, the
        # trust level would describe the API outage, not the answer, so stop.
        if len(errors) > n // 2:
            raise LLMError(f"{len(errors)} of {n} Gemini calls failed; first error: {errors[0][:300]}")
        return [reply for reply, _ in results]


class OpenAICompatWriter:
    """Writes SQL with any server that speaks the OpenAI chat API.

    One class covers both places Qwen runs:

        vLLM on the college GPU   OpenAICompatWriter("http://gpu-pc:8000/v1", "verdict-qwen")
        Ollama on the laptop      OpenAICompatWriter("http://localhost:11434/v1", "verdict-qwen")

    The n attempts are n separate requests sent at the same time. vLLM batches
    them on the GPU. Ollama ignores the API's ``n`` option, so one request per
    attempt is the only way that works on both.

    Uses only the standard library, so the laptop needs no extra package to
    talk to Ollama.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = 512,
        timeout_s: float = 120.0,
        max_parallel: int = 8,
        system_prompt: str | None = None,
        api_key: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.max_parallel = max_parallel
        self.system_prompt = system_prompt
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _one(self, prompt: str) -> tuple[str, str | None]:
        """Return (reply, error). Never raises."""
        import urllib.error
        import urllib.request

        messages = [{"role": "user", "content": prompt}]
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or "", None
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            return "", f"HTTP {e.code}: {detail}"
        except Exception as e:  # connection refused, timeout, bad JSON
            return "", f"{type(e).__name__}: {e}"

    def write(self, prompt: str, n: int) -> list[str]:
        with ThreadPoolExecutor(max_workers=max(1, min(n, self.max_parallel))) as pool:
            results = list(pool.map(lambda _: self._one(prompt), range(n)))

        errors = [err for _, err in results if err]
        # Same rule as GeminiWriter: if most calls failed, the problem is the
        # server, not the question, so say so instead of returning a verdict.
        if len(errors) > n // 2:
            raise LLMError(
                f"{len(errors)} of {n} calls to {self.base_url} failed; first error: {errors[0][:300]}"
            )
        return [reply for reply, _ in results]

    def reachable(self, timeout_s: float = 2.0) -> bool:
        """True if the server answers GET /models. Used by /api/health."""
        import urllib.request

        req = urllib.request.Request(f"{self.base_url}/models", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False


class FixedWriter:
    """Returns pre-written replies. Used by tests and offline demos.

    With fewer replies than ``n`` it cycles through them.
    """

    def __init__(self, replies: list[str]):
        if not replies:
            raise ValueError("FixedWriter needs at least one reply")
        self.replies = list(replies)
        self.prompts: list[str] = []

    def write(self, prompt: str, n: int) -> list[str]:
        self.prompts.append(prompt)
        return [self.replies[i % len(self.replies)] for i in range(n)]
