from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from .models import DocumentClassConfig, DocumentDTO, load_document_configs
from .llm_client import call_llm_with_retry
from .logging_config import log_intermediate

logger = logging.getLogger(__name__)
load_dotenv()


class DocumentClassifier:
    def __init__(self, config_directory: str | Path = "configs") -> None:
        self.configs = load_document_configs(config_directory)

    def _heuristic(self, text: str) -> tuple[str | None, int]:
        text_lower = text.casefold()
        best_id: str | None = None
        best_score = 0
        for config in self.configs:
            score = sum(
                2 if keyword.casefold() in text_lower else 0
                for keyword in config.classification_keywords
            )
            if score > best_score:
                best_score = score
                best_id = config.class_id
        return best_id, best_score

    def _llm_classify(self, document: DocumentDTO) -> str | None:
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not api_key or not base_url or not model:
            return None
        client = OpenAI(api_key=api_key, base_url=base_url)
        allowed = ", ".join(config.class_id for config in self.configs)
        descriptions = "\n".join(
            f"- {config.class_id}: {config.description}" for config in self.configs
        )
        prompt = (
            "Jesteś klasyfikatorem polskich dokumentów zamówień publicznych. "
            f"Klasy dozwolone: {allowed}. UNKNOWN oznacza brak dopasowania.\n"
            f"{descriptions}\n\n"
            "Zwróć WYŁĄCZNIE obiekt JSON: {\"class_id\":\"...\"}.\n"
            "Treść dokumentu:\n" + document.get_relevant_text(
                int(os.getenv("MAX_FIRST_PAGES", "4")), True
            )[:20_000]
        )
        try:
            response = call_llm_with_retry(
                client,
                model=model,
                messages=[
                    {"role": "system", "content": "Odpowiadaj wyłącznie poprawnym JSON-em."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            log_intermediate(
                logger,
                f"Odpowiedź LLM klasyfikacji {document.source_path}",
                response.choices[0].message.content or "{}",
            )
            candidate = payload.get("class_id")
            return candidate if candidate in {config.class_id for config in self.configs} else None
        except Exception as exc:
            logger.warning("LLM classification failed: %s", exc)
            return None

    def classify(self, document: DocumentDTO) -> DocumentClassConfig | None:
        text = document.get_relevant_text(
            int(os.getenv("MAX_FIRST_PAGES", "4")), True
        )
        log_intermediate(logger, f"Tekst przekazany do klasyfikacji {document.source_path}", text)
        heuristic_id, score = self._heuristic(text)
        logger.info(
            "Klasyfikacja heurystyczna %s: wynik=%s, wynik punktowy=%d",
            document.source_path,
            heuristic_id or "UNKNOWN",
            score,
        )
        if score >= 4:
            return next(config for config in self.configs if config.class_id == heuristic_id)
        llm_id = self._llm_classify(document)
        if llm_id:
            return next(config for config in self.configs if config.class_id == llm_id)
        if score >= 2 and heuristic_id:
            return next(config for config in self.configs if config.class_id == heuristic_id)
        return None
