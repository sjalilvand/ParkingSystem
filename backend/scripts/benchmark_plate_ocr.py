"""Benchmark the Iranian plate OCR engine against a labeled CSV dataset.

Example (PowerShell):
  python scripts/benchmark_plate_ocr.py --metadata ..\\metadata.csv --images-dir ..\\ocr-eval-images --output ..\\ocr-eval-report.csv

The CSV must contain: filename, plate_chars_ltr
Images are read from --images-dir. The script never changes source data.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import cv2

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.modules.plate_ocr import plate_text as pt  # noqa: E402
from app.modules.plate_ocr.engine import capabilities, get_reader  # noqa: E402


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance with O(min(len(a), len(b))) memory."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ca != cb),
            ))
        previous = current
    return previous[-1]


def read_rows(metadata: Path, images_dir: Path):
    with metadata.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"filename", "plate_chars_ltr"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV columns missing: {', '.join(sorted(missing))}")
        for row in reader:
            filename = (row.get("filename") or "").strip()
            truth_raw = (row.get("plate_chars_ltr") or "").strip()
            if not filename:
                continue
            # Resolve only a basename; metadata cannot escape the image directory.
            image_path = images_dir / Path(filename).name
            yield filename, truth_raw, pt.normalize(truth_raw), image_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Iranian plate OCR against CSV labels")
    parser.add_argument("--metadata", type=Path, required=True, help="CSV with filename,plate_chars_ltr")
    parser.add_argument("--images-dir", type=Path, required=True, help="Directory containing labeled images")
    parser.add_argument("--output", type=Path, default=Path("plate-ocr-benchmark.csv"))
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of labeled images")
    parser.add_argument("--min-conf", type=float, default=0.25)
    parser.add_argument("--slow-mode", action="store_true", help="Do not skip full-image fallback")
    args = parser.parse_args()

    if not args.metadata.is_file():
        parser.error(f"Metadata CSV not found: {args.metadata}")
    if not args.images_dir.is_dir():
        parser.error(f"Images directory not found: {args.images_dir}")

    caps = capabilities(args.models_dir)
    print("OCR capabilities:")
    for key, value in caps.items():
        print(f"  {key}: {value}")
    if not caps.get("opencv") or not caps.get("numpy"):
        print("ERROR: Install OCR dependencies first: pip install -r requirements-ocr.txt", file=sys.stderr)
        return 2
    if not caps.get("easyocr") and not (caps.get("crnn_weights") and caps.get("torch")):
        print("ERROR: No OCR backend available. Install EasyOCR or provide CRNN weights + torch.", file=sys.stderr)
        return 2

    reader = get_reader(args.models_dir)
    rows = []
    labeled = missing = 0
    exact_top1 = exact_top5 = 0
    total_chars = total_errors = 0
    started = time.perf_counter()

    for filename, truth_raw, truth, image_path in read_rows(args.metadata, args.images_dir):
        if args.limit and labeled + missing >= args.limit:
            break
        if not truth:
            continue
        labeled += 1
        if not image_path.is_file():
            missing += 1
            rows.append({
                "filename": filename, "truth": truth_raw, "prediction": "",
                "top_candidates": "", "exact_top1": 0, "exact_top5": 0,
                "char_error_rate": "", "confidence": "", "elapsed_ms": "",
                "status": "IMAGE_MISSING",
            })
            continue

        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            rows.append({
                "filename": filename, "truth": truth_raw, "prediction": "",
                "top_candidates": "", "exact_top1": 0, "exact_top5": 0,
                "char_error_rate": "", "confidence": "", "elapsed_ms": "",
                "status": "IMAGE_DECODE_ERROR",
            })
            continue

        t0 = time.perf_counter()
        result = reader.read_image(
            image, min_conf=args.min_conf, want_annotated=False,
            fast_mode=not args.slow_mode,
        )
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        candidates = []
        seen = set()
        for item in result.get("plates", []):
            candidate = pt.normalize(item.get("raw", ""))
            if candidate and candidate not in seen:
                seen.add(candidate)
                candidates.append((candidate, float(item.get("confidence") or 0)))
        best = pt.normalize((result.get("best") or {}).get("raw", ""))
        if not best and candidates:
            best = candidates[0][0]
        top5 = [candidate for candidate, _ in candidates[:5]]
        hit1 = int(best == truth)
        hit5 = int(truth in top5)
        distance = edit_distance(best, truth) if best else len(truth)
        cer = distance / max(1, len(truth))
        total_errors += distance
        total_chars += len(truth)
        exact_top1 += hit1
        exact_top5 += hit5
        rows.append({
            "filename": filename,
            "truth": truth,
            "prediction": best,
            "top_candidates": " | ".join(top5),
            "exact_top1": hit1,
            "exact_top5": hit5,
            "char_error_rate": round(cer, 4),
            "confidence": (result.get("best") or {}).get("confidence", ""),
            "elapsed_ms": elapsed_ms,
            "status": "OK" if result.get("success") else "NO_PLATE",
        })
        print(f"[{labeled}] {filename}: truth={truth} predicted={best or '-'} "
              f"top1={'OK' if hit1 else 'MISS'} time={elapsed_ms}ms")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["filename", "truth", "prediction", "top_candidates", "exact_top1",
              "exact_top5", "char_error_rate", "confidence", "elapsed_ms", "status"]
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    valid_rows = [r for r in rows if r["status"] in ("OK", "NO_PLATE")]
    scored = len(valid_rows)
    elapsed = round((time.perf_counter() - started), 2)
    print("\n=== SUMMARY ===")
    print(f"Labeled rows processed: {labeled}")
    print(f"Images missing: {missing}")
    print(f"Scored images: {scored}")
    print(f"Exact top-1: {exact_top1}/{scored} ({(100*exact_top1/scored if scored else 0):.1f}%)")
    print(f"Exact top-5: {exact_top5}/{scored} ({(100*exact_top5/scored if scored else 0):.1f}%)")
    print(f"Character error rate: {(total_errors/total_chars if total_chars else 0):.4f}")
    print(f"Wall time: {elapsed}s")
    print(f"Report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
