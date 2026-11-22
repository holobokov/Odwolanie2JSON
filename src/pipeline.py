from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

from .classifier import DocumentClassifier
from .extractor import LLMExtractor
from .reader import PdfReader
from .logging_config import log_intermediate

logger = logging.getLogger(__name__)
load_dotenv()


class Pipeline:
    def __init__(
        self,
        input_directory: str | Path = "input",
        output_directory: str | Path = "output",
        config_directory: str | Path = "configs",
    ) -> None:
        self.input_directory = Path(input_directory)
        self.output_directory = Path(output_directory)
        self.reader = PdfReader()
        self.classifier = DocumentClassifier(config_directory)
        self.extractor = LLMExtractor(config_directory)

    def _pdf_files(self) -> Iterator[Path]:
        if not self.input_directory.exists():
            return
        yield from sorted(self.input_directory.rglob("*.pdf"))

    def process_file(self, pdf_path: str | Path) -> dict:
        pdf_path = Path(pdf_path)
        try:
            logger.info("Rozpoczęto przetwarzanie pliku: %s", pdf_path)
            document = self.reader.read(pdf_path)
            config = self.classifier.classify(document)
            if config is None:
                logger.info("Brak klasy dokumentu, zapisuję {}; plik: %s", pdf_path)
                return {}
            result = self.extractor.extract(document, config)
            logger.info("Ekstrakcja zakończona dla %s jako klasa %s", pdf_path, config.class_id)
            log_intermediate(
                logger,
                f"Kanoniczny JSON po normalizacji {pdf_path}",
                result,
            )
            return result
        except Exception as exc:
            logger.exception("Failed to process %s: %s", pdf_path, exc)
            return {}

    def run(self) -> tuple[int, int]:
        processed = 0
        successful = 0
        logger.info("Skanowanie katalogu wejściowego: %s", self.input_directory)
        pdf_count = sum(1 for _ in self._pdf_files())
        logger.info("Znaleziono %d plików PDF", pdf_count)
        for pdf_path in self._pdf_files():
            processed += 1
            relative = pdf_path.relative_to(self.input_directory)
            destination = self.output_directory / relative.with_suffix(".json")
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                result = self.process_file(pdf_path)
                with destination.open("w", encoding="utf-8") as handle:
                    json.dump(result, handle, ensure_ascii=False, indent=2)
                successful += 1
                logger.info("Zapisano JSON: %s", destination)
            except Exception as exc:
                logger.exception("Could not write %s: %s", destination, exc)
        return processed, successful
