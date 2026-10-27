import httpx
import pytest
import respx

from app.ingest.jd_fetch import (
    JdFetchError,
    extract_from_html,
    extract_jsonld,
    fetch_job_posting,
    from_pasted,
    strip_boilerplate,
)
from app.ingest.pdf import PdfError, extract_pdf_text

URL = "https://mbition.io/career/working-student-intern-driving-functions-software-development-all-genders/"


def test_mbition_fixture_main_content(mbition_html):
    jd = extract_from_html(mbition_html, URL)
    assert jd.source == "main-content"
    assert "Working Student / Intern" in jd.title
    assert "Design, implement, and maintain software components in C++ and Java" in jd.text
    assert "C++ and Python are essential" in jd.text
    assert "Experience with Android application or system-level development" in jd.text
    # Page chrome must not leak into the JD.
    lowered = jd.text.lower()
    for chrome in ("cookie", "skip to content", "accessibility menu", "privacy policy"):
        assert chrome not in lowered
    assert jd.text.count("Your Profile\nYour Profile") == 0


def test_jsonld_job_posting_is_preferred():
    description = "<p>Build things.</p><ul>" + "".join(f"<li>Requirement number {i} in detail</li>" for i in range(40)) + "</ul>"
    page = f"""<html><head><script type="application/ld+json">
    {{"@context": "https://schema.org", "@graph": [{{"@type": "Organization", "name": "X"}},
      {{"@type": "JobPosting", "title": "C++ Engineer", "description": {description!r},
        "hiringOrganization": {{"@type": "Organization", "name": "Acme"}}}}]}}
    </script></head><body><nav>Menu</nav><p>short</p></body></html>""".replace("'", '"')
    jd = extract_jsonld(page)
    assert jd is not None and jd.source == "json-ld"
    assert jd.company == "Acme"
    assert "- Requirement number 3 in detail" in jd.text
    assert extract_from_html(page).source == "json-ld"


def test_js_rendered_page_is_too_short():
    page = "<html><body><div id='root'></div><script>render()</script><p>Loading job…</p></body></html>"
    with pytest.raises(JdFetchError) as e:
        extract_from_html(page)
    assert e.value.reason == "too_short"


def test_strip_boilerplate():
    text = "Skip to content\nAccessibility menu\nYour Profile\nYour Profile\n- C++\nAccept all cookies"
    assert strip_boilerplate(text) == "Your Profile\n- C++"


@respx.mock
async def test_fetch_uses_browser_user_agent(mbition_html):
    route = respx.get(URL).mock(return_value=httpx.Response(200, text=mbition_html,
                                                            headers={"content-type": "text/html"}))
    jd = await fetch_job_posting(URL)
    assert "Mozilla/5.0" in route.calls[0].request.headers["user-agent"]
    assert "Concurrency awareness" in jd.text


@respx.mock
async def test_fetch_http_error():
    respx.get(URL).mock(return_value=httpx.Response(403))
    with pytest.raises(JdFetchError) as e:
        await fetch_job_posting(URL)
    assert e.value.reason == "fetch_failed" and "403" in e.value.message


@respx.mock
async def test_fetch_network_error():
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("timeout"))
    with pytest.raises(JdFetchError) as e:
        await fetch_job_posting(URL)
    assert e.value.reason == "fetch_failed"


async def test_invalid_url():
    with pytest.raises(JdFetchError) as e:
        await fetch_job_posting("mbition.io/career")
    assert e.value.reason == "invalid_url"


def test_pasted_text():
    assert from_pasted("We need C++ engineers. " * 20).source == "pasted"
    with pytest.raises(JdFetchError):
        from_pasted("too short")


def test_pdf_pdfplumber(resume_pdf):
    pdf = extract_pdf_text(resume_pdf)
    assert pdf.extractor == "pdfplumber" and pdf.page_count == 1
    assert "Implemented a thread-safe message queue in C++17" in pdf.text


def test_pdf_falls_back_to_pypdf(resume_pdf, monkeypatch):
    from app.ingest import pdf as pdf_module

    def broken(_):
        raise RuntimeError("pdfplumber exploded")

    monkeypatch.setattr(pdf_module, "_pdfplumber", broken)
    out = extract_pdf_text(resume_pdf)
    assert out.extractor == "pypdf"
    assert "Languages: C++, Python, Java, TypeScript" in out.text


def test_not_a_pdf():
    with pytest.raises(PdfError):
        extract_pdf_text(b"hello")
