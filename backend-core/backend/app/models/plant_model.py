from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.sql import func
from ..database import Base


class PlantModel(Base):
    """A 3D model of a real plant or piece of furniture, made from a photo (or a
    description) by ``plant_model_service``. A library shared by every house: a
    landscape item whose ``plant`` matches ``name`` (``kind`` "plant"), or a piece of
    furniture whose ``name`` matches it (``kind`` "furniture"), or whose ``model_id``
    is this id, is drawn with it. Files live under ``settings.plant_models_dir/<id>/``.
    """

    __tablename__ = "plant_models"

    id = Column(Integer, primary_key=True, index=True)
    # plant (landscape items use it) or furniture (pieces in the rooms use it)
    kind = Column(String(20), nullable=False, default="plant", server_default="plant")
    name = Column(String(120), nullable=False)  # what plans call it: "Coral rose"
    description = Column(Text)  # used to draw a picture when there is no photo
    source = Column(String(20), nullable=False)  # photo | description
    provider = Column(String(30))  # replicate | triposr, the one that made it
    status = Column(String(20), nullable=False, default="pending")  # pending, generating, ready, failed
    error = Column(Text)

    image_path = Column(String(500))  # relative to plant_models_dir
    model_path = Column(String(500))  # the normalised .glb, relative to plant_models_dir
    height_ft = Column(Float)  # usual height, when the person gave one
    aspect = Column(Float)  # width / height of the model
    triangles = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<PlantModel(id={self.id}, name='{self.name}', status='{self.status}')>"
