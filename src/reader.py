from __future__ import annotations

import logging
import os
from pathlib import Path

import fitz

from .models import DocumentDTO, PageDTO, PageType
from .logging_config import log_intermediate

logger = logging.getLogger(__name__)


class PdfReader:
    def __init__(self, dpi: int | None = None, max_first_pages: int | None = None) -> None:
        self.dpi = dpi or int(os.getenv("OCR_DPI", "220"))
        self.max_first_pages = (
            max_first_pages
            if max_first_pages is not None
            else int(os.getenv("MAX_FIRST_PAGES", "4"))
        )
        self._ocr = None

    def _ocr_engine(self):
        if self._ocr is None:
            logger.info("Inicjalizacja silnika OCR")
            try:
                from rapidocr_onnxruntime import RapidOCR
                logger.info("Załadowano rapidocr-onnxruntime")
            except ImportError:
                from rapidocr import RapidOCR
                logger.info("Załadowano rapidocr")
            self._ocr = RapidOCR()
        return self._ocr

    def _ocr_pixmap(self, pixmap: fitz.Pixmap) -> str:
        import numpy as np

        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, pixmap.n
        )
        engine_result = self._ocr_engine()(image)
        if hasattr(engine_result, "txts"):
            texts = engine_result.txts
            return "\n".join(str(text) for text in texts if text)
        if isinstance(engine_result, tuple):
            result = engine_result[0]
        else:
            result = engine_result
        if not result:
            return ""
        lines: list[str] = []
        for item in result:
            if isinstance(item, (list, tuple)):
                if len(item) >= 2:
                    text = item[1]
                else:
                    continue
            elif isinstance(item, str):
                text = item
            else:
                continue
            if text:
                lines.append(str(text))
        return "\n".join(lines)

    def read(self, pdf_path: str | Path) -> DocumentDTO:
        path = Path(pdf_path)
        pages: list[PageDTO] = []
        logger.info("Otwarto PDF do odczytu: %s", path)
        with fitz.open(path) as document:
            logger.info(
                "Plik PDF %s ma %d stron; analizowane strony: pierwsze %d i ostatnia",
                path,
                document.page_count,
                self.max_first_pages,
            )
            indices = set(range(min(self.max_first_pages, document.page_count)))
            if document.page_count:
                indices.add(document.page_count - 1)
            for index in sorted(indices):
                page = document.load_page(index)
                text = page.get_text("text").strip()
                char_count = len(text)
                if char_count >= 80:
                    page_type = PageType.NATIVE_TEXT
                    logger.info("Strona %d: tekst natywny, %d znaków", index + 1, char_count)
                elif not text:
                    page_type = PageType.EMPTY
                    logger.info("Strona %d: brak tekstu natywnego, uruchamiam OCR", index + 1)
                    # Render blank or image-only pages at 220 DPI for OCR.
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(self.dpi / 72, self.dpi / 72), alpha=False)
                    logger.info("Strona %d: renderowanie OCR w %d DPI", index + 1, self.dpi)
                    text = self._ocr_pixmap(pixmap).strip()
                    char_count = len(text)
                    if text:
                        page_type = PageType.SCANNED_OCR
                        logger.info("Strona %d: OCR zakończony, %d znaków", index + 1, char_count)
                else:
                    page_type = PageType.SCANNED_OCR
                    logger.info("Strona %d: mało tekstu, uruchamiam OCR", index + 1)
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(self.dpi / 72, self.dpi / 72), alpha=False)
                    text = self._ocr_pixmap(pixmap).strip()
                    char_count = len(text)
                    logger.info("Strona %d: OCR zakończony, %d znaków", index + 1, char_count)
                pages.append(PageDTO(number=index + 1, type=page_type, text=text, char_count=char_count))
                log_intermediate(
                    logger,
                    f"Tekst pośredni PDF {path}, strona {index + 1}",
                    text,
                )
        logger.info("Zamknięto PDF i utworzono DocumentDTO: %s", path)
        return DocumentDTO(source_path=str(path), pages=pages)
