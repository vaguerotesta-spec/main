"""
Regenerates the PDF by overlaying adapted text onto the original PDF.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF

import config
from pipeline.extractor import TextBlock


def regenerate(
    original_pdf_path: str | Path,
    original_map: list[TextBlock],
    adapted_cv_json: dict,
    original_cv_json: dict,
    output_path: str | Path | None = None,
) -> Path:
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = config.OUTPUTS_DIR / f"cv_adapted_{ts}.pdf"

    output_path = Path(output_path)
    changes = _diff_cv_jsons(original_cv_json, adapted_cv_json)

    doc = fitz.open(str(original_pdf_path))
    for page in doc:
        _apply_changes_to_page(page, original_map, changes)
    doc.save(str(output_path))
    doc.close()
    return output_path


def _apply_changes_to_page(page, position_map, changes):
    page_blocks = [b for b in position_map if b.page == page.number]
    for original_text, new_text in changes:
        if original_text == new_text:
            continue
        block = _find_matching_block(page_blocks, original_text)
        if block is None:
            continue
        _replace_block_text(page, block, new_text)


def _replace_block_text(page, block, new_text):
    if not new_text or not new_text.strip():
        return

    x0, y0, x1, y1 = block.bbox
    bg_color = _sample_background(page, x0, y0, x1, y1)

    font_size = 11.0
    font_name = "helv"
    text_color = (0, 0, 0)

    if block.lines and block.lines[0]["spans"]:
        span = block.lines[0]["spans"][0]
        font_size = span.get("size", 11.0)
        raw_color = span.get("color", 0)
        text_color = _int_to_rgb(raw_color)

    rect = fitz.Rect(x0, y0, x1, y1)

    # Trim text to fit at original font size (no font shrinking)
    text_to_write = _trim_to_fit(rect, new_text, font_size, font_name)

    page.draw_rect(rect, color=bg_color, fill=bg_color)
    page.insert_textbox(rect, text_to_write, fontsize=font_size, fontname=font_name, color=text_color, align=0)


def _trim_to_fit(rect, text, font_size, font_name):
    """Check if text fits. If not and it's comma-separated, trim items from end."""
    tmp_doc = fitz.open()
    tmp_page = tmp_doc.new_page(width=rect.width * 10, height=rect.height * 10)
    tmp_rect = fitz.Rect(0, 0, rect.width, rect.height)
    result = tmp_page.insert_textbox(tmp_rect, text, fontsize=font_size, fontname=font_name)
    tmp_doc.close()

    if result >= 0:
        return text

    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        while len(parts) > 1:
            parts.pop()
            candidate = ", ".join(parts)
            tmp_doc = fitz.open()
            tmp_page = tmp_doc.new_page(width=rect.width * 10, height=rect.height * 10)
            result = tmp_page.insert_textbox(tmp_rect, candidate, fontsize=font_size, fontname=font_name)
            tmp_doc.close()
            if result >= 0:
                return candidate

    return text


def _sample_background(page, x0, y0, x1, y1, margin=3.0):
    sample_x = (x0 + x1) / 2
    sample_y = max(0, y0 - margin)
    pix = page.get_pixmap(
        matrix=fitz.Matrix(1, 1),
        clip=fitz.Rect(sample_x - 1, sample_y - 1, sample_x + 1, sample_y + 1),
    )
    if pix.n >= 3:
        r, g, b = pix.pixel(0, 0)[:3]
        return (r / 255, g / 255, b / 255)
    return (1.0, 1.0, 1.0)


def _int_to_rgb(color_int):
    r = ((color_int >> 16) & 0xFF) / 255
    g = ((color_int >> 8) & 0xFF) / 255
    b = (color_int & 0xFF) / 255
    return (r, g, b)


def _find_matching_block(blocks, target_text):
    target_lower = target_text.lower().strip()
    best_block = None
    best_score = 0.0
    for block in blocks:
        score = _similarity(block.full_text.lower().strip(), target_lower)
        if score > best_score and score > 0.5:
            best_score = score
            best_block = block
    return best_block


def _similarity(a, b):
    if not a or not b:
        return 0.0
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a), len(words_b))


def _diff_cv_jsons(original, adapted):
    original_flat = _flatten_cv(original)
    adapted_flat = _flatten_cv(adapted)
    return [(o, a) for o, a in zip(original_flat, adapted_flat) if o != a]


def _flatten_cv(cv):
    result = []
    contact = cv.get("contact", {})
    for f in ("name", "email", "phone", "location", "linkedin", "website", "other"):
        val = contact.get(f, "")
        if val:
            result.append(str(val))
    summary = cv.get("summary", "")
    if summary:
        result.append(summary)
    for exp in cv.get("experience", []):
        for k in ("title", "company", "dates"):
            if exp.get(k):
                result.append(exp[k])
        for bullet in exp.get("bullets", []):
            if bullet:
                result.append(bullet)
    for edu in cv.get("education", []):
        for k in ("degree", "institution"):
            if edu.get(k):
                result.append(edu[k])
    # Skills as individual items (not joined) so each matches its own PDF block
    for skill in cv.get("skills", []):
        if skill:
            result.append(skill)
    for cert in cv.get("certifications", []):
        if cert:
            result.append(cert)
    for section in cv.get("other_sections", []):
        if section.get("content"):
            result.append(section["content"])
    return result
