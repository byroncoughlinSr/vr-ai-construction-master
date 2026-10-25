"""Project controls for one project: schedule (phases, tasks, baseline), budget
(earned value, expenses, change orders), compliance (permits, inspections), the
punch list and an overview with what needs attention. The figures are worked out in
``project_controls_service``. Mounted under /api/v1/projects beside projects.py.

The construction plan is kept in pm-mcp: these routes read and write it there
(``pm_client``), so the responses keep the shapes the dashboard uses. Errors:
404 for a phase/task/record that isn't this project's, 409 when pm-mcp refuses
(e.g. finishing an inspection task before its inspection passed), 422 for bad
values, 503 when pm-mcp isn't running.
"""

import logging
from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Project, PunchItem
from ...services import project_controls_service as controls
from ...services.pm_client import ACTOR, PMClient, PMError, PMUnavailable, get_pm
from ...services.project_controls_service import ControlsError, NotFound, Plan

router = APIRouter()
logger = logging.getLogger(__name__)


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


@contextmanager
def _pm_errors() -> Iterator[None]:
    try:
        yield
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ControlsError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except PMUnavailable as e:
        raise HTTPException(status_code=503, detail=f"The construction plan service is unavailable: {e}")
    except PMError as e:
        message = str(e)
        raise HTTPException(status_code=404 if "not found" in message else 409, detail=message)


def _plan(db: Session, pm: PMClient, project: Project) -> Plan:
    """This project's plan in pm-mcp, creating the pm-mcp project on first use."""
    controls.ensure_pm_project(db, pm, project)
    return controls.load_plan(pm, project)


# --- overview --------------------------------------------------------------

@router.get("/{project_id}/overview")
def project_overview(project_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    """Schedule, budget and compliance figures for the dashboard's home page,
    the current floor plan, linked clients, and what needs attention. Still
    answers when pm-mcp is down (``pm_available`` false, plan figures empty)."""
    return controls.overview(db, pm, _project(db, project_id), date.today())


# --- construction plan templates -------------------------------------------

class ApplyTemplate(BaseModel):
    template: str = Field(..., min_length=1)
    start_date: Optional[date] = None


@router.get("/{project_id}/construction-templates")
def list_templates(project_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    """pm-mcp's construction plan templates (phases, task count, roles) that
    can be laid into this project."""
    _project(db, project_id)
    with _pm_errors():
        return {"templates": pm.call("list_templates")}


@router.post("/{project_id}/construction-plan", status_code=201)
def apply_template(project_id: int, body: ApplyTemplate, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    """Lay a pm-mcp template's phases and tasks (with permits, inspections and
    their gates) into the project's plan; with ``start_date`` also baseline it."""
    project = _project(db, project_id)
    with _pm_errors():
        plan = _plan(db, pm, project)
        result = pm.call("apply_template", project_id=plan.pm_project_id, template=body.template, actor=ACTOR)
        if body.start_date:
            controls.baseline_schedule(pm, controls.load_plan(pm, project), project, body.start_date)
            _commit(db)
        return {"tasks_created": result["tasks_created"], "records_created": result["records_created"],
                **controls.schedule(controls.load_plan(pm, project), project, date.today())}


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


@router.get("/{project_id}/schedule")
def get_schedule(project_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    """Phases in order with their tasks, earned progress and planned dates."""
    project = _project(db, project_id)
    with _pm_errors():
        return controls.schedule(_plan(db, pm, project), project, date.today())


@router.post("/{project_id}/schedule/baseline")
def baseline(project_id: int, body: BaselineRequest, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    """Plan every task from ``start_date`` along the plan's dependencies using
    the task durations. Replaces any planned dates."""
    project = _project(db, project_id)
    with _pm_errors():
        controls.baseline_schedule(pm, _plan(db, pm, project), project, body.start_date)
        _commit(db)
        return controls.schedule(controls.load_plan(pm, project), project, date.today())


@router.post("/{project_id}/phases", status_code=201)
def create_phase(project_id: int, body: PhaseCreate, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        phase_id = controls.create_phase(pm, _plan(db, pm, project), body.model_dump())
        plan = controls.load_plan(pm, project)
        return controls.serialize_phase(plan, plan.phase(phase_id), date.today())


@router.patch("/{project_id}/phases/{phase_id}")
def update_phase(project_id: int, phase_id: int, body: PhaseUpdate, db: Session = Depends(get_db),
                 pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        plan = _plan(db, pm, project)
        controls.update_phase(pm, plan, plan.phase(phase_id), body.model_dump(exclude_unset=True))
        plan = controls.load_plan(pm, project)
        return controls.serialize_phase(plan, plan.phase(phase_id), date.today())


@router.post("/{project_id}/phases/{phase_id}/tasks", status_code=201)
def create_task(project_id: int, phase_id: int, body: TaskCreate, db: Session = Depends(get_db),
                pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        plan = _plan(db, pm, project)
        task_id = controls.create_task(pm, plan, plan.phase(phase_id), body.model_dump())
        plan = controls.load_plan(pm, project)
        task, phase = plan.task(task_id)
        return controls.serialize_task(task, phase, date.today())


@router.patch("/{project_id}/tasks/{task_id}")
def update_task(project_id: int, task_id: int, body: TaskUpdate, db: Session = Depends(get_db),
                pm: PMClient = Depends(get_pm)):
    """Change a task. A status change records when work actually started and
    finished and re-earns the phase's progress. An inspection task can't be
    completed until its inspection passes (409)."""
    project = _project(db, project_id)
    with _pm_errors():
        plan = _plan(db, pm, project)
        task, phase = plan.task(task_id)
        controls.update_task(pm, plan, task, phase, body.model_dump(exclude_unset=True))
        plan = controls.load_plan(pm, project)
        task, phase = plan.task(task_id)
        today = date.today()
        return {"task": controls.serialize_task(task, phase, today),
                "phase": controls.serialize_phase(plan, phase, today)}


@router.delete("/{project_id}/tasks/{task_id}")
def delete_task(project_id: int, task_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        plan = _plan(db, pm, project)
        controls.delete_task(pm, plan, plan.task(task_id)[0])
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
def get_budget(project_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    """Earned value (BAC, PV, EV, AC, CPI, SPI, EAC), cost by phase and by category."""
    project = _project(db, project_id)
    with _pm_errors():
        return controls.budget_summary(_plan(db, pm, project), project, date.today())


@router.get("/{project_id}/expenses")
def list_expenses(project_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        plan = _plan(db, pm, project)
        expenses = [controls.serialize_expense(plan, r) for r in plan.expenses()]
        expenses.sort(key=lambda e: (e["date"] or e["created_at"] or "", e["id"]), reverse=True)
        return {"expenses": expenses}


@router.post("/{project_id}/expenses", status_code=201)
def create_expense(project_id: int, body: ExpenseCreate, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        plan = _plan(db, pm, project)
        try:
            record = controls.add_expense(pm, plan, body.model_dump())
        except NotFound as e:
            raise ControlsError(f"Phase {body.phase_id} is not part of this project") from e
        return controls.serialize_expense(plan, record)


@router.delete("/{project_id}/expenses/{expense_id}")
def delete_expense(project_id: int, expense_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        plan = _plan(db, pm, project)
        if not any(r["id"] == expense_id for r in plan.expenses()):
            raise NotFound("Expense not found")
        pm.call("delete_record", record_id=expense_id, actor=ACTOR)
        return {"deleted": expense_id}


@router.get("/{project_id}/change-orders")
def list_change_orders(project_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        records = _plan(db, pm, project).of_type("change_order")
        return {"change_orders": [controls.serialize_change_order(project, r)
                                  for r in sorted(records, key=lambda r: r["number"], reverse=True)]}


@router.post("/{project_id}/change-orders", status_code=201)
def create_change_order(project_id: int, body: ChangeOrderCreate, db: Session = Depends(get_db),
                        pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        controls.check(body.status, controls.CHANGE_ORDER_STATUSES, "change order status")
        plan = _plan(db, pm, project)
        data = body.model_dump()
        record = pm.call("create_record", project_id=plan.pm_project_id, record_type="change_order",
                         title=body.title, status=body.status, actor=ACTOR,
                         data={k: v for k, v in controls.change_order_fields(
                             data, data["status"] in ("approved", "rejected")).items() if v is not None})
        return controls.serialize_change_order(project, record)


@router.patch("/{project_id}/change-orders/{co_id}")
def update_change_order(project_id: int, co_id: int, body: ChangeOrderUpdate, db: Session = Depends(get_db),
                        pm: PMClient = Depends(get_pm)):
    """Edit a change order, or approve / reject it (records when)."""
    project = _project(db, project_id)
    with _pm_errors():
        data = body.model_dump(exclude_unset=True)
        controls.check(data.get("status"), controls.CHANGE_ORDER_STATUSES, "change order status")
        current = _plan(db, pm, project).record(co_id, "change_order", "Change order")
        changed = data.get("status") is not None and data["status"] != current["status"]
        record = pm.call("update_record", record_id=co_id, status=data.get("status"), title=data.get("title"),
                         data=controls.change_order_fields(data, changed) or None, actor=ACTOR)
        return controls.serialize_change_order(project, record)


# --- compliance ------------------------------------------------------------

class PermitCreate(BaseModel):
    permit_number: Optional[str] = Field(None, max_length=100)
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
    permit_number: Optional[str] = Field(None, max_length=100)
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


@router.get("/{project_id}/compliance")
def get_compliance(project_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    """Permits, inspections (soonest first) and their summary counts."""
    project = _project(db, project_id)
    with _pm_errors():
        plan = _plan(db, pm, project)
        return {
            "summary": controls.compliance_summary(plan, date.today()),
            "statuses": {"permit": list(controls.PERMIT_STATUSES), "inspection": list(controls.INSPECTION_STATUSES)},
            "permits": [controls.serialize_permit(project, r) for r in sorted(plan.of_type("permit"), key=lambda r: r["id"])],
            "inspections": [controls.serialize_inspection(project, plan, r) for r in controls.sorted_inspections(plan)],
        }


@router.post("/{project_id}/permits", status_code=201)
def create_permit(project_id: int, body: PermitCreate, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        controls.check(body.status, controls.PERMIT_STATUSES, "permit status")
        plan = _plan(db, pm, project)
        data, title = controls.permit_fields(body.model_dump())
        record = pm.call("create_record", project_id=plan.pm_project_id, record_type="permit", title=title,
                         status=body.status, data=data, actor=ACTOR)
        return controls.serialize_permit(project, record)


@router.patch("/{project_id}/permits/{permit_id}")
def update_permit(project_id: int, permit_id: int, body: PermitUpdate, db: Session = Depends(get_db),
                  pm: PMClient = Depends(get_pm)):
    """Edit a permit. Approving it completes the plan's permit task that waits on it."""
    project = _project(db, project_id)
    with _pm_errors():
        data = body.model_dump(exclude_unset=True)
        controls.check(data.get("status"), controls.PERMIT_STATUSES, "permit status")
        _plan(db, pm, project).record(permit_id, "permit", "Permit")
        fields, _title = controls.permit_fields(data)
        record = pm.call("update_record", record_id=permit_id, status=data.get("status"), data=fields or None,
                         actor=ACTOR)
        return controls.serialize_permit(project, record)


@router.delete("/{project_id}/permits/{permit_id}")
def delete_permit(project_id: int, permit_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        _plan(db, pm, project).record(permit_id, "permit", "Permit")
        pm.call("delete_record", record_id=permit_id, actor=ACTOR)
        return {"deleted": permit_id}


def _check_links(plan: Plan, permit_id: Optional[int], task_id: Optional[int]) -> None:
    if permit_id is not None:
        plan.record(permit_id, "permit", "Permit")
    if task_id is not None:
        plan.task(task_id)


@router.post("/{project_id}/inspections", status_code=201)
def create_inspection(project_id: int, body: InspectionCreate, db: Session = Depends(get_db),
                      pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        plan = _plan(db, pm, project)
        _check_links(plan, body.permit_id, body.task_id)
        record = pm.call("create_record", project_id=plan.pm_project_id, record_type="inspection",
                         title=f"{body.inspection_type} inspection", task_id=body.task_id,
                         status="scheduled" if body.scheduled_date else "not_scheduled",
                         data={k: v for k, v in controls.inspection_fields(body.model_dump()).items() if v is not None},
                         actor=ACTOR)
        return controls.serialize_inspection(project, controls.load_plan(pm, project), record)


@router.patch("/{project_id}/inspections/{inspection_id}")
def update_inspection(project_id: int, inspection_id: int, body: InspectionUpdate, db: Session = Depends(get_db),
                      pm: PMClient = Depends(get_pm)):
    """Reschedule an inspection or record its result. passed completes the
    plan's inspection task; failed or partial adds a correction task to it."""
    project = _project(db, project_id)
    with _pm_errors():
        data = body.model_dump(exclude_unset=True)
        status = data.pop("status", None)
        controls.check(status, controls.INSPECTION_STATUSES, "inspection status")
        plan = _plan(db, pm, project)
        plan.record(inspection_id, "inspection", "Inspection")
        _check_links(plan, data.get("permit_id"), None)
        fields = controls.inspection_fields(data)
        if status in ("passed", "failed", "partial"):
            fields["actual_at"] = datetime.now().astimezone().isoformat()
        if fields or (status and status not in ("passed", "failed", "partial")):
            pm.call("update_record", record_id=inspection_id, data=fields or None,
                    status=status if status not in ("passed", "failed", "partial") else None, actor=ACTOR)
        effects = {}
        if status in ("passed", "failed", "partial"):
            result = pm.call("record_inspection_result", inspection_id=inspection_id, result=status,
                             notes=data.get("critical_findings") or data.get("result_details") or "",
                             inspector=data.get("inspector_name"), actor=ACTOR)
            effects = {k: result[k] for k in ("completed_task", "correction_task") if k in result}
        plan = controls.load_plan(pm, project)
        return {**controls.serialize_inspection(project, plan, plan.record(inspection_id, "inspection", "Inspection")),
                **effects}


@router.delete("/{project_id}/inspections/{inspection_id}")
def delete_inspection(project_id: int, inspection_id: int, db: Session = Depends(get_db),
                      pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    with _pm_errors():
        _plan(db, pm, project).record(inspection_id, "inspection", "Inspection")
        pm.call("delete_record", record_id=inspection_id, actor=ACTOR)
        return {"deleted": inspection_id}


# --- punch list ------------------------------------------------------------
# Punch items stay in this database (they belong to rooms of the floor plan);
# each is copied one way to pm-mcp so agents and other apps see it.

class PunchItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    room: Optional[str] = Field(None, max_length=100)
    trade: str = "general"
    priority: str = "medium"
    status: str = "open"
    assignee: Optional[str] = Field(None, max_length=255)
    due_date: Optional[date] = None
    phase_id: Optional[int] = None


class PunchItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    room: Optional[str] = Field(None, max_length=100)
    trade: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = Field(None, max_length=255)
    due_date: Optional[date] = None
    phase_id: Optional[int] = None


def _check_punch_fields(db: Session, pm: PMClient, project: Project, data: dict) -> None:
    try:
        controls.check(data.get("trade"), controls.PUNCH_TRADES, "trade")
        controls.check(data.get("priority"), controls.TASK_PRIORITIES, "priority")
        controls.check(data.get("status"), controls.PUNCH_STATUSES, "punch item status")
    except ControlsError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if data.get("phase_id") is not None:
        with _pm_errors():
            _plan(db, pm, project).phase(data["phase_id"])


def _sync_punch(db: Session, pm: PMClient, project: Project, item: PunchItem) -> None:
    """Copy the item to pm-mcp; a pm-mcp outage doesn't stop the punch list."""
    try:
        controls.sync_punch_item(pm, project, item)
        db.commit()
    except (PMError, PMUnavailable) as e:
        logger.warning(f"⚠️  Punch item {item.id} not copied to pm-mcp: {e}")


@router.get("/{project_id}/punch-list")
def get_punch_list(project_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    """Punch items (open first, most urgent first), their summary, the floor
    plan's rooms, the trades an item can be given and the plan's phases."""
    project = _project(db, project_id)
    return controls.punch_list(db, project, date.today(), controls.load_plan_or_empty(pm, project))


@router.post("/{project_id}/punch-items", status_code=201)
def create_punch_item(project_id: int, body: PunchItemCreate, db: Session = Depends(get_db),
                      pm: PMClient = Depends(get_pm)):
    project = _project(db, project_id)
    data = body.model_dump()
    _check_punch_fields(db, pm, project, data)
    status = data.pop("status")
    item = PunchItem(project_id=project.id, number=controls.next_punch_number(project), **data)
    controls.set_punch_status(item, status)
    db.add(item)
    _commit(db)
    _sync_punch(db, pm, project, item)
    return controls.serialize_punch_item(item, date.today(), controls.load_plan_or_empty(pm, project))


@router.patch("/{project_id}/punch-items/{item_id}")
def update_punch_item(project_id: int, item_id: int, body: PunchItemUpdate, db: Session = Depends(get_db),
                      pm: PMClient = Depends(get_pm)):
    """Edit an item or move it along (closing records when; reopening clears it)."""
    project = _project(db, project_id)
    item = _owned(db, PunchItem, item_id, project_id, "Punch item")
    data = body.model_dump(exclude_unset=True)
    _check_punch_fields(db, pm, project, data)
    if "status" in data:
        controls.set_punch_status(item, data.pop("status"))
    for field, value in data.items():
        setattr(item, field, value)
    _commit(db)
    _sync_punch(db, pm, project, item)
    return controls.serialize_punch_item(item, date.today(), controls.load_plan_or_empty(pm, project))


@router.delete("/{project_id}/punch-items/{item_id}")
def delete_punch_item(project_id: int, item_id: int, db: Session = Depends(get_db), pm: PMClient = Depends(get_pm)):
    item = _owned(db, PunchItem, item_id, project_id, "Punch item")
    record_id = item.pm_record_id
    db.delete(item)
    _commit(db)
    if record_id:
        try:
            pm.call("delete_record", record_id=record_id, actor=ACTOR)
        except (PMError, PMUnavailable):
            pass  # the pm-mcp copy is informational
    return {"deleted": item_id}
