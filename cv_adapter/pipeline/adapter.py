"""
Handles all Claude API calls.
"""
from __future__ import annotations
import json
from pathlib import Path
import anthropic
import config

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _load_prompt(name: str) -> str:
    return (config.PROMPTS_DIR / name).read_text(encoding="utf-8")


def _call(prompt: str, max_tokens: int = 4096) -> str:
    client = _get_client()
    message = client.messages.create(
        model=config.MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def structure_cv(raw_text: str) -> dict:
    prompt = _load_prompt("extraction_prompt.txt").replace("{raw_text}", raw_text)
    response = _call(prompt, max_tokens=4096)
    return _parse_json(response)


def extract_keywords(job_description: str) -> list[str]:
    prompt = _load_prompt("keywords_prompt.txt").replace("{job_description}", job_description)
    response = _call(prompt, max_tokens=512)
    result = _parse_json(response)
    if isinstance(result, list):
        return result
    return []


def adapt_cv(cv_json: dict, job_description: str, keywords: list[str]) -> dict:
    prompt = (
        _load_prompt("adaptation_prompt.txt")
        .replace("{cv_json}", json.dumps(cv_json, ensure_ascii=False, indent=2))
        .replace("{job_description}", job_description)
        .replace("{keywords}", ", ".join(keywords))
    )
    response = _call(prompt, max_tokens=4096)
    return _parse_json(response)


def _parse_json(text: str) -> dict | list:
    if "```" in text:
        lines = text.split("\n")
        inside = False
        json_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                inside = not inside
                continue
            if inside:
                json_lines.append(line)
        text = "\n".join(json_lines)
    return json.loads(text)
