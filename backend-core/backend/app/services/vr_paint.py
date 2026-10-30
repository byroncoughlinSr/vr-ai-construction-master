"""Paint, metres: a room's ``wall_color`` (and an ``accent_wall``, a ``ceiling_color``)
drawn as a thin surface on the room's own side of each of its walls and under its
ceiling.

Every room has its own wall pieces, so a wall between two rooms is drawn twice in
the same place; paint goes just in front of the face toward the room it belongs to,
so a sage bedroom beside a white hall shows sage on one side and white on the other.
The walls themselves stay drywall white: an unpainted room needs nothing.

The result is ``{"meshes", "pieces"}`` like the floor finishes (``vr_floors``): one
mesh per painted room, in world coordinates about its piece's position.

Room fields (feet plan, as the AI and the dashboard send them):
- ``wall_color``: "sage green", "#a7b59a", ...
- ``accent_wall``: ``{"side": front|back|left|right, "color": ...}`` (front is the street side)
- ``ceiling_color``
"""

from __future__ import annotations

import re
from typing import Any

from .vr_exterior import NAMED_COLORS, color_hex
from .vr_plants import PlantMesh

SIDES = ("front", "back", "left", "right")
FIELDS = ("wall_color", "accent_wall", "ceiling_color")
OFFSET = 0.004  # in front of the wall face / under the ceiling slab, metres
SLAB_HALF = 0.025  # half the ceiling slab's thickness (HouseGenerator.generateCeiling)
_EPS = 1e-3

# Interior paint names, before the general colours (whose "green" is a siding green).
PAINT_COLORS = {
    "white": "#f4f4f0", "off white": "#eeebe2", "bright white": "#f7f7f4", "warm white": "#f3eee2", "eggshell": "#efe9d9",
    "linen": "#ece4d4", "cream": "#efe6cf", "ivory": "#f2ecd8", "greige": "#c9bfb1",
    "sage": "#a7b59a", "sage green": "#a7b59a", "mint": "#c8e3cf", "mint green": "#c8e3cf",
    "seafoam": "#b9dccd", "emerald": "#2f7a52", "hunter green": "#355e3b", "olive green": "#7a7a4a",
    "sky blue": "#a9cbe3", "powder blue": "#c3d7e8", "baby blue": "#bcd6ea", "navy blue": "#24344d",
    "pale yellow": "#f3e7a9", "butter yellow": "#f2df9c", "blush": "#e8c4c0", "blush pink": "#e8c4c0",
    "coral": "#e8836b", "peach": "#f2c3a0", "lilac": "#c8b5d9", "mauve": "#b48a9b",
    "terracotta": "#c0623a", "charcoal": "#3b3d40",
}
_LIGHT = ("light", "pale", "soft", "pastel")
_DARK = ("dark", "deep")


def _mix(hex_color: str, toward: str, t: float) -> str:
    a, b = hex_color.lstrip("#"), toward.lstrip("#")
    parts = [round(int(a[i:i + 2], 16) * (1 - t) + int(b[i:i + 2], 16) * t) for i in (0, 2, 4)]
    return "#" + "".join(f"{p:02x}" for p in parts)


def paint_color(value: Any) -> str | None:
    """``#rrggbb`` for a paint colour in words or hex, or None when it names none.
    "light"/"pale" and "dark"/"deep" lighten or darken a colour that has no own entry."""
    text = " ".join(re.findall(r"[a-z0-9#]+", str(value or "").lower()))
    if not text:
        return None
    for name in sorted(PAINT_COLORS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", text):
            return PAINT_COLORS[name]
    exact = color_hex(text, "")
    if not exact:
        return None
    words = set(text.split())
    if text in NAMED_COLORS or text.startswith("#"):
        return exact
    if words & set(_LIGHT):
        return _mix(exact, "#ffffff", 0.45)
    if words & set(_DARK):
        return _mix(exact, "#000000", 0.35)
    return exact


def clean_paint(room: dict) -> dict:
    """``room`` with its paint fields as stored: colours as hex, an accent wall only
    with a side and a colour; unusable ones dropped."""
    out = {k: v for k, v in room.items() if k not in FIELDS}
    for key in ("wall_color", "ceiling_color"):
        color = paint_color(room.get(key))
        if color:
            out[key] = color
    accent = room.get("accent_wall")
    if isinstance(accent, dict):
        side = str(accent.get("side") or "").strip().lower()
        side = {"rear": "back", "street": "front"}.get(side, side)
        color = paint_color(accent.get("color"))
        if side in SIDES and color:
            out["accent_wall"] = {"side": side, "color": color}
    return out


def apply_paint(rooms: list, change: Any) -> tuple[list, list[str]]:
    """``rooms`` with ``change`` (``{"Room name": {wall_color, accent_wall, ceiling_color}}``)
    painted on, and the names of the rooms it changed. A field given as null, "" or
    "none" takes that paint off; fields left out stay as they are."""
    if not isinstance(change, dict):
        return list(rooms or []), []
    wanted = {" ".join(str(k).lower().split()): v for k, v in change.items() if isinstance(v, dict)}
    out, changed = [], []
    for room in rooms or []:
        fields = wanted.get(" ".join(str(room.get("name", "")).lower().split())) if isinstance(room, dict) else None
        if fields is None:
            out.append(room)
            continue
        new = dict(room)
        for key in FIELDS:
            if key not in fields:
                continue
            value = fields[key]
            if value is None or str(value).strip().lower() in ("", "none", "null", "remove"):
                new.pop(key, None)
            else:
                new[key] = value
        new = clean_paint(new)
        out.append(new)
        if any(new.get(k) != room.get(k) for k in FIELDS):
            changed.append(str(room["name"]))
    return out, changed


def room_paint(room: dict) -> dict | None:
    """``{"walls", "accent": {side, color} | None, "ceiling"}`` for a room, or None when
    nothing is painted."""
    clean = clean_paint(room)
    paint = {"walls": clean.get("wall_color"), "accent": clean.get("accent_wall"), "ceiling": clean.get("ceiling_color")}
    return paint if any(paint.values()) else None


def _side_of(wall: dict, b: dict) -> str | None:
    """The side of the room's rectangle ``b`` a wall piece runs along, if any."""
    s, e = wall["start"], wall["end"]
    if abs(s["z"] - e["z"]) < _EPS:
        for side, line in (("front", b["z0"]), ("back", b["z1"])):
            if abs(s["z"] - line) < _EPS:
                return side
    elif abs(s["x"] - e["x"]) < _EPS:
        for side, line in (("left", b["x0"]), ("right", b["x1"])):
            if abs(s["x"] - line) < _EPS:
                return side
    return None


def _wall_quad(m: PlantMesh, color: str, wall: dict, b: dict, side: str | None, wt: float, c: tuple[float, float]):
    s, e = wall["start"], wall["end"]
    ax, az, bx, bz = s["x"], s["z"], e["x"], e["z"]
    if side in ("front", "back"):  # inside the corners the side walls fill
        lo, hi = max(min(ax, bx), b["x0"] + wt), min(max(ax, bx), b["x1"] - wt)
        ax, bx = lo, hi
    elif side in ("left", "right"):
        lo, hi = max(min(az, bz), b["z0"] + wt), min(max(az, bz), b["z1"] - wt)
        az, bz = lo, hi
    length = ((bx - ax) ** 2 + (bz - az) ** 2) ** 0.5
    if length < 0.01:
        return
    nx, nz = -(bz - az) / length, (bx - ax) / length
    if nx * (c[0] - (ax + bx) / 2) + nz * (c[1] - (az + bz) / 2) < 0:
        nx, nz = -nx, -nz  # toward the room
    d = wt + OFFSET
    y0, y1 = s["y"], s["y"] + wall["height"]
    ox, oz = nx * d - c[0], nz * d - c[1]
    m.quad(color, (ax + ox, y0, az + oz), (bx + ox, y0, bz + oz), (bx + ox, y1, bz + oz), (ax + ox, y1, az + oz))


def build_paint(rooms: list[dict], specs: list[dict], wall_t: float) -> dict | None:
    """Paint for the built ``rooms`` (``id``, ``name``, ``bounds``, ``walls``,
    ``ceilings``) from the plan's rooms ``specs`` (matched by name). Each built room
    gets its ``paint`` (or null) for the dashboard."""
    by_name = {" ".join(str(r.get("name", "")).lower().split()): r for r in specs if isinstance(r, dict)}
    meshes: dict[str, dict] = {}
    pieces: list[dict] = []
    for room in rooms:
        paint = room_paint(by_name.get(" ".join(str(room["name"]).lower().split()), {}))
        room["paint"] = paint
        if not paint:
            continue
        b = room["bounds"]
        c = ((b["x0"] + b["x1"]) / 2, (b["z0"] + b["z1"]) / 2)
        m = PlantMesh()
        accent = paint["accent"]
        for wall in room["walls"]:
            side = _side_of(wall, b)
            color = accent["color"] if accent and side == accent["side"] else paint["walls"]
            if color:
                _wall_quad(m, color, wall, b, side, wall_t, c)
        if paint["ceiling"]:
            for slab in room.get("ceilings") or []:
                v = slab["vertices"]
                x0, x1 = max(min(v[0]["x"], v[2]["x"]), b["x0"] + wall_t), min(max(v[0]["x"], v[2]["x"]), b["x1"] - wall_t)
                z0, z1 = max(min(v[0]["z"], v[2]["z"]), b["z0"] + wall_t), min(max(v[0]["z"], v[2]["z"]), b["z1"] - wall_t)
                if x1 - x0 > 0.01 and z1 - z0 > 0.01:
                    y = v[0]["y"] - SLAB_HALF - OFFSET
                    m.quad(paint["ceiling"], (x0 - c[0], y, z0 - c[1]), (x1 - c[0], y, z0 - c[1]),
                           (x1 - c[0], y, z1 - c[1]), (x0 - c[0], y, z1 - c[1]))
        if not m.groups:
            continue
        key = f"paint-{room['id']}"
        meshes[key] = m.out()
        pieces.append({
            "room": room["id"], "type": "paint",
            "position": {"x": round(c[0], 4), "y": 0.0, "z": round(c[1], 4)},
            "yaw": 0.0, "mesh": key, "scale": {"x": 1, "y": 1, "z": 1},
        })
    return {"meshes": meshes, "pieces": pieces} if pieces else None
