import json

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import db
from ..ingest.jd_fetch import JdFetchError, fetch_job_posting, from_pasted
from ..ingest.pdf import PdfError, extract_pdf_text

router = APIRouter(prefix="/api")
MAX_PDF_BYTES = 15 * 1024 * 1024


@router.post("/resume")
async def upload_resume(file: UploadFile) -> dict:
    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, "The PDF is larger than 15 MB.")
    try:
        pdf = extract_pdf_text(data)
    except PdfError as e:
        raise HTTPException(422, str(e)) from e
    cur = db.execute(
        "INSERT INTO resumes (filename, extractor, page_count, text, text_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (file.filename, pdf.extractor, pdf.page_count, pdf.text, db.sha256(pdf.text), db.now()),
    )
    return {"resume_id": cur.lastrowid, "text": pdf.text, "extractor": pdf.extractor,
            "page_count": pdf.page_count, "filename": file.filename}


class ResumeText(BaseModel):
    text: str = Field(min_length=50, max_length=100_000)


@router.put("/resume/{resume_id}")
def update_resume(resume_id: int, body: ResumeText) -> dict:
    cur = db.execute("UPDATE resumes SET text = ?, text_hash = ?, edited = 1 WHERE id = ?",
                     (body.text, db.sha256(body.text), resume_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "Resume not found.")
    return {"resume_id": resume_id, "text": body.text}


class JdInput(BaseModel):
    url: str | None = None
    text: str | None = Field(default=None, max_length=100_000)


@router.post("/jd")
async def add_job_posting(body: JdInput):
    try:
        if body.text and body.text.strip():
            jd = from_pasted(body.text)
        elif body.url:
            jd = await fetch_job_posting(body.url.strip())
        else:
            raise JdFetchError("invalid_url", "Enter a job posting URL or paste the text.")
    except JdFetchError as e:
        return JSONResponse(status_code=422, content={"detail": e.message, "reason": e.reason})
    cur = db.execute(
        "INSERT INTO job_postings (url, source, title, company, meta_json, text, text_hash, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (body.url, jd.source, jd.title, jd.company, json.dumps(jd.meta), jd.text, db.sha256(jd.text), db.now()),
    )
    return {"jd_id": cur.lastrowid, "text": jd.text, "source": jd.source, "title": jd.title,
            "company": jd.company, "url": body.url}
