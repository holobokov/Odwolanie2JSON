from __future__ import annotations

import logging
import os
from pathlib import Path

import fitz

from .models import DocumentDTO, PageDTO, PageType

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
            from rapidocr_onnxruntime import RapidOCR

            self._ocr = RapidOCR()
        return self._ocr

    def _ocr_pixmap(self, pixmap: fitz.Pixmap) -> str:
        import numpy as np

        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, pixmap.n
        )
        result, _ = self._ocr_engine()(image)
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
        with fitz.open(path) as document:
            indices = set(range(min(self.max_first_pages, document.page_count)))
            if document.page_count:
                indices.add(document.page_count - 1)
            for index in sorted(indices):
                page = document.load_page(index)
                text = page.get_text("text").strip()
                char_count = len(text)
                if char_count >= 80:
                    page_type = PageType.NATIVE_TEXT
                elif not text:
                    page_type = PageType.EMPTY
                    # Render blank or image-only pages at 220 DPI for OCR.
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(self.dpi / 72, self.dpi / 72), alpha=False)
                    text = self._ocr_pixmap(pixmap).strip()
                    char_count = len(text)
                    if text:
                        page_type = PageType.SCANNED_OCR
                else:
                    page_type = PageType.SCANNED_OCR
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(self.dpi / 72, self.dpi / 72), alpha=False)
                    text = self._ocr_pixmap(pixmap).strip()
                    char_count = len(text)
                pages.append(PageDTO(number=index + 1, type=page_type, text=text, char_count=char_count))
        return DocumentDTO(source_path=str(path), pages=pages)
