"""Project controls for one project: schedule (phases, tasks, baseline), budget
(earned value, expenses, change orders), compliance (permits, inspections) and
an overview with what needs attention. The figures are worked out in
``project_controls_service``. Mounted under /api/v1/projects beside projects.py.
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import BudgetItem, ChangeOrder, ConstructionPhase, Inspection, Permit, Project, Task
from ...services import project_controls_service as controls
from ...services.project_controls_service import ControlsError, at_midnight

router = APIRouter()


def _project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _owned(db: Session, model, item_id: int, project_id: int, what: str):
    item = db.get(model, item_id)
    if item is None or item.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"{what} not found")
    return item


def _commit(db: Session) -> None:
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not save: {e}")


def _apply(target, data: dict, dates: tuple[str, ...] = ()) -> None:
    for field, value in data.items():
        if field in dates and isinstance(value, date) and not isinstance(value, datetime):
            value = at_midnight(value)
        setattr(target, field, value)


# --- overview --------------------------------------------------------------

@router.get("/{project_id}/overview")
def project_overview(project_id: int, db: Session = Depends(get_db)):
    """Schedule, budget and compliance figures for the dashboard's home page,
    the current floor plan, linked clients, and what needs attention."""
    return controls.overview(db, _project(db, project_id), date.today())


# --- schedule --------------------------------------------------------------

class BaselineRequest(BaseModel):
    start_date: date


class PhaseUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    budgeted_cost: Optional[float] = Field(None, ge=0)
    progress_percentage: Optional[float] = Field(None, ge=0, le=100)


class PhaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    budgeted_cost: float = Field(0.0, ge=0)


class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    priority: str = "medium"
    planned_duration_days: float = Field(1.0, gt=0)
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    budgeted_cost: float = Field(0.0, ge=0)
    requires_inspection: bool = False


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    planned_duration_days: Optional[float] = Field(None, gt=0)
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    budgeted_cost: Optional[float] = Field(None, ge=0)
    actual_cost: Optional[float] = Field(None, ge=0)
    requires_inspection: Optional[bool] = None


TASK_DATES = ("planned_start_date", "planned_end_date")


@router.get("/{project_id}/schedule")
def get_schedule(project_id: int, db: Session = Depends(get_db)):
    """Phases in order with their tasks, earned progress and planned dates."""
    return controls.schedule(_project(db, project_id), date.today())


@router.post("/{project_id}/schedule/baseline")
def baseline(project_id: int, body: BaselineRequest, db: Session = Depends(get_db)):
    """Plan every phase and task end to end from ``start_date`` using the task
    durations. Replaces any planned dates."""
    project = _project(db, project_id)
    controls.baseline_schedule(project, body.start_date)
    _commit(db)
    return controls.schedule(project, date.today())


@router.post("/{project_id}/phases", status_code=201)
def create_phase(project_id: int, body: PhaseCreate, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    order = max((p.phase_order or 0 for p in project.phases or []), default=0) + 1
    phase = ConstructionPhase(project_id=project.id, phase_order=order, status="pending", **body.model_dump())
    db.add(phase)
    _commit(db)
    return controls.serialize_phase(phase, date.today())


@router.patch("/{project_id}/phases/{phase_id}")
def update_phase(project_id: int, phase_id: int, body: PhaseUpdate, db: Session = Depends(get_db)):
    phase = _owned(db, ConstructionPhase, phase_id, project_id, "Phase")
    _apply(phase, body.model_dump(exclude_unset=True), TASK_DATES)
    _commit(db)
    return controls.serialize_phase(phase, date.today())


@router.post("/{project_id}/phases/{phase_id}/tasks", status_code=201)
def create_task(project_id: int, phase_id: int, body: TaskCreate, db: Session = Depends(get_db)):
    phase = _owned(db, ConstructionPhase, phase_id, project_id, "Phase")
    try:
        controls.check(body.priority, controls.TASK_PRIORITIES, "priority")
    except ControlsError as e:
        raise HTTPException(status_code=422, detail=str(e))
    order = max((t.task_order or 0 for t in phase.tasks or []), default=0) + 1
    task = Task(project_id=project_id, phase_id=phase.id, task_order=order, status="pending")
    _apply(task, body.model_dump(), TASK_DATES)
    db.add(task)
    db.flush()
    db.refresh(phase)
    controls.refresh_phase(phase, date.today())
    _commit(db)
    return controls.serialize_task(task, date.today())


@router.patch("/{project_id}/tasks/{task_id}")
def update_task(project_id: int, task_id: int, body: TaskUpdate, db: Session = Depends(get_db)):
    """Change a task. A status change records when work actually started and
    finished and re-earns the phase's progress."""
    task = _owned(db, Task, task_id, project_id, "Task")
    today = date.today()
    data = body.model_dump(exclude_unset=True)
    try:
        controls.check(data.get("priority"), controls.TASK_PRIORITIES, "priority")
        if "status" in data:
            controls.set_task_status(task, data.pop("status"), today)
    except ControlsError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _apply(task, data, TASK_DATES)
    controls.refresh_phase(task.phase, today)
    _commit(db)
    return {"task": controls.serialize_task(task, today), "phase": controls.serialize_phase(task.phase, today)}


@router.delete("/{project_id}/tasks/{task_id}")
def delete_task(project_id: int, task_id: int, db: Session = Depends(get_db)):
    task = _owned(db, Task, task_id, project_id, "Task")
    phase = task.phase
    db.delete(task)
    db.flush()
    db.refresh(phase)
    controls.refresh_phase(phase, date.today())
    _commit(db)
    return {"deleted": task_id}


# --- budget ----------------------------------------------------------------

class ExpenseCreate(BaseModel):
    vendor: str = Field(..., min_length=1, max_length=255)
    amount: float = Field(..., gt=0)
    category: str = "other"
    description: Optional[str] = None
    status: str = "paid"
    incurred_on: Optional[date] = None
    invoice_number: Optional[str] = Field(None, max_length=100)
    phase_id: Optional[int] = None


class ChangeOrderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    cost_impact: float = 0.0
    schedule_impact_days: float = 0.0
    status: str = "submitted"
    requested_by: Optional[str] = Field(None, max_length=255)
    floor_plan_version: Optional[int] = None


class ChangeOrderUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    cost_impact: Optional[float] = None
    schedule_impact_days: Optional[float] = None
    status: Optional[str] = None
    requested_by: Optional[str] = Field(None, max_length=255)


@router.get("/{project_id}/budget")
def get_budget(project_id: int, db: Session = Depends(get_db)):
    """Earned value (BAC, PV, EV, AC, CPI, SPI, EAC), cost by phase and by category."""
    return controls.budget_summary(_project(db, project_id), date.today())


@router.get("/{project_id}/expenses")
def list_expenses(project_id: int, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    items = sorted(project.budget_items or [], key=lambda i: (i.actual_date or i.created_at or datetime.min, i.id), reverse=True)
    return {"expenses": [controls.serialize_expense(i) for i in items]}


@router.post("/{project_id}/expenses", status_code=201)
def create_expense(project_id: int, body: ExpenseCreate, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    try:
        item = controls.add_expense(db, project, body.model_dump())
    except ControlsError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _commit(db)
    db.refresh(item)
    return controls.serialize_expense(item)


@router.delete("/{project_id}/expenses/{expense_id}")
def delete_expense(project_id: int, expense_id: int, db: Session = Depends(get_db)):
    db.delete(_owned(db, BudgetItem, expense_id, project_id, "Expense"))
    _commit(db)
    return {"deleted": expense_id}


@router.get("/{project_id}/change-orders")
def list_change_orders(project_id: int, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    return {"change_orders": [controls.serialize_change_order(co) for co in reversed(project.change_orders or [])]}


@router.post("/{project_id}/change-orders", status_code=201)
def create_change_order(project_id: int, body: ChangeOrderCreate, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    if body.status not in controls.CHANGE_ORDER_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown change order status '{body.status}'")
    co = ChangeOrder(project_id=project.id, number=controls.next_change_order_number(project), **body.model_dump())
    if co.status in ("approved", "rejected"):
        co.decided_at = datetime.now().astimezone()
    db.add(co)
    _commit(db)
    return controls.serialize_change_order(co)


@router.patch("/{project_id}/change-orders/{co_id}")
def update_change_order(project_id: int, co_id: int, body: ChangeOrderUpdate, db: Session = Depends(get_db)):
    """Edit a change order, or approve / reject it (records when)."""
    co = _owned(db, ChangeOrder, co_id, project_id, "Change order")
    data = body.model_dump(exclude_unset=True)
    status = data.get("status")
    if status is not None and status not in controls.CHANGE_ORDER_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown change order status '{status}'")
    if status and status != co.status:
        co.decided_at = datetime.now().astimezone() if status in ("approved", "rejected") else None
    _apply(co, data)
    _commit(db)
    return controls.serialize_change_order(co)


# --- compliance ------------------------------------------------------------

class PermitCreate(BaseModel):
    permit_number: str = Field(..., min_length=1, max_length=100)
    permit_type: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    jurisdiction: Optional[str] = Field(None, max_length=255)
    status: str = "applied"
    application_date: Optional[date] = None
    issued_date: Optional[date] = None
    expiration_date: Optional[date] = None
    permit_fee: float = Field(0.0, ge=0)
    conditions: Optional[str] = None
    contact_name: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)
    contact_email: Optional[str] = Field(None, max_length=255)


class PermitUpdate(BaseModel):
    permit_number: Optional[str] = Field(None, min_length=1, max_length=100)
    permit_type: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    jurisdiction: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = None
    application_date: Optional[date] = None
    issued_date: Optional[date] = None
    expiration_date: Optional[date] = None
    permit_fee: Optional[float] = Field(None, ge=0)
    conditions: Optional[str] = None
    contact_name: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)
    contact_email: Optional[str] = Field(None, max_length=255)


class InspectionCreate(BaseModel):
    inspection_type: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    permit_id: Optional[int] = None
    task_id: Optional[int] = None
    inspector_name: Optional[str] = Field(None, max_length=255)
    scheduled_date: Optional[datetime] = None


class InspectionUpdate(BaseModel):
    inspection_type: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    permit_id: Optional[int] = None
    inspector_name: Optional[str] = Field(None, max_length=255)
    scheduled_date: Optional[datetime] = None
    status: Optional[str] = None
    result_details: Optional[str] = None
    critical_findings: Optional[str] = None
    requires_followup: Optional[bool] = None
    followup_completed: Optional[bool] = None


PERMIT_DATES = ("application_date", "issued_date", "expiration_date")


def _check_permit_status(status: Optional[str]) -> None:
    if status is not None and status not in controls.PERMIT_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown permit status '{status}'")


def _check_permit_link(db: Session, project_id: int, permit_id: Optional[int]) -> None:
    if permit_id is not None:
        _owned(db, Permit, permit_id, project_id, "Permit")


@router.get("/{project_id}/compliance")
def get_compliance(project_id: int, db: Session = Depends(get_db)):
    """Permits, inspections (soonest first) and their summary counts."""
    project = _project(db, project_id)
    today = date.today()
    inspections = sorted(project.inspections or [], key=lambda i: (i.scheduled_date is None, i.scheduled_date or datetime.min, i.id))
    return {
        "summary": controls.compliance_summary(project, today),
        "permits": [controls.serialize_permit(p) for p in sorted(project.permits or [], key=lambda p: p.id)],
        "inspections": [controls.serialize_inspection(i) for i in inspections],
    }


@router.post("/{project_id}/permits", status_code=201)
def create_permit(project_id: int, body: PermitCreate, db: Session = Depends(get_db)):
    _project(db, project_id)
    _check_permit_status(body.status)
    permit = Permit(project_id=project_id)
    _apply(permit, body.model_dump(), PERMIT_DATES)
    permit.total_cost = permit.permit_fee
    db.add(permit)
    _commit(db)
    return controls.serialize_permit(permit)


@router.patch("/{project_id}/permits/{permit_id}")
def update_permit(project_id: int, permit_id: int, body: PermitUpdate, db: Session = Depends(get_db)):
    permit = _owned(db, Permit, permit_id, project_id, "Permit")
    data = body.model_dump(exclude_unset=True)
    _check_permit_status(data.get("status"))
    _apply(permit, data, PERMIT_DATES)
    _commit(db)
    return controls.serialize_permit(permit)


@router.delete("/{project_id}/permits/{permit_id}")
def delete_permit(project_id: int, permit_id: int, db: Session = Depends(get_db)):
    db.delete(_owned(db, Permit, permit_id, project_id, "Permit"))
    _commit(db)
    return {"deleted": permit_id}


@router.post("/{project_id}/inspections", status_code=201)
def create_inspection(project_id: int, body: InspectionCreate, db: Session = Depends(get_db)):
    _project(db, project_id)
    _check_permit_link(db, project_id, body.permit_id)
    if body.task_id is not None:
        _owned(db, Task, body.task_id, project_id, "Task")
    inspection = Inspection(project_id=project_id, status="scheduled", **body.model_dump())
    db.add(inspection)
    _commit(db)
    return controls.serialize_inspection(inspection)


@router.patch("/{project_id}/inspections/{inspection_id}")
def update_inspection(project_id: int, inspection_id: int, body: InspectionUpdate, db: Session = Depends(get_db)):
    """Reschedule an inspection or record its result."""
    inspection = _owned(db, Inspection, inspection_id, project_id, "Inspection")
    data = body.model_dump(exclude_unset=True)
    status = data.get("status")
    if status is not None and status not in controls.INSPECTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown inspection status '{status}'")
    _check_permit_link(db, project_id, data.get("permit_id"))
    if status in ("passed", "failed") and not inspection.actual_date:
        inspection.actual_date = datetime.now().astimezone()
    _apply(inspection, data)
    _commit(db)
    return controls.serialize_inspection(inspection)


@router.delete("/{project_id}/inspections/{inspection_id}")
def delete_inspection(project_id: int, inspection_id: int, db: Session = Depends(get_db)):
    db.delete(_owned(db, Inspection, inspection_id, project_id, "Inspection"))
    _commit(db)
    return {"deleted": inspection_id}
