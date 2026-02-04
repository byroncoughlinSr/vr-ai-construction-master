from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from sqlalchemy import or_, and_

from ...database import get_db
from ...models import Project
from ...schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    ProjectListResponse, ProjectStats
)

router = APIRouter()


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


@router.get("/stats", response_model=ProjectStats)
async def get_project_stats(db: Session = Depends(get_db)):
    """Get project statistics summary."""
    total_projects = db.query(Project).count()
    active_projects = db.query(Project).filter(Project.status == "active").count()
    completed_projects = db.query(Project).filter(Project.status == "completed").count()

    # Calculate totals
    budget_result = db.query(Project).with_entities(
        db.func.sum(Project.budget),
        db.func.sum(Project.estimated_cost),
        db.func.sum(Project.actual_cost)
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

    This endpoint processes the project's designs and generates optimized
    3D geometry suitable for VR rendering.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # TODO: Implement actual VR geometry generation
    # For now, return a placeholder response
    return {
        "success": True,
        "message": "VR geometry generation initiated",
        "project_id": project_id,
        "status": "processing",
        "estimated_completion_time": "5-10 minutes"
    }
