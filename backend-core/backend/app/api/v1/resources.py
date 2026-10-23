"""Crew (labor_resources) and equipment, shared across projects: each is on at
most one project at a time. Mounted under /api/v1/resources.
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Equipment, LaborResource, Project
from ...services import project_controls_service as controls
from ...services.project_controls_service import at_midnight

router = APIRouter()


def _commit(db: Session) -> None:
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not save: {e}")


def _check_project(db: Session, project_id: Optional[int]) -> None:
    if project_id is not None and db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


def _get(db: Session, model, item_id: int, what: str):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{what} not found")
    return item


# --- crew ------------------------------------------------------------------

class CrewMember(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    hourly_rate: float = Field(0.0, ge=0)
    max_hours_per_week: float = Field(40.0, ge=0)
    is_available: bool = True
    project_id: Optional[int] = None


class CrewUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    hourly_rate: Optional[float] = Field(None, ge=0)
    max_hours_per_week: Optional[float] = Field(None, ge=0)
    is_available: Optional[bool] = None
    project_id: Optional[int] = None


def _crew_fields(data: dict) -> dict:
    if "project_id" in data:
        data["current_project_id"] = data.pop("project_id")
    return data


@router.get("/crew")
def list_crew(project_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    """Everyone, or only those on ``project_id``."""
    query = db.query(LaborResource)
    if project_id is not None:
        query = query.filter(LaborResource.current_project_id == project_id)
    return {"crew": [controls.serialize_crew(m) for m in query.order_by(LaborResource.role, LaborResource.name)]}


@router.post("/crew", status_code=201)
def create_crew(body: CrewMember, db: Session = Depends(get_db)):
    _check_project(db, body.project_id)
    member = LaborResource(**_crew_fields(body.model_dump()))
    db.add(member)
    _commit(db)
    return controls.serialize_crew(member)


@router.patch("/crew/{member_id}")
def update_crew(member_id: int, body: CrewUpdate, db: Session = Depends(get_db)):
    member = _get(db, LaborResource, member_id, "Crew member")
    data = body.model_dump(exclude_unset=True)
    _check_project(db, data.get("project_id"))
    for field, value in _crew_fields(data).items():
        setattr(member, field, value)
    _commit(db)
    db.refresh(member)
    return controls.serialize_crew(member)


@router.delete("/crew/{member_id}")
def delete_crew(member_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, LaborResource, member_id, "Crew member"))
    _commit(db)
    return {"deleted": member_id}


# --- equipment -------------------------------------------------------------

class EquipmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    equipment_type: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    model: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=100)
    owned: bool = True
    rental_company: Optional[str] = Field(None, max_length=255)
    daily_rate: float = Field(0.0, ge=0)
    status: str = "available"
    next_maintenance_date: Optional[date] = None
    location: Optional[str] = Field(None, max_length=255)
    project_id: Optional[int] = None


class EquipmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    equipment_type: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    model: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=100)
    owned: Optional[bool] = None
    rental_company: Optional[str] = Field(None, max_length=255)
    daily_rate: Optional[float] = Field(None, ge=0)
    status: Optional[str] = None
    next_maintenance_date: Optional[date] = None
    location: Optional[str] = Field(None, max_length=255)
    project_id: Optional[int] = None


EQUIPMENT_COLUMNS = {
    "owned": "owned_by_company",
    "daily_rate": "rental_rate_daily",
    "location": "current_location",
    "project_id": "assigned_to_project_id",
}


def _equipment_fields(data: dict) -> dict:
    fields = {EQUIPMENT_COLUMNS.get(k, k): v for k, v in data.items()}
    day = fields.get("next_maintenance_date")
    if isinstance(day, date) and not isinstance(day, datetime):
        fields["next_maintenance_date"] = at_midnight(day)
    return fields


def _check_status(status: Optional[str]) -> None:
    if status is not None and status not in controls.EQUIPMENT_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown equipment status '{status}'")


@router.get("/equipment")
def list_equipment(project_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Equipment)
    if project_id is not None:
        query = query.filter(Equipment.assigned_to_project_id == project_id)
    return {"equipment": [controls.serialize_equipment(e) for e in query.order_by(Equipment.equipment_type, Equipment.name)]}


@router.post("/equipment", status_code=201)
def create_equipment(body: EquipmentCreate, db: Session = Depends(get_db)):
    _check_status(body.status)
    _check_project(db, body.project_id)
    item = Equipment(**_equipment_fields(body.model_dump()))
    db.add(item)
    _commit(db)
    return controls.serialize_equipment(item)


@router.patch("/equipment/{item_id}")
def update_equipment(item_id: int, body: EquipmentUpdate, db: Session = Depends(get_db)):
    item = _get(db, Equipment, item_id, "Equipment")
    data = body.model_dump(exclude_unset=True)
    _check_status(data.get("status"))
    _check_project(db, data.get("project_id"))
    for field, value in _equipment_fields(data).items():
        setattr(item, field, value)
    _commit(db)
    db.refresh(item)
    return controls.serialize_equipment(item)


@router.delete("/equipment/{item_id}")
def delete_equipment(item_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, Equipment, item_id, "Equipment"))
    _commit(db)
    return {"deleted": item_id}
