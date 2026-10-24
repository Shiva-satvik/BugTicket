"""Multi-provider LLM service for BugPilot.

Fixes the "AI analysis always returns a standard/template response" bug.

Root causes fixed here:
  1. The old service only talked to Ollama and never read LLM_PROVIDER or
     the HF_* variables from .env. If Ollama was not running, or the model
     was not pulled, every analysis failed and the pipeline silently
     returned the retrieval-grounded template fallback.
  2. Failures were not actionable: a dead Ollama server made each request
     hang for up to OLLAMA_TIMEOUT seconds before failing.

Providers (selected with LLM_PROVIDER in .env):
  - "ollama"      : local Ollama server only.
  - "huggingface" : Hugging Face Inference router only (requires HF_TOKEN).
  - "auto"        : Ollama first; if unreachable/failed, fall back to
                    Hugging Face when HF_TOKEN is configured (default).

The public API is unchanged, so every agent keeps working:
  generate_response(prompt, response_format=None, num_predict=512) -> str
  warmup_model() -> dict
  get_llm_status() -> dict   (new: used by /api/ai/status diagnostics)
  OLLAMA_MODEL               (module-level constant, still exported)
"""

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

# ============================================================
# PROVIDER SELECTION
# ============================================================

# "auto" (default) | "ollama" | "huggingface"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()
if LLM_PROVIDER in {"hf", "hugging-face", "hub"}:
    LLM_PROVIDER = "huggingface"
if LLM_PROVIDER not in {"auto", "ollama", "huggingface"}:
    logger.warning(
        "Unknown LLM_PROVIDER %r; falling back to 'auto'.", LLM_PROVIDER
    )
    LLM_PROVIDER = "auto"

# ============================================================
# OLLAMA SETTINGS (unchanged behaviour)
# ============================================================

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
# which degrades output quality and can stall generation.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

# How long Ollama keeps the model in memory between calls. Reloading the
# model after an idle period costs 10-40 seconds per request, so the default
# was raised from 10m to 30m.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip() or "30m"

# Seconds for the cheap "is Ollama alive" probe. This must stay small so a
# dead Ollama fails fast and auto mode can switch to Hugging Face instead
# of hanging for OLLAMA_TIMEOUT seconds.
OLLAMA_PROBE_TIMEOUT = float(os.getenv("OLLAMA_PROBE_TIMEOUT", "3"))

# ============================================================
# HUGGING FACE SETTINGS (were completely ignored before this fix)
# ============================================================

HF_API_TOKEN = os.getenv("HF_TOKEN", "").strip()
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct").strip()
HF_API_URL = os.getenv(
    "HF_API_URL",
    "https://router.huggingface.co/v1/chat/completions",
).strip()
HF_TIMEOUT = int(os.getenv("HF_TIMEOUT", "120"))
HF_TEMPERATURE = float(os.getenv("HF_TEMPERATURE", str(OLLAMA_TEMPERATURE)))

# ============================================================
# RESPONSE CACHE (successful generations only)
# ============================================================

# In-process cache for identical LLM prompts. Repeated or retried tickets
# return instantly instead of paying the full generation cost again.
# Set LLM_RESPONSE_CACHE_TTL=0 to disable caching completely.
LLM_RESPONSE_CACHE_TTL = int(os.getenv("LLM_RESPONSE_CACHE_TTL", "3600"))
LLM_RESPONSE_CACHE_MAX = 256

_cache_lock = threading.Lock()
_response_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()

SYSTEM_PROMPT = (
    "You are BugPilot, an ERP incident analysis assistant. "
    "Use supplied ticket details, historical tickets, and "
    "financial documents as evidence. Do not invent records "
    "or policies. Clearly explain uncertainty."
)


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


# ============================================================
# OLLAMA TRANSPORT
# ============================================================


def _post_chat(payload: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as http_response:
        return json.loads(http_response.read().decode("utf-8"))


def probe_ollama() -> dict:
    """
    Cheap reachability + model check against the local Ollama server.

    Returns {"reachable": bool, "model_installed": bool,
             "installed_models": list[str], "error": str | None}.
    Never raises.
    """
    info = {
        "reachable": False,
        "model_installed": False,
        "installed_models": [],
        "error": None,
    }

    try:
        request = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/tags",
            headers={"Content-Type": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(
            request, timeout=OLLAMA_PROBE_TIMEOUT
        ) as http_response:
            data = json.loads(http_response.read().decode("utf-8"))

    except urllib.error.HTTPError as exc:
        info["error"] = f"Ollama HTTP {exc.code} on /api/tags"
        return info
    except Exception as exc:  # connection refused, timeout, DNS, ...
        info["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return info

    info["reachable"] = True
    models = [
        str(item.get("name", "")).strip()
        for item in (data.get("models") or [])
        if str(item.get("name", "")).strip()
    ]
    info["installed_models"] = models[:25]

    wanted = OLLAMA_MODEL.strip()
    wanted_base = wanted.split(":")[0].strip().lower()
    for name in models:
        name_base = name.split(":")[0].strip().lower()
        if name == wanted or (wanted_base and name_base == wanted_base):
            info["model_installed"] = True
            break

    return info


def _ollama_generate(
    prompt: str,
    response_format=None,
    num_predict: int = 512,
) -> str:
    """Call the local Ollama model. Raises RuntimeError with actionable text."""

    # Fast probe first: a dead server or missing model should fail in
    # ~3 seconds with a helpful message, not hang for OLLAMA_TIMEOUT.
    probe = probe_ollama()
    if not probe["reachable"]:
        raise RuntimeError(
            f"Ollama is not reachable at {OLLAMA_BASE_URL} "
            f"({probe['error']}). Start it with: ollama serve "
            f"(on Windows, start the Ollama app), then try again."
        )
    if not probe["model_installed"]:
        raise RuntimeError(
            f"Ollama is running but model '{OLLAMA_MODEL}' is not installed. "
            f"Installed models: {', '.join(probe['installed_models']) or 'none'}. "
            f"Run: ollama pull {OLLAMA_MODEL}"
        )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt.strip()},
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
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        logger.error("Ollama HTTP error %s: %s", exc.code, details[:1000])
        raise RuntimeError(
            f"Ollama returned HTTP {exc.code}: {details[:500]}"
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        logger.exception("Ollama request timed out or failed")
        raise RuntimeError(
            f"Ollama request failed or timed out after {OLLAMA_TIMEOUT}s: {exc}"
        ) from exc
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.exception("Invalid Ollama response")
        raise RuntimeError("Ollama returned an invalid response.") from exc

    answer = result.get("message", {}).get("content", "").strip()
    if not answer:
        raise RuntimeError("Ollama returned an empty response.")

    logger.info(
        "Ollama request completed in %.2f seconds",
        time.monotonic() - started,
    )
    return answer


# ============================================================
# HUGGING FACE TRANSPORT (OpenAI-compatible router API)
# ============================================================


def _hf_generate(
    prompt: str,
    response_format=None,
    num_predict: int = 512,
) -> str:
    """Call the Hugging Face router chat-completions API."""

    if not HF_API_TOKEN:
        raise RuntimeError(
            "Hugging Face fallback is not configured: HF_TOKEN is empty "
            "in .env. Create a token at https://huggingface.co/settings/tokens "
            "and set HF_TOKEN, or start Ollama instead."
        )

    payload = {
        "model": HF_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt.strip()},
        ],
        "temperature": HF_TEMPERATURE,
        "max_tokens": max(64, min(int(num_predict), 1800)),
        "stream": False,
    }

    # The HF router's support for response_format varies per model/provider,
    # so JSON mode is enforced through the prompt (agents already demand a
    # bare JSON object) plus the pipeline's JSON cleaner.
    if response_format == "json":
        payload["messages"][1]["content"] = (
            f"{prompt.strip()}\n\nRespond with ONE valid JSON object only. "
            "No Markdown fences, no text before or after the JSON."
        )

    request = urllib.request.Request(
        HF_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {HF_API_TOKEN}",
        },
        method="POST",
    )

    started = time.monotonic()
    logger.info(
        "Hugging Face request started: model=%s, prompt_chars=%d, max_tokens=%d",
        HF_MODEL,
        len(prompt),
        payload["max_tokens"],
    )

    try:
        with urllib.request.urlopen(request, timeout=HF_TIMEOUT) as http_response:
            result = json.loads(http_response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        logger.error("Hugging Face HTTP error %s: %s", exc.code, details[:1000])
        hint = ""
        if exc.code in (401, 403):
            hint = " (check that HF_TOKEN is valid and has inference access)"
        elif exc.code == 404:
            hint = f" (check that model '{HF_MODEL}' exists on the router)"
        elif exc.code == 429:
            hint = " (rate limited; wait and retry, or use Ollama)"
        raise RuntimeError(
            f"Hugging Face returned HTTP {exc.code}{hint}: {details[:400]}"
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        logger.exception("Hugging Face request timed out or failed")
        raise RuntimeError(
            f"Hugging Face request failed or timed out after {HF_TIMEOUT}s: {exc}"
        ) from exc
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.exception("Invalid Hugging Face response")
        raise RuntimeError("Hugging Face returned an invalid response.") from exc

    try:
        answer = str(
            result["choices"][0]["message"]["content"] or ""
        ).strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise RuntimeError(
            f"Hugging Face response missing message content: "
            f"{json.dumps(result)[:300]}"
        ) from exc

    if not answer:
        raise RuntimeError("Hugging Face returned an empty response.")

    logger.info(
        "Hugging Face request completed in %.2f seconds",
        time.monotonic() - started,
    )
    return answer


# ============================================================
# PROVIDER RESOLUTION
# ============================================================


def _provider_chain() -> list[str]:
    """Ordered list of providers to attempt for one generation."""
    if LLM_PROVIDER == "ollama":
        return ["ollama"]
    if LLM_PROVIDER == "huggingface":
        return ["huggingface"]
    # auto: local first (free, private), cloud second (resilient).
    if HF_API_TOKEN:
        return ["ollama", "huggingface"]
    return ["ollama"]


def generate_response(
    prompt: str,
    response_format=None,
    num_predict: int = 512,
) -> str:
    """Generate a response using the configured provider chain.

    Tries each provider in order (LLM_PROVIDER=auto: Ollama, then Hugging
    Face). Only successful answers are cached. If every provider fails, a
    single RuntimeError with all provider errors is raised so the pipeline
    fallback has the full picture for the user.
    """

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("The LLM prompt cannot be empty.")

    # Cache key is provider-independent on purpose: a cached answer for the
    # same prompt is valid no matter which provider produced it.
    probe_payload = {
        "model": f"{LLM_PROVIDER}:auto",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt.strip()},
        ],
        "format": "json" if response_format == "json" else None,
        "options": {"num_predict": max(64, min(int(num_predict), 1800))},
    }
    cache_key = _cache_key(probe_payload)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(
            "LLM request served from cache: prompt_chars=%d", len(prompt)
        )
        return cached

    errors: list[str] = []

    for provider in _provider_chain():
        try:
            if provider == "ollama":
                answer = _ollama_generate(prompt, response_format, num_predict)
            else:
                answer = _hf_generate(prompt, response_format, num_predict)

            _cache_put(cache_key, answer)
            return answer

        except ValueError:
            # Prompt-level validation problems will not be fixed by
            # switching providers; re-raise immediately.
            raise
        except RuntimeError as exc:
            errors.append(f"[{provider}] {exc}")
            logger.warning(
                "Provider '%s' failed: %s; trying next provider",
                provider,
                str(exc)[:300],
            )

    raise RuntimeError(
        "All LLM providers failed. "
        + " | ".join(errors)
        + " — Hint: start Ollama (ollama serve) and pull the model "
        f"(ollama pull {OLLAMA_MODEL}), or set HF_TOKEN in .env to enable "
        "the Hugging Face fallback. GET /api/ai/status shows live details."
    )


def warmup_model() -> dict:
    """
    Preload the first available provider so the first user request does not
    pay the cold-start cost.

    Never raises: warmup failures are logged and returned as status.
    """
    started = time.monotonic()

    for provider in _provider_chain():
        try:
            if provider == "ollama":
                payload = {
                    "model": OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": "ping"}],
                    "stream": False,
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "options": {"num_predict": 1, "num_ctx": OLLAMA_NUM_CTX},
                }
                # Probe first so a dead server warms up in ~3s, not 120s.
                probe = probe_ollama()
                if not probe["reachable"] or not probe["model_installed"]:
                    raise RuntimeError(
                        probe["error"]
                        or f"model '{OLLAMA_MODEL}' is not installed"
                    )
                _post_chat(payload, min(OLLAMA_TIMEOUT, 120))
            else:
                _hf_generate("ping", None, 1)

            elapsed = time.monotonic() - started
            logger.info(
                "LLM warmup via %s completed in %.2f seconds",
                provider,
                elapsed,
            )
            return {
                "status": "ok",
                "provider": provider,
                "elapsed_seconds": round(elapsed, 2),
            }

        except Exception as exc:
            logger.warning("LLM warmup via %s failed: %s", provider, exc)

    return {
        "status": "failed",
        "error": "no configured provider could be warmed up",
    }


def get_llm_status() -> dict:
    """
    Live diagnostics for the /api/ai/status endpoint.

    Shows which provider is reachable, whether the Ollama model is
    installed, and which provider auto mode will use. Contains no secrets.
    """
    ollama = probe_ollama()
    hf = {
        "configured": bool(HF_API_TOKEN),
        "model": HF_MODEL,
        "api_url": HF_API_URL,
    }

    if LLM_PROVIDER == "ollama":
        active = "ollama" if ollama["reachable"] and ollama["model_installed"] else "none"
    elif LLM_PROVIDER == "huggingface":
        active = "huggingface" if hf["configured"] else "none"
    else:  # auto
        if ollama["reachable"] and ollama["model_installed"]:
            active = "ollama"
        elif hf["configured"]:
            active = "huggingface"
        else:
            active = "none"

    hints = []
    if not ollama["reachable"]:
        hints.append(f"Start Ollama at {OLLAMA_BASE_URL} (run: ollama serve).")
    elif not ollama["model_installed"]:
        hints.append(f"Run: ollama pull {OLLAMA_MODEL}")
    if not hf["configured"]:
        hints.append(
            "Set HF_TOKEN in .env to enable the Hugging Face cloud fallback."
        )
    if active == "none":
        hints.append(
            "Until a provider is available, AI analyses will return the "
            "rule-based fallback (a standard template response)."
        )

    return {
        "provider_setting": LLM_PROVIDER,
        "active_provider": active,
        "ollama": {
            "base_url": OLLAMA_BASE_URL,
            "model": OLLAMA_MODEL,
            "reachable": ollama["reachable"],
            "model_installed": ollama["model_installed"],
            "installed_models": ollama["installed_models"],
            "error": ollama["error"],
        },
        "huggingface": hf,
        "hints": hints,
    }
