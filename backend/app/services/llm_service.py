
import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434",
).rstrip("/")

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))
# 0.2 was so deterministic that repeated tickets produced near-identical
# boilerplate phrasing. 0.3 keeps JSON output stable but adds specificity.
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))

# Explicit context window. Ollama's default (2048/4096 depending on version)
# silently truncates or context-shifts the ~6-7K-character analysis prompts,
# which degrades output quality and can stall generation. 4096 comfortably
# fits the merged prompt; raise it if you extend the prompts.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

# How long Ollama keeps the model in memory between calls. Reloading the
# model after an idle period costs 10-40 seconds per request, so the default
# was raised from 10m to 30m.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip() or "30m"

# In-process cache for identical LLM prompts. Repeated or retried tickets
# return instantly instead of paying the full generation cost again.
# Set LLM_RESPONSE_CACHE_TTL=0 to disable caching completely.
LLM_RESPONSE_CACHE_TTL = int(os.getenv("LLM_RESPONSE_CACHE_TTL", "3600"))
LLM_RESPONSE_CACHE_MAX = 256

_cache_lock = threading.Lock()
_response_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()


def _cache_key(payload: dict) -> str:
    canonical = json.dumps(
        {
            "model": payload.get("model"),
            "messages": payload.get("messages"),
            "format": payload.get("format"),
            "options": payload.get("options"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> str | None:
    if LLM_RESPONSE_CACHE_TTL <= 0:
        return None
    now = time.monotonic()
    with _cache_lock:
        entry = _response_cache.get(key)
        if entry is None:
            return None
        stored_at, answer = entry
        if now - stored_at > LLM_RESPONSE_CACHE_TTL:
            _response_cache.pop(key, None)
            return None
        # Move to the end so the OrderedDict behaves as an LRU.
        _response_cache.move_to_end(key)
        return answer


def _cache_put(key: str, answer: str) -> None:
    if LLM_RESPONSE_CACHE_TTL <= 0:
        return
    with _cache_lock:
        _response_cache[key] = (time.monotonic(), answer)
        _response_cache.move_to_end(key)
        while len(_response_cache) > LLM_RESPONSE_CACHE_MAX:
            _response_cache.popitem(last=False)


def _post_chat(payload: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as http_response:
        return json.loads(http_response.read().decode("utf-8"))


def generate_response(
    prompt: str,
    response_format=None,
    num_predict: int = 512,
) -> str:
    """Generate a response using the configured local Ollama model."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("The LLM prompt cannot be empty.")

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are BugPilot, an ERP incident analysis assistant. "
                    "Use supplied ticket details, historical tickets, and "
                    "financial documents as evidence. Do not invent records "
                    "or policies. Clearly explain uncertainty."
                ),
            },
            {
                "role": "user",
                "content": prompt.strip(),
            },
        ],
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "num_predict": max(64, min(int(num_predict), 1800)),
            "temperature": OLLAMA_TEMPERATURE,
            "num_ctx": OLLAMA_NUM_CTX,
        },
    }

    if response_format == "json":
        payload["format"] = "json"

    cache_key = _cache_key(payload)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(
            "Ollama request served from cache: model=%s, prompt_chars=%d",
            OLLAMA_MODEL,
            len(prompt),
        )
        return cached

    started = time.monotonic()

    logger.info(
        "Ollama request started: model=%s, prompt_chars=%d, "
        "format=%s, num_predict=%d, num_ctx=%d",
        OLLAMA_MODEL,
        len(prompt),
        response_format or "text",
        payload["options"]["num_predict"],
        OLLAMA_NUM_CTX,
    )

    try:
        result = _post_chat(payload, OLLAMA_TIMEOUT)

        answer = (
            result.get("message", {})
            .get("content", "")
            .strip()
        )

        if not answer:
            raise RuntimeError("Ollama returned an empty response.")

        logger.info(
            "Ollama request completed in %.2f seconds",
            time.monotonic() - started,
        )

        _cache_put(cache_key, answer)

        return answer

    except urllib.error.HTTPError as exc:
        details = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        logger.error(
            "Ollama HTTP error %s: %s",
            exc.code,
            details[:1000],
        )

        raise RuntimeError(
            f"Ollama returned HTTP {exc.code}: {details[:500]}"
        ) from exc

    except (TimeoutError, urllib.error.URLError) as exc:
        logger.exception("Ollama request timed out or failed")

        raise RuntimeError(
            f"Ollama request failed or timed out: {exc}"
        ) from exc

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.exception("Invalid Ollama response")

        raise RuntimeError(
            "Ollama returned an invalid response."
        ) from exc


def warmup_model() -> dict:
    """
    Load the configured model into Ollama's memory before the first user
    request. A cold model load otherwise adds 10-40 seconds to the first
    analysis after startup or an idle period.

    Never raises: warmup failures are logged and returned as status.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"num_predict": 1, "num_ctx": OLLAMA_NUM_CTX},
    }

    started = time.monotonic()

    try:
        _post_chat(payload, min(OLLAMA_TIMEOUT, 120))
        elapsed = time.monotonic() - started
        logger.info("Ollama model warmup completed in %.2f seconds", elapsed)
        return {"status": "ok", "elapsed_seconds": round(elapsed, 2)}
    except Exception as exc:
        logger.warning("Ollama model warmup failed: %s", exc)
        return {"status": "failed", "error": str(exc)[:300]}
