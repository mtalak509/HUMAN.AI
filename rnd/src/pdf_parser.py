from pathlib import Path

from loguru import logger
from pypdf import PdfReader


def pdf_to_text(path: str | Path) -> str:
    """Extract text from PDF and keep page boundaries."""
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {pdf_path.name}")

    logger.info("pdf_to_text: reading {}", pdf_path)
    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    empty_pages: list[int] = []
    for i, page in enumerate(reader.pages, start=1):
        # Some pages can be image-only; extract_text() then returns None.
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            empty_pages.append(i)
        pages.append(f"--- PAGE {i} ---\n{page_text}")

    result = "\n\n".join(pages)
    logger.info(
        "pdf_to_text: {} — pages={}, chars={}, empty_pages={}",
        pdf_path.name,
        len(pages),
        len(result),
        empty_pages or "none",
    )
    return result

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python pdf_parser.py <path-to-pdf> [out.txt]")
        sys.exit(1)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) >= 3 else src.with_suffix(".txt")
    dst.write_text(pdf_to_text(src), encoding="utf-8")
    print(f"Saved to: {dst}")