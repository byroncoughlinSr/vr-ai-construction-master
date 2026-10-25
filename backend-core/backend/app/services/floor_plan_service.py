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

from ..models import AIGeneration, FloorPlan, Material, Project
from . import plant_model_service
from .vr_exterior import exterior_spec
from .vr_furniture import furniture_spec, merge_furniture, prune_furniture, rename_furniture_rooms
from .vr_geometry_service import (
    FT_TO_M,
    LayoutError,
    _room_sides,
    _SIDE_NAMES,
    build_geometry_from_rooms,
    exterior_intervals,
    find_shared_walls,
    layout_rects_from_tree,
)

logger = logging.getLogger(__name__)


class FloorPlanError(ValueError):
    """The floor plan can't be turned into a house."""


# Room fields that hold other rooms' names.
_ROOM_REFS = ("connects_to", "no_door_to", "open_to")


def rename_rooms(structure: dict, renames: Any) -> dict:
    """A copy of ``structure`` with rooms renamed (``{"Old name": "New name"}``,
    case-insensitive) everywhere a name appears: layout leaves, ``entry``, the
    room list, the names in ``connects_to`` / ``no_door_to`` / ``open_to`` and the
    rooms ``furniture`` is listed under."""
    if not isinstance(renames, dict):
        return structure
    mapping = {
        str(old).strip().lower(): str(new).strip()
        for old, new in renames.items() if str(old or "").strip() and str(new or "").strip()
    }
    if not mapping:
        return structure

    def renamed(name: Any) -> Any:
        return mapping.get(name.strip().lower(), name) if isinstance(name, str) else name

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("room"), str):
                node["room"] = renamed(node["room"])
            for part in node.get("parts") or []:
                walk(part)

    out = copy.deepcopy(structure)
    layout = out.get("layout")
    if isinstance(layout, dict):
        walk(layout)
        if "entry" in layout:
            layout["entry"] = renamed(layout["entry"])
    for room in out.get("rooms") or []:
        if not isinstance(room, dict):
            continue
        if "name" in room:
            room["name"] = renamed(room["name"])
        for key in _ROOM_REFS:
            value = room.get(key)
            if isinstance(value, list):
                room[key] = [renamed(v) for v in value]
            elif isinstance(value, str):
                room[key] = renamed(value)
    if isinstance(out.get("furniture"), dict):
        out["furniture"] = rename_furniture_rooms(out["furniture"], mapping)
    return out


def validate_structure(structure: Any) -> dict:
    """Check a ``project_structure`` and return a clean copy (``layout``, ``rooms``
    and, when it has them, the cleaned ``exterior`` and ``furniture``).

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
        listed = {str(r["name"]).strip().lower() for r in rooms}
        drawn = {name.strip().lower() for name, _ in placed}
        missing = [name for name, _ in placed if name.strip().lower() not in listed]
        orphans = [r["name"] for r in rooms if str(r["name"]).strip().lower() not in drawn]
        if len(missing) == 1 and len(orphans) == 1:
            # Renamed in only one of the two places (the AI does this): follow the
            # layout, so the room keeps its materials, doorways and windows.
            rooms = rename_rooms({"rooms": rooms}, {orphans[0]: missing[0]})["rooms"]
            listed = {str(r["name"]).strip().lower() for r in rooms}
        # Rooms only drawn in the layout still get a house; give them an entry
        # in the room list so they can be edited like the others.
        for name, _ in placed:
            if name.strip().lower() not in listed:
                rooms.append({"name": name, "dimensions": {"height": 9}})
        layout = copy.deepcopy(layout)
    if not rooms:
        raise FloorPlanError("floor plan has no rooms")
    clean = {"layout": layout, "rooms": rooms}
    if "exterior" in structure:
        clean["exterior"] = exterior_spec(structure.get("exterior"))
    if "furniture" in structure:
        clean["furniture"] = furniture_spec(structure.get("furniture"))
    return clean


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
    """Validate ``structure`` and store it as the project's next version (not committed).

    The outside of the house and the furniture come from ``structure["exterior"]`` /
    ``["furniture"]`` when given, else they are carried over from the current
    version (furniture only for rooms the plan still has).
    """
    clean = validate_structure(structure)
    if "exterior" not in clean or "furniture" not in clean:
        current = current_floor_plan(db, project_id)
        clean.setdefault("exterior", current.exterior if current else None)
        clean.setdefault("furniture", current.furniture if current else None)
    clean["furniture"] = prune_furniture(clean["furniture"], [str(r["name"]) for r in clean["rooms"]])
    latest = db.query(func.max(FloorPlan.version)).filter(FloorPlan.project_id == project_id).scalar()
    plan = FloorPlan(
        project_id=project_id,
        version=(latest or 0) + 1,
        name=(name or "").strip() or "Untitled House",
        layout=clean["layout"],
        rooms=clean["rooms"],
        exterior=clean["exterior"],
        furniture=clean["furniture"],
        change_type=change_type,
        change_note=change_note,
        source=source,
    )
    db.add(plan)
    db.flush()
    logger.info(f"🗺️  Floor plan v{plan.version} '{plan.name}' saved for project {project_id} ({change_type})")
    return plan


def update_exterior(db: Session, plan: FloorPlan, exterior: Any, source: str | None = None) -> FloorPlan:
    """Replace the outside of the house on ``plan`` itself, without a new version
    (not committed). Raises FloorPlanError when ``exterior`` describes nothing."""
    clean = exterior_spec(exterior)
    if clean is None and exterior:
        raise FloorPlanError("the exterior description has nothing usable in it")
    plan.exterior = clean
    db.add(plan)
    db.flush()
    logger.info(
        f"🏡 Exterior of project {plan.project_id} floor plan v{plan.version} updated in place"
        + (f" ({source})" if source else "")
    )
    return plan


def update_furniture(db: Session, plan: FloorPlan, furniture: Any, source: str | None = None) -> FloorPlan:
    """Change the furniture on ``plan`` itself, without a new version (not committed):
    the rooms ``furniture`` lists are replaced, the others kept. Raises FloorPlanError
    when it describes nothing."""
    change = furniture_spec(furniture)
    if change is None:
        raise FloorPlanError("the furniture description has nothing usable in it")
    names = [str(r.get("name")) for r in plan.rooms or [] if isinstance(r, dict)]
    plan.furniture = prune_furniture(merge_furniture(plan.furniture, change), names)
    db.add(plan)
    db.flush()
    logger.info(
        f"🛋️  Furniture of project {plan.project_id} floor plan v{plan.version} updated in place"
        f" ({', '.join(change.get('rooms') or {}) or 'auto'})" + (f" ({source})" if source else "")
    )
    return plan


def site_summary(plan: FloorPlan, plant_models: list[str] | None = None,
                 furniture_models: list[str] | None = None) -> dict:
    """Where things are, in feet, so the AI can place plants and paths around the
    house: the footprint, the front door (and which way it faces), each room's
    rectangle, the other doors to the yard and the open (outdoor) parts of the footprint.
    ``plant_models`` / ``furniture_models`` name the plants and pieces that have a
    3D model made from a photo."""
    geometry = build_geometry_from_rooms(rooms_ft=list(plan.rooms or []), layout=plan.layout)

    def ft(v: float) -> float:
        return round(v / FT_TO_M, 1)

    bounds = [r["bounds"] for r in geometry["rooms"]] + [a["bounds"] for a in geometry["open_areas"]]
    site: dict[str, Any] = {}
    if bounds:
        site["footprint"] = {
            "length": ft(max(b["x1"] for b in bounds) - min(b["x0"] for b in bounds)),
            "width": ft(max(b["z1"] for b in bounds) - min(b["z0"] for b in bounds)),
        }
    door = next((d for d in geometry["doors"] if d.get("door_type") == "exterior"), None)
    spawn = geometry.get("spawn_position")
    if door:
        site["front_door"] = {"x": ft(door["position"]["x"]), "z": ft(door["position"]["z"])}
        if spawn:
            # The player starts just outside it, so this says which way it faces.
            dx, dz = spawn["x"] - door["position"]["x"], spawn["z"] - door["position"]["z"]
            if abs(dx) > abs(dz):
                out, faces = (-1 if dx < 0 else 1, 0), ("-x (left)" if dx < 0 else "+x (right)")
            else:
                out, faces = (0, -1 if dz < 0 else 1), ("-z (toward the street)" if dz < 0 else "+z (toward the back)")
            dx_ft, dz_ft = site["front_door"]["x"], site["front_door"]["z"]
            side = (out[1], out[0])  # along the wall
            site["front_door"]["faces"] = faces
            # Ready-made spots, since models are poor at this arithmetic.
            site["front_door"]["beside_it"] = [
                {"x": round(dx_ft + out[0] * 4 + s * side[0] * 5, 1), "z": round(dz_ft + out[1] * 4 + s * side[1] * 5, 1)}
                for s in (-1, 1)
            ]
    names = {r["id"]: r["name"] for r in geometry["rooms"]}
    walls = _walls_by_room(geometry, names)
    site["rooms"] = [
        {
            "name": r["name"], **{k: ft(v) for k, v in r["bounds"].items()},
            # One string per wall: the nested form cost ~1k tokens a house, which
            # pushed the refine prompt past Groq's per-minute token limit.
            "walls": {
                side: f"{', '.join(w['faces'])}: {', '.join(w['has']) or 'none'}" + (" (solid)" if w.get("solid") else "")
                for side, w in walls[r["id"]].items()
            },
        }
        for r in geometry["rooms"]
    ]
    site["outside_doors"] = [
        {
            "room": names.get((d.get("rooms") or [None])[0]),
            "style": d.get("style"),
            "side": d.get("side"),
            "x": ft(d["position"]["x"]),
            "z": ft(d["position"]["z"]),
        }
        for d in geometry["doors"] if d.get("door_type") == "patio"
    ]
    site["open_areas"] = [
        {k: ft(v) for k, v in a["bounds"].items()} for a in geometry["open_areas"]
    ]
    # Every doorway the house really has, including ones the builder adds so all
    # rooms are reachable; those are in no room's connects_to, so without this
    # the AI cannot see (or remove) them.
    site["doorways"] = [
        [names.get(a), names.get(b)]
        for d in geometry["doors"] if d.get("door_type") == "interior"
        for a, b in [d["rooms"]]
    ]
    if plant_models:
        site["plant_models"] = plant_models[:20]
    if furniture_models:
        site["furniture_models"] = furniture_models[:20]
    return site


def _walls_by_room(geometry: dict, names: dict[int, str]) -> dict[int, dict]:
    """Each room's four walls as the AI should see them: what is on the other side
    ("outside" or room names), the openings in it, and whether it is kept solid,
    e.g. ``{"back": {"faces": ["outside"], "has": ["window"]}}``."""
    rooms = geometry["rooms"]
    rects = [r["bounds"] for r in rooms]
    shared = find_shared_walls(rects)
    walls: dict[int, dict] = {}
    for idx, room in enumerate(rooms):
        sides = {}
        for name, side in zip(_SIDE_NAMES, _room_sides(room["bounds"])):
            faces = [
                names[rooms[j if i == idx else i]["id"]]
                for (i, j), wall in shared.items()
                if idx in (i, j) and wall[0] == side[0] and abs(wall[1] - side[1]) < 1e-3
            ]
            if exterior_intervals(side, shared):
                faces.append("outside")
            sides[name] = {"faces": faces, "has": []}
            if name in (room.get("solid_walls") or []):
                sides[name]["solid"] = True
        walls[room["id"]] = sides

    def side_of(room_id: int, position: dict, rotation: float) -> str | None:
        b = rooms[room_id - 1]["bounds"]
        if round(rotation) % 180 == 0:  # runs along x: a front or back wall
            return "front" if abs(position["z"] - b["z0"]) < abs(position["z"] - b["z1"]) else "back"
        return "left" if abs(position["x"] - b["x0"]) < abs(position["x"] - b["x1"]) else "right"

    for d in geometry["doors"]:
        ids = d.get("rooms") or []
        for rid in ids:
            if d.get("door_type") == "interior":
                other = next((o for o in ids if o != rid), None)
                label = f"doorway to {names.get(other)}"
            elif d.get("door_type") == "exterior":
                label = "front door"
            else:
                label = f"{str(d.get('style') or 'hinged').replace('_', ' ')} door to the yard"
            side = d.get("side") or side_of(rid, d["position"], d.get("rotation", 0))
            walls[rid][side]["has"].append(label)
    for w in geometry["windows"]:
        rid = w["room"]
        if w.get("bay"):
            side = (rooms[rid - 1].get("bay_window") or {}).get("side")
            if side and "bay window" not in walls[rid][side]["has"]:
                walls[rid][side]["has"].append("bay window")
            continue
        walls[rid][side_of(rid, w["position"], w.get("rotation", 0))]["has"].append("window")
    for o in geometry.get("open_walls") or []:
        a, b = o["rooms"]
        rotation = 0 if abs(o["start"]["z"] - o["end"]["z"]) < 1e-3 else 90
        for rid, other in ((a, b), (b, a)):
            walls[rid][side_of(rid, o["start"], rotation)]["has"].append(f"open to {names.get(other)} (no wall)")
    return walls


def serialize(plan: FloorPlan) -> dict:
    return {
        "id": plan.id,
        "project_id": plan.project_id,
        "version": plan.version,
        "name": plan.name,
        "layout": plan.layout,
        "rooms": plan.rooms,
        "exterior": plan.exterior,
        "furniture": plan.furniture,
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
    plant_models: list[dict] | None = None,
    furniture_models: list[dict] | None = None,
) -> dict:
    """VR geometry for one floor-plan version, named after the house.
    ``plant_models`` / ``furniture_models``: the finished photo models
    (``plant_model_service.ready_models``)."""
    geometry = build_geometry_from_rooms(
        rooms_ft=list(plan.rooms or []),
        layout=plan.layout,
        exterior=plan.exterior,
        plant_models=plant_models,
        furniture=plan.furniture,
        furniture_models=furniture_models,
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
    ai_generations, else none."""
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

    return [], None


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
        return geometry_for_plan(
            plan, materials, target_platform, optimize_for_vr,
            plant_models=plant_model_service.ready_models(db, "plant"),
            furniture_models=plant_model_service.ready_models(db, "furniture"),
        )

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
