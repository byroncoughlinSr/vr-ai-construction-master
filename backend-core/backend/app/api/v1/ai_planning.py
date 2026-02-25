from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
import uuid
import asyncio
import logging

from ...services import AIPlanningService, AIImageService
from ...database import get_db
from ...models import Project, ConstructionPhase, Task, Material
from .websocket import send_image_progress_update, complete_image_generation, fail_image_generation

logger = logging.getLogger(__name__)

# Rate limiter for AI endpoints
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()
planning_service = AIPlanningService()
image_service = AIImageService()


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
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Plan generation failed: {result.get('error', 'Unknown error')}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Construction planning service error: {str(e)}"
        )


@router.get("/status")
async def get_service_status():
    """Check the status of the AI planning service."""
    try:
        return {
            "service": "AI Construction Planning",
            "status": "healthy",
            "ollama_available": planning_service.ollama_available,
            "gemini_available": planning_service.gemini_available,
            "models": {
                "primary": "Llama 3.1 8B (Ollama)" if planning_service.ollama_available else None,
                "fallback": "Gemini Pro" if planning_service.gemini_available else None
            },
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
        models = []

        if planning_service.ollama_available:
            models.append({
                "name": "Llama 3.1 8B",
                "provider": "Ollama",
                "status": "available",
                "capabilities": ["text generation", "planning", "analysis"]
            })

        if planning_service.gemini_available:
            models.append({
                "name": "Gemini Pro",
                "provider": "Google",
                "status": "available",
                "capabilities": ["text generation", "planning", "analysis"]
            })

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


@router.post("/generate-project")
@limiter.limit("2/minute")  # 2 complete project generations per minute
async def generate_complete_project(
    project_request: CompleteProjectRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Generate a complete construction project from a single prompt.
    
    This endpoint:
    1. Generates a project name from the prompt
    2. Creates detailed construction plan with phases and tasks
    3. Generates material list with costs
    4. Saves everything to the database
    5. Optionally generates architectural visualization image
    6. Returns project ID and metadata immediately
    
    The image generation happens in background. Use WebSocket to track progress.
    """
    try:
        logger.info(f"Starting complete project generation: {project_request.prompt[:100]}")
        
        # Generate complete project plan using AI
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
        
        # Save to database
        plan = project_data.get("plan", {})
        
        # Create project
        db_project = Project(
            name=project_data.get("project_name", "Unnamed Project"),
            description=project_request.prompt,
            status="planning",
            budget=project_request.budget,
            estimated_cost=plan.get("total_cost", 0) if isinstance(plan.get("total_cost"), (int, float)) else 0
        )
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
        
        logger.info(f"Project created with ID: {db_project.id}")
        
        # Store AI generation data for later VR geometry generation
        from ...models import AIGeneration
        import json
        
        ai_generation = AIGeneration(
            project_id=db_project.id,
            prompt=project_request.prompt,
            model_used=project_data.get("source", "unknown"),
            output_data=plan if isinstance(plan, dict) else {},
            generation_type="construction_plan",
            status="completed"
        )
        db.add(ai_generation)
        db.commit()
        logger.info(f"AI generation data saved for project {db_project.id}")
        
        # Create construction phases
        phases_created = 0
        for idx, phase_data in enumerate(plan.get("phases", [])):
            db_phase = ConstructionPhase(
                project_id=db_project.id,
                name=phase_data.get("name", f"Phase {idx+1}"),
                description=phase_data.get("description", ""),
                phase_order=idx + 1,
                budgeted_cost=phase_data.get("estimated_cost", 0),
                status="pending"
            )
            db.add(db_phase)
            db.commit()
            db.refresh(db_phase)
            phases_created += 1
            
            # Create tasks for this phase
            for task_idx, task_data in enumerate(phase_data.get("tasks", [])):
                db_task = Task(
                    project_id=db_project.id,
                    phase_id=db_phase.id,
                    name=task_data.get("name", f"Task {task_idx+1}"),
                    description=task_data.get("description", ""),
                    task_order=task_idx + 1,
                    planned_duration_days=task_data.get("duration_days", 1),
                    budgeted_cost=task_data.get("estimated_cost", 0),
                    status="pending"
                )
                db.add(db_task)
        
        db.commit()
        logger.info(f"Created {phases_created} phases with tasks")
        
        # Create materials
        materials_created = 0
        for material_data in plan.get("material_list", []):
            db_material = Material(
                project_id=db_project.id,
                name=material_data.get("name", "Unknown Material"),
                material_type=material_data.get("material_type", "other"),
                unit=material_data.get("unit", "each"),
                unit_cost=material_data.get("unit_cost", 0),
                quantity_needed=material_data.get("quantity", 0),
                supplier_name=material_data.get("supplier_type", ""),
                status="planned"
            )
            db.add(db_material)
            materials_created += 1
        
        db.commit()
        logger.info(f"Created {materials_created} materials")
        
        # Prepare response
        response_data = {
            "success": True,
            "project_id": db_project.id,
            "project_name": db_project.name,
            "description": db_project.description,
            "metadata": {
                "total_cost": db_project.estimated_cost,
                "total_duration_weeks": plan.get("total_duration_weeks", 0),
                "phases_count": phases_created,
                "materials_count": materials_created,
                "ai_source": project_data.get("source", "unknown")
            }
        }
        
        # Start background image generation if requested
        if project_request.generate_image:
            generation_id = str(uuid.uuid4())
            response_data["image_generation_id"] = generation_id
            response_data["websocket_url"] = f"/api/v1/ws/image-progress/{generation_id}"
            
            # Background task for image generation
            async def background_image_generation():
                try:
                    logger.info(f"Starting background image generation for project {db_project.id}")
                    
                    async def progress_callback(progress_data):
                        await send_image_progress_update(generation_id, progress_data)
                    
                    result = await image_service.generate_architectural_visualization(
                        design_description=project_request.prompt,
                        style="modern",
                        time_of_day="day",
                        view_type="exterior",
                        progress_callback=progress_callback,
                        generation_id=generation_id
                    )
                    
                    if result["success"]:
                        await complete_image_generation(generation_id, result)
                        logger.info(f"Image generation completed for project {db_project.id}")
                    else:
                        await fail_image_generation(generation_id, result.get("error", "Unknown error"))
                        
                except Exception as e:
                    logger.error(f"Background image generation failed: {e}")
                    await fail_image_generation(generation_id, str(e))
            
            asyncio.create_task(background_image_generation())
        
        return JSONResponse(
            status_code=201,
            content=response_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complete project generation failed: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate project: {str(e)}"
        )
