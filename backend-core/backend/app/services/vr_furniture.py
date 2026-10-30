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


_CORNERS = tuple(f"{a}-{b}" for a in ("front", "back") for b in ("left", "right"))
_DIAGONAL = re.compile(r"\b(diagonal\w*|angled?|45)\b")


def _corner(value: Any) -> str | None:
    """"front-right" from words naming both walls of a corner ("the back left corner")."""
    words = [_SIDE_ALIASES.get(w, w) for w in name_key(value).split()]
    fb = next((w for w in words if w in ("front", "back")), None)
    lr = next((w for w in words if w in ("left", "right")), None)
    return f"{fb}-{lr}" if fb and lr else None


def _between(raw: dict, room: str) -> list[str] | None:
    """The two pieces a counter runs between: ``between`` (a list or "stove and fridge"),
    or ``from`` / ``to``."""
    value = raw.get("between")
    if isinstance(value, str):
        value = re.split(r"\band\b|\bto\b|,|&", value)
    if not isinstance(value, list):
        value = [raw.get("from"), raw.get("to")]
    kinds = [find_piece(v, room) for v in value if v]
    return kinds if len(kinds) == 2 and all(kinds) and kinds[0] != kinds[1] else None


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
    where = " ".join(str(raw.get(k) or "") for k in ("corner", "place", "position", "wall"))
    corner = _corner(where)
    if PIECES[kind].builder == "stove":
        # A stove across a corner: a corner named, or "diagonal" / "corner" asked for.
        diagonal = raw.get("diagonal") is True or bool(_DIAGONAL.search(f"{name_key(words)} {name_key(where)}"))
        if corner or diagonal or place == "corner" or raw.get("corner") == "any":
            item["corner"] = corner or "any"
            item.pop("place", None)
    elif corner and PIECES[kind].builder in _WALL_BUILDERS:
        item["corner"] = corner  # against one of its walls, pushed into it
    style = " ".join(str(raw.get("style") or "").split())[:80]
    if style and PIECES[kind].builder in _KITCHEN:
        item["style"] = style
    # What a counter run or an island has, when the plan says: "no sink", "add wall cabinets".
    for key in _FEATURES.get(PIECES[kind].builder, ()):
        flag = _flag(raw.get(key) if key in raw else raw.get({"uppers": "upper"}.get(key, "")))
        if flag is not None:
            item[key] = flag
    rotation = _num(raw.get("rotation"), -720, 720)
    if rotation is not None and "x" in item:
        item["rotation"] = round(rotation % 360, 1)
    if PIECES[kind].builder == "counter":
        between = _between(raw, room)
        if between:
            item["between"] = between
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


_FEATURES = {"counter": ("sink", "range", "uppers"), "island": ("sink",)}


def _flag(value: Any) -> bool | None:
    """True/False from a boolean or a yes/no word; None when it says neither."""
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return True if text in ("true", "yes", "1", "on") else False if text in ("false", "no", "0", "off", "none") else None


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


class MoveError(ValueError):
    """A piece that can't be moved (it no longer matches the plan)."""


def move_piece(spec: dict | None, ref: dict, target: str, x_ft: float, z_ft: float, rotation: float,
               sizes: dict[str, tuple[float, float]]) -> dict:
    """``spec`` with the piece ``ref`` names (``{"room", "item", "width", "depth", "auto"}``,
    as ``build_furniture`` gave it) standing at ``x_ft``/``z_ft`` (feet from ``target``'s
    front-left corner, its centre) turned ``rotation`` degrees: as it was left after
    being grabbed. A room furnished automatically gets its list written out first;
    one of several (``count``) is split off; it keeps the size it had and loses
    where it was told to go (``place``, ``corner``, ``between``, ``facing``).
    ``sizes`` are the rooms' sizes in metres (length, width)."""
    spec = {**(spec or {}), "rooms": {k: [dict(i) for i in v] for k, v in ((spec or {}).get("rooms") or {}).items()}}
    rooms = spec["rooms"]

    def items_of(name: str) -> list[dict]:
        key = next((k for k in rooms if k.strip().lower() == name.strip().lower()), None)
        if key is not None:
            return rooms[key]
        listed = []
        if spec.get("auto") and name in sizes:
            listed = [i for i in (_clean_item(r, room_kind(name)) for r in auto_items(name, *sizes[name])) if i]
        rooms[name] = listed
        return listed

    if ref.get("room") not in sizes or target not in sizes:
        raise MoveError("that room is not in the house")
    items = items_of(ref["room"])
    n = ref.get("item")
    if not isinstance(n, int) or not 0 <= n < len(items):
        raise MoveError("that piece is no longer in the plan; reload the house")
    item = items[n]
    if item.get("count", 1) > 1:
        item["count"] -= 1
        if item["count"] == 1:
            item.pop("count")
        moved = {k: v for k, v in item.items() if k != "count"}
        at = None
    else:
        moved = items.pop(n)
        at = n
    moved = {k: v for k, v in moved.items() if k not in ("place", "corner", "between", "facing", "auto")}
    for key in ("width", "depth"):
        if ref.get(key):
            moved[key] = ref[key]
    moved.update({"x": round(x_ft, 1), "z": round(z_ft, 1), "rotation": round(rotation % 360, 1)})
    dest = items_of(target)
    if dest is items and at is not None:
        dest.insert(at, moved)  # same room: same place in the list, so other refs still hold
    else:
        dest.append(moved)
    return spec


def shown_furniture(spec: dict | None, rooms: list[dict] | None) -> dict | None:
    """``spec`` as the refine prompt shows it: rooms ``auto`` furnishes are listed with
    what they get, so a change to one of them keeps the rest of its pieces. ``auto`` is
    left out: with every room listed the AI took it for moot and sent ``false``."""
    if not spec or not spec.get("auto") or not rooms:
        return spec
    listed = dict(spec.get("rooms") or {})
    lower = {k.strip().lower() for k in listed}
    for room in rooms:
        name = str(room.get("name") or "")
        dims = room.get("dimensions") or {}
        if not name or name.strip().lower() in lower:
            continue
        try:
            length, width = _m(float(dims["length"])), _m(float(dims["width"]))
        except (KeyError, TypeError, ValueError):
            continue
        items = auto_items(name, length, width)
        if items:
            listed[name] = items
    return {**{k: v for k, v in spec.items() if k != "auto"}, "rooms": listed}


_WHOLE_HOUSE = re.compile(r"\b(furnish\w*|furniture|empty|unfurnish\w*|clear)\b", re.I)


def with_named_style(raw: Any, instruction: str, style_names: list[str]) -> dict | None:
    """The AI's furniture change for ``instruction``, cleaned: the kitchen style the
    request names is put on the kitchen pieces of rooms where the AI left it out ("in
    Farmhouse kitchen style": Groq returned the kitchen without it), and an ``auto`` the
    request didn't ask for is dropped (Groq sent ``false`` with a kitchen change, which
    would have emptied every automatically furnished room)."""
    spec = furniture_spec(raw)
    if spec and "auto" in spec and not _WHOLE_HOUSE.search(str(instruction or "")):
        spec.pop("auto")
    words = f" {name_key(instruction)} "
    named = next((n for n in sorted(style_names, key=len, reverse=True)
                  if name_key(n) and f" {name_key(n)} " in words), None)
    if not spec or not named:
        return spec
    for items in (spec.get("rooms") or {}).values():
        kitchen = [i for i in items if PIECES[i["type"]].builder in _KITCHEN]
        if kitchen and not any(i.get("style") for i in kitchen):
            for i in kitchen:
                i["style"] = named
    return spec


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


GLASS = "#8fa3a8"  # a glass cabinet door, the dishes behind it


def _put(m, part: PlantMesh, fn):
    """Copy ``part`` into ``m`` with every point moved by ``fn`` (a turn: winding kept)."""
    for color, pts in part.groups.items():
        m.groups.setdefault(color, []).extend(fn(*p) for p in pts)


def _front(m, color: str, x0: float, x1: float, y0: float, y1: float, z: float, o: dict, glass: bool = False):
    """A cabinet door or drawer front on the +z plane at ``z``, in the kitchen style's
    door look (``o["door"]``): flat, shaker (a frame round a recessed panel), raised
    (a raised panel in the frame), or glass panes with muntins."""
    door = o.get("door") or "flat"
    if door == "flat" and not glass:
        box(m, color, x0, x1, y0, y1, z - 0.02, z)
        return
    rail = min(0.06, (y1 - y0) / 4, (x1 - x0) / 4)
    for rx0, rx1, ry0, ry1 in ((x0, x0 + rail, y0, y1), (x1 - rail, x1, y0, y1),
                               (x0 + rail, x1 - rail, y0, y0 + rail), (x0 + rail, x1 - rail, y1 - rail, y1)):
        box(m, color, rx0, rx1, ry0, ry1, z - 0.02, z)
    ix0, ix1, iy0, iy1 = x0 + rail, x1 - rail, y0 + rail, y1 - rail
    if glass:
        box(m, GLASS, ix0, ix1, iy0, iy1, z - 0.016, z - 0.012)
        bar = 0.012
        mx = (ix0 + ix1) / 2
        box(m, color, mx - bar / 2, mx + bar / 2, iy0, iy1, z - 0.012, z - 0.004)
        rows = max(2, round((iy1 - iy0) / 0.16))
        for k in range(1, rows):
            y = iy0 + (iy1 - iy0) * k / rows
            box(m, color, ix0, ix1, y - bar / 2, y + bar / 2, z - 0.012, z - 0.004)
        return
    box(m, _shade(color, 0.93), ix0, ix1, iy0, iy1, z - 0.02, z - 0.008)
    if door == "raised" and min(ix1 - ix0, iy1 - iy0) > 0.06:
        box(m, _shade(color, 1.02), ix0 + 0.02, ix1 - 0.02, iy0 + 0.02, iy1 - 0.02, z - 0.008, z - 0.002)


def _fleck(m, color: str, x0: float, x1: float, z0: float, z1: float, y: float, inside=None):
    """Specks of a granite countertop on its top at ``y`` (``inside(x, z)`` limits them
    to a shape)."""
    rng = random.Random(f"fleck/{x0:.2f}/{x1:.2f}/{z0:.2f}/{z1:.2f}")
    light = _shade(color, 1.35)
    for _ in range(int((x1 - x0) * (z1 - z0) * 140)):
        x, z, r = rng.uniform(x0, x1), rng.uniform(z0, z1), rng.uniform(0.003, 0.007)
        if inside and not inside(x, z):
            continue
        a, b, c_, d = (x - r, y, z - r), (x + r, y, z - r), (x + r, y, z + r), (x - r, y, z + r)
        m.quad(color if rng.random() < 0.7 else light, a, d, c_, b)


def _backsplash(m, o: dict, x0: float, x1: float, y0: float, y1: float, z: float):
    """The wall between the countertop and the wall cabinets, facing +z from ``z``:
    plain tile with grout lines, or a mosaic of short strips in shades of its colour."""
    kind, color = o.get("splash"), o.get("splash_color") or "#d9d6cf"
    if not kind or y1 - y0 < 0.03:
        return
    if kind == "tile":
        box(m, color, x0, x1, y0, y1, z, z + 0.008)
        grout = _shade(color, 1.2)
        y = y0 + 0.075
        while y < y1 - 0.01:
            m.quad(grout, (x0, y, z + 0.009), (x1, y, z + 0.009), (x1, y + 0.003, z + 0.009), (x0, y + 0.003, z + 0.009))
            y += 0.075
        return
    box(m, _shade(color, 0.55), x0, x1, y0, y1, z, z + 0.006)  # the grout
    palette = [color, color, _shade(color, 0.75), _shade(color, 1.3), _shade(color, 1.7), "#b9bcbf"]
    rng = random.Random(f"mosaic/{x1 - x0:.2f}/{y1 - y0:.2f}")
    row, gap, zf = 0.03, 0.004, z + 0.008
    y = y0 + gap
    while y + row <= y1:
        x = x0 + rng.uniform(0, 0.08)
        while x < x1 - 0.02:
            w = min(rng.uniform(0.06, 0.22), x1 - x)
            m.quad(rng.choice(palette), (x, y, zf), (x + w, y, zf), (x + w, y + row, zf), (x, y + row, zf))
            x += w + gap
        y += row + gap


def _uppers(m, x0: float, x1: float, D: float, cab: str, o: dict, y0: float = 1.38, y1: float = 2.12,
            ud: float = 0.33, glass: bool | None = None):
    """Wall cabinets over ``x0``..``x1`` against the wall at -D/2, with the style's crown."""
    box(m, _shade(cab, 0.9), x0, x1, y0, y1, -D / 2, -D / 2 + ud - 0.02)
    run = x1 - x0
    n = max(1, round(run / 0.5))
    fw = run / n
    glass = o.get("glass") if glass is None else glass
    hc = o.get("handle") or STEEL
    for k in range(n):
        fx0 = x0 + k * fw + 0.006
        fx1 = fx0 + fw - 0.012
        _front(m, cab, fx0, fx1, y0 + 0.01, y1 - 0.01, -D / 2 + ud, o, glass=bool(glass))
        hx = fx1 - 0.045 if k % 2 == 0 else fx0 + 0.03
        box(m, hc, hx, hx + 0.015, y0 + 0.06, y0 + 0.16, -D / 2 + ud, -D / 2 + ud + 0.02)
    if o.get("crown"):
        box(m, cab, x0 - 0.01, x1 + 0.01, y1, y1 + 0.05, -D / 2, -D / 2 + ud + 0.03)
        box(m, _shade(cab, 1.03), x0 - 0.02, x1 + 0.02, y1 + 0.05, y1 + 0.09, -D / 2, -D / 2 + ud + 0.06)


def _counter(m, W, D, H, c, o):
    """Base cabinets with a countertop; the auto kitchen adds a fridge, a range and a sink.
    A kitchen style (``o``) gives the doors, handles, granite, backsplash and crown."""
    cab, top = c["main"], c.get("top", "#e6e1d8")
    hc = o.get("handle") or STEEL
    fridge_w = 0.9 if o.get("fridge") else 0.0
    x0 = -W / 2 + fridge_w
    if fridge_w:
        _fridge_at(m, -W / 2, -W / 2 + fridge_w - 0.02, D, 1.8)
    box(m, "#3a3a3a", x0, W / 2, 0, 0.1, -D / 2, D / 2 - 0.07)
    box(m, _shade(cab, 0.9), x0, W / 2, 0.1, H - 0.04, -D / 2, D / 2 - 0.02)
    box(m, top, x0 - 0.01, W / 2 + 0.01, H - 0.04, H, -D / 2, D / 2 + 0.02)
    if o.get("fleck"):
        _fleck(m, o["fleck"], x0, W / 2, -D / 2, D / 2 + 0.02, H + 0.001)
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
            _front(m, cab, fx0, fx1, 0.12, H - 0.22, D / 2, o)
            _front(m, cab, fx0, fx1, H - 0.2, H - 0.06, D / 2, o)
            box(m, hc, (fx0 + fx1) / 2 - 0.06, (fx0 + fx1) / 2 + 0.06, H - 0.14, H - 0.12, D / 2, D / 2 + 0.02)
            if o.get("door"):  # a pull on the door too, by its opening edge
                hx = fx1 - 0.05 if k % 2 == 0 else fx0 + 0.035
                box(m, hc, hx, hx + 0.015, H - 0.42, H - 0.3, D / 2, D / 2 + 0.02)
    upper = bool(o.get("upper"))
    _backsplash(m, o, x0, W / 2, H, 1.38 if upper else H + 0.1, -D / 2)
    if upper:
        _uppers(m, x0, W / 2, D, cab, o)
        if range_x is not None:
            box(m, STEEL, range_x - 0.38, range_x + 0.38, 1.28, 1.43, -D / 2, -D / 2 + 0.45)


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
    if o.get("fleck"):
        _fleck(m, o["fleck"], -W / 2 - 0.02, W / 2 + 0.02, -D / 2 - 0.02, D / 2, H + 0.001)
    if o.get("sink"):
        sx, sz = 0.0, (-D / 2 + D / 2 - over) / 2
        box(m, "#9aa0a6", sx - 0.38, sx + 0.38, H, H + 0.004, sz - 0.22, sz + 0.22)
        box(m, "#5f6368", sx - 0.35, sx + 0.35, H + 0.004, H + 0.006, sz - 0.19, sz + 0.19)
        tube(m, STEEL, (sx, H, -D / 2 + 0.06), (sx, H + 0.3, -D / 2 + 0.06), 0.015, 0.015, 6)
        tube(m, STEEL, (sx, H + 0.3, -D / 2 + 0.06), (sx, H + 0.28, sz - 0.05), 0.013, 0.012, 6)
    # The fronts face the kitchen (-z): drawn facing +z, then turned round.
    part = PlantMesh()
    hc = o.get("handle") or STEEL
    n = max(1, round(W / 0.6))
    fw = W / n
    for k in range(n):
        fx0 = -W / 2 + k * fw + 0.006
        _front(part, cab, fx0, fx0 + fw - 0.012, 0.12, H - 0.06, D / 2 + 0.02, o)
        box(part, hc, fx0 + fw / 2 - 0.06, fx0 + fw / 2 + 0.06, H - 0.14, H - 0.12, D / 2 + 0.02, D / 2 + 0.04)
    _put(m, part, lambda x, y, z: (-x, y, -z))


def _fridge(m, W, D, H, c, o):
    _fridge_at(m, -W / 2, W / 2, D, H)


def _stove(m, W, D, H, c, o):
    if o.get("corner"):
        _corner_stove(m, W, H, o.get("cabinet") or WHITE, c.get("top", "#e6e1d8"), o)
    else:
        _range_at(m, 0.0, D, H)


RANGE_W = 0.76  # what _range_at draws


def _corner_size(range_w: float = RANGE_W) -> float:
    """The side of a corner stove's square: counters' depth along each wall, then the
    range (``range_w`` wide: a photo model's own width) across the corner between them."""
    return _m(PIECES["counter"].depth) + range_w / math.sqrt(2)


def _ear_clip(poly: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """Triangles of a simple counter-clockwise polygon."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    idx, tris = list(range(len(poly))), []
    while len(idx) > 3:
        for k in range(len(idx)):
            i, j, l = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i], poly[j], poly[l]
            if cross(a, b, c) <= 1e-9:
                continue
            if any(cross(a, b, poly[q]) >= 0 and cross(b, c, poly[q]) >= 0 and cross(c, a, poly[q]) >= 0
                   for q in idx if q not in (i, j, l)):
                continue
            tris.append((i, j, l))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def _prism(m, color: str, poly: list[tuple[float, float]], y0: float, y1: float):
    """An upright prism over a polygon of (x, z) points, its top and sides."""
    # Clockwise in (x, z), as box() winds its top (normal up) and outward sides.
    if sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1])) > 0:  # counter-clockwise
        poly = poly[::-1]
    for i, j, k in _ear_clip([(x, -z) for x, z in poly]):
        m.tri(color, *((poly[n][0], y1, poly[n][1]) for n in (i, j, k)))
    for (ax, az), (bx, bz) in zip(poly, poly[1:] + poly[:1]):
        m.quad(color, (ax, y0, az), (bx, y0, bz), (bx, y1, bz), (ax, y1, az))


def _inside(poly: list[tuple[float, float]], x: float, z: float) -> bool:
    """Whether (x, z) is inside a polygon (even-odd rule)."""
    hit = False
    for (ax, az), (bx, bz) in zip(poly, poly[1:] + poly[:1]):
        if (az > z) != (bz > z) and x < ax + (z - az) * (bx - ax) / (bz - az):
            hit = not hit
    return hit


def _corner_stove(m, L, H, cab, top, o: dict | None = None):
    """A range set across a corner: the corner (back-left, local -x and -z) filled
    with a cabinet and countertop, the range's front on the diagonal between the
    two counter runs, a hood and a wall cabinet above it. With ``o["model"]`` the
    range is a photo model placed beside the mesh (``corner_stove_spot``): only the
    cabinet and countertop round it are drawn, and a wall cabinet over the model's
    top (``o["upper_from"]``) when there is room."""
    o = o or {}
    d = _m(PIECES["counter"].depth)
    sd = _m(PIECES["stove"].depth)
    rw = float(o.get("range_w") or RANGE_W)
    r2 = math.sqrt(2) / 2
    mid = (L + d) / 2  # the middle of the diagonal, from the corner along each wall
    c = mid - sd / 2 * r2  # the range's centre

    def at(u, v):  # corner-relative to local
        return u - L / 2, v - L / 2

    back = mid - sd * r2
    stove_back = [(back + rw / 2 * r2, back - rw / 2 * r2), (back - rw / 2 * r2, back + rw / 2 * r2)]
    around = [(0, 0), (L, 0), (L, d), *stove_back, (d, L), (0, L)]  # the corner less the range
    base = [at(u, v) for u, v in around]
    _prism(m, "#3a3a3a", base, 0, 0.1)
    _prism(m, _shade(cab, 0.9), base, 0.1, H - 0.04)
    _prism(m, top, base, H - 0.04, H)
    if o.get("fleck"):
        _fleck(m, o["fleck"], -L / 2, L / 2, -L / 2, L / 2, H + 0.001, inside=lambda x, z: _inside(base, x, z))
    # The backsplash on both walls: the back one faces +z, the left one turned to face +x.
    _backsplash(m, o, -L / 2, L / 2, H, 1.38, -L / 2)
    side = PlantMesh()
    _backsplash(side, o, -L / 2, L / 2, H, 1.38, -L / 2)
    _put(m, side, lambda x, y, z: (z, y, -x))
    # The range, its hood and the cabinet over it, drawn facing +z and turned 45° to face
    # out of the corner.
    part = PlantMesh()
    if o.get("model"):
        y0 = max(1.38, float(o.get("upper_from") or 0) + 0.03)
    else:
        _range_at(part, 0.0, sd, H)
        box(part, STEEL, -0.38, 0.38, 1.4, 1.55, -sd / 2, -sd / 2 + 0.45)
        y0 = 1.55
    if 2.12 - y0 >= 0.2:
        _uppers(part, -rw / 2, rw / 2, sd, cab, o, y0=y0, glass=False)
    cx, cz = at(c, c)
    _put(m, part, lambda x, y, z: (cx + x * r2 + z * r2, y, cz - x * r2 + z * r2))


def corner_stove_spot(L: float, depth: float) -> tuple[float, float, tuple[float, float]]:
    """Where a photo model of a range goes in a corner stove's square (``L``): its centre
    (local x, z), its back on the cut's back line, and its front's direction (local)."""
    d = _m(PIECES["counter"].depth)
    sd = _m(PIECES["stove"].depth)
    r2 = math.sqrt(2) / 2
    u = (L + d) / 2 - sd * r2 + depth / 2 * r2
    return u - L / 2, u - L / 2, (r2, r2)


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
# A kitchen run: these stand flush against each other, without room to walk between.
_RUN = {"counter", "fridge", "stove"}
_KITCHEN = {"counter", "island", "fridge", "stove"}  # what a kitchen style draws
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
    options: tuple = ()  # what its mesh was drawn with (a counter's sink)
    corner: str | None = None  # the corner it stands in ("front-right")


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
        self.open_clear: dict[str, list[tuple]] = {}  # the keep_clear zones of opened-up walls, by side
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
                if kind == "open":
                    self.open_clear.setdefault(side, []).append(self.keep_clear[-1])

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

    def fits(self, box_: tuple, height: float, ignore: tuple = (), flush: bool = False) -> bool:
        """Whether a piece this tall with these plan bounds is inside the room, clear
        of doorways (and of windows unless it is lower than the sill) and of the
        other pieces. ``height`` is what stands against the wall: a bed's headboard
        may run up in front of a window, its mattress may not. ``flush``: a piece of
        a kitchen run may touch the run's other pieces."""
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
            if _overlap(box_, raw_box(p) if p in ignore or (flush and p.piece.builder in _RUN) else p_box(p)):
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

    def wall_spots(self, side: str, W: float, D: float, H: float, extra=None, flush: bool = False) -> list[float]:
        """Every position along ``side`` (5 cm apart) where the piece fits."""
        lo, hi = self.side_span(side)
        spots = []
        t = lo + W / 2 + 0.02
        while t <= hi - W / 2 - 0.02 + _EPS:
            cx, cz, yaw = self.against(side, t, W, D)
            if self.fits(_aabb(cx, cz, W, D, yaw), H, flush=flush) and (extra is None or extra(cx, cz, yaw)):
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
    if item.get("top"):
        colors["top"] = item["top"]
    if piece.builder == "vanity":
        colors["wood_cab"] = item.get("color") or named or item.get("wood") or "#f0ede6"
    return tuple(sorted(colors.items()))


# --- Building it ------------------------------------------------------------------

class Furnishing:
    """Collects the furniture of a house: shared meshes with their instances, the
    photo models, and notes about what did not fit."""

    def __init__(self, models: list[dict] | None, styles: list[dict] | None = None):
        self.meshes: dict[str, dict] = {}
        self.pieces: list[dict] = []
        self.models: list[dict] = []
        self.photo_models = models or []
        self.styles = styles or []
        self.room_name = ""  # the room being furnished, for each piece's ``ref``
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
        if not key:
            return None
        # "my office desk" is the "Office desk" model; the longest name that fits wins.
        return next((m for m in self.photo_models if name_key(m["name"]) == key), None) or max(
            (m for m in self.photo_models if name_key(m["name"]) and re.search(rf"\b{re.escape(name_key(m['name']))}\b", key)),
            key=lambda m: len(name_key(m["name"])), default=None)

    def kitchen_style(self, name: Any) -> dict | None:
        """The saved kitchen style ``name`` calls for ("farmhouse" is "Farmhouse kitchen")."""
        key = name_key(name)
        if not key or not self.styles:
            return None
        return next((s for s in self.styles if name_key(s["name"]) == key), None) or max(
            (s for s in self.styles if name_key(s["name"]) and (
                re.search(rf"\b{re.escape(name_key(s['name']))}\b", key) or re.search(rf"\b{re.escape(key)}\b", name_key(s["name"])))),
            key=lambda s: len(name_key(s["name"])), default=None)

    def add(self, room_id: int, item: dict, piece: Piece, W: float, D: float, H: float,
            cx: float, cz: float, yaw: float, options: tuple = (), photo: bool = True):
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
        if "_i" in item:
            # Which item of the plan this is, so the headset can move it (PUT .../furniture/move).
            out["ref"] = {"room": self.room_name, "item": item["_i"], "width": round(W / FT_TO_M, 1),
                          "depth": round(D / FT_TO_M, 1), **({"auto": True} if item.get("auto") else {})}
        model = self._photo_model(item) if photo else None
        if model:
            out.update({"model_id": model["id"], "url": model["url"], "scale": round(H, 3)})
            if model.get("turn"):  # the way the photo was taken is not the piece's front
                out["yaw"] = round((yaw + model["turn"]) % 360, 1)
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
        spots = space.wall_spots(side, W, D, _wall_height(piece, H), flush=piece.builder in _RUN)
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


def _seated(item: dict, piece: Piece, W: float, D: float, H: float, cx: float, cz: float, yaw: float,
            seats: list[tuple[float, float, float]], chair: tuple[float, float, float],
            side: str | None = None) -> Placed:
    cw, cd, ch = chair
    parts = []
    for lx, lz, lyaw in seats:
        dx, dz = _turn(yaw, lx, lz)
        parts.append((cx + dx, cz + dz, cw, cd, yaw + lyaw))
    return Placed(item, piece, W, D, H, cx, cz, yaw, side, tuple(parts))


def _place_center(space: RoomSpace, item: dict, piece: Piece, W: float, D: float, H: float,
                  seats: list[tuple[float, float, float]], chair: tuple[float, float, float]) -> Placed | None:
    """In the middle of the room (or the free spot nearest it), long side along the
    room's long side, with its chairs; its front toward ``facing`` if the plan gives one."""
    room_w, room_d = space.size
    yaws = [0.0, 90.0] if room_w >= room_d else [90.0, 0.0]
    if W < D:
        yaws.reverse()
    if item.get("facing"):
        yaws = [yaw_facing(*_FACING[item["facing"]])]
    cx0, cz0 = (space.x0 + space.x1) / 2, (space.z0 + space.z1) / 2
    step = 0.1
    ni, nj = int(room_w / 2 / step) + 1, int(room_d / 2 / step) + 1
    candidates = [(cx0 + i * step, cz0 + j * step) for i in range(-ni, ni + 1) for j in range(-nj, nj + 1)]
    candidates.sort(key=lambda p: (p[0] - cx0) ** 2 + (p[1] - cz0) ** 2)
    for yaw in yaws:
        for cx, cz in candidates:
            placed = _seated(item, piece, W, D, H, cx, cz, yaw, seats, chair)
            if _try_place(space, placed):
                return placed
    return None


def _span(zone: tuple, side: str) -> tuple[float, float]:
    """How far a keep-clear zone on ``side`` runs along that side."""
    return (zone[0], zone[1]) if side in ("front", "back") else (zone[2], zone[3])


def _place_along(space: RoomSpace, item: dict, piece: Piece, W: float, D: float, H: float, side: str,
                 seats: list[tuple[float, float, float]], chair: tuple[float, float, float]) -> Placed | None:
    """With its back on ``side`` (an island backing onto a wall, or onto the open edge
    of the next room), its chairs in front, as near the middle of that side as fits.
    An opened-up wall on that side is not kept clear: the rest of it is the way through.
    ``facing`` the same open side turns it round: its front at the edge and its chairs
    out in the next room (stools on the family-room side of a kitchen island)."""
    lo, hi = space.side_span(side)
    mid, step = (lo + hi) / 2, 0.05
    n = int((hi - lo) / 2 / step) + 1
    open_zones = space.open_clear.get(side, [])
    outward = item.get("facing") == side and bool(open_zones)
    saved = space.keep_clear
    space.keep_clear = [k for k in saved if k not in open_zones]
    try:
        for t in sorted((mid + i * step for i in range(-n, n + 1)), key=lambda t: abs(t - mid)):
            if t - W / 2 < lo - _EPS or t + W / 2 > hi + _EPS:
                continue
            cx, cz, yaw = space.against(side, t, W, D)
            if not outward:
                placed = _seated(item, piece, W, D, H, cx, cz, yaw, seats, chair, side)
                if _try_place(space, placed):
                    return placed
                continue
            # The chairs go through the opening, so all of it must be open; only
            # the island itself has to fit in this room.
            if not any(_span(z, side)[0] <= t - W / 2 + _EPS and t + W / 2 <= _span(z, side)[1] + _EPS
                       for z in open_zones):
                continue
            yaw = (yaw + 180) % 360
            if _try_place(space, Placed(item, piece, W, D, H, cx, cz, yaw, side)):
                space.placed[-1] = _seated(item, piece, W, D, H, cx, cz, yaw, seats, chair, side)
                return space.placed[-1]
    finally:
        space.keep_clear = saved
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


_FACING = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}


def _place_exact(space: RoomSpace, item: dict, piece: Piece, W: float, D: float, H: float) -> Placed:
    """Where the plan says (feet from the room's front-left corner), kept inside the room."""
    r = space.rect
    cx, cz = r["x0"] + _m(item["x"]), r["z0"] + _m(item["z"])
    if "rotation" in item:
        # Turned any way (as it was left after being grabbed and moved).
        x0, x1, z0, z1 = _aabb(cx, cz, W, D, item["rotation"])
        cx += max(0.0, space.x0 - x0) - max(0.0, x1 - space.x1)
        cz += max(0.0, space.z0 - z0) - max(0.0, z1 - space.z1)
        placed = Placed(item, piece, W, D, H, cx, cz, item["rotation"])
        space.placed.append(placed)
        return placed
    facing = item.get("facing")
    if facing:
        fx, fz = _FACING[facing]
    else:
        # Toward the middle of the room, along whichever axis is further off.
        mx, mz = (space.x0 + space.x1) / 2 - cx, (space.z0 + space.z1) / 2 - cz
        fx, fz = ((1 if mx > 0 else -1), 0) if abs(mx) > abs(mz) else (0, (1 if mz > 0 else -1))
    # Facing left or right the piece lies across: its width runs along z.
    ex, ez = (D, W) if fx else (W, D)
    cx = min(max(cx, space.x0 + ex / 2), space.x1 - ex / 2)
    cz = min(max(cz, space.z0 + ez / 2), space.z1 - ez / 2)
    placed = Placed(item, piece, W, D, H, cx, cz, yaw_facing(fx, fz))
    space.placed.append(placed)
    return placed


def _counter_options(space: RoomSpace, side: str, cx: float, cz: float, W: float, item: dict,
                     items: list[dict] = ()) -> tuple:
    """A kitchen run: a sink (one per room), a range on a long run unless the room has
    a stove of its own, the fridge when it was furnished automatically, wall cabinets
    where no window is in the way."""
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
    run = W - (0.9 if fridge else 0)
    stove = any(PIECES[it["type"]].builder == "stove" for it in items)
    sink = not any(p.piece.builder in ("counter", "island") and dict(p.options).get("sink") for p in space.placed)
    # What the plan says wins over what a kitchen usually has.
    return (("fridge", fridge), ("range", item.get("range", run >= 2.0 and not stove) and run >= 1.0),
            ("sink", item.get("sink", sink) and run >= 1.0), ("upper", item.get("uppers", not window)))


def _styled(item: dict, style: dict | None) -> dict:
    """A kitchen piece in a saved kitchen style: its cabinet and countertop colours (a
    colour of its own wins), and a stove or fridge with nothing named is the style's
    photo model."""
    builder = PIECES[item["type"]].builder
    if not style or builder not in _KITCHEN:
        return item
    out = {**item, "kitchen": style}
    if builder in ("counter", "island"):
        out.setdefault("color", style["cabinet"])
    out.setdefault("top", style["top"])
    model_id = style.get(f"{builder}_model_id")
    # A name that only says what it is ("stove": the AI names pieces so) is no name of a model.
    generic = name_key(item.get("name")) in ("", name_key(item["type"]), name_key(PIECES[item["type"]].label))
    if builder in ("stove", "fridge") and model_id and generic and "model_id" not in item:
        out["model_id"] = model_id
    return out


def _style_options(item: dict) -> tuple:
    """What a kitchen style changes in a piece's mesh (also its cache key)."""
    st = item.get("kitchen")
    if not st:
        return ()
    return (("door", st["door"]), ("glass", st["uppers"] == "glass"), ("handle", st["handle"]),
            ("crown", bool(st["crown"])), ("fleck", st.get("fleck") or ""),
            ("splash", st["backsplash"] if st["backsplash"] != "none" else ""),
            ("splash_color", st["backsplash_color"] if st["backsplash"] != "none" else ""))


def _model_size(model: dict, item: dict, H: float) -> tuple[float, float, float]:
    """A photo model's real width, depth and height (metres), turned as it is placed."""
    h = _m(item["height"]) if "height" in item else _m(model["height_ft"]) if model.get("height_ft") else H
    mx, mz = (v * h for v in model["footprint"])
    return (mz, mx, h) if model.get("turn") in (90, 270) else (mx, mz, h)


def furnish_room(f: Furnishing, room_id: int, space: RoomSpace, items: list[dict]):
    """Place ``items`` in ``space`` and add them to ``f``."""
    # One kitchen style for the room: the first piece that names one.
    style = next((st for st in (f.kitchen_style(it.get("style")) for it in items if it.get("style")) if st), None)
    items = [_styled(it, style) for it in items]
    expanded: list[dict] = []
    for item in items:
        for _ in range(item.get("count", 1) if PIECES[item["type"]].builder not in ("stool",) else 1):
            expanded.append(item)
    run_built = any("corner" in it or "between" in it for it in expanded)
    order = sorted(
        range(len(expanded)),
        key=lambda i: (0 if "x" in expanded[i] else 1,
                       # Pieces in a corner first (the runs butt against them), then counters between two
                       # pieces, then (in such a kitchen) the other counters, which take what is left, and
                       # the island in the floor the runs leave.
                       0 if "corner" in expanded[i] else 2 if "between" in expanded[i]
                       else 3 if run_built and PIECES[expanded[i]["type"]].builder == "counter"
                       else 4 if run_built and PIECES[expanded[i]["type"]].builder == "island" else 1,
                       _ORDER.get(PIECES[expanded[i]["type"]].place, 0) if not expanded[i].get("place") else 0, i),
    )
    for i in order:
        item = expanded[i]
        piece = PIECES[item["type"]]
        W, D, H = _size(item, piece, space)
        model = f._photo_model(item)
        if model and model.get("footprint") and "width" not in item and "depth" not in item:
            # A photo model takes the space it really fills, not the drawn piece's.
            W, D, _ = _model_size(model, item, H)
        label = _label(item, piece)
        place = item.get("place") or piece.place
        if place == "center" and piece.builder in _WALL_BUILDERS:
            place = piece.place  # a sofa or a bed "in the middle of the room" still has its back to a wall
        sofa = _find(space, "sofa", "sectional")
        placed: Placed | None = None
        options: tuple = ()
        drawn = False  # a corner stove's cabinet, drawn round its photo model
        seats = item.get("seats", piece.seats)

        if piece.builder == "counter" and "x" not in item:
            if item.get("between"):
                placed = _place_between(space, item, piece, D, H)
                if placed is None:
                    a, b = (PIECES[k].label or k for k in item["between"])
                    f.notes.append(f"No room for a counter between the {a} and the {b} in {space.name}")
                    continue
            else:
                prefer = item.get("place") if item.get("place") in _SIDES else None
                placed = _place_counter(space, item, piece, D, H, prefer) if prefer or not run_built else None
                if placed is None and run_built:
                    # "Cabinets on the other side of the fridge": on along the walls the run stands on,
                    # then (none named) any wall.
                    # The AI's guess at a length gives way to what is there.
                    loose = {k: v for k, v in item.items() if k != "width"}
                    for side in dict.fromkeys(p.side for p in space.placed if p.piece.builder in _RUN and p.side):
                        if side != prefer and (placed := _place_counter(space, item, piece, D, H, side)
                                               or _place_counter(space, loose, piece, D, H, side)):
                            break
                    if placed is None and not prefer:
                        placed = _place_counter(space, item, piece, D, H)
                if placed is None and prefer and any(
                        p.piece.builder == "counter" and p.side == prefer for p in space.placed):
                    continue  # that wall has its counter already (one between two pieces)
        elif piece.builder == "stove" and item.get("corner") and "x" not in item:
            # A photo model of the range: the corner is cut to its width.
            range_w = min(1.0, max(0.6, _model_size(model, item, H)[0])) if model and model.get("footprint") else RANGE_W
            placed = _place_corner_stove(space, item, piece, H, range_w)
            if placed is None:
                f.notes.append(f"No free corner for the stove in {space.name}")
                continue
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
                elif piece.builder == "island" and place in _SIDES:
                    placed = _place_along(space, item, piece, W, D, H, place, layout, (cw, cd, ch))
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
        elif run_built and (not item.get("place") or any(
                "width" in it and item["type"] in (it.get("between") or []) for it in items)) and (
                placed := _run_end(space, item, piece, W, D, H, items)):
            pass  # an end of a counter run (where a "between" counter with a width puts it)
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
        elif item.get("corner") in _CORNERS:
            sides = item["corner"].split("-")
            point = (space.x0 if "left" in sides else space.x1, space.z0 if "front" in sides else space.z1)
            prefer = [place] + [s_ for s_ in sides if s_ != place] if place in sides else sides
            placed = _place_wall(space, item, piece, W, D, H, prefer=prefer, near=point)
            if placed:
                placed.corner = item["corner"]
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

        if placed is None and run_built and piece.builder in _RUN:
            placed = _run_end(space, item, piece, W, D, H, items)  # the wall asked for is full
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
            options = _counter_options(space, placed.side or "back", placed.cx, placed.cz, placed.W, item, items)
        elif piece.builder == "stove" and item.get("corner"):
            counter = next((it for it in items if PIECES[it["type"]].builder == "counter"), {"type": "counter"})
            options = (("corner", True), ("cabinet", item.get("color") or dict(_colors(counter, PIECES["counter"]))["main"]))
            if model and model.get("footprint"):
                mw, md, mh = _model_size(model, item, H)
                lx, lz, (fx, fz) = corner_stove_spot(placed.W, md)
                dx, dz = _turn(placed.yaw, lx, lz)
                f.add(room_id, item, piece, mw, md, mh, placed.cx + dx, placed.cz + dz,
                      yaw_facing(*_turn(placed.yaw, fx, fz)))
                options += (("range_w", f"{range_w:.2f}"), ("model", True), ("upper_from", f"{mh:.2f}"))
                drawn = True
        elif piece.builder == "potted_plant":
            species = find_species(item.get("name"))
            options = (("species", species),) if species else ()
        if piece.builder == "island" and item.get("sink"):
            options = (("sink", True),)
        if piece.builder in ("counter", "island", "stove"):
            options += _style_options(item)
        placed.options = options
        f.add(room_id, item, piece, placed.W, placed.D, placed.H, placed.cx, placed.cz, placed.yaw, options,
              photo=not drawn)


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
        for W in ([want] if want else [hi - lo - 0.04 - k * 0.1 for k in range(60)]):
            if W is None or W < 0.9:
                break
            spots = space.wall_spots(side, W, D, _wall_height(piece, H), flush=True)
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
    spots = space.wall_spots(side, W, D, _wall_height(piece, H), flush=True)
    if not spots:
        return None
    lo, hi = space.side_span(side)
    t = min(spots, key=lambda s: abs(s - (lo + W / 2 + 0.02)))  # into a corner
    cx, cz, yaw = space.against(side, t, W, D)
    placed = Placed(item, piece, W, D, H, cx, cz, yaw, side)
    space.placed.append(placed)
    return placed


def _place_corner_stove(space: RoomSpace, item: dict, piece: Piece, H: float,
                        range_w: float = RANGE_W) -> Placed | None:
    """A range across a corner (``item["corner"]``, or the first free one), in a
    square of counter that the runs on both walls butt against."""
    L = _corner_size(range_w)
    corners = {"front-left": (space.x0, space.z0), "front-right": (space.x1, space.z0),
               "back-left": (space.x0, space.z1), "back-right": (space.x1, space.z1)}
    names = [item["corner"]] if item.get("corner") in corners else list(corners)
    for name in names:
        x, z = corners[name]
        sx, sz = (1 if x == space.x0 else -1), (1 if z == space.z0 else -1)
        cx, cz = x + sx * (L / 2 + 0.02), z + sz * (L / 2 + 0.02)
        if not space.fits(_aabb(cx, cz, L, L, 0), _wall_height(PIECES["counter"], H), flush=True):
            continue
        # The mesh has the corner at its back-left: back on one wall, left on the other.
        for fx, fz in ((0, sz), (sx, 0)):
            yaw = yaw_facing(fx, fz)
            lx, lz = _turn(yaw, -1, 0)
            if (round(lx), round(lz)) in ((-sx, 0), (0, -sz)):
                side = {(0, 1): "front", (0, -1): "back", (1, 0): "left", (-1, 0): "right"}[(fx, fz)]
                placed = Placed(item, piece, L, L, H, cx, cz, yaw, side, corner=name)
                space.placed.append(placed)
                return placed
    return None


def _run_end(space: RoomSpace, item: dict, piece: Piece, W: float, D: float, H: float,
              items: list[dict]) -> Placed | None:
    """A piece a counter runs to ("between") from a piece in a corner: at the far
    end of one of that corner's walls, the longer first, so the counter fills the wall.
    A counter with a ``width`` sets the gap instead: the piece stands that far along the
    wall from the corner piece, leaving the rest of the wall for other cabinets."""
    for it in items:
        ends = it.get("between") or []
        if item["type"] not in ends:
            continue
        other = PIECES[ends[1] if ends[0] == item["type"] else ends[0]].builder
        anchor = next((p for p in space.placed if p.piece.builder == other and p.corner), None)
        if not anchor:
            continue
        corner = anchor.corner
        fb, lr = corner.split("-")
        if "width" in it:
            gap = _m(it["width"])
            box_ = raw_box(anchor)
            for side in sorted((fb, lr), key=lambda w: -(space.side_span(w)[1] - space.side_span(w)[0])):
                a0, a1 = _along(box_, side)
                # Away from the corner: on from the anchor's far edge (left/front corners
                # run toward +x/+z along the wall, the others back).
                ahead = (lr == "left") if side in ("front", "back") else (fb == "front")
                t = a1 + gap + W / 2 + 0.002 if ahead else a0 - gap - W / 2 - 0.002
                cx, cz, yaw = space.against(side, t, W, D)
                if space.fits(_aabb(cx, cz, W, D, yaw), _wall_height(piece, H), flush=True):
                    placed = Placed(item, piece, W, D, H, cx, cz, yaw, side)
                    space.placed.append(placed)
                    return placed
        far = {"front": space.z1, "back": space.z0, "left": space.x1, "right": space.x0}
        walls = sorted([(fb, (far[lr], space.z0 if fb == "front" else space.z1)),
                        (lr, (space.x0 if lr == "left" else space.x1, far[fb]))],
                       key=lambda w: -(space.side_span(w[0])[1] - space.side_span(w[0])[0]))
        for side, point in walls:
            placed = _place_wall(space, item, piece, W, D, H, prefer=[side], near=point)
            if placed:
                return placed
    return None


def _along(box_: tuple, side: str) -> tuple[float, float]:
    return (box_[0], box_[1]) if side in ("front", "back") else (box_[2], box_[3])


def _touches(space: RoomSpace, box_: tuple, side: str) -> bool:
    x0, x1, z0, z1 = box_
    return {"front": z0 <= space.z0 + 0.1, "back": z1 >= space.z1 - 0.1,
            "left": x0 <= space.x0 + 0.1, "right": x1 >= space.x1 - 0.1}[side]


def _place_between(space: RoomSpace, item: dict, piece: Piece, D: float, H: float) -> Placed | None:
    """A counter filling the wall between two pieces already placed (``between``:
    "from the stove to the refrigerator"), on the wall both stand against."""
    ends = []
    for kind in item["between"]:
        builder = PIECES[kind].builder
        found = [p for p in space.placed if p.piece.builder == builder]
        if not found:
            return None
        ends.append(found)
    best = None
    for side in ([item["place"]] if item.get("place") in _SIDES else list(_SIDES)):
        for a in ends[0]:
            for b in ends[1]:
                ba, bb = raw_box(a), raw_box(b)
                if not (_touches(space, ba, side) and _touches(space, bb, side)):
                    continue
                (a0, a1), (b0, b1) = _along(ba, side), _along(bb, side)
                lo, hi = (a1, b0) if a1 <= b0 + _EPS else (b1, a0)
                W = hi - lo - 0.004
                if W < 0.3 or (best and W <= best[0]):
                    continue
                cx, cz, yaw = space.against(side, (lo + hi) / 2, W, D)
                if space.fits(_aabb(cx, cz, W, D, yaw), _wall_height(piece, H), flush=True):
                    best = (W, side, cx, cz, yaw)
    if best is None:
        return None
    W, side, cx, cz, yaw = best
    placed = Placed(item, piece, W, D, H, cx, cz, yaw, side)
    space.placed.append(placed)
    return placed


def build_furniture(
    spec: dict | None,
    rooms: list[dict],
    openings: list[dict],
    models: list[dict] | None = None,
    styles: list[dict] | None = None,
    blocked: list[dict] | None = None,
) -> tuple[dict | None, list[str]]:
    """Furniture for every room, metres (the headset scales it).

    ``rooms`` are ``{"id", "name", "bounds"}`` as built, ``openings`` every door,
    window and opened-up wall cut in the walls, ``models`` the finished photo models
    of kind "furniture", ``styles`` the saved kitchen styles
    (``kitchen_style_service.ready_styles``), ``blocked`` floor nothing may stand on
    (stairs, the hole they come up through). Returns ``({"meshes", "pieces", "models"}, notes)``, or
    ``(None, [])`` when the plan has no furniture.
    """
    if not spec or not rooms:
        return None, []
    listed = {k.strip().lower(): v for k, v in (spec.get("rooms") or {}).items()}
    f = Furnishing(models, styles)
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
        items = [{**it, "_i": n} for n, it in enumerate(items)]
        f.room_name = name
        space = RoomSpace(name, b, openings)
        for r in blocked or []:
            if min(r["x1"], b["x1"]) > max(r["x0"], b["x0"]) and min(r["z1"], b["z1"]) > max(r["z0"], b["z0"]):
                w, d = r["x1"] - r["x0"] + 0.2, r["z1"] - r["z0"] + 0.2  # and a step round it
                space.placed.append(Placed({"type": "custom"}, PIECES["custom"], w, d, 3.0,
                                           (r["x0"] + r["x1"]) / 2, (r["z0"] + r["z1"]) / 2, 0.0))
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
