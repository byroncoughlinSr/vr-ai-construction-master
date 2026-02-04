from sqlalchemy import Column, Integer, String, Text, DateTime, Float, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class MaterialCategory(Base):
    """Categories for organizing materials."""

    __tablename__ = "material_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    materials = relationship("Material", back_populates="category", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MaterialCategory(id={self.id}, name='{self.name}')>"


class Material(Base):
    """Material model for construction materials."""

    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Project relationship
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Category relationship
    category_id = Column(Integer, ForeignKey("material_categories.id"))

    # Material properties
    material_type = Column(String(50))  # wood, concrete, metal, glass, etc.
    unit = Column(String(20))  # sq_ft, cu_ft, linear_ft, each, etc.
    unit_cost = Column(Float, nullable=False)
    quantity_available = Column(Float, default=0.0)
    quantity_needed = Column(Float, default=0.0)

    # Supplier information
    supplier_name = Column(String(255))
    supplier_contact = Column(String(255))
    supplier_website = Column(String(500))

    # Sustainability data
    is_sustainable = Column(Boolean, default=False)
    carbon_footprint = Column(Float)  # kg CO2 per unit
    recycled_content = Column(Float)  # percentage

    # Additional properties
    specifications = Column(JSON)  # technical specs, certifications, etc.

    # Status
    status = Column(String(50), default="available")  # available, ordered, delivered, used

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="materials")
    category = relationship("MaterialCategory", back_populates="materials")
    design_elements = relationship("DesignElement", back_populates="material")

    @property
    def total_cost(self) -> float:
        """Calculate total cost based on quantity needed and unit cost."""
        return self.quantity_needed * self.unit_cost

    def __repr__(self):
        return f"<Material(id={self.id}, name='{self.name}', cost={self.unit_cost}/{self.unit})>"
