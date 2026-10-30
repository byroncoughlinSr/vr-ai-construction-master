from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
import logging

from ...services import AIPlanningService, get_image_service
from ...services.vr_geometry_service import build_geometry_from_rooms
from ...services import floor_plan_service
from ...config import settings
from ...database import SessionLocal
from ...models import Project, Material, AIGeneration
from ...services import project_controls_service as controls
from ...services.pm_client import PMError, PMUnavailable, get_pm
from .image_jobs import start_image_generation

logger = logging.getLogger(__name__)

# Rate limiter for AI endpoints
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()
planning_service = AIPlanningService()
image_service = get_image_service()


class ConstructionPlanRequest(BaseModel):
    """Request model for construction plan generation."""
    project_description: str
    budget: Optional[float] = None
    timeline_weeks: Optional[int] = None
    constraints: Optional[List[str]] = None


class CompleteProjectRequest(BaseModel):
    """Request model for complete project generation."""
    prompt: str
    budget: Optional[float] = None
    timeline_weeks: Optional[int] = None
    constraints: Optional[List[str]] = None
    generate_image: Optional[bool] = True


class VRFromPromptRequest(BaseModel):
    """Request model for prompt-only VR geometry generation."""
    prompt: str
    image_prompt: Optional[str] = None


@router.post("/generate-plan")
@limiter.limit("3/minute")  # 3 plan generations per minute
async def generate_construction_plan(plan_request: ConstructionPlanRequest, request: Request):
    """
    Generate a comprehensive construction plan using AI.

    This endpoint creates detailed project plans including phases, tasks,
    material requirements, timelines, and cost estimates.
    """
    try:
        result = await planning_service.generate_construction_plan(
            project_description=plan_request.project_description,
            budget=plan_request.budget,
            timeline_weeks=plan_request.timeline_weeks,
            constraints=plan_request.constraints
        )

        if result["success"]:
            return JSONResponse(
                status_code=200,
                content=result
            )
        raise HTTPException(
            status_code=500,
            detail=f"Plan generation failed: {result.get('error', 'Unknown error')}"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Construction planning service error: {str(e)}"
        )


def _available_models() -> list[dict]:
    """Planner providers that are currently usable, in fallback order."""
    candidates = [
        ("Groq", settings.groq_model, planning_service.groq_available),
        ("Ollama", settings.ollama_model, planning_service.ollama_available),
        ("Gemini", settings.gemini_model, planning_service.gemini_available),
    ]
    return [{"provider": p, "model": m} for p, m, ok in candidates if ok]


@router.get("/status")
async def get_service_status():
    """Check the status of the AI planning service."""
    try:
        return {
            "service": "AI Construction Planning",
            "status": "healthy",
            "groq_available": planning_service.groq_available,
            "ollama_available": planning_service.ollama_available,
            "gemini_available": planning_service.gemini_available,
            # Providers in the order the planner tries them (Groq → Ollama → Gemini).
            "models": _available_models(),
            "capabilities": [
                "construction plan generation",
                "cost estimation",
                "timeline planning",
                "risk assessment",
                "material requirements"
            ]
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Service status check failed: {str(e)}"
        )


@router.get("/models")
async def list_available_models():
    """List available AI models for planning."""
    try:
        models = [
            {
                "name": m["model"],
                "provider": m["provider"],
                "status": "available",
                "capabilities": ["text generation", "planning", "analysis"],
            }
            for m in _available_models()
        ]

        if not models:
            models.append({
                "name": "No models available",
                "provider": "None",
                "status": "unavailable",
                "capabilities": []
            })

        return {
            "models": models,
            "total_available": len([m for m in models if m["status"] == "available"])
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Model listing failed: {str(e)}"
        )


def _save_project(prompt: str, budget: Optional[float], project_data: dict) -> dict:
    """Save a generated project with its plan, floor plan (version 1) and
    materials, then put its phases and tasks into pm-mcp.

    The project is one transaction: either everything here is saved or nothing
    is. The phases go to pm-mcp afterwards; if pm-mcp is down the project is
    still saved and ``construction_plan`` says so (a template can be applied
    later). Runs in a worker thread because the session and client are synchronous.
    """
    plan = project_data.get("plan", {}) or {}
    total_cost = plan.get("total_cost")
    source = project_data.get("source") or "unknown"
    name = (project_data.get("project_name") or "").strip() or "Unnamed Project"
    with SessionLocal() as db:
        try:
            project = Project(
                name=name,
                description=prompt,
                status="planning",
                budget=budget,
                estimated_cost=total_cost if isinstance(total_cost, (int, float)) else 0,
            )
            db.add(project)
            db.flush()  # assigns project.id

            # Kept for later VR geometry generation (rooms, layout tree).
            # The full plan as the planner returned it.
            db.add(AIGeneration(
                project_id=project.id,
                prompt=prompt,
                source=source,
                model_used=_model_name(source),
                output_data=plan if isinstance(plan, dict) else {},
                generation_type="construction_plan",
                status="completed",
            ))

            # The floor plan the house is built from; later edits add versions.
            floor_plan_version = None
            try:
                floor_plan = floor_plan_service.add_floor_plan_version(
                    db, project.id, name, plan.get("project_structure") or {},
                    change_type="generated", change_note=prompt, source=source,
                )
                floor_plan_version = floor_plan.version
            except floor_plan_service.FloorPlanError as e:
                logger.warning(f"⚠️  Plan for project {project.id} has no usable floor plan: {e}")

            materials = plan.get("material_list", []) or []
            for material_data in materials:
                db.add(Material(
                    project_id=project.id,
                    name=material_data.get("name", "Unknown Material"),
                    material_type=material_data.get("material_type", "other"),
                    unit=material_data.get("unit", "each"),
                    unit_cost=material_data.get("unit_cost", 0),
                    quantity_needed=material_data.get("quantity", 0),
                    supplier_name=material_data.get("supplier_type", ""),
                    status="planned",
                ))

            db.commit()
        except Exception:
            db.rollback()
            raise

        phases = plan.get("phases", []) or []
        construction_plan = "none"
        if phases:
            try:
                pm = get_pm()
                controls.ensure_pm_project(db, pm, project)
                controls.import_ai_phases(pm, controls.load_plan(pm, project), phases)
                construction_plan = "saved"
            except (PMError, PMUnavailable) as e:
                logger.warning(f"⚠️  Project {project.id} saved without its phases in pm-mcp: {e}")
                construction_plan = "pm_unavailable"

        return {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "estimated_cost": project.estimated_cost,
            "phases_count": len(phases),
            "construction_plan": construction_plan,
            "materials_count": len(materials),
            "floor_plan_version": floor_plan_version,
        }


def _model_name(source: str) -> str:
    """The configured model behind a planner source name."""
    return {
        "claude": settings.anthropic_model,
        "groq": settings.groq_model,
        "ollama": settings.ollama_model,
    }.get(source, source)


def _project_geometry(project_id: int) -> dict:
    """VR geometry for a saved project (worker thread)."""
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        return floor_plan_service.geometry_for_project(db, project)


@router.post("/generate-project")
@limiter.limit("2/minute")  # 2 complete project generations per minute
async def generate_complete_project(
    project_request: CompleteProjectRequest,
    request: Request,
):
    """
    Generate a complete construction project from a single prompt.

    This endpoint:
    1. Generates a project name and a detailed plan (phases, tasks, materials, layout)
    2. Saves everything to the database in one transaction
    3. Optionally starts an architectural visualization in the background
    4. Returns the project ID and metadata immediately

    Track the image on /ws/image-progress/{image_generation_id}.
    """
    try:
        logger.info(f"Starting complete project generation: {project_request.prompt[:100]}")

        project_data = await planning_service.generate_complete_project(
            project_description=project_request.prompt,
            budget=project_request.budget,
            timeline_weeks=project_request.timeline_weeks,
            constraints=project_request.constraints
        )

        if not project_data.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Project generation failed: {project_data.get('error')}"
            )

        saved = await run_in_threadpool(
            _save_project, project_request.prompt, project_request.budget, project_data
        )
        plan = project_data.get("plan", {}) or {}
        logger.info(
            f"Project {saved['id']} saved: {saved['phases_count']} phases, "
            f"{saved['materials_count']} materials"
        )

        response_data = {
            "success": True,
            "project_id": saved["id"],
            "project_name": saved["name"],
            "description": saved["description"],
            "floor_plan_version": saved["floor_plan_version"],
            "metadata": {
                "total_cost": saved["estimated_cost"],
                "total_duration_weeks": plan.get("total_duration_weeks", 0),
                "phases_count": saved["phases_count"],
                "materials_count": saved["materials_count"],
                "ai_source": project_data.get("source", "unknown")
            }
        }

        if project_request.generate_image:
            generation_id = start_image_generation(
                lambda progress, gen_id: image_service.generate_architectural_visualization(
                    design_description=project_request.prompt,
                    style="modern",
                    time_of_day="day",
                    view_type="exterior",
                    progress_callback=progress,
                    generation_id=gen_id,
                ),
                label=f"project {saved['id']} image",
            )
            response_data["image_generation_id"] = generation_id
            response_data["websocket_url"] = f"/api/v1/ws/image-progress/{generation_id}"

        return JSONResponse(status_code=201, content=response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complete project generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate project: {str(e)}"
        )


@router.post("/generate-vr-from-prompt")
@limiter.limit("3/minute")
async def generate_vr_from_prompt(
    vr_request: VRFromPromptRequest,
    request: Request,
):
    """
    Generate a house from a floor-plan prompt and save it as a project.

    Used by the first voice prompt in the VR two-prompt flow: the user
    describes the floor plan, walks the generated house, then speaks a second
    prompt for the 2D image. The optional ``image_prompt`` is prepended as
    grounding context so the planning AI keeps the style consistent with it.

    The plan is saved like ``/generate-project`` (project, floor plan v1,
    phases, materials), so the house shows up in the dashboard and can be
    refined later. If saving fails the geometry is still returned, without a
    ``project_id``. The response has the same ``geometry`` shape as
    ``GET /projects/{id}/generate-vr``.
    """
    try:
        if vr_request.image_prompt:
            combined_prompt = (
                f"{vr_request.image_prompt}\n\n"
                f"Floor plan details: {vr_request.prompt}"
            )
        else:
            combined_prompt = vr_request.prompt

        logger.info(
            f"🎯 VR-from-prompt: {combined_prompt[:160]}"
            f"{'…' if len(combined_prompt) > 160 else ''}"
        )

        project_data = await planning_service.generate_complete_project(
            project_description=combined_prompt,
        )

        if not project_data.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Plan generation failed: {project_data.get('error', 'unknown')}",
            )

        plan = project_data.get("plan", {}) or {}
        project_structure = plan.get("project_structure", {}) or {}

        saved = None
        try:
            saved = await run_in_threadpool(_save_project, combined_prompt, None, project_data)
        except Exception as e:
            logger.error(f"⚠️  Could not save the voice-flow house, returning it unsaved: {e}", exc_info=True)

        if saved and saved["floor_plan_version"]:
            geometry = await run_in_threadpool(_project_geometry, saved["id"])
        else:
            if not project_structure.get("rooms"):
                logger.warning("⚠️  AI plan returned no rooms — VR scene will be empty")
            geometry = build_geometry_from_rooms(
                rooms_ft=list(project_structure.get("rooms", []) or []),
                layout=project_structure.get("layout"),
                exterior=project_structure.get("exterior"),
                furniture=project_structure.get("furniture"),
                materials=plan.get("material_list"),
                project_id=saved["id"] if saved else None,
                project_name=project_data.get("project_name") or "Generated House",
            )

        logger.info(
            f"🎉 VR-from-prompt geometry ready: '{geometry['project_name']}' "
            f"(project {geometry['project_id']}), {len(geometry['rooms'])} rooms, "
            f"{len(geometry['doors'])} doors, {len(geometry['windows'])} windows"
        )

        return {
            "success": True,
            "geometry": geometry,
            "project_id": geometry["project_id"],
            "project_name": geometry["project_name"],
            "status": "ready",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"VR-from-prompt generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate VR geometry from prompt: {str(e)}",
        )
