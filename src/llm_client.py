from __future__ import annotations

import logging
import os
import time
from openai import OpenAI, RateLimitError
from .logging_config import log_intermediate

logger = logging.getLogger(__name__)

_LAST_CALL_TS: float = 0.0
_MIN_INTERVAL: float = float(os.getenv("LLM_MIN_INTERVAL", "1.1"))


def call_llm_with_retry(client: OpenAI, **kwargs):
    global _LAST_CALL_TS
    model = kwargs.get("model", "unknown")
    logger.info("Wysyłanie żądania LLM; model=%s", model)
    log_intermediate(logger, f"Pełne argumenty żądania LLM model={model}", kwargs)
    for attempt in range(4):
        elapsed = time.monotonic() - _LAST_CALL_TS
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        try:
            _LAST_CALL_TS = time.monotonic()
            response = client.chat.completions.create(**kwargs)
            usage = getattr(response, "usage", None)
            logger.info(
                "Odpowiedź LLM odebrana; model=%s, próba=%d, użycie=%s",
                model,
                attempt + 1,
                getattr(usage, "model_dump", lambda: usage)(),
            )
            return response
        except RateLimitError:
            wait = 5 * (attempt + 1)
            logger.warning("Mistral rate limit (429), czekam %ss...", wait)
            time.sleep(wait)
    raise RuntimeError("Przekroczono limit zapytań LLM (429) po 4 próbach")