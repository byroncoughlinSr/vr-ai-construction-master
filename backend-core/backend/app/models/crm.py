from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Client(Base):
    """A homeowner or company the builder is selling to or building for.

    A client moves through the sales pipeline (``stage``) and, once won, is
    linked to the project being built for them (``project_id``).
    """

    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    phone = Column(String(50))
    company = Column(String(255))

    # Pipeline
    stage = Column(String(50), nullable=False, default="new_inquiry", index=True)
    tier = Column(String(50), default="standard")  # standard, premium, vip, commercial
    source = Column(String(100))  # referral, website, walk-in, ...
    deal_value = Column(Float, default=0.0)
    win_probability = Column(Float, default=10.0)  # percent
    lost_reason = Column(Text)

    # What they want built
    site_address = Column(Text)
    preferred_style = Column(String(255))
    target_budget = Column(Float)
    target_square_feet = Column(Float)
    target_completion_date = Column(DateTime(timezone=True))
    requirements = Column(Text)  # free text from discovery
    tags = Column(JSON)  # list of strings

    # Follow-up
    next_follow_up_at = Column(DateTime(timezone=True))
    next_action = Column(String(500))
    last_contact_at = Column(DateTime(timezone=True))
    sentiment = Column(String(30))  # enthusiastic, positive, neutral, concerned

    # Written by the AI from the activity log (ai_assistant_service.client_insights)
    ai_summary = Column(Text)
    ai_insights = Column(JSON)  # {preferences: [], risks: [], next_best_action: str}
    ai_updated_at = Column(DateTime(timezone=True))

    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", back_populates="clients")
    activities = relationship(
        "ClientActivity", back_populates="client", cascade="all, delete-orphan",
        order_by="ClientActivity.occurred_at.desc()", passive_deletes=True,
    )

    def __repr__(self):
        return f"<Client(id={self.id}, name='{self.name}', stage='{self.stage}')>"


class ClientActivity(Base):
    """One entry in a client's timeline: a note, call, email, meeting, VR demo,
    site visit, or a stage change the CRM logged itself."""

    __tablename__ = "client_activities"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(30), nullable=False, default="note")
    summary = Column(String(500), nullable=False)
    details = Column(Text)
    sentiment = Column(String(30))
    action_items = Column(JSON)  # list of strings
    author = Column(String(255))
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client", back_populates="activities")

    def __repr__(self):
        return f"<ClientActivity(id={self.id}, kind='{self.kind}', client={self.client_id})>"
