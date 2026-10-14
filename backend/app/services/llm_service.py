
import json
import logging
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434",
).rstrip("/")

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))


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
        "keep_alive": "10m",
        "options": {
            "num_predict": max(64, min(int(num_predict), 1800)),
            "temperature": 0.2,
        },
    }

    if response_format == "json":
        payload["format"] = "json"

    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.monotonic()

    logger.info(
        "Ollama request started: model=%s, prompt_chars=%d, "
        "format=%s, num_predict=%d",
        OLLAMA_MODEL,
        len(prompt),
        response_format or "text",
        payload["options"]["num_predict"],
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_TIMEOUT,
        ) as http_response:
            result = json.loads(
                http_response.read().decode("utf-8")
            )

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
