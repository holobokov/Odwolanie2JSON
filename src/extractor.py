from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .llm_client import call_llm_with_retry, get_client, parse_json_response
from .logging_config import log_intermediate
from .models import DocumentClassConfig, DocumentDTO
from .normalizer import normalize_document

logger = logging.getLogger(__name__)
load_dotenv()


class LLMExtractor:
    def __init__(self, config_directory: str | Path = "configs") -> None:
        self.config_directory = Path(config_directory)

    def extract(self, document: DocumentDTO, config: DocumentClassConfig) -> dict[str, Any]:
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not api_key or not base_url or not model:
            logger.warning("LLM configuration is incomplete; extraction skipped")
            return normalize_document(config.class_id, {})

        schema_json = json.dumps(config.schema_spec, ensure_ascii=False, indent=2)
        text = document.get_relevant_text(
            int(config.pages_strategy.get("first_pages", os.getenv("MAX_FIRST_PAGES", "4"))),
            bool(config.pages_strategy.get("include_last", True)),
        )
        prompt = (
            "Wypakuj dane z polskiego dokumentu zamówień publicznych. "
            "Nie zgaduj brakujących ani zamazanych danych (zwróć null, nigdy '***' ani '[REDACTED]'). "
            "Zwróć WYŁĄCZNIE jeden poprawny obiekt JSON.\n\n"
            f"Kategoria: {config.class_id} — {config.description}\n"
            f"Instrukcje i schema_spec:\n{schema_json}\n\n"
            "Tekst dokumentu:\n" + text[:24_000]
        )
        log_intermediate(logger, f"Tekst do ekstrakcji {document.source_path}", text)

        try:
            client = get_client(api_key, base_url)
            messages = [
                {"role": "system", "content": "Ekstraktor danych. Zwracaj wyłącznie poprawny JSON zgodny ze schema_spec."},
                {"role": "user", "content": prompt},
            ]
            response = call_llm_with_retry(
                client,
                model=model,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            log_intermediate(logger, f"Odpowiedź LLM ekstrakcji {document.source_path}", content)
            try:
                raw = parse_json_response(content)
            except json.JSONDecodeError:
                # One repair retry
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "To nie był poprawny JSON. Zwróć WYŁĄCZNIE poprawny obiekt JSON bez komentarzy."})
                response = call_llm_with_retry(
                    client, model=model, messages=messages, temperature=0, response_format={"type": "json_object"}
                )
                raw = parse_json_response(response.choices[0].message.content)
            return normalize_document(config.class_id, raw)
        except Exception as exc:
            logger.error("LLM extraction failed for %s: %s", document.source_path, exc)
            return normalize_document(config.class_id, {})