"""The libraries of 3D models made from photos (plant_model_service.py): plants
under /plants/models, furniture under /furniture/models.

A plant added here ("Coral rose" + a photo) gets a model in the background; any
house whose landscaping names it is then drawn with that model. Furniture works
the same way: a piece named "Grandma's armchair" is drawn with its model.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import PlantModel
from ...services import plant_model_service
from ...services.plant_model_service import PlantModelError

logger = logging.getLogger(__name__)
def make_router(kind: str) -> APIRouter:
    """The routes of one library (``kind`` "plant" or "furniture")."""
    router = APIRouter()
    example = "'Coral rose'" if kind == "plant" else "'Grandma's armchair'"

    def _get(db: Session, model_id: int) -> PlantModel:
        model = db.get(PlantModel, model_id)
        if model is None or (model.kind or "plant") != kind:
            raise HTTPException(status_code=404, detail=f"No such {kind} model")
        return model

    @router.get("/models")
    def list_models(db: Session = Depends(get_db)):
        """Everything in the library, and whether models can be made right now."""
        models = plant_model_service.list_models(db, kind)
        return {"models": [plant_model_service.serialize(m) for m in models], **plant_model_service.provider_status()}

    @router.post("/models", status_code=202)
    async def create_model(
        name: str = Form(..., description=f"What plans call it, e.g. {example}"),
        description: Optional[str] = Form(None, description="Used to draw it when there is no photo"),
        height_ft: Optional[float] = Form(None, description="Its usual height"),
        photo: Optional[UploadFile] = File(None),
        db: Session = Depends(get_db),
    ):
        """Add one from a photo (or a description) and start making its 3D model."""
        _require_provider()
        data = await photo.read(plant_model_service.MAX_PHOTO_BYTES + 1) if photo else None
        try:
            model = plant_model_service.create(
                db, name, photo=data or None, description=description, height_ft=height_ft, kind=kind,
            )
        except PlantModelError as e:
            db.rollback()
            raise HTTPException(status_code=422, detail=str(e))
        plant_model_service.start(model.id)
        return JSONResponse(status_code=202, content=plant_model_service.serialize(model))

    @router.get("/models/{model_id}")
    def get_model(model_id: int, db: Session = Depends(get_db)):
        plant_model_service.list_models(db)  # marks a job cut off by a restart
        return plant_model_service.serialize(_get(db, model_id))

    @router.post("/models/{model_id}/retry", status_code=202)
    def retry_model(model_id: int, db: Session = Depends(get_db)):
        """Make the model again (after a failure, or for a better one)."""
        model = _get(db, model_id)
        if plant_model_service.is_running(model.id):
            raise HTTPException(status_code=409, detail="This model is already being made")
        _require_provider()
        model.status, model.error = "pending", None
        db.commit()
        plant_model_service.start(model.id)
        return JSONResponse(status_code=202, content=plant_model_service.serialize(model))

    @router.delete("/models/{model_id}")
    def delete_model(model_id: int, db: Session = Depends(get_db)):
        """Remove one; houses that named it go back to the drawn version."""
        plant_model_service.delete(db, _get(db, model_id))
        return {"deleted": model_id}

    return router


def _require_provider():
    status = plant_model_service.provider_status()
    if not status["provider_ready"]:
        raise HTTPException(status_code=503, detail=status["provider_problem"])


router = make_router("plant")
furniture_router = make_router("furniture")
