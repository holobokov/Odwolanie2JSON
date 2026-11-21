from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI

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
            "Nie zgaduj wartości nieobecnych w tekście. "
            "Zwróć WYŁĄCZNIE jeden poprawny obiekt JSON o wymaganym kluczu głównym.\n\n"
            f"Kategoria: {config.class_id} — {config.description}\n"
            f"Instrukcje i schema_spec:\n{schema_json}\n\n"
            "Tekst dokumentu:\n" + text[:30_000]
        )
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "Ekstraktor danych. Zwracaj tylko JSON zgodny ze schema_spec.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            raw = json.loads(content)
            return normalize_document(config.class_id, raw)
        except json.JSONDecodeError as exc:
            logger.error("LLM returned invalid JSON for %s: %s", document.source_path, exc)
        except Exception as exc:
            logger.error("LLM extraction failed for %s: %s", document.source_path, exc)
        return normalize_document(config.class_id, {})
