from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def flatten(value: Any, path: str = "", include_nulls: bool = False) -> set[tuple[str, str]]:
    if isinstance(value, dict):
        if not value:
            return {(path, "{}")} if path else set()
        pairs: set[tuple[str, str]] = set()
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            pairs |= flatten(child, child_path, include_nulls)
        return pairs
    if isinstance(value, list):
        if not value:
            return {(path, "[]")} if path else set()
        pairs = set()
        for index, child in enumerate(value):
            pairs |= flatten(child, f"{path}[{index}]", include_nulls)
        return pairs
    if value is None:
        return {(path, "null")} if (path and include_nulls) else set()
    return {(path, " ".join(str(value).strip().casefold().split()))}


def load_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8").strip()
    return json.loads(raw) if raw else {}


def score(generated_dir: Path, reference_dir: Path) -> dict[str, Any]:
    tp = fp = fn = 0
    field_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    references = {p.relative_to(reference_dir): p for p in reference_dir.rglob("*.json")}
    generated = {p.relative_to(generated_dir): p for p in generated_dir.rglob("*.json")}

    for relative in sorted(set(references) | set(generated)):
        predicted = flatten(load_json(generated[relative])) if relative in generated else set()
        expected = flatten(load_json(references[relative])) if relative in references else set()
        tp += len(predicted & expected)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
        for path, val in predicted & expected:
            field_stats[path.split("[")[0]][0] += 1
        for path, val in predicted - expected:
            field_stats[path.split("[")[0]][1] += 1
        for path, val in expected - predicted:
            field_stats[path.split("[")[0]][2] += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    worst = []
    for k, (ftp, ffp, ffn) in field_stats.items():
        fp_r = ftp / (ftp + ffp) if ftp + ffp else 0.0
        fr_r = ftp / (ftp + ffn) if ftp + ffn else 0.0
        ff1 = 2 * fp_r * fr_r / (fp_r + fr_r) if fp_r + fr_r else 0.0
        worst.append((ff1, k, ftp, ffp, ffn))
    return {
        "non_null_precision": round(precision, 4),
        "non_null_recall": round(recall, 4),
        "non_null_f1": round(f1, 4),
        "tp": tp, "fp": fp, "fn": fn,
        "worst_fields": [
            {"field": k, "f1": round(ff1, 3), "tp": ftp, "fp": ffp, "fn": ffn}
            for ff1, k, ftp, ffp, ffn in sorted(worst)[:12]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated", default="./output")
    parser.add_argument("--reference", default="./reference")
    args = parser.parse_args()
    print(json.dumps(score(Path(args.generated), Path(args.reference)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())