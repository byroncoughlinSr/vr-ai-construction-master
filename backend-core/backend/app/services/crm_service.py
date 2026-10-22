"""Client CRM: the sales pipeline from first inquiry to handover.

A client's ``stage`` follows ``STAGES``; moving it logs a ``stage_change``
activity and, unless a probability is given, sets the stage's usual chance of
winning the job. A won client is linked to the project built for them, which
``create_project_for_client`` can start.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Client, ClientActivity, Project
from .project_controls_service import as_date, iso

# (id, label, usual win probability %)
STAGES = (
    ("new_inquiry", "New inquiry", 10),
    ("vr_consultation", "VR consultation", 25),
    ("schematic_design", "Floor plan design", 40),
    ("cost_estimation", "Estimate & proposal", 55),
    ("contract_permitting", "Contract & permits", 80),
    ("active_build", "Under construction", 100),
    ("handover", "Handover", 100),
    ("closed_lost", "Lost", 0),
)
STAGE_IDS = tuple(s[0] for s in STAGES)
STAGE_LABELS = {s[0]: s[1] for s in STAGES}
STAGE_PROBABILITY = {s[0]: s[2] for s in STAGES}
OPEN_STAGES = STAGE_IDS[:5]

ACTIVITY_KINDS = ("note", "call", "email", "meeting", "vr_demo", "site_visit", "stage_change", "ai")
SENTIMENTS = ("enthusiastic", "positive", "neutral", "concerned")
TIERS = ("standard", "premium", "vip", "commercial")


class CrmError(ValueError):
    pass


def check_choice(value: Optional[str], allowed: tuple[str, ...], what: str) -> None:
    if value is not None and value not in allowed:
        raise CrmError(f"Unknown {what} '{value}' (expected one of: {', '.join(allowed)})")


def serialize_activity(activity: ClientActivity) -> dict:
    return {
        "id": activity.id,
        "client_id": activity.client_id,
        "kind": activity.kind,
        "summary": activity.summary,
        "details": activity.details,
        "sentiment": activity.sentiment,
        "action_items": activity.action_items or [],
        "author": activity.author,
        "occurred_at": iso(activity.occurred_at),
    }


def serialize_client(client: Client, with_activities: bool = False) -> dict:
    data = {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "phone": client.phone,
        "company": client.company,
        "stage": client.stage,
        "stage_label": STAGE_LABELS.get(client.stage, client.stage),
        "tier": client.tier or "standard",
        "source": client.source,
        "deal_value": client.deal_value or 0.0,
        "win_probability": client.win_probability if client.win_probability is not None else STAGE_PROBABILITY.get(client.stage, 0),
        "lost_reason": client.lost_reason,
        "site_address": client.site_address,
        "preferred_style": client.preferred_style,
        "target_budget": client.target_budget,
        "target_square_feet": client.target_square_feet,
        "target_completion_date": iso(as_date(client.target_completion_date)),
        "requirements": client.requirements,
        "tags": client.tags or [],
        "next_follow_up_at": iso(client.next_follow_up_at),
        "next_action": client.next_action,
        "last_contact_at": iso(client.last_contact_at),
        "sentiment": client.sentiment,
        "ai_summary": client.ai_summary,
        "ai_insights": client.ai_insights or None,
        "ai_updated_at": iso(client.ai_updated_at),
        "project_id": client.project_id,
        "project_name": client.project.name if client.project else None,
        "activity_count": len(client.activities or []),
        "created_at": iso(client.created_at),
        "updated_at": iso(client.updated_at),
    }
    if with_activities:
        data["activities"] = [serialize_activity(a) for a in client.activities or []]
    return data


def _now() -> datetime:
    return datetime.now(timezone.utc)


def log_activity(client: Client, kind: str, summary: str, **fields) -> ClientActivity:
    check_choice(kind, ACTIVITY_KINDS, "activity kind")
    check_choice(fields.get("sentiment"), SENTIMENTS, "sentiment")
    activity = ClientActivity(kind=kind, summary=summary, **fields)
    if activity.occurred_at is None:
        activity.occurred_at = _now()
    client.activities.append(activity)
    # Talking to the client (not a note to self or the CRM's own entries) counts as contact.
    if kind in ("call", "email", "meeting", "vr_demo", "site_visit"):
        occurred = activity.occurred_at
        last = client.last_contact_at
        if last is None or as_date(occurred) >= as_date(last):
            client.last_contact_at = occurred
        if fields.get("sentiment"):
            client.sentiment = fields["sentiment"]
    return activity


def apply_update(client: Client, data: dict, author: Optional[str] = None) -> None:
    """Apply edits; a stage change is logged and resets the win probability to
    the stage's usual one unless the edit gives its own."""
    check_choice(data.get("stage"), STAGE_IDS, "stage")
    check_choice(data.get("tier"), TIERS, "tier")
    check_choice(data.get("sentiment"), SENTIMENTS, "sentiment")
    new_stage = data.pop("stage", None)
    for field, value in data.items():
        setattr(client, field, value)
    if new_stage and new_stage != client.stage:
        old = client.stage
        client.stage = new_stage
        if "win_probability" not in data:
            client.win_probability = STAGE_PROBABILITY[new_stage]
        log_activity(
            client, "stage_change",
            f"{STAGE_LABELS.get(old, old)} → {STAGE_LABELS[new_stage]}",
            author=author,
        )


def create_project_for_client(db: Session, client: Client, name: Optional[str] = None) -> Project:
    """Start a project for a won client, carrying over the site, budget and brief."""
    brief = "\n".join(
        part for part in (
            client.requirements,
            f"Style: {client.preferred_style}" if client.preferred_style else None,
            f"About {client.target_square_feet:,.0f} sq ft" if client.target_square_feet else None,
        ) if part
    )
    project = Project(
        name=(name or "").strip() or f"{client.name} residence",
        description=brief or None,
        status="planning",
        address=client.site_address,
        budget=client.target_budget,
        estimated_completion_date=client.target_completion_date,
    )
    db.add(project)
    db.flush()
    client.project_id = project.id
    log_activity(client, "note", f"Project started: {project.name}")
    return project


def pipeline(clients: list[Client], today: date) -> dict:
    """Counts and value per stage, the weighted forecast, and follow-ups due."""
    stages = []
    for stage_id, label, _ in STAGES:
        in_stage = [c for c in clients if c.stage == stage_id]
        stages.append({
            "id": stage_id,
            "label": label,
            "count": len(in_stage),
            "value": round(sum(c.deal_value or 0 for c in in_stage), 2),
        })
    open_clients = [c for c in clients if c.stage in OPEN_STAGES]
    won = [c for c in clients if c.stage in ("active_build", "handover")]
    lost = [c for c in clients if c.stage == "closed_lost"]
    due = [
        c for c in clients
        if c.stage != "closed_lost" and c.next_follow_up_at and as_date(c.next_follow_up_at) <= today
    ]
    stale = [
        c for c in open_clients
        if not c.next_follow_up_at and (as_date(c.last_contact_at or c.created_at) or today) <= today - timedelta(days=14)
    ]
    decided = len(won) + len(lost)
    return {
        "stages": stages,
        "open_count": len(open_clients),
        "open_value": round(sum(c.deal_value or 0 for c in open_clients), 2),
        "weighted_value": round(sum((c.deal_value or 0) * (c.win_probability or 0) / 100 for c in open_clients), 2),
        "won_value": round(sum(c.deal_value or 0 for c in won), 2),
        "win_rate": round(100 * len(won) / decided) if decided else None,
        "follow_ups_due": [
            {"id": c.id, "name": c.name, "next_follow_up_at": iso(c.next_follow_up_at), "next_action": c.next_action}
            for c in sorted(due, key=lambda c: as_date(c.next_follow_up_at))
        ],
        "stale": [{"id": c.id, "name": c.name, "last_contact_at": iso(c.last_contact_at)} for c in stale],
    }
