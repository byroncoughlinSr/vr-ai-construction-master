from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Any, Optional
from sqlalchemy import or_, func
import logging
from pathlib import Path

from ...database import get_db
from ...config import settings
from ...models import AIGeneration, FloorPlan, Project
from ...schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    ProjectListResponse, ProjectStats
)
from ...services import get_image_service
from ...services import floor_plan_service, kitchen_style_service, plant_model_service
from ...services.vr_furniture import furniture_spec, merge_furniture, with_named_style
from ...services.vr_paint import apply_paint
from ...services.floor_plan_service import FloorPlanError
from ...services.pm_client import ACTOR, PMClient, PMError, PMUnavailable, get_pm
from .image_jobs import start_image_generation

logger = logging.getLogger(__name__)
router = APIRouter()
image_service = get_image_service()


@router.post("/", response_model=ProjectResponse)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db)
):
    """Create a new construction project."""
    try:
        db_project = Project(**project.dict())
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
        return ProjectResponse.from_orm(db_project)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create project: {str(e)}"
        )


@router.get("/stats", response_model=ProjectStats)
def get_project_stats(db: Session = Depends(get_db)):
    """Get project statistics summary."""
    total_projects = db.query(Project).count()
    active_projects = db.query(Project).filter(Project.status == "active").count()
    completed_projects = db.query(Project).filter(Project.status == "completed").count()

    # Calculate totals
    budget_result = db.query(
        func.sum(Project.budget),
        func.sum(Project.estimated_cost),
        func.sum(Project.actual_cost)
    ).first()

    total_budget = budget_result[0] or 0.0
    total_estimated_cost = budget_result[1] or 0.0
    total_actual_cost = budget_result[2] or 0.0

    # For simplicity, return 0 for average completion - would need more complex calculation
    average_completion_percentage = 0.0

    return ProjectStats(
        total_projects=total_projects,
        active_projects=active_projects,
        completed_projects=completed_projects,
        total_budget=total_budget,
        total_estimated_cost=total_estimated_cost,
        total_actual_cost=total_actual_cost,
        average_completion_percentage=average_completion_percentage
    )


@router.get("/latest")
def get_latest_project(db: Session = Depends(get_db)):
    """Return the most recently created project ID and name (for VR auto-load)."""
    project = db.query(Project).order_by(Project.id.desc()).first()
    if not project:
        raise HTTPException(status_code=404, detail="No projects found")
    logger.info(f"📡 Latest project requested → id={project.id} name='{project.name}'")
    return {"project_id": project.id, "project_name": project.name}


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific project by ID."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.from_orm(project)


@router.get("/", response_model=ProjectListResponse)
def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List projects with pagination and filtering."""
    query = db.query(Project)

    # Apply filters
    if search:
        query = query.filter(
            or_(
                Project.name.ilike(f"%{search}%"),
                Project.description.ilike(f"%{search}%"),
                Project.address.ilike(f"%{search}%")
            )
        )

    if status:
        query = query.filter(Project.status == status)

    # Get total count
    total = query.count()

    # Newest first: the dashboard auto-selects the first project in the list.
    query = query.order_by(Project.created_at.desc(), Project.id.desc())

    # Apply pagination
    projects = query.offset((page - 1) * page_size).limit(page_size).all()

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size

    return ProjectListResponse(
        projects=[ProjectResponse.from_orm(p) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    project_update: ProjectUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        # Update only provided fields
        update_data = project_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(project, field, value)

        db.commit()
        db.refresh(project)
        return ProjectResponse.from_orm(project)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to update project: {str(e)}"
        )


def _project_files(db: Session, project: Project) -> list[Path]:
    """Files on disk that belong to ``project`` alone: its rendered images (in
    ``generated_images``) and its documents (in ``uploads``). An image another
    project also links is left alone."""
    def inside(path: Path, directory: str) -> bool:
        return path.resolve().is_relative_to(Path(directory).resolve())

    urls = {plan.image_url for plan in project.floor_plans} | {g.result_url for g in project.ai_generations}
    files: list[Path] = []
    for url in sorted(u for u in urls if u and u.startswith("/generated_images/")):
        shared = (
            db.query(FloorPlan.id).filter(FloorPlan.image_url == url, FloorPlan.project_id != project.id).first()
            or db.query(AIGeneration.id).filter(
                AIGeneration.result_url == url, AIGeneration.project_id != project.id
            ).first()
        )
        path = Path(settings.generated_images_dir) / Path(url).name
        if not shared and inside(path, settings.generated_images_dir):
            files.append(path)
    for document in project.documents:
        path = Path(document.file_path or "")
        if document.file_path and inside(path, settings.uploads_dir):
            files.append(path)
    return files


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    purge: bool = Query(False, description="Also delete the pm-mcp plan and the project's files"),
    db: Session = Depends(get_db),
    pm: PMClient = Depends(get_pm),
):
    """Delete a project. Its construction plan in pm-mcp is archived, not
    deleted (other apps or agents may still refer to it) — unless ``purge``: then
    the pm-mcp project goes too, with the project's images and documents on disk.
    A purge is refused (503) while pm-mcp is down, before anything is deleted."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    pm_project_id = project.pm_project_id
    files = _project_files(db, project) if purge else []
    if purge and pm_project_id:
        try:
            pm.call("delete_project", project_id=pm_project_id, actor=ACTOR)
        except PMUnavailable as e:
            raise HTTPException(
                status_code=503,
                detail=f"pm-mcp is not reachable ({e}), so the construction plan can't be deleted. "
                       "Start it and try again, or delete without removing everything (the plan is then archived).",
            )
        except PMError as e:
            if "not found" not in str(e).lower():
                raise HTTPException(status_code=409, detail=f"pm-mcp refused to delete the plan: {e}")
    try:
        db.delete(project)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to delete project: {str(e)}"
        )
    if pm_project_id and not purge:
        try:
            pm.call("update_project", project_id=pm_project_id, status="archived", actor=ACTOR)
        except (PMError, PMUnavailable) as e:
            logger.warning(f"⚠️  pm-mcp project {pm_project_id} not archived: {e}")
    removed = 0
    for path in files:
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning(f"⚠️  Could not delete {path}: {e}")
    if purge:
        logger.info(f"🗑️  Project {project_id} deleted completely (pm-mcp {pm_project_id}, {removed} file(s))")
    return {"message": "Project deleted successfully", "purged": purge, "files_deleted": removed}


@router.post("/{project_id}/load-to-vr")
async def load_project_to_vr(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Load an existing project into VR with image generation.
    
    This endpoint:
    1. Validates the project exists
    2. Starts background image generation with WebSocket progress
    3. Prepares VR geometry (already available via /generate-vr)
    4. Returns generation_id for tracking
    
    Use WebSocket /api/v1/ws/image-progress/{generation_id} for progress updates.
    The dashboard passes the generation_id to the headset (Android.loadProjectWithImage),
    which builds the house and shows this image for review once it is ready.
    """
    logger.info(f"🎮 Load-to-VR requested for project {project_id}")
    
    # Validate project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    logger.info(f"📦 Project found: '{project.name}' (id={project_id})")
    
    project_description = project.description or project.name
    generation_id = start_image_generation(
        lambda progress, gen_id: image_service.generate_architectural_visualization(
            design_description=project_description,
            style="modern",
            time_of_day="day",
            progress_callback=progress,
            generation_id=gen_id,
        ),
        label=f"project {project_id} image",
    )

    return JSONResponse(
        status_code=202,  # Accepted - processing in background
        content={
            "success": True,
            "project_id": project_id,
            "project_name": project.name,
            "generation_id": generation_id,
            "status": "processing",
            "message": "Project loading to VR initiated. Image generation in progress.",
            "websocket_url": f"/api/v1/ws/image-progress/{generation_id}",
            "vr_geometry_url": f"/api/v1/projects/{project_id}/generate-vr"
        }
    )


@router.get("/{project_id}/generate-vr")
def generate_vr_geometry(
    project_id: int,
    include_materials: bool = Query(True),
    include_textures: bool = Query(True),
    optimize_for_vr: bool = Query(True),
    target_platform: str = Query("quest2"),
    db: Session = Depends(get_db)
):
    """
    VR geometry for the project's current floor plan.

    Built from the newest ``floor_plans`` version (projects saved before floor
    plans existed fall back to their stored plan, then to phase names), named
    after the house. ``geometry.floor_plan`` says which version it is.
    Returns JSON geometry that can be loaded directly into the VR application.
    """
    logger.info(f"🥽 VR geometry requested for project {project_id}")
    project = _get_project(db, project_id)

    try:
        geometry = floor_plan_service.geometry_for_project(
            db, project, target_platform=target_platform, optimize_for_vr=optimize_for_vr,
        )
        logger.info(
            f"🎉 VR geometry ready: '{geometry['project_name']}' {len(geometry['rooms'])} rooms, "
            f"{len(geometry['doors'])} doors, {len(geometry['windows'])} windows → sending to Quest"
        )
        return {
            "success": True,
            "geometry": geometry,
            "project_id": project_id,
            "status": "ready"
        }

    except Exception as e:
        logger.error(f"❌ VR geometry generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate VR geometry: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Floor plans: every change is a new version; the newest is what VR shows.
# ---------------------------------------------------------------------------

class FloorPlanUpdate(BaseModel):
    """A whole floor plan, as edited in the dashboard (sizes in feet)."""
    name: Optional[str] = Field(None, max_length=255)
    layout: Optional[dict[str, Any]] = None
    rooms: list[dict[str, Any]]
    note: Optional[str] = Field(None, max_length=2000)


class FloorPlanRefineRequest(BaseModel):
    """A change in words: "make the kitchen bigger", "add a laundry room"."""
    instruction: str = Field(..., min_length=1, max_length=2000)


class FloorPlanImageLink(BaseModel):
    generation_id: str = Field(..., min_length=1, max_length=64)
    image_url: str = Field(..., pattern=r"^/generated_images/[\w.-]+$")


def _get_project(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _current_plan(db: Session, project_id: int) -> FloorPlan:
    _get_project(db, project_id)
    plan = floor_plan_service.current_floor_plan(db, project_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Project has no floor plan")
    return plan


def _new_version_response(db: Session, plan: FloorPlan) -> dict:
    return {
        "success": True,
        "floor_plan": floor_plan_service.serialize(plan),
        "geometry": floor_plan_service.geometry_for_project(db, plan.project),
    }


@router.get("/{project_id}/floor-plans")
def list_floor_plans(project_id: int, db: Session = Depends(get_db)):
    """All versions of the project's floor plan, newest first."""
    _get_project(db, project_id)
    plans = (
        db.query(FloorPlan)
        .filter(FloorPlan.project_id == project_id)
        .order_by(FloorPlan.version.desc())
        .all()
    )
    return {"project_id": project_id, "floor_plans": [floor_plan_service.serialize(p) for p in plans]}


@router.get("/{project_id}/floor-plan")
def get_floor_plan(project_id: int, db: Session = Depends(get_db)):
    """The current floor plan (newest version)."""
    return floor_plan_service.serialize(_current_plan(db, project_id))


@router.put("/{project_id}/floor-plan")
def update_floor_plan(project_id: int, update: FloorPlanUpdate, db: Session = Depends(get_db)):
    """Save an edited floor plan as a new version and return its geometry.

    Renaming the floor plan renames the project too — it is the house's name.
    Returns 422 if the layout can't be built.
    """
    project = _get_project(db, project_id)
    current = floor_plan_service.current_floor_plan(db, project_id)
    name = (update.name or "").strip() or (current.name if current else project.name)
    try:
        plan = floor_plan_service.add_floor_plan_version(
            db, project_id, name, {"layout": update.layout, "rooms": update.rooms},
            change_type="edited", change_note=update.note or "Edited in the dashboard",
            source="dashboard",
        )
    except FloorPlanError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    project.name = plan.name
    db.commit()
    db.refresh(plan)
    return _new_version_response(db, plan)


class FurnitureMove(BaseModel):
    ref: dict = Field(..., description="The piece's ref from the geometry: {room, item, width, depth, auto}")
    x: float = Field(..., description="Where its centre was left, world metres")
    z: float
    yaw: float = Field(0.0, description="Degrees, the geometry's convention")


@router.put("/{project_id}/furniture/move")
def move_furniture(project_id: int, move: FurnitureMove, db: Session = Depends(get_db)):
    """A piece of furniture grabbed and put down in the headset: saved on the current
    floor plan in place (the house keeps its version)."""
    plan = floor_plan_service.current_floor_plan(db, project_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="This project has no floor plan")
    try:
        room = floor_plan_service.move_furniture(db, plan, move.ref, move.x, move.z, move.yaw)
    except FloorPlanError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"moved": True, "room": room, "version": plan.version}


@router.post("/{project_id}/floor-plan/refine")
async def refine_floor_plan(project_id: int, refine: FloorPlanRefineRequest, db: Session = Depends(get_db)):
    """Change the house in words; used by the headset's voice refinement and the dashboard.

    A change to the rooms is saved as a new floor-plan version. A change to only
    the outside (roof, walls, yard), the furniture or the paint updates the current
    version in place; ``updated_in_place`` says which happened.
    """
    from .ai_planning import planning_service  # one shared planner (and its Ollama probe state)

    current = _current_plan(db, project_id)
    logger.info(f"✏️  Refining project {project_id} v{current.version}: {refine.instruction[:160]}")
    try:
        result = await planning_service.refine_floor_plan(
            current.structure, refine.instruction,
            site=floor_plan_service.site_summary(
                current,
                plant_models=[m["name"] for m in plant_model_service.ready_models(db, "plant")],
                furniture_models=[m["name"] for m in plant_model_service.ready_models(db, "furniture")],
                kitchen_styles=[s.name for s in kitchen_style_service.list_styles(db)],
            ),
        )
    except Exception as e:
        logger.error(f"❌ Floor plan refinement failed: {e}")
        raise HTTPException(status_code=502, detail=f"Refinement failed: {e}")

    revised = result.get("plan") or {}
    structure = revised.get("project_structure") or {}
    exterior = revised.get("exterior", structure.get("exterior"))
    furniture = revised.get("furniture", structure.get("furniture"))
    paint = revised.get("paint")
    if furniture is not None:
        furniture = with_named_style(furniture, refine.instruction, [s.name for s in kitchen_style_service.list_styles(db)])
    scope = str(revised.get("scope") or "").strip().lower()
    if scope not in ("exterior", "furniture", "paint", "floor_plan", "both"):
        scope = (
            "floor_plan" if structure.get("rooms")
            else "exterior" if exterior is not None
            else "furniture" if furniture is not None
            else "paint" if paint is not None
            else "floor_plan"
        )
    in_place = scope in ("exterior", "furniture", "paint")
    logger.info(f"✏️  Change scope: {scope}")

    try:
        if in_place:
            if exterior is None and furniture is None and paint is None:
                raise FloorPlanError(f"the AI returned no {scope}")
            plan = current
            if exterior is not None:
                plan = floor_plan_service.update_exterior(db, plan, exterior, source=result.get("source"))
            if furniture is not None:
                plan = floor_plan_service.update_furniture(db, plan, furniture, source=result.get("source"))
            if paint is not None:
                plan = floor_plan_service.update_paint(db, plan, paint, source=result.get("source"))
        else:
            # The furniture the AI returns is only the rooms that change: start from
            # the current furniture (renamed with its rooms) and apply that.
            structure = {**structure, "furniture": current.furniture}
            # A rename the AI may have applied in only some places.
            structure = floor_plan_service.rename_rooms(structure, revised.get("renames"))
            if furniture is not None:
                structure["furniture"] = merge_furniture(structure["furniture"], furniture_spec(furniture))
            if exterior is not None:
                structure = {**structure, "exterior": exterior}
            if paint is not None:
                structure = {**structure, "rooms": apply_paint(structure.get("rooms"), paint)[0]}
            plan = floor_plan_service.add_floor_plan_version(
                db, project_id, current.name, structure,
                change_type="refined", change_note=refine.instruction, source=result.get("source"),
            )
    except FloorPlanError as e:
        db.rollback()
        logger.warning(f"⚠️  Revised floor plan rejected: {e}")
        raise HTTPException(status_code=422, detail=f"The revised plan is not buildable: {e}")
    db.commit()
    db.refresh(plan)
    return {**_new_version_response(db, plan), "updated_in_place": in_place}


@router.put("/{project_id}/floor-plan/image")
def link_floor_plan_image(project_id: int, link: FloorPlanImageLink, db: Session = Depends(get_db)):
    """Record an accepted render on the current floor plan."""
    _current_plan(db, project_id)
    plan = floor_plan_service.attach_image(db, project_id, link.generation_id, link.image_url)
    return {"success": True, "floor_plan": floor_plan_service.serialize(plan)}
