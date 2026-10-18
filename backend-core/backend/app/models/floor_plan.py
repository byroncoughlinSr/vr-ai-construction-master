from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class FloorPlan(Base):
    """One version of a project's floor plan.

    Every change (the first plan, a dashboard edit, a voice refinement) adds a
    new row with the next ``version``; the highest version is the current plan.
    ``layout`` and ``rooms`` are the planner's ``project_structure.layout`` /
    ``.rooms`` in feet, the input to ``vr_geometry_service.build_geometry_from_rooms``.
    """

    __tablename__ = "floor_plans"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_floor_plan_version"),)

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)

    name = Column(String(255), nullable=False)  # the house name shown in VR
    layout = Column(JSON)  # nested-split tree: length, width, entry, split, parts
    rooms = Column(JSON, nullable=False)  # name, dimensions, materials, connects_to
    # Roof, wall finish and landscaping (vr_exterior.exterior_spec). A change to only
    # the outside updates the current version in place; new versions carry it over.
    exterior = Column(JSON)
    # Furniture by room name (vr_furniture.furniture_spec); handled like the exterior:
    # a furniture-only change updates the current version in place, new versions carry it over.
    furniture = Column(JSON)

    # How this version came about
    change_type = Column(String(50), nullable=False)  # generated, edited, refined, example
    change_note = Column(Text)  # the prompt, or the spoken refinement
    source = Column(String(100))  # planner that produced it (groq, ollama, gemini, dashboard, ...)

    # Rendered image of the house, once one has been generated for this version
    image_url = Column(String(500))
    image_generation_id = Column(String(64))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="floor_plans")

    @property
    def structure(self) -> dict:
        """The plan as the planner's ``project_structure``."""
        return {"layout": self.layout, "rooms": self.rooms or [], "exterior": self.exterior, "furniture": self.furniture}

    def __repr__(self):
        return f"<FloorPlan(project_id={self.project_id}, version={self.version}, name='{self.name}')>"
