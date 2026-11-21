from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PageType(str, Enum):
    NATIVE_TEXT = "NATIVE_TEXT"
    SCANNED_OCR = "SCANNED_OCR"
    EMPTY = "EMPTY"


class PageDTO(BaseModel):
    number: int
    type: PageType
    text: str = ""
    char_count: int = 0


class DocumentDTO(BaseModel):
    source_path: str
    pages: list[PageDTO] = Field(default_factory=list)

    def get_relevant_text(self, max_first_pages: int = 4, include_last: bool = True) -> str:
        if not self.pages:
            return ""
        selected: list[PageDTO] = []
        seen: set[int] = set()
        for page in self.pages[: max(0, max_first_pages)]:
            seen.add(page.number)
            selected.append(page)
        if include_last and self.pages:
            last = self.pages[-1]
            if last.number not in seen:
                selected.append(last)
        return "\n\n".join(
            f"--- STRONA {page.number} [{page.type.value}] ---\n{page.text}"
            for page in selected
            if page.text.strip()
        )


class DocumentClassConfig(BaseModel):
    class_id: str
    description: str
    classification_keywords: list[str] = Field(default_factory=list)
    pages_strategy: dict[str, Any] = Field(default_factory=dict)
    schema_spec: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "DocumentClassConfig":
        with Path(path).open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return cls.model_validate(data)


def load_document_configs(directory: str | Path = "configs") -> list[DocumentClassConfig]:
    directory = Path(directory)
    return [
        DocumentClassConfig.load(path)
        for path in sorted(directory.glob("*.yaml"))
        if path.is_file()
    ]
