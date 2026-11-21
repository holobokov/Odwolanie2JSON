from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def flatten(value: Any, path: str = "") -> set[tuple[str, str]]:
    if isinstance(value, dict):
        if not value:
            return {(path, "{}")} if path else set()
        pairs: set[tuple[str, str]] = set()
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            pairs |= flatten(child, child_path)
        return pairs
    if isinstance(value, list):
        if not value:
            return {(path, "[]")} if path else set()
        pairs = set()
        for index, child in enumerate(value):
            pairs |= flatten(child, f"{path}[{index}]")
        return pairs
    if value is None:
        return {(path, "null")} if path else set()
    return {(path, str(value).strip().casefold())}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def score(generated_dir: Path, reference_dir: Path) -> tuple[int, int, int]:
    tp = fp = fn = 0
    references = {p.relative_to(reference_dir): p for p in reference_dir.rglob("*.json")}
    generated = {p.relative_to(generated_dir): p for p in generated_dir.rglob("*.json")}
    for relative in set(references) | set(generated):
        predicted = flatten(load_json(generated[relative])) if relative in generated else set()
        expected = flatten(load_json(references[relative])) if relative in references else set()
        tp += len(predicted & expected)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
    return tp, fp, fn


def main() -> int:
    parser = argparse.ArgumentParser(description="Porównaj wygenerowane JSON-y z referencją")
    parser.add_argument("--generated", default="./output")
    parser.add_argument("--reference", default="./reference")
    args = parser.parse_args()
    tp, fp, fn = score(Path(args.generated), Path(args.reference))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    print(json.dumps({
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
