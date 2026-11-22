from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

from .classifier import DocumentClassifier
from .extractor import LLMExtractor
from .logging_config import log_intermediate
from .reader import PdfReader

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
            log_intermediate(logger, f"Kanoniczny JSON po normalizacji {pdf_path}", result)
            return result
        except Exception as exc:
            logger.exception("Failed to process %s: %s", pdf_path, exc)
            return {}

    def _process_and_write(self, pdf_path: Path) -> bool:
        relative = pdf_path.relative_to(self.input_directory)
        destination = self.output_directory / relative.with_suffix(".json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = self.process_file(pdf_path)
        with destination.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        logger.info("Zapisano JSON: %s", destination)
        return True

    def run(self) -> tuple[int, int]:
        pdfs = list(self._pdf_files())
        logger.info("Skanowanie %s: znaleziono %d plików PDF", self.input_directory, len(pdfs))
        workers = max(1, int(os.getenv("MAX_WORKERS", "4")))
        processed = len(pdfs)
        successful = 0

        if workers == 1:
            for pdf_path in pdfs:
                try:
                    if self._process_and_write(pdf_path):
                        successful += 1
                except Exception as exc:
                    logger.exception("Could not write for %s: %s", pdf_path, exc)
            return processed, successful

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._process_and_write, p): p for p in pdfs}
            for fut in as_completed(futures):
                try:
                    if fut.result():
                        successful += 1
                except Exception as exc:
                    logger.exception("Worker error on %s: %s", futures[fut], exc)
        return processed, successful