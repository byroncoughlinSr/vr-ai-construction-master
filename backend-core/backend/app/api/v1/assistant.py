"""The dashboard copilot: questions about the current project and the CRM,
answered from the database by the AI (``ai_assistant_service.copilot``), with
actions the dashboard can carry out once the user confirms them.
Mounted under /api/v1/assistant.
"""

from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Client, Project
from ...services import ai_assistant_service as assistant
from ...services.ai_assistant_service import AssistantError
from .ai_planning import limiter, planning_service

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=8000)


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1)
    project_id: Optional[int] = None
    client_id: Optional[int] = None


@router.post("/chat")
@limiter.limit("20/minute")
async def chat(body: ChatRequest, request: Request, db: Session = Depends(get_db)):
    """``{reply, actions, source}``. Actions: refine_floor_plan, create_task,
    draft_email, create_change_order, navigate — the dashboard asks before
    running one."""
    if body.messages[-1].role != "user":
        raise HTTPException(status_code=422, detail="The last message must be the user's")
    project = db.get(Project, body.project_id) if body.project_id is not None else None
    if body.project_id is not None and project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    client = db.get(Client, body.client_id) if body.client_id is not None else None
    try:
        return await assistant.copilot(
            planning_service, db, [m.model_dump() for m in body.messages], project, client, date.today(),
        )
    except AssistantError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/status")
def status():
    """Which AI providers the copilot can use right now."""
    return {
        "groq": planning_service.groq_available,
        "ollama": planning_service.ollama_available,
        "gemini": planning_service.gemini_available,
    }
