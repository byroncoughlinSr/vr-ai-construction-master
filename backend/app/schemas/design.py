"""
Pydantic schemas for design-related API operations.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from .common import TimestampModel


class DesignElementBase(BaseModel):
    """Base design element schema."""
    element_type: str = Field(..., description="Type of design element (wall, door, window, etc.)")
    name: Optional[str] = None
    position: Optional[Dict[str, float]] = Field(None, description="x, y, z coordinates")
    rotation: Optional[Dict[str, float]] = Field(None, description="Rotation values")
    scale: Optional[Dict[str, float]] = Field(None, description="Scale values")
    dimensions: Optional[Dict[str, float]] = Field(None, description="width, height, depth")
    material_id: Optional[int] = None
    properties: Optional[Dict[str, Any]] = Field(None, description="Additional custom properties")


class DesignElementCreate(DesignElementBase):
    """Schema for creating a design element."""
    pass


class DesignElementUpdate(BaseModel):
    """Schema for updating a design element."""
    element_type: Optional[str] = None
    name: Optional[str] = None
    position: Optional[Dict[str, float]] = None
    rotation: Optional[Dict[str, float]] = None
    scale: Optional[Dict[str, float]] = None
    dimensions: Optional[Dict[str, float]] = None
    material_id: Optional[int] = None
    properties: Optional[Dict[str, Any]] = None


class DesignElementResponse(DesignElementBase, TimestampModel):
    """Schema for design element response."""
    id: int
    design_id: int

    class Config:
        from_attributes = True


class DesignBase(BaseModel):
    """Base design schema."""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    project_id: int
    design_type: Optional[str] = Field(None, description="floor_plan, elevation, 3d_model, etc.")
    version: str = Field(default="1.0")
    geometry_data: Optional[Dict[str, Any]] = Field(None, description="3D coordinates and materials")
    blueprint_url: Optional[str] = None
    model_3d_url: Optional[str] = None
    status: str = Field(default="draft")


class DesignCreate(DesignBase):
    """Schema for creating a design."""
    pass


class DesignUpdate(BaseModel):
    """Schema for updating a design."""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    design_type: Optional[str] = None
    version: Optional[str] = None
    geometry_data: Optional[Dict[str, Any]] = None
    blueprint_url: Optional[str] = None
    model_3d_url: Optional[str] = None
    status: Optional[str] = None


class DesignResponse(DesignBase, TimestampModel):
    """Schema for design response."""
    id: int
    elements: List[DesignElementResponse] = []

    class Config:
        from_attributes = True


class VRGeometryRequest(BaseModel):
    """Request for VR geometry generation."""
    include_materials: bool = Field(default=True)
    include_textures: bool = Field(default=True)
    optimize_for_vr: bool = Field(default=True)
    target_platform: str = Field(default="quest2", description="quest2, oculus, steamvr, etc.")


class VRGeometryResponse(BaseModel):
    """Response for VR geometry generation."""
    success: bool
    geometry_data: Dict[str, Any]
    material_count: int
    vertex_count: int
    triangle_count: int
    file_size_mb: float
    download_url: Optional[str] = None
