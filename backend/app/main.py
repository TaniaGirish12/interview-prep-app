import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api import analyses, flashcards, inputs, plan, topics
from .config import get_settings
from .pipeline.topic_queue import queue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.connect()
    queue.start()
    yield
    await queue.stop()


app = FastAPI(title="Interview Prep API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(inputs.router)
app.include_router(analyses.router)
app.include_router(topics.router)
app.include_router(plan.router)
app.include_router(flashcards.router)


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    out = {"ok": True, "backend": s.llm_backend, "model": s.anthropic_model}
    if s.llm_backend == "api":
        out["api_key_set"] = bool(s.anthropic_api_key)
    else:
        from .llm.cli_backend import cli_path

        out["claude_cli"] = cli_path()
    return out
