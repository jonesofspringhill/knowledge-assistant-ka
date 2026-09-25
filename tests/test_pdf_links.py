"""Tests for the allow-listed PDF link downloader."""

from email.message import Message
from pathlib import Path

from knowledge_assistant.config import PdfLinkDownloadSettings
from knowledge_assistant.utilities import pdf_links


class _Response:
    def __init__(self, url: str, content: bytes, content_type: str) -> None:
        self._url = url
        self._content = content
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self) -> str:
        return self._url

    def read(self, _size: int) -> bytes:
        return self._content


def test_downloads_allowed_pdf_link(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        pdf_links, "extract_pdf_links", lambda _path: ["https://docs.example/report"]
    )
    monkeypatch.setattr(
        pdf_links,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            "https://docs.example/report", b"%PDF-content", "application/pdf"
        ),
    )
    settings = PdfLinkDownloadSettings(allowed_hosts=["docs.example"])

    results = pdf_links.download_pdf_links(tmp_path / "source.pdf", tmp_path, settings)

    assert results[0].status == "downloaded"
    assert next(iter(tmp_path.glob("report-*.pdf"))).read_bytes() == b"%PDF-content"


def test_skips_non_allowlisted_host(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        pdf_links,
        "extract_pdf_links",
        lambda _path: ["https://untrusted.example/a.pdf"],
    )
    settings = PdfLinkDownloadSettings(allowed_hosts=["docs.example"])

    results = pdf_links.download_pdf_links(tmp_path / "source.pdf", tmp_path, settings)

    assert results == [
        pdf_links.DownloadResult(
            "https://untrusted.example/a.pdf", "skipped", "host is not allow-listed"
        )
    ]


def test_rejects_unrecognised_content(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        pdf_links, "extract_pdf_links", lambda _path: ["https://docs.example/page"]
    )
    monkeypatch.setattr(
        pdf_links,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            "https://docs.example/page", b"<html>", "text/html"
        ),
    )
    settings = PdfLinkDownloadSettings(allowed_hosts=["docs.example"])

    results = pdf_links.download_pdf_links(tmp_path / "source.pdf", tmp_path, settings)

    assert results[0].status == "skipped"
    assert not list(tmp_path.iterdir())
