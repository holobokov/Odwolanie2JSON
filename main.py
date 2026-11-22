from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.logging_config import configure_logging

def main() -> int:
    if sys.version_info < (3, 13):
        print(
            "Projekt wymaga Python 3.13+. "
            "Zainstaluj go albo uruchom Dockerem: docker compose up --build"
        )
        return 2
    try:
        from dotenv import load_dotenv
        from src.pipeline import Pipeline
    except ModuleNotFoundError as exc:
        print(
            f"Brakuje zależności: {exc.name}. "
            "Uruchom: python -m pip install -r requirements.txt "
            "lub ./run.sh"
        )
        return 2

    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Konwertuj wielodokumentowe PDF-y odwołań KIO do JSON"
    )
    parser.add_argument("--input", default="./input")
    parser.add_argument("--output", default="./output")
    parser.add_argument("--configs", default="./configs")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    log_file = configure_logging(args.log_level)
    logging.getLogger(__name__).info("Uruchomiono CLI; plik logu: %s", log_file)
    processed, successful = Pipeline(
        input_directory=Path(args.input),
        output_directory=Path(args.output),
        config_directory=Path(args.configs),
    ).run()
    logging.getLogger(__name__).info(
        "Zakończono: przetworzono %d, zapisano %d plików JSON",
        processed,
        successful,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
