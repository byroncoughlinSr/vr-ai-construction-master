from sqlalchemy import Column, Integer, String, Text, DateTime, Float, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Project(Base):
    """Project model for construction projects."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), default="planning")  # planning, active, completed, paused

    # Budget and timeline
    budget = Column(Float)
    estimated_cost = Column(Float, default=0.0)
    actual_cost = Column(Float, default=0.0)

    # Dates
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    estimated_completion_date = Column(DateTime(timezone=True))

    # Location
    address = Column(Text)
    latitude = Column(Float)
    longitude = Column(Float)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    designs = relationship("Design", back_populates="project", cascade="all, delete-orphan")
    materials = relationship("Material", back_populates="project", cascade="all, delete-orphan")
    ai_generations = relationship("AIGeneration", back_populates="project", cascade="all, delete-orphan")
    phases = relationship("ConstructionPhase", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    labor_resources = relationship("LaborResource", back_populates="current_project")
    equipment = relationship("Equipment", back_populates="assigned_project")
    budget_items = relationship("BudgetItem", back_populates="project", cascade="all, delete-orphan")
    permits = relationship("Permit", back_populates="project", cascade="all, delete-orphan")
    inspections = relationship("Inspection", back_populates="project", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    labor_assignments = relationship("LaborAssignment", back_populates="project", cascade="all, delete-orphan")
    equipment_assignments = relationship("EquipmentAssignment", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}', status='{self.status}')>"
