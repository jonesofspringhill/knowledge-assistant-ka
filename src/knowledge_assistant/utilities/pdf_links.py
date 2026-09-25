"""Download allow-listed text and PDF links embedded in a PDF."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import unquote, urlparse, urlunparse
from urllib.request import Request, urlopen

from knowledge_assistant.config import PdfLinkDownloadSettings


@dataclass(frozen=True)
class DownloadResult:
    """Outcome for one link found in the input PDF."""

    url: str
    status: str
    detail: str


def extract_pdf_links(pdf_path: Path) -> list[str]:
    """Return unique HTTP(S) URI actions from PDF link annotations."""
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("PDF link support requires the 'pypdf' package") from error

    links: set[str] = set()
    for page in PdfReader(pdf_path).pages:
        for annotation_reference in page.get("/Annots", []):
            annotation = annotation_reference.get_object()
            action = annotation.get("/A")
            uri = action.get("/URI") if action else None
            if uri:
                url = _normalise_url(str(uri))
                if url:
                    links.add(url)
    return sorted(links)


def download_pdf_links(
    pdf_path: Path,
    destination: Path,
    settings: PdfLinkDownloadSettings,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> list[DownloadResult]:
    """Download configured document links from ``pdf_path`` to ``destination``."""
    results: list[DownloadResult] = []
    for url in extract_pdf_links(pdf_path):
        if not _is_allowed_host(url, settings.allowed_hosts):
            results.append(DownloadResult(url, "skipped", "host is not allow-listed"))
        elif dry_run:
            results.append(DownloadResult(url, "would-download", "allow-listed host"))
        else:
            try:
                results.append(_download(url, destination, settings, overwrite))
            except (OSError, URLError, ValueError) as error:
                results.append(DownloadResult(url, "failed", str(error)))
    return results


def _download(
    url: str, destination: Path, settings: PdfLinkDownloadSettings, overwrite: bool
) -> DownloadResult:
    request = Request(url, headers={"User-Agent": "knowledge-assistant/0.1"})
    with urlopen(request, timeout=settings.timeout_seconds) as response:
        final_url = _normalise_url(response.geturl())
        if not final_url or not _is_allowed_host(final_url, settings.allowed_hosts):
            return DownloadResult(
                url, "skipped", "redirected to a non-allow-listed host"
            )
        content_type = response.headers.get_content_type().lower()
        extension = Path(unquote(urlparse(final_url).path)).suffix.lower()
        if (
            extension not in settings.allowed_extensions
            and content_type not in settings.allowed_content_types
        ):
            return DownloadResult(
                url, "skipped", "target is not an allowed text or PDF type"
            )
        content = _read_limited(response, settings.maximum_bytes)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / _filename(final_url, extension, content_type)
    if target.exists() and not overwrite:
        return DownloadResult(url, "skipped", f"already exists: {target.name}")
    target.write_bytes(content)
    return DownloadResult(url, "downloaded", str(target))


def _read_limited(response, maximum_bytes: int) -> bytes:
    content = response.read(maximum_bytes + 1)
    if len(content) > maximum_bytes:
        raise ValueError(f"response exceeds maximum_bytes ({maximum_bytes})")
    return content


def _normalise_url(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    return urlunparse(parsed._replace(fragment=""))


def _is_allowed_host(url: str, allowed_hosts: list[str]) -> bool:
    host = urlparse(url).hostname
    return bool(host) and any(
        host.lower() == allowed or host.lower().endswith(f".{allowed}")
        for allowed in allowed_hosts
    )


def _filename(url: str, extension: str, content_type: str) -> str:
    stem = Path(unquote(urlparse(url).path)).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-") or "download"
    extension = extension or (".pdf" if content_type == "application/pdf" else ".txt")
    return f"{safe_stem}-{hashlib.sha256(url.encode()).hexdigest()[:10]}{extension}"
