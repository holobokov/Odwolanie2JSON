from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st
import yaml

from src.classifier import DocumentClassifier
from src.extractor import LLMExtractor
from src.reader import PdfReader


st.set_page_config(page_title="Odwołania2JSON", layout="wide")
st.title("Odwołania2JSON")

tab_extract, tab_config = st.tabs(["Ekstrakcja PDF", "Nowa klasa YAML"])

with tab_extract:
    uploaded = st.file_uploader("Wybierz PDF", type=["pdf"])
    if uploaded:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = Path(tmp.name)
        document = PdfReader().read(tmp_path)
        config = DocumentClassifier("configs").classify(document)
        left, right = st.columns(2)
        with left:
            st.subheader("Diagnostyka stron")
            for page in document.pages:
                with st.expander(f"Strona {page.number} · {page.type.value} · {page.char_count} znaków"):
                    st.text(page.text or "(brak tekstu)")
        with right:
            st.subheader("Wynik ekstrakcji")
            if config is None:
                st.json({})
            else:
                st.json(LLMExtractor("configs").extract(document, config))
                st.caption(f"Klasa: {config.class_id}")
        tmp_path.unlink(missing_ok=True)

with tab_config:
    st.subheader("Dodaj klasę dokumentu przez YAML")
    class_id = st.text_input("class_id", value="nowa-klasa")
    description = st.text_area("description (polski opis)", value="")
    keywords = st.text_area("classification_keywords (po jednym na linię)", value="")
    schema_text = st.text_area(
        "schema_spec (YAML)",
        value="root_fields:\n  nowe_pole:\n    typ: \"string | null\"\n",
        height=220,
    )
    if st.button("Zapisz konfigurację"):
        try:
            schema_spec = yaml.safe_load(schema_text) or {}
            safe_name = "".join(
                c.lower() if c.isalnum() or c in "-_" else "-"
                for c in class_id
            ).strip("-") + ".yaml"
            config = {
                "class_id": class_id,
                "description": description,
                "classification_keywords": [
                    line.strip() for line in keywords.splitlines() if line.strip()
                ],
                "pages_strategy": {"first_pages": 4, "include_last": True},
                "schema_spec": schema_spec,
            }
            target = Path("configs") / safe_name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
            st.success(f"Zapisano {target}")
        except yaml.YAMLError as exc:
            st.error(f"Błąd YAML: {exc}")
