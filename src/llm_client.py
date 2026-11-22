from __future__ import annotations

import logging
import os
import threading
import time
from functools import lru_cache

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from .logging_config import log_intermediate
import re

def parse_json_response(content: str | None) -> dict:
    text = (content or "").strip()
    # Strip <think>...</think> reasoning blocks if a model emits them (e.g., Qwen)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    # Strip ```json ... ``` markdown fences
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return json.loads(text)

logger = logging.getLogger(__name__)

_RATE_LOCK = threading.Lock()
_LAST_CALL_TS: float = 0.0


@lru_cache(maxsize=4)
def get_client(api_key: str, base_url: str) -> OpenAI:
    timeout = float(os.getenv("LLM_TIMEOUT_SEC", "60"))
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)


def call_llm_with_retry(client: OpenAI, **kwargs):
    global _LAST_CALL_TS
    min_interval = float(os.getenv("LLM_MIN_INTERVAL", "0.25"))
    model = kwargs.get("model", "unknown")

    # Mistral requires top_p=1 when temperature=0 (error code 3054)
    if kwargs.get("temperature", None) == 0 and "top_p" not in kwargs:
        kwargs["top_p"] = 1.0

    logger.info("Wysyłanie żądania LLM; model=%s", model)
    log_intermediate(logger, f"Pełne argumenty żądania LLM model={model}", kwargs)

    for attempt in range(5):
        with _RATE_LOCK:
            elapsed = time.monotonic() - _LAST_CALL_TS
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            _LAST_CALL_TS = time.monotonic()

        try:
            response = client.chat.completions.create(**kwargs)
            usage = getattr(response, "usage", None)
            logger.info(
                "Odpowiedź LLM odebrana; model=%s, próba=%d, użycie=%s",
                model,
                attempt + 1,
                getattr(usage, "model_dump", lambda: usage)(),
            )
            return response
        except RateLimitError as exc:
            wait = min(30, 2 * (2**attempt))
            logger.warning("Rate limit (429), czekam %ss... (%s)", wait, exc)
            time.sleep(wait)
        except (APIConnectionError, APIStatusError) as exc:
            status = getattr(exc, "status_code", 500)
            if status in (408, 429, 500, 502, 503, 504) and attempt < 4:
                wait = min(20, 1.5 * (2**attempt))
                logger.warning("Błąd przejściowy LLM (%s), ponawiam za %.1fs", status, wait)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Przekroczono limit ponowień LLM po 5 próbach")