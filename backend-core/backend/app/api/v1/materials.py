from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from ...database import get_db
from ...models import Material, MaterialCategory
from ...schemas.material import (
    MaterialCreate, MaterialUpdate, MaterialResponse,
    MaterialListResponse, MaterialCategoryCreate,
    MaterialCategoryResponse, SupplierInfo
)

router = APIRouter()


@router.post("/", response_model=MaterialResponse)
async def create_material(
    material: MaterialCreate,
    db: Session = Depends(get_db)
):
    """Create a new material."""
    try:
        db_material = Material(**material.dict())
        db.add(db_material)
        db.commit()
        db.refresh(db_material)
        return MaterialResponse.from_orm(db_material)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create material: {str(e)}"
        )


@router.get("/{material_id}", response_model=MaterialResponse)
async def get_material(
    material_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific material by ID."""
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    return MaterialResponse.from_orm(material)


@router.get("/", response_model=MaterialListResponse)
async def list_materials(
    project_id: Optional[int] = Query(None),
    category_id: Optional[int] = Query(None),
    material_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List materials with pagination and filtering."""
    query = db.query(Material)

    # Apply filters
    if project_id:
        query = query.filter(Material.project_id == project_id)
    if category_id:
        query = query.filter(Material.category_id == category_id)
    if material_type:
        query = query.filter(Material.material_type == material_type)
    if status:
        query = query.filter(Material.status == status)
    if search:
        query = query.filter(Material.name.ilike(f"%{search}%"))

    # Get total count
    total = query.count()

    # Apply pagination
    materials = query.offset((page - 1) * page_size).limit(page_size).all()

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size

    return MaterialListResponse(
        materials=[MaterialResponse.from_orm(m) for m in materials],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.put("/{material_id}", response_model=MaterialResponse)
async def update_material(
    material_id: int,
    material_update: MaterialUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing material."""
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    try:
        update_data = material_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(material, field, value)

        db.commit()
        db.refresh(material)
        return MaterialResponse.from_orm(material)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to update material: {str(e)}"
        )


@router.delete("/{material_id}")
async def delete_material(
    material_id: int,
    db: Session = Depends(get_db)
):
    """Delete a material."""
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    try:
        db.delete(material)
        db.commit()
        return {"message": "Material deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to delete material: {str(e)}"
        )


# Material Categories endpoints
@router.post("/categories", response_model=MaterialCategoryResponse)
async def create_material_category(
    category: MaterialCategoryCreate,
    db: Session = Depends(get_db)
):
    """Create a new material category."""
    try:
        db_category = MaterialCategory(**category.dict())
        db.add(db_category)
        db.commit()
        db.refresh(db_category)
        return MaterialCategoryResponse.from_orm(db_category)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create material category: {str(e)}"
        )


@router.get("/categories", response_model=List[MaterialCategoryResponse])
async def list_material_categories(
    category_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List all material categories."""
    query = db.query(MaterialCategory)

    if category_type:
        query = query.filter(MaterialCategory.category_type == category_type)

    categories = query.all()
    return [MaterialCategoryResponse.from_orm(c) for c in categories]


@router.get("/suppliers", response_model=List[SupplierInfo])
async def list_suppliers(db: Session = Depends(get_db)):
    """List all suppliers with material counts."""
    # This is a simplified implementation
    # In a real app, you'd aggregate this data from the database
    suppliers = db.query(
        Material.supplier_name,
        Material.supplier_contact,
        Material.supplier_website,
        db.func.count(Material.id).label("total_materials")
    ).filter(
        Material.supplier_name.isnot(None)
    ).group_by(
        Material.supplier_name,
        Material.supplier_contact,
        Material.supplier_website
    ).all()

    return [
        SupplierInfo(
            name=supplier.supplier_name,
            contact=supplier.supplier_contact,
            website=supplier.supplier_website,
            total_materials=supplier.total_materials,
            average_rating=None  # Would need a rating system
        )
        for supplier in suppliers
    ]


@router.get("/project/{project_id}/summary")
async def get_project_material_summary(
    project_id: int,
    db: Session = Depends(get_db)
):
    """Get material summary for a project."""
    # Verify project exists
    from ...models import Project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get material statistics
    stats = db.query(
        db.func.count(Material.id).label("total_materials"),
        db.func.sum(Material.quantity_needed * Material.unit_cost).label("total_cost"),
        db.func.sum(Material.quantity_available).label("total_available"),
        db.func.sum(Material.quantity_needed).label("total_needed")
    ).filter(Material.project_id == project_id).first()

    return {
        "project_id": project_id,
        "total_materials": stats.total_materials or 0,
        "total_cost": float(stats.total_cost or 0),
        "total_available": float(stats.total_available or 0),
        "total_needed": float(stats.total_needed or 0),
        "shortage": max(0, float(stats.total_needed or 0) - float(stats.total_available or 0))
    }
