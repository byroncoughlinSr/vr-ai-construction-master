"""Saved kitchen looks (kitchen_style_service.py), under /kitchen-styles.

A kitchen piece whose ``style`` names one is drawn in it, in any house.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import KitchenStyle
from ...services import kitchen_style_service
from ...services.kitchen_style_service import KitchenStyleError

router = APIRouter()


class StyleIn(BaseModel):
    name: Optional[str] = Field(None, description="What plans call it: \"Farmhouse kitchen\"")
    style: dict[str, Any] = Field(default_factory=dict, description="cabinet, door, uppers, handle, crown, top, "
                                  "fleck, backsplash, backsplash_color, stove_model_id, fridge_model_id")


def _get(db: Session, style_id: int) -> KitchenStyle:
    row = db.get(KitchenStyle, style_id)
    if row is None:
        raise HTTPException(status_code=404, detail="kitchen style not found")
    return row


@router.get("")
def list_styles(db: Session = Depends(get_db)):
    return {
        "styles": [kitchen_style_service.as_dict(s) for s in kitchen_style_service.list_styles(db)],
        "choices": {"door": kitchen_style_service.DOORS, "uppers": kitchen_style_service.UPPERS,
                    "backsplash": kitchen_style_service.BACKSPLASHES},
        "defaults": kitchen_style_service.DEFAULT_STYLE,
    }


@router.post("", status_code=201)
def create_style(body: StyleIn, db: Session = Depends(get_db)):
    try:
        return kitchen_style_service.as_dict(kitchen_style_service.create(db, body.name, body.style))
    except KitchenStyleError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/{style_id}")
def update_style(style_id: int, body: StyleIn, db: Session = Depends(get_db)):
    row = _get(db, style_id)
    try:
        return kitchen_style_service.as_dict(kitchen_style_service.update(db, row, body.name, body.style))
    except KitchenStyleError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{style_id}")
def delete_style(style_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, style_id))
    db.commit()
    return {"deleted": style_id}
