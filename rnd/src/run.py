"""Batch smoke-test runner: PDF -> text -> LLM -> Resume JSON.

Walks rnd/data/resume/, saves three files per PDF into rnd/data/results/:
    <name>.txt           — raw text after pypdf
    <name>.raw.json      — raw LLM response
    <name>.parsed.json   — Pydantic-validated Resume

Run:
    python -m rnd.src.run                 # from repo root
    python rnd/src/run.py                 # also works
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

# Make `core.logger` importable when running this file directly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from loguru import logger

from core.logger import setup_logging

try:
    from .openrouter_client import OpenRouterClient
    from .pdf_parser import pdf_to_text
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from openrouter_client import OpenRouterClient
    from pdf_parser import pdf_to_text


def find_input_dir(rnd_root: Path) -> Path:
    in_dir = rnd_root / "data" / "resume"
    if not in_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {in_dir}")
    if not any(in_dir.glob("*.pdf")):
        raise FileNotFoundError(f"No PDFs found in {in_dir}")
    return in_dir


def main() -> int:
    setup_logging(
        level=os.getenv("LOG_LEVEL", "INFO"),
        json_mode=os.getenv("LOG_JSON", "false").lower() == "true",
    )

    rnd_root = Path(__file__).resolve().parents[1]
    in_dir = find_input_dir(rnd_root)
    out_dir = rnd_root / "data" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(in_dir.glob("*.pdf"))
    logger.info("run: in_dir={}, out_dir={}, pdfs={}", in_dir, out_dir, len(pdfs))

    client = OpenRouterClient()
    failures = 0

    for pdf in pdfs:
        stem = pdf.stem
        txt_path = out_dir / f"{stem}.txt"
        raw_path = out_dir / f"{stem}.raw.json"
        parsed_path = out_dir / f"{stem}.parsed.json"

        logger.info("[{}] start", stem)
        text = pdf_to_text(pdf)
        txt_path.write_text(text, encoding="utf-8")
        logger.info("[{}] wrote {}", stem, txt_path.name)

        try:
            parsed, raw = client.extract_resume(text)
        except Exception:
            failures += 1
            err_path = out_dir / f"{stem}.error.txt"
            err_path.write_text(traceback.format_exc(), encoding="utf-8")
            logger.exception("[{}] FAILED — see {}", stem, err_path.name)
            continue

        raw_path.write_text(raw, encoding="utf-8")
        parsed_path.write_text(
            parsed.model_dump_json(indent=2, exclude_none=False),
            encoding="utf-8",
        )
        logger.info("[{}] wrote {} and {}", stem, raw_path.name, parsed_path.name)

    logger.info(
        "run: done. results_in={}, failures={}/{}", out_dir, failures, len(pdfs)
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
