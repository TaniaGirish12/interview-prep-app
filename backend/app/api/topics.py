from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..llm.client import LLMError
from ..pipeline.topic_queue import queue
from ..pipeline.topics import get_cached_topic

router = APIRouter(prefix="/api/analyses/{analysis_id}/topics")


@router.get("/{jd_id}")
async def get_topic(analysis_id: int, jd_id: str):
    try:
        content = get_cached_topic(analysis_id, jd_id)
    except KeyError as e:
        raise HTTPException(404, f"Unknown requirement {jd_id}.") from e
    except LLMError as e:
        raise HTTPException(409, str(e)) from e
    if content is not None:
        return {"status": "ready", "content": content}
    return JSONResponse(status_code=202, content=queue.status_of(analysis_id, jd_id))


@router.post("/{jd_id}/open")
async def open_topic(analysis_id: int, jd_id: str) -> dict:
    try:
        queue.open(analysis_id, jd_id)
    except KeyError as e:
        raise HTTPException(404, f"Unknown requirement {jd_id}.") from e
    except LLMError as e:
        raise HTTPException(409, str(e)) from e
    return queue.status_of(analysis_id, jd_id)
