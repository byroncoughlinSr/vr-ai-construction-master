from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Permit(Base):
    """Permits required for construction projects."""

    __tablename__ = "permits"

    id = Column(Integer, primary_key=True, index=True)
    permit_number = Column(String(100), nullable=False, unique=True)
    permit_type = Column(String(100), nullable=False)  # building, electrical, plumbing, etc.

    # Project relationship
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Permit details
    description = Column(Text)
    issuing_authority = Column(String(255))  # City, County, State agency
    jurisdiction = Column(String(255))  # Specific city/county/state

    # Application details
    application_date = Column(DateTime(timezone=True))
    approval_date = Column(DateTime(timezone=True))
    expiration_date = Column(DateTime(timezone=True))
    issued_date = Column(DateTime(timezone=True))

    # Status and fees
    status = Column(String(50), default="applied")  # applied, approved, issued, expired, rejected
    application_fee = Column(Float, default=0.0)
    permit_fee = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)

    # Conditions and requirements
    conditions = Column(Text)  # Special conditions or requirements
    inspection_required = Column(Boolean, default=True)

    # Document links
    application_url = Column(String(500))
    permit_document_url = Column(String(500))

    # Contact information
    contact_name = Column(String(255))
    contact_phone = Column(String(50))
    contact_email = Column(String(255))

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="permits")
    inspections = relationship("Inspection", back_populates="permit", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Permit(id={self.id}, number='{self.permit_number}', type='{self.permit_type}', status='{self.status}')>"


class Inspection(Base):
    """Inspections for quality control and compliance."""

    __tablename__ = "inspections"

    id = Column(Integer, primary_key=True, index=True)
    inspection_type = Column(String(100), nullable=False)  # foundation, framing, electrical, final, etc.

    # Relationships
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"))  # Associated task if applicable
    permit_id = Column(Integer, ForeignKey("permits.id"))  # Associated permit if applicable

    # Inspection details
    description = Column(Text)
    inspector_name = Column(String(255))
    inspector_company = Column(String(255))
    inspector_certification = Column(String(100))

    # Scheduling
    scheduled_date = Column(DateTime(timezone=True))
    actual_date = Column(DateTime(timezone=True))
    requested_date = Column(DateTime(timezone=True))

    # Results
    status = Column(String(50), default="scheduled")  # scheduled, passed, failed, rescheduled, cancelled
    result_details = Column(Text)  # Detailed findings
    critical_findings = Column(Text)  # Critical issues that must be addressed
    recommended_actions = Column(Text)  # What needs to be done

    # Follow-up
    requires_followup = Column(Boolean, default=False)
    followup_date = Column(DateTime(timezone=True))
    followup_completed = Column(Boolean, default=False)

    # Documentation
    report_url = Column(String(500))  # Inspection report document
    photos = Column(JSON)  # List of photo URLs

    # Cost tracking
    inspection_fee = Column(Float, default=0.0)
    reinspection_fee = Column(Float, default=0.0)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="inspections")
    task = relationship("Task", back_populates="inspections")
    permit = relationship("Permit", back_populates="inspections")

    def __repr__(self):
        return f"<Inspection(id={self.id}, type='{self.inspection_type}', status='{self.status}')>"
