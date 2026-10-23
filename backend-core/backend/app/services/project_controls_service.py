"""Project controls: the schedule, budget and compliance figures the dashboard
shows for one project, worked out from what is in the database.

Phases and tasks come from the AI plan (``_save_project`` in ``ai_planning.py``)
and are then managed by hand. Progress is *earned* with the 50/50 rule: a task
earns half its weight when it starts and the rest when it is completed, a task's
weight being its planned duration. Earned value uses each phase's budgeted cost;
planned value needs a baselined schedule (planned dates), so until the schedule
is baselined there is no SPI.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from ..models import (
    BudgetCategory, BudgetItem, ChangeOrder, Client, ConstructionPhase, Equipment,
    Inspection, LaborResource, Permit, Project, Task,
)
from . import floor_plan_service

TASK_STATUSES = ("pending", "in_progress", "completed", "blocked")
TASK_PRIORITIES = ("low", "medium", "high", "critical")
EXPENSE_CATEGORIES = ("labor", "materials", "equipment", "subcontract", "permits", "other")
EXPENSE_STATUSES = ("pending", "paid")
CHANGE_ORDER_STATUSES = ("draft", "submitted", "approved", "rejected")
PERMIT_STATUSES = ("applied", "approved", "issued", "expired", "rejected")
INSPECTION_STATUSES = ("scheduled", "passed", "failed", "cancelled")
EQUIPMENT_STATUSES = ("available", "in_use", "maintenance", "out_of_service")

# A phase with no tasks still takes time when the schedule is baselined.
DEFAULT_PHASE_DAYS = 7


class ControlsError(ValueError):
    """A request the controls can't carry out (bad status, unknown phase...)."""


# --- dates -----------------------------------------------------------------

def as_date(value: Any) -> Optional[date]:
    """The calendar date of a stored timestamp (SQLite hands them back naive,
    Postgres aware), so dates compare without timezone trouble."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
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


# --- schedule --------------------------------------------------------------

def task_days(task: Task) -> float:
    days = task.planned_duration_days
    return float(days) if days and days > 0 else 1.0


def _earned_fraction(task: Task) -> float:
    if task.status == "completed":
        return 1.0
    if task.status == "in_progress":
        return 0.5
    return 0.0


def phase_progress(phase: ConstructionPhase) -> float:
    """Percent complete, earned from the phase's tasks (50/50 rule, weighted by
    duration); a phase without tasks keeps the progress entered for it."""
    tasks = list(phase.tasks or [])
    if not tasks:
        return float(phase.progress_percentage or 0.0)
    weight = sum(task_days(t) for t in tasks)
    return round(100.0 * sum(task_days(t) * _earned_fraction(t) for t in tasks) / weight, 1)


def phase_days(phase: ConstructionPhase) -> float:
    tasks = list(phase.tasks or [])
    if tasks:
        return sum(task_days(t) for t in tasks)
    start, end = as_date(phase.planned_start_date), as_date(phase.planned_end_date)
    if start and end and end > start:
        return float((end - start).days)
    return float(DEFAULT_PHASE_DAYS)


def refresh_phase(phase: ConstructionPhase, today: date) -> None:
    """Store the progress and status the phase's tasks add up to, and when it
    actually started and finished."""
    tasks = list(phase.tasks or [])
    if not tasks:
        return
    phase.progress_percentage = phase_progress(phase)
    if all(t.status == "completed" for t in tasks):
        phase.status = "completed"
        if not phase.actual_end_date:
            phase.actual_end_date = at_midnight(today)
    elif any(t.status in ("in_progress", "completed") for t in tasks):
        phase.status = "in_progress"
        phase.actual_end_date = None
    else:
        phase.status = "pending"
        phase.actual_end_date = None
    if phase.status != "pending" and not phase.actual_start_date:
        phase.actual_start_date = at_midnight(today)


def set_task_status(task: Task, status: str, today: date) -> None:
    check(status, TASK_STATUSES, "task status")
    task.status = status
    if status in ("in_progress", "completed") and not task.actual_start_date:
        task.actual_start_date = at_midnight(today)
    if status == "completed":
        if not task.actual_end_date:
            task.actual_end_date = at_midnight(today)
    else:
        task.actual_end_date = None


def _planned_fraction(start: Optional[date], end: Optional[date], today: date) -> Optional[float]:
    """How much of [start, end] has passed by ``today`` (0..1); None when unplanned."""
    if not start or not end:
        return None
    if today <= start:
        return 0.0
    if today >= end:
        return 1.0
    return (today - start).days / max((end - start).days, 1)


def _is_late(planned_end: Any, done: bool, today: date) -> bool:
    end = as_date(planned_end)
    return bool(end and end < today and not done)


def ordered_phases(project: Project) -> list[ConstructionPhase]:
    return sorted(project.phases or [], key=lambda p: (p.phase_order or 0, p.id))


def ordered_tasks(phase: ConstructionPhase) -> list[Task]:
    return sorted(phase.tasks or [], key=lambda t: (t.task_order or 0, t.id))


def serialize_task(task: Task, today: date) -> dict:
    return {
        "id": task.id,
        "phase_id": task.phase_id,
        "name": task.name,
        "description": task.description,
        "status": task.status or "pending",
        "priority": task.priority or "medium",
        "task_order": task.task_order,
        "duration_days": task_days(task),
        "planned_start": iso(as_date(task.planned_start_date)),
        "planned_end": iso(as_date(task.planned_end_date)),
        "actual_start": iso(as_date(task.actual_start_date)),
        "actual_end": iso(as_date(task.actual_end_date)),
        "budgeted_cost": task.budgeted_cost or 0.0,
        "actual_cost": task.actual_cost or 0.0,
        "requires_inspection": bool(task.requires_inspection),
        "late": _is_late(task.planned_end_date, task.status == "completed", today),
    }


def serialize_phase(phase: ConstructionPhase, today: date, actual_cost: float = 0.0) -> dict:
    progress = phase_progress(phase)
    return {
        "id": phase.id,
        "name": phase.name,
        "description": phase.description,
        "phase_order": phase.phase_order,
        "status": phase.status or "pending",
        "progress": progress,
        "duration_days": phase_days(phase),
        "planned_start": iso(as_date(phase.planned_start_date)),
        "planned_end": iso(as_date(phase.planned_end_date)),
        "actual_start": iso(as_date(phase.actual_start_date)),
        "actual_end": iso(as_date(phase.actual_end_date)),
        "budgeted_cost": phase.budgeted_cost or 0.0,
        "actual_cost": actual_cost,
        "late": _is_late(phase.planned_end_date, progress >= 100, today),
        "tasks": [serialize_task(t, today) for t in ordered_tasks(phase)],
    }


def _actual_by_phase(project: Project) -> dict[int, float]:
    totals: dict[int, float] = {}
    for item in project.budget_items or []:
        if item.phase_id:
            totals[item.phase_id] = totals.get(item.phase_id, 0.0) + (item.actual_amount or 0.0)
    return totals


def schedule_summary(project: Project, today: date) -> dict:
    phases = ordered_phases(project)
    tasks = [t for p in phases for t in (p.tasks or [])]
    total_days = sum(phase_days(p) for p in phases)
    progress = (
        round(sum(phase_days(p) * phase_progress(p) for p in phases) / total_days, 1)
        if total_days else 0.0
    )
    starts = [as_date(p.planned_start_date) for p in phases if p.planned_start_date]
    ends = [as_date(p.planned_end_date) for p in phases if p.planned_end_date]
    current = next((p for p in phases if phase_progress(p) < 100), None)
    return {
        "progress": progress,
        "baselined": bool(starts and ends),
        "planned_start": iso(min(starts)) if starts else None,
        "planned_finish": iso(max(ends)) if ends else None,
        "total_days": total_days,
        "phase_count": len(phases),
        "current_phase": {"id": current.id, "name": current.name} if current else None,
        "tasks": {
            "total": len(tasks),
            "completed": sum(t.status == "completed" for t in tasks),
            "in_progress": sum(t.status == "in_progress" for t in tasks),
            "blocked": sum(t.status == "blocked" for t in tasks),
            "late": sum(_is_late(t.planned_end_date, t.status == "completed", today) for t in tasks),
        },
    }


def schedule(project: Project, today: date) -> dict:
    actual = _actual_by_phase(project)
    return {
        "project_id": project.id,
        **schedule_summary(project, today),
        "phases": [serialize_phase(p, today, actual.get(p.id, 0.0)) for p in ordered_phases(project)],
    }


def baseline_schedule(project: Project, start: date) -> None:
    """Lay the phases end to end from ``start``, each phase's tasks one after
    another (calendar days, durations rounded up). Overwrites planned dates."""
    cursor = start
    for phase in ordered_phases(project):
        phase.planned_start_date = at_midnight(cursor)
        tasks = ordered_tasks(phase)
        if tasks:
            for task in tasks:
                task.planned_start_date = at_midnight(cursor)
                cursor += timedelta(days=math.ceil(task_days(task)))
                task.planned_end_date = at_midnight(cursor)
        else:
            cursor += timedelta(days=DEFAULT_PHASE_DAYS)
        phase.planned_end_date = at_midnight(cursor)
    project.start_date = at_midnight(start)
    project.estimated_completion_date = at_midnight(cursor)


# --- budget ----------------------------------------------------------------

def _category(db: Session, kind: str) -> BudgetCategory:
    check(kind, EXPENSE_CATEGORIES, "expense category")
    name = kind.capitalize()
    category = db.query(BudgetCategory).filter(BudgetCategory.name == name).first()
    if category is None:
        category = BudgetCategory(name=name, category_type=kind)
        db.add(category)
        db.flush()
    return category


def add_expense(db: Session, project: Project, data: dict) -> BudgetItem:
    """Log a cost against the project. Kept as a budget item whose budgeted and
    actual amounts are both the amount."""
    check(data.get("status"), EXPENSE_STATUSES, "expense status")
    phase_id = data.get("phase_id")
    if phase_id and not any(p.id == phase_id for p in project.phases or []):
        raise ControlsError(f"Phase {phase_id} is not part of this project")
    amount = float(data["amount"])
    category = _category(db, data.get("category") or "other")
    item = BudgetItem(
        project_id=project.id,
        category_id=category.id,
        phase_id=phase_id,
        name=data["vendor"],
        vendor_name=data["vendor"],
        notes=data.get("description"),
        budgeted_amount=amount,
        actual_amount=amount,
        status=data.get("status") or "paid",
        purchase_order_number=data.get("invoice_number"),
        actual_date=at_midnight(data.get("incurred_on") or date.today()),
    )
    db.add(item)
    return item


def serialize_expense(item: BudgetItem) -> dict:
    return {
        "id": item.id,
        "vendor": item.vendor_name or item.name,
        "description": item.notes,
        "category": item.category.category_type if item.category else "other",
        "amount": item.actual_amount or 0.0,
        "status": item.status,
        "date": iso(as_date(item.actual_date)),
        "invoice_number": item.purchase_order_number,
        "phase_id": item.phase_id,
        "phase_name": item.phase.name if item.phase else None,
        "created_at": iso(item.created_at),
    }


def next_change_order_number(project: Project) -> int:
    return max((co.number for co in project.change_orders or []), default=0) + 1


def serialize_change_order(co: ChangeOrder) -> dict:
    return {
        "id": co.id,
        "project_id": co.project_id,
        "number": co.number,
        "code": f"CO-{co.number:03d}",
        "title": co.title,
        "description": co.description,
        "cost_impact": co.cost_impact or 0.0,
        "schedule_impact_days": co.schedule_impact_days or 0.0,
        "status": co.status,
        "requested_by": co.requested_by,
        "floor_plan_version": co.floor_plan_version,
        "decided_at": iso(co.decided_at),
        "created_at": iso(co.created_at),
    }


def _ratio(numerator: float, denominator: Optional[float]) -> Optional[float]:
    return round(numerator / denominator, 2) if denominator else None


def budget_summary(project: Project, today: date) -> dict:
    """Earned value figures for the project.

    BAC = the phases' budgeted cost (or the plan's estimate when the phases
    carry none) plus approved change orders. EV = each phase's budget times its
    earned progress. AC = every logged expense. PV only once the schedule has
    planned dates.
    """
    phases = ordered_phases(project)
    phase_budget = sum(p.budgeted_cost or 0.0 for p in phases)
    baseline = phase_budget if phase_budget > 0 else float(project.estimated_cost or 0.0)
    cos = project.change_orders or []
    approved = sum(co.cost_impact or 0.0 for co in cos if co.status == "approved")
    pending = sum(co.cost_impact or 0.0 for co in cos if co.status == "submitted")
    bac = baseline + approved

    if phase_budget > 0:
        ev = sum((p.budgeted_cost or 0.0) * phase_progress(p) / 100 for p in phases)
    else:
        ev = baseline * schedule_summary(project, today)["progress"] / 100

    fractions = [_planned_fraction(as_date(p.planned_start_date), as_date(p.planned_end_date), today) for p in phases]
    if phases and all(f is not None for f in fractions):
        if phase_budget > 0:
            pv: Optional[float] = sum((p.budgeted_cost or 0.0) * f for p, f in zip(phases, fractions))
        else:
            days = [phase_days(p) for p in phases]
            pv = baseline * sum(d * f for d, f in zip(days, fractions)) / (sum(days) or 1)
    else:
        pv = None

    items = project.budget_items or []
    ac = sum(i.actual_amount or 0.0 for i in items)
    unpaid = sum(i.actual_amount or 0.0 for i in items if i.status != "paid")
    cpi = _ratio(ev, ac)
    spi = _ratio(ev, pv)
    eac = round(bac / cpi, 2) if cpi else bac

    actual_by_phase = _actual_by_phase(project)
    by_category: dict[str, float] = {}
    for item in items:
        kind = item.category.category_type if item.category else "other"
        by_category[kind] = by_category.get(kind, 0.0) + (item.actual_amount or 0.0)

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
                "phase_id": p.id,
                "name": p.name,
                "budgeted": p.budgeted_cost or 0.0,
                "earned": round((p.budgeted_cost or 0.0) * phase_progress(p) / 100, 2),
                "actual": round(actual_by_phase.get(p.id, 0.0), 2),
            }
            for p in phases
        ],
        "by_category": [{"category": k, "actual": round(v, 2)} for k, v in sorted(by_category.items())],
    }


# --- compliance ------------------------------------------------------------

def serialize_permit(permit: Permit) -> dict:
    return {
        "id": permit.id,
        "project_id": permit.project_id,
        "permit_number": permit.permit_number,
        "permit_type": permit.permit_type,
        "description": permit.description,
        "jurisdiction": permit.jurisdiction or permit.issuing_authority,
        "status": permit.status,
        "application_date": iso(as_date(permit.application_date)),
        "issued_date": iso(as_date(permit.issued_date)),
        "expiration_date": iso(as_date(permit.expiration_date)),
        "permit_fee": permit.permit_fee or 0.0,
        "conditions": permit.conditions,
        "contact_name": permit.contact_name,
        "contact_phone": permit.contact_phone,
        "contact_email": permit.contact_email,
    }


def serialize_inspection(inspection: Inspection) -> dict:
    return {
        "id": inspection.id,
        "project_id": inspection.project_id,
        "permit_id": inspection.permit_id,
        "permit_number": inspection.permit.permit_number if inspection.permit else None,
        "task_id": inspection.task_id,
        "inspection_type": inspection.inspection_type,
        "description": inspection.description,
        "inspector_name": inspection.inspector_name,
        "scheduled_date": iso(inspection.scheduled_date),
        "actual_date": iso(inspection.actual_date),
        "status": inspection.status,
        "result_details": inspection.result_details,
        "critical_findings": inspection.critical_findings,
        "requires_followup": bool(inspection.requires_followup),
    }


def compliance_summary(project: Project, today: date) -> dict:
    permits = project.permits or []
    inspections = project.inspections or []
    decided = [i for i in inspections if i.status in ("passed", "failed")]
    return {
        "permits_total": len(permits),
        "permits_active": sum(p.status in ("approved", "issued") for p in permits),
        "inspections_upcoming": sum(
            i.status == "scheduled" and (as_date(i.scheduled_date) or today) >= today for i in inspections
        ),
        "inspections_passed": sum(i.status == "passed" for i in inspections),
        "inspections_failed": sum(i.status == "failed" for i in inspections),
        "pass_rate": round(100 * sum(i.status == "passed" for i in decided) / len(decided)) if decided else None,
    }


# --- resources -------------------------------------------------------------

def serialize_crew(member: LaborResource) -> dict:
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


def serialize_equipment(item: Equipment) -> dict:
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

def attention(project: Project, today: date) -> list[dict]:
    """What needs the project manager now, most pressing first."""
    items: list[dict] = []
    for phase in ordered_phases(project):
        for task in ordered_tasks(phase):
            if task.status == "blocked":
                items.append({"kind": "task_blocked", "severity": "high", "title": f"Blocked: {task.name}",
                              "detail": phase.name, "route": "/timeline"})
            elif _is_late(task.planned_end_date, task.status == "completed", today):
                items.append({"kind": "task_late", "severity": "high", "title": f"Late: {task.name}",
                              "detail": f"Planned to finish {iso(as_date(task.planned_end_date))}", "route": "/timeline"})
    for inspection in project.inspections or []:
        day = as_date(inspection.scheduled_date)
        if inspection.status == "failed" and not inspection.followup_completed:
            items.append({"kind": "inspection_failed", "severity": "high",
                          "title": f"Failed inspection: {inspection.inspection_type}",
                          "detail": inspection.critical_findings or inspection.result_details or "",
                          "route": "/compliance"})
        elif inspection.status == "scheduled" and day and today <= day <= today + timedelta(days=7):
            items.append({"kind": "inspection_soon", "severity": "medium",
                          "title": f"Inspection {iso(day)}: {inspection.inspection_type}",
                          "detail": inspection.inspector_name or "", "route": "/compliance"})
    for permit in project.permits or []:
        expires = as_date(permit.expiration_date)
        if permit.status in ("approved", "issued") and expires and expires <= today + timedelta(days=30):
            items.append({"kind": "permit_expiring", "severity": "medium" if expires >= today else "high",
                          "title": f"Permit {permit.permit_number} expires {iso(expires)}",
                          "detail": permit.permit_type, "route": "/compliance"})
    for co in project.change_orders or []:
        if co.status == "submitted":
            items.append({"kind": "change_order_pending", "severity": "medium",
                          "title": f"CO-{co.number:03d} awaiting approval: {co.title}",
                          "detail": f"${co.cost_impact or 0:,.0f}", "route": "/budget"})
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


def overview(db: Session, project: Project, today: date) -> dict:
    clients = db.query(Client).filter(Client.project_id == project.id).all()
    return {
        "project_id": project.id,
        "floor_plan": floor_plan_brief(db, project),
        "schedule": schedule_summary(project, today),
        "budget": budget_summary(project, today),
        "compliance": compliance_summary(project, today),
        "clients": [{"id": c.id, "name": c.name, "stage": c.stage} for c in clients],
        "materials": {
            "count": len(project.materials or []),
            "ordered": sum(m.status == "ordered" for m in project.materials or []),
            "delivered": sum(m.status == "delivered" for m in project.materials or []),
        },
        "attention": attention(project, today),
    }
