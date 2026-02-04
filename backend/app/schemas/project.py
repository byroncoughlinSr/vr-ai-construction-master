"""
Pydantic schemas for project-related API operations.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from .common import TimestampModel


class ProjectBase(BaseModel):
    """Base project schema with common fields."""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    status: str = Field(default="planning")
    budget: Optional[float] = Field(None, ge=0)
    estimated_cost: float = Field(default=0.0, ge=0)
    actual_cost: float = Field(default=0.0, ge=0)
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    estimated_completion_date: Optional[datetime] = None


class ProjectCreate(ProjectBase):
    """Schema for creating a new project."""
    pass


class ProjectUpdate(BaseModel):
    """Schema for updating an existing project."""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[float] = Field(None, ge=0)
    estimated_cost: Optional[float] = Field(None, ge=0)
    actual_cost: Optional[float] = Field(None, ge=0)
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    estimated_completion_date: Optional[datetime] = None


class ProjectResponse(ProjectBase, TimestampModel):
    """Schema for project response data."""
    id: int

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    """Schema for paginated project list response."""
    projects: List[ProjectResponse]
    total: int
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
    total_pages: int


class ProjectStats(BaseModel):
    """Project statistics summary."""
    total_projects: int
    active_projects: int
    completed_projects: int
    total_budget: float
    total_estimated_cost: float
    total_actual_cost: float
    average_completion_percentage: float
