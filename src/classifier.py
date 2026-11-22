from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .llm_client import call_llm_with_retry, get_client, parse_json_response
from .logging_config import log_intermediate
from .models import DocumentClassConfig, DocumentDTO, load_document_configs

logger = logging.getLogger(__name__)
load_dotenv()


class DocumentClassifier:
    def __init__(self, config_directory: str | Path = "configs") -> None:
        self.configs = load_document_configs(config_directory)

    def _keyword_hints(self, text: str) -> dict[str, int]:
        text_lower = text.casefold()
        return {
            cfg.class_id: sum(1 for kw in cfg.classification_keywords if kw.casefold() in text_lower)
            for cfg in self.configs
        }

    def _llm_classify(self, document: DocumentDTO, hints: dict[str, int]) -> tuple[str | None, float]:
        api_key = os.getenv("LLM_API_KEY", "").strip()
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL")
        if not base_url or not model:
            return None, 0.0
        client = get_client(api_key, base_url)

        allowed = ", ".join(cfg.class_id for cfg in self.configs)
        descriptions = "\n".join(f"- {cfg.class_id}: {cfg.description}" for cfg in self.configs)
        text = document.get_relevant_text(int(os.getenv("MAX_FIRST_PAGES", "4")), True)[:10_000]

        prompt = (
            "Jesteś klasyfikatorem polskich dokumentów zamówień publicznych. Ignoruj nazwę pliku.\n"
            f"Dozwolone klasy: {allowed}, UNKNOWN.\n"
            f"{descriptions}\n"
            "- UNKNOWN: KAŻDY inny dokument, w tym: ogłoszenie o zamówieniu (TED / OJ S / BZP), "
            "wyrok lub postanowienie KIO ('Krajowa Izba Odwoławcza w składzie... po rozpoznaniu... orzeka'), "
            "prezentacja lub materiał szkoleniowy o KIO, SWZ/OPZ, decyzja ministra lub urzędu, "
            "pismo przewodnie, broszura, przystąpienie, wezwanie, informacja z otwarcia ofert, "
            "faktura, KRS, odpowiedź zamawiającego, oraz dokument zawierający jedynie pouczenie "
            "o możliwości złożenia odwołania do KIO.\n\n"
            f"Pomocnicza liczba trafień słów kluczowych: {hints}\n"
            'Zwróć WYŁĄCZNIE JSON: {"class_id": "...", "confidence": 0.95, "reason": "..."}.\n\n'
            f"Treść dokumentu:\n{text}"
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
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            raw_content = response.choices[0].message.content or "{}"
            log_intermediate(logger, f"Odpowiedź LLM klasyfikacji {document.source_path}", raw_content)
            payload = parse_json_response(raw_content)
            candidate = str(payload.get("class_id", "UNKNOWN")).strip()
            confidence = float(payload.get("confidence", 1.0) or 0.0)
            valid_ids = {cfg.class_id for cfg in self.configs}
            if candidate in valid_ids and confidence >= float(os.getenv("MIN_CLASS_CONFIDENCE", "0.60")):
                return candidate, confidence
            return None, confidence
        except Exception as exc:
            logger.warning("LLM classification failed: %s", exc)
            return None, 0.0

    def classify(self, document: DocumentDTO) -> DocumentClassConfig | None:
        text = document.get_relevant_text(int(os.getenv("MAX_FIRST_PAGES", "4")), True)
        if not text.strip():
            return None
        hints = self._keyword_hints(text)
        llm_id, conf = self._llm_classify(document, hints)
        logger.info("Klasyfikacja %s: wynik=%s (conf=%.2f, hints=%s)", document.source_path, llm_id or "UNKNOWN", conf, hints)
        if llm_id:
            return next(cfg for cfg in self.configs if cfg.class_id == llm_id)
        return None