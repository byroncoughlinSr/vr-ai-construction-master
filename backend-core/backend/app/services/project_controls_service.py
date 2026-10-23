"""Project controls: the schedule, budget and compliance figures the dashboard
shows for one project.

The construction plan lives in pm-mcp (``pm_client``): phases are pm-mcp
milestones, tasks are pm-mcp tasks, and permits, inspections, budget lines,
expenses and change orders are pm-mcp records. Each request loads the
project's plan once (``load_plan``, one ``export_project`` call) and the
figures below are worked out from it. What is tied to the 3D house stays in
this database: the punch list (rooms of the floor plan), materials, floor
plans; a punch item's ``phase_id`` is a pm-mcp milestone id.

Progress is *earned* with the 50/50 rule: a task earns half its weight when it
starts and the rest when it is completed, a task's weight being its planned
duration. Earned value uses each phase's budget; planned value needs planned
dates, so until the schedule is baselined there is no SPI.

The VR app's plan is sequential (phases in order, tasks in order within a
phase). Tasks it adds are chained with pm-mcp dependencies in that order, so
pm-mcp's scheduler lays them end to end; plans from pm-mcp templates keep
their own dependencies. Schedules here count calendar days (``workdays_only``
false on the pm-mcp project).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from ..models import Client, Project, PunchItem
from . import floor_plan_service
from .pm_client import ACTOR, SYSTEM, PMClient, PMError, PMUnavailable

logger = logging.getLogger(__name__)

TASK_STATUSES = ("pending", "in_progress", "completed", "blocked", "cancelled")
TASK_PRIORITIES = ("low", "medium", "high", "critical")
EXPENSE_CATEGORIES = ("labor", "materials", "equipment", "subcontract", "permits", "other")
EXPENSE_STATUSES = ("pending", "paid")
CHANGE_ORDER_STATUSES = ("draft", "submitted", "approved", "rejected", "void")
# pm-mcp's statuses, used as they are.
PERMIT_STATUSES = ("not_applied", "applied", "in_review", "corrections_required", "approved", "rejected", "expired")
PERMIT_TYPES = (
    "building", "grading", "demolition", "electrical", "plumbing", "mechanical", "fire",
    "right_of_way", "certificate_of_occupancy", "other",
)
INSPECTION_STATUSES = ("not_scheduled", "scheduled", "passed", "failed", "partial", "cancelled")
EQUIPMENT_STATUSES = ("available", "in_use", "maintenance", "out_of_service")
PUNCH_STATUSES = ("open", "in_progress", "ready", "closed")
PUNCH_TRADES = (
    "general", "carpentry", "drywall", "paint", "flooring", "tile", "cabinets", "electrical",
    "plumbing", "hvac", "roofing", "siding", "windows_doors", "landscaping", "cleaning",
)

# Translations between this app's words and pm-mcp's.
_TO_PM_STATUS = {"pending": "todo", "in_progress": "in_progress", "completed": "done",
                 "blocked": "blocked", "cancelled": "cancelled"}
_FROM_PM_STATUS = {"todo": "pending", "in_progress": "in_progress", "review": "in_progress",
                   "blocked": "blocked", "done": "completed", "cancelled": "cancelled"}
_TO_PM_PRIORITY = {"critical": "urgent"}
_FROM_PM_PRIORITY = {"urgent": "critical"}
_TO_PM_CATEGORY = {"materials": "material", "permits": "fee"}
_FROM_PM_CATEGORY = {"material": "materials", "fee": "permits", "contingency": "other"}
_TO_PM_PUNCH = {"ready": "ready_for_review"}
_FROM_PM_PUNCH = {"ready_for_review": "ready"}

# A phase with no tasks still takes time when the schedule is baselined.
DEFAULT_PHASE_DAYS = 7


class ControlsError(ValueError):
    """A request the controls can't carry out (bad status, unknown phase...)."""


class NotFound(ControlsError):
    """The phase, task or record isn't part of this project."""


# --- dates -----------------------------------------------------------------

def as_date(value: Any) -> Optional[date]:
    """The calendar date of a stored timestamp or ISO string. pm-mcp's UTC
    timestamps are read in local time, so 'today' means the same day here."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value.astimezone().date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return None


def at_midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=timezone.utc)


def iso(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None else None


def check(value: Optional[str], allowed: Iterable[str], what: str) -> None:
    if value is not None and value not in allowed:
        raise ControlsError(f"Unknown {what} '{value}' (expected one of: {', '.join(allowed)})")


# --- the plan --------------------------------------------------------------

@dataclass
class Plan:
    """One pm-mcp project as this app sees it, loaded once per request."""

    pm_project_id: Optional[int] = None
    details: dict = field(default_factory=dict)
    phases: list[dict] = field(default_factory=list)  # milestones in order, each with its "tasks"
    records: list[dict] = field(default_factory=list)
    available: bool = True

    @classmethod
    def from_export(cls, export: dict) -> "Plan":
        tasks_by_phase: dict[int, list[dict]] = {}
        for task in export["tasks"]:
            if task.get("milestone_id") is not None:
                tasks_by_phase.setdefault(task["milestone_id"], []).append(task)
        phases = []
        for order, m in enumerate(export["milestones"], start=1):
            phases.append({**m, "order": order, "tasks": sorted(tasks_by_phase.get(m["id"], []), key=lambda t: t["id"])})
        return cls(export["project"]["id"], export["project"].get("details") or {}, phases, export["records"])

    def phase(self, phase_id: int) -> dict:
        found = next((p for p in self.phases if p["id"] == phase_id), None)
        if found is None:
            raise NotFound("Phase not found")
        return found

    def task(self, task_id: int) -> tuple[dict, dict]:
        for p in self.phases:
            for t in p["tasks"]:
                if t["id"] == task_id:
                    return t, p
        raise NotFound("Task not found")

    def tasks(self) -> list[dict]:
        return [t for p in self.phases for t in p["tasks"]]

    def of_type(self, rtype: str) -> list[dict]:
        return [r for r in self.records if r["type"] == rtype]

    def record(self, record_id: int, rtype: str, what: str) -> dict:
        found = next((r for r in self.records if r["id"] == record_id and r["type"] == rtype), None)
        if found is None:
            raise NotFound(f"{what} not found")
        return found

    def expenses(self) -> list[dict]:
        return [r for r in self.of_type("budget_item") if r["data"].get("line") == "expense"]

    def budget_lines(self, phase_id: Optional[int] = None) -> list[dict]:
        lines = [r for r in self.of_type("budget_item") if r["data"].get("line") != "expense"]
        return lines if phase_id is None else [r for r in lines if r["milestone_id"] == phase_id]

    def phase_name(self, phase_id: Optional[int]) -> Optional[str]:
        return next((p["name"] for p in self.phases if p["id"] == phase_id), None)


def ensure_pm_project(db: Session, pm: PMClient, project: Project) -> int:
    """The pm-mcp project behind this one, created and linked on first use."""
    if project.pm_project_id:
        return project.pm_project_id
    details = {
        "site_address": project.address or None,
        "contract_value": project.budget,
        "start_date": iso(as_date(project.start_date)),
        "target_completion": iso(as_date(project.estimated_completion_date)),
        "workdays_only": False,
        "vr_project_id": project.id,
    }
    details = {k: v for k, v in details.items() if v is not None}
    try:
        created = pm.call("create_project", name=project.name, description=project.description or "",
                          details=details, actor=ACTOR)
    except PMError:
        # pm-mcp project names are unique across every app that uses it.
        created = pm.call("create_project", name=f"{project.name} (VR #{project.id})",
                          description=project.description or "", details=details, actor=ACTOR)
    try:
        pm.call("link_external", entity_type="project", entity_id=created["id"], system=SYSTEM,
                external_id=str(project.id), actor=ACTOR)
    except PMError as e:
        # pm_project_id is what this app relies on; the link is for other apps. It is
        # taken when pm-mcp outlived an earlier database whose ids started over.
        logger.warning(f"⚠️  pm-mcp project {created['id']} not linked to VR project {project.id}: {e}")
    project.pm_project_id = created["id"]
    db.commit()
    return created["id"]


def load_plan(pm: PMClient, project: Project) -> Plan:
    if not project.pm_project_id:
        return Plan()
    return Plan.from_export(pm.call("export_project", project_id=project.pm_project_id))


# --- schedule --------------------------------------------------------------

def task_days(task: dict) -> float:
    days = task.get("duration_days")
    return float(days) if days and days > 0 else 1.0


def _counted(tasks: list[dict]) -> list[dict]:
    return [t for t in tasks if t["status"] != "cancelled"]


def _earned_fraction(task: dict) -> float:
    if task["status"] == "done":
        return 1.0
    if task["status"] in ("in_progress", "review"):
        return 0.5
    return 0.0


def phase_progress(phase: dict) -> float:
    """Percent complete, earned from the phase's tasks (50/50 rule, weighted by
    duration); a phase without tasks keeps the progress entered for it."""
    tasks = _counted(phase["tasks"])
    if not tasks:
        return float(phase["details"].get("progress") or 0.0)
    weight = sum(task_days(t) for t in tasks)
    return round(100.0 * sum(task_days(t) * _earned_fraction(t) for t in tasks) / weight, 1)


def _task_end(task: dict) -> Optional[date]:
    """End of the planned span, exclusive: pm-mcp's finish is the last working day."""
    finish = as_date(task.get("planned_finish"))
    if finish is None:
        return None
    return finish + timedelta(days=1) if task.get("duration_days") != 0 else finish


def phase_dates(phase: dict) -> tuple[Optional[date], Optional[date]]:
    """Dates set on the phase itself win; otherwise its tasks' span."""
    d = phase["details"]
    if d.get("planned_start") or d.get("planned_end"):
        return as_date(d.get("planned_start")), as_date(d.get("planned_end"))
    starts = [as_date(t.get("planned_start")) for t in phase["tasks"] if t.get("planned_start")]
    ends = [_task_end(t) for t in phase["tasks"] if t.get("planned_finish")]
    return (min(starts) if starts else None), (max(ends) if ends else None)


def phase_days(phase: dict) -> float:
    tasks = _counted(phase["tasks"])
    if tasks:
        return sum(task_days(t) for t in tasks)
    start, end = phase_dates(phase)
    if start and end and end > start:
        return float((end - start).days)
    return float(DEFAULT_PHASE_DAYS)


def phase_status(phase: dict) -> str:
    tasks = _counted(phase["tasks"])
    if not tasks:
        progress = phase_progress(phase)
        return "completed" if progress >= 100 else "in_progress" if progress > 0 else "pending"
    if all(t["status"] == "done" for t in tasks):
        return "completed"
    if any(t["status"] in ("in_progress", "review", "done") for t in tasks):
        return "in_progress"
    return "pending"


def _planned_fraction(start: Optional[date], end: Optional[date], today: date) -> Optional[float]:
    """How much of [start, end] has passed by ``today`` (0..1); None when unplanned."""
    if not start or not end:
        return None
    if today <= start:
        return 0.0
    if today >= end:
        return 1.0
    return (today - start).days / max((end - start).days, 1)


def _is_late(planned_end: Optional[date], done: bool, today: date) -> bool:
    return bool(planned_end and planned_end < today and not done)


def serialize_task(task: dict, phase: dict, today: date) -> dict:
    done = task["status"] == "done"
    return {
        "id": task["id"],
        "phase_id": phase["id"],
        "name": task["title"],
        "description": task.get("description") or None,
        "status": _FROM_PM_STATUS.get(task["status"], task["status"]),
        "priority": _FROM_PM_PRIORITY.get(task["priority"], task["priority"]),
        "task_order": next(i for i, t in enumerate(phase["tasks"], start=1) if t["id"] == task["id"]),
        "duration_days": task_days(task),
        "planned_start": iso(as_date(task.get("planned_start"))),
        "planned_end": iso(_task_end(task)),
        "actual_start": iso(as_date(task.get("started_at"))),
        "actual_end": iso(as_date(task.get("completed_at"))) if done else None,
        "budgeted_cost": task.get("budgeted_cost") or 0.0,
        "actual_cost": task.get("actual_cost") or 0.0,
        "requires_inspection": task.get("kind") == "inspection",
        "kind": task.get("kind", "task"),
        "roles": task.get("tags") or [],
        "assignee": task.get("assignee"),
        "late": _is_late(_task_end(task), done or task["status"] == "cancelled", today),
    }


def phase_budget(plan: Plan, phase: dict) -> float:
    return sum(r["data"].get("budgeted", 0.0) for r in plan.budget_lines(phase["id"]))


def _actual_by_phase(plan: Plan) -> dict[int, float]:
    totals: dict[int, float] = {}
    for r in plan.of_type("budget_item"):
        if r["milestone_id"]:
            totals[r["milestone_id"]] = totals.get(r["milestone_id"], 0.0) + r["data"].get("actual", 0.0)
    return totals


def serialize_phase(plan: Plan, phase: dict, today: date) -> dict:
    progress = phase_progress(phase)
    start, end = phase_dates(phase)
    tasks = _counted(phase["tasks"])
    started = [as_date(t.get("started_at")) for t in tasks if t.get("started_at")]
    finished = [as_date(t.get("completed_at")) for t in tasks if t.get("completed_at")]
    status = phase_status(phase)
    return {
        "id": phase["id"],
        "name": phase["name"],
        "description": phase.get("description") or None,
        "phase_order": phase["order"],
        "status": status,
        "progress": progress,
        "duration_days": phase_days(phase),
        "planned_start": iso(start),
        "planned_end": iso(end),
        "actual_start": iso(min(started)) if started else None,
        "actual_end": iso(max(finished)) if status == "completed" and finished else None,
        "budgeted_cost": phase_budget(plan, phase),
        "actual_cost": round(_actual_by_phase(plan).get(phase["id"], 0.0), 2),
        "late": _is_late(end, progress >= 100, today),
        "tasks": [serialize_task(t, phase, today) for t in phase["tasks"]],
    }


def schedule_summary(plan: Plan, today: date) -> dict:
    phases = plan.phases
    tasks = _counted(plan.tasks())
    total_days = sum(phase_days(p) for p in phases)
    progress = (
        round(sum(phase_days(p) * phase_progress(p) for p in phases) / total_days, 1)
        if total_days else 0.0
    )
    spans = [phase_dates(p) for p in phases]
    starts = [s for s, _ in spans if s]
    ends = [e for _, e in spans if e]
    current = next((p for p in phases if phase_progress(p) < 100), None)
    return {
        "progress": progress,
        "baselined": bool(starts and ends),
        "planned_start": iso(min(starts)) if starts else None,
        "planned_finish": iso(max(ends)) if ends else None,
        "total_days": total_days,
        "phase_count": len(phases),
        "current_phase": {"id": current["id"], "name": current["name"]} if current else None,
        "tasks": {
            "total": len(tasks),
            "completed": sum(t["status"] == "done" for t in tasks),
            "in_progress": sum(t["status"] in ("in_progress", "review") for t in tasks),
            "blocked": sum(t["status"] == "blocked" for t in tasks),
            "late": sum(_is_late(_task_end(t), t["status"] == "done", today) for t in tasks),
        },
    }


def schedule(plan: Plan, project: Project, today: date) -> dict:
    return {
        "project_id": project.id,
        "pm_project_id": plan.pm_project_id,
        "pm_available": plan.available,
        **schedule_summary(plan, today),
        "phases": [serialize_phase(plan, p, today) for p in plan.phases],
    }


def baseline_schedule(pm: PMClient, plan: Plan, project: Project, start: date) -> None:
    """Plan every task from ``start`` along its dependencies (calendar days) and
    store the dates on the tasks. Phases without tasks get DEFAULT_PHASE_DAYS
    after the phase before them. Overwrites planned dates."""
    pm.call("update_project", project_id=plan.pm_project_id, details={"start_date": start.isoformat(),
                                                                      "workdays_only": False}, actor=ACTOR)
    finish = start
    if plan.tasks():
        result = pm.call("compute_schedule", project_id=plan.pm_project_id, mode="plan", save=True,
                         start_date=start.isoformat())
        finish = as_date(result["finish_date"]) + timedelta(days=1)
    plan = load_plan(pm, project)
    cursor = start
    for phase in plan.phases:
        if _counted(phase["tasks"]):
            pm.call("update_milestone", milestone_id=phase["id"],
                    details={"planned_start": None, "planned_end": None}, actor=ACTOR)
            phase["details"] = {}
            cursor = phase_dates(phase)[1] or cursor
        else:
            end = cursor + timedelta(days=DEFAULT_PHASE_DAYS)
            pm.call("update_milestone", milestone_id=phase["id"],
                    details={"planned_start": cursor.isoformat(), "planned_end": end.isoformat()}, actor=ACTOR)
            cursor = end
    project.start_date = at_midnight(start)
    project.estimated_completion_date = at_midnight(max(finish, cursor))


def _chain_predecessor(plan: Plan, phase: dict) -> Optional[int]:
    """The task a new task appended to ``phase`` should follow: the phase's last
    task, or the last task of the nearest earlier phase that has any."""
    for p in reversed(plan.phases[: phase["order"]]):
        tasks = _counted(p["tasks"])
        if tasks:
            return tasks[-1]["id"]
    return None


def create_phase(pm: PMClient, plan: Plan, data: dict) -> int:
    milestone = pm.call("create_milestone", project_id=plan.pm_project_id, name=data["name"],
                        description=data.get("description") or "", actor=ACTOR)
    if data.get("budgeted_cost"):
        _set_phase_budget(pm, plan, {"id": milestone["id"], "name": data["name"]}, data["budgeted_cost"])
    return milestone["id"]


def _set_phase_budget(pm: PMClient, plan: Plan, phase: dict, total: float) -> None:
    """Make the phase's budget add up to ``total``: its own line covers what
    the itemised lines (from estimators) don't."""
    lines = plan.budget_lines(phase["id"])
    own = next((r for r in lines if r["data"].get("line") == "phase_budget"), None)
    itemised = sum(r["data"].get("budgeted", 0.0) for r in lines if r is not own)
    if total < itemised:
        raise ControlsError(f"Phase has ${itemised:,.2f} in itemised budget lines; its budget can't be lower")
    if own:
        pm.call("update_record", record_id=own["id"], data={"budgeted": total - itemised}, actor=ACTOR)
    else:
        pm.call("create_record", project_id=plan.pm_project_id, record_type="budget_item",
                title=f"{phase['name']} budget", milestone_id=phase["id"], actor=ACTOR,
                data={"cost_code": phase["name"], "category": "other", "budgeted": total - itemised,
                      "line": "phase_budget"})


def update_phase(pm: PMClient, plan: Plan, phase: dict, data: dict) -> None:
    details = {}
    for key in ("planned_start_date", "planned_end_date"):
        if key in data:
            details[key.replace("_date", "")] = iso(data[key])
    if "progress_percentage" in data:
        details["progress"] = data["progress_percentage"]
    if any(k in data for k in ("name", "description")) or details:
        pm.call("update_milestone", milestone_id=phase["id"], name=data.get("name"),
                description=data.get("description"), details=details or None, actor=ACTOR)
    if data.get("budgeted_cost") is not None:
        _set_phase_budget(pm, plan, phase, data["budgeted_cost"])


def _task_fields(data: dict) -> dict:
    fields = {
        "title": data.get("name"),
        "description": data.get("description"),
        "priority": _TO_PM_PRIORITY.get(data.get("priority"), data.get("priority")),
        "duration_days": data.get("planned_duration_days"),
        "budgeted_cost": data.get("budgeted_cost"),
        "actual_cost": data.get("actual_cost"),
    }
    if "planned_start_date" in data:
        fields["planned_start"] = iso(data["planned_start_date"]) or ""
    if "planned_end_date" in data:
        end = data["planned_end_date"]
        fields["planned_finish"] = iso(end - timedelta(days=1)) if end else ""
    return fields


def create_task(pm: PMClient, plan: Plan, phase: dict, data: dict) -> int:
    check(data.get("priority"), TASK_PRIORITIES, "priority")
    predecessor = _chain_predecessor(plan, phase)
    fields = {k: v for k, v in _task_fields(data).items() if v not in (None, "")}
    task = pm.call("create_task", project_id=plan.pm_project_id, milestone_id=phase["id"],
                   depends_on=[predecessor] if predecessor else None,
                   kind="inspection" if data.get("requires_inspection") else "task", actor=ACTOR,
                   **{k: v for k, v in fields.items() if k not in ("planned_start", "planned_finish")})
    if fields.get("planned_start") or fields.get("planned_finish"):
        pm.call("update_task", task_id=task["id"], planned_start=fields.get("planned_start"),
                planned_finish=fields.get("planned_finish"), actor=ACTOR)
    if data.get("requires_inspection"):
        _ensure_inspection(pm, plan, task["id"], task["title"], phase["id"])
    # Later phases' first tasks that followed the old predecessor now follow this task too.
    if predecessor:
        for later in plan.phases[phase["order"]:]:
            first = next(iter(_counted(later["tasks"])), None)
            if first and predecessor in first.get("depends_on", []):
                pm.call("add_dependency", task_id=first["id"], depends_on_id=task["id"], actor=ACTOR)
    return task["id"]


def _ensure_inspection(pm: PMClient, plan: Plan, task_id: int, title: str, phase_id: int) -> None:
    if not any(r["task_id"] == task_id for r in plan.of_type("inspection")):
        pm.call("create_record", project_id=plan.pm_project_id, record_type="inspection", title=title,
                task_id=task_id, milestone_id=phase_id, data={"inspection_type": title}, actor=ACTOR)


def update_task(pm: PMClient, plan: Plan, task: dict, phase: dict, data: dict) -> None:
    """Change a task. A status change goes through pm-mcp, which records when
    work started and finished and refuses to finish an inspection gate whose
    inspection hasn't passed."""
    check(data.get("priority"), TASK_PRIORITIES, "priority")
    check(data.get("status"), TASK_STATUSES, "task status")
    fields = _task_fields(data)
    if "status" in data:
        fields["status"] = _TO_PM_STATUS[data["status"]]
    if "requires_inspection" in data and data["requires_inspection"] is not None:
        fields["kind"] = "inspection" if data["requires_inspection"] else "task"
        if data["requires_inspection"]:
            _ensure_inspection(pm, plan, task["id"], data.get("name") or task["title"], phase["id"])
    fields = {k: v for k, v in fields.items() if v is not None}
    if fields:
        pm.call("update_task", task_id=task["id"], actor=ACTOR, **fields)


def delete_task(pm: PMClient, plan: Plan, task: dict) -> None:
    """Delete a task, keeping the chain: whatever waited on it now waits on
    what it waited on."""
    for other in plan.tasks():
        if task["id"] in other.get("depends_on", []):
            for dep in task.get("depends_on", []):
                if dep not in other["depends_on"]:
                    pm.call("add_dependency", task_id=other["id"], depends_on_id=dep, actor=ACTOR)
    pm.call("delete_task", task_id=task["id"], actor=ACTOR)


def import_ai_phases(pm: PMClient, plan: Plan, phases: list[dict]) -> None:
    """Load the AI planner's phases and tasks into pm-mcp, in order."""
    previous: Optional[int] = None
    for idx, phase_data in enumerate(phases or []):
        name = phase_data.get("name") or f"Phase {idx + 1}"
        milestone = pm.call("create_milestone", project_id=plan.pm_project_id, name=name,
                            description=phase_data.get("description") or "", actor=ACTOR)
        if phase_data.get("estimated_cost"):
            pm.call("create_record", project_id=plan.pm_project_id, record_type="budget_item",
                    title=f"{name} budget", milestone_id=milestone["id"], actor=ACTOR,
                    data={"cost_code": name, "category": "other", "budgeted": float(phase_data["estimated_cost"]),
                          "line": "phase_budget"})
        for task_idx, task_data in enumerate(phase_data.get("tasks") or []):
            task = pm.call("create_task", project_id=plan.pm_project_id, milestone_id=milestone["id"],
                           title=task_data.get("name") or f"Task {task_idx + 1}",
                           description=task_data.get("description") or "",
                           duration_days=float(task_data.get("duration_days") or 1),
                           budgeted_cost=float(task_data.get("estimated_cost") or 0),
                           depends_on=[previous] if previous else None, actor=ACTOR)
            previous = task["id"]


# --- budget ----------------------------------------------------------------

def add_expense(pm: PMClient, plan: Plan, data: dict) -> dict:
    """Log a cost against the project: a pm-mcp budget line whose actual is the amount."""
    check(data.get("status"), EXPENSE_STATUSES, "expense status")
    category = data.get("category") or "other"
    check(category, EXPENSE_CATEGORIES, "expense category")
    if data.get("phase_id"):
        plan.phase(data["phase_id"])
    incurred = data.get("incurred_on") or date.today()
    return pm.call(
        "create_record", project_id=plan.pm_project_id, record_type="budget_item", title=data["vendor"],
        status="paid" if (data.get("status") or "paid") == "paid" else "invoiced",
        milestone_id=data.get("phase_id"), actor=ACTOR,
        data={"cost_code": category, "category": _TO_PM_CATEGORY.get(category, category),
              "budgeted": 0.0, "actual": float(data["amount"]), "vendor": data["vendor"], "line": "expense",
              "description": data.get("description"), "invoice_number": data.get("invoice_number"),
              "incurred_on": iso(incurred)},
    )


def serialize_expense(plan: Plan, record: dict) -> dict:
    d = record["data"]
    return {
        "id": record["id"],
        "vendor": d.get("vendor") or record["title"],
        "description": d.get("description"),
        "category": d.get("cost_code") if d.get("cost_code") in EXPENSE_CATEGORIES
        else _FROM_PM_CATEGORY.get(d.get("category"), d.get("category", "other")),
        "amount": d.get("actual", 0.0),
        "status": "paid" if record["status"] == "paid" else "pending",
        "date": d.get("incurred_on"),
        "invoice_number": d.get("invoice_number"),
        "phase_id": record["milestone_id"],
        "phase_name": plan.phase_name(record["milestone_id"]),
        "created_at": record["created_at"],
    }


def serialize_change_order(project: Project, record: dict) -> dict:
    d = record["data"]
    return {
        "id": record["id"],
        "project_id": project.id,
        "number": record["number"],
        "code": f"CO-{record['number']:03d}",
        "title": record["title"],
        "description": d.get("description") or None,
        "cost_impact": d.get("cost_impact", 0.0),
        "schedule_impact_days": d.get("schedule_impact_days", 0),
        "status": record["status"],
        "requested_by": d.get("requested_by"),
        "floor_plan_version": d.get("floor_plan_version"),
        "decided_at": d.get("decided_at"),
        "created_at": record["created_at"],
    }


def change_order_fields(data: dict, status_changed: bool) -> dict:
    fields = {k: data[k] for k in ("description", "requested_by", "floor_plan_version") if k in data}
    if data.get("cost_impact") is not None:
        fields["cost_impact"] = float(data["cost_impact"])
    if data.get("schedule_impact_days") is not None:
        fields["schedule_impact_days"] = int(round(data["schedule_impact_days"]))
    if status_changed:
        fields["decided_at"] = (datetime.now().astimezone().isoformat()
                                if data.get("status") in ("approved", "rejected") else None)
    return fields


def _ratio(numerator: float, denominator: Optional[float]) -> Optional[float]:
    return round(numerator / denominator, 2) if denominator else None


def budget_summary(plan: Plan, project: Project, today: date) -> dict:
    """Earned value figures for the project.

    BAC = the phases' budgets (or the plan's estimate when there are none) plus
    approved change orders. EV = each phase's budget times its earned progress.
    AC = every actual cost in pm-mcp's budget lines (logged expenses and any
    actuals on estimator lines). PV only once the schedule has planned dates.
    """
    phases = plan.phases
    budgets = {p["id"]: phase_budget(plan, p) for p in phases}
    lines_budget = sum(r["data"].get("budgeted", 0.0) for r in plan.budget_lines())
    baseline = lines_budget if lines_budget > 0 else float(project.estimated_cost or 0.0)
    cos = plan.of_type("change_order")
    approved = sum(r["data"].get("cost_impact", 0.0) for r in cos if r["status"] == "approved")
    pending = sum(r["data"].get("cost_impact", 0.0) for r in cos if r["status"] == "submitted")
    bac = baseline + approved
    phase_total = sum(budgets.values())

    if phase_total > 0:
        ev = sum(budgets[p["id"]] * phase_progress(p) / 100 for p in phases)
    else:
        ev = baseline * schedule_summary(plan, today)["progress"] / 100

    fractions = [_planned_fraction(*phase_dates(p), today) for p in phases]
    if phases and all(f is not None for f in fractions):
        if phase_total > 0:
            pv: Optional[float] = sum(budgets[p["id"]] * f for p, f in zip(phases, fractions))
        else:
            days = [phase_days(p) for p in phases]
            pv = baseline * sum(d * f for d, f in zip(days, fractions)) / (sum(days) or 1)
    else:
        pv = None

    items = plan.of_type("budget_item")
    ac = sum(r["data"].get("actual", 0.0) for r in items)
    unpaid = sum(r["data"].get("actual", 0.0) for r in plan.expenses() if r["status"] != "paid")
    cpi = _ratio(ev, ac)
    spi = _ratio(ev, pv)
    eac = round(bac / cpi, 2) if cpi else bac

    actual_by_phase = _actual_by_phase(plan)
    by_category: dict[str, float] = {}
    for r in items:
        if r["data"].get("actual"):
            kind = serialize_expense(plan, r)["category"]
            by_category[kind] = by_category.get(kind, 0.0) + r["data"]["actual"]

    return {
        "target_budget": project.budget,
        "baseline": round(baseline, 2),
        "approved_change_orders": round(approved, 2),
        "pending_change_orders": round(pending, 2),
        "bac": round(bac, 2),
        "planned_value": round(pv, 2) if pv is not None else None,
        "earned_value": round(ev, 2),
        "actual_cost": round(ac, 2),
        "unpaid": round(unpaid, 2),
        "cost_variance": round(ev - ac, 2),
        "schedule_variance": round(ev - pv, 2) if pv is not None else None,
        "cpi": cpi,
        "spi": spi,
        "eac": round(eac, 2),
        "etc": round(max(eac - ac, 0.0), 2),
        "vac": round(bac - eac, 2),
        "percent_spent": round(100 * ac / bac, 1) if bac else 0.0,
        "materials_cost": round(sum((m.quantity_needed or 0) * (m.unit_cost or 0) for m in project.materials or []), 2),
        "by_phase": [
            {
                "phase_id": p["id"],
                "name": p["name"],
                "budgeted": budgets[p["id"]],
                "earned": round(budgets[p["id"]] * phase_progress(p) / 100, 2),
                "actual": round(actual_by_phase.get(p["id"], 0.0), 2),
            }
            for p in phases
        ],
        "by_category": [{"category": k, "actual": round(v, 2)} for k, v in sorted(by_category.items())],
    }


# --- compliance ------------------------------------------------------------

def permit_fields(data: dict) -> tuple[dict, Optional[str]]:
    """pm-mcp record data for this app's permit fields, and the title."""
    out: dict = {}
    if data.get("permit_type") is not None:
        kind = data["permit_type"].strip().lower().replace(" ", "_").replace("-", "_")
        out["permit_type"] = kind if kind in PERMIT_TYPES else "other"
        out["type_label"] = data["permit_type"]
    mapping = {"permit_number": "permit_number", "jurisdiction": "authority", "application_date": "applied_date",
               "issued_date": "approved_date", "expiration_date": "expires_date", "permit_fee": "fee",
               "description": "description", "conditions": "conditions", "contact_name": "contact_name",
               "contact_phone": "contact_phone", "contact_email": "contact_email"}
    for key, target in mapping.items():
        if key in data:
            value = data[key]
            out[target] = iso(value) if isinstance(value, date) else value
    title = None
    if data.get("permit_type") or data.get("permit_number"):
        title = " ".join(filter(None, [data.get("permit_type"), "permit", data.get("permit_number")])).strip()
    return out, title


def serialize_permit(project: Project, record: dict) -> dict:
    d = record["data"]
    return {
        "id": record["id"],
        "project_id": project.id,
        "title": record["title"],
        "permit_number": d.get("permit_number"),
        "permit_type": d.get("type_label") or d.get("permit_type", "other").replace("_", " ").title(),
        "description": d.get("description"),
        "jurisdiction": d.get("authority"),
        "status": record["status"],
        "application_date": d.get("applied_date"),
        "issued_date": d.get("approved_date"),
        "expiration_date": d.get("expires_date"),
        "permit_fee": d.get("fee") or 0.0,
        "conditions": d.get("conditions"),
        "contact_name": d.get("contact_name"),
        "contact_phone": d.get("contact_phone"),
        "contact_email": d.get("contact_email"),
        "task_id": record["task_id"],
    }


def inspection_fields(data: dict) -> dict:
    out: dict = {}
    mapping = {"inspection_type": "inspection_type", "description": "description", "permit_id": "permit_id",
               "inspector_name": "inspector", "result_details": "result_notes",
               "critical_findings": "critical_findings", "requires_followup": "requires_followup",
               "followup_completed": "followup_completed"}
    for key, target in mapping.items():
        if key in data:
            out[target] = data[key]
    if "scheduled_date" in data:
        when = data["scheduled_date"]
        out["scheduled_at"] = when.isoformat() if when else None
        out["scheduled_date"] = iso(as_date(when)) if when else None
    return out


def serialize_inspection(project: Project, plan: Plan, record: dict) -> dict:
    d = record["data"]
    permit = next((r for r in plan.of_type("permit") if r["id"] == d.get("permit_id")), None)
    attempts = d.get("attempts") or []
    return {
        "id": record["id"],
        "project_id": project.id,
        "title": record["title"],
        "permit_id": d.get("permit_id"),
        "permit_number": permit["data"].get("permit_number") if permit else None,
        "task_id": record["task_id"],
        "inspection_type": d.get("inspection_type"),
        "description": d.get("description"),
        "inspector_name": d.get("inspector"),
        "scheduled_date": d.get("scheduled_at") or d.get("scheduled_date"),
        "actual_date": d.get("actual_at") or (attempts[-1]["date"] if attempts else None),
        "status": record["status"],
        "result_details": d.get("result_notes"),
        "critical_findings": d.get("critical_findings"),
        "requires_followup": bool(d.get("requires_followup")),
        "attempts": attempts,
    }


def compliance_summary(plan: Plan, today: date) -> dict:
    permits = plan.of_type("permit")
    inspections = plan.of_type("inspection")
    decided = [r for r in inspections if r["status"] in ("passed", "failed", "partial")]
    return {
        "permits_total": len(permits),
        "permits_active": sum(r["status"] == "approved" for r in permits),
        "inspections_upcoming": sum(
            r["status"] == "scheduled" and (as_date(r["data"].get("scheduled_date")) or today) >= today
            for r in inspections
        ),
        "inspections_passed": sum(r["status"] == "passed" for r in inspections),
        "inspections_failed": sum(r["status"] in ("failed", "partial") for r in inspections),
        "pass_rate": round(100 * sum(r["status"] == "passed" for r in decided) / len(decided)) if decided else None,
    }


def sorted_inspections(plan: Plan) -> list[dict]:
    return sorted(plan.of_type("inspection"), key=lambda r: (
        r["data"].get("scheduled_date") is None, r["data"].get("scheduled_at") or r["data"].get("scheduled_date") or "",
        r["id"]))


# --- punch list ------------------------------------------------------------

def next_punch_number(project: Project) -> int:
    return max((p.number for p in project.punch_items or []), default=0) + 1


def set_punch_status(item: PunchItem, status: str) -> None:
    """Move an item along open → in_progress → ready → closed; closing records
    when, reopening clears it."""
    check(status, PUNCH_STATUSES, "punch item status")
    item.status = status
    if status == "closed":
        if not item.closed_at:
            item.closed_at = datetime.now().astimezone()
    else:
        item.closed_at = None


def _punch_overdue(item: PunchItem, today: date) -> bool:
    return _is_late(as_date(item.due_date), item.status == "closed", today)


def serialize_punch_item(item: PunchItem, today: date, plan: Optional[Plan] = None) -> dict:
    return {
        "id": item.id,
        "project_id": item.project_id,
        "number": item.number,
        "code": f"PL-{item.number:03d}",
        "title": item.title,
        "description": item.description,
        "room": item.room,
        "trade": item.trade or "general",
        "priority": item.priority or "medium",
        "status": item.status or "open",
        "assignee": item.assignee,
        "due_date": iso(as_date(item.due_date)),
        "phase_id": item.phase_id,
        "phase_name": plan.phase_name(item.phase_id) if plan and item.phase_id else None,
        "overdue": _punch_overdue(item, today),
        "closed_at": iso(item.closed_at),
        "created_at": iso(item.created_at),
    }


def punch_summary(project: Project, today: date) -> dict:
    items = project.punch_items or []
    open_items = [i for i in items if i.status != "closed"]
    by_room: dict[str, int] = {}
    for item in open_items:
        room = item.room or "Unassigned"
        by_room[room] = by_room.get(room, 0) + 1
    return {
        "total": len(items),
        "open": sum(i.status == "open" for i in items),
        "in_progress": sum(i.status == "in_progress" for i in items),
        "ready": sum(i.status == "ready" for i in items),
        "closed": sum(i.status == "closed" for i in items),
        "overdue": sum(_punch_overdue(i, today) for i in items),
        "high_priority_open": sum(i.priority in ("high", "critical") for i in open_items),
        "percent_closed": round(100 * (len(items) - len(open_items)) / len(items), 1) if items else None,
        "open_by_room": [{"room": k, "open": v} for k, v in sorted(by_room.items(), key=lambda kv: (-kv[1], kv[0]))],
    }


def punch_list(db: Session, project: Project, today: date, plan: Optional[Plan] = None) -> dict:
    """Open items first (critical, then soonest due), closed ones last; the
    floor plan's rooms are what the dashboard offers as locations."""
    rank = {p: n for n, p in enumerate(reversed(TASK_PRIORITIES))}
    items = sorted(
        project.punch_items or [],
        key=lambda i: (
            i.status == "closed", rank.get(i.priority or "medium", 9),
            i.due_date is None, as_date(i.due_date) or date.max, i.number,
        ),
    )
    floor_plan = floor_plan_brief(db, project)
    return {
        "summary": punch_summary(project, today),
        "rooms": [r for r in (floor_plan or {}).get("rooms", []) if r],
        "trades": list(PUNCH_TRADES),
        "phases": [{"id": p["id"], "name": p["name"]} for p in (plan.phases if plan else [])],
        "items": [serialize_punch_item(i, today, plan) for i in items],
    }


def sync_punch_item(pm: PMClient, project: Project, item: PunchItem) -> None:
    """Copy a punch item to pm-mcp (one way: this app owns punch items) so
    agents and other apps see it. Best effort; the caller commits."""
    if not project.pm_project_id:
        return
    data = {"location": item.room, "description": item.description or item.title, "trade": item.trade,
            "assigned_to": item.assignee, "priority": item.priority, "vr_code": f"PL-{item.number:03d}"}
    status = _TO_PM_PUNCH.get(item.status, item.status)
    due = iso(as_date(item.due_date)) or ""
    if item.pm_record_id:
        pm.call("update_record", record_id=item.pm_record_id, title=item.title, status=status, data=data,
                due_date=due or None, milestone_id=item.phase_id or 0, actor=ACTOR)
    else:
        record = pm.call("create_record", project_id=project.pm_project_id, record_type="punch_item",
                         title=item.title, status=status, data=data, due_date=due or None,
                         milestone_id=item.phase_id, actor=ACTOR)
        item.pm_record_id = record["id"]
        try:
            pm.call("link_external", entity_type="record", entity_id=record["id"], system=SYSTEM,
                    external_id=f"punch_item:{item.id}", actor=ACTOR)
        except PMError as e:
            logger.warning(f"⚠️  pm-mcp record {record['id']} not linked to punch item {item.id}: {e}")


# --- resources -------------------------------------------------------------

def serialize_crew(member) -> dict:
    return {
        "id": member.id,
        "name": member.name,
        "role": member.role,
        "email": member.email,
        "phone": member.phone,
        "hourly_rate": member.hourly_rate or 0.0,
        "max_hours_per_week": member.max_hours_per_week or 0.0,
        "is_available": bool(member.is_available),
        "project_id": member.current_project_id,
        "project_name": member.current_project.name if member.current_project else None,
    }


def serialize_equipment(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "equipment_type": item.equipment_type,
        "model": item.model,
        "serial_number": item.serial_number,
        "owned": bool(item.owned_by_company),
        "rental_company": item.rental_company,
        "daily_rate": item.rental_rate_daily or 0.0,
        "status": item.status or "available",
        "next_maintenance_date": iso(as_date(item.next_maintenance_date)),
        "location": item.current_location,
        "project_id": item.assigned_to_project_id,
        "project_name": item.assigned_project.name if item.assigned_project else None,
    }


# --- overview --------------------------------------------------------------

def attention(plan: Plan, project: Project, today: date) -> list[dict]:
    """What needs the project manager now, most pressing first."""
    items: list[dict] = []
    if not plan.available:
        items.append({"kind": "pm_unavailable", "severity": "high",
                      "title": "Construction plan service (pm-mcp) is not running",
                      "detail": "Schedule, budget and permits can't be shown until it is started.",
                      "route": "/timeline"})
    for phase in plan.phases:
        for task in phase["tasks"]:
            if task["status"] == "blocked":
                items.append({"kind": "task_blocked", "severity": "high", "title": f"Blocked: {task['title']}",
                              "detail": phase["name"], "route": "/timeline"})
            elif _is_late(_task_end(task), task["status"] in ("done", "cancelled"), today):
                items.append({"kind": "task_late", "severity": "high", "title": f"Late: {task['title']}",
                              "detail": f"Planned to finish {iso(_task_end(task))}", "route": "/timeline"})
    for r in plan.of_type("inspection"):
        day = as_date(r["data"].get("scheduled_date"))
        if r["status"] in ("failed", "partial") and not r["data"].get("followup_completed"):
            items.append({"kind": "inspection_failed", "severity": "high",
                          "title": f"Failed inspection: {r['data'].get('inspection_type') or r['title']}",
                          "detail": r["data"].get("critical_findings") or r["data"].get("result_notes") or "",
                          "route": "/compliance"})
        elif r["status"] == "scheduled" and day and today <= day <= today + timedelta(days=7):
            items.append({"kind": "inspection_soon", "severity": "medium",
                          "title": f"Inspection {iso(day)}: {r['data'].get('inspection_type') or r['title']}",
                          "detail": r["data"].get("inspector") or "", "route": "/compliance"})
    for r in plan.of_type("permit"):
        expires = as_date(r["data"].get("expires_date"))
        if r["status"] == "approved" and expires and expires <= today + timedelta(days=30):
            label = r["data"].get("permit_number") or r["title"]
            items.append({"kind": "permit_expiring", "severity": "medium" if expires >= today else "high",
                          "title": f"Permit {label} expires {iso(expires)}",
                          "detail": r["data"].get("type_label") or r["data"].get("permit_type", ""),
                          "route": "/compliance"})
    for r in plan.of_type("change_order"):
        if r["status"] == "submitted":
            items.append({"kind": "change_order_pending", "severity": "medium",
                          "title": f"CO-{r['number']:03d} awaiting approval: {r['title']}",
                          "detail": f"${r['data'].get('cost_impact', 0):,.0f}", "route": "/budget"})
    # A punch list runs to dozens of items: one line each for what is overdue
    # and what waits for sign-off, not one per item.
    punch = project.punch_items or []
    overdue = [p for p in punch if _punch_overdue(p, today)]
    if overdue:
        first = min(overdue, key=lambda p: (as_date(p.due_date), p.number))
        items.append({"kind": "punch_overdue", "severity": "high",
                      "title": f"{len(overdue)} punch item{'s' if len(overdue) != 1 else ''} overdue",
                      "detail": f"PL-{first.number:03d} {first.title}", "route": "/punch-list"})
    ready = [p for p in punch if p.status == "ready"]
    if ready:
        items.append({"kind": "punch_ready", "severity": "medium",
                      "title": f"{len(ready)} punch item{'s' if len(ready) != 1 else ''} ready for sign-off",
                      "detail": ", ".join(f"PL-{p.number:03d}" for p in ready[:5]), "route": "/punch-list"})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(items, key=lambda i: order[i["severity"]])


def floor_plan_brief(db: Session, project: Project) -> Optional[dict]:
    plan = floor_plan_service.current_floor_plan(db, project.id)
    if plan is None:
        return None
    layout = plan.layout or {}
    return {
        "id": plan.id,
        "version": plan.version,
        "name": plan.name,
        "rooms": [r.get("name") for r in plan.rooms or [] if isinstance(r, dict)],
        "footprint_ft": [layout.get("length"), layout.get("width")] if layout.get("length") else None,
        "image_url": plan.image_url,
        "change_note": plan.change_note,
        "created_at": iso(plan.created_at),
    }


def load_plan_or_empty(pm: PMClient, project: Project) -> Plan:
    """The plan, or an empty one marked unavailable when pm-mcp is down, for
    pages that should still show what this database has."""
    try:
        return load_plan(pm, project)
    except PMUnavailable:
        return Plan(available=False)


def overview(db: Session, pm: PMClient, project: Project, today: date, plan: Optional[Plan] = None) -> dict:
    plan = plan if plan is not None else load_plan_or_empty(pm, project)
    clients = db.query(Client).filter(Client.project_id == project.id).all()
    return {
        "project_id": project.id,
        "pm_project_id": project.pm_project_id,
        "pm_available": plan.available,
        "floor_plan": floor_plan_brief(db, project),
        "schedule": schedule_summary(plan, today),
        "budget": budget_summary(plan, project, today),
        "compliance": compliance_summary(plan, today),
        "punch_list": punch_summary(project, today),
        "clients": [{"id": c.id, "name": c.name, "stage": c.stage} for c in clients],
        "materials": {
            "count": len(project.materials or []),
            "ordered": sum(m.status == "ordered" for m in project.materials or []),
            "delivered": sum(m.status == "delivered" for m in project.materials or []),
        },
        "attention": attention(plan, project, today),
    }
