"""Thunderbird-compatible RFC 5322 email extraction using the standard library."""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar


class _HTMLTextParser(HTMLParser):
    """Make a conservative, dependency-free text representation of HTML mail."""

    _BLOCK_TAGS: ClassVar[set[str]] = {
        "address",
        "article",
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "table",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return "\n".join(
            line.strip() for line in "".join(self.parts).splitlines() if line.strip()
        )


def _html_to_text(value: str) -> str:
    parser = _HTMLTextParser()
    parser.feed(value)
    parser.close()
    return parser.text()


def _body(message) -> tuple[str, str]:
    """Return preferred plain text, falling back to non-attachment HTML."""
    plain: list[str] = []
    html: list[str] = []
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode(part.get_content_charset() or "utf-8", "replace")
        if not isinstance(content, str):
            continue
        if content_type == "text/plain":
            plain.append(content.strip())
        else:
            html.append(_html_to_text(content))
    if any(plain):
        return "\n\n".join(part for part in plain if part), "plain"
    return "\n\n".join(part for part in html if part), "html" if html else "none"


def extract_eml(path: Path) -> tuple[str, dict[str, str | int | None]]:
    """Extract searchable headers and body from a saved email without attachments."""
    with path.open("rb") as source:
        message = BytesParser(policy=policy.default).parse(source)
    body, body_format = _body(message)
    headers = {
        "subject": str(message.get("Subject", "")).strip(),
        "from": str(message.get("From", "")).strip(),
        "to": str(message.get("To", "")).strip(),
        "date": str(message.get("Date", "")).strip(),
        "message_id": str(message.get("Message-ID", "")).strip(),
    }
    searchable_headers = [
        f"Subject: {headers['subject']}",
        f"From: {headers['from']}",
        f"To: {headers['to']}",
        f"Date: {headers['date']}",
    ]
    text = "\n".join(line for line in searchable_headers if line.split(": ", 1)[1])
    if body:
        text = f"{text}\n\n{body}" if text else body
    return text, {
        "title": headers["subject"] or None,
        "author": headers["from"] or None,
        "email_to": headers["to"] or None,
        "email_date": headers["date"] or None,
        "message_id": headers["message_id"] or None,
        "body_format": body_format,
    }
