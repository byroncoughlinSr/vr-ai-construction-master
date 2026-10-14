"""Versioned floor plans: storing, validating and turning them into VR geometry.

A floor plan is the planner's ``project_structure`` (``layout`` tree + ``rooms``,
sizes in feet). Each change adds a new ``FloorPlan`` row; the highest version
is current. All routes that build a house from a saved project go through
``geometry_for_project`` so the headset and the dashboard see the same plan.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import AIGeneration, ConstructionPhase, FloorPlan, Material, Project
from .vr_geometry_service import LayoutError, build_geometry_from_rooms, layout_rects_from_tree

logger = logging.getLogger(__name__)


class FloorPlanError(ValueError):
    """The floor plan can't be turned into a house."""


def validate_structure(structure: Any) -> dict:
    """Check a ``project_structure`` and return a clean copy (``layout`` + ``rooms``).

    Rooms must be objects with names; a ``layout``, when given, must be a valid
    nested-split tree. Raises FloorPlanError otherwise.
    """
    if not isinstance(structure, dict):
        raise FloorPlanError("floor plan must be an object")
    rooms = structure.get("rooms")
    if not isinstance(rooms, list):
        raise FloorPlanError("floor plan has no room list")
    rooms = [copy.deepcopy(r) for r in rooms if isinstance(r, dict) and str(r.get("name") or "").strip()]
    layout = structure.get("layout")
    if layout is not None:
        try:
            placed = layout_rects_from_tree(layout)
        except LayoutError as e:
            raise FloorPlanError(f"invalid layout: {e}") from e
        # Rooms only drawn in the layout still get a house; give them an entry
        # in the room list so they can be edited like the others.
        listed = {str(r["name"]).strip().lower() for r in rooms}
        for name, _ in placed:
            if name.strip().lower() not in listed:
                rooms.append({"name": name, "dimensions": {"height": 9}})
        layout = copy.deepcopy(layout)
    if not rooms:
        raise FloorPlanError("floor plan has no rooms")
    return {"layout": layout, "rooms": rooms}


def current_floor_plan(db: Session, project_id: int) -> FloorPlan | None:
    return (
        db.query(FloorPlan)
        .filter(FloorPlan.project_id == project_id)
        .order_by(FloorPlan.version.desc())
        .first()
    )


def add_floor_plan_version(
    db: Session,
    project_id: int,
    name: str,
    structure: dict,
    change_type: str,
    change_note: str | None = None,
    source: str | None = None,
) -> FloorPlan:
    """Validate ``structure`` and store it as the project's next version (not committed)."""
    clean = validate_structure(structure)
    latest = db.query(func.max(FloorPlan.version)).filter(FloorPlan.project_id == project_id).scalar()
    plan = FloorPlan(
        project_id=project_id,
        version=(latest or 0) + 1,
        name=(name or "").strip() or "Untitled House",
        layout=clean["layout"],
        rooms=clean["rooms"],
        change_type=change_type,
        change_note=change_note,
        source=source,
    )
    db.add(plan)
    db.flush()
    logger.info(f"🗺️  Floor plan v{plan.version} '{plan.name}' saved for project {project_id} ({change_type})")
    return plan


def serialize(plan: FloorPlan) -> dict:
    return {
        "id": plan.id,
        "project_id": plan.project_id,
        "version": plan.version,
        "name": plan.name,
        "layout": plan.layout,
        "rooms": plan.rooms,
        "change_type": plan.change_type,
        "change_note": plan.change_note,
        "source": plan.source,
        "image_url": plan.image_url,
        "image_generation_id": plan.image_generation_id,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


def geometry_for_plan(
    plan: FloorPlan,
    materials: list[dict] | None = None,
    target_platform: str = "quest2",
    optimize_for_vr: bool = True,
) -> dict:
    """VR geometry for one floor-plan version, named after the house."""
    geometry = build_geometry_from_rooms(
        rooms_ft=list(plan.rooms or []),
        layout=plan.layout,
        materials=materials,
        project_id=plan.project_id,
        project_name=plan.name,
        target_platform=target_platform,
        optimize_for_vr=optimize_for_vr,
    )
    geometry["floor_plan"] = {
        "id": plan.id,
        "version": plan.version,
        "name": plan.name,
        "image_url": plan.image_url,
    }
    return geometry


def _legacy_rooms(db: Session, project_id: int) -> tuple[list[dict], dict | None]:
    """Rooms for a project saved before floor plans existed: the newest plan in
    ai_generations, else rooms guessed from phase names."""
    ai_data = (
        db.query(AIGeneration)
        .filter(
            AIGeneration.project_id == project_id,
            AIGeneration.generation_type == "construction_plan",
        )
        .order_by(AIGeneration.id.desc())
        .first()
    )
    if ai_data and isinstance(ai_data.output_data, dict):
        structure = ai_data.output_data.get("project_structure") or {}
        rooms = [r for r in structure.get("rooms") or [] if isinstance(r, dict)]
        if rooms:
            return rooms, structure.get("layout")

    rooms_ft: list[dict] = []
    phases = (
        db.query(ConstructionPhase)
        .filter(ConstructionPhase.project_id == project_id)
        .order_by(ConstructionPhase.phase_order)
        .all()
    )
    for phase in phases:
        name_lower = phase.name.lower()
        if any(kw in name_lower for kw in ("room", "bedroom", "kitchen", "bathroom", "garage")):
            dimensions_ft = {"length": 15.0, "width": 12.0, "height": 9.0}
            if "master" in name_lower:
                dimensions_ft = {"length": 17.0, "width": 15.0, "height": 9.0}
            elif "kitchen" in name_lower:
                dimensions_ft = {"length": 16.0, "width": 14.0, "height": 9.0}
            elif "bathroom" in name_lower:
                dimensions_ft = {"length": 10.0, "width": 8.0, "height": 9.0}
            elif "garage" in name_lower:
                dimensions_ft = {"length": 20.0, "width": 20.0, "height": 10.0}
            rooms_ft.append({"name": phase.name, "dimensions": dimensions_ft})
    logger.info(f"🔄 Fallback: {len(phases)} phases → {len(rooms_ft)} rooms found")
    return rooms_ft, None


def geometry_for_project(
    db: Session,
    project: Project,
    target_platform: str = "quest2",
    optimize_for_vr: bool = True,
) -> dict:
    """VR geometry for the project's current floor plan (or its legacy plan data)."""
    materials = [
        {"material_type": m.material_type, "name": m.name}
        for m in db.query(Material).filter(Material.project_id == project.id).all()
    ]
    plan = current_floor_plan(db, project.id)
    if plan:
        logger.info(f"🗺️  Using floor plan v{plan.version} '{plan.name}'")
        return geometry_for_plan(plan, materials, target_platform, optimize_for_vr)

    rooms_ft, layout = _legacy_rooms(db, project.id)
    if not rooms_ft:
        logger.warning("⚠️  No rooms generated — VR scene will be empty")
    geometry = build_geometry_from_rooms(
        rooms_ft=rooms_ft,
        layout=layout,
        materials=materials,
        project_id=project.id,
        project_name=project.name,
        target_platform=target_platform,
        optimize_for_vr=optimize_for_vr,
    )
    geometry["floor_plan"] = None
    return geometry


def attach_image(db: Session, project_id: int, generation_id: str, image_url: str) -> FloorPlan | None:
    """Record a finished render on the project's current floor plan (committed)."""
    plan = current_floor_plan(db, project_id)
    if not plan:
        return None
    plan.image_url = image_url
    plan.image_generation_id = generation_id
    db.add(AIGeneration(
        project_id=project_id,
        generation_type="image",
        source="stable_diffusion",
        result_url=image_url,
        output_data={"generation_id": generation_id, "floor_plan_version": plan.version},
        status="completed",
    ))
    db.commit()
    logger.info(f"🖼️  Image {generation_id} linked to project {project_id} floor plan v{plan.version}")
    return plan
