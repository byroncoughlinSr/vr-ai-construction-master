from sqlalchemy import JSON, Column, DateTime, Integer, String
from sqlalchemy.sql import func
from ..database import Base


class KitchenStyle(Base):
    """A saved look for kitchens, shared by every house: the cabinets, doors,
    countertop, backsplash and the photo models of its appliances
    (``kitchen_style_service.clean_style`` says what ``style`` holds). A kitchen
    piece whose ``style`` names it is drawn that way (``vr_furniture``)."""

    __tablename__ = "kitchen_styles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), nullable=False, unique=True)  # what plans call it: "Farmhouse kitchen"
    style = Column(JSON, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<KitchenStyle(id={self.id}, name='{self.name}')>"
