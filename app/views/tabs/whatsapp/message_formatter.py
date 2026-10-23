"""Presentation helpers for WhatsApp chat messages (chat tab and template preview)."""
import html
import json
import re
from datetime import date, datetime, time
from typing import Any, Callable, Iterable, List, Optional, Union

from ....models.chat import ChatMessage
from . import theme


_BLANK_LINES_RE = re.compile(r"\n{3,}")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_WHITESPACE_RE = re.compile(r"\s+")
# A link ends before trailing punctuation and formatting markers (``*https://…*``).
_URL_RE = re.compile(r"https?://[^\s<]*[^\s<.,;:!?)*_~]")
_MARKUP_CHARS_RE = re.compile(r"[*_~`]")
_STASHED_RE = re.compile("\x00(\\d+)\x00")

_WEEKDAYS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
_QUOTE_PREFIXES = {"image": "📷", "video": "🎥", "document": "📄", "audio": "🎤", "sticker": "🟢"}


# ----------------------------------------------------------------------------
# WhatsApp formatting
# ----------------------------------------------------------------------------
def _render_markup(text: str, link_html: Callable[[str], str]) -> str:
    """Escape ``text`` and apply the safe subset of WhatsApp formatting. Code spans and
    links are set aside first so ``_`` or ``*`` inside them never turn into formatting."""
    stash: List[str] = []

    def keep(fragment: str) -> str:
        stash.append(fragment)
        return f"\x00{len(stash) - 1}\x00"

    rendered = re.sub(
        r"```(.+?)```",
        lambda m: keep(f'<code style="font-family: Consolas, monospace;">{m.group(1)}</code>'),
        html.escape(text or ""),
        flags=re.DOTALL,
    )
    rendered = _URL_RE.sub(lambda m: keep(link_html(m.group(0))), rendered)
    rendered = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"(?<!_)_([^_\n]+?)_(?!_)", r"<em>\1</em>", rendered)
    rendered = re.sub(r"~([^~\n]+?)~", r"<s>\1</s>", rendered)
    rendered = _STASHED_RE.sub(lambda m: stash[int(m.group(1))], rendered)
    return rendered.replace("\n", "<br>")


def whatsapp_markup_html(text: str) -> str:
    """WhatsApp formatting (*bold*, _italic_, ~strike~, ```mono```) as safe HTML."""
    return _render_markup(text, lambda url: url)


def message_html(
    text: str,
    pal: theme.WaPalette,
    *,
    clickable_links: bool = False,
    highlight_variables: bool = False,
) -> str:
    """A message body the way the phone shows it: WhatsApp formatting and tinted links
    (clickable in the chat). Template drafts can highlight variables still lacking a
    sample, so they read as "to be filled"."""

    def link(url: str) -> str:
        if clickable_links:
            return f'<a href="{url}" style="color:{pal.link}; text-decoration:none;">{url}</a>'
        return f'<span style="color:{pal.link};">{url}</span>'

    rendered = _render_markup(text, link)
    if highlight_variables:
        rendered = _PLACEHOLDER_RE.sub(
            lambda m: (
                f'<span style="background-color:{pal.var_bg}; color:{pal.var_text};">'
                f"&nbsp;{m.group(0)}&nbsp;</span>"
            ),
            rendered,
        )
    return rendered


def quote_snippet(text: str, prefix: str = "", empty: str = "Archivo") -> str:
    """One-line excerpt of a quoted message: its first line without WhatsApp markers,
    after the media emoji when the quoted message carries one."""
    first_line = next((line.strip() for line in (text or "").splitlines() if line.strip()), "")
    first_line = _MARKUP_CHARS_RE.sub("", first_line)
    if prefix:
        return f"{prefix} {first_line}" if first_line else f"{prefix} {empty}"
    return first_line


def quote_text_for_message(message: ChatMessage) -> str:
    """What a reply shows of the message it quotes (caption or media label for media)."""
    media_type = message.media.media_type if message.media else message.message_type
    prefix = _QUOTE_PREFIXES.get(media_type, "") if (message.is_media or message.media) else ""
    if not prefix:
        return quote_snippet(display_text_for_message(message))
    label = theme.MEDIA_LABELS.get(media_type, "Archivo").split(" ", 1)[-1]
    return quote_snippet(extract_useful_text(message.text_content, message.message_type), prefix, label)


# ----------------------------------------------------------------------------
# Times and days (es-MX, as WhatsApp prints them)
# ----------------------------------------------------------------------------
def clock_text(moment: Optional[Union[datetime, time]] = None) -> str:
    """Time of day, e.g. «6:42 p. m.»; the current time when omitted."""
    moment = moment or datetime.now()
    suffix = "a. m." if moment.hour < 12 else "p. m."
    return f"{moment.hour % 12 or 12}:{moment.minute:02d} {suffix}"


def day_label(day: date, today: date) -> str:
    """Day separator of the chat: «Hoy», «Ayer», the weekday within the last week, else
    the date."""
    days_ago = (today - day).days
    if days_ago == 0:
        return "Hoy"
    if days_ago == 1:
        return "Ayer"
    if 1 < days_ago < 7:
        return _WEEKDAYS[day.weekday()]
    return day.strftime("%d/%m/%Y")


def list_time_text(moment: Optional[datetime], now: Optional[datetime] = None) -> str:
    """Stamp of a conversation row: the time today, otherwise the day as the chat names it."""
    if moment is None:
        return ""
    now = now or datetime.now(moment.tzinfo)
    if moment.date() == now.date():
        return clock_text(moment)
    return day_label(moment.date(), now.date())


# ----------------------------------------------------------------------------
# Message text
# ----------------------------------------------------------------------------
def display_text_for_message(message: ChatMessage) -> str:
    """Return user-facing text for a message without storage/API artifacts."""
    # Reactions render as a badge on their target bubble, never as text.
    if message.message_type == "reaction":
        return ""

    useful = extract_useful_text(message.text_content, message.message_type)
    if useful:
        # A tap on a template quick-reply button: mark it so staff can tell it apart from
        # text the customer actually typed (mirrors the "reaction" special-case above). The
        # business's own interactive messages (the «Pagar ahora» link) read as plain text,
        # with their button drawn under the bubble.
        if message.message_type in ("button", "interactive") and message.is_inbound:
            return f"🔘 {useful}"
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
