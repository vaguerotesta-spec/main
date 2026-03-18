"""
ATS validation and diff display.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
import fitz


@dataclass
class ATSResult:
    score: int
    keywords_found: list[str] = field(default_factory=list)
    keywords_missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        total = len(self.keywords_found) + len(self.keywords_missing)
        if total == 0:
            return 1.0
        return len(self.keywords_found) / total


def validate(pdf_path: str | Path, keywords: list[str]) -> ATSResult:
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    cv_text = "\n".join(page.get_text() for page in doc)
    doc.close()
    cv_text_lower = cv_text.lower()
    found, missing = [], []
    for kw in keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, cv_text_lower):
            found.append(kw)
        else:
            missing.append(kw)
    warnings = []
    if len(cv_text.strip()) < 100:
        warnings.append("Muy poco texto extraido del PDF — puede haber problemas de legibilidad ATS.")
    base = 40 if not warnings else 20
    keyword_score = int(60 * (len(found) / max(len(keywords), 1)))
    score = min(100, base + keyword_score)
    return ATSResult(score=score, keywords_found=found, keywords_missing=missing, warnings=warnings)


def diff_cv_texts(original_json: dict, adapted_json: dict) -> list[dict]:
    changes = []
    orig_summary = original_json.get("summary", "")
    adap_summary = adapted_json.get("summary", "")
    if orig_summary != adap_summary:
        changes.append({"section": "Summary", "original": orig_summary, "adapted": adap_summary})
    for orig, adap in zip(original_json.get("experience", []), adapted_json.get("experience", [])):
        for j, (ob, ab) in enumerate(zip(orig.get("bullets", []), adap.get("bullets", []))):
            if ob != ab:
                changes.append({
                    "section": f"Experiencia: {orig.get('company', '')} — punto {j + 1}",
                    "original": ob,
                    "adapted": ab,
                })
    orig_skills = original_json.get("skills", [])
    adap_skills = adapted_json.get("skills", [])
    if orig_skills != adap_skills:
        changes.append({
            "section": "Skills",
            "original": ", ".join(orig_skills),
            "adapted": ", ".join(adap_skills),
        })
    return changes
