from sqlalchemy import Column, Integer, String, Text, DateTime, Float, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Design(Base):
    """Design model for architectural designs."""

    __tablename__ = "designs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Project relationship
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Design metadata
    design_type = Column(String(50))  # floor_plan, elevation, 3d_model, etc.
    version = Column(String(20), default="1.0")

    # VR geometry data (stored as JSON)
    geometry_data = Column(JSON)  # 3D coordinates, materials, etc.

    # Design files
    blueprint_url = Column(String(500))
    model_3d_url = Column(String(500))

    # Status
    status = Column(String(50), default="draft")  # draft, reviewed, approved, rejected

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="designs")
    elements = relationship("DesignElement", back_populates="design", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Design(id={self.id}, name='{self.name}', type='{self.design_type}')>"


class DesignElement(Base):
    """Individual elements within a design (walls, doors, windows, etc.)."""

    __tablename__ = "design_elements"

    id = Column(Integer, primary_key=True, index=True)
    design_id = Column(Integer, ForeignKey("designs.id"), nullable=False)

    # Element properties
    element_type = Column(String(50), nullable=False)  # wall, door, window, floor, etc.
    name = Column(String(255))
    position = Column(JSON)  # x, y, z coordinates
    rotation = Column(JSON)  # rotation values
    scale = Column(JSON)    # scale values
    dimensions = Column(JSON)  # width, height, depth

    # Material relationship
    material_id = Column(Integer, ForeignKey("materials.id"))

    # Additional properties (flexible JSON storage)
    properties = Column(JSON)  # color, texture, custom properties

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    design = relationship("Design", back_populates="elements")
    material = relationship("Material", back_populates="design_elements")

    def __repr__(self):
        return f"<DesignElement(id={self.id}, type='{self.element_type}', name='{self.name}')>"
