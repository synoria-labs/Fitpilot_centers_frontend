"""Presentation helpers for WhatsApp chat messages."""
import json
import re
from typing import Any, Iterable, List, Optional

from ....models.chat import ChatMessage
from . import theme


_BLANK_LINES_RE = re.compile(r"\n{3,}")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_WHITESPACE_RE = re.compile(r"\s+")


def display_text_for_message(message: ChatMessage) -> str:
    """Return user-facing text for a message without storage/API artifacts."""
    useful = extract_useful_text(message.text_content, message.message_type)
    if useful:
        return useful

    if message.message_type == "template":
        return "Plantilla enviada"

    if message.message_type and message.message_type != "text":
        return theme.MEDIA_LABELS.get(message.message_type, f"[{message.message_type}]")

    return ""


def snippet_for_message(message: ChatMessage, max_length: int = 48) -> str:
    text = _WHITESPACE_RE.sub(" ", display_text_for_message(message)).strip()
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def extract_useful_text(text_content: Optional[str], message_type: str = "") -> str:
    raw = text_content or ""
    if not raw.strip():
        return ""

    should_parse = _should_try_structured_parse(raw, message_type)
    if should_parse:
        for value in _iter_json_values(raw):
            extracted = _extract_from_json_value(value)
            if extracted:
                return extracted

    if message_type == "template" and _looks_structured(raw):
        return ""

    return _normalize_text(raw)


def _should_try_structured_parse(raw: str, message_type: str) -> bool:
    return message_type == "template" or _looks_structured(raw)


def _looks_structured(raw: str) -> bool:
    stripped = raw.lstrip()
    return (
        stripped.startswith("{")
        or stripped.startswith("[")
        or '\\"' in raw
    )


def _iter_json_values(raw: str) -> Iterable[Any]:
    seen = set()
    for candidate in _candidate_json_strings(raw):
        if not candidate:
            continue
        for value in _decode_json_stream(candidate):
            marker = repr(value)
            if marker in seen:
                continue
            seen.add(marker)
            yield value


def _candidate_json_strings(raw: str) -> List[str]:
    stripped = raw.strip()
    candidates = [stripped]

    quote_relaxed = stripped.replace('\\"', '"').replace("\\/", "/")
    if quote_relaxed != stripped:
        candidates.append(quote_relaxed.strip())

    relaxed = (
        quote_relaxed
        .replace("\\r", "\r")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
    )
    if relaxed != stripped and relaxed != quote_relaxed:
        candidates.append(relaxed.strip())

    return candidates


def _decode_json_stream(candidate: str) -> Iterable[Any]:
    decoder = json.JSONDecoder()
    index = 0
    length = len(candidate)

    while index < length:
        while index < length and candidate[index].isspace():
            index += 1
        if index >= length:
            break

        try:
            value, next_index = decoder.raw_decode(candidate, index)
        except json.JSONDecodeError:
            next_positions = [
                pos for pos in (
                    candidate.find("{", index + 1),
                    candidate.find("[", index + 1),
                )
                if pos != -1
            ]
            if not next_positions:
                break
            index = min(next_positions)
            continue

        yield value
        index = next_index


def _extract_from_json_value(value: Any) -> str:
    if isinstance(value, list):
        template_text = _extract_template_components(value)
        if template_text:
            return template_text

        parts = [_extract_from_json_value(item) for item in value]
        return _normalize_text("\n\n".join(part for part in parts if part))

    if isinstance(value, dict):
        components = value.get("components")
        if isinstance(components, list):
            template_text = _extract_template_components(components)
            if template_text:
                return template_text

        text = value.get("text")
        if isinstance(text, str):
            return _normalize_text(text)

        for key in ("body", "message", "caption"):
            nested = value.get(key)
            if isinstance(nested, str):
                return _normalize_text(nested)
            if isinstance(nested, (dict, list)):
                extracted = _extract_from_json_value(nested)
                if extracted:
                    return extracted

    if isinstance(value, str):
        return _normalize_text(value)

    return ""


def _extract_template_components(components: List[Any]) -> str:
    body_text = ""
    footer_text = ""

    for component in components:
        if not isinstance(component, dict):
            continue

        component_type = str(component.get("type") or "").upper()
        text = component.get("text")
        if not isinstance(text, str):
            continue

        if component_type == "BODY":
            body_text = _replace_template_placeholders(text, component)
        elif component_type == "FOOTER":
            footer_text = text

    return _normalize_text("\n\n".join(part for part in (body_text, footer_text) if part))


def _replace_template_placeholders(text: str, component: dict) -> str:
    values = _template_example_values(component)
    if not values:
        return text

    def replace(match: re.Match) -> str:
        index = int(match.group(1)) - 1
        if 0 <= index < len(values):
            return values[index]
        return match.group(0)

    return _PLACEHOLDER_RE.sub(replace, text)


def _template_example_values(component: dict) -> List[str]:
    example = component.get("example")
    if not isinstance(example, dict):
        return []

    body_text = example.get("body_text")
    if not isinstance(body_text, list) or not body_text:
        return []

    first_row = body_text[0]
    if not isinstance(first_row, list):
        return []

    return [str(value) for value in first_row]


def _normalize_text(text: str) -> str:
    normalized = (
        str(text)
        .replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace("\\t", "\t")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\\\n", "\n")
    )
    lines = [line.rstrip() for line in normalized.split("\n")]
    normalized = "\n".join(lines).strip()
    return _BLANK_LINES_RE.sub("\n\n", normalized)
