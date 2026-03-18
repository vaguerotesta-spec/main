"""
Extracts text content and position map from the CV PDF using PyMuPDF.
"""
from __future__ import annotations
import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import fitz  # PyMuPDF


@dataclass
class TextBlock:
    page: int
    block_no: int
    bbox: tuple[float, float, float, float]
    lines: list[dict[str, Any]] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return " ".join(
            span["text"]
            for line in self.lines
            for span in line["spans"]
        ).strip()


def extract(pdf_path: str | Path) -> tuple[str, list[TextBlock]]:
    doc = fitz.open(str(pdf_path))
    position_map: list[TextBlock] = []
    pages_text: list[str] = []
    for page_num, page in enumerate(doc):
        page_text_parts: list[str] = []
        raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            tb = TextBlock(
                page=page_num,
                block_no=block["number"],
                bbox=tuple(block["bbox"]),
            )
            for line in block.get("lines", []):
                line_spans = []
                line_text_parts = []
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    line_spans.append({
                        "text": span["text"],
                        "font": span.get("font", ""),
                        "size": span.get("size", 12),
                        "color": span.get("color", 0),
                        "bbox": tuple(span["bbox"]),
                    })
                    line_text_parts.append(text)
                if line_spans:
                    tb.lines.append({
                        "text": " ".join(line_text_parts),
                        "spans": line_spans,
                    })
            if tb.full_text:
                position_map.append(tb)
                page_text_parts.append(tb.full_text)
        pages_text.append("\n".join(page_text_parts))
    doc.close()
    structured_text = "\n\n---PAGE BREAK---\n\n".join(pages_text)
    total_chars = sum(len(p) for p in pages_text)
    if total_chars < 200 * len(pages_text):
        print(
            "[extractor] WARNING: muy poco texto encontrado. "
            "El PDF puede tener texto como imagen."
        )
    return structured_text, position_map


def pdf_page_to_image_bytes(pdf_path: str | Path, page_num: int = 0, dpi: int = 150) -> bytes:
    doc = fitz.open(str(pdf_path))
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = doc[page_num].get_pixmap(matrix=mat)
    doc.close()
    return pix.tobytes("png")


def pdf_to_images_base64(pdf_path: str | Path, dpi: int = 150) -> list[str]:
    doc = fitz.open(str(pdf_path))
    images = []
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        images.append(base64.b64encode(pix.tobytes("png")).decode())
    doc.close()
    return images
