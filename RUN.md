# Uruchomienie Odwołania2JSON

## Wykorzystywane usługi zewnętrzne
- **OVHcloud AI Endpoints** (`https://oai.endpoints.kepler.ai.cloud.ovh.net/v1`) — otwartoźródłowy model językowy (Apache 2.0) hostowany we Francji (EU/EOG, Zero Data Retention). Konfiguracja i opcjonalny klucz API znajdują się w `/opt/solution/.env`.
- **OCR (Tesseract `pol` + RapidOCR)** działa w 100% lokalnie na CPU wewnątrz kontenera Docker (bez GPU i bez zewnętrznego OCR API).

## Komenda uruchamiająca (ekstrakcja wsadowa `/opt/solution/input` -> `/opt/solution/output`)
```bash
docker compose run --rm cli