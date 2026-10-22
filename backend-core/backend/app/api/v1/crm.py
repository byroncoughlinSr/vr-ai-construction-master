"""Client CRM: clients through the sales pipeline, their activity timeline,
starting a project for a won client, and AI insights / email drafts
(``ai_assistant_service``). Mounted under /api/v1/crm.
"""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Client, ClientActivity, Project
from ...services import ai_assistant_service as assistant
from ...services import crm_service
from ...services.ai_assistant_service import AssistantError
from ...services.crm_service import CrmError
from ...services.project_controls_service import at_midnight
from .ai_planning import limiter, planning_service

router = APIRouter()


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    company: Optional[str] = Field(None, max_length=255)
    stage: str = "new_inquiry"
    tier: str = "standard"
    source: Optional[str] = Field(None, max_length=100)
    deal_value: float = Field(0.0, ge=0)
    win_probability: Optional[float] = Field(None, ge=0, le=100)
    site_address: Optional[str] = None
    preferred_style: Optional[str] = Field(None, max_length=255)
    target_budget: Optional[float] = Field(None, ge=0)
    target_square_feet: Optional[float] = Field(None, ge=0)
    target_completion_date: Optional[date] = None
    requirements: Optional[str] = None
    tags: List[str] = []
    next_follow_up_at: Optional[datetime] = None
    next_action: Optional[str] = Field(None, max_length=500)
    project_id: Optional[int] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    company: Optional[str] = Field(None, max_length=255)
    stage: Optional[str] = None
    tier: Optional[str] = None
    source: Optional[str] = Field(None, max_length=100)
    deal_value: Optional[float] = Field(None, ge=0)
    win_probability: Optional[float] = Field(None, ge=0, le=100)
    lost_reason: Optional[str] = None
    site_address: Optional[str] = None
    preferred_style: Optional[str] = Field(None, max_length=255)
    target_budget: Optional[float] = Field(None, ge=0)
    target_square_feet: Optional[float] = Field(None, ge=0)
    target_completion_date: Optional[date] = None
    requirements: Optional[str] = None
    tags: Optional[List[str]] = None
    next_follow_up_at: Optional[datetime] = None
    next_action: Optional[str] = Field(None, max_length=500)
    sentiment: Optional[str] = None
    project_id: Optional[int] = None


class ActivityCreate(BaseModel):
    kind: str = "note"
    summary: str = Field(..., min_length=1, max_length=500)
    details: Optional[str] = None
    sentiment: Optional[str] = None
    action_items: List[str] = []
    author: Optional[str] = Field(None, max_length=255)
    occurred_at: Optional[datetime] = None


class StartProject(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    project_id: Optional[int] = None  # link an existing project instead


class DraftRequest(BaseModel):
    purpose: str = "follow_up"
    notes: Optional[str] = None
    sender: Optional[str] = Field(None, max_length=120)


def _client(db: Session, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _commit(db: Session) -> None:
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not save: {e}")


def _fields(data: dict, db: Session) -> dict:
    if data.get("project_id") is not None and db.get(Project, data["project_id"]) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if isinstance(data.get("target_completion_date"), date):
        data["target_completion_date"] = at_midnight(data["target_completion_date"])
    return data


def _detail(db: Session, client: Client) -> dict:
    db.refresh(client)  # re-sorts the activities, newest first
    return crm_service.serialize_client(client, with_activities=True)


@router.get("/clients")
def list_clients(
    stage: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Client)
    if stage:
        query = query.filter(Client.stage == stage)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(
            Client.name.ilike(like), Client.email.ilike(like), Client.company.ilike(like),
            Client.site_address.ilike(like), Client.preferred_style.ilike(like),
        ))
    clients = query.order_by(Client.updated_at.desc().nullslast(), Client.id.desc()).all()
    return {"clients": [crm_service.serialize_client(c) for c in clients]}


@router.get("/pipeline")
def get_pipeline(db: Session = Depends(get_db)):
    """Counts and value per stage, weighted forecast, win rate, follow-ups due
    and leads gone quiet (no contact for two weeks, no follow-up set)."""
    return crm_service.pipeline(db.query(Client).all(), date.today())


@router.post("/clients", status_code=201)
def create_client(body: ClientCreate, db: Session = Depends(get_db)):
    data = _fields(body.model_dump(), db)
    try:
        crm_service.check_choice(data["stage"], crm_service.STAGE_IDS, "stage")
        crm_service.check_choice(data["tier"], crm_service.TIERS, "tier")
    except CrmError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if data["win_probability"] is None:
        data["win_probability"] = crm_service.STAGE_PROBABILITY[data["stage"]]
    client = Client(**data)
    db.add(client)
    crm_service.log_activity(client, "note", "Client added")
    _commit(db)
    return _detail(db, client)


@router.get("/clients/{client_id}")
def get_client(client_id: int, db: Session = Depends(get_db)):
    return crm_service.serialize_client(_client(db, client_id), with_activities=True)


@router.patch("/clients/{client_id}")
def update_client(client_id: int, body: ClientUpdate, db: Session = Depends(get_db)):
    client = _client(db, client_id)
    try:
        crm_service.apply_update(client, _fields(body.model_dump(exclude_unset=True), db))
    except CrmError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _commit(db)
    return _detail(db, client)


@router.delete("/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    db.delete(_client(db, client_id))
    _commit(db)
    return {"deleted": client_id}


@router.post("/clients/{client_id}/activities", status_code=201)
def add_activity(client_id: int, body: ActivityCreate, db: Session = Depends(get_db)):
    """Log a call, email, meeting, VR demo, site visit or note."""
    client = _client(db, client_id)
    data = body.model_dump()
    kind, summary = data.pop("kind"), data.pop("summary")
    try:
        crm_service.log_activity(client, kind, summary, **data)
    except CrmError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _commit(db)
    return _detail(db, client)


@router.delete("/clients/{client_id}/activities/{activity_id}")
def delete_activity(client_id: int, activity_id: int, db: Session = Depends(get_db)):
    activity = db.get(ClientActivity, activity_id)
    if activity is None or activity.client_id != client_id:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.delete(activity)
    _commit(db)
    return _detail(db, _client(db, client_id))


@router.post("/clients/{client_id}/project", status_code=201)
def start_project(client_id: int, body: StartProject, db: Session = Depends(get_db)):
    """Start a project for the client (site, budget and brief carried over), or
    link an existing one with ``project_id``."""
    client = _client(db, client_id)
    if body.project_id is not None:
        project = db.get(Project, body.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        client.project_id = project.id
        crm_service.log_activity(client, "note", f"Linked to project: {project.name}")
    else:
        project = crm_service.create_project_for_client(db, client, body.name)
    _commit(db)
    return {"project_id": project.id, "project_name": project.name, "client": _detail(db, client)}


@router.post("/clients/{client_id}/ai/insights")
@limiter.limit("10/minute")
async def ai_insights(client_id: int, request: Request, db: Session = Depends(get_db)):
    """Summarise the client from their record and activity: preferences, risks,
    the next best action. Saved on the client."""
    client = _client(db, client_id)
    try:
        insights = await assistant.client_insights(planning_service, db, client, date.today())
    except AssistantError as e:
        raise HTTPException(status_code=503, detail=str(e))
    client.ai_summary = insights["summary"]
    client.ai_insights = {k: insights[k] for k in ("preferences", "risks", "next_best_action")}
    client.ai_updated_at = datetime.now().astimezone()
    if insights["sentiment"] and not client.sentiment:
        client.sentiment = insights["sentiment"]
    _commit(db)
    return {"client": _detail(db, client), "source": insights["source"]}


@router.post("/clients/{client_id}/ai/draft")
@limiter.limit("10/minute")
async def ai_draft(client_id: int, body: DraftRequest, request: Request, db: Session = Depends(get_db)):
    """Draft an email to the client from their record and project. Nothing is
    sent; log it as an activity once it has been."""
    client = _client(db, client_id)
    try:
        return await assistant.draft_email(
            planning_service, db, client, body.purpose, body.notes, body.sender, date.today(),
        )
    except AssistantError as e:
        raise HTTPException(status_code=503, detail=str(e))
