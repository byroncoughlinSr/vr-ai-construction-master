"""The outside of the house: roof, wall finish, ground and landscaping.

A floor plan may carry an ``exterior`` description (sizes in feet, positions in
the layout's coordinates: x along the footprint's length from its left edge, z
from the street side (z = 0) toward the back, so the front yard is at z < 0):

    {"roof": {"style": "hip", "material": "clay_tile", "color": "#b5562f", "pitch": 5, "overhang": 1.5},
     "walls": {"material": "stucco", "color": "#e3d4b6"},
     "trim": {"color": "#ffffff"},
     "ground": {"material": "grass", "color": "#5f8f3e"},
     "landscape": [{"type": "palm", "x": 6, "z": -6, "height": 18}, ...]}

``exterior_spec`` cleans what the AI returns into that shape (named colors become
hex, unknown types are dropped). ``build_exterior`` turns it into what the headset
draws, in metres: roof triangle meshes, box ``parts`` for the wall finish, ground and
paving, and plants (``vr_plants``: low-poly meshes per species, drawn as instances).
A plant may also stand for a 3D model made from a photo (``plant_model_service``);
those are the only files, and the plan stores just their id or name.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

from .vr_plants import FLOWER_COLORS, SPECIES, Yard, find_species, name_key
from .vr_geometry_service import (
    FT_TO_M,
    WALL_T,
    _EPS,
    _feet,
    _opening_on,
    _room_sides,
    exterior_intervals,
)

logger = logging.getLogger(__name__)

# --- Vocabulary --------------------------------------------------------------

ROOF_STYLES = ("gable", "hip", "flat", "shed")
ROOF_MATERIALS = {
    "clay_tile": "#b5562f",
    "concrete_tile": "#8c7b6b",
    "asphalt_shingle": "#55575a",
    "metal": "#5f6b73",
    "slate": "#4a5058",
    "wood_shake": "#8a6a48",
}
WALL_MATERIALS = {
    "stucco": "#e3d4b6",
    "siding": "#dfe3e6",
    "brick": "#9c4a32",
    "stone": "#a39a8c",
    "wood": "#a57a52",
    "paint": "#f2f0eb",
}
GROUND_MATERIALS = {"grass": "#5f8f3e", "gravel": "#a49d92", "dirt": "#7b5d43", "sand": "#d8c9a3"}
SURFACE_MATERIALS = {
    "concrete": "#bdb8ae",
    "pavers": "#a8826a",
    "brick": "#9c4a32",
    "stone": "#a39a8c",
    "tile": "#c9a77c",
    "gravel": "#a49d92",
    "asphalt": "#3f4042",
    "wood": "#9b7653",
    "grass": "#5f8f3e",
    "water": "#3fa7d6",
    "mulch": "#5a3f2b",
}
# Surfaces in these materials are laid as individual tiles (size in metres).
TILE_SIZES = {"pavers": 0.6, "brick": 0.4, "stone": 0.75, "tile": 0.6}

NAMED_COLORS = {
    "white": "#f4f4f0", "off white": "#eeebe2", "cream": "#efe6cf", "ivory": "#f2ecd8",
    "beige": "#e3d4b6", "tan": "#cdb48e", "sand": "#d8c9a3", "khaki": "#c3b091",
    "taupe": "#a39282", "brown": "#7b5536", "dark brown": "#4e3424", "chocolate": "#5a3a26",
    "terracotta": "#c0623a", "rust": "#a4482a", "red": "#a63a32", "brick red": "#9c4a32",
    "burgundy": "#6e2430", "orange": "#e07b39", "yellow": "#e8c547", "gold": "#c9a227",
    "green": "#4f7a35", "sage": "#9caf88", "olive": "#6b6b3a", "dark green": "#2f4f2a",
    "forest green": "#2e5a33", "blue": "#3c6e9e", "light blue": "#9cc3dd", "navy": "#24344d",
    "teal": "#2f7f7a", "gray": "#8a8a88", "grey": "#8a8a88", "light gray": "#c4c4c0",
    "light grey": "#c4c4c0", "dark gray": "#4f5052", "dark grey": "#4f5052",
    "charcoal": "#3b3d40", "slate": "#4a5058", "black": "#222222", "pink": "#e39aac",
    "purple": "#7d5ba6", "lavender": "#b6a4d6",
    **FLOWER_COLORS,
}

POINT_TYPES = ("tree", "pine", "palm", "shrub", "rock")
LINE_TYPES = ("hedge", "fence", "garden_wall")
SURFACE_TYPES = ("lawn", "path", "driveway", "patio", "deck", "flower_bed", "pool")
_TYPE_ALIASES = {
    "bush": "shrub", "shrubs": "shrub", "plant": "shrub", "boulder": "rock", "stone": "rock",
    "oak": "tree", "maple": "tree", "fir": "pine", "spruce": "pine", "conifer": "pine",
    "evergreen": "pine", "palm_tree": "palm", "flowers": "flower_bed", "flowerbed": "flower_bed",
    "garden": "flower_bed", "garden_bed": "flower_bed", "walkway": "path", "sidewalk": "path",
    "grass": "lawn", "yard": "lawn", "terrace": "patio", "wall": "garden_wall",
    "swimming_pool": "pool",
}
# Feet: (height, width) for points, (height, width) for lines, (default material) for surfaces.
_POINT_DEFAULTS = {"tree": (16.0, 10.0), "pine": (20.0, 8.0), "palm": (18.0, 8.0), "shrub": (3.0, 3.0), "rock": (1.5, 2.5)}
_LINE_DEFAULTS = {"hedge": (4.0, 2.0, "#3f6b2f"), "fence": (4.0, 0.3, "#f4f4f0"), "garden_wall": (3.0, 1.0, "#a39a8c")}
_SURFACE_MATERIAL = {
    "lawn": "grass", "path": "concrete", "driveway": "concrete", "patio": "pavers",
    "deck": "wood", "flower_bed": "mulch", "pool": "water",
}

MAX_ITEMS = 80
MAX_ABS_FT = 400.0  # nothing further than this from the house


# --- Cleaning the description --------------------------------------------------

def _key(value: Any) -> str:
    return re.sub(r"[\s-]+", "_", str(value or "").strip().lower())


def _choice(value: Any, options, default: str | None) -> str | None:
    key = _key(value)
    for option in options:
        if key == option or key.replace("_", "") == option.replace("_", ""):
            return option
    # "clay tiles", "spanish tile" → clay_tile; "shingles" → asphalt_shingle
    for option in options:
        if any(word and word in key for word in option.split("_") if len(word) > 3):
            return option
    return default


def color_hex(value: Any, default: str) -> str:
    """A ``#rrggbb`` color from hex or a common color name."""
    text = str(value or "").strip().lower()
    if re.fullmatch(r"#?[0-9a-f]{6}", text):
        return "#" + text.lstrip("#")
    if re.fullmatch(r"#?[0-9a-f]{3}", text):
        return "#" + "".join(c * 2 for c in text.lstrip("#"))
    text = text.replace("-", " ").replace("_", " ")
    if text in NAMED_COLORS:
        return NAMED_COLORS[text]
    for name in sorted(NAMED_COLORS, key=len, reverse=True):  # "warm beige" → beige
        if re.search(rf"\b{re.escape(name)}\b", text):
            return NAMED_COLORS[name]
    return default


def _rgb(hex_color: str) -> dict:
    h = hex_color.lstrip("#")
    return {k: round(int(h[i:i + 2], 16) / 255, 3) for k, i in (("r", 0), ("g", 2), ("b", 4))}


def _shade(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    parts = [min(255, max(0, round(int(h[i:i + 2], 16) * factor))) for i in (0, 2, 4)]
    return "#" + "".join(f"{p:02x}" for p in parts)


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and abs(number) <= MAX_ABS_FT else None


def _pt(raw: Any) -> dict | None:
    if isinstance(raw, dict):
        x, z = _num(raw.get("x")), _num(raw.get("z"))
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        x, z = _num(raw[0]), _num(raw[1])
    else:
        return None
    return None if x is None or z is None else {"x": round(x, 1), "z": round(z, 1)}


def _clean_item(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    kind = _key(raw.get("type"))
    known = POINT_TYPES + LINE_TYPES + SURFACE_TYPES
    plant = raw.get("plant") or raw.get("species") or raw.get("variety")
    for guess in (kind, kind[:-1] if kind.endswith("s") else "", kind[:-2] if kind.endswith("es") else ""):
        guess = _TYPE_ALIASES.get(guess, guess)
        if guess in known:
            kind = guess
            break
    else:
        # {"type": "hydrangea"} or {"type": "coral rose"}: a plant named as its type.
        species = find_species(raw.get("type"))
        if not species:
            return None
        kind = SPECIES[species].category
        plant = plant or str(raw.get("type"))
    item: dict[str, Any] = {"type": kind}
    start, end = _pt(raw.get("from")), _pt(raw.get("to"))
    center = _pt(raw)
    if kind in LINE_TYPES or (kind in SURFACE_TYPES and start and end and not center):
        if not (start and end) or (start == end):
            return None
        item["from"], item["to"] = start, end
    elif center:
        item.update(center)
    else:
        return None
    for key in ("width", "depth", "height"):
        value = _num(raw.get(key))
        if value is not None and value > 0:
            item[key] = round(value, 1)
    if raw.get("color"):
        item["color"] = color_hex(raw.get("color"), "")
        if not item["color"]:
            del item["color"]
    if kind in SURFACE_TYPES:
        material = _choice(raw.get("material"), SURFACE_MATERIALS, None)
        if material:
            item["material"] = material
    if kind == "fence" and _key(raw.get("style")) in ("privacy", "solid"):
        item["style"] = "privacy"
    if plant and kind in POINT_TYPES + ("flower_bed", "hedge"):
        item["plant"] = re.sub(r"\s+", " ", str(plant)).strip()[:60]
    if raw.get("flower_color") and kind in POINT_TYPES + ("flower_bed",):
        flower = color_hex(raw.get("flower_color"), "")
        if flower:
            item["flower_color"] = flower
    model_id = raw.get("model_id")
    if isinstance(model_id, (int, float, str)) and str(model_id).strip().isdigit() and kind in POINT_TYPES:
        item["model_id"] = int(str(model_id).strip())
    if raw.get("label"):
        item["label"] = str(raw["label"])[:60]
    return item


def exterior_spec(raw: Any) -> dict | None:
    """Clean an ``exterior`` description (as the AI or the dashboard sent it).

    Returns the stored form, or None when there is nothing usable. Parts left out
    stay as they are today: no roof, white walls, no ground or plants.
    """
    if not isinstance(raw, dict):
        return None
    spec: dict[str, Any] = {}

    # An empty object asks for one with the defaults.
    roof = raw.get("roof")
    if isinstance(roof, dict):
        material = _choice(roof.get("material"), ROOF_MATERIALS, "asphalt_shingle")
        pitch = _num(roof.get("pitch"))
        overhang = _num(roof.get("overhang"))
        spec["roof"] = {
            "style": _choice(roof.get("style"), ROOF_STYLES, "gable"),
            "material": material,
            "color": color_hex(roof.get("color"), ROOF_MATERIALS[material]),
            "pitch": round(min(12.0, max(1.0, pitch)), 1) if pitch else 5.0,
            "overhang": round(min(3.0, max(0.0, overhang)), 1) if overhang is not None else 1.5,
        }

    walls = raw.get("walls")
    if isinstance(walls, dict):
        material = _choice(walls.get("material"), WALL_MATERIALS, "paint")
        spec["walls"] = {"material": material, "color": color_hex(walls.get("color"), WALL_MATERIALS[material])}

    trim = raw.get("trim")
    if isinstance(trim, dict) and trim.get("color"):
        spec["trim"] = {"color": color_hex(trim.get("color"), "#f4f4f0")}

    ground = raw.get("ground")
    if isinstance(ground, dict):
        material = _choice(ground.get("material"), GROUND_MATERIALS, "grass")
        spec["ground"] = {"material": material, "color": color_hex(ground.get("color"), GROUND_MATERIALS[material])}

    items = [i for i in (_clean_item(r) for r in (raw.get("landscape") or [])[:MAX_ITEMS * 2]) if i]
    if items:
        spec["landscape"] = items[:MAX_ITEMS]

    return spec or None


# --- Building it ------------------------------------------------------------------

SKIN_T = 0.02  # outside finish on exterior walls, metres
GROUND_TOP = -0.10  # the house's floors sit on a foundation this far above the yard
FOUNDATION_COLOR = "#9a968e"
YARD_FRONT, YARD_SIDE, YARD_BACK = 9.0, 6.0, 6.0  # metres of yard around the footprint
MAX_TILES = 300  # per surface; tiles grow to stay under it


def _box(center: tuple[float, float, float], size: tuple[float, float, float], color: str,
         yaw: float = 0.0, walkable: bool = False, kind: str = "landscape") -> dict:
    part = {
        "shape": "box",
        "center": {"x": round(center[0], 4), "y": round(center[1], 4), "z": round(center[2], 4)},
        "size": {"x": round(size[0], 4), "y": round(size[1], 4), "z": round(size[2], 4)},
        "yaw": round(yaw, 2),
        "color": _rgb(color),
        "kind": kind,
    }
    if walkable:
        part["walkable"] = True
    return part


def _sphere(center: tuple[float, float, float], size: tuple[float, float, float], color: str,
            yaw: float = 0.0) -> dict:
    part = _box(center, size, color, yaw)
    part["shape"] = "sphere"
    return part


# Roof ------------------------------------------------------------------------------

def roof_sections(rects: list[dict], heights: list[float]) -> list[tuple[dict, float, list[int]]]:
    """Merge room rectangles into as few roof rectangles as possible.

    Two pieces merge when they share a whole edge, so a plain rectangular house
    gets one roof and an L-shaped one two. Returns ``(rect, eave height, room
    indices)``: the eave sits on the tallest room under it, and the outside finish
    of lower rooms runs up to meet it.
    """
    pieces = [(dict(r), h, [i]) for i, (r, h) in enumerate(zip(rects, heights))]
    while True:
        best = None
        for i in range(len(pieces)):
            for j in range(i + 1, len(pieces)):
                a, b = pieces[i][0], pieces[j][0]
                union = None
                if abs(a["z0"] - b["z0"]) < _EPS and abs(a["z1"] - b["z1"]) < _EPS and (
                    abs(a["x1"] - b["x0"]) < _EPS or abs(b["x1"] - a["x0"]) < _EPS
                ):
                    union = {"x0": min(a["x0"], b["x0"]), "x1": max(a["x1"], b["x1"]), "z0": a["z0"], "z1": a["z1"]}
                elif abs(a["x0"] - b["x0"]) < _EPS and abs(a["x1"] - b["x1"]) < _EPS and (
                    abs(a["z1"] - b["z0"]) < _EPS or abs(b["z1"] - a["z0"]) < _EPS
                ):
                    union = {"x0": a["x0"], "x1": a["x1"], "z0": min(a["z0"], b["z0"]), "z1": max(a["z1"], b["z1"])}
                if union:
                    area = (union["x1"] - union["x0"]) * (union["z1"] - union["z0"])
                    if best is None or area > best[0]:
                        best = (area, i, j, union)
        if best is None:
            return pieces
        _, i, j, union = best
        merged = (union, max(pieces[i][1], pieces[j][1]), pieces[i][2] + pieces[j][2])
        pieces = [p for k, p in enumerate(pieces) if k not in (i, j)] + [merged]


class _Mesh:
    """Triangles, both windings, with flat normals: the headset draws them as-is."""

    def __init__(self):
        self.positions: list[float] = []
        self.normals: list[float] = []

    def tri(self, a, b, c):
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        if length < 1e-9:
            return
        n = (nx / length, ny / length, nz / length)
        for p in (a, b, c):
            self.positions += [round(v, 4) for v in p]
            self.normals += [round(v, 4) for v in n]
        for p in (a, c, b):
            self.positions += [round(v, 4) for v in p]
            self.normals += [round(-v, 4) for v in n]

    def quad(self, a, b, c, d):
        self.tri(a, b, c)
        self.tri(a, c, d)

    def out(self, color: str) -> dict | None:
        if not self.positions:
            return None
        return {
            "positions": self.positions,
            "normals": self.normals,
            "indices": list(range(len(self.positions) // 3)),
            "color": _rgb(color),
        }


def _roof_section(rect: dict, height: float, roof: dict, roof_mesh: _Mesh, gable_mesh: _Mesh, parts: list):
    """Add one roof over ``rect`` (walls ``height`` tall) to the meshes."""
    style = roof["style"]
    slope = roof["pitch"] / 12.0
    e = WALL_T + roof["overhang"] * FT_TO_M  # eave distance past the room's edge
    x0, x1, z0, z1 = rect["x0"] - e, rect["x1"] + e, rect["z0"] - e, rect["z1"] + e

    if style == "flat":
        t = 0.2
        parts.append(_box(
            ((x0 + x1) / 2, height + t / 2, (z0 + z1) / 2), (x1 - x0, t, z1 - z0),
            roof["color"], kind="roof",
        ))
        return

    # Work in (along, across) with the ridge along the longer side.
    along_x = (x1 - x0) >= (z1 - z0)

    def P(a: float, c: float, y: float):
        return (a, y, c) if along_x else (c, y, a)

    a0, a1, c0, c1 = (x0, x1, z0, z1) if along_x else (z0, z1, x0, x1)
    wa0, wa1 = (rect["x0"] - WALL_T, rect["x1"] + WALL_T) if along_x else (rect["z0"] - WALL_T, rect["z1"] + WALL_T)
    wc0, wc1 = (rect["z0"] - WALL_T, rect["z1"] + WALL_T) if along_x else (rect["x0"] - WALL_T, rect["x1"] + WALL_T)
    # The roof planes rest on the walls' outer faces at ``height``.
    eave = height - (e - WALL_T) * slope

    if style == "shed":
        # One plane rising from the front (c0) to the back (c1).
        def y_at(c: float) -> float:
            return height + (c - wc0) * slope

        roof_mesh.quad(P(a0, c0, y_at(c0)), P(a1, c0, y_at(c0)), P(a1, c1, y_at(c1)), P(a0, c1, y_at(c1)))
        top = y_at(wc1)
        for a in (wa0, wa1):  # side triangles
            gable_mesh.tri(P(a, wc0, height), P(a, wc1, height), P(a, wc1, top))
        gable_mesh.quad(P(wa0, wc1, height), P(wa1, wc1, height), P(wa1, wc1, top), P(wa0, wc1, top))
        return

    cm = (c0 + c1) / 2
    ridge = eave + (cm - c0) * slope
    if style == "hip":
        half = (c1 - c0) / 2
        r0, r1 = a0 + half, a1 - half
        if r1 < r0:
            r0 = r1 = (a0 + a1) / 2
        roof_mesh.quad(P(a0, c0, eave), P(a1, c0, eave), P(r1, cm, ridge), P(r0, cm, ridge))
        roof_mesh.quad(P(a1, c1, eave), P(a0, c1, eave), P(r0, cm, ridge), P(r1, cm, ridge))
        roof_mesh.tri(P(a0, c1, eave), P(a0, c0, eave), P(r0, cm, ridge))
        roof_mesh.tri(P(a1, c0, eave), P(a1, c1, eave), P(r1, cm, ridge))
        return

    # Gable: two planes meeting at the ridge, closed by triangles above the end walls.
    roof_mesh.quad(P(a0, c0, eave), P(a1, c0, eave), P(a1, cm, ridge), P(a0, cm, ridge))
    roof_mesh.quad(P(a1, c1, eave), P(a0, c1, eave), P(a0, cm, ridge), P(a1, cm, ridge))
    apex = height + (cm - wc0) * slope
    for a in (wa0, wa1):
        gable_mesh.tri(P(a, wc0, height), P(a, wc1, height), P(a, cm, apex))


def _bay_roof(info: dict, height: float, roof: dict, mesh: _Mesh):
    """A small lean-to over a bay window, sloping down and out from the house wall."""
    outline = info.get("outline") or []
    if len(outline) < 4:
        return
    a, b = outline[0], outline[-1]  # where the bay meets the house wall
    ux, uz = b["x"] - a["x"], b["z"] - a["z"]
    length = math.hypot(ux, uz)
    if length < _EPS:
        return
    ux, uz = ux / length, uz / length
    # Outward: toward the bay's far corners.
    far = outline[1]
    nx, nz = -uz, ux
    if (far["x"] - a["x"]) * nx + (far["z"] - a["z"]) * nz < 0:
        nx, nz = -nx, -nz
    depth = max((p["x"] - a["x"]) * nx + (p["z"] - a["z"]) * nz for p in outline)
    e = WALL_T + 0.15
    rise = (depth + e) * min(roof["pitch"] / 12.0, 0.5)
    top = height + rise
    s0 = -e
    s1 = length + e

    def at(s: float, d: float, y: float):
        return (a["x"] + ux * s + nx * d, y, a["z"] + uz * s + nz * d)

    mesh.quad(at(s0, 0, top), at(s1, 0, top), at(s1, depth + e, height), at(s0, depth + e, height))


# Walls -----------------------------------------------------------------------------

_OUTWARD = ((0, -1), (1, 0), (0, 1), (-1, 0))  # front, east, back, west (as _room_sides)


def _skin_box(x0: float, z0: float, x1: float, z1: float, y0: float, y1: float, color: str) -> dict:
    """A thin box along the segment (x0, z0) → (x1, z1), from ``y0`` to ``y1``."""
    length = math.hypot(x1 - x0, z1 - z0)
    yaw = math.degrees(math.atan2(z1 - z0, x1 - x0))
    return _box(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (length, y1 - y0, SKIN_T), color, yaw, kind="wall")


def wall_skins(rect: dict, height: float, openings: list[dict], shared: dict, color: str) -> list[dict]:
    """Colored finish on the outer face of a room's exterior walls, with the same
    door and window holes as the walls themselves."""
    out = []
    off = WALL_T + SKIN_T / 2
    for index, side in enumerate(_room_sides(rect)):
        axis, line, s_lo, s_hi = side
        dx, dz = _OUTWARD[index]
        for lo, hi in exterior_intervals(side, shared):
            # Run past the corners so neighbouring faces close up.
            ext = WALL_T + SKIN_T
            if abs(lo - s_lo) < _EPS:
                lo -= ext
            if abs(hi - s_hi) < _EPS:
                hi += ext

            def piece(a: float, b: float, y0: float, y1: float):
                if b - a <= _EPS or y1 - y0 <= _EPS:
                    return
                if axis == "x":
                    z = line + dz * off
                    out.append(_skin_box(a, z, b, z, y0, y1, color))
                else:
                    x = line + dx * off
                    out.append(_skin_box(x, a, x, b, y0, y1, color))

            cursor = lo
            for o in sorted(_opening_on(side, openings), key=lambda o: o["lo"]):
                o_lo, o_hi = max(o["lo"], lo), min(o["hi"], hi)
                if o_hi <= o_lo:
                    continue
                piece(cursor, o_lo, 0.0, height)
                piece(o_lo, o_hi, 0.0, min(o["bottom"], height))
                piece(o_lo, o_hi, max(o["top"], 0.0), height)
                cursor = max(cursor, o_hi)
            piece(cursor, hi, 0.0, height)
    return out


def bay_skins(walls: list[dict], rect: dict, color: str) -> list[dict]:
    """Finish on the outside of a bay window's walls (pieces of any angle)."""
    cx, cz = (rect["x0"] + rect["x1"]) / 2, (rect["z0"] + rect["z1"]) / 2
    out = []
    for w in walls:
        s, t = w["start"], w["end"]
        length = math.hypot(t["x"] - s["x"], t["z"] - s["z"])
        if length < _EPS:
            continue
        ux, uz = (t["x"] - s["x"]) / length, (t["z"] - s["z"]) / length
        nx, nz = -uz, ux
        mx, mz = (s["x"] + t["x"]) / 2, (s["z"] + t["z"]) / 2
        if (mx - cx) * nx + (mz - cz) * nz < 0:
            nx, nz = -nx, -nz
        off = WALL_T + SKIN_T / 2
        y0 = s["y"]
        out.append(_skin_box(
            s["x"] + nx * off, s["z"] + nz * off, t["x"] + nx * off, t["z"] + nz * off,
            y0, y0 + w["height"], color,
        ))
    return out


# Landscaping -------------------------------------------------------------------------

def _m(feet: float) -> float:
    return feet * FT_TO_M


def _surface_rect(item: dict) -> tuple[float, float, float, float, float]:
    """``(cx, cz, length, width, yaw)`` of a surface, metres; lines get their width."""
    if "from" in item:
        a, b = item["from"], item["to"]
        length = _m(math.hypot(b["x"] - a["x"], b["z"] - a["z"]))
        width = _m(item.get("width", 4.0))
        yaw = math.degrees(math.atan2(b["z"] - a["z"], b["x"] - a["x"]))
        return _m((a["x"] + b["x"]) / 2), _m((a["z"] + b["z"]) / 2), length, width, yaw
    return _m(item["x"]), _m(item["z"]), _m(item.get("width", 10.0)), _m(item.get("depth", 10.0)), 0.0


def _local(cx: float, cz: float, yaw: float, u: float, v: float) -> tuple[float, float]:
    """Point ``u`` along and ``v`` across a shape centred at (cx, cz) turned by ``yaw``."""
    r = math.radians(yaw)
    return cx + u * math.cos(r) - v * math.sin(r), cz + u * math.sin(r) + v * math.cos(r)


def _surface_parts(item: dict) -> list[dict]:
    kind = item["type"]
    material = item.get("material") or _SURFACE_MATERIAL[kind]
    color = item.get("color") or SURFACE_MATERIALS[material]
    cx, cz, length, width, yaw = _surface_rect(item)
    if length < 0.1 or width < 0.1:
        return []
    base_y = GROUND_TOP
    parts: list[dict] = []
    if kind == "lawn":
        return [_box((cx, base_y + 0.005, cz), (length, 0.01, width), color, yaw, walkable=True)]
    if kind == "pool":
        coping = 0.3
        parts.append(_box((cx, base_y + 0.02, cz), (length, 0.04, width), color, yaw))
        stone = SURFACE_MATERIALS["stone"]
        for u, v, lx, wz in (
            (0, -(width + coping) / 2, length + 2 * coping, coping),
            (0, (width + coping) / 2, length + 2 * coping, coping),
            (-(length + coping) / 2, 0, coping, width),
            ((length + coping) / 2, 0, coping, width),
        ):
            px, pz = _local(cx, cz, yaw, u, v)
            parts.append(_box((px, base_y + 0.03, pz), (lx, 0.06, wz), stone, yaw, walkable=True))
        return parts
    if kind == "flower_bed":
        h = 0.15
        # The soil; the flowers are planted over it by build_exterior (vr_plants).
        return [_box((cx, base_y + h / 2, cz), (length, h, width), SURFACE_MATERIALS[material], yaw)]

    # Paths, driveways, patios and decks: a slab, laid as tiles for tiled materials.
    t = 0.04
    tile = TILE_SIZES.get(material)
    if tile is None:
        return [_box((cx, base_y + t / 2, cz), (length, t, width), color, yaw, walkable=True)]
    grout = _shade(color, 0.7)
    parts.append(_box((cx, base_y + t / 2, cz), (length, t, width), grout, yaw, walkable=True))
    while (length / tile) * (width / tile) > MAX_TILES:
        tile *= 1.25
    nu, nv = max(1, round(length / tile)), max(1, round(width / tile))
    tu, tv = length / nu, width / nv
    gap = min(0.02, tu * 0.1, tv * 0.1)
    for i in range(nu):
        for j in range(nv):
            u = -length / 2 + (i + 0.5) * tu
            v = -width / 2 + (j + 0.5) * tv
            px, pz = _local(cx, cz, yaw, u, v)
            shade = color if (i + j) % 2 == 0 else _shade(color, 0.92)
            parts.append(_box((px, base_y + t + 0.005, pz), (tu - gap, 0.01, tv - gap), shade, yaw))
    return parts


def _line_parts(item: dict) -> list[dict]:
    kind = item["type"]
    h_ft, w_ft, default_color = _LINE_DEFAULTS[kind]
    height, width = _m(item.get("height", h_ft)), _m(item.get("width", w_ft))
    color = item.get("color") or default_color
    a, b = item["from"], item["to"]
    ax, az, bx, bz = _m(a["x"]), _m(a["z"]), _m(b["x"]), _m(b["z"])
    length = math.hypot(bx - ax, bz - az)
    yaw = math.degrees(math.atan2(bz - az, bx - ax))
    cx, cz = (ax + bx) / 2, (az + bz) / 2
    y = GROUND_TOP
    if kind != "fence" or item.get("style") == "privacy":
        thickness = width if kind != "fence" else 0.05
        return [_box((cx, y + height / 2, cz), (length, height, thickness), color, yaw)]
    # Posts every 2.4 m with two rails.
    parts = []
    posts = max(1, math.ceil(length / 2.4))
    for k in range(posts + 1):
        u = -length / 2 + k * length / posts
        px, pz = _local(cx, cz, yaw, u, 0)
        parts.append(_box((px, y + height / 2, pz), (0.09, height, 0.09), color, yaw))
    for frac in (0.3, 0.8):
        parts.append(_box((cx, y + height * frac, cz), (length, 0.07, 0.04), color, yaw))
    return parts


def _item_extent(item: dict) -> tuple[float, float, float, float]:
    """Plan bounds of an item in metres, for sizing the yard."""
    if "from" in item:
        xs = [_m(item["from"]["x"]), _m(item["to"]["x"])]
        zs = [_m(item["from"]["z"]), _m(item["to"]["z"])]
        pad = _m(item.get("width", 4.0)) / 2
    else:
        xs, zs = [_m(item["x"])], [_m(item["z"])]
        pad = _m(max(item.get("width", 10.0), item.get("depth", 10.0))) / 2
    return min(xs) - pad, max(xs) + pad, min(zs) - pad, max(zs) + pad


def _clear_of_house(x: float, z: float, radius: float, rects: list[dict]) -> tuple[float, float]:
    """Move a point (metres) the shortest way out of the house when it would sit
    in a room, so a plant ``radius`` wide clears the walls."""
    pad = WALL_T + radius
    boxes = [(r["x0"] - pad, r["x1"] + pad, r["z0"] - pad, r["z1"] + pad) for r in rects]

    def inside(px: float, pz: float) -> bool:
        return any(x0 < px < x1 and z0 < pz < z1 for x0, x1, z0, z1 in boxes)

    if not inside(x, z):
        return x, z
    xs = [x] + [v for b in boxes for v in b[:2]]
    zs = [z] + [v for b in boxes for v in b[2:]]
    # The nearest free point lies on the edges of the padded rooms: try every
    # combination of their edge lines with the point's own x / z.
    candidates = [(cx, cz) for cx in xs for cz in zs]
    free = [p for p in candidates if not inside(*p)]
    if not free:
        return x, z
    return min(free, key=lambda p: (p[0] - x) ** 2 + (p[1] - z) ** 2)


# Plant models made from photos ---------------------------------------------------------

def _plant_model(item: dict, plant_models: list[dict] | None) -> dict | None:
    """The photo model an item stands for: by ``model_id``, else by name ("coral
    roses" uses the model called "Coral rose")."""
    if not plant_models:
        return None
    if "model_id" in item:
        return next((m for m in plant_models if m["id"] == item["model_id"]), None)
    key = name_key(item.get("plant") or item.get("label"))
    if not key:
        return None
    return next((m for m in plant_models if name_key(m["name"]) == key), None)


def _model_placement(item: dict, model: dict, x: float, z: float) -> dict:
    """Where the headset puts a model: its files are normalised to stand 1 m tall
    on their origin, so the scale is the plant's height in metres."""
    aspect = model.get("aspect") or 1.0
    if item.get("height"):
        height = _m(item["height"])
    elif item.get("width"):
        height = _m(item["width"]) / aspect
    else:
        species = find_species(item.get("plant") or model["name"])
        height = _m(model.get("height_ft") or (SPECIES[species].height if species else _POINT_DEFAULTS[item["type"]][0]))
    yaw = (x * 37.0 + z * 53.0) % 360
    return {
        "model_id": model["id"],
        "name": model["name"],
        "url": model["url"],
        "position": {"x": round(x, 3), "y": GROUND_TOP, "z": round(z, 3)},
        "scale": round(height, 3),
        "yaw": round(yaw, 1),
        # For the dashboard's plan: how wide it is.
        "width": round(height * aspect, 3),
    }


# Everything --------------------------------------------------------------------------

def build_exterior(
    spec: dict | None,
    rects: list[dict],
    heights: list[float],
    open_rects: list[dict],
    openings: list[dict],
    shared: dict,
    bays: dict[int, dict],
    plant_models: list[dict] | None = None,
) -> dict | None:
    """Geometry for the outside of the house, metres (the headset scales it).

    ``rects``/``heights`` are the rooms as built, ``openings`` every door, window
    and bay cut in the walls, ``bays`` the built bay windows by room index,
    ``plant_models`` the finished photo models (``plant_model_service.ready_models``).
    Returns ``{"roof": [meshes], "parts": [boxes], "plant_meshes", "plants",
    "models", "trim_color", ...}`` or None when the plan has no exterior.
    """
    if not spec or not rects:
        return None
    parts: list[dict] = []
    roof_meshes: list[dict] = []
    walls = spec.get("walls")
    wall_color = walls["color"] if walls else "#f2f2f2"

    roof = spec.get("roof")
    sections = roof_sections(rects, heights) if roof else []
    # With a roof, each room's outside finish runs up to its section's eave.
    finish_heights = list(heights)
    for _, eave, members in sections:
        for idx in members:
            finish_heights[idx] = eave

    if walls:
        for idx, (rect, height) in enumerate(zip(rects, finish_heights)):
            parts += wall_skins(rect, height, openings, shared, wall_color)
            bay = bays.get(idx)
            if bay:
                parts += bay_skins(bay["walls"], rect, wall_color)

    if roof:
        roof_mesh, gable_mesh = _Mesh(), _Mesh()
        for rect, eave, _ in sections:
            _roof_section(rect, eave, roof, roof_mesh, gable_mesh, parts)
        for idx, bay in bays.items():
            _bay_roof(bay["info"], heights[idx], roof, roof_mesh)
        roof_meshes = [m for m in (roof_mesh.out(roof["color"]), gable_mesh.out(wall_color)) if m]
        logger.info(f"  🏠 {roof['style']} {roof['material']} roof over {len(sections)} section(s)")

    # The yard: ground under and around the house, a foundation under each room,
    # then whatever was planted or paved.
    xs0 = [r["x0"] for r in rects + open_rects]
    xs1 = [r["x1"] for r in rects + open_rects]
    zs0 = [r["z0"] for r in rects + open_rects]
    zs1 = [r["z1"] for r in rects + open_rects]
    x0, x1 = min(xs0) - YARD_SIDE, max(xs1) + YARD_SIDE
    z0, z1 = min(zs0) - YARD_FRONT, max(zs1) + YARD_BACK
    items = spec.get("landscape") or []
    for item in items:
        ix0, ix1, iz0, iz1 = _item_extent(item)
        x0, x1 = min(x0, ix0 - 1.5), max(x1, ix1 + 1.5)
        z0, z1 = min(z0, iz0 - 1.5), max(z1, iz1 + 1.5)
    ground = spec.get("ground") or {"material": "grass", "color": GROUND_MATERIALS["grass"]}
    ground_t = 0.05
    parts.append(_box(
        ((x0 + x1) / 2, GROUND_TOP - ground_t / 2, (z0 + z1) / 2), (x1 - x0, ground_t, z1 - z0),
        ground["color"], walkable=True, kind="ground",
    ))
    found_top = -0.026  # just under the floors (0.05 world units thick, centred on 0; 1 unit = 1 m)
    for rect in rects:
        parts.append(_box(
            ((rect["x0"] + rect["x1"]) / 2, (GROUND_TOP + found_top) / 2, (rect["z0"] + rect["z1"]) / 2),
            (rect["x1"] - rect["x0"] + 2 * WALL_T, found_top - GROUND_TOP, rect["z1"] - rect["z0"] + 2 * WALL_T),
            FOUNDATION_COLOR, kind="ground",
        ))
    for idx, bay in bays.items():
        b = bay["bounds"]
        parts.append(_box(
            ((b["x0"] + b["x1"]) / 2, (GROUND_TOP + found_top) / 2, (b["z0"] + b["z1"]) / 2),
            (b["x1"] - b["x0"], found_top - GROUND_TOP, b["z1"] - b["z0"]),
            FOUNDATION_COLOR, kind="ground",
        ))

    # Plants never stand inside the house (or a bay window's bump-out).
    obstacles = rects + [bay["bounds"] for bay in bays.values()]
    yard = Yard(NAMED_COLORS)
    models: list[dict] = []
    counts: dict[str, int] = {}
    for item in items:
        kind = item["type"]
        if kind in POINT_TYPES:
            w = _m(item.get("width", _POINT_DEFAULTS[kind][1]))
            x, z = _clear_of_house(_m(item["x"]), _m(item["z"]), max(0.3, w * 0.3), obstacles)
            model = _plant_model(item, plant_models)
            if model:
                models.append(_model_placement(item, model, x, z))
            else:
                height = _m(item["height"]) if item.get("height") else None
                width = _m(item["width"]) if item.get("width") else None
                yard.add_plant(item, x, GROUND_TOP, z, height, width)
        elif kind in LINE_TYPES:
            if kind != "hedge":
                parts += _line_parts(item)
            else:
                h_ft, w_ft, default_color = _LINE_DEFAULTS["hedge"]
                a, b = item["from"], item["to"]
                yard.add_hedge(
                    item, (_m(a["x"]), _m(a["z"])), (_m(b["x"]), _m(b["z"])), GROUND_TOP,
                    _m(item.get("height", h_ft)), _m(item.get("width", w_ft)), item.get("color") or default_color,
                )
        else:
            parts += _surface_parts(item)
            if kind == "flower_bed":
                cx, cz, length, width, yaw = _surface_rect(item)
                if length >= 0.1 and width >= 0.1:
                    yard.add_bed(item, cx, cz, length, width, yaw, GROUND_TOP + 0.15)
        counts[kind] = counts.get(kind, 0) + 1
    if counts:
        logger.info(
            f"  🌳 Landscaping: {', '.join(f'{n} {k}' for k, n in sorted(counts.items()))}"
            f" ({len(yard.meshes)} plant meshes, {yard.triangles} triangles"
            + (f", {len(models)} photo models" if models else "") + ")"
        )

    trim = spec.get("trim")
    return {
        "roof": roof_meshes,
        "parts": parts,
        **yard.out(),
        "models": models,
        "trim_color": _rgb(trim["color"]) if trim else None,
        "ground_bounds": {"x0": round(x0, 3), "x1": round(x1, 3), "z0": round(z0, 3), "z1": round(z1, 3)},
        # The description in feet, for the dashboard to draw and list.
        "spec": spec,
    }
