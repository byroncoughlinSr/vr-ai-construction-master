from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from ...database import get_db
from ...models import Design, DesignElement
from ...schemas.design import (
    DesignCreate, DesignUpdate, DesignResponse,
    DesignElementCreate, DesignElementUpdate, DesignElementResponse,
    VRGeometryRequest, VRGeometryResponse
)

router = APIRouter()


@router.post("/", response_model=DesignResponse)
async def create_design(
    design: DesignCreate,
    db: Session = Depends(get_db)
):
    """Create a new design for a project."""
    try:
        db_design = Design(**design.dict())
        db.add(db_design)
        db.commit()
        db.refresh(db_design)
        return DesignResponse.from_orm(db_design)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create design: {str(e)}"
        )


@router.get("/{design_id}", response_model=DesignResponse)
async def get_design(
    design_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific design by ID."""
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")
    return DesignResponse.from_orm(design)


@router.get("/", response_model=List[DesignResponse])
async def list_designs(
    project_id: Optional[int] = Query(None),
    design_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List designs with optional filtering."""
    query = db.query(Design)

    if project_id:
        query = query.filter(Design.project_id == project_id)
    if design_type:
        query = query.filter(Design.design_type == design_type)
    if status:
        query = query.filter(Design.status == status)

    designs = query.all()
    return [DesignResponse.from_orm(d) for d in designs]


@router.put("/{design_id}", response_model=DesignResponse)
async def update_design(
    design_id: int,
    design_update: DesignUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing design."""
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")

    try:
        update_data = design_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(design, field, value)

        db.commit()
        db.refresh(design)
        return DesignResponse.from_orm(design)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to update design: {str(e)}"
        )


@router.delete("/{design_id}")
async def delete_design(
    design_id: int,
    db: Session = Depends(get_db)
):
    """Delete a design."""
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")

    try:
        db.delete(design)
        db.commit()
        return {"message": "Design deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to delete design: {str(e)}"
        )


# Design Elements endpoints
@router.post("/{design_id}/elements", response_model=DesignElementResponse)
async def create_design_element(
    design_id: int,
    element: DesignElementCreate,
    db: Session = Depends(get_db)
):
    """Create a new design element."""
    # Verify design exists
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")

    try:
        db_element = DesignElement(design_id=design_id, **element.dict())
        db.add(db_element)
        db.commit()
        db.refresh(db_element)
        return DesignElementResponse.from_orm(db_element)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create design element: {str(e)}"
        )


@router.get("/{design_id}/elements", response_model=List[DesignElementResponse])
async def list_design_elements(
    design_id: int,
    element_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List all elements for a design."""
    query = db.query(DesignElement).filter(DesignElement.design_id == design_id)

    if element_type:
        query = query.filter(DesignElement.element_type == element_type)

    elements = query.all()
    return [DesignElementResponse.from_orm(e) for e in elements]


@router.put("/{design_id}/elements/{element_id}", response_model=DesignElementResponse)
async def update_design_element(
    design_id: int,
    element_id: int,
    element_update: DesignElementUpdate,
    db: Session = Depends(get_db)
):
    """Update a design element."""
    element = db.query(DesignElement).filter(
        DesignElement.id == element_id,
        DesignElement.design_id == design_id
    ).first()

    if not element:
        raise HTTPException(status_code=404, detail="Design element not found")

    try:
        update_data = element_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(element, field, value)

        db.commit()
        db.refresh(element)
        return DesignElementResponse.from_orm(element)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to update design element: {str(e)}"
        )


@router.delete("/{design_id}/elements/{element_id}")
async def delete_design_element(
    design_id: int,
    element_id: int,
    db: Session = Depends(get_db)
):
    """Delete a design element."""
    element = db.query(DesignElement).filter(
        DesignElement.id == element_id,
        DesignElement.design_id == design_id
    ).first()

    if not element:
        raise HTTPException(status_code=404, detail="Design element not found")

    try:
        db.delete(element)
        db.commit()
        return {"message": "Design element deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to delete design element: {str(e)}"
        )


@router.post("/{design_id}/generate-vr", response_model=VRGeometryResponse)
async def generate_vr_geometry(
    design_id: int,
    request: VRGeometryRequest,
    db: Session = Depends(get_db)
):
    """
    Generate VR geometry for a design.

    This endpoint processes design elements and generates optimized
    3D geometry suitable for VR rendering.
    """
    design = db.query(Design).filter(Design.id == design_id).first()
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")

    # TODO: Implement actual VR geometry generation
    # For now, return a placeholder response
    return VRGeometryResponse(
        success=True,
        geometry_data={
            "vertices": [],
            "faces": [],
            "materials": [],
            "textures": []
        },
        material_count=0,
        vertex_count=0,
        triangle_count=0,
        file_size_mb=0.0,
        download_url=None
    )
