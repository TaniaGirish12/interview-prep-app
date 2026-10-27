"""Job posting URL → text.

Order: JSON-LD JobPosting if present, then main-content extraction with trafilatura.
Navigation, footers and accessibility menus are stripped. If the result is too short
to be a job description (typically a JavaScript-rendered page) a JdFetchError is raised
and the UI offers a paste box. The JD is never reconstructed from model memory.
"""

import html as html_lib
import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
import trafilatura
from lxml import html as lxml_html

from ..config import get_settings

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}

# Lines that are page chrome rather than posting content.
_BOILERPLATE = re.compile(
    r"^(skip to (main )?content|accessibility( menu| settings)?|cookie(s| settings| policy)?|"
    r"accept( all)?( cookies)?|reject all|menu|close|share( this job)?|back to (jobs|careers)|"
    r"imprint|privacy policy|legal notice|font size|high contrast|increase text|decrease text)\.?$",
    re.I,
)


class JdFetchError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason  # "fetch_failed" | "too_short" | "invalid_url"
        self.message = message


@dataclass
class JdText:
    text: str
    source: str  # "json-ld" | "main-content" | "pasted"
    title: str | None = None
    company: str | None = None
    meta: dict = field(default_factory=dict)


def _html_to_text(fragment: str) -> str:
    """JSON-LD descriptions are often HTML. Keep list items and paragraphs on separate lines."""
    if "<" not in fragment:
        return html_lib.unescape(fragment).strip()
    doc = lxml_html.fromstring(f"<div>{fragment}</div>")
    for br in doc.iter("br"):
        br.tail = "\n" + (br.tail or "")
    lines: list[str] = []
    for el in doc.iter():
        if el.tag in ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            t = " ".join(el.text_content().split())
            if t:
                lines.append(("- " if el.tag == "li" else "") + t)
    if not lines:
        lines = [doc.text_content()]
    return "\n".join(lines).strip()


def _iter_jsonld(node):
    if isinstance(node, list):
        for n in node:
            yield from _iter_jsonld(n)
    elif isinstance(node, dict):
        yield node
        if "@graph" in node:
            yield from _iter_jsonld(node["@graph"])


def extract_jsonld(page_html: str) -> JdText | None:
    doc = lxml_html.fromstring(page_html)
    for script in doc.xpath('//script[@type="application/ld+json"]'):
        try:
            data = json.loads(script.text_content())
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _iter_jsonld(data):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if "JobPosting" not in types:
                continue
            parts = []
            title = node.get("title")
            if title:
                parts.append(title)
            for key in ("description", "responsibilities", "qualifications", "skills",
                        "experienceRequirements", "educationRequirements"):
                val = node.get(key)
                if isinstance(val, str) and val.strip():
                    parts.append(_html_to_text(val))
            org = node.get("hiringOrganization")
            company = org.get("name") if isinstance(org, dict) else None
            return JdText(text="\n\n".join(parts), source="json-ld", title=title, company=company,
                          meta={"employmentType": node.get("employmentType"),
                                "datePosted": node.get("datePosted")})
    return None


def strip_boilerplate(text: str) -> str:
    out: list[str] = []
    prev = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        if _BOILERPLATE.match(line) or line == prev:  # drop chrome and repeated headings
            continue
        out.append(line)
        prev = line
    return "\n".join(out).strip()


def extract_main_content(page_html: str, url: str | None = None) -> JdText | None:
    text = trafilatura.extract(
        page_html, url=url, include_comments=False, include_tables=True,
        include_links=False, favor_recall=True,
    )
    if not text:
        return None
    meta = trafilatura.extract_metadata(page_html, default_url=url)
    title = meta.title if meta else None
    company = meta.sitename if meta else None
    body = strip_boilerplate(text)
    if title and title not in body[:300]:
        body = f"{title}\n\n{body}"
    return JdText(text=body, source="main-content", title=title, company=company)


def extract_from_html(page_html: str, url: str | None = None) -> JdText:
    min_chars = get_settings().jd_min_chars
    candidates = [c for c in (extract_jsonld(page_html), extract_main_content(page_html, url)) if c]
    for c in candidates:
        if len(c.text) >= min_chars:
            return c
    longest = max((len(c.text) for c in candidates), default=0)
    raise JdFetchError(
        "too_short",
        f"Only {longest} characters of job description text were found on this page. "
        "It is probably rendered with JavaScript. Paste the job description text instead.",
    )


async def fetch_job_posting(url: str) -> JdText:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise JdFetchError("invalid_url", "Enter a full http(s) URL.")
    settings = get_settings()
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=settings.fetch_timeout_s,
                                     follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise JdFetchError("fetch_failed", f"The page returned HTTP {e.response.status_code}.") from e
    except httpx.HTTPError as e:
        raise JdFetchError("fetch_failed", f"Could not fetch the page: {type(e).__name__}.") from e
    if "html" not in resp.headers.get("content-type", "html"):
        raise JdFetchError("fetch_failed", "The URL does not point to an HTML page.")
    return extract_from_html(resp.text, str(resp.url))


def from_pasted(text: str) -> JdText:
    text = strip_boilerplate(text)
    if len(text) < 200:
        raise JdFetchError("too_short", "The pasted text is too short to be a job description.")
    return JdText(text=text, source="pasted")
