# Odwołania2JSON / Appeal PDFs to JSON

Production-oriented Python 3.13+ pipeline for the HackNation 2026 public procurement challenge. It recursively converts KIO appeal case PDFs from `input/<case>/<document>.pdf` to matching `output/<case>/<document>.json` files. Unknown or corrupted documents produce `{}`.

## Polish / Polski

### Szybki start

1. Skopiuj `.env.example` do `.env` i ustaw klucz/API EU-EEA.
2. Zainstaluj zależności: `python3.13 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`.
3. Wstaw pliki do `input/nazwa-sprawy/`.
4. Uruchom CLI: `python main.py`.
5. Uruchom interfejs: `./run.sh` lub `start.bat`.

Docker: `docker compose up --build`, następnie otwórz `http://localhost:8501`.

### Konfiguracja LLM

Projekt używa API zgodnego z OpenAI. Przykład Mistral API:

```env
LLM_API_KEY=...
LLM_BASE_URL=https://api.mistral.ai/v1
LLM_MODEL=ministral-8b-latest
OCR_DPI=220
MAX_FIRST_PAGES=4
```

Możliwe jest Ollama z `LLM_BASE_URL=http://host.docker.internal:11434/v1` i modelem lokalnym. Używaj modelu open-source hostowanego wyłącznie w EU/EEA, jeśli wymaga tego polityka HackNation lub regulamin instytucjonalny.

### Dodawanie nowej klasy dokumentu

Nie należy zmieniać kodu Python. Dodaj `configs/nazwa.yaml` z polami:

- `class_id`
- `description` po polsku
- `classification_keywords`
- `pages_strategy`
- `schema_spec` opisujące dokładny wynik JSON

Klasa zostanie automatycznie załadowana przy kolejnym uruchomieniu. Interfejs Streamlit również pozwala utworzyć podstawową konfigurację.

### Architektura

- `src/reader.py`: tekst natywny PyMuPDF lub RapidOCR dla stron zeskanowanych.
- `src/classifier.py`: heurystyki słów kluczowych oraz klasyfikacja lekkim LLM.
- `src/extractor.py`: JSON mode OpenAI-compatible API.
- `src/normalizer.py`: deterministyczne daty, identyfikatory, NIP, KRS, IBAN, TED, BZP i mapowanie czynności.
- `src/pipeline.py`: rekurencyjna hierarchia wejścia i wyjścia oraz odporność na błędy PDF.

### Logowanie operacji

CLI i interfejs Streamlit zapisują operacje do `logs/odwolania2json.log` z rotacją co 10 MB (maksymalnie 10 kopii). Zawiera zdarzenia takie jak otwarcie PDF, wybór stron, tryb tekstu/OCR, inicjalizacja OCR, klasyfikacja, wywołanie i odpowiedź LLM oraz zapis JSON/YAML.
Przy `LOG_INTERMEDIATE=true` logowana jest też pełna treść pośrednia: tekst stron PDF, tekst przekazany do klasyfikacji i ekstrakcji, prompt LLM oraz odpowiedź JSON.

Poziom i katalog logów można zmienić zmiennymi `.env`:

```env
LOG_LEVEL=INFO
LOG_DIR=./logs
LOG_INTERMEDIATE=true
```

### Ewaluacja

```bash
python eval/evaluate_f1.py --generated ./output --reference ./reference
```

Ewaluator spłaszcza zagnieżdżone obiekty i tablice do par `(ścieżka, znormalizowana_wartość)` i raportuje Precision, Recall i F1.

## English

### Setup

Copy `.env.example` to `.env`, install Python 3.13 dependencies, place PDFs under `input/<case_name>/`, and run `python main.py`. The CLI preserves the relative directory hierarchy and replaces `.pdf` with `.json`.

The web UI reads uploaded PDFs, shows page extraction diagnostics, and generates JSON. It also provides a form for creating YAML document classes.

### LLM provider

Configure `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`. The project works with OpenAI-compatible EU/EEA providers and local Ollama. CPU-only OCR and extraction do not require a GPU.

### Docker

```bash
docker compose up --build
```

Open `http://localhost:8501`. Volumes preserve `input`, `output`, and `configs`.
