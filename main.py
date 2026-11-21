from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from src.pipeline import Pipeline


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Konwertuj wielodokumentowe PDF-y odwołań KIO do JSON"
    )
    parser.add_argument("--input", default="./input")
    parser.add_argument("--output", default="./output")
    parser.add_argument("--configs", default="./configs")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
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

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
