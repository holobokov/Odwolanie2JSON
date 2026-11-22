from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageOps

from .logging_config import log_intermediate
from .models import DocumentDTO, PageDTO, PageType

logger = logging.getLogger(__name__)


def _looks_garbled_or_empty(text: str, min_alnum: int = 50) -> bool:
    if not text or "(cid:" in text.lower():
        return True
    alnum = sum(ch.isalnum() for ch in text)
    if alnum < min_alnum:
        return True
    return (text.count("\ufffd") / max(len(text), 1)) > 0.05


class PdfReader:
    def __init__(self, dpi: int | None = None, max_first_pages: int | None = None) -> None:
        self.dpi = dpi or int(os.getenv("OCR_DPI", "220"))
        self.max_first_pages = (
            max_first_pages
            if max_first_pages is not None
            else int(os.getenv("MAX_FIRST_PAGES", "4"))
        )
        self._ocr = None
        self._has_tess = self._check_tesseract_pol()

    @staticmethod
    def _check_tesseract_pol() -> bool:
        if shutil.which("tesseract") is None:
            return False
        try:
            return "pol" in pytesseract.get_languages(config="")
        except Exception:
            return False

    def _ocr_engine(self):
        if self._ocr is None:
            logger.info("Inicjalizacja silnika RapidOCR (Polish/Latin)")
            try:
                from rapidocr import EngineType, LangRec, OCRVersion, RapidOCR

                try:
                    self._ocr = RapidOCR(
                        params={
                            "Rec.lang_type": LangRec.LATIN,
                            "Rec.engine_type": EngineType.ONNXRUNTIME,
                            "Rec.ocr_version": OCRVersion.PPOCRV4,
                            "Det.ocr_version": OCRVersion.PPOCRV4,
                        }
                    )
                except Exception as exc:
                    logger.warning("Fallback do domyślnego RapidOCR: %s", exc)
                    self._ocr = RapidOCR()
            except ImportError:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr = RapidOCR()
        return self._ocr

    def _ocr_image(self, pil_img: Image.Image) -> str:
        if self._has_tess:
            gray = ImageOps.grayscale(pil_img)
            return pytesseract.image_to_string(gray, lang="pol+eng", config="--psm 4").strip()

        arr = np.array(pil_img.convert("RGB"))
        engine_result = self._ocr_engine()(arr)
        if hasattr(engine_result, "txts"):
            texts = engine_result.txts
            return "\n".join(str(t) for t in (texts or []) if t).strip()
        result = engine_result[0] if isinstance(engine_result, tuple) else engine_result
        if not result:
            return ""
        lines = []
        for item in result:
            if isinstance(item, (list, tuple)) and len(item) >= 2 and item[1]:
                lines.append(str(item[1]))
            elif isinstance(item, str) and item:
                lines.append(item)
        return "\n".join(lines).strip()

    def read(self, pdf_path: str | Path) -> DocumentDTO:
        path = Path(pdf_path)
        pages: list[PageDTO] = []
        logger.info("Otwarto PDF do odczytu: %s", path)
        pdf = pdfium.PdfDocument(str(path))
        try:
            total = len(pdf)
            indices = set(range(min(self.max_first_pages, total)))
            if total > 0:
                indices.add(total - 1)
            scale = self.dpi / 72.0

            for index in sorted(indices):
                page = pdf[index]
                textpage = None
                bitmap = None
                try:
                    textpage = page.get_textpage()
                    text = textpage.get_text_bounded().strip()
                    if not _looks_garbled_or_empty(text):
                        page_type = PageType.NATIVE_TEXT
                        logger.info("Strona %d: tekst natywny, %d znaków", index + 1, len(text))
                    else:
                        bitmap = page.render(scale=scale)
                        pil_img = bitmap.to_pil()
                        text = self._ocr_image(pil_img)
                        page_type = PageType.SCANNED_OCR if text else PageType.EMPTY
                        logger.info("Strona %d: OCR (%s), %d znaków", index + 1, "tesseract" if self._has_tess else "rapidocr", len(text))
                finally:
                    if bitmap is not None:
                        bitmap.close()
                    if textpage is not None:
                        textpage.close()
                    page.close()

                pages.append(PageDTO(number=index + 1, type=page_type, text=text, char_count=len(text)))
                log_intermediate(logger, f"Tekst pośredni PDF {path}, strona {index + 1}", text)
        finally:
            pdf.close()

        return DocumentDTO(source_path=str(path), pages=pages)