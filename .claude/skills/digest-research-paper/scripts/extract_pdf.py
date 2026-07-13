# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf>=4.0"]
# ///
"""Extract text and metadata from a research paper PDF.

Writes UTF-8 output files so downstream tools never hit Windows cp1252
encoding errors. Splits long papers into chunk files so each chunk fits
comfortably in an LLM context read.

Usage:
    uv run extract_pdf.py --pdf paper.pdf --outdir extracted/
    uv run extract_pdf.py --pdf paper.pdf --outdir extracted/ --chunk-chars 60000
"""

import argparse
import json
import sys
from pathlib import Path

from pypdf import PdfReader


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, help="Path to input PDF")
    parser.add_argument("--outdir", required=True, help="Directory for extracted output")
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=60000,
        help="Max characters per chunk file (default 60000)",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(pdf_path))

    pages = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001 - a single bad page should not kill extraction
            pages.append("")
            print(f"WARN: failed to extract page {i + 1}: {exc}", file=sys.stderr)

    full_text = "\n\n".join(
        f"[PAGE {i + 1}]\n{text}" for i, text in enumerate(pages)
    )

    if not full_text.strip():
        print(
            "ERROR: no extractable text (likely a scanned/image-only PDF).",
            file=sys.stderr,
        )
        return 2

    # Chunk on page boundaries so no page is split mid-sentence across files.
    chunks: list[str] = []
    current = ""
    for i, text in enumerate(pages):
        page_block = f"[PAGE {i + 1}]\n{text}\n\n"
        if current and len(current) + len(page_block) > args.chunk_chars:
            chunks.append(current)
            current = ""
        current += page_block
    if current:
        chunks.append(current)

    chunk_files = []
    for idx, chunk in enumerate(chunks, start=1):
        chunk_file = outdir / f"text_chunk_{idx:02d}.txt"
        chunk_file.write_text(chunk, encoding="utf-8")
        chunk_files.append(str(chunk_file))

    meta = reader.metadata or {}
    info = {
        "source_pdf": str(pdf_path.resolve()),
        "page_count": len(reader.pages),
        "total_chars": len(full_text),
        "chunk_files": chunk_files,
        "pdf_metadata": {
            "title": (meta.title or "").strip() or None,
            "author": (meta.author or "").strip() or None,
            "subject": (meta.subject or "").strip() or None,
            "producer": (meta.producer or "").strip() or None,
        },
    }
    info_file = outdir / "extraction_info.json"
    info_file.write_text(json.dumps(info, indent=2), encoding="utf-8")

    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
