import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { keys } from "../api/hooks";
import { ErrorState } from "../components/ui";

type Resume = { id: number; text: string; savedText: string; filename: string | null; extractor: string };
type Job = { id: number; text: string; source: string; title: string | null };

export function NewAnalysis() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [resume, setResume] = useState<Resume | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [url, setUrl] = useState("");
  const [pasteMode, setPasteMode] = useState(false);
  const [pasted, setPasted] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [hours, setHours] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const upload = useMutation({
    mutationFn: api.uploadResume,
    onSuccess: (r) => setResume({ id: r.resume_id, text: r.text, savedText: r.text, filename: r.filename, extractor: r.extractor }),
  });
  const saveResume = useMutation({
    mutationFn: () => api.saveResume(resume!.id, resume!.text),
    onSuccess: (r) => setResume((s) => (s ? { ...s, savedText: r.text } : s)),
  });
  const fetchJob = useMutation({
    mutationFn: (input: { url?: string; text?: string }) => api.addJob(input),
    onSuccess: (j) => setJob({ id: j.jd_id, text: j.text, source: j.source, title: j.title }),
    onError: (e) => {
      if (e instanceof ApiError && (e.reason === "too_short" || e.reason === "fetch_failed")) setPasteMode(true);
    },
  });
  const start = useMutation({
    mutationFn: async () => {
      if (resume && resume.text !== resume.savedText) await saveResume.mutateAsync();
      return api.createAnalysis({
        resume_id: resume!.id, jd_id: job!.id,
        interview_date: date || null, interview_time: date && time ? time : null,
        hours_per_day: hours ? Number(hours) : null,
      });
    },
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: keys.list });
      navigate(`/a/${a.analysis_id}`);
    },
  });

  const onFiles = (files: FileList | null) => {
    const f = files?.[0];
    if (f) upload.mutate(f);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    onFiles(e.dataTransfer.files);
  };

  const resumeDirty = resume && resume.text !== resume.savedText;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl sm:text-3xl font-bold">Prepare for an interview</h1>
        <p className="muted mt-1">Upload your resume and the job posting. Notes are built only from what the posting asks for.</p>
      </header>

      <section aria-labelledby="resume-h" className="card p-5 space-y-4">
        <h2 id="resume-h" className="text-lg font-semibold">1 · Resume (PDF)</h2>
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className="rounded-lg border-2 border-dashed p-6 text-center transition-colors"
          style={{ borderColor: dragging ? "var(--accent)" : "var(--border)", background: dragging ? "var(--surface-2)" : undefined }}
        >
          <p className="font-medium">Drag and drop your resume PDF here</p>
          <p className="muted text-sm my-2">or</p>
          <button className="btn" onClick={() => fileInput.current?.click()} disabled={upload.isPending}>
            {upload.isPending ? "Extracting text…" : "Choose PDF"}
          </button>
          <input ref={fileInput} type="file" accept="application/pdf,.pdf" className="sr-only"
            aria-label="Resume PDF file" onChange={(e) => onFiles(e.target.files)} />
        </div>
        {upload.isError && <ErrorState message={upload.error.message} />}
        {resume && (
          <div className="space-y-2">
            <label htmlFor="resume-text" className="text-sm font-medium flex flex-wrap gap-x-2">
              Extracted text from {resume.filename ?? "your PDF"}
              <span className="muted font-normal">({resume.extractor}). Check it and correct any errors before analysing.</span>
            </label>
            <textarea id="resume-text" className="field font-mono text-xs h-64"
              value={resume.text} onChange={(e) => setResume({ ...resume, text: e.target.value })} />
            <div className="flex items-center gap-3">
              <button className="btn-ghost" disabled={!resumeDirty || saveResume.isPending} onClick={() => saveResume.mutate()}>
                {saveResume.isPending ? "Saving…" : "Save corrections"}
              </button>
              {resumeDirty && <span className="text-xs muted">Unsaved changes are saved when you start the analysis.</span>}
              {saveResume.isError && <span className="text-xs" style={{ color: "var(--gap)" }}>{saveResume.error.message}</span>}
            </div>
          </div>
        )}
      </section>

      <section aria-labelledby="jd-h" className="card p-5 space-y-4">
        <h2 id="jd-h" className="text-lg font-semibold">2 · Job posting</h2>
        {!pasteMode ? (
          <form className="flex flex-col sm:flex-row gap-2"
            onSubmit={(e) => { e.preventDefault(); if (url.trim()) fetchJob.mutate({ url: url.trim() }); }}>
            <label htmlFor="jd-url" className="sr-only">Job posting URL</label>
            <input id="jd-url" className="field" type="url" placeholder="https://company.com/careers/job"
              value={url} onChange={(e) => setUrl(e.target.value)} required />
            <button className="btn shrink-0" disabled={fetchJob.isPending || !url.trim()}>
              {fetchJob.isPending ? "Fetching…" : "Fetch posting"}
            </button>
          </form>
        ) : (
          <div className="space-y-2">
            <label htmlFor="jd-paste" className="text-sm font-medium">Paste the full job description text</label>
            <textarea id="jd-paste" className="field h-56 text-sm" value={pasted} onChange={(e) => setPasted(e.target.value)} />
            <div className="flex gap-2">
              <button className="btn" disabled={fetchJob.isPending || pasted.trim().length < 200}
                onClick={() => fetchJob.mutate({ text: pasted })}>
                {fetchJob.isPending ? "Saving…" : "Use this text"}
              </button>
              <button className="btn-ghost" onClick={() => { setPasteMode(false); fetchJob.reset(); }}>Back to URL</button>
            </div>
          </div>
        )}
        {fetchJob.isError && (
          <ErrorState message={fetchJob.error.message} />
        )}
        {!pasteMode && !job && (
          <button className="text-sm underline muted" onClick={() => setPasteMode(true)}>Paste the text instead</button>
        )}
        {job && (
          <details className="text-sm" open>
            <summary className="cursor-pointer font-medium">
              {job.title ?? "Job description"} · {job.text.length.toLocaleString()} characters ({job.source})
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded p-3 text-xs" style={{ background: "var(--surface-2)" }}>
              {job.text}
            </pre>
          </details>
        )}
      </section>

      <section aria-labelledby="plan-h" className="card p-5 space-y-4">
        <h2 id="plan-h" className="text-lg font-semibold">3 · Optional: your schedule</h2>
        <p className="text-sm muted">Used for the countdown and to work out how much study time you have.</p>
        <div className="grid sm:grid-cols-3 gap-4">
          <label className="text-sm">
            <span className="block mb-1">Interview date</span>
            <input className="field" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label className="text-sm">
            <span className="block mb-1">Interview time</span>
            <input className="field" type="time" value={time} disabled={!date} onChange={(e) => setTime(e.target.value)} />
          </label>
          <label className="text-sm">
            <span className="block mb-1">Hours available per day</span>
            <input className="field" type="number" min={0.5} max={16} step={0.5} value={hours}
              onChange={(e) => setHours(e.target.value)} />
          </label>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <button className="btn text-base px-6 py-3" disabled={!resume || !job || start.isPending} onClick={() => start.mutate()}>
          {start.isPending ? "Starting…" : "Analyse"}
        </button>
        {(!resume || !job) && <span className="text-sm muted">Add a resume and a job posting first.</span>}
        {start.isError && <ErrorState message={start.error.message} />}
      </div>
    </div>
  );
}
