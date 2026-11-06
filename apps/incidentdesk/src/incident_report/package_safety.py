"""Contain exported text/resources without rewriting approved text or imported bytes."""

import base64
import ipaddress
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from incident_report.evidence_import.reader import safe_path


class UnsafePayload(ValueError):
    pass


def _text(text: str) -> None:
    text = unquote(unescape(text))
    for url in re.findall(r'https?://[^\s"<>]+', text):
        try:
            parts = urlsplit(url)
            host = (parts.hostname or "").lower().rstrip(".")
            if not host or parts.username or parts.password or host == "localhost" or host.endswith(".localhost"):
                raise UnsafePayload("A payload contains a machine-local host or credential URL.")
            if (
                all(part.isdecimal() or part.lower().startswith("0x") for part in host.split("."))
                and len(host.split(".")) != 4
            ):
                raise UnsafePayload("A payload contains an ambiguous numeric machine-local host.")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is None and (
                "." not in host
                or host.endswith((".local", ".internal", ".lan", ".home"))
                or all(part.isdecimal() or part.lower().startswith("0x") for part in host.split("."))
            ):
                raise UnsafePayload("A payload contains an ambiguous numeric or machine-local host.")
            if address is not None and not address.is_global:
                raise UnsafePayload("A payload contains a machine-local host.")
        except ValueError:
            raise UnsafePayload("A payload contains an unsafe host URL.") from None
    without_urls = re.sub(r'https?://[^\s"<>]+', "", text)
    if re.search(
        r"[A-Za-z]:[\\/]|file://|\\\\|(?<![\w:/])//|(?<![\w/<])/(?!/)[\w.-]+(?:/[\w.-]+)*|\blocalhost\b|127\.0\.0\.1",
        without_urls,
    ):
        raise UnsafePayload("A payload contains a machine-local path or host.")


class _OfflineHTML(HTMLParser):
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {
            "script",
            "iframe",
            "object",
            "embed",
            "form",
            "video",
            "audio",
            "source",
            "img",
            "svg",
            "math",
            "base",
        }:
            raise UnsafePayload("An HTML payload contains an active resource.")
        for key, value in attrs:
            value = value or ""
            if key.startswith("on") or key in {"src", "srcset", "style", "action"}:
                raise UnsafePayload("An HTML payload contains an active resource attribute.")
            if key == "href" and tag == "link":
                if not value.startswith("data:text/css;base64,"):
                    raise UnsafePayload("A stylesheet is not embedded.")
                try:
                    css = base64.b64decode(value.split(",", 1)[1].split("#")[0], validate=True).decode()
                except (ValueError, UnicodeError):
                    raise UnsafePayload("An embedded stylesheet is invalid.") from None
                if "@import" in css.lower() or any(
                    not url.strip("\"' ").startswith("data:font/woff2;base64,")
                    for url in re.findall(r"url\((.*?)\)", css, re.S)
                ):
                    raise UnsafePayload("A stylesheet contains an active network resource.")
            elif key == "href":
                if not (value.startswith("#") or value.startswith(("https://", "http://"))):
                    raise UnsafePayload("An HTML link has an unsafe path or scheme.")
                _text(value)
            else:
                _text(value)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        _text(data)


def validate_payload(path: str, content: bytes) -> None:
    if path.startswith("views/"):
        return  # Original video bytes are hash checked before they reach this boundary.
    if path.startswith("reconstruction/") and path != "reconstruction/review_aid.html":
        if not path.endswith((".json", ".jsonl")):
            raise UnsafePayload("An imported artifact has an active or unsupported format.")
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        raise UnsafePayload("An artifact is not portable UTF-8 text.") from None
    if path in {"report.html", "reconstruction/review_aid.html"}:
        _OfflineHTML().feed(text)
    else:
        _text(text)


def member_path(name: str) -> None:
    safe_path(name)
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    for part in name.split("/"):
        if (
            part.endswith((" ", "."))
            or any(char in '<>"|?*' for char in part)
            or part.split(".")[0].lower() in reserved
            or any(ord(c) < 32 or ord(c) == 127 for c in part)
        ):
            raise UnsafePayload("Unsafe or non-portable member path.")
