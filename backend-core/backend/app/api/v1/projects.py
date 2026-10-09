from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from sqlalchemy import or_, and_, func
import logging
import uuid
import asyncio

from ...database import get_db
from ...models import Project
from ...schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    ProjectListResponse, ProjectStats
)
from ...services import AIImageService
from ...services.vr_geometry_service import build_geometry_from_rooms
from .websocket import send_image_progress_update, complete_image_generation, fail_image_generation

logger = logging.getLogger(__name__)
router = APIRouter()
image_service = AIImageService()


@router.post("/", response_model=ProjectResponse)
async def create_project(
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
async def get_project_stats(db: Session = Depends(get_db)):
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
async def get_latest_project(db: Session = Depends(get_db)):
    """Return the most recently created project ID and name (for VR auto-load)."""
    project = db.query(Project).order_by(Project.id.desc()).first()
    if not project:
        raise HTTPException(status_code=404, detail="No projects found")
    logger.info(f"📡 Latest project requested → id={project.id} name='{project.name}'")
    return {"project_id": project.id, "project_name": project.name}


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific project by ID."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.from_orm(project)


@router.get("/", response_model=ProjectListResponse)
async def list_projects(
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
async def update_project(
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


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db)
):
    """Delete a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        db.delete(project)
        db.commit()
        return {"message": "Project deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to delete project: {str(e)}"
        )


@router.post("/{project_id}/load-to-vr")
async def load_project_to_vr(
    project_id: int,
    background_tasks: BackgroundTasks,
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
    """
    logger.info(f"🎮 Load-to-VR requested for project {project_id}")
    
    # Validate project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    logger.info(f"📦 Project found: '{project.name}' (id={project_id})")
    
    try:
        # Generate unique ID for image generation tracking
        generation_id = str(uuid.uuid4())
        
        # Get project description for image generation
        project_description = project.description or project.name
        
        # Start background image generation
        async def background_image_generation():
            try:
                logger.info(f"🖼️ Starting image generation for project {project_id}")
                
                # Progress callback for WebSocket updates
                async def progress_callback(progress_data):
                    await send_image_progress_update(generation_id, progress_data)
                
                # Generate architectural visualization
                result = await image_service.generate_architectural_visualization(
                    design_description=project_description,
                    style="modern",
                    time_of_day="day",
                    progress_callback=progress_callback,
                    generation_id=generation_id
                )
                
                if result["success"]:
                    await complete_image_generation(generation_id, result)
                    logger.info(f"✅ Image generation completed for project {project_id}")
                else:
                    error_msg = result.get('error', 'Unknown error')
                    await fail_image_generation(generation_id, error_msg)
                    logger.error(f"❌ Image generation failed: {error_msg}")
                    
            except Exception as e:
                logger.error(f"❌ Background image generation error: {e}", exc_info=True)
                await fail_image_generation(generation_id, str(e))
        
        # Start background task
        asyncio.create_task(background_image_generation())
        
        # Return response immediately
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
        
    except Exception as e:
        logger.error(f"❌ Load-to-VR failed for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load project to VR: {str(e)}"
        )


@router.get("/{project_id}/generate-vr")
async def generate_vr_geometry(
    project_id: int,
    include_materials: bool = Query(True),
    include_textures: bool = Query(True),
    optimize_for_vr: bool = Query(True),
    target_platform: str = Query("quest2"),
    db: Session = Depends(get_db)
):
    """
    Generate VR geometry for a project.

    This endpoint processes the project's construction phases and materials 
    to generate optimized 3D geometry suitable for VR rendering on Quest devices.
    
    Returns JSON geometry that can be loaded directly into the VR application.
    """
    logger.info(f"🥽 VR geometry requested for project {project_id}")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    logger.info(f"🏗️  Project found: '{project.name}' (id={project_id})")

    try:
        from ...models import ConstructionPhase, Material, AIGeneration

        phases = db.query(ConstructionPhase).filter(
            ConstructionPhase.project_id == project_id
        ).order_by(ConstructionPhase.phase_order).all()

        materials = db.query(Material).filter(
            Material.project_id == project_id
        ).all()

        logger.info(f"📦 DB records: {len(phases)} phases, {len(materials)} materials")

        ai_data = db.query(AIGeneration).filter(
            AIGeneration.project_id == project_id
        ).first()
        logger.info(f"🤖 AIGeneration record: {'found' if ai_data else 'not found'}")

        # Build rooms_ft — dimensions in feet, fed into the shared geometry helper.
        rooms_ft: list[dict] = []

        # Path A: use AI-generated room structure
        if ai_data and ai_data.output_data:
            try:
                response_data = ai_data.output_data if isinstance(ai_data.output_data, dict) else {}
                project_structure = response_data.get("project_structure", {})
                ai_rooms = project_structure.get("rooms", [])
                logger.info(f"🏠 AI project_structure has {len(ai_rooms)} rooms")
                rooms_ft = list(ai_rooms)
            except Exception as e:
                logger.warning(f"⚠️  AI room parse failed: {e} — falling back to phase-based parsing")
                rooms_ft = []

        # Path B: fallback — extract rooms from phase names
        if not rooms_ft:
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

        if not rooms_ft:
            logger.warning("⚠️  No rooms generated — VR scene will be empty")

        materials_payload = [
            {"material_type": m.material_type, "name": m.name} for m in materials
        ]

        geometry = build_geometry_from_rooms(
            rooms_ft=rooms_ft,
            materials=materials_payload,
            project_id=project_id,
            project_name=project.name,
            target_platform=target_platform,
            optimize_for_vr=optimize_for_vr,
        )

        logger.info(
            f"🎉 VR geometry ready: {len(geometry['rooms'])} rooms, "
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
