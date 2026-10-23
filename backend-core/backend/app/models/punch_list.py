from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class PunchItem(Base):
    """Something to fix or finish before handover: where it is (a room of the
    floor plan), which trade fixes it, who has it, and when it is due. It goes
    open → in_progress → ready (for the PM to check) → closed, and can be reopened."""

    __tablename__ = "punch_items"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    number = Column(Integer, nullable=False)  # PL-001, PL-002, ... per project
    title = Column(String(255), nullable=False)
    description = Column(Text)
    room = Column(String(100))  # a room name from the floor plan, or "Exterior"
    trade = Column(String(50), default="general")
    priority = Column(String(20), default="medium")  # low, medium, high, critical
    status = Column(String(20), default="open")  # open, in_progress, ready, closed
    assignee = Column(String(255))
    due_date = Column(Date)
    phase_id = Column(Integer)  # a pm-mcp milestone (phase) id
    pm_record_id = Column(Integer)  # the punch_item record this is copied to in pm-mcp
    closed_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", back_populates="punch_items")

    def __repr__(self):
        return f"<PunchItem(id={self.id}, project={self.project_id}, number={self.number}, status='{self.status}')>"
