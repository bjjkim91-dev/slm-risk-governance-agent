"""File ingestion: text extraction and chunking."""

from __future__ import annotations

import re
from pathlib import Path

from config import CHUNK_SIZE_CHARS, CHUNK_OVERLAP_CHARS, SUPPORTED_FILE_TYPES


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from an uploaded file based on extension."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_FILE_TYPES:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {SUPPORTED_FILE_TYPES}")

    if ext in (".txt", ".md"):
        return file_bytes.decode("utf-8", errors="replace")

    if ext == ".pdf":
        return _extract_pdf(file_bytes)

    if ext == ".csv":
        return _extract_csv(file_bytes)

    if ext in (".xlsx", ".xls"):
        return _extract_excel(file_bytes)

    if ext == ".docx":
        return _extract_docx(file_bytes)

    raise ValueError(f"No extractor for {ext}")


def _extract_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("PyMuPDF is required for PDF support. Install with: pip install PyMuPDF")

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            pages.append(f"[Page {i + 1}]\n{text}")
    doc.close()

    if not pages:
        raise ValueError("PDF appears to contain no extractable text (possibly scanned/image-based).")

    return "\n\n".join(pages)


def _extract_csv(file_bytes: bytes) -> str:
    """Extract text from CSV by converting rows to readable text."""
    import io
    import csv

    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        raise ValueError("CSV file is empty.")

    headers = rows[0]
    lines = []
    for i, row in enumerate(rows[1:], 1):
        parts = [f"{h}: {v}" for h, v in zip(headers, row) if v.strip()]
        if parts:
            lines.append(f"[Row {i}] " + " | ".join(parts))

    return "\n".join(lines)


def _extract_excel(file_bytes: bytes) -> str:
    """Extract text from Excel by reading all sheets."""
    import io
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    all_text = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        all_text.append(f"[Sheet: {sheet_name}]")
        headers = [str(h) if h is not None else "" for h in rows[0]]

        for i, row in enumerate(rows[1:], 1):
            parts = []
            for h, v in zip(headers, row):
                if v is not None and str(v).strip():
                    parts.append(f"{h}: {v}")
            if parts:
                all_text.append(f"[Row {i}] " + " | ".join(parts))

        all_text.append("")

    wb.close()

    if not all_text:
        raise ValueError("Excel file contains no data.")

    return "\n".join(all_text)


def _extract_docx(file_bytes: bytes) -> str:
    """Extract text from Word (.docx) documents."""
    import io
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            if para.style and para.style.name and para.style.name.startswith("Heading"):
                paragraphs.append(f"\n## {text}")
            else:
                paragraphs.append(text)

    for table in doc.tables:
        headers = [cell.text.strip() for cell in table.rows[0].cells]
        for i, row in enumerate(table.rows[1:], 1):
            parts = []
            for h, cell in zip(headers, row.cells):
                v = cell.text.strip()
                if v:
                    parts.append(f"{h}: {v}")
            if parts:
                paragraphs.append(f"[Table Row {i}] " + " | ".join(parts))

    if not paragraphs:
        raise ValueError("Word document contains no extractable text.")

    return "\n\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    source_name: str = "",
    chunk_size: int = CHUNK_SIZE_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[dict]:
    """Split text into overlapping chunks, preferring paragraph/section boundaries.

    Returns list of dicts: {text, source_name, chunk_index, char_start, char_end}
    """
    if not text.strip():
        return []

    paragraphs = _split_into_paragraphs(text)
    chunks = []
    current_chunk = ""
    current_start = 0
    char_pos = 0

    for para in paragraphs:
        if len(current_chunk) + len(para) + 1 > chunk_size and current_chunk:
            chunks.append({
                "text": current_chunk.strip(),
                "source_name": source_name,
                "chunk_index": len(chunks),
                "char_start": current_start,
                "char_end": char_pos,
            })
            # Overlap: keep the tail of the current chunk
            overlap_text = current_chunk[-overlap:] if overlap > 0 else ""
            current_chunk = overlap_text + "\n\n" + para
            current_start = max(0, char_pos - overlap)
        else:
            if not current_chunk:
                current_start = char_pos
            current_chunk += ("\n\n" if current_chunk else "") + para

        char_pos += len(para) + 2  # +2 for the \n\n between paragraphs

    if current_chunk.strip():
        chunks.append({
            "text": current_chunk.strip(),
            "source_name": source_name,
            "chunk_index": len(chunks),
            "char_start": current_start,
            "char_end": char_pos,
        })

    return chunks


def _split_into_paragraphs(text: str) -> list[str]:
    """Split on double newlines or markdown headers."""
    parts = re.split(r"\n{2,}", text)
    result = []
    for part in parts:
        stripped = part.strip()
        if stripped:
            result.append(stripped)
    return result
