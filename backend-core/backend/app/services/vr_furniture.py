"""Furniture for the rooms, built from triangles the way ``vr_plants`` builds plants.

A floor plan may carry a ``furniture`` description (column ``floor_plans.furniture``),
by room name, sizes in feet:

    {"auto": true,
     "rooms": {"Dining Room": [{"type": "dining table", "seats": 6, "name": "oak farmhouse table"}],
               "Living Room": [{"type": "sofa", "color": "navy", "place": "back"},
                               {"type": "coffee table"}],
               "Office": []}}

``furniture_spec`` cleans what the AI (or the dashboard) sends into that shape:
``find_piece`` matches each item's words against ``PIECES`` ("couch" → sofa,
"queen bed" → bed, size queen), color words tint it. ``"auto": true`` furnishes
every room the description leaves out by what it is (``auto_items``: a bedroom gets
a bed, nightstands and a dresser); an empty list keeps a room empty.

``build_furniture`` places each piece in its room, in metres: against a free stretch
of wall (never in front of a doorway, and under a window only when it is lower than
the sill), in the middle (tables, islands), in a corner (lamps, plants) or beside
another piece (nightstands by the bed, a coffee table in front of the sofa, chairs
round the table). ``x``/``z`` (feet from the room's front-left corner) put a piece
exactly there. Each piece is a low-poly mesh in metres, base on the floor and front
toward +z, shared by every piece of the same kind, size and color; a piece whose
name matches a 3D model made from a photo (``plant_model_service``, kind
"furniture") is drawn with that model instead. Pieces that do not fit are listed
as notes.
"""

from __future__ import annotations

import logging
import math
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .vr_exterior import NAMED_COLORS, color_hex
from .vr_geometry_service import FT_TO_M, WALL_T, _EPS
from .vr_plants import PlantMesh, SPECIES, _point_in, _shade, find_species, name_key, plant_mesh, tube

logger = logging.getLogger(__name__)

Vec = tuple[float, float, float]

FLOOR_TOP = 0.025  # the floor slabs are 0.05 world units thick, centred on 0 (1 unit = 1 m)
MAX_PER_ROOM = 30
MAX_SEATS = 12
MAX_FT = 40.0


# --- Catalogue -------------------------------------------------------------------

@dataclass(frozen=True)
class Piece:
    builder: str  # which function draws it
    width: float  # feet, along the wall it stands against (or its long side)
    depth: float  # feet, front to back
    height: float
    place: str  # wall | center | corner | beside_bed | front_of_sofa | beside_sofa | facing_sofa
    #             | opposite_sofa | front_of_desk | front_of_island | under
    color: str  # its main material: upholstery, wood, cabinets, ...
    seats: int = 0  # chairs it comes with (dining tables, desks)
    label: str = ""  # what to call it in notes


WOOD = "#8b6a4f"
DARK_WOOD = "#5a3f2e"
WHITE = "#f2f1ec"
STEEL = "#c3c6c9"
BLACK = "#262626"
FABRIC = "#7d8a96"

PIECES: dict[str, Piece] = {
    # Seating
    "sofa": Piece("sofa", 7.0, 3.2, 2.8, "wall", FABRIC),
    "loveseat": Piece("sofa", 5.0, 3.1, 2.8, "wall", FABRIC),
    "sectional": Piece("sectional", 9.0, 6.5, 2.8, "wall", FABRIC),
    "armchair": Piece("armchair", 2.8, 2.9, 3.0, "facing_sofa", "#a39282"),
    "recliner": Piece("armchair", 3.0, 3.2, 3.4, "facing_sofa", "#6b5446"),
    "dining chair": Piece("chair", 1.5, 1.7, 3.0, "wall", WOOD),
    "office chair": Piece("office_chair", 2.0, 2.0, 3.3, "front_of_desk", BLACK),
    "bar stool": Piece("stool", 1.3, 1.3, 2.5, "front_of_island", DARK_WOOD),
    "bench": Piece("bench", 4.0, 1.3, 1.5, "wall", WOOD),
    # Tables
    "dining table": Piece("table", 6.0, 3.3, 2.5, "center", WOOD, seats=6),
    "kitchen table": Piece("table", 4.0, 3.0, 2.5, "center", WOOD, seats=4),
    "round table": Piece("round_table", 4.0, 4.0, 2.5, "center", WOOD, seats=4),
    "coffee table": Piece("coffee_table", 4.0, 2.0, 1.5, "front_of_sofa", WOOD),
    "side table": Piece("side_table", 1.8, 1.8, 2.0, "beside_sofa", WOOD),
    "console table": Piece("console", 4.0, 1.2, 2.6, "wall", DARK_WOOD),
    "desk": Piece("desk", 4.5, 2.2, 2.5, "wall", WOOD, seats=1),
    # Bedroom
    "bed": Piece("bed", 5.0, 6.9, 3.6, "wall", "#9fb3c8"),
    "crib": Piece("crib", 2.5, 4.4, 3.3, "wall", WHITE),
    "nightstand": Piece("nightstand", 1.8, 1.5, 2.1, "beside_bed", WOOD),
    "dresser": Piece("dresser", 5.0, 1.7, 2.8, "wall", WOOD),
    "chest of drawers": Piece("dresser", 3.0, 1.6, 4.0, "wall", WOOD),
    "wardrobe": Piece("wardrobe", 4.0, 2.0, 6.5, "wall", WOOD),
    # Storage and media
    "bookshelf": Piece("bookshelf", 3.0, 1.1, 6.0, "wall", WOOD),
    "tv stand": Piece("tv_stand", 5.0, 1.5, 1.8, "opposite_sofa", DARK_WOOD),
    "sideboard": Piece("cabinet", 5.0, 1.6, 2.8, "wall", DARK_WOOD),
    "piano": Piece("piano", 5.0, 2.0, 4.0, "wall", BLACK),
    # Kitchen
    "counter": Piece("counter", 10.0, 2.1, 3.0, "wall", WHITE),
    "kitchen island": Piece("island", 6.0, 3.0, 3.0, "center", WHITE),
    "refrigerator": Piece("fridge", 3.0, 2.6, 5.9, "wall", STEEL),
    "stove": Piece("stove", 2.5, 2.2, 3.0, "wall", STEEL),
    # Bathroom and laundry
    "toilet": Piece("toilet", 1.7, 2.4, 2.6, "wall", WHITE),
    "vanity": Piece("vanity", 3.0, 1.8, 2.8, "wall", WHITE),
    "bathtub": Piece("bathtub", 5.0, 2.5, 1.8, "wall", WHITE),
    "shower": Piece("shower", 3.0, 3.0, 6.8, "corner", STEEL),
    "washer": Piece("washer", 2.25, 2.3, 3.2, "wall", WHITE),
    "dryer": Piece("washer", 2.25, 2.3, 3.2, "wall", WHITE, label="dryer"),
    # Decor
    "rug": Piece("rug", 8.0, 5.0, 0.05, "under", "#b5a48a"),
    "floor lamp": Piece("lamp", 1.4, 1.4, 5.3, "corner", "#efe6cf"),
    "potted plant": Piece("potted_plant", 1.6, 1.6, 4.0, "corner", "#c0623a"),
    # Anything else the person names: a plain box of the size they give.
    "custom": Piece("custom", 2.0, 2.0, 3.0, "wall", "#b0a89c"),
}

_ALIASES = {
    "couch": "sofa", "settee": "loveseat", "love seat": "loveseat", "l shaped sofa": "sectional",
    "l shaped couch": "sectional", "sectional sofa": "sectional", "sectional couch": "sectional",
    "accent chair": "armchair", "lounge chair": "armchair", "club chair": "armchair",
    "reading chair": "armchair", "wingback": "armchair", "easy chair": "armchair",
    "lazy boy": "recliner", "la z boy": "recliner", "desk chair": "office chair",
    "counter stool": "bar stool", "stool": "bar stool", "barstool": "bar stool",
    "dinner table": "dining table", "farmhouse table": "dining table", "breakfast table": "round table",
    "bistro table": "round table", "end table": "side table", "accent table": "side table",
    "entry table": "console table", "hall table": "console table", "sofa table": "console table",
    "writing desk": "desk", "computer desk": "desk", "work desk": "desk",
    "king bed": "bed", "queen bed": "bed", "twin bed": "bed", "full bed": "bed", "double bed": "bed",
    "single bed": "bed", "bunk bed": "bed", "daybed": "bed", "bedside table": "nightstand",
    "night stand": "nightstand", "night table": "nightstand", "chest": "chest of drawers",
    "tallboy": "chest of drawers", "armoire": "wardrobe", "closet cabinet": "wardrobe",
    "bookcase": "bookshelf", "book shelf": "bookshelf", "shelves": "bookshelf", "shelf": "bookshelf",
    "shelving": "bookshelf", "tv": "tv stand", "television": "tv stand", "media console": "tv stand",
    "media cabinet": "tv stand", "entertainment center": "tv stand", "tv console": "tv stand",
    "buffet": "sideboard", "credenza": "sideboard", "hutch": "sideboard",
    "upright piano": "piano", "grand piano": "piano", "kitchen counter": "counter",
    "countertop": "counter", "kitchen cabinet": "counter", "cabinetry": "counter",
    "island": "kitchen island", "fridge": "refrigerator", "range": "stove", "oven": "stove",
    "cooktop": "stove", "commode": "toilet", "bathroom sink": "vanity", "kitchen sink": "counter",
    "bath": "bathtub", "tub": "bathtub", "soaking tub": "bathtub", "shower stall": "shower",
    "walk in shower": "shower", "washing machine": "washer", "clothes dryer": "dryer",
    "area rug": "rug", "carpet": "rug", "runner": "rug", "lamp": "floor lamp",
    "standing lamp": "floor lamp", "plant": "potted plant", "houseplant": "potted plant",
    "house plant": "potted plant", "indoor plant": "potted plant", "fiddle leaf fig": "potted plant",
    "ficus": "potted plant", "monstera": "potted plant",
}
# Words that only mean a piece in context: "a table" in the dining room is the dining table.
_CONTEXT = {
    "chair": {"dining": "dining chair", "kitchen": "dining chair", "office": "office chair", "": "armchair"},
    "table": {"dining": "dining table", "kitchen": "kitchen table", "living": "coffee table",
              "office": "desk", "bedroom": "nightstand", "": "side table"},
    "sink": {"kitchen": "counter", "laundry": "counter", "": "vanity"},
    "cabinet": {"kitchen": "counter", "bathroom": "vanity", "powder": "vanity", "": "sideboard"},
}
# Feet (width, depth) of a bed by its size word.
BED_SIZES = {
    "king": (6.6, 7.0), "california king": (6.2, 7.3), "queen": (5.2, 6.9), "full": (4.6, 6.5),
    "double": (4.6, 6.5), "twin": (3.4, 6.5), "single": (3.4, 6.5), "crib": (2.5, 4.4),
}
WOODS = {
    "oak": "#a67c52", "white oak": "#c2a07a", "walnut": "#5c4033", "cherry": "#8e4a35",
    "mahogany": "#6b2f24", "maple": "#c9a77c", "pine": "#c99e67", "teak": "#9a6a3f",
    "birch": "#d4b98c", "ebony": "#2e2621", "espresso": "#3b2a22", "bamboo": "#c8ad73",
    "driftwood": "#a39582", "rustic": "#7a5a3c", "reclaimed": "#7a5a3c",
}


def _lookup_keys() -> list[tuple[str, str]]:
    names = {name_key(name): name for name in PIECES if name != "custom"}
    names.update({name_key(alias): target for alias, target in _ALIASES.items()})
    return sorted(names.items(), key=lambda kv: -len(kv[0]))


_LOOKUP = _lookup_keys()


def room_kind(name: Any) -> str:
    """What a room is for, from its name: living, dining, kitchen, bedroom, primary,
    kids, bathroom, powder, office, laundry, entry, sunroom, media, or ""."""
    n = f" {name_key(name)} "
    for kind, words in _ROOM_WORDS:
        if any(f" {w} " in n for w in words):
            return kind
    return ""


# First match wins: "Hall Bathroom" is a bathroom, "Primary Closet" is storage.
_ROOM_WORDS = (
    ("powder", ("powder", "half bath", "wc", "half bathroom")),
    ("bathroom", ("bathroom", "bath", "ensuite", "en suite", "restroom", "lavatory")),
    ("storage", ("closet", "pantry", "storage", "stair", "stairway", "walk in")),
    ("garage", ("garage", "carport", "workshop")),
    ("primary", ("primary", "master", "owner suite")),
    ("kids", ("nursery", "kid", "child", "children")),
    ("bedroom", ("bedroom", "guest room", "bunk room", "sleeping")),
    ("kitchen", ("kitchen", "kitchenette")),
    ("dining", ("dining", "breakfast", "nook")),
    ("office", ("office", "study", "library", "workspace", "studio")),
    ("laundry", ("laundry", "utility", "mudroom", "mud room")),
    ("media", ("media", "theater", "theatre", "game room", "rec room", "recreation", "playroom")),
    ("sunroom", ("sunroom", "sun room", "conservatory", "porch room")),
    ("entry", ("entry", "foyer", "vestibule", "entrance")),
    ("living", ("living", "family", "great room", "den", "lounge", "sitting", "parlor", "parlour")),
    ("hall", ("hallway", "hall", "corridor")),
)


def find_piece(text: Any, room: str = "") -> str | None:
    """The piece a description names ("navy velvet couch" → sofa), or None.
    ``room`` (a ``room_kind``) decides what a plain "chair" or "table" is."""
    key = f" {name_key(text)} "
    for alias, piece in _LOOKUP:
        if f" {alias} " in key:
            return piece
    for word, by_room in _CONTEXT.items():
        if f" {word} " in key:
            area = {"primary": "bedroom", "kids": "bedroom", "media": "living", "sunroom": "living"}.get(room, room)
            return by_room.get(area, by_room[""])
    return None


def _color_word(text: Any) -> str | None:
    words = name_key(text)
    for name in sorted(NAMED_COLORS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name_key(name))}\b", words):
            return NAMED_COLORS[name]
    return None


def _wood_word(text: Any) -> str | None:
    words = name_key(text)
    for name in sorted(WOODS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", words):
            return WOODS[name]
    return None


# --- Cleaning the description ---------------------------------------------------

_SIDES = ("front", "back", "left", "right")
_SIDE_ALIASES = {"rear": "back", "far": "back", "street": "front", "east": "right", "west": "left",
                 "north": "back", "south": "front"}
_PLACES = _SIDES + ("center", "corner")


def _num(value: Any, lo: float, hi: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < lo or number > hi:
        return None
    return number


def _side(value: Any, options=_SIDES) -> str | None:
    text = name_key(value)
    for word in text.split():
        word = _SIDE_ALIASES.get(word, word)
        if word in options:
            return word
    if "middle" in text or "centre" in text:
        return "center" if "center" in options else None
    return None


def _clean_item(raw: Any, room: str) -> dict | None:
    if isinstance(raw, str):
        raw = {"type": raw}
    if not isinstance(raw, dict):
        return None
    words = " ".join(str(raw.get(k) or "") for k in ("type", "name", "label"))
    kind = find_piece(raw.get("type"), room) or find_piece(words, room)
    name = re.sub(r"\s+", " ", str(raw.get("name") or raw.get("label") or "")).strip()[:60]
    if not kind:
        if not (name or raw.get("type")):
            return None
        kind = "custom"
        name = name or re.sub(r"\s+", " ", str(raw.get("type"))).strip()[:60]
    item: dict[str, Any] = {"type": kind}
    if name:
        item["name"] = name
    for key in ("x", "z"):
        value = _num(raw.get(key), -1.0, MAX_FT * 4)
        if value is not None:
            item[key] = round(value, 1)
    if ("x" in item) != ("z" in item):
        item.pop("x", None)
        item.pop("z", None)
    for key in ("width", "depth", "height"):
        value = _num(raw.get(key), 0.1, MAX_FT)
        if value is not None:
            item[key] = round(value, 1)
    facing = _side(raw.get("facing"))
    if facing:
        item["facing"] = facing
    place = _side(raw.get("place") or raw.get("wall") or raw.get("position"), _PLACES)
    if place:
        item["place"] = place
    if raw.get("color"):
        color = color_hex(raw.get("color"), "") or WOODS.get(name_key(raw.get("color")), "")
        if color:
            item["color"] = color
    material = _wood_word(raw.get("material")) or _wood_word(words)
    if material:
        item["wood"] = material
    seats = _num(raw.get("seats") if raw.get("seats") is not None else raw.get("chairs"), 0, MAX_SEATS)
    if seats is not None and PIECES[kind].builder in ("table", "round_table", "desk", "island"):
        item["seats"] = int(seats)
    count = _num(raw.get("count") or raw.get("quantity"), 1, MAX_SEATS)
    if count is not None and int(count) > 1:
        item["count"] = int(count)
    size = next((s for s in sorted(BED_SIZES, key=len, reverse=True) if re.search(rf"\b{s}\b", words.lower())), None)
    if kind == "bed":
        size = _side(raw.get("size"), tuple(BED_SIZES)) or name_key(raw.get("size")) or size
        if size in BED_SIZES:
            item["size"] = size
    if kind in ("dining table", "kitchen table") and ("round" in words.lower() or _key(raw.get("shape")) == "round"):
        item["type"] = "round table"
    model_id = raw.get("model_id")
    if isinstance(model_id, (int, float, str)) and str(model_id).strip().isdigit():
        item["model_id"] = int(str(model_id).strip())
    return item


def _key(value: Any) -> str:
    return re.sub(r"[\s-]+", "_", str(value or "").strip().lower())


def furniture_spec(raw: Any) -> dict | None:
    """Clean a ``furniture`` description (as the AI or the dashboard sent it).

    Takes ``{"auto": bool, "rooms": {name: [items]}}``, a ``{name: [items]}`` map or
    a list of items that each name their ``room``. Returns the stored form or None.
    """
    if isinstance(raw, list):
        rooms: dict[str, list] = {}
        for item in raw:
            if isinstance(item, dict) and str(item.get("room") or "").strip():
                rooms.setdefault(str(item["room"]).strip(), []).append(item)
        raw = {"rooms": rooms}
    if not isinstance(raw, dict):
        return None
    spec: dict[str, Any] = {}
    if "auto" in raw:
        spec["auto"] = bool(raw.get("auto")) and str(raw.get("auto")).strip().lower() not in ("false", "0", "no")
    rooms_raw = raw.get("rooms")
    if not isinstance(rooms_raw, dict):
        rooms_raw = {k: v for k, v in raw.items() if k != "auto" and isinstance(v, list)}
    rooms_out: dict[str, list] = {}
    for name, items in rooms_raw.items():
        name = re.sub(r"\s+", " ", str(name or "")).strip()[:80]
        if not name or not isinstance(items, list):
            continue
        kind = room_kind(name)
        clean = [i for i in (_clean_item(r, kind) for r in items[:MAX_PER_ROOM * 2]) if i]
        rooms_out[name] = clean[:MAX_PER_ROOM]
    if rooms_out:
        spec["rooms"] = rooms_out
    return spec or None


def merge_furniture(current: dict | None, change: dict | None) -> dict | None:
    """``current`` with ``change`` applied: rooms it lists are replaced (an empty
    list empties one), the others are kept; its ``auto`` wins when given."""
    if not change:
        return current
    out: dict[str, Any] = {k: v for k, v in (current or {}).items() if k != "rooms"}
    rooms = {k: v for k, v in ((current or {}).get("rooms") or {}).items()}
    lower = {k.lower(): k for k in rooms}
    for name, items in (change.get("rooms") or {}).items():
        rooms.pop(lower.get(name.lower(), name), None)
        rooms[name] = items
    if "auto" in change:
        out["auto"] = change["auto"]
    if rooms:
        out["rooms"] = rooms
    return out or None


def rename_furniture_rooms(spec: dict | None, mapping: dict[str, str]) -> dict | None:
    """``spec`` with room names renamed (``mapping`` keys lower-case)."""
    if not spec or not spec.get("rooms") or not mapping:
        return spec
    return {**spec, "rooms": {mapping.get(k.strip().lower(), k): v for k, v in spec["rooms"].items()}}


def prune_furniture(spec: dict | None, room_names: list[str]) -> dict | None:
    """Drop the furniture of rooms the plan no longer has."""
    if not spec or not spec.get("rooms"):
        return spec
    names = {n.strip().lower() for n in room_names}
    rooms = {k: v for k, v in spec["rooms"].items() if k.strip().lower() in names}
    out = {k: v for k, v in spec.items() if k != "rooms"}
    if rooms:
        out["rooms"] = rooms
    return out or None


def summary(spec: dict | None) -> dict:
    """The furniture as the refine prompt shows it: ``{room: "sofa, coffee table, ..."}``,
    plus whether rooms left out are furnished automatically."""
    out: dict[str, Any] = {"auto": bool((spec or {}).get("auto"))}
    for room, items in ((spec or {}).get("rooms") or {}).items():
        out[room] = items
    return out


# --- Furnishing a room automatically ----------------------------------------------

def auto_items(name: str, length_m: float, width_m: float) -> list[dict]:
    """What a room is furnished with when the plan asks for ``auto`` furniture."""
    kind = room_kind(name)
    short, long_ = sorted((length_m, width_m))
    area = length_m * width_m
    if kind in ("living", "media"):
        items = [{"type": "sofa"}, {"type": "coffee table"}, {"type": "rug"}, {"type": "tv stand"}]
        if short >= 3.3:
            items.append({"type": "armchair"})
        if kind == "living":
            items.append({"type": "floor lamp"})
            if area >= 16:
                items.append({"type": "potted plant"})
        return items
    if kind == "dining":
        if area < 9:
            return [{"type": "round table", "seats": 4}]
        seats = 8 if long_ >= 4.8 and short >= 3.4 else 6 if long_ >= 3.6 else 4
        items = [{"type": "dining table", "seats": seats}]
        if area >= 14:
            items.append({"type": "sideboard"})
        return items
    if kind == "kitchen":
        items: list[dict] = [{"type": "counter"}]
        if short >= 3.6 and long_ >= 3.4:
            items += [{"type": "kitchen island", "seats": 3 if long_ >= 4.2 else 2}]
        elif area >= 12:
            items.append({"type": "round table", "seats": 4})
        return items
    if kind in ("primary", "bedroom", "kids"):
        if kind == "kids" and "nursery" in name.lower():
            return [{"type": "crib"}, {"type": "dresser"}, {"type": "armchair"}]
        size = "king" if kind == "primary" and short >= 3.6 else "twin" if short < 3.0 or kind == "kids" else "queen"
        items = [{"type": "bed", "size": size}, {"type": "nightstand"}]
        if short >= 3.0:
            items.append({"type": "nightstand"})
        items.append({"type": "dresser"})
        if kind == "primary" and area >= 18:
            items.append({"type": "armchair"})
        if kind == "kids":
            items.append({"type": "bookshelf"})
        return items
    if kind == "bathroom":
        items = [{"type": "toilet"}, {"type": "vanity"}]
        if long_ >= 2.3 and area >= 4.5:
            items.append({"type": "bathtub"})
        elif area >= 3.5:
            items.append({"type": "shower"})
        return items
    if kind == "powder":
        return [{"type": "toilet"}, {"type": "vanity", "width": 2.0}]
    if kind == "office":
        items = [{"type": "desk"}, {"type": "bookshelf"}]
        if "library" in name.lower():
            items.append({"type": "bookshelf"})
        if area >= 12:
            items.append({"type": "armchair"})
        return items
    if kind == "laundry":
        if "mud" in name.lower():
            return [{"type": "bench"}]
        return [{"type": "washer"}, {"type": "dryer"}]
    if kind == "sunroom":
        return [{"type": "armchair"}, {"type": "armchair"}, {"type": "side table"}, {"type": "potted plant"},
                {"type": "potted plant"}]
    if kind == "entry" and area >= 4:
        return [{"type": "console table"}, {"type": "potted plant"}]
    return []


# --- Mesh building ------------------------------------------------------------------

def box(m: PlantMesh, color: str, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float,
        bottom: bool = False):
    """An axis-aligned box (the floor side only when ``bottom``)."""
    a, b, c, d = (x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)
    m.quad(color, a, d, c, b)  # top
    m.quad(color, (x0, y0, z1), (x1, y0, z1), c, d)  # front (+z)
    m.quad(color, (x1, y0, z0), (x0, y0, z0), a, b)  # back
    m.quad(color, (x0, y0, z0), (x0, y0, z1), d, a)  # left
    m.quad(color, (x1, y0, z1), (x1, y0, z0), b, c)  # right
    if bottom:
        m.quad(color, (x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))


def disc(m: PlantMesh, color: str, cx: float, cz: float, y0: float, y1: float, r: float, sides: int = 14):
    """A short upright cylinder with a top."""
    tube(m, color, (cx, y0, cz), (cx, y1, cz), r, r, sides, cap=True)


def front_disc(m: PlantMesh, color: str, cx: float, cy: float, z0: float, z1: float, r: float, sides: int = 16):
    """A cylinder lying along z (a washer door, a knob), capped at the front."""
    tube(m, color, (cx, cy, z0), (cx, cy, z1), r, r, sides, cap=True)


def _legs(m: PlantMesh, color: str, W: float, D: float, top: float, inset: float, t: float,
          round_: bool = False, cx: float = 0.0, cz: float = 0.0):
    """Four legs under a ``W`` × ``D`` top centred on (cx, cz)."""
    for sx in (-1, 1):
        for sz in (-1, 1):
            x, z = cx + sx * (W / 2 - inset - t / 2), cz + sz * (D / 2 - inset - t / 2)
            if round_:
                tube(m, color, (x, 0, z), (x, top, z), t / 2, t / 2 * 0.8, 6)
            else:
                box(m, color, x - t / 2, x + t / 2, 0, top, z - t / 2, z + t / 2)


def _sofa_body(m: PlantMesh, c: dict, x0: float, x1: float, zb: float, zf: float, H: float,
               arm_l: bool, arm_r: bool, cushions: int, back: bool = True):
    seat, arm_h, back_t = 0.42, min(0.64, H * 0.75), 0.22
    frame, cushion, legs = _shade(c["main"], 0.82), c["main"], c["wood"]
    a = min(0.2, (x1 - x0) * 0.12)
    _legs(m, legs, x1 - x0, zf - zb, 0.1, 0.04, 0.05, cx=(x0 + x1) / 2, cz=(zb + zf) / 2)
    box(m, frame, x0, x1, 0.1, seat - 0.08, zb, zf)
    if back:
        box(m, frame, x0 + (a if arm_l else 0), x1 - (a if arm_r else 0), seat - 0.08, H * 0.82, zb, zb + back_t)
    if arm_l:
        box(m, frame, x0, x0 + a, 0.1, arm_h, zb, zf)
    if arm_r:
        box(m, frame, x1 - a, x1, 0.1, arm_h, zb, zf)
    ix0, ix1 = x0 + (a if arm_l else 0.02), x1 - (a if arm_r else 0.02)
    step = (ix1 - ix0) / cushions
    for k in range(cushions):
        cx0, cx1 = ix0 + k * step + 0.008, ix0 + (k + 1) * step - 0.008
        box(m, cushion, cx0, cx1, seat - 0.08, seat + 0.04, zb + (back_t if back else 0.02), zf - 0.02)
        if back:
            box(m, _shade(cushion, 1.06), cx0, cx1, seat + 0.04, H - 0.02, zb + back_t, zb + back_t + 0.17)


def _cushions(width: float) -> int:
    return 1 if width < 1.2 else 2 if width < 1.9 else 3


def _sofa(m, W, D, H, c, o):
    _sofa_body(m, c, -W / 2, W / 2, -D / 2, D / 2, H, True, True, _cushions(W))


def _armchair(m, W, D, H, c, o):
    _sofa_body(m, c, -W / 2, W / 2, -D / 2, D / 2, H, True, True, 1)


def _sectional(m, W, D, H, c, o):
    main_d = min(1.0, D * 0.48)
    cw = min(1.0, W * 0.38)
    _sofa_body(m, c, -W / 2, W / 2 - cw, -D / 2, -D / 2 + main_d, H, True, False, _cushions(W - cw))
    # The chaise: the right end runs forward, with its back only along the wall.
    _sofa_body(m, c, W / 2 - cw, W / 2, -D / 2, D / 2, H, False, True, 1, back=False)
    box(m, _shade(c["main"], 0.82), W / 2 - cw, W / 2 - min(0.2, cw * 0.2), 0.34, H * 0.82, -D / 2, -D / 2 + 0.22)


def _chair(m, W, D, H, c, o):
    wood, seat = c["wood"], 0.46
    t = 0.035
    _legs(m, wood, W, D, seat - 0.03, 0.02, t)
    box(m, c.get("seat", wood), -W / 2, W / 2, seat - 0.03, seat + 0.01, -D / 2, D / 2)
    for sx in (-1, 1):
        x = sx * (W / 2 - 0.02 - t / 2)
        box(m, wood, x - t / 2, x + t / 2, seat, H, -D / 2 + 0.02, -D / 2 + 0.02 + t)
    box(m, wood, -W / 2 + 0.03, W / 2 - 0.03, H - 0.16, H - 0.04, -D / 2 + 0.02, -D / 2 + 0.05)
    box(m, wood, -W / 2 + 0.03, W / 2 - 0.03, seat + 0.14, seat + 0.2, -D / 2 + 0.02, -D / 2 + 0.05)


def _office_chair(m, W, D, H, c, o):
    dark, main = "#2f3133", c["main"]
    for k in range(5):
        ang = 2 * math.pi * k / 5
        tube(m, dark, (0, 0.06, 0), (math.cos(ang) * W * 0.42, 0.04, math.sin(ang) * D * 0.42), 0.025, 0.02, 4)
        disc(m, BLACK, math.cos(ang) * W * 0.42, math.sin(ang) * D * 0.42, 0, 0.05, 0.03, 6)
    tube(m, STEEL, (0, 0.06, 0), (0, 0.42, 0), 0.025, 0.025, 8)
    box(m, main, -0.25, 0.25, 0.42, 0.5, -0.24, 0.26)
    box(m, main, -0.23, 0.23, 0.58, H, -0.27, -0.2)
    box(m, dark, -0.03, 0.03, 0.45, 0.62, -0.26, -0.22)


def _stool(m, W, D, H, c, o):
    wood, r = c["wood"], min(W, D) * 0.4
    for k in range(4):
        ang = math.pi / 4 + k * math.pi / 2
        tube(m, wood, (math.cos(ang) * r * 1.05, 0.02, math.sin(ang) * r * 1.05),
             (math.cos(ang) * r * 0.6, H - 0.05, math.sin(ang) * r * 0.6), 0.018, 0.016, 5)
    for k in range(4):
        a0, a1 = math.pi / 4 + k * math.pi / 2, math.pi / 4 + (k + 1) * math.pi / 2
        y = H * 0.3
        tube(m, wood, (math.cos(a0) * r * 0.93, y, math.sin(a0) * r * 0.93),
             (math.cos(a1) * r * 0.93, y, math.sin(a1) * r * 0.93), 0.012, 0.012, 4)
    disc(m, c.get("seat", _shade(wood, 1.1)), 0, 0, H - 0.05, H, r * 1.05, 14)


def _bench(m, W, D, H, c, o):
    wood = c["wood"]
    box(m, wood, -W / 2, W / 2, H - 0.05, H, -D / 2, D / 2)
    for sx in (-1, 1):
        x = sx * (W / 2 - 0.08)
        box(m, _shade(wood, 0.88), x - 0.03, x + 0.03, 0, H - 0.05, -D / 2 + 0.03, D / 2 - 0.03)
    box(m, _shade(wood, 0.88), -W / 2 + 0.08, W / 2 - 0.08, 0.12, 0.16, -0.03, 0.03)


def _table(m, W, D, H, c, o):
    wood = c["wood"]
    box(m, wood, -W / 2, W / 2, H - 0.045, H, -D / 2, D / 2)
    box(m, _shade(wood, 0.9), -W / 2 + 0.06, W / 2 - 0.06, H - 0.12, H - 0.045, -D / 2 + 0.06, D / 2 - 0.06)
    _legs(m, _shade(wood, 0.9), W, D, H - 0.045, 0.06, 0.07)


def _round_table(m, W, D, H, c, o):
    wood, r = c["wood"], min(W, D) / 2
    disc(m, wood, 0, 0, H - 0.045, H, r, 20)
    tube(m, _shade(wood, 0.9), (0, 0.05, 0), (0, H - 0.045, 0), 0.07, 0.06, 10)
    disc(m, _shade(wood, 0.85), 0, 0, 0, 0.05, r * 0.45, 12)


def _coffee_table(m, W, D, H, c, o):
    wood = c["wood"]
    box(m, wood, -W / 2, W / 2, H - 0.04, H, -D / 2, D / 2)
    box(m, _shade(wood, 0.92), -W / 2 + 0.06, W / 2 - 0.06, 0.1, 0.13, -D / 2 + 0.06, D / 2 - 0.06)
    _legs(m, _shade(wood, 0.85), W, D, H - 0.04, 0.03, 0.05)


def _side_table(m, W, D, H, c, o):
    wood = c["wood"]
    box(m, wood, -W / 2, W / 2, H - 0.035, H, -D / 2, D / 2)
    box(m, _shade(wood, 0.92), -W / 2 + 0.04, W / 2 - 0.04, H * 0.35, H * 0.38, -D / 2 + 0.04, D / 2 - 0.04)
    _legs(m, _shade(wood, 0.85), W, D, H - 0.035, 0.02, 0.04)


def _console(m, W, D, H, c, o):
    wood = c["wood"]
    box(m, wood, -W / 2, W / 2, H - 0.035, H, -D / 2, D / 2)
    box(m, _shade(wood, 0.9), -W / 2 + 0.03, W / 2 - 0.03, H - 0.16, H - 0.035, -D / 2 + 0.03, D / 2 - 0.03)
    box(m, _shade(wood, 0.95), -W / 2 + 0.05, W / 2 - 0.05, 0.12, 0.15, -D / 2 + 0.05, D / 2 - 0.05)
    _legs(m, _shade(wood, 0.85), W, D, H - 0.035, 0.03, 0.045)


def _cabinet_body(m, W, D, H, color, drawers_rows: int, cols: int, foot: float = 0.08, doors: bool = False):
    """A cabinet standing on short feet with drawer or door fronts on its front."""
    box(m, _shade(color, 0.9), -W / 2, W / 2, foot, H - 0.03, -D / 2, D / 2 - 0.015)
    box(m, color, -W / 2 - 0.01, W / 2 + 0.01, H - 0.03, H, -D / 2, D / 2 + 0.01)
    _legs(m, _shade(color, 0.7), W, D, foot, 0.04, 0.04)
    gap = 0.012
    rows = max(1, drawers_rows)
    fh = (H - 0.03 - foot - 0.03) / rows
    fw = (W - 0.04) / cols
    for r in range(rows):
        for k in range(cols):
            x0 = -W / 2 + 0.02 + k * fw + gap / 2
            y0 = foot + 0.015 + r * fh + gap / 2
            box(m, color, x0, x0 + fw - gap, y0, y0 + fh - gap, D / 2 - 0.015, D / 2)
            # A handle: drawers in the middle, doors by the opening edge.
            hx = (x0 + fw / 2 - 0.05, x0 + fw / 2 + 0.05) if not doors else (
                (x0 + fw - gap - 0.05, x0 + fw - gap - 0.03) if k % 2 == 0 else (x0 + 0.03, x0 + 0.05))
            hy = (y0 + fh / 2 - 0.01, y0 + fh / 2 + 0.01) if not doors else (y0 + fh / 2 - 0.06, y0 + fh / 2 + 0.06)
            box(m, STEEL, hx[0], hx[1], hy[0], hy[1], D / 2, D / 2 + 0.02)


def _dresser(m, W, D, H, c, o):
    _cabinet_body(m, W, D, H, c["wood"], 3 if H < 1.0 else 5, 2 if W > 1.0 else 1)


def _nightstand(m, W, D, H, c, o):
    _cabinet_body(m, W, D, H * 0.85, c["wood"], 2, 1)
    # A lamp on it.
    disc(m, "#d8d2c4", 0, 0, H * 0.85, H * 0.85 + 0.02, 0.06, 10)
    tube(m, "#8a8580", (0, H * 0.85 + 0.02, 0), (0, H * 0.85 + 0.25, 0), 0.012, 0.012, 6)
    tube(m, "#efe6cf", (0, H * 0.85 + 0.2, 0), (0, H * 0.85 + 0.36, 0), 0.12, 0.08, 12, cap=True)


def _wardrobe(m, W, D, H, c, o):
    _cabinet_body(m, W, D, H, c["wood"], 1, 2, foot=0.06, doors=True)


def _cabinet(m, W, D, H, c, o):
    _cabinet_body(m, W, D, H, c["wood"], 1, max(2, round(W / 0.5)), doors=True)


_BOOK_COLORS = ("#7a2e2e", "#2e4a7a", "#3f6b3a", "#c9a227", "#e8e2d0", "#4a3a5e", "#a4482a", "#2b2b2b")


def _bookshelf(m, W, D, H, c, o):
    wood = c["wood"]
    t = 0.025
    box(m, wood, -W / 2, -W / 2 + t, 0, H, -D / 2, D / 2)
    box(m, wood, W / 2 - t, W / 2, 0, H, -D / 2, D / 2)
    box(m, wood, -W / 2, W / 2, H - t, H, -D / 2, D / 2)
    box(m, _shade(wood, 0.8), -W / 2 + t, W / 2 - t, 0, H - t, -D / 2, -D / 2 + 0.012)
    shelves = max(3, int(H / 0.36))
    step = (H - 0.08) / shelves
    rng = random.Random(f"books/{round(W, 2)}/{round(H, 2)}")
    for s in range(shelves):
        y = 0.06 + s * step
        box(m, wood, -W / 2 + t, W / 2 - t, y - t, y, -D / 2, D / 2)
        if s == shelves - 1 and rng.random() < 0.5:
            continue  # the top shelf is often left for other things
        x = -W / 2 + t + 0.02
        while x < W / 2 - t - 0.08:
            bw = rng.uniform(0.02, 0.05)
            bh = min(step - 0.04, rng.uniform(0.18, 0.3))
            if rng.random() < 0.12:
                x += rng.uniform(0.05, 0.15)  # a gap
                continue
            box(m, rng.choice(_BOOK_COLORS), x, x + bw, y, y + bh, -D / 2 + 0.03, D / 2 - rng.uniform(0.03, 0.08))
            x += bw + 0.004


def _tv_stand(m, W, D, H, c, o):
    _cabinet_body(m, W, D, H, c["wood"], 1, 3, doors=True)
    sw = min(W * 0.85, 1.6)
    sh = sw * 9 / 16
    box(m, "#1a1a1a", -0.15, 0.15, H, H + 0.02, -0.1, 0.1)
    box(m, "#1a1a1a", -0.03, 0.03, H + 0.02, H + 0.12, -0.03, 0.01)
    box(m, "#202020", -sw / 2, sw / 2, H + 0.1, H + 0.1 + sh, -0.03, 0.01)
    box(m, "#0d1117", -sw / 2 + 0.015, sw / 2 - 0.015, H + 0.115, H + 0.085 + sh, 0.01, 0.014)


def _piano(m, W, D, H, c, o):
    body = c["main"]
    box(m, body, -W / 2, W / 2, 0.06, H, -D / 2, D / 2 - 0.25)
    box(m, body, -W / 2, -W / 2 + 0.06, 0, 0.75, -D / 2, D / 2)
    box(m, body, W / 2 - 0.06, W / 2, 0, 0.75, -D / 2, D / 2)
    box(m, body, -W / 2 + 0.06, W / 2 - 0.06, 0.68, 0.73, -D / 2, D / 2 - 0.05)
    box(m, "#f4f2ea", -W / 2 + 0.08, W / 2 - 0.08, 0.73, 0.75, D / 2 - 0.2, D / 2 - 0.05)
    keys = int((W - 0.16) / 0.0235)
    for k in range(keys):
        if k % 7 in (0, 1, 3, 4, 5):
            x = -W / 2 + 0.08 + (k + 0.7) * 0.0235
            box(m, "#111111", x, x + 0.012, 0.75, 0.765, D / 2 - 0.2, D / 2 - 0.1)
    box(m, _shade(body, 1.3), -W * 0.3, W * 0.3, 0.9, 1.15, D / 2 - 0.26, D / 2 - 0.25)


def _counter(m, W, D, H, c, o):
    """Base cabinets with a countertop; the auto kitchen adds a fridge, a range and a sink."""
    cab, top = c["main"], c.get("top", "#e6e1d8")
    fridge_w = 0.9 if o.get("fridge") else 0.0
    x0 = -W / 2 + fridge_w
    if fridge_w:
        _fridge_at(m, -W / 2, -W / 2 + fridge_w - 0.02, D, 1.8)
    box(m, "#3a3a3a", x0, W / 2, 0, 0.1, -D / 2, D / 2 - 0.07)
    box(m, _shade(cab, 0.9), x0, W / 2, 0.1, H - 0.04, -D / 2, D / 2 - 0.02)
    box(m, top, x0 - 0.01, W / 2 + 0.01, H - 0.04, H, -D / 2, D / 2 + 0.02)
    run = W / 2 - x0
    range_x = None
    if o.get("range") and run >= 2.0:
        range_x = x0 + run * 0.55
        _range_at(m, range_x, D, H)
    sink_x = x0 + run * 0.22 if range_x is not None else x0 + run * 0.5
    if o.get("sink") and run >= 1.0:
        box(m, "#9aa0a6", sink_x - 0.38, sink_x + 0.38, H, H + 0.004, -D / 2 + 0.12, D / 2 - 0.1)
        box(m, "#5f6368", sink_x - 0.35, sink_x + 0.35, H + 0.004, H + 0.006, -D / 2 + 0.15, D / 2 - 0.13)
        tube(m, STEEL, (sink_x, H, -D / 2 + 0.07), (sink_x, H + 0.3, -D / 2 + 0.07), 0.015, 0.015, 6)
        tube(m, STEEL, (sink_x, H + 0.3, -D / 2 + 0.07), (sink_x, H + 0.28, -D / 2 + 0.25), 0.013, 0.012, 6)
    # Door and drawer fronts between the appliances.
    spans = [(x0, range_x - 0.38)] if range_x is not None else [(x0, W / 2)]
    if range_x is not None:
        spans.append((range_x + 0.38, W / 2))
    for a, b in spans:
        n = max(1, round((b - a) / 0.6))
        fw = (b - a) / n
        for k in range(n):
            fx0 = a + k * fw + 0.006
            fx1 = fx0 + fw - 0.012
            box(m, cab, fx0, fx1, 0.12, H - 0.22, D / 2 - 0.02, D / 2)
            box(m, cab, fx0, fx1, H - 0.2, H - 0.06, D / 2 - 0.02, D / 2)
            box(m, STEEL, (fx0 + fx1) / 2 - 0.06, (fx0 + fx1) / 2 + 0.06, H - 0.14, H - 0.12, D / 2, D / 2 + 0.02)
    if o.get("upper"):
        y0, y1, ud = 1.38, 2.12, 0.33
        box(m, _shade(cab, 0.9), x0, W / 2, y0, y1, -D / 2, -D / 2 + ud - 0.02)
        n = max(1, round(run / 0.5))
        fw = run / n
        for k in range(n):
            fx0 = x0 + k * fw + 0.006
            box(m, cab, fx0, fx0 + fw - 0.012, y0 + 0.01, y1 - 0.01, -D / 2 + ud - 0.02, -D / 2 + ud)
        if range_x is not None:
            box(m, STEEL, range_x - 0.38, range_x + 0.38, y0 - 0.1, y0 + 0.05, -D / 2, -D / 2 + 0.45)


def _fridge_at(m, x0: float, x1: float, D: float, H: float):
    box(m, STEEL, x0, x1, 0, H, -D / 2, D / 2 - 0.03)
    box(m, _shade(STEEL, 1.05), x0 + 0.01, x1 - 0.01, H * 0.36, H - 0.01, D / 2 - 0.03, D / 2)
    box(m, _shade(STEEL, 1.05), x0 + 0.01, x1 - 0.01, 0.02, H * 0.36 - 0.012, D / 2 - 0.03, D / 2)
    for y0, y1 in ((H * 0.45, H * 0.85), (H * 0.1, H * 0.3)):
        hx = (x0 + x1) / 2 - 0.02
        box(m, "#7d8287", hx, hx + 0.025, y0, y1, D / 2, D / 2 + 0.04)


def _range_at(m, cx: float, D: float, H: float):
    box(m, STEEL, cx - 0.38, cx + 0.38, 0, H - 0.04, -D / 2, D / 2)
    box(m, "#1b1b1b", cx - 0.38, cx + 0.38, H - 0.04, H - 0.01, -D / 2, D / 2)
    for bx in (-0.18, 0.18):
        for bz in (-0.13, 0.13):
            disc(m, "#3b3b3b", cx + bx, bz, H - 0.01, H, 0.09, 12)
    box(m, "#111a22", cx - 0.28, cx + 0.28, 0.25, 0.6, D / 2, D / 2 + 0.005)
    box(m, "#7d8287", cx - 0.3, cx + 0.3, 0.68, 0.7, D / 2, D / 2 + 0.04)


def _island(m, W, D, H, c, o):
    cab, top = c["main"], c.get("top", "#e6e1d8")
    over = 0.28  # the stools tuck under the front
    box(m, "#3a3a3a", -W / 2 + 0.05, W / 2 - 0.05, 0, 0.1, -D / 2 + 0.07, D / 2 - over - 0.05)
    box(m, _shade(cab, 0.9), -W / 2, W / 2, 0.1, H - 0.04, -D / 2, D / 2 - over)
    box(m, top, -W / 2 - 0.02, W / 2 + 0.02, H - 0.04, H, -D / 2 - 0.02, D / 2)
    n = max(1, round(W / 0.6))
    fw = W / n
    for k in range(n):
        fx0 = -W / 2 + k * fw + 0.006
        box(m, cab, fx0, fx0 + fw - 0.012, 0.12, H - 0.06, -D / 2 - 0.02, -D / 2)
        box(m, STEEL, fx0 + fw / 2 - 0.06, fx0 + fw / 2 + 0.06, H - 0.14, H - 0.12, -D / 2 - 0.04, -D / 2 - 0.02)


def _fridge(m, W, D, H, c, o):
    _fridge_at(m, -W / 2, W / 2, D, H)


def _stove(m, W, D, H, c, o):
    _range_at(m, 0.0, D, H)


def _toilet(m, W, D, H, c, o):
    white = c["main"]
    box(m, white, -0.22, 0.22, 0.4, 0.78, -D / 2, -D / 2 + 0.2)
    box(m, _shade(white, 0.95), -0.23, 0.23, 0.78, 0.8, -D / 2 - 0.005, -D / 2 + 0.205)
    zc = -D / 2 + 0.2 + 0.24
    tube(m, white, (0, 0, zc), (0, 0.38, zc), 0.13, 0.2, 14)
    disc(m, _shade(white, 0.97), 0, zc, 0.38, 0.41, 0.2, 14)
    box(m, white, -0.1, 0.1, 0.2, 0.42, -D / 2 + 0.18, zc - 0.1)


def _vanity(m, W, D, H, c, o):
    cab = c.get("wood_cab", c["wood"])
    _cabinet_body(m, W, D, 0.82, cab, 1, max(1, round(W / 0.5)), doors=True)
    box(m, "#e8e4dc", -W / 2 - 0.01, W / 2 + 0.01, 0.82, 0.85, -D / 2, D / 2 + 0.01)
    sinks = 2 if W >= 1.5 else 1
    for k in range(sinks):
        sx = 0 if sinks == 1 else (k - 0.5) * W / 2
        disc(m, "#ffffff", sx, 0.03, 0.85, 0.87, 0.18, 14)
        disc(m, "#d9dde0", sx, 0.03, 0.87, 0.872, 0.15, 14)
        tube(m, STEEL, (sx, 0.85, -D / 2 + 0.06), (sx, 1.05, -D / 2 + 0.06), 0.014, 0.014, 6)
        tube(m, STEEL, (sx, 1.05, -D / 2 + 0.06), (sx, 1.03, -D / 2 + 0.17), 0.012, 0.012, 6)
        mw = min(0.75, W / sinks * 0.85)
        box(m, "#3a3a3a", sx - mw / 2 - 0.02, sx + mw / 2 + 0.02, 1.03, 1.82, -D / 2, -D / 2 + 0.02)
        box(m, "#c9d3d8", sx - mw / 2, sx + mw / 2, 1.05, 1.8, -D / 2 + 0.02, -D / 2 + 0.025)


def _bathtub(m, W, D, H, c, o):
    white, t = c["main"], 0.08
    box(m, white, -W / 2, W / 2, 0, 0.12, -D / 2, D / 2)
    box(m, white, -W / 2, W / 2, 0.12, H, -D / 2, -D / 2 + t)
    box(m, white, -W / 2, W / 2, 0.12, H, D / 2 - t, D / 2)
    box(m, white, -W / 2, -W / 2 + t, 0.12, H, -D / 2 + t, D / 2 - t)
    box(m, white, W / 2 - t, W / 2, 0.12, H, -D / 2 + t, D / 2 - t)
    box(m, "#dfe9ee", -W / 2 + t, W / 2 - t, 0.12, 0.125, -D / 2 + t, D / 2 - t)
    tube(m, STEEL, (W / 2 - 0.2, H, -D / 2 + 0.04), (W / 2 - 0.2, H + 0.12, -D / 2 + 0.04), 0.015, 0.015, 6)
    tube(m, STEEL, (W / 2 - 0.2, H + 0.12, -D / 2 + 0.04), (W / 2 - 0.2, H + 0.1, -D / 2 + 0.16), 0.013, 0.012, 6)


def _shower(m, W, D, H, c, o):
    metal = c["main"]
    box(m, "#f4f4f2", -W / 2, W / 2, 0, 0.08, -D / 2, D / 2)
    box(m, "#c8cdd0", -0.05, 0.05, 0.08, 0.082, -0.05, 0.05)
    for x, z in ((W / 2 - 0.02, D / 2 - 0.02), (-W / 2 + 0.02, D / 2 - 0.02)):
        box(m, metal, x - 0.015, x + 0.015, 0.08, H, z - 0.015, z + 0.015)
    box(m, metal, -W / 2, W / 2, H - 0.03, H, D / 2 - 0.035, D / 2 - 0.005)
    box(m, metal, W / 2 - 0.035, W / 2 - 0.005, H - 0.03, H, -D / 2, D / 2)
    tube(m, metal, (0, 1.95, -D / 2), (0, 1.98, -D / 2 + 0.25), 0.012, 0.012, 6)
    disc(m, metal, 0, -D / 2 + 0.27, 1.9, 1.96, 0.08, 12)
    box(m, metal, -0.04, 0.04, 1.0, 1.1, -D / 2, -D / 2 + 0.03)


def _washer(m, W, D, H, c, o):
    white = c["main"]
    box(m, white, -W / 2, W / 2, 0, H, -D / 2, D / 2)
    box(m, "#d9dcde", -W / 2, W / 2, H - 0.14, H, D / 2, D / 2 + 0.01)
    front_disc(m, "#9aa0a6", 0, H * 0.45, D / 2, D / 2 + 0.03, 0.22, 18)
    front_disc(m, "#2c3e50", 0, H * 0.45, D / 2 + 0.03, D / 2 + 0.035, 0.17, 18)
    front_disc(m, "#555555", W / 2 - 0.12, H - 0.07, D / 2 + 0.01, D / 2 + 0.03, 0.03, 10)


def _bed(m, W, D, H, c, o):
    wood, bedding = c["wood"], c["main"]
    frame_top, mattress_top = 0.32, 0.58
    _legs(m, _shade(wood, 0.85), W, D, 0.12, 0.03, 0.06)
    box(m, wood, -W / 2, W / 2, 0.12, frame_top, -D / 2 + 0.05, D / 2)
    box(m, "#f4f2ec", -W / 2 + 0.03, W / 2 - 0.03, frame_top, mattress_top, -D / 2 + 0.08, D / 2 - 0.02)
    # The duvet over all but the pillows, hanging a little over the sides.
    box(m, bedding, -W / 2 + 0.01, W / 2 - 0.01, mattress_top - 0.18, mattress_top + 0.04,
        -D / 2 + 0.55, D / 2 + 0.01)
    box(m, _shade(bedding, 0.9), -W / 2 + 0.01, W / 2 - 0.01, mattress_top - 0.02, mattress_top + 0.05,
        D / 2 - 0.45, D / 2 + 0.015)
    pillows = 1 if W < 1.3 else 2
    pw = (W - 0.16) / pillows
    for k in range(pillows):
        px = -W / 2 + 0.08 + k * pw
        box(m, "#ffffff", px + 0.02, px + pw - 0.02, mattress_top, mattress_top + 0.12, -D / 2 + 0.12, -D / 2 + 0.5)
    box(m, wood, -W / 2 - 0.02, W / 2 + 0.02, 0.0, max(H, 1.0), -D / 2, -D / 2 + 0.06)
    if o.get("crib"):
        for zf in (D / 2 - 0.03,):
            box(m, wood, -W / 2, W / 2, 0.9, 0.95, zf - 0.03, zf)
        for side in (-1, 1):
            box(m, wood, side * W / 2 - 0.03, side * W / 2, 0.9, 0.95, -D / 2, D / 2)
        n = int(W / 0.09)
        for k in range(1, n):
            x = -W / 2 + k * W / n
            box(m, wood, x - 0.01, x + 0.01, frame_top, 0.9, D / 2 - 0.03, D / 2)


def _crib(m, W, D, H, c, o):
    _bed(m, W, D, min(H, 1.0), {**c, "main": "#f2e6d8"}, {"crib": True})


def _rug(m, W, D, H, c, o):
    main = c["main"]
    border = 0.1
    box(m, main, -W / 2 + border, W / 2 - border, 0, 0.012, -D / 2 + border, D / 2 - border)
    edge = _shade(main, 0.72)
    box(m, edge, -W / 2, W / 2, 0, 0.011, -D / 2, -D / 2 + border)
    box(m, edge, -W / 2, W / 2, 0, 0.011, D / 2 - border, D / 2)
    box(m, edge, -W / 2, -W / 2 + border, 0, 0.011, -D / 2 + border, D / 2 - border)
    box(m, edge, W / 2 - border, W / 2, 0, 0.011, -D / 2 + border, D / 2 - border)


def _lamp(m, W, D, H, c, o):
    disc(m, "#3b3b3b", 0, 0, 0, 0.03, min(W, D) * 0.3, 12)
    tube(m, "#5a5a5a", (0, 0.03, 0), (0, H - 0.3, 0), 0.012, 0.012, 6)
    tube(m, c["main"], (0, H - 0.38, 0), (0, H, 0), min(W, D) * 0.34, min(W, D) * 0.24, 14, cap=True)


def _potted_plant(m, W, D, H, c, o):
    pot_h = min(0.45, H * 0.3)
    r = min(W, D) * 0.28
    tube(m, c["main"], (0, 0, 0), (0, pot_h, 0), r * 0.75, r, 12)
    disc(m, "#4a3626", 0, 0, pot_h - 0.04, pot_h - 0.02, r * 0.95, 12)
    species = o.get("species") or ("shade tree" if H > 1.4 else "fern")
    sp = SPECIES[species]
    plant = plant_mesh(species, 0, sp.leaf, sp.flower)
    size = min(W, D) * 0.95
    _point_in(m, plant, (0, pot_h - 0.03, 0), (size, H - pot_h, size), 20)


def _custom(m, W, D, H, c, o):
    main = c["main"]
    box(m, _shade(main, 0.92), -W / 2, W / 2, 0, H - 0.03, -D / 2, D / 2)
    box(m, main, -W / 2 - 0.01, W / 2 + 0.01, H - 0.03, H, -D / 2 - 0.01, D / 2 + 0.01)


def _desk(m, W, D, H, c, o):
    """A top on a panel leg at the left and a drawer pedestal at the right."""
    wood = c["wood"]
    pw = min(0.42, W * 0.32)
    box(m, wood, -W / 2, W / 2, H - 0.035, H, -D / 2, D / 2)
    box(m, _shade(wood, 0.9), -W / 2 + 0.02, -W / 2 + 0.06, 0, H - 0.035, -D / 2 + 0.03, D / 2 - 0.03)
    box(m, _shade(wood, 0.9), -W / 2 + 0.06, W / 2 - pw, H - 0.3, H - 0.035, -D / 2 + 0.03, -D / 2 + 0.05)
    # _cabinet_body builds round the origin: build the pedestal apart and move it.
    pedestal = PlantMesh()
    _cabinet_body(pedestal, pw, D - 0.06, H - 0.035, _shade(wood, 0.95), 3, 1, foot=0.03)
    dx = W / 2 - pw / 2 - 0.02
    for color, pts in pedestal.groups.items():
        m.groups.setdefault(color, []).extend((x + dx, y, z) for x, y, z in pts)


BUILDERS = {
    "sofa": _sofa, "sectional": _sectional, "armchair": _armchair, "chair": _chair,
    "office_chair": _office_chair, "stool": _stool, "bench": _bench, "table": _table,
    "round_table": _round_table, "coffee_table": _coffee_table, "side_table": _side_table,
    "console": _console, "desk": _desk, "bed": _bed, "crib": _crib, "nightstand": _nightstand,
    "dresser": _dresser, "wardrobe": _wardrobe, "bookshelf": _bookshelf, "tv_stand": _tv_stand,
    "cabinet": _cabinet, "piano": _piano, "counter": _counter, "island": _island, "fridge": _fridge,
    "stove": _stove, "toilet": _toilet, "vanity": _vanity, "bathtub": _bathtub, "shower": _shower,
    "washer": _washer, "rug": _rug, "lamp": _lamp, "potted_plant": _potted_plant, "custom": _custom,
}


@lru_cache(maxsize=512)
def piece_mesh(builder: str, W: float, D: float, H: float, colors: tuple, options: tuple) -> PlantMesh:
    """One piece in metres: base at y = 0, centred on x and z, front toward +z
    (cached: the same chair six times is one mesh)."""
    m = PlantMesh()
    BUILDERS[builder](m, W, D, H, dict(colors), dict(options))
    return m


# --- Placing pieces in a room ----------------------------------------------------------

_INWARD = {"front": (0.0, 1.0), "back": (0.0, -1.0), "left": (1.0, 0.0), "right": (-1.0, 0.0)}
_OPPOSITE = {"front": "back", "back": "front", "left": "right", "right": "left"}
# Pieces that go against a wall even when the plan says where (they need one behind them).
_WALL_BUILDERS = {"sofa", "sectional", "bed", "crib", "dresser", "wardrobe", "bookshelf", "tv_stand", "cabinet",
                  "piano", "counter", "fridge", "stove", "toilet", "vanity", "bathtub", "washer", "console", "desk"}
# The order pieces are placed in: big pieces against walls first, then what goes with them.
_ORDER = {
    "wall": 0, "center": 1, "opposite_sofa": 2, "beside_bed": 3, "front_of_sofa": 3, "beside_sofa": 4,
    "facing_sofa": 4, "front_of_desk": 5, "front_of_island": 5, "corner": 6, "under": 7,
}


def yaw_facing(fx: float, fz: float) -> float:
    """The yaw (degrees, the geometry's convention) that turns a piece's front (+z) toward (fx, fz)."""
    return math.degrees(math.atan2(-fx, fz))


def _turn(yaw: float, lx: float, lz: float) -> tuple[float, float]:
    """A local (x, z) offset of a piece turned ``yaw`` degrees, in world axes."""
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return lx * c - lz * s, lx * s + lz * c


def _outline(cx: float, cz: float, W: float, D: float, yaw: float) -> list[list[float]]:
    pts = []
    for lx, lz in ((-W / 2, -D / 2), (W / 2, -D / 2), (W / 2, D / 2), (-W / 2, D / 2)):
        dx, dz = _turn(yaw, lx, lz)
        pts.append([round(cx + dx, 3), round(cz + dz, 3)])
    return pts


def _aabb(cx: float, cz: float, W: float, D: float, yaw: float) -> tuple[float, float, float, float]:
    pts = _outline(cx, cz, W, D, yaw)
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), max(xs), min(zs), max(zs)


def _overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[1] - _EPS and b[0] < a[1] - _EPS and a[2] < b[3] - _EPS and b[2] < a[3] - _EPS


@dataclass
class Placed:
    item: dict
    piece: Piece
    W: float
    D: float
    H: float
    cx: float
    cz: float
    yaw: float
    side: str | None = None  # the wall it stands against
    parts: tuple = ()  # chairs and stools that came with it


class RoomSpace:
    """One room's floor: its inside (walls' inner faces), the zones kept clear in
    front of doorways and windows, and the pieces placed so far."""

    DOOR_CLEAR = 0.9  # metres kept free in front of a doorway
    WALK = 0.1  # gap between pieces

    def __init__(self, name: str, rect: dict, openings: list[dict]):
        self.name = name
        self.rect = rect
        self.x0, self.x1 = rect["x0"] + WALL_T, rect["x1"] - WALL_T
        self.z0, self.z1 = rect["z0"] + WALL_T, rect["z1"] - WALL_T
        self.placed: list[Placed] = []
        # (x0, x1, z0, z1, allowed height below it)
        self.keep_clear: list[tuple[float, float, float, float, float]] = []
        for side, (axis, line) in self._side_lines().items():
            for o in openings:
                if o["axis"] != axis or abs(o["line"] - line) > _EPS:
                    continue
                lo, hi = (self.x0, self.x1) if axis == "x" else (self.z0, self.z1)
                a, b = max(lo, o["lo"]), min(hi, o["hi"])
                if b - a <= _EPS:
                    continue
                kind = o.get("kind") or ("door" if o["bottom"] < 0.05 else "window")
                if kind == "door":
                    depth, below, pad = self.DOOR_CLEAR, 0.0, 0.1
                elif kind == "open":  # an opened-up wall: a way through, less than a door's swing
                    depth, below, pad = 0.6, 0.0, 0.0
                elif kind == "bay":  # a bay window's bump-out: step into it, sit in front of it
                    depth, below, pad = 0.3, 0.0, 0.0
                else:  # a window: only what is taller than the sill is in the way
                    depth, below, pad = 0.5, o["bottom"] - 0.02, 0.05
                self.keep_clear.append(self._zone(side, a - pad, b + pad, depth) + (below,))

    def _side_lines(self) -> dict[str, tuple[str, float]]:
        r = self.rect
        return {"front": ("x", r["z0"]), "back": ("x", r["z1"]), "left": ("z", r["x0"]), "right": ("z", r["x1"])}

    def _zone(self, side: str, a: float, b: float, depth: float) -> tuple[float, float, float, float]:
        if side == "front":
            return a, b, self.z0, self.z0 + depth
        if side == "back":
            return a, b, self.z1 - depth, self.z1
        if side == "left":
            return self.x0, self.x0 + depth, a, b
        return self.x1 - depth, self.x1, a, b

    @property
    def size(self) -> tuple[float, float]:
        return self.x1 - self.x0, self.z1 - self.z0

    def side_span(self, side: str) -> tuple[float, float]:
        return (self.x0, self.x1) if side in ("front", "back") else (self.z0, self.z1)

    def fits(self, box_: tuple, height: float, ignore: tuple = ()) -> bool:
        """Whether a piece this tall with these plan bounds is inside the room, clear
        of doorways (and of windows unless it is lower than the sill) and of the
        other pieces. ``height`` is what stands against the wall: a bed's headboard
        may run up in front of a window, its mattress may not."""
        x0, x1, z0, z1 = box_
        if x0 < self.x0 - _EPS or x1 > self.x1 + _EPS or z0 < self.z0 - _EPS or z1 > self.z1 + _EPS:
            return False
        for kx0, kx1, kz0, kz1, below in self.keep_clear:
            if height > below and _overlap(box_, (kx0, kx1, kz0, kz1)):
                return False
        for p in self.placed:
            if p.piece.builder == "rug":
                continue
            # A piece set beside another (a nightstand by the bed) only has to miss it.
            if _overlap(box_, raw_box(p) if p in ignore else p_box(p)):
                return False
        return True

    def against(self, side: str, t: float, W: float, D: float) -> tuple[float, float, float]:
        """Centre and yaw of a piece ``W`` × ``D`` with its back on ``side``, ``t`` along it."""
        fx, fz = _INWARD[side]
        gap = 0.02
        if side == "front":
            return t, self.z0 + gap + D / 2, yaw_facing(fx, fz)
        if side == "back":
            return t, self.z1 - gap - D / 2, yaw_facing(fx, fz)
        if side == "left":
            return self.x0 + gap + D / 2, t, yaw_facing(fx, fz)
        return self.x1 - gap - D / 2, t, yaw_facing(fx, fz)

    def wall_spots(self, side: str, W: float, D: float, H: float, extra=None) -> list[float]:
        """Every position along ``side`` (5 cm apart) where the piece fits."""
        lo, hi = self.side_span(side)
        spots = []
        t = lo + W / 2 + 0.02
        while t <= hi - W / 2 - 0.02 + _EPS:
            cx, cz, yaw = self.against(side, t, W, D)
            if self.fits(_aabb(cx, cz, W, D, yaw), H) and (extra is None or extra(cx, cz, yaw)):
                spots.append(t)
            t += 0.05
        return spots


def raw_box(p: Placed) -> tuple:
    """The plan bounds of a piece and the chairs that came with it."""
    boxes = [_aabb(p.cx, p.cz, p.W, p.D, p.yaw)] + [_aabb(*part[:5]) for part in p.parts]
    return (min(b[0] for b in boxes), max(b[1] for b in boxes), min(b[2] for b in boxes), max(b[3] for b in boxes))


def p_box(p: Placed) -> tuple:
    """``raw_box`` with room to walk round it."""
    x0, x1, z0, z1 = raw_box(p)
    pad = RoomSpace.WALK
    return x0 - pad, x1 + pad, z0 - pad, z1 + pad


def _longest_run(spots: list[float]) -> float:
    if not spots:
        return 0.0
    best = run = 0.0
    for a, b in zip(spots, spots[1:]):
        run = run + (b - a) if b - a < 0.06 else 0.0
        best = max(best, run)
    return best + 0.05


def _wall_height(piece: Piece, H: float) -> float:
    """How tall a piece is where it meets a window: a bed only to its mattress (the
    headboard may stand in front of the glass), a counter just under the sill (the
    sink under the kitchen window)."""
    if piece.builder in ("bed", "crib"):
        return min(H, 0.66)
    if piece.builder in ("counter", "vanity", "island", "washer"):
        return min(H, 0.85)
    return H


def _m(feet: float) -> float:
    return feet * FT_TO_M


# --- Sizes and colors of one item ---------------------------------------------------

def _size(item: dict, piece: Piece, space: RoomSpace) -> tuple[float, float, float]:
    W, D, H = piece.width, piece.depth, piece.height
    if item["type"] == "bed" and item.get("size") in BED_SIZES:
        W, D = BED_SIZES[item["size"]]
    W, D, H = (_m(item.get(k, v)) for k, v in (("width", W), ("depth", D), ("height", H)))
    room_w, room_d = space.size
    if piece.builder == "counter" and "width" not in item:
        W = max(room_w, room_d)  # trimmed to the wall it lands on
    if piece.builder == "rug" and "width" not in item:
        W, D = min(W, room_w - 0.6), min(D, room_d - 0.6)
    return max(0.2, W), max(0.1, D), max(0.01, H)


def _colors(item: dict, piece: Piece) -> tuple:
    """The colors a piece is drawn in, as a hashable tuple: ``main`` (upholstery,
    bedding, cabinets) and ``wood`` (frames, legs, tabletops)."""
    named = _color_word(item.get("name")) if item.get("name") else None
    wood = item.get("wood") or WOOD
    main = item.get("color") or named or piece.color
    wooden = piece.builder in ("table", "round_table", "coffee_table", "side_table", "console", "desk",
                               "nightstand", "dresser", "wardrobe", "bookshelf", "cabinet", "bench", "chair",
                               "stool", "tv_stand")
    if wooden:
        # A wooden piece's color is its wood (a "white dresser" is painted white).
        wood = item.get("color") or named or item.get("wood") or piece.color
    colors = {"main": main, "wood": wood}
    if piece.builder == "vanity":
        colors["wood_cab"] = item.get("color") or named or item.get("wood") or "#f0ede6"
    return tuple(sorted(colors.items()))


# --- Building it ------------------------------------------------------------------

class Furnishing:
    """Collects the furniture of a house: shared meshes with their instances, the
    photo models, and notes about what did not fit."""

    def __init__(self, models: list[dict] | None):
        self.meshes: dict[str, dict] = {}
        self.pieces: list[dict] = []
        self.models: list[dict] = []
        self.photo_models = models or []
        self.notes: list[str] = []
        self.triangles = 0

    def _mesh_id(self, builder: str, W: float, D: float, H: float, colors: tuple, options: tuple) -> str:
        W, D, H = round(W, 2), round(D, 2), round(H, 2)
        key = f"{builder}-{int(W * 100)}x{int(D * 100)}x{int(H * 100)}-" + "-".join(
            v.lstrip("#") for _, v in colors) + "".join(
            f"-{k}" + (f"_{name_key(v).replace(' ', '_')}" if isinstance(v, str) else "") for k, v in options if v)
        if key not in self.meshes:
            mesh = piece_mesh(builder, W, D, H, colors, options)
            self.meshes[key] = mesh.out()
            self.triangles += mesh.triangles
        return key

    def _photo_model(self, item: dict) -> dict | None:
        if not self.photo_models:
            return None
        if "model_id" in item:
            return next((m for m in self.photo_models if m["id"] == item["model_id"]), None)
        key = name_key(item.get("name"))
        return next((m for m in self.photo_models if key and name_key(m["name"]) == key), None)

    def add(self, room_id: int, item: dict, piece: Piece, W: float, D: float, H: float,
            cx: float, cz: float, yaw: float, options: tuple = ()):
        colors = _colors(item, piece)
        out = {
            "room": room_id,
            "type": item["type"],
            "position": {"x": round(cx, 3), "y": FLOOR_TOP, "z": round(cz, 3)},
            "yaw": round(yaw % 360, 1),
            # For the dashboard's plan.
            "outline": _outline(cx, cz, W, D, yaw),
            "color": _rgb(dict(colors)["main" if piece.builder not in ("table", "round_table") else "wood"]),
        }
        if item.get("name"):
            out["name"] = item["name"]
        model = self._photo_model(item)
        if model:
            out.update({"model_id": model["id"], "url": model["url"], "scale": round(H, 3)})
            if not item.get("height") and model.get("height_ft"):
                out["scale"] = round(_m(model["height_ft"]), 3)
            out["name"] = model["name"]
            self.models.append(out)
            return
        out["mesh"] = self._mesh_id(piece.builder, W, D, H, colors, options)
        out["scale"] = {"x": 1, "y": 1, "z": 1}
        self.pieces.append(out)

    def out(self) -> dict:
        return {"meshes": self.meshes, "pieces": self.pieces, "models": self.models}


def _rgb(hex_color: str) -> dict:
    h = hex_color.lstrip("#")
    return {k: round(int(h[i:i + 2], 16) / 255, 3) for k, i in (("r", 0), ("g", 2), ("b", 4))}


def _label(item: dict, piece: Piece) -> str:
    return item.get("name") or piece.label or item["type"]


def _find(space: RoomSpace, *builders: str) -> Placed | None:
    return next((p for p in space.placed if p.piece.builder in builders), None)


def _seat_split(n: int, ends_ok: bool = True) -> tuple[int, int]:
    """Chairs per long side and at the ends: 4 → 2+2, 5 → 2+2+1, 6 → 2+2+2, 8 → 3+3+2;
    without ``ends_ok`` (a long table in a narrow room) 6 → 3+3."""
    ends = (0 if n % 2 == 0 else 1) if n <= 4 or not ends_ok else (2 if n % 2 == 0 else 1)
    return (n - ends) // 2, ends


def _seat_layout(n: int, W: float, D: float, round_: bool, chair_d: float,
                 ends_ok: bool = True) -> list[tuple[float, float, float]]:
    """Local (x, z, yaw) of ``n`` chairs round a table ``W`` × ``D`` (each facing it)."""
    if n <= 0:
        return []
    tuck = 0.1
    if round_:
        r = min(W, D) / 2 + chair_d / 2 - tuck
        return [
            (math.sin(a) * r, math.cos(a) * r, yaw_facing(-math.sin(a), -math.cos(a)))
            for a in (2 * math.pi * k / n for k in range(n))
        ]
    per_side, ends = _seat_split(n, ends_ok)
    seats = []
    for side in (1, -1):
        for k in range(per_side):
            x = -W / 2 + W * (k + 0.5) / per_side
            seats.append((x, side * (D / 2 + chair_d / 2 - tuck), yaw_facing(0, -side)))
    for k in range(ends):
        side = 1 if k == 0 else -1
        seats.append((side * (W / 2 + chair_d / 2 - tuck), 0.0, yaw_facing(-side, 0)))
    return seats


def _table_size(item: dict, piece: Piece, W: float, D: float, seats: int,
                ends_ok: bool = True) -> tuple[float, float]:
    """A table long enough for its chairs (0.6 m each along a side)."""
    if piece.builder == "round_table" or "width" in item:
        if piece.builder == "round_table" and "width" not in item:
            W = D = max(W, min(1.8, 0.75 + 0.1 * seats))
        return W, D
    per_side, _ = _seat_split(seats, ends_ok)
    return max(W, 0.6 * per_side + 0.2), D


def _try_place(space: RoomSpace, placed: Placed, beside: Placed | None = None) -> bool:
    if space.fits(raw_box(placed), _wall_height(placed.piece, placed.H), (beside,) if beside else ()):
        space.placed.append(placed)
        return True
    return False


def _place_wall(space: RoomSpace, item: dict, piece: Piece, W: float, D: float, H: float,
                prefer: list[str] | None = None, near: tuple[float, float] | None = None,
                avoid: str | None = None) -> Placed | None:
    """Against the wall with the longest free stretch (or one of ``prefer``)."""
    best: tuple | None = None
    sides = prefer or ["back", "left", "right", "front"]
    for rank, side in enumerate(sides):
        if side == avoid:
            continue
        spots = space.wall_spots(side, W, D, _wall_height(piece, H))
        if not spots:
            continue
        lo, hi = space.side_span(side)
        if near:
            target = near[0] if side in ("front", "back") else near[1]
        else:
            target = (lo + hi) / 2
        t = min(spots, key=lambda s: abs(s - target))
        # A preferred wall wins outright; otherwise the longest clear stretch does.
        score = (-rank if prefer else 0, _longest_run(spots), -abs(t - target))
        if best is None or score > best[0]:
            best = (score, side, t)
    if best is None:
        return None
    _, side, t = best
    cx, cz, yaw = space.against(side, t, W, D)
    placed = Placed(item, piece, W, D, H, cx, cz, yaw, side)
    space.placed.append(placed)
    return placed


def _place_center(space: RoomSpace, item: dict, piece: Piece, W: float, D: float, H: float,
                  seats: list[tuple[float, float, float]], chair: tuple[float, float, float]) -> Placed | None:
    """In the middle of the room (or the free spot nearest it), long side along the
    room's long side, with its chairs."""
    room_w, room_d = space.size
    yaws = [0.0, 90.0] if room_w >= room_d else [90.0, 0.0]
    if W < D:
        yaws.reverse()
    cx0, cz0 = (space.x0 + space.x1) / 2, (space.z0 + space.z1) / 2
    step = 0.1
    ni, nj = int(room_w / 2 / step) + 1, int(room_d / 2 / step) + 1
    candidates = [(cx0 + i * step, cz0 + j * step) for i in range(-ni, ni + 1) for j in range(-nj, nj + 1)]
    candidates.sort(key=lambda p: (p[0] - cx0) ** 2 + (p[1] - cz0) ** 2)
    cw, cd, ch = chair
    for yaw in yaws:
        for cx, cz in candidates:
            parts = []
            for lx, lz, lyaw in seats:
                dx, dz = _turn(yaw, lx, lz)
                parts.append((cx + dx, cz + dz, cw, cd, yaw + lyaw))
            placed = Placed(item, piece, W, D, H, cx, cz, yaw, None, tuple(parts))
            if _try_place(space, placed):
                return placed
    return None


def _place_beside(space: RoomSpace, item: dict, piece: Piece, W: float, D: float, H: float,
                  anchor: Placed, offsets: list[tuple[float, float, float]]) -> Placed | None:
    """At one of ``offsets`` (local x, z, yaw) of ``anchor``."""
    for lx, lz, lyaw in offsets:
        dx, dz = _turn(anchor.yaw, lx, lz)
        placed = Placed(item, piece, W, D, H, anchor.cx + dx, anchor.cz + dz, anchor.yaw + lyaw, anchor.side)
        if _try_place(space, placed, anchor):
            return placed
    return None


def _place_corner(space: RoomSpace, item: dict, piece: Piece, W: float, D: float, H: float,
                  near: tuple[float, float] | None = None) -> Placed | None:
    corners = [
        (space.x0, space.z0, 1, 1), (space.x1, space.z0, -1, 1),
        (space.x0, space.z1, 1, -1), (space.x1, space.z1, -1, -1),
    ]
    if near:
        corners.sort(key=lambda c: (c[0] - near[0]) ** 2 + (c[1] - near[1]) ** 2)
    for x, z, sx, sz in corners:
        for inset in (0.05, 0.3, 0.6):
            cx, cz = x + sx * (W / 2 + inset), z + sz * (D / 2 + inset)
            placed = Placed(item, piece, W, D, H, cx, cz, yaw_facing(0, sz))
            if _try_place(space, placed):
                return placed
    return None


def _place_exact(space: RoomSpace, item: dict, piece: Piece, W: float, D: float, H: float) -> Placed:
    """Where the plan says (feet from the room's front-left corner), kept inside the room."""
    r = space.rect
    cx = min(max(r["x0"] + _m(item["x"]), space.x0 + W / 2), space.x1 - W / 2)
    cz = min(max(r["z0"] + _m(item["z"]), space.z0 + D / 2), space.z1 - D / 2)
    facing = item.get("facing")
    if facing:
        fx, fz = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}[facing]
    else:
        # Toward the middle of the room, along whichever axis is further off.
        mx, mz = (space.x0 + space.x1) / 2 - cx, (space.z0 + space.z1) / 2 - cz
        fx, fz = ((1 if mx > 0 else -1), 0) if abs(mx) > abs(mz) else (0, (1 if mz > 0 else -1))
    placed = Placed(item, piece, W, D, H, cx, cz, yaw_facing(fx, fz))
    space.placed.append(placed)
    return placed


def _counter_options(space: RoomSpace, side: str, cx: float, cz: float, W: float, item: dict) -> tuple:
    """A kitchen run: a sink always, a range on a long run, the fridge when it was
    furnished automatically, wall cabinets where no window is in the way."""
    along_x = side in ("front", "back")
    lo, hi = (cx - W / 2, cx + W / 2) if along_x else (cz - W / 2, cz + W / 2)
    on_wall = {
        "front": lambda z0, z1, x0, x1: z0 <= space.z0 + _EPS,
        "back": lambda z0, z1, x0, x1: z1 >= space.z1 - _EPS,
        "left": lambda z0, z1, x0, x1: x0 <= space.x0 + _EPS,
        "right": lambda z0, z1, x0, x1: x1 >= space.x1 - _EPS,
    }[side]
    window = any(
        below > 0 and on_wall(kz0, kz1, kx0, kx1) and ((kx0 < hi and lo < kx1) if along_x else (kz0 < hi and lo < kz1))
        for kx0, kx1, kz0, kz1, below in space.keep_clear
    )
    fridge = bool(item.get("auto")) and W >= 3.2
    return (("fridge", fridge), ("range", W - (0.9 if fridge else 0) >= 2.0), ("sink", True), ("upper", not window))


def furnish_room(f: Furnishing, room_id: int, space: RoomSpace, items: list[dict]):
    """Place ``items`` in ``space`` and add them to ``f``."""
    expanded: list[dict] = []
    for item in items:
        for _ in range(item.get("count", 1) if PIECES[item["type"]].builder not in ("stool",) else 1):
            expanded.append(item)
    order = sorted(
        range(len(expanded)),
        key=lambda i: (0 if "x" in expanded[i] else 1, _ORDER.get(PIECES[expanded[i]["type"]].place, 0)
                       if not expanded[i].get("place") else 0, i),
    )
    for i in order:
        item = expanded[i]
        piece = PIECES[item["type"]]
        W, D, H = _size(item, piece, space)
        label = _label(item, piece)
        place = item.get("place") or piece.place
        if place == "center" and piece.builder in _WALL_BUILDERS:
            place = piece.place  # a sofa or a bed "in the middle of the room" still has its back to a wall
        sofa = _find(space, "sofa", "sectional")
        placed: Placed | None = None
        options: tuple = ()
        seats = item.get("seats", piece.seats)

        if piece.builder == "counter" and "x" not in item:
            placed = _place_counter(space, item, piece, D, H, item.get("place") if item.get("place") in _SIDES else None)
        elif piece.builder in ("table", "round_table", "island"):
            W0, D0 = W, D
            round_ = piece.builder == "round_table"
            chair_piece = PIECES["bar stool" if piece.builder == "island" else "dining chair"]
            cw, cd, ch = (_m(chair_piece.width), _m(chair_piece.depth), _m(chair_piece.height))
            # Every way of seating them, most chairs first: with chairs at the ends,
            # then all along the sides (a longer table for a narrower room).
            tries = []
            for n in range(seats, -1, -2) if seats else [0]:
                for ends_ok in ((True, False) if n >= 5 and not round_ else (True,)):
                    if piece.builder == "island":
                        layout = [(-W0 / 2 + W0 * (k + 0.5) / n, D0 / 2 + cd / 2 - 0.05, 180.0) for k in range(n)]
                        tries.append((W0, D0, layout))
                    else:
                        tw, td = _table_size(item, piece, W0, D0, n, ends_ok)
                        tries.append((tw, td, _seat_layout(n, tw, td, round_, cd, ends_ok)))
            for W, D, layout in tries:
                if "x" in item:
                    placed = _place_exact(space, item, piece, W, D, H)
                    parts = []
                    for lx, lz, lyaw in layout:
                        dx, dz = _turn(placed.yaw, lx, lz)
                        parts.append((placed.cx + dx, placed.cz + dz, cw, cd, placed.yaw + lyaw))
                    placed.parts = tuple(parts)
                else:
                    placed = _place_center(space, item, piece, W, D, H, layout, (cw, cd, ch))
                if placed:
                    break
            if placed and len(placed.parts) < item.get("seats", piece.seats) and not item.get("auto"):
                f.notes.append(f"Only {len(placed.parts)} chairs fit round the {label} in {space.name}")
            if placed:
                chair_item = {"type": chair_piece_name(piece)}
                if item.get("wood") or item.get("color"):
                    chair_item["wood"] = item.get("wood") or item.get("color")
                for cx, cz, _, _, cyaw in placed.parts:
                    f.add(room_id, chair_item, chair_piece, cw, cd, ch, cx, cz, cyaw)
        elif "x" in item:
            placed = _place_exact(space, item, piece, W, D, H)
        elif piece.builder == "bed" and "width" not in item:
            # The size asked for, else the next one down that fits.
            want = item.get("size") or ("queen" if W > 1.2 else "twin")
            steps = ["king", "queen", "full", "twin"]
            smaller = [s_ for s_ in steps if BED_SIZES[s_][0] < BED_SIZES[want][0]]
            for size in [want] + smaller:
                W, D = (_m(v) for v in BED_SIZES[size])
                placed = _place_wall(space, item, piece, W, D, H, prefer=[place] if place in _SIDES else None)
                if placed:
                    if size != want and not item.get("auto"):
                        f.notes.append(f"A {want} bed doesn't fit in {space.name}, so it has a {size}")
                    break
        elif place in _SIDES:
            placed = _place_wall(space, item, piece, W, D, H, prefer=[place])
        elif place == "center":
            placed = _place_center(space, item, piece, W, D, H, [], (0, 0, 0))
        elif place == "corner" or piece.place == "corner":
            near = (sofa.cx, sofa.cz) if sofa and piece.builder == "lamp" else None
            placed = _place_corner(space, item, piece, W, D, H, near)
        elif piece.place == "beside_bed":
            bed = _find(space, "bed", "crib")
            if bed:
                off = bed.W / 2 + 0.05 + W / 2
                back = -bed.D / 2 + D / 2 + 0.02
                placed = _place_beside(space, item, piece, W, D, H, bed, [(-off, back, 0), (off, back, 0)])
        elif piece.place == "front_of_sofa" and sofa:
            if sofa.piece.builder == "sectional":
                main_d = min(1.0, sofa.D * 0.48)
                lz = -sofa.D / 2 + main_d + 0.45 + D / 2
                cw = min(1.0, sofa.W * 0.38)
                offsets = [(-cw / 2, lz, 0)]
            else:
                offsets = [(0, sofa.D / 2 + 0.45 + D / 2, 0), (0, sofa.D / 2 + 0.35 + D / 2, 0)]
            placed = _place_beside(space, item, piece, W, D, H, sofa, offsets)
        elif piece.place == "beside_sofa" and sofa:
            off = sofa.W / 2 + 0.05 + W / 2
            placed = _place_beside(space, item, piece, W, D, H, sofa,
                                   [(off, -sofa.D / 2 + D / 2, 0), (-off, -sofa.D / 2 + D / 2, 0)])
        elif piece.place == "facing_sofa" and sofa:
            table = _find(space, "coffee_table")
            lz = sofa.D / 2 + 0.45 + (table.D / 2 if table else 0.3)
            reach = (table.W / 2 if table else sofa.W / 2 - 0.3) + 0.45 + D / 2
            placed = _place_beside(space, item, piece, W, D, H, sofa, [
                (reach, lz, 90.0), (-reach, lz, -90.0),
                (sofa.W / 2 + 0.3 + D / 2, lz + 0.3, 90.0), (-(sofa.W / 2 + 0.3 + D / 2), lz + 0.3, -90.0),
            ])
        elif piece.place == "opposite_sofa" and sofa and sofa.side:
            placed = _place_wall(space, item, piece, W, D, H, prefer=[_OPPOSITE[sofa.side]],
                                 near=(sofa.cx, sofa.cz))
        elif piece.place == "front_of_desk":
            desk = _find(space, "desk")
            if desk:
                placed = _place_beside(space, item, piece, W, D, H, desk, [(-0.15, desk.D / 2 + 0.05, 180.0)])
        elif piece.place == "front_of_island":
            island = _find(space, "island")
            if island:
                n = item.get("count", 3)
                for k in range(n):
                    lx = -island.W / 2 + island.W * (k + 0.5) / n
                    stool = _place_beside(space, item, piece, W, D, H, island,
                                          [(lx, island.D / 2 + D / 2 + 0.02, 180.0)])
                    if stool:
                        f.add(room_id, item, piece, W, D, H, stool.cx, stool.cz, stool.yaw)
                continue
        elif piece.place == "under":
            anchor = _find(space, "coffee_table") or sofa or _find(space, "bed")
            if anchor and anchor.piece.builder == "bed":
                W, D = min(W, anchor.W + 1.0), min(D, anchor.D * 0.75)
                dx, dz = _turn(anchor.yaw, 0, anchor.D * 0.2)
                cx, cz, yaw = anchor.cx + dx, anchor.cz + dz, anchor.yaw
            elif anchor:
                if anchor.piece.builder in ("sofa", "sectional"):
                    dx, dz = _turn(anchor.yaw, 0, anchor.D / 2 + 0.6)
                    cx, cz = anchor.cx + dx, anchor.cz + dz
                else:
                    cx, cz = anchor.cx, anchor.cz
                yaw = anchor.yaw
            else:
                cx, cz, yaw = (space.x0 + space.x1) / 2, (space.z0 + space.z1) / 2, 0.0
            x0, x1, z0, z1 = _aabb(cx, cz, W, D, yaw)
            cx += max(0, space.x0 + 0.1 - x0) - max(0, x1 - space.x1 + 0.1)
            cz += max(0, space.z0 + 0.1 - z0) - max(0, z1 - space.z1 + 0.1)
            placed = Placed(item, piece, W, D, H, cx, cz, yaw)
            space.placed.append(placed)

        if placed is None and piece.builder not in ("counter", "table", "round_table", "island", "rug"):
            # Whatever it was meant to go with is missing or in the way: any free wall.
            placed = _place_wall(space, item, piece, W, D, H)
            if placed is None and piece.builder not in _WALL_BUILDERS:
                placed = _place_center(space, item, piece, W, D, H, [], (0, 0, 0))
        if placed is None and item.get("auto") and piece.builder == "bathtub":
            # Furnished automatically: a shower where a tub won't go.
            piece, item = PIECES["shower"], {"type": "shower", "auto": True}
            W, D, H = _size(item, piece, space)
            placed = _place_corner(space, item, piece, W, D, H)
        if placed is None:
            if not item.get("auto"):  # nobody asked for what auto furnishing leaves out
                f.notes.append(f"No room for the {label} in {space.name}")
            continue
        if piece.builder == "counter":
            options = _counter_options(space, placed.side or "back", placed.cx, placed.cz, placed.W, item)
        elif piece.builder == "potted_plant":
            species = find_species(item.get("name"))
            options = (("species", species),) if species else ()
        f.add(room_id, item, piece, placed.W, placed.D, placed.H, placed.cx, placed.cz, placed.yaw, options)


def chair_piece_name(piece: Piece) -> str:
    return "bar stool" if piece.builder == "island" else "dining chair"


def _place_counter(space: RoomSpace, item: dict, piece: Piece, D: float, H: float,
                   prefer: str | None = None) -> Placed | None:
    """Kitchen counters along the longest clear stretch of wall (or of ``prefer``),
    as long as it allows (or as long as the plan asks), pushed into a corner."""
    want = _m(item["width"]) if "width" in item else None
    best = None
    for side in ([prefer] if prefer else ["back", "left", "right", "front"]):
        lo, hi = space.side_span(side)
        for W in ([want] if want else [hi - lo - 0.04 - k * 0.3 for k in range(20)]):
            if W is None or W < 0.9:
                break
            spots = space.wall_spots(side, W, D, _wall_height(piece, H))
            if spots:
                if best is None or W > best[0]:
                    lo_, hi_ = space.side_span(side)
                    t = min(spots, key=lambda s: abs(s - (lo_ + hi_) / 2))
                    best = (W, side, t)
                break
    if best is None:
        return None
    W, side, t = best
    W = min(W, 4.9) if not want else W
    spots = space.wall_spots(side, W, D, _wall_height(piece, H))
    if not spots:
        return None
    lo, hi = space.side_span(side)
    t = min(spots, key=lambda s: abs(s - (lo + W / 2 + 0.02)))  # into a corner
    cx, cz, yaw = space.against(side, t, W, D)
    placed = Placed(item, piece, W, D, H, cx, cz, yaw, side)
    space.placed.append(placed)
    return placed


def build_furniture(
    spec: dict | None,
    rooms: list[dict],
    openings: list[dict],
    models: list[dict] | None = None,
) -> tuple[dict | None, list[str]]:
    """Furniture for every room, metres (the headset scales it).

    ``rooms`` are ``{"id", "name", "bounds"}`` as built, ``openings`` every door,
    window and opened-up wall cut in the walls, ``models`` the finished photo models
    of kind "furniture". Returns ``({"meshes", "pieces", "models"}, notes)``, or
    ``(None, [])`` when the plan has no furniture.
    """
    if not spec or not rooms:
        return None, []
    listed = {k.strip().lower(): v for k, v in (spec.get("rooms") or {}).items()}
    f = Furnishing(models)
    counts: dict[str, int] = {}
    for room in rooms:
        name = room["name"]
        b = room["bounds"]
        items = listed.get(name.strip().lower())
        if items is None:
            if not spec.get("auto"):
                continue
            items = [
                {**i, "auto": True}
                for i in (_clean_item(r, room_kind(name)) for r in auto_items(name, b["x1"] - b["x0"], b["z1"] - b["z0"]))
                if i
            ]
        if not items:
            continue
        space = RoomSpace(name, b, openings)
        before = len(f.pieces) + len(f.models)
        furnish_room(f, room["id"], space, items)
        counts[name] = len(f.pieces) + len(f.models) - before
    if not counts and not f.notes:
        return None, []
    logger.info(
        f"  🛋️  Furniture: {', '.join(f'{n} in {k}' for k, n in counts.items())}"
        f" ({len(f.meshes)} meshes, {f.triangles} triangles"
        + (f", {len(f.models)} photo models" if f.models else "") + ")"
    )
    return {**f.out(), "spec": spec}, f.notes
