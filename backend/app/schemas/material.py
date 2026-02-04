"""
Pydantic schemas for material-related API operations.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from .common import TimestampModel


class MaterialCategoryBase(BaseModel):
    """Base material category schema."""
    name: str = Field(..., max_length=100, unique=True)
    description: Optional[str] = None
    category_type: str = Field(..., description="labor, materials, equipment, permits, etc.")


class MaterialCategoryCreate(MaterialCategoryBase):
    """Schema for creating a material category."""
    pass


class MaterialCategoryResponse(MaterialCategoryBase, TimestampModel):
    """Schema for material category response."""
    id: int

    class Config:
        from_attributes = True


class MaterialBase(BaseModel):
    """Base material schema."""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    project_id: int
    category_id: Optional[int] = None
    material_type: Optional[str] = Field(None, description="wood, concrete, metal, glass, etc.")
    unit: str = Field(..., description="sq_ft, cu_ft, linear_ft, each, etc.")
    unit_cost: float = Field(..., ge=0)
    quantity_available: float = Field(default=0.0, ge=0)
    quantity_needed: float = Field(default=0.0, ge=0)
    supplier_name: Optional[str] = None
    supplier_contact: Optional[str] = None
    supplier_website: Optional[str] = None
    is_sustainable: bool = Field(default=False)
    carbon_footprint: Optional[float] = Field(None, ge=0, description="kg CO2 per unit")
    recycled_content: Optional[float] = Field(None, ge=0, le=100, description="percentage")
    specifications: Optional[Dict[str, Any]] = Field(None, description="Technical specs and certifications")
    status: str = Field(default="available")


class MaterialCreate(MaterialBase):
    """Schema for creating a material."""
    pass


class MaterialUpdate(BaseModel):
    """Schema for updating a material."""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    category_id: Optional[int] = None
    material_type: Optional[str] = None
    unit: Optional[str] = None
    unit_cost: Optional[float] = Field(None, ge=0)
    quantity_available: Optional[float] = Field(None, ge=0)
    quantity_needed: Optional[float] = Field(None, ge=0)
    supplier_name: Optional[str] = None
    supplier_contact: Optional[str] = None
    supplier_website: Optional[str] = None
    is_sustainable: Optional[bool] = None
    carbon_footprint: Optional[float] = Field(None, ge=0)
    recycled_content: Optional[float] = Field(None, ge=0, le=100)
    specifications: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class MaterialResponse(MaterialBase, TimestampModel):
    """Schema for material response."""
    id: int
    total_cost: float
    category: Optional[MaterialCategoryResponse] = None

    class Config:
        from_attributes = True


class MaterialListResponse(BaseModel):
    """Schema for paginated material list response."""
    materials: List[MaterialResponse]
    total: int
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
    total_pages: int


class SupplierInfo(BaseModel):
    """Supplier information summary."""
    name: str
    contact: Optional[str]
    website: Optional[str]
    total_materials: int
    average_rating: Optional[float]
