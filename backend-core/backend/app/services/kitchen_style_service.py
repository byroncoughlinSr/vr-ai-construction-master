"""Saved kitchen looks (table ``kitchen_styles``), shared by every house.

A style is made once ("Farmhouse kitchen": cream raised-panel doors, glass uppers,
black granite, a dark mosaic backsplash, the stove and fridge photographed) and
any house's kitchen can then be drawn in it: a kitchen piece with ``"style":
"Farmhouse kitchen"`` (vr_furniture). The drawn counters keep stretching to fit;
only their look comes from here. The appliances are photo models from the
furniture library, which the runs leave room for at their real size.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..models import KitchenStyle, PlantModel
from .vr_exterior import color_hex
from .vr_plants import name_key

logger = logging.getLogger(__name__)

DOORS = ("flat", "shaker", "raised")
UPPERS = ("solid", "glass")
BACKSPLASHES = ("none", "tile", "mosaic")

# What a new style starts from: the drawn kitchen as it was before styles.
DEFAULT_STYLE: dict[str, Any] = {
    "cabinet": "#f2f1ec",
    "door": "flat",
    "uppers": "solid",
    "handle": "#c3c6c9",
    "crown": False,
    "top": "#e6e1d8",
    "fleck": None,
    "backsplash": "none",
    "backsplash_color": "#d9d6cf",
    "stove_model_id": None,
    "fridge_model_id": None,
}


class KitchenStyleError(ValueError):
    """A style that can't be saved (a 422 / 404 for the routes)."""


def clean_style(raw: Any, base: dict | None = None) -> dict:
    """``raw`` (as the dashboard sent it) over ``base`` (or the defaults): colours as
    hex, choices from their lists; anything unusable keeps the base's value."""
    out = dict(DEFAULT_STYLE)
    out.update({k: v for k, v in (base or {}).items() if k in DEFAULT_STYLE})
    if not isinstance(raw, dict):
        return out
    for key in ("cabinet", "handle", "top", "backsplash_color"):
        if raw.get(key):
            out[key] = color_hex(raw[key], out[key]) or out[key]
    if "fleck" in raw:
        out["fleck"] = color_hex(raw["fleck"], "") or None if raw["fleck"] else None
    for key, choices in (("door", DOORS), ("uppers", UPPERS), ("backsplash", BACKSPLASHES)):
        value = str(raw.get(key) or "").strip().lower()
        if value in choices:
            out[key] = value
    if "crown" in raw:
        out["crown"] = bool(raw["crown"])
    for key in ("stove_model_id", "fridge_model_id"):
        if key in raw:
            value = raw[key]
            out[key] = int(value) if isinstance(value, (int, float, str)) and str(value).strip().isdigit() else None
    return out


def _name(name: Any) -> str:
    name = " ".join(str(name or "").split())[:80]
    if not name:
        raise KitchenStyleError("a kitchen style needs a name")
    return name


def _check_models(db: Session, style: dict):
    for key in ("stove_model_id", "fridge_model_id"):
        if style.get(key) is not None:
            model = db.get(PlantModel, style[key])
            if model is None or model.kind != "furniture":
                raise KitchenStyleError(f"no furniture model {style[key]} for {key}")


def _taken(db: Session, name: str, other: int | None = None) -> bool:
    return any(s.id != other and name_key(s.name) == name_key(name) for s in db.query(KitchenStyle).all())


def as_dict(style: KitchenStyle) -> dict:
    return {"id": style.id, "name": style.name, **clean_style(style.style),
            "created_at": style.created_at.isoformat() if style.created_at else None}


def list_styles(db: Session) -> list[KitchenStyle]:
    return db.query(KitchenStyle).order_by(KitchenStyle.name).all()


def create(db: Session, name: Any, raw: Any) -> KitchenStyle:
    name = _name(name)
    if _taken(db, name):
        raise KitchenStyleError(f"there is a kitchen style called '{name}' already")
    style = clean_style(raw)
    _check_models(db, style)
    row = KitchenStyle(name=name, style=style)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update(db: Session, row: KitchenStyle, name: Any, raw: Any) -> KitchenStyle:
    if name is not None:
        name = _name(name)
        if _taken(db, name, row.id):
            raise KitchenStyleError(f"there is a kitchen style called '{name}' already")
        row.name = name
    style = clean_style(raw, row.style)
    _check_models(db, style)
    row.style = style
    db.commit()
    db.refresh(row)
    return row


def ready_styles(db: Session) -> list[dict]:
    """Every style as ``vr_furniture.build_furniture`` takes them: name and look, an
    appliance model only while it is in the library."""
    out = []
    for row in list_styles(db):
        style = clean_style(row.style)
        for key in ("stove_model_id", "fridge_model_id"):
            model = db.get(PlantModel, style[key]) if style[key] is not None else None
            if model is None or model.kind != "furniture":
                style[key] = None
        out.append({"id": row.id, "name": row.name, **style})
    return out
