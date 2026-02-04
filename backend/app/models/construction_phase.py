from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class ConstructionPhase(Base):
    """Construction phases for organizing project work."""

    __tablename__ = "construction_phases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Project relationship
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Phase ordering and dependencies
    phase_order = Column(Integer, nullable=False)  # 1, 2, 3, etc.
    depends_on_phase_id = Column(Integer, ForeignKey("construction_phases.id"))

    # Timeline
    planned_start_date = Column(DateTime(timezone=True))
    planned_end_date = Column(DateTime(timezone=True))
    actual_start_date = Column(DateTime(timezone=True))
    actual_end_date = Column(DateTime(timezone=True))

    # Status and progress
    status = Column(String(50), default="pending")  # pending, in_progress, completed, delayed
    progress_percentage = Column(Float, default=0.0)

    # Budget
    budgeted_cost = Column(Float, default=0.0)
    actual_cost = Column(Float, default=0.0)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="phases")
    tasks = relationship("Task", back_populates="phase", cascade="all, delete-orphan")
    dependent_phases = relationship("ConstructionPhase", foreign_keys=[depends_on_phase_id])

    def __repr__(self):
        return f"<ConstructionPhase(id={self.id}, name='{self.name}', order={self.phase_order}, status='{self.status}')>"


class Task(Base):
    """Individual tasks within construction phases."""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Relationships
    phase_id = Column(Integer, ForeignKey("construction_phases.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Task dependencies
    depends_on_task_id = Column(Integer, ForeignKey("tasks.id"))
    task_order = Column(Integer)  # Order within phase

    # Timeline
    planned_start_date = Column(DateTime(timezone=True))
    planned_end_date = Column(DateTime(timezone=True))
    actual_start_date = Column(DateTime(timezone=True))
    actual_end_date = Column(DateTime(timezone=True))

    # Duration in days
    planned_duration_days = Column(Float)
    actual_duration_days = Column(Float)

    # Status and progress
    status = Column(String(50), default="pending")  # pending, in_progress, completed, blocked
    priority = Column(String(20), default="medium")  # low, medium, high, critical

    # Resources
    required_labor_hours = Column(Float)
    required_equipment = Column(Text)  # JSON list of equipment needed

    # Budget
    budgeted_cost = Column(Float, default=0.0)
    actual_cost = Column(Float, default=0.0)

    # Quality control
    requires_inspection = Column(Boolean, default=False)
    inspection_status = Column(String(50))  # pending, passed, failed

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    phase = relationship("ConstructionPhase", back_populates="tasks")
    project = relationship("Project", back_populates="tasks")
    dependent_tasks = relationship("Task", foreign_keys=[depends_on_task_id])
    labor_assignments = relationship("LaborAssignment", back_populates="task", cascade="all, delete-orphan")
    equipment_assignments = relationship("EquipmentAssignment", back_populates="task", cascade="all, delete-orphan")
    inspections = relationship("Inspection", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Task(id={self.id}, name='{self.name}', status='{self.status}')>"
