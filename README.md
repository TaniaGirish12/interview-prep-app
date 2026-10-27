# Interview Prep

Upload your resume (PDF) and a job posting URL. The app pulls every requirement out of the posting, matches each one against your resume, and generates study notes, diagrams and checked code examples for what the posting asks for. Every requirement keeps the exact line it was quoted from.

- **Backend:** FastAPI, Anthropic Python SDK, SQLite (`backend/`)
- **Frontend:** React, TypeScript, Vite, Tailwind, Recharts, Mermaid, Shiki (`frontend/`)
- **Design:** see [DESIGN.md](DESIGN.md) for schemas, prompts and the checks

## Setup

Requirements: Python 3.10+, Node 20+, and optionally `g++` (on macOS the Xcode command-line tools provide it) for checking C++ snippets.

```bash
npm install
```

```bash
npm run setup
```

```bash
cp .env.example .env
```

### Choose a model backend

The app can call Claude in two ways. Set `LLM_BACKEND` in `.env`.

**`claude-code` (default): uses your Claude subscription, with no API key.**
The backend runs the Claude Code CLI headless (`claude -p`) for each step. Install the CLI once:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Then run `claude` once in a terminal and log in with your Claude account. Afterwards, `claude -p "hi"` should answer. If `claude` isn't on your PATH, set `CLAUDE_CLI` in `.env` to its full path. Usage counts against your plan's limits and calls are slower than the API. The app removes any `ANTHROPIC_API_KEY` from the CLI's environment, so this backend never bills per token. Check your plan's terms if you use this for more than personal prep.

**`api`: Anthropic API, billed per token.**
Create a key at https://platform.claude.com (API Keys; requires credits) and set `LLM_BACKEND=api` and `ANTHROPIC_API_KEY=...`. This backend adds prompt caching, the refusal fallback and a dollar cost estimate.

Both backends use the same prompts, schemas, validation, retry and checks. http://127.0.0.1:8000/api/health shows which backend is active.

## Run

```bash
npm run dev
```

This starts the API on http://127.0.0.1:8000 and the app on http://localhost:5173. Vite forwards `/api` requests to the backend.

## Try it with your resume and the MBition posting

1. Open http://localhost:5173.
2. Drag `resume.pdf` onto the upload area. Check the extracted text and fix anything the PDF parser got wrong, such as broken lines, missing bullets or merged columns. Your corrections are what gets analysed.
3. Paste `https://mbition.io/career/working-student-intern-driving-functions-software-development-all-genders/` and click **Fetch posting**. The page is server-rendered, so the full JD is extracted from the HTML. You can expand the preview to check it.
4. Optionally set the interview date and hours per day, then click **Analyse**.
5. Watch the four pipeline steps complete. Then:
   - **Overview** shows the match score, a radar by skill area, requirements by tier and status, the countdown, and "study next".
   - **JD vs resume** is the filterable, sortable matrix. Expand a row to see the quoted JD line and the resume evidence.
   - Click any requirement to open its **topic notes**. The top 5 tier 1–2 topics in study-next order are pre-generated in the background (`PREFETCH_TOPICS` in `.env`; `0` turns this off). Opening any topic generates it on demand and moves it to the front of the queue.
   - **Knowledge gaps** shows an ordered learning plan with hour estimates. **Company & role** shows quotes from the posting only.

The top right of each analysis shows the running cost estimate (API backend) or the token count (subscription backend). Reopening an analysis, or analysing the same resume and posting again, comes from the cache and costs nothing.

If a posting page is rendered with JavaScript, fetching fails with a clear message and a paste box appears. The app never makes up a JD.

## Tests

```bash
npm test
```

- **Backend (`pytest`):**
  - URL extraction against the saved MBition page (`backend/tests/fixtures/mbition_jd.html`), JSON-LD, too-short pages and fetch errors
  - PDF parsing, including the pypdf fallback
  - Strict tool schemas and Pydantic validation
  - Quote normalisation and verification
  - ID integrity and scoring, with hand-computed values
  - The whole pipeline with a mocked LLM, including the retry-once path
  - C++ checks with g++ and ThreadSanitizer, and Python 3.10 checks
- **Frontend (`vitest`):**
  - The matrix filter, sort and expand
  - Code block badge and copy
  - Answer reveal
  - Mermaid fallback
  - Markdown safety
  - A contract test that parses the backend's payloads with the zod schemas

The resume used in tests is synthetic (`backend/tests/make_fixtures.py`), so no real resume is needed.

## How it keeps the output honest

- **Quotes are verified in code.** Every JD item, resume item and evidence quote must appear in its source text (after normalising whitespace, quotes, dashes and PDF ligatures). Items that fail are dropped and listed under *Deterministic checks* on the overview. A match whose evidence all fails is set to Gap.
- **IDs are assigned in code** (`JD-T01`, `JD-R01`, `JD-N01`, `CV-01`). Anything that references an unknown ID is dropped.
- **Scores are computed in Python.** Tier weights are 4/3/2/1 and status values 1/0.5/0. The model never computes a score.
- **Code is compiled.** C++ is checked with `g++ -std=c++17 -Wall -Wextra -fsyntax-only`; runnable snippets are also built and run with `-fsanitize=thread`. Python is checked with `py_compile` plus a Python 3.10 grammar check. A failing snippet gets one repair attempt; if it still fails it's shown with a **Not verified** badge.
- **Structured output.** Each step has one JSON schema: a strict tool on the API backend, `--json-schema` on the CLI backend. The result is validated with Pydantic, and a failure is fed back to the model once. Forced `tool_choice` is rejected by this model, so the prompt names the tool instead.
- **Fetched pages and your resume are treated as data.** They're wrapped in `<job_posting_data>` and `<resume_data>`, and the system prompt tells the model never to follow instructions inside them.

## Layout

```
backend/app/ingest/     PDF and job-posting extraction
backend/app/llm/        Claude backends (API: strict tools + caching; CLI: claude -p), retry, prompts
backend/app/pipeline/   steps 1–4, topic queue (step 5), gaps, SSE events, cache keys
backend/app/checks/     quote, ID, scoring and code checks
frontend/src/pages/     NewAnalysis, Dashboard, Matrix, Topic, Gaps, Company
frontend/src/schemas/   zod mirrors of the backend schemas
```

Data lives in `backend/data/app.db` (SQLite). Delete that file to start fresh.
