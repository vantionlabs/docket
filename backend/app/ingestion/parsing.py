"""Document parsing: raw bytes -> plain text/markdown.

Markdown and plain text parse natively. PDF parsing needs the `docling`
extra (`uv sync --extra docling`) — it's kept optional because docling
pulls heavy dependencies the API image doesn't need.
"""

import tempfile
from pathlib import Path


class UnsupportedFileType(Exception):
    pass


TEXT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
}


def parse_document(raw: bytes, content_type: str, filename: str) -> str:
    if content_type in TEXT_TYPES or filename.lower().endswith((".md", ".txt")):
        return raw.decode("utf-8", errors="replace")

    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return _parse_pdf(raw, filename)

    raise UnsupportedFileType(
        f"Unsupported file type {content_type!r} ({filename}). "
        "Supported: .md, .txt, and .pdf (with the docling extra installed)."
    )


def _parse_pdf(raw: bytes, filename: str) -> str:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise UnsupportedFileType(
            "PDF parsing requires the docling extra: uv sync --extra docling"
        ) from exc

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / (Path(filename).name or "document.pdf")
        path.write_bytes(raw)
        result = DocumentConverter().convert(str(path))
        return result.document.export_to_markdown()
