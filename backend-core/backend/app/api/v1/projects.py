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
        from ...models import ConstructionPhase, Task, Material

        phases = db.query(ConstructionPhase).filter(
            ConstructionPhase.project_id == project_id
        ).order_by(ConstructionPhase.phase_order).all()

        materials = db.query(Material).filter(
            Material.project_id == project_id
        ).all()

        logger.info(f"📦 DB records: {len(phases)} phases, {len(materials)} materials")

        rooms = []
        doors = []
        windows = []

        from ...models import AIGeneration
        ai_data = db.query(AIGeneration).filter(
            AIGeneration.project_id == project_id
        ).first()

        logger.info(f"🤖 AIGeneration record: {'found' if ai_data else 'not found'}")

        room_count = 0

        # Path A: use AI-generated room structure
        if ai_data and ai_data.output_data:
            import json
            try:
                response_data = ai_data.output_data if isinstance(ai_data.output_data, dict) else {}
                project_structure = response_data.get("project_structure", {})
                ai_rooms = project_structure.get("rooms", [])

                logger.info(f"🏠 AI project_structure has {len(ai_rooms)} rooms")

                packed_positions = compute_packed_positions(ai_rooms)
                for idx, ai_room in enumerate(ai_rooms):
                    room_count += 1
                    dimensions = ai_room.get("dimensions", {"length": 15.0, "width": 12.0, "height": 9.0})
                    x_offset, z_offset, eff_width = packed_positions[idx]
                    # Use row's max-width for geometry so all room walls align flush
                    geom_dims = {**dimensions, "width": eff_width}

                    room_name = ai_room.get("name", f"Room {room_count}")
                    logger.info(
                        f"  Room {room_count}: '{room_name}' "
                        f"{dimensions['length']}x{eff_width:.1f}(eff)x{dimensions['height']}ft "
                        f"@ ({x_offset:.1f}, 0, {z_offset:.1f})"
                    )

                    room = {
                        "id": room_count,
                        "name": room_name,
                        "position": {"x": x_offset, "y": 0, "z": z_offset},
                        "dimensions": dimensions,
                        "walls": generate_walls(geom_dims, x_offset, z_offset),
                        "floor": generate_floor(geom_dims, x_offset, z_offset, ai_room.get("floor_material", "carpet")),
                        "ceiling": generate_ceiling(geom_dims, x_offset, z_offset, ai_room.get("wall_material", "drywall"))
                    }
                    rooms.append(room)

                    doors.append({
                        "id": 100 + room_count,
                        "position": {"x": x_offset + dimensions["length"]/2, "y": 0, "z": z_offset},
                        "width": 3.0,
                        "height": 6.67,
                        "rotation": 90,  # EAST wall runs along Z-axis → 90° Y-rotation
                        "door_type": "interior"
                    })

                    windows.append({
                        "id": 200 + room_count,
                        "position": {"x": x_offset, "y": 3.0, "z": z_offset + dimensions["width"]/2},
                        "width": 4.0,
                        "height": 5.0,
                        "rotation": 180,  # NORTH wall runs along -X-axis → 180° Y-rotation
                        "glass_type": "double_pane"
                    })

                logger.info(f"✅ AI path: generated {room_count} rooms")
            except Exception as e:
                logger.warning(f"⚠️  AI room parse failed: {e} — falling back to phase-based parsing")

        # Path B: fallback — extract rooms from phase names
        if room_count == 0:
            # Pass 1: collect room data so we can compute packed positions
            fallback_rooms_data = []
            for phase in phases:
                name_lower = phase.name.lower()
                if any(kw in name_lower for kw in ("room", "bedroom", "kitchen", "bathroom", "garage")):
                    dimensions = {"length": 15.0, "width": 12.0, "height": 9.0}
                    if "master" in name_lower:
                        dimensions = {"length": 17.0, "width": 15.0, "height": 9.0}
                    elif "kitchen" in name_lower:
                        dimensions = {"length": 16.0, "width": 14.0, "height": 9.0}
                    elif "bathroom" in name_lower:
                        dimensions = {"length": 10.0, "width": 8.0, "height": 9.0}
                    elif "garage" in name_lower:
                        dimensions = {"length": 20.0, "width": 20.0, "height": 10.0}
                    fallback_rooms_data.append({"name": phase.name, "dimensions": dimensions})

            logger.info(f"🔄 Fallback: {len(phases)} phases → {len(fallback_rooms_data)} rooms found")
            packed_positions = compute_packed_positions(fallback_rooms_data)

            # Pass 2: generate geometry using packed positions
            for idx, room_data in enumerate(fallback_rooms_data):
                room_count += 1
                room_name = room_data["name"]
                dimensions = room_data["dimensions"]
                x_offset, z_offset, eff_width = packed_positions[idx]
                geom_dims = {**dimensions, "width": eff_width}

                logger.info(
                    f"  Room {room_count}: '{room_name}' (from phase) "
                    f"{dimensions['length']}x{eff_width:.1f}(eff)x{dimensions['height']}ft "
                    f"@ ({x_offset:.1f}, 0, {z_offset:.1f})"
                )

                room = {
                    "id": room_count,
                    "name": room_name,
                    "position": {"x": x_offset, "y": 0, "z": z_offset},
                    "dimensions": dimensions,
                    "walls": generate_walls(geom_dims, x_offset, z_offset),
                    "floor": generate_floor(geom_dims, x_offset, z_offset),
                    "ceiling": generate_ceiling(geom_dims, x_offset, z_offset)
                }
                rooms.append(room)

                doors.append({
                    "id": 100 + room_count,
                    "position": {"x": x_offset + dimensions["length"]/2, "y": 0, "z": z_offset},
                    "width": 3.0,
                    "height": 6.67,
                    "rotation": 90,  # EAST wall runs along Z-axis → 90° Y-rotation
                    "door_type": "interior"
                })

                windows.append({
                    "id": 200 + room_count,
                    "position": {"x": x_offset, "y": 3.0, "z": z_offset + dimensions["width"]/2},
                    "width": 4.0,
                    "height": 5.0,
                    "rotation": 180,  # NORTH wall runs along -X-axis → 180° Y-rotation
                    "glass_type": "double_pane"
                })

            logger.info(f"✅ Fallback path: generated {room_count} rooms from phases")

        if room_count == 0:
            logger.warning("⚠️  No rooms generated — VR scene will be empty")

        # Build material map
        material_map = {}
        for material in materials:
            material_map[material.material_type] = {
                "name": material.name,
                "color": get_material_color(material.material_type),
                "texture": get_material_texture(material.material_type)
            }
        logger.info(f"🎨 Material map: {list(material_map.keys())}")

        geometry = {
            "project_id": project_id,
            "project_name": project.name,
            "rooms": rooms,
            "doors": doors,
            "windows": windows,
            "materials": material_map,
            "spawn_position": {
                "x": rooms[0]["position"]["x"] if rooms else 0.0,
                "y": 1.6,
                "z": -3.0
            },
            "metadata": {
                "total_rooms": len(rooms),
                "total_doors": len(doors),
                "total_windows": len(windows),
                "platform": target_platform,
                "optimized": optimize_for_vr
            }
        }

        logger.info(
            f"🎉 VR geometry ready: {len(rooms)} rooms, {len(doors)} doors, "
            f"{len(windows)} windows → sending to Quest"
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


def compute_packed_positions(rooms: list, max_cols: int = 3) -> list:
    """
    Compute (x_center, z_center, effective_width) for each room.
    Rooms pack edge-to-edge in X. All rooms in the same row share the
    row's max width so their north and south walls flush perfectly —
    no gaps at the boundaries between rooms of differing depths.
    Returns list of (x_center, z_center, effective_width).
    """
    row_x_cursor: dict = {}
    row_max_width: dict = {}
    coords = []

    for idx, room in enumerate(rooms):
        row = idx // max_cols
        dims = room.get("dimensions", {"length": 15.0, "width": 12.0})
        length = float(dims.get("length", 15.0))
        width = float(dims.get("width", 12.0))

        if row not in row_x_cursor:
            row_x_cursor[row] = 0.0
            row_max_width[row] = 0.0

        x_center = row_x_cursor[row] + length / 2.0
        row_x_cursor[row] += length
        row_max_width[row] = max(row_max_width[row], width)
        coords.append((row, x_center))

    # Compute z_start per row using each row's max width
    z_starts: dict = {}
    running_z = 0.0
    for row_idx in sorted(set(r for r, _ in coords)):
        z_starts[row_idx] = running_z
        running_z += row_max_width[row_idx]

    # All rooms in a row share the same z_center (row_max_width / 2) and effective_width
    return [
        (x, z_starts[r] + row_max_width[r] / 2.0, row_max_width[r])
        for r, x in coords
    ]


def generate_walls(dimensions: dict, x_offset: float, z_offset: float) -> list:
    """Generate wall geometry for a room."""
    length = dimensions["length"]
    width = dimensions["width"]
    height = dimensions["height"]
    
    return [
        {
            "start": {"x": x_offset - length/2, "y": 0, "z": z_offset - width/2},
            "end": {"x": x_offset + length/2, "y": 0, "z": z_offset - width/2},
            "height": height,
            "material": "drywall"
        },
        {
            "start": {"x": x_offset + length/2, "y": 0, "z": z_offset - width/2},
            "end": {"x": x_offset + length/2, "y": 0, "z": z_offset + width/2},
            "height": height,
            "material": "drywall"
        },
        {
            "start": {"x": x_offset + length/2, "y": 0, "z": z_offset + width/2},
            "end": {"x": x_offset - length/2, "y": 0, "z": z_offset + width/2},
            "height": height,
            "material": "drywall"
        },
        {
            "start": {"x": x_offset - length/2, "y": 0, "z": z_offset + width/2},
            "end": {"x": x_offset - length/2, "y": 0, "z": z_offset - width/2},
            "height": height,
            "material": "drywall"
        }
    ]


def generate_floor(dimensions: dict, x_offset: float, z_offset: float, material: str = "carpet") -> dict:
    """Generate floor geometry for a room."""
    length = dimensions["length"]
    width = dimensions["width"]
    
    return {
        "vertices": [
            {"x": x_offset - length/2, "y": 0, "z": z_offset - width/2},
            {"x": x_offset + length/2, "y": 0, "z": z_offset - width/2},
            {"x": x_offset + length/2, "y": 0, "z": z_offset + width/2},
            {"x": x_offset - length/2, "y": 0, "z": z_offset + width/2}
        ],
        "material": material
    }


def generate_ceiling(dimensions: dict, x_offset: float, z_offset: float, material: str = "drywall") -> dict:
    """Generate ceiling geometry for a room."""
    length = dimensions["length"]
    width = dimensions["width"]
    height = dimensions["height"]
    
    return {
        "vertices": [
            {"x": x_offset - length/2, "y": height, "z": z_offset - width/2},
            {"x": x_offset + length/2, "y": height, "z": z_offset - width/2},
            {"x": x_offset + length/2, "y": height, "z": z_offset + width/2},
            {"x": x_offset - length/2, "y": height, "z": z_offset + width/2}
        ],
        "material": material
    }


def get_material_color(material_type: str) -> dict:
    """Get RGB color for a material type."""
    colors = {
        "wood": {"r": 0.7, "g": 0.5, "b": 0.3},
        "concrete": {"r": 0.6, "g": 0.6, "b": 0.6},
        "metal": {"r": 0.8, "g": 0.8, "b": 0.9},
        "glass": {"r": 0.7, "g": 0.9, "b": 1.0},
        "carpet": {"r": 0.7, "g": 0.6, "b": 0.5},
        "tile": {"r": 0.9, "g": 0.85, "b": 0.8},
        "drywall": {"r": 0.95, "g": 0.95, "b": 0.95}
    }
    return colors.get(material_type, {"r": 0.8, "g": 0.8, "b": 0.8})


def get_material_texture(material_type: str) -> str:
    """Get texture name for a material type."""
    textures = {
        "wood": "wood_grain",
        "concrete": "concrete_rough",
        "metal": "metal_brushed",
        "glass": "glass_clear",
        "carpet": "carpet_beige",
        "tile": "ceramic_tile",
        "drywall": "paint_white"
    }
    return textures.get(material_type, "default")
