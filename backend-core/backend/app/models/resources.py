from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class LaborResource(Base):
    """Labor resources available for project work."""

    __tablename__ = "labor_resources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)  # Worker name or role type
    role = Column(String(100), nullable=False)  # Electrician, Plumber, Carpenter, etc.

    # Contact information
    email = Column(String(255))
    phone = Column(String(50))

    # Skills and certifications
    skills = Column(Text)  # JSON list of skills
    certifications = Column(Text)  # JSON list of certifications

    # Availability and scheduling
    is_available = Column(Boolean, default=True)
    hourly_rate = Column(Float, nullable=False)
    max_hours_per_week = Column(Float, default=40.0)

    # Project assignment
    current_project_id = Column(Integer, ForeignKey("projects.id"))

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    current_project = relationship("Project", back_populates="labor_resources")
    assignments = relationship("LaborAssignment", back_populates="labor_resource", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<LaborResource(id={self.id}, name='{self.name}', role='{self.role}')>"


class Equipment(Base):
    """Equipment and tools available for project work."""

    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Equipment details
    equipment_type = Column(String(100), nullable=False)  # Excavator, Crane, Power Tool, etc.
    model = Column(String(100))
    serial_number = Column(String(100))

    # Ownership and rental
    owned_by_company = Column(Boolean, default=True)
    rental_company = Column(String(255))
    rental_rate_daily = Column(Float)
    rental_rate_weekly = Column(Float)

    # Maintenance and status
    maintenance_schedule = Column(Text)  # JSON maintenance schedule
    last_maintenance_date = Column(DateTime(timezone=True))
    next_maintenance_date = Column(DateTime(timezone=True))
    status = Column(String(50), default="available")  # available, in_use, maintenance, out_of_service

    # Location and assignment
    current_location = Column(String(255))
    assigned_to_project_id = Column(Integer, ForeignKey("projects.id"))

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    assigned_project = relationship("Project", back_populates="equipment")
    assignments = relationship("EquipmentAssignment", back_populates="equipment", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Equipment(id={self.id}, name='{self.name}', type='{self.equipment_type}', status='{self.status}')>"


class LaborAssignment(Base):
    """Assignment of labor resources to specific tasks."""

    __tablename__ = "labor_assignments"

    id = Column(Integer, primary_key=True, index=True)

    # Relationships
    labor_resource_id = Column(Integer, ForeignKey("labor_resources.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Assignment details
    assigned_hours = Column(Float, nullable=False)
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))

    # Status
    status = Column(String(50), default="assigned")  # assigned, working, completed

    # Cost tracking
    hourly_rate_at_assignment = Column(Float)  # Store rate at time of assignment
    total_cost = Column(Float, default=0.0)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    labor_resource = relationship("LaborResource", back_populates="assignments")
    task = relationship("Task", back_populates="labor_assignments")
    project = relationship("Project", back_populates="labor_assignments")

    def __repr__(self):
        return f"<LaborAssignment(id={self.id}, labor={self.labor_resource_id}, task={self.task_id}, hours={self.assigned_hours})>"


class EquipmentAssignment(Base):
    """Assignment of equipment to specific tasks."""

    __tablename__ = "equipment_assignments"

    id = Column(Integer, primary_key=True, index=True)

    # Relationships
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Assignment details
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    planned_duration_days = Column(Float)

    # Cost tracking
    daily_rate_at_assignment = Column(Float)
    total_cost = Column(Float, default=0.0)

    # Status
    status = Column(String(50), default="assigned")  # assigned, in_use, returned

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    equipment = relationship("Equipment", back_populates="assignments")
    task = relationship("Task", back_populates="equipment_assignments")
    project = relationship("Project", back_populates="equipment_assignments")

    def __repr__(self):
        return f"<EquipmentAssignment(id={self.id}, equipment={self.equipment_id}, task={self.task_id})>"
