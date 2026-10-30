"""Shared VR geometry builder used by both project-backed and prompt-backed
VR endpoints.

Used by ``POST /planning/generate-vr-from-prompt`` (headset voice flow) and
``GET /projects/{id}/generate-vr`` (dashboard / load-to-VR), so both produce the
same geometry JSON for ``HouseGenerator.kt``.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


WALL_T = 0.1  # Half wall thickness — matches Box(..., 0.1f) in HouseGenerator.kt
FT_TO_M = 0.3048  # AI returns dimensions in feet; VR world uses metres (1 unit = 1 m)


def _feet(value: Any, default: float) -> float:
    """A positive size in feet from LLM output, which may be null, a string or nonsense."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def ft_to_m_dims(dims: dict) -> dict:
    """Convert a dimensions dict from feet to metres."""
    return {
        "length": round(_feet(dims.get("length"), 15.0) * FT_TO_M, 3),
        "width": round(_feet(dims.get("width"), 12.0) * FT_TO_M, 3),
        "height": round(_feet(dims.get("height"), 9.0) * FT_TO_M, 3),
    }


def compute_packed_positions(rooms: list, max_cols: int = 3) -> list:
    """
    Fallback layout, used only when the AI's nested-split ``layout`` is missing
    or invalid (see ``layout_rects_from_tree``); room 0 is then the entry.

    Compute (x_center, z_center, effective_width) for each room.
    Rooms pack edge-to-edge in X. All rooms in the same row share the
    row's max width so their north and south walls flush perfectly —
    no gaps at the boundaries between rooms of differing depths.
    """
    row_x_cursor: dict = {}
    row_max_width: dict = {}
    coords = []

    for idx, room in enumerate(rooms):
        row = idx // max_cols
        dims = room.get("dimensions") or {}
        length = _feet(dims.get("length"), 15.0)
        width = _feet(dims.get("width"), 12.0)

        if row not in row_x_cursor:
            row_x_cursor[row] = 0.0
            row_max_width[row] = 0.0

        x_center = row_x_cursor[row] + length / 2.0
        row_x_cursor[row] += length
        row_max_width[row] = max(row_max_width[row], width)
        coords.append((row, x_center))

    z_starts: dict = {}
    running_z = 0.0
    for row_idx in sorted(set(r for r, _ in coords)):
        z_starts[row_idx] = running_z
        running_z += row_max_width[row_idx]

    return [
        (x, z_starts[r] + row_max_width[r] / 2.0, row_max_width[r])
        for r, x in coords
    ]


# Smallest a room may be along a split, metres. Proportional scaling can otherwise
# squeeze a closet or hallway into a sliver when the AI's numbers don't add up.
# Just under 3 ft: a toilet room or a closet is 3 ft wide (1.2 m rejected them).
MIN_PART = 0.9


class LayoutError(ValueError):
    """The AI's layout tree is unusable; callers fall back to the grid layout."""


def _allocate(extent: float, sizes: list[float]) -> list[float]:
    """Divide ``extent`` in proportion to ``sizes``, giving every part at least MIN_PART."""
    if extent < MIN_PART * len(sizes):
        raise LayoutError(f"{len(sizes)} parts do not fit in {extent:.2f} m")
    fixed: dict[int, float] = {}
    while True:
        free = [i for i in range(len(sizes)) if i not in fixed]
        remaining = extent - sum(fixed.values())
        total = sum(sizes[i] for i in free)
        shares = {i: remaining * sizes[i] / total for i in free}
        small = [i for i, v in shares.items() if v < MIN_PART]
        if not small:
            fixed.update(shares)
            return [fixed[i] for i in range(len(sizes))]
        for i in small:
            fixed[i] = MIN_PART


def layout_rects_from_tree(layout: dict) -> list[tuple[str, dict]]:
    """Turn the AI's nested-split floor plan into room rectangles (metres).

    ``layout`` is ``{"length": ft, "width": ft, "split": "x"|"z", "parts": [...]}``.
    Each part has a relative ``size`` and is either a leaf ``{"room": name}``, an
    open leaf ``{"open": true}`` (outdoors: a yard or notch that gives the house an
    L/U/T shape) or another split. ``"x"`` lays parts left to right; ``"z"`` front
    to back, so the first part is on the street side (z = 0). Part sizes are
    rescaled to fill their parent exactly, so rooms and open areas together tile
    the footprint with no gaps or overlaps.

    Returns ``[(room_name, rect), ...]`` in reading order (open areas are left
    out; see ``layout_open_rects``). Raises LayoutError when the tree is malformed.

    NOTE: the planning prompt (`_build_planning_prompt` in ai_planning_service.py)
    describes this format to the AI. Change both together.
    """
    return _walk_layout(layout)[0]


def layout_open_rects(layout: dict) -> list[dict]:
    """Rectangles (metres) of the layout's open, outdoor parts."""
    return _walk_layout(layout)[1]


def _is_open(node: dict) -> bool:
    return node.get("open") is True and not node.get("room")


def _walk_layout(layout: dict) -> tuple[list[tuple[str, dict]], list[dict]]:
    if not isinstance(layout, dict):
        raise LayoutError("layout is not an object")
    if is_rect_layout(layout):
        return _rect_layout(layout)
    try:
        length = float(layout.get("length")) * FT_TO_M
        width = float(layout.get("width")) * FT_TO_M
    except (TypeError, ValueError):
        raise LayoutError("footprint length/width missing")
    if length <= 0 or width <= 0:
        raise LayoutError("footprint must be positive")

    out: list[tuple[str, dict]] = []
    open_out: list[dict] = []

    def walk(node: dict, rect: dict, depth: int):
        if depth > 8:
            raise LayoutError("layout nested too deeply")
        if not isinstance(node, dict):
            raise LayoutError("layout node is not an object")
        if depth > 0 and _is_open(node):
            open_out.append(rect)
            return
        name = node.get("room")
        if isinstance(name, str) and _clean_name(name):
            out.append((_clean_name(name), rect))
            return
        axis, parts = node.get("split"), node.get("parts")
        if axis not in ("x", "z") or not isinstance(parts, list) or not parts:
            raise LayoutError(f"node is neither a room nor a split: {str(node)[:80]}")
        sizes = []
        for part in parts:
            try:
                size = float(part.get("size", 1.0)) if isinstance(part, dict) else 0.0
            except (TypeError, ValueError):
                size = 0.0
            sizes.append(size if size > 0 else 1.0)
        lo_key, hi_key = ("x0", "x1") if axis == "x" else ("z0", "z1")
        cursor = rect[lo_key]
        for part, extent in zip(parts, _allocate(rect[hi_key] - rect[lo_key], sizes)):
            child = {**rect, lo_key: cursor, hi_key: cursor + extent}
            cursor += extent
            walk(part, child, depth + 1)

    walk(layout, {"x0": 0.0, "x1": length, "z0": 0.0, "z1": width}, 0)

    if not out:
        raise LayoutError("layout has no rooms")
    names = [_normalize(n) for n, _ in out]
    if len(set(names)) != len(names):
        raise LayoutError("a room appears more than once in the layout")
    return out, open_out


# Room edges closer than this (feet) are taken to be the same line: the AI writes
# 15.4 beside 15.5, which would otherwise leave a 3 cm slit and no shared wall.
RECT_SNAP_FT = 0.35


def is_rect_layout(layout: Any) -> bool:
    """A floor plan given as room rectangles, ``{"entry": name, "rects": [{"room",
    "x", "z", "length", "width"}, ...]}`` in feet (x left to right, z from the street),
    rather than as a nested-split tree.

    NOTE: the planning prompts (`RECT_LAYOUT_FORMAT` in ai_planning_service.py)
    describe this format to the AI. Change both together.
    """
    return isinstance(layout, dict) and isinstance(layout.get("rects"), list)


def _snap(values: list[float]) -> dict[float, float]:
    """Map each value to the first of a run of values each within RECT_SNAP_FT of the run's start."""
    out: dict[float, float] = {}
    anchor = None
    for v in sorted(set(values)):
        if anchor is None or v - anchor > RECT_SNAP_FT:
            anchor = v
        out[v] = anchor
    return out


def rect_entries(layout: dict) -> list[dict]:
    """The rooms of a rectangle layout in feet, ``[{"room", "x0", "x1", "z0", "z1"}]``:
    edges snapped together and shifted so the plan starts at x = 0 and z = 0 (the
    street). Raises LayoutError for entries that aren't rooms with a usable size."""
    raw = []
    for item in layout.get("rects") or []:
        if not isinstance(item, dict):
            raise LayoutError("a layout rectangle is not an object")
        name = _clean_name(item.get("room") or item.get("name"))
        if not name:
            raise LayoutError("a layout rectangle has no room name")
        try:
            x, z = float(item.get("x") or 0), float(item.get("z") or 0)
            length, width = float(item.get("length")), float(item.get("width"))
        except (TypeError, ValueError):
            raise LayoutError(f"{name}'s rectangle needs numbers for x, z, length and width")
        if length <= 0 or width <= 0:
            raise LayoutError(f"{name}'s rectangle must have a positive length and width")
        raw.append((name, x, x + length, z, z + width, rect_level(item)))
    if not raw:
        raise LayoutError("layout has no rooms")
    xs = _snap([v for _, x0, x1, _, _, _ in raw for v in (x0, x1)])
    zs = _snap([v for _, _, _, z0, z1, _ in raw for v in (z0, z1)])
    left, front = min(xs.values()), min(zs.values())
    origin = layout.get("origin")
    if isinstance(origin, (list, tuple)) and len(origin) == 2:
        left, front = origin  # one level of a house: the whole house's corner, so the levels line up
    out = []
    for name, x0, x1, z0, z1, level in raw:
        entry = {"room": name, "x0": xs[x0] - left, "x1": xs[x1] - left,
                 "z0": zs[z0] - front, "z1": zs[z1] - front}
        if level:
            entry["level"] = level
        if entry["x1"] - entry["x0"] < 1 or entry["z1"] - entry["z0"] < 1:
            raise LayoutError(f"{name}'s rectangle is under 1 ft across")
        out.append(entry)
    names = [_normalize(e["room"]) for e in out]
    if len(set(names)) != len(names):
        raise LayoutError("a room appears more than once in the layout")
    return out


MAX_LEVELS = 4


def rect_level(item: Any) -> int:
    """The level (storey) of a layout rectangle: 0 is the ground floor."""
    try:
        return min(MAX_LEVELS - 1, max(0, int(float((item or {}).get("level") or 0))))
    except (TypeError, ValueError, AttributeError):
        return 0


def layout_levels(layout: Any) -> dict[int, dict]:
    """A rectangle layout split into one layout per level (0, 1, ... with no gaps),
    each keeping the whole house's front-left corner as its ``origin`` so the levels
    stack. The ground floor keeps the ``entry`` and ``notes``. A layout with one level
    (or a tree) comes back as ``{0: layout}``."""
    if not is_rect_layout(layout):
        return {0: layout}
    items = [i for i in layout["rects"] if isinstance(i, dict)]
    found = sorted({rect_level(i) for i in items})
    if len(found) <= 1:
        return {0: layout}
    try:
        left = min(float(i.get("x") or 0) for i in items)
        front = min(float(i.get("z") or 0) for i in items)
    except (TypeError, ValueError):
        return {0: layout}
    out: dict[int, dict] = {}
    for n, level in enumerate(found):
        lay: dict[str, Any] = {"rects": [i for i in items if rect_level(i) == level], "origin": [left, front]}
        if n == 0:
            lay.update({k: layout[k] for k in ("entry", "notes") if k in layout})
        out[n] = lay
    return out


def subtract_rects(rect: dict, holes: list[dict]) -> list[dict]:
    """``rect`` less every rectangle in ``holes`` (same units), as rectangles."""
    pieces = [dict(rect)]
    for h in holes:
        out = []
        for p in pieces:
            if h["x1"] <= p["x0"] + _EPS or h["x0"] >= p["x1"] - _EPS or h["z1"] <= p["z0"] + _EPS or h["z0"] >= p["z1"] - _EPS:
                out.append(p)
                continue
            if h["z0"] > p["z0"] + _EPS:
                out.append({**p, "z1": h["z0"]})
            if h["z1"] < p["z1"] - _EPS:
                out.append({**p, "z0": h["z1"]})
            z0, z1 = max(p["z0"], h["z0"]), min(p["z1"], h["z1"])
            if h["x0"] > p["x0"] + _EPS:
                out.append({**p, "x1": h["x0"], "z0": z0, "z1": z1})
            if h["x1"] < p["x1"] - _EPS:
                out.append({**p, "x0": h["x1"], "z0": z0, "z1": z1})
        pieces = out
    return [p for p in pieces if p["x1"] - p["x0"] > 0.01 and p["z1"] - p["z0"] > 0.01]


def rect_overlaps(entries: list[dict]) -> list[tuple[str, str, float, float]]:
    """Rooms on the same level whose rectangles overlap: ``(room, room, overlap along x,
    along z)`` in feet."""
    out = []
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            if a.get("level", 0) != b.get("level", 0):
                continue
            dx = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
            dz = min(a["z1"], b["z1"]) - max(a["z0"], b["z0"])
            if dx > 0.05 and dz > 0.05:
                out.append((a["room"], b["room"], dx, dz))
    return out


def uncovered_rects(rects: list[dict]) -> list[dict]:
    """The parts of the rooms' bounding box no room covers, as rectangles (same units)."""
    if not rects:
        return []
    xs = sorted({v for r in rects for v in (r["x0"], r["x1"])})
    zs = sorted({v for r in rects for v in (r["z0"], r["z1"])})

    def covered(x: float, z: float) -> bool:
        return any(r["x0"] < x < r["x1"] and r["z0"] < z < r["z1"] for r in rects)

    merged: list[dict] = []
    for za, zb in zip(zs, zs[1:]):
        # Runs of uncovered cells along this band, then each run joined onto the
        # rectangle right in front of it when that has the same width.
        runs, run = [], None
        for xa, xb in zip(xs, xs[1:]):
            if covered((xa + xb) / 2, (za + zb) / 2):
                if run:
                    runs.append(run)
                run = None
            else:
                run = (run[0], xb) if run else (xa, xb)
        if run:
            runs.append(run)
        for xa, xb in runs:
            above = next((m for m in merged if m["x0"] == xa and m["x1"] == xb and m["z1"] == za), None)
            if above:
                above["z1"] = zb
            else:
                merged.append({"x0": xa, "x1": xb, "z0": za, "z1": zb})
    return merged


def _rect_layout(layout: dict) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Rooms and open areas (metres) of a rectangle layout: whatever of the bounding
    box no room covers is outdoors (an L/U shape, a courtyard, an inset porch)."""
    entries = rect_entries(layout)
    overlaps = rect_overlaps(entries)
    if overlaps:
        a, b, dx, dz = overlaps[0]
        raise LayoutError(f"{a} and {b} overlap by {dx:.1f} x {dz:.1f} ft")

    def metres(r: dict) -> dict:
        return {k: r[k] * FT_TO_M for k in ("x0", "x1", "z0", "z1")}

    placed = [(e["room"], metres(e)) for e in entries]
    return placed, [metres(r) for r in uncovered_rects([e for e in entries if not e.get("level")])]


def layout_as_rects(layout: dict) -> dict:
    """``layout`` as a rectangle layout in feet (a tree's rooms where it draws them),
    for prompts and editors that work on rectangles. Keeps ``entry`` and ``notes``.
    Raises LayoutError like ``layout_rects_from_tree``."""
    if is_rect_layout(layout):
        boxes = [(e["room"], e) for e in rect_entries(layout)]
    else:
        boxes = [(name, {k: v / FT_TO_M for k, v in r.items()}) for name, r in _walk_layout(layout)[0]]
    rects = []
    for name, r in boxes:
        # Round the edges, not the sizes, so neighbours still meet exactly.
        x0, x1, z0, z1 = (round(r[k], 1) for k in ("x0", "x1", "z0", "z1"))
        rects.append({"room": name, "x": x0, "z": z0, "length": round(x1 - x0, 1), "width": round(z1 - z0, 1),
                      **({"level": r["level"]} if r.get("level") else {})})
    out: dict[str, Any] = {"entry": layout.get("entry"), "rects": rects}
    if layout.get("notes"):
        out["notes"] = layout["notes"]
    return out


# Opening sizes, metres. A door or window is only placed where the wall leaves at
# least EDGE_MARGIN of solid wall on each side, so openings never eat into corners.
DOOR_W = round(3.0 * FT_TO_M, 3)
DOOR_H = round(6.67 * FT_TO_M, 3)
WINDOW_W = round(4.0 * FT_TO_M, 3)
SMALL_WINDOW_W = round(2.0 * FT_TO_M, 3)
WINDOW_H = round(4.0 * FT_TO_M, 3)
WINDOW_SILL = round(3.0 * FT_TO_M, 3)
EDGE_MARGIN = 0.25
# An interior doorway sits centred on the wall two rooms share and only needs a
# jamb's width beside it, so a door fits at the end of a 4-4.5 ft hallway.
DOOR_EDGE_MARGIN = 0.12
_EPS = 1e-3

# Bay windows: a walk-in bump-out of a room's outside wall, glazed on every face.
BAY_DEFAULT_W = round(8.0 * FT_TO_M, 3)
BAY_DEFAULT_D = round(2.5 * FT_TO_M, 3)
BAY_MIN_W = round(4.0 * FT_TO_M, 3)
BAY_MIN_D = round(1.0 * FT_TO_M, 3)
BAY_MAX_D = round(6.0 * FT_TO_M, 3)
BAY_SILL = round(1.5 * FT_TO_M, 3)
BAY_MIN_INSET = round(0.5 * FT_TO_M, 3)  # an angled side narrower than this becomes a box
BAY_GLASS_MARGIN = 0.12  # solid wall left at each end of a bay face
# Side → (index into _room_sides, outward direction (dx, dz)).
_BAY_SIDES = {"front": (0, (0, -1)), "right": (1, (1, 0)), "back": (2, (0, 1)), "left": (3, (-1, 0))}

# Rooms that get no window (interior circulation and storage).
_NO_WINDOW_KEYWORDS = ("hall", "corridor", "closet", "pantry", "stair")
_SMALL_WINDOW_KEYWORDS = ("bath", "laundry", "powder", "wc", "toilet")
# When a room has no requested door, connect it through one of these first.
_CIRCULATION_KEYWORDS = ("hall", "corridor", "foyer", "entry", "living", "family", "great")
# Rooms that always keep one wall free of openings, for counters and cabinets.
_CLEAN_WALL_KEYWORDS = ("kitchen",)
CLEAN_WALL_MIN = round(6.0 * FT_TO_M, 3)  # shorter walls don't count as room for counters


def _room_rect(x_center: float, z_center: float, length: float, width: float) -> dict:
    return {
        "x0": x_center - length / 2, "x1": x_center + length / 2,
        "z0": z_center - width / 2, "z1": z_center + width / 2,
    }


def find_shared_walls(rects: list[dict]) -> dict:
    """Map each pair of touching rooms ``(i, j)`` (``i < j``) to the wall they share.

    A shared wall is ``(axis, line, lo, hi)``: the wall runs along ``axis``
    (``"x"`` or ``"z"``) on the line ``x == line`` / ``z == line`` and the two
    rooms touch over ``lo..hi`` along that axis.
    """
    shared = {}
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            for ax, bx in ((a["x1"], b["x0"]), (a["x0"], b["x1"])):
                if abs(ax - bx) < _EPS:
                    lo, hi = max(a["z0"], b["z0"]), min(a["z1"], b["z1"])
                    if hi - lo > _EPS:
                        shared[(i, j)] = ("z", ax, lo, hi)
            for az, bz in ((a["z1"], b["z0"]), (a["z0"], b["z1"])):
                if abs(az - bz) < _EPS:
                    lo, hi = max(a["x0"], b["x0"]), min(a["x1"], b["x1"])
                    if hi - lo > _EPS:
                        shared[(i, j)] = ("x", az, lo, hi)
    return shared


def _fits(lo: float, hi: float, opening_w: float, margin: float = EDGE_MARGIN) -> bool:
    return hi - lo >= opening_w + 2 * margin


def _normalize(name: str) -> str:
    return " ".join(str(name).lower().split())


def _resolve_room(name: str, names: list[str]) -> int | None:
    """Match a ``connects_to`` entry to a room index: exact name, else a unique partial match."""
    target = _normalize(name)
    if not target:
        return None
    for idx, n in enumerate(names):
        if n == target:
            return idx
    partial = [idx for idx, n in enumerate(names) if target in n or n in target]
    return partial[0] if len(partial) == 1 else None


def _name_list(value: Any) -> list:
    return [value] if isinstance(value, str) else list(value or []) if isinstance(value, list) else []


def plan_open_walls(
    rooms: list[dict], rects: list[dict], shared: dict, notes: list[str],
) -> list[tuple[int, int]]:
    """Pairs of rooms whose shared wall is taken out altogether: a room's
    ``open_to`` names rooms it is open to (an open kitchen and dining room).
    Rooms that don't touch, or a wall either room keeps solid, are reported in ``notes``."""
    names = [_normalize(r.get("name", "")) for r in rooms]
    pairs: list[tuple[int, int]] = []
    for i, room in enumerate(rooms):
        for target in _name_list(room.get("open_to")):
            j = _resolve_room(target, names)
            if j is None or j == i:
                logger.info(f"  ↪ '{room.get('name')}' open_to '{target}': no such room")
                continue
            pair = (min(i, j), max(i, j))
            if pair in pairs:
                continue
            a, b = rooms[pair[0]].get("name"), rooms[pair[1]].get("name")
            wall = shared.get(pair)
            if wall is None:
                notes.append(f"{a} and {b} don't share a wall, so it could not be opened up")
                continue
            if any(_side_name(rects[k], wall[0], wall[1]) in _side_set(rooms[k].get("solid_walls")) for k in pair):
                notes.append(f"The wall between {a} and {b} is kept solid, so it was not opened up")
                continue
            pairs.append(pair)
    return pairs


def plan_connections(
    rooms: list[dict], shared: dict, notes: list[str] | None = None,
    rects: list[dict] | None = None, open_pairs: list[tuple[int, int]] = (),
) -> list[tuple[int, int]]:
    """Decide which pairs of rooms get a doorway.

    Honours each room's ``connects_to`` where the two rooms actually share
    enough wall for a door, then adds doors until every room is reachable from
    the entry (room 0), preferring to connect through circulation spaces.
    A room's ``no_door_to`` names rooms it must not get a doorway to: a pair
    listed there is never requested and only added for reachability as a last
    resort, so "remove the door between X and Y" sticks even when that door
    was one added here. Such a last-resort door is reported in ``notes``. A wall
    either room keeps solid (``solid_walls``, needs ``rects``) blocks the pair the
    same way. ``open_pairs`` (``plan_open_walls``) are already joined: they get
    no door and count towards reachability.
    """
    names = [_normalize(r.get("name", "")) for r in rooms]
    pairs: list[tuple[int, int]] = []
    open_pairs = list(open_pairs)

    blocked: set[tuple[int, int]] = set()
    for i, room in enumerate(rooms):
        for target in _name_list(room.get("no_door_to")):
            j = _resolve_room(target, names)
            if j is not None and j != i:
                blocked.add((min(i, j), max(i, j)))
    if rects is not None:
        for pair, (axis, line, _, _) in shared.items():
            if any(_side_name(rects[k], axis, line) in _side_set(rooms[k].get("solid_walls")) for k in pair):
                blocked.add(pair)

    for i, room in enumerate(rooms):
        for target in _name_list(room.get("connects_to")):
            j = _resolve_room(target, names)
            if j is None or j == i:
                logger.info(f"  ↪ '{room.get('name')}' connects_to '{target}': no such room")
                continue
            pair = (min(i, j), max(i, j))
            if pair in pairs or pair in open_pairs:
                continue
            if pair in blocked:
                logger.info(
                    f"  ↪ '{rooms[pair[0]].get('name')}' ↔ '{rooms[pair[1]].get('name')}' "
                    f"requested but marked no_door_to or solid — skipped"
                )
                continue
            wall = shared.get(pair)
            if wall is None or not _fits(wall[2], wall[3], DOOR_W, DOOR_EDGE_MARGIN):
                logger.info(
                    f"  ↪ '{rooms[pair[0]].get('name')}' ↔ '{rooms[pair[1]].get('name')}' "
                    f"requested but not adjacent — skipped"
                )
                continue
            pairs.append(pair)

    if not rooms:
        return pairs

    def reachable() -> set[int]:
        seen, stack = {0}, [0]
        while stack:
            cur = stack.pop()
            for a, b in pairs + open_pairs:
                nxt = b if a == cur else a if b == cur else None
                if nxt is not None and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    seen = reachable()
    while len(seen) < len(rooms):
        candidates = []
        for (a, b), (_, _, lo, hi) in shared.items():
            if (a in seen) == (b in seen) or not _fits(lo, hi, DOOR_W, DOOR_EDGE_MARGIN):
                continue
            inside = a if a in seen else b
            is_circulation = any(k in names[inside] for k in _CIRCULATION_KEYWORDS)
            candidates.append(((a, b) not in blocked, is_circulation, hi - lo, (a, b)))
        if not candidates:
            stranded = [rooms[i].get("name") for i in range(len(rooms)) if i not in seen]
            logger.warning(f"⚠️  No wall wide enough to reach: {stranded}")
            break
        allowed, _, _, pair = max(candidates)
        if not allowed:
            logger.warning(
                f"⚠️  '{rooms[pair[0]].get('name')}' ↔ '{rooms[pair[1]].get('name')}' is marked "
                f"no_door_to but is the only way in — keeping the door"
            )
            if notes is not None:
                notes.append(
                    f"The doorway between {rooms[pair[0]].get('name')} and {rooms[pair[1]].get('name')} "
                    f"stays: it is the only way into part of the house"
                )
        logger.info(
            f"  ➕ Added door '{rooms[pair[0]].get('name')}' ↔ '{rooms[pair[1]].get('name')}' "
            f"so every room is reachable"
        )
        pairs.append(pair)
        seen = reachable()
    return pairs


def _free_intervals(lo: float, hi: float, blocked: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Subtract ``blocked`` intervals from ``lo..hi``."""
    free, cursor = [], lo
    for b_lo, b_hi in sorted(blocked):
        if b_lo > cursor:
            free.append((cursor, min(b_lo, hi)))
        cursor = max(cursor, b_hi)
        if cursor >= hi:
            break
    if cursor < hi:
        free.append((cursor, hi))
    return [(a, b) for a, b in free if b - a > _EPS]


def _room_sides(rect: dict) -> list[tuple[str, float, float, float]]:
    """The four sides of a room as ``(axis, line, lo, hi)``: front, east, back, west."""
    return [
        ("x", rect["z0"], rect["x0"], rect["x1"]),
        ("z", rect["x1"], rect["z0"], rect["z1"]),
        ("x", rect["z1"], rect["x0"], rect["x1"]),
        ("z", rect["x0"], rect["z0"], rect["z1"]),
    ]


_SIDE_NAMES = ("front", "right", "back", "left")  # the order of _room_sides


def _side_name(rect: dict, axis: str, line: float) -> str | None:
    """Which side of the room (front/right/back/left) lies on ``axis``/``line``."""
    for name, (ax, ln, _, _) in zip(_SIDE_NAMES, _room_sides(rect)):
        if ax == axis and abs(ln - line) < _EPS:
            return name
    return None


def _side_set(raw: Any) -> set[str]:
    """The sides a room field names (``"solid_walls": ["back", "left"]``), with
    the usual aliases; ``"all"`` (or ``true``) means every side."""
    if raw is True:
        return set(_SIDE_NAMES)
    sides = set()
    for item in _name_list(raw):
        side = str(item or "").strip().lower().removesuffix("wall").strip()
        if side in ("all", "every", "all sides"):
            return set(_SIDE_NAMES)
        side = _SIDE_ALIASES.get(side, side)
        if side in _SIDE_NAMES:
            sides.add(side)
    return sides


def _openings_within(side: tuple, openings: list[dict]) -> list[dict]:
    """Openings on this stretch of wall itself, not just on its line."""
    _, _, lo, hi = side
    return [o for o in _opening_on(side, openings) if o["hi"] > lo + _EPS and o["lo"] < hi - _EPS]


def exterior_intervals(side: tuple, shared: dict) -> list[tuple[float, float]]:
    """Parts of a room side (``(axis, line, lo, hi)``) that no other room touches."""
    axis, line, lo, hi = side
    blocked = [(w[2], w[3]) for w in shared.values() if w[0] == axis and abs(w[1] - line) < _EPS]
    return _free_intervals(lo, hi, blocked)


def _point(axis: str, line: float, along: float, y: float = 0.0) -> dict:
    if axis == "x":
        return {"x": round(along, 4), "y": round(y, 4), "z": round(line, 4)}
    return {"x": round(line, 4), "y": round(y, 4), "z": round(along, 4)}


def _opening_on(side: tuple, openings: list[dict]) -> list[dict]:
    axis, line, _, _ = side
    return [o for o in openings if o["axis"] == axis and abs(o["line"] - line) < _EPS]


def generate_walls(rect: dict, height: float, openings: list[dict]) -> list:
    """Generate wall geometry for a room, split around door and window openings.

    N/S walls are extended by WALL_T on each end so they wrap around and fill
    the corners where E/W walls meet them, eliminating the corner gaps.

    Each opening removes a ``bottom..top`` band over ``lo..hi`` from every wall on
    its line, so the walls of both rooms either side of a doorway get the same
    hole. A wall comes out as several pieces; each piece's ``start.y`` is the
    height of its base (0 for full-height pieces, the door/window top for headers).
    """
    wt = WALL_T
    pieces = []
    for axis, line, lo, hi in _room_sides(rect):
        if axis == "x":
            lo, hi = lo - wt, hi + wt

        def piece(a: float, b: float, y0: float, y1: float):
            if b - a > _EPS and y1 - y0 > _EPS:
                pieces.append({
                    "start": _point(axis, line, a, y0),
                    "end": _point(axis, line, b, y0),
                    "height": round(y1 - y0, 4),
                    "material": "drywall",
                })

        cursor = lo
        for o in sorted(_opening_on((axis, line, lo, hi), openings), key=lambda o: o["lo"]):
            o_lo, o_hi = max(o["lo"], lo), min(o["hi"], hi)
            if o_hi <= o_lo:
                continue
            piece(cursor, o_lo, 0.0, height)
            piece(o_lo, o_hi, 0.0, min(o["bottom"], height))
            piece(o_lo, o_hi, max(o["top"], 0.0), height)
            cursor = max(cursor, o_hi)
        piece(cursor, hi, 0.0, height)
    return pieces


def _segment_wall(
    a: tuple[float, float], b: tuple[float, float], height: float,
    hole: tuple[float, float, float, float] | None = None,
) -> list[dict]:
    """Wall pieces along the straight segment ``a → b`` (``(x, z)`` points, any angle).

    ``hole`` is ``(lo, hi, bottom, top)``: a window between ``lo`` and ``hi`` metres
    from ``a``. Pieces use the same shape as ``generate_walls``.
    """
    length = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
    if length <= _EPS:
        return []
    ux, uz = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    pieces = []

    def piece(t0: float, t1: float, y0: float, y1: float):
        if t1 - t0 > _EPS and y1 - y0 > _EPS:
            pieces.append({
                "start": {"x": round(a[0] + ux * t0, 4), "y": round(y0, 4), "z": round(a[1] + uz * t0, 4)},
                "end": {"x": round(a[0] + ux * t1, 4), "y": round(y0, 4), "z": round(a[1] + uz * t1, 4)},
                "height": round(y1 - y0, 4),
                "material": "drywall",
            })

    if hole is None:
        piece(0.0, length, 0.0, height)
        return pieces
    lo, hi, bottom, top = hole
    piece(0.0, lo, 0.0, height)
    piece(lo, hi, 0.0, bottom)
    piece(lo, hi, top, height)
    piece(hi, length, 0.0, height)
    return pieces


def _slab(x0: float, x1: float, z0: float, z1: float, y: float, material: str) -> dict:
    """An axis-aligned floor/ceiling slab in the ``generate_floor`` vertex format."""
    return {
        "vertices": [
            {"x": round(x0, 4), "y": y, "z": round(z0, 4)},
            {"x": round(x1, 4), "y": y, "z": round(z0, 4)},
            {"x": round(x1, 4), "y": y, "z": round(z1, 4)},
            {"x": round(x0, 4), "y": y, "z": round(z1, 4)},
        ],
        "material": material,
    }


def bay_spec(room: dict) -> dict | None:
    """The room's requested bay window, cleaned up (sizes in metres), or None.

    The floor plan stores ``{"side": "front"|"back"|"left"|"right", "width": ft,
    "depth": ft, "style": "angled"|"box"}``; side defaults to front, style to angled.
    """
    raw = room.get("bay_window")
    if raw is True:
        raw = {}
    if not isinstance(raw, dict):
        return None
    side = str(raw.get("side") or "front").strip().lower()
    side = {"street": "front", "rear": "back", "east": "right", "west": "left"}.get(side, side)
    if side not in _BAY_SIDES:
        return None
    style = "box" if str(raw.get("style") or "").strip().lower() == "box" else "angled"
    return {
        "side": side,
        "style": style,
        "width": max(BAY_MIN_W, _feet(raw.get("width"), BAY_DEFAULT_W / FT_TO_M) * FT_TO_M),
        "depth": min(BAY_MAX_D, max(BAY_MIN_D, _feet(raw.get("depth"), BAY_DEFAULT_D / FT_TO_M) * FT_TO_M)),
    }


def _gap_outward(axis: str, line: float, lo: float, hi: float, n: int, rects: list[dict]) -> float | None:
    """Clear distance from a wall (``axis``/``line``, over ``lo..hi``) outward (``n`` = ±1)
    to the nearest rectangle in the way, or None when nothing is."""
    gap = None
    for r in rects:
        if axis == "x":  # wall runs along x at z = line
            overlaps = r["x0"] < hi - _EPS and r["x1"] > lo + _EPS
            d = (r["z0"] - line) if n > 0 else (line - r["z1"])
        else:
            overlaps = r["z0"] < hi - _EPS and r["z1"] > lo + _EPS
            d = (r["x0"] - line) if n > 0 else (line - r["x1"])
        if overlaps and d > -_EPS and (gap is None or d < gap):
            gap = d
    return gap


def build_bay(
    rect: dict, spec: dict, height: float, openings: list[dict],
    shared: dict, obstacles: list[dict], floor_material: str, ceiling_material: str,
) -> dict | None:
    """Place a bay window on one side of a room, or return None if it doesn't fit.

    It goes on the longest stretch of outside wall on that side that is clear of
    other openings, shrinking to fit; it never pushes into ``obstacles`` (other rooms
    and bays). Returns the opening to cut in the room's wall plus the bay's walls,
    windows, floor and ceiling, and its outline for drawing.
    """
    index, (dx, dz) = _BAY_SIDES[spec["side"]]
    side = _room_sides(rect)[index]
    axis, line, _, _ = side
    n = dx + dz  # +1 or -1: which way "out" is along the wall's normal
    near = [(o["lo"] - EDGE_MARGIN, o["hi"] + EDGE_MARGIN) for o in _opening_on(side, openings)]
    spans = [
        piece
        for ext_lo, ext_hi in exterior_intervals(side, shared)
        for piece in _free_intervals(ext_lo + EDGE_MARGIN, ext_hi - EDGE_MARGIN, near)
    ]
    if not spans:
        return None
    s_lo, s_hi = max(spans, key=lambda iv: iv[1] - iv[0])
    width = min(spec["width"], s_hi - s_lo)
    if width < BAY_MIN_W - _EPS:
        return None
    center = (s_lo + s_hi) / 2
    lo, hi = center - width / 2, center + width / 2

    depth = spec["depth"]
    gap = _gap_outward(axis, line, lo - WALL_T, hi + WALL_T, n, obstacles)
    if gap is not None:
        depth = min(depth, gap / 2 - WALL_T)
    if depth < BAY_MIN_D - _EPS:
        return None
    style = spec["style"]
    inset = 0.0
    if style == "angled":
        # Sides at 45° (inset = depth), steepened when the bay is deep for its width
        # so the front keeps at least half the minimum bay width.
        inset = min(depth, (width - BAY_MIN_W / 2) / 2)
        if inset < BAY_MIN_INSET:
            style, inset = "box", 0.0

    def pt(along: float, out: float) -> tuple[float, float]:
        p = _point(axis, line + n * out, along)
        return (p["x"], p["z"])

    corners = [pt(lo, 0), pt(lo + inset, depth), pt(hi - inset, depth), pt(hi, 0)]
    top = min(WINDOW_SILL + WINDOW_H, height - 0.15)
    walls, windows = [], []
    # Run each face past its ends so the joints close up: a wall-thickness into the
    # room's wall at the base, and past the bay's own corners by tan(turn / 2) of it,
    # where turn is the angle between a side face and the front (90° on a box bay).
    turn = math.atan2(depth, inset)
    corner_ext = WALL_T * math.tan(turn / 2)
    for k, (a, b) in enumerate(zip(corners, corners[1:])):
        length = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        ux, uz = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        ext_a = WALL_T if k == 0 else corner_ext
        ext_b = WALL_T if k == 2 else corner_ext
        a2 = (a[0] - ux * ext_a, a[1] - uz * ext_a)
        b2 = (b[0] + ux * ext_b, b[1] + uz * ext_b)
        glass = length - 2 * BAY_GLASS_MARGIN
        if glass >= 0.3 and top - BAY_SILL > 0.3:
            g_lo = ext_a + BAY_GLASS_MARGIN
            walls += _segment_wall(a2, b2, height, (g_lo, g_lo + glass, BAY_SILL, top))
            windows.append({
                "position": {
                    "x": round((a[0] + b[0]) / 2, 4),
                    "y": round((BAY_SILL + top) / 2, 4),
                    "z": round((a[1] + b[1]) / 2, 4),
                },
                "width": round(glass, 4),
                "height": round(top - BAY_SILL, 4),
                # Degrees, same convention as the axis-aligned walls (0 = along x).
                "rotation": round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), 2),
            })
        else:
            walls += _segment_wall(a2, b2, height)

    xs = [c[0] for c in corners]
    zs = [c[1] for c in corners]
    # The slabs cover the bay's bounding box; on an angled bay the corners outside
    # the angled faces show as a small ledge and eave.
    x0, x1 = min(xs) - WALL_T, max(xs) + WALL_T
    z0, z1 = min(zs) - WALL_T, max(zs) + WALL_T
    return {
        "opening": {"axis": axis, "line": line, "lo": lo, "hi": hi, "bottom": 0.0, "top": height + 1.0, "kind": "bay"},
        "walls": walls,
        "windows": windows,
        "bounds": {"x0": x0, "x1": x1, "z0": z0, "z1": z1},
        "info": {
            "side": spec["side"],
            "style": style,
            "width": round(width, 3),
            "depth": round(depth, 3),
            "outline": [{"x": round(c[0], 4), "z": round(c[1], 4)} for c in corners],
            "floor": _slab(x0, x1, z0, z1, 0, floor_material),
            "ceiling": _slab(x0, x1, z0, z1, height, ceiling_material),
        },
    }


# Outside doors other than the front door: sliding glass, French or hinged doors
# from a room to the yard. Widths in feet when the plan gives none.
OUTSIDE_DOOR_STYLES = {"sliding_glass": 6.0, "french": 5.0, "hinged": 3.0}
OUTSIDE_DOOR_MIN_W = DOOR_W
OUTSIDE_DOOR_MAX_W = round(16.0 * FT_TO_M, 3)
_SIDE_ALIASES = {"street": "front", "rear": "back", "backyard": "back", "east": "right", "west": "left"}


def _door_style(raw: Any) -> str:
    text = str(raw or "").strip().lower().replace("-", " ").replace("_", " ")
    if any(k in text for k in ("slid", "slider", "glass", "patio")):
        return "sliding_glass"
    if "french" in text or "double" in text:
        return "french"
    return "hinged"


def outside_door_specs(room: dict) -> list[dict]:
    """The room's requested doors to the outside, cleaned up (sizes in metres).

    The floor plan stores ``"outside_doors": [{"side": "front"|"back"|"left"|"right",
    "style": "sliding_glass"|"french"|"hinged", "width": ft}]``; style defaults to
    hinged, width to the style's usual size. Entries with no usable side are dropped.
    """
    raw = room.get("outside_doors")
    if raw is None:
        raw = room.get("outside_door")
    if isinstance(raw, (dict, str)):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    specs = []
    for item in raw:
        if isinstance(item, str):
            item = {"side": item}
        if not isinstance(item, dict):
            continue
        side = str(item.get("side") or "").strip().lower()
        side = _SIDE_ALIASES.get(side, side)
        if side not in _BAY_SIDES:
            continue
        style = _door_style(item.get("style"))
        width = _feet(item.get("width"), OUTSIDE_DOOR_STYLES[style]) * FT_TO_M
        specs.append({
            "side": side,
            "style": style,
            "width": min(OUTSIDE_DOOR_MAX_W, max(OUTSIDE_DOOR_MIN_W, width)),
        })
    return specs


def place_outside_door(rect: dict, spec: dict, openings: list[dict], shared: dict) -> tuple | None:
    """Where an outside door goes on its side of the room: ``(axis, line, center, width)``,
    or None when that side has no stretch of outside wall wide enough for a door.

    It takes the longest stretch of outside wall clear of other openings, centred,
    narrowed to fit (never below a plain door's width).
    """
    index, _ = _BAY_SIDES[spec["side"]]
    side = _room_sides(rect)[index]
    axis, line, _, _ = side
    near = [(o["lo"] - EDGE_MARGIN, o["hi"] + EDGE_MARGIN) for o in _opening_on(side, openings)]
    spans = [
        piece
        for ext_lo, ext_hi in exterior_intervals(side, shared)
        for piece in _free_intervals(ext_lo + EDGE_MARGIN, ext_hi - EDGE_MARGIN, near)
    ]
    if not spans:
        return None
    s_lo, s_hi = max(spans, key=lambda iv: iv[1] - iv[0])
    width = min(spec["width"], s_hi - s_lo)
    if width < OUTSIDE_DOOR_MIN_W - _EPS:
        return None
    return axis, line, (s_lo + s_hi) / 2, width


def generate_floor(dimensions: dict, x_offset: float, z_offset: float, material: str = "carpet") -> dict:
    """Generate floor geometry for a room.

    Extended by WALL_T on all sides so the floor slab runs under the walls,
    closing the visible gap between the floor edge and each wall's inner face.
    """
    length = dimensions["length"]
    width = dimensions["width"]
    wt = WALL_T

    return {
        "vertices": [
            {"x": x_offset - length / 2 - wt, "y": 0, "z": z_offset - width / 2 - wt},
            {"x": x_offset + length / 2 + wt, "y": 0, "z": z_offset - width / 2 - wt},
            {"x": x_offset + length / 2 + wt, "y": 0, "z": z_offset + width / 2 + wt},
            {"x": x_offset - length / 2 - wt, "y": 0, "z": z_offset + width / 2 + wt},
        ],
        "material": material,
    }


def generate_ceiling(dimensions: dict, x_offset: float, z_offset: float, material: str = "drywall") -> dict:
    """Generate ceiling geometry for a room.

    Extended by WALL_T on all sides — mirrors the floor so the ceiling slab
    sits flush with the tops of all four walls.
    """
    length = dimensions["length"]
    width = dimensions["width"]
    height = dimensions["height"]
    wt = WALL_T

    return {
        "vertices": [
            {"x": x_offset - length / 2 - wt, "y": height, "z": z_offset - width / 2 - wt},
            {"x": x_offset + length / 2 + wt, "y": height, "z": z_offset - width / 2 - wt},
            {"x": x_offset + length / 2 + wt, "y": height, "z": z_offset + width / 2 + wt},
            {"x": x_offset - length / 2 - wt, "y": height, "z": z_offset + width / 2 + wt},
        ],
        "material": material,
    }


_MATERIAL_COLORS = {
    "wood": {"r": 0.7, "g": 0.5, "b": 0.3},
    "concrete": {"r": 0.6, "g": 0.6, "b": 0.6},
    "metal": {"r": 0.8, "g": 0.8, "b": 0.9},
    "glass": {"r": 0.7, "g": 0.9, "b": 1.0},
    "carpet": {"r": 0.7, "g": 0.6, "b": 0.5},
    "tile": {"r": 0.9, "g": 0.85, "b": 0.8},
    "drywall": {"r": 0.95, "g": 0.95, "b": 0.95},
}

_MATERIAL_TEXTURES = {
    "wood": "wood_grain",
    "concrete": "concrete_rough",
    "metal": "metal_brushed",
    "glass": "glass_clear",
    "carpet": "carpet_beige",
    "tile": "ceramic_tile",
    "drywall": "paint_white",
}


def get_material_color(material_type: str) -> dict:
    """Get RGB color for a material type."""
    return _MATERIAL_COLORS.get(material_type, {"r": 0.8, "g": 0.8, "b": 0.8})


def get_material_texture(material_type: str) -> str:
    """Get texture name for a material type."""
    return _MATERIAL_TEXTURES.get(material_type, "default")


def _clean_name(name: Any) -> str:
    """Room name as displayed, without stray list punctuation ("Bedroom 1,")."""
    return str(name or "").strip().rstrip(",;:.").strip()


def _overlap_area(a: dict, b: dict) -> float:
    return max(0.0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])) * max(0.0, min(a["z1"], b["z1"]) - max(a["z0"], b["z0"]))


def _rooms_and_rects(
    rooms_ft: list[dict], layout: dict | None
) -> tuple[list[dict], list[dict], list[dict], str]:
    """Pair each room (dimensions converted to metres) with its rectangle.

    Uses the AI's nested-split ``layout`` when it is valid, else packs
    ``rooms_ft`` on the 3-wide grid. Room 0 of the result is the entry. Also
    returns the layout's open (outdoor) rectangles, which the grid never has.
    """
    rooms_ft = [
        {**r, "name": _clean_name(r.get("name"))} if r.get("name") else r
        for r in rooms_ft
        if isinstance(r, dict)
    ]
    by_name = {_normalize(r.get("name", "")): r for r in rooms_ft}
    if layout:
        try:
            placed, open_rects = _walk_layout(layout)
            rooms, rects = [], []
            for name, rect in placed:
                src = by_name.get(_normalize(name), {})
                height = _feet((src.get("dimensions") or {}).get("height"), 9.0)
                rooms.append({**src, "name": name, "dimensions": {
                    "length": round(rect["x1"] - rect["x0"], 3),
                    "width": round(rect["z1"] - rect["z0"], 3),
                    "height": round(height * FT_TO_M, 3),
                }})
                rects.append(rect)
            missing = set(by_name) - {_normalize(n) for n, _ in placed}
            if missing:
                logger.warning(f"⚠️  Rooms listed but not in the layout (dropped): {sorted(missing)}")
            entry = _pick_entry(rooms, rects, (layout or {}).get("entry"))
            order = [entry] + [i for i in range(len(rooms)) if i != entry]
            kind = "rects" if is_rect_layout(layout) else "split"
            logger.info(f"📐 Using {'rectangle' if kind == 'rects' else 'nested-split'} layout: "
                        f"{len(rooms)} rooms, entry '{rooms[entry]['name']}'")
            return [rooms[i] for i in order], [rects[i] for i in order], open_rects, kind
        except LayoutError as e:
            logger.warning(f"⚠️  Layout rejected ({e}) — falling back to grid layout")

    rooms = [{**r, "dimensions": ft_to_m_dims(r.get("dimensions") or {})} for r in rooms_ft]
    rects = []
    for room, (x, z, eff_width) in zip(rooms, compute_packed_positions(rooms)):
        rects.append(_room_rect(x, z, room["dimensions"]["length"], eff_width))
        room["dimensions"] = {**room["dimensions"], "width": eff_width}
    return rooms, rects, [], "grid"


_ENTRY_KEYWORDS = ("entry", "foyer", "mudroom", "living", "great", "family")


SPAWN_DISTANCE = 3.0


def _spawn_distance(x: float, z: float, dx: int, dz: int, rects: list[dict]) -> float:
    """How far outside the front door at ``(x, z)`` to put the player, walking
    ``(dx, dz)``: SPAWN_DISTANCE, or half the gap when the door opens into an
    open area with another room across it (the inside corner of an L)."""
    gap = None
    for r in rects:
        if dz and r["x0"] - _EPS <= x <= r["x1"] + _EPS:
            d = (r["z0"] - z) if dz > 0 else (z - r["z1"])
        elif dx and r["z0"] - _EPS <= z <= r["z1"] + _EPS:
            d = (r["x0"] - x) if dx > 0 else (x - r["x1"])
        else:
            continue
        if d > -_EPS and (gap is None or d < gap):
            gap = d
    return SPAWN_DISTANCE if gap is None else min(SPAWN_DISTANCE, gap / 2)


def _pick_entry(rooms: list[dict], rects: list[dict], named: str | None) -> int:
    """Index of the room that gets the front door: the one the AI named, else the
    first street-facing room that sounds like an entry, else the first street-facing room."""
    if named:
        idx = _resolve_room(named, [_normalize(r["name"]) for r in rooms])
        if idx is not None:
            return idx
    front = [i for i, r in enumerate(rects) if abs(r["z0"]) < _EPS] or list(range(len(rooms)))
    for keyword in _ENTRY_KEYWORDS:
        for i in front:
            if keyword in _normalize(rooms[i]["name"]):
                return i
    return front[0]


def _build_storey(
    rooms_ft: list[dict],
    materials: list[dict] | None = None,
    project_id: int | None = None,
    project_name: str = "Generated House",
    target_platform: str = "quest2",
    optimize_for_vr: bool = True,
    layout: dict | None = None,
    exterior: dict | None = None,
    plant_models: list[dict] | None = None,
    furniture: dict | None = None,
    furniture_models: list[dict] | None = None,
    kitchen_styles: list[dict] | None = None,
    level: int = 0,
    rise: float | None = None,
    holes: list[dict] | None = None,
    check: bool = True,
) -> dict:
    """One storey of the house (``build_geometry_from_rooms`` stacks them).

    ``level`` > 0 is an upper floor: no front door or doors to the yard, and the
    floor-plan check is left to the caller. ``rise`` (metres) is the height to the
    floor above, which stair rooms climb; ``holes`` are where the stairs from below
    come up through this floor (metres), cut out of it and railed round. The result
    keeps what the storeys are stacked with under ``_storey``.

    Args:
        rooms_ft: Rooms with dimensions in FEET. Each dict may include:
            ``name``, ``dimensions`` (``length``/``width``/``height`` in ft),
            ``floor_material`` (default ``"carpet"``),
            ``wall_material`` (default ``"drywall"``),
            ``connects_to`` (names of rooms reached through a doorway),
            ``no_door_to`` (names of rooms it must not get a doorway to).
            Without a ``layout`` they are packed 3 per row in list order and
            room 0 is the entry.
        materials: Optional list of material dicts with ``material_type`` and
            ``name`` keys (matches the ``Material`` model shape). If omitted,
            the material map falls back to drywall/carpet defaults used by the
            generated walls/floors.
        project_id / project_name: Metadata echoed into the response.
        target_platform / optimize_for_vr: Metadata for the Quest client.
        layout: The AI's nested-split floor plan (see ``layout_rects_from_tree``).
            Positions and sizes come from it when valid; ``rooms_ft`` then only
            supplies heights, materials and ``connects_to``.
        exterior: The plan's outside description (roof, wall finish, landscaping;
            see ``vr_exterior.exterior_spec``). Without one the house is built
            as before: no roof, white walls, no yard.
        plant_models: Finished 3D models made from photos
            (``plant_model_service.ready_models``); a plant naming one is drawn
            with it instead of its procedural mesh.
        furniture: The plan's furniture by room (see ``vr_furniture.furniture_spec``).
        furniture_models: Finished photo models of kind "furniture"; a piece whose
            name matches one is drawn with it.

    Returns:
        The ``geometry`` dict sent to the Quest. Walls are pre-split around door
        and window openings (each piece's ``start.y`` is its base height); doors
        list the ``rooms`` they join and rooms list the ids they ``connects_to``.
    """
    rooms_m, rects, open_rects, layout_source = _rooms_and_rects(rooms_ft, layout)
    shared = find_shared_walls(rects)
    holes = holes or []
    # Requested features that could not be built, in words for the headset/dashboard.
    notes: list[str] = []
    if isinstance(layout, dict) and check:
        from .layout_check import layout_problems  # it imports this module

        # What the planner changed to make the description fit, then what is still wrong.
        notes += [str(n) for n in _name_list(layout.get("notes"))][:4]
        notes += layout_problems({"layout": layout, "rooms": rooms_ft})[:4]
    open_pairs = plan_open_walls(rooms_m, rects, shared, notes)
    connections = plan_connections(rooms_m, shared, notes, rects=rects, open_pairs=open_pairs)
    solid = [_side_set(r.get("solid_walls")) for r in rooms_m]

    openings: list[dict] = []
    doors: list[dict] = []
    windows: list[dict] = []
    connected_ids: dict[int, list[int]] = {i: [] for i in range(len(rooms_m))}
    open_ids: dict[int, list[int]] = {i: [] for i in range(len(rooms_m))}

    # Walls taken out between open rooms: a full-width hole up to the lower ceiling
    # (the taller room keeps a strip of wall above it).
    open_walls: list[dict] = []
    for a, b in open_pairs:
        axis, line, lo, hi = shared[(a, b)]
        top = min(rooms_m[a]["dimensions"]["height"], rooms_m[b]["dimensions"]["height"])
        openings.append({"axis": axis, "line": line, "lo": lo, "hi": hi, "bottom": 0.0, "top": top, "kind": "open"})
        open_walls.append({
            "rooms": [a + 1, b + 1],
            "start": _point(axis, line, lo),
            "end": _point(axis, line, hi),
            "height": round(top, 4),
        })
        open_ids[a].append(b + 1)
        open_ids[b].append(a + 1)
        logger.info(f"  ⬜ '{rooms_m[a].get('name')}' open to '{rooms_m[b].get('name')}' (wall removed)")

    def add_door(
        axis: str, line: float, center: float, room_ids: list[int], door_type: str,
        width: float = DOOR_W, **extra: Any,
    ):
        openings.append({
            "axis": axis, "line": line,
            "lo": center - width / 2, "hi": center + width / 2,
            "bottom": 0.0, "top": DOOR_H, "kind": "door",
        })
        doors.append({
            "id": 100 + len(doors) + 1,
            "position": _point(axis, line, center),
            "width": round(width, 4),
            "height": DOOR_H,
            "rotation": 0 if axis == "x" else 90,
            "door_type": door_type,
            "rooms": room_ids,
            **extra,
        })

    # Front door: on the entry's (room 0's) outside wall, street side first.
    # Spawn the player a few metres outside it.
    spawn = None
    if rects and level == 0:
        front, east, back, west = _room_sides(rects[0])
        # Each side with the direction pointing out of the house, street side first;
        # walls kept solid only when there is no other way in.
        sides = (("front", front, (0, -1)), ("right", east, (1, 0)), ("left", west, (-1, 0)), ("back", back, (0, 1)))
        for keep_solid in (True, False):
            for name, side, (dx, dz) in sides:
                if keep_solid and name in solid[0]:
                    continue
                spans = [iv for iv in exterior_intervals(side, shared) if _fits(*iv, DOOR_W)]
                if not spans:
                    continue
                lo, hi = max(spans, key=lambda iv: iv[1] - iv[0])
                center = (lo + hi) / 2
                add_door(side[0], side[1], center, [1], "exterior")
                door = doors[-1]["position"]
                step = _spawn_distance(door["x"], door["z"], dx, dz, rects[1:])
                spawn = {"x": door["x"] + dx * step, "y": 1.6, "z": door["z"] + dz * step}
                if not keep_solid:
                    notes.append(f"The front door had to go in {rooms_m[0].get('name')}'s solid {name} wall")
                break
            if spawn:
                break

    for a, b in connections:
        axis, line, lo, hi = shared[(a, b)]
        add_door(axis, line, (lo + hi) / 2, [a + 1, b + 1], "interior")
        connected_ids[a].append(b + 1)
        connected_ids[b].append(a + 1)

    # Doors to the yard (door_type "patio"; the front door stays the only "exterior"
    # one). Placed before bay windows and ordinary windows, which then keep clear of them.
    for idx, (room, rect) in enumerate(zip(rooms_m, rects)):
        for spec in outside_door_specs(room):
            label = spec["style"].replace("_", " ")
            if level > 0:
                notes.append(f"{room.get('name')} is upstairs, so its {label} door to the yard was left out")
                continue
            if spec["side"] in solid[idx]:
                notes.append(f"{room.get('name')}'s {spec['side']} wall is kept solid, so the {label} door was left out")
                continue
            spot = place_outside_door(rect, spec, openings, shared)
            if spot is None:
                logger.info(f"  ↪ '{room.get('name')}': no {spec['side']} outside wall for a {label} door — skipped")
                notes.append(f"{room.get('name')} has no {spec['side']} outside wall for a {label} door")
                continue
            axis, line, center, width = spot
            add_door(axis, line, center, [idx + 1], "patio", width, style=spec["style"], side=spec["side"])
            logger.info(f"  🚪 '{room.get('name')}': {width / FT_TO_M:.0f} ft {label} door on the {spec['side']}")

    # Bay windows, where the plan asks for them. They replace the room's ordinary window.
    bays: dict[int, dict] = {}
    for idx, (room, rect) in enumerate(zip(rooms_m, rects)):
        spec = bay_spec(room)
        if spec is None:
            continue
        if spec["side"] in solid[idx]:
            notes.append(f"{room.get('name')}'s {spec['side']} wall is kept solid, so the bay window was left out")
            continue
        obstacles = [r for j, r in enumerate(rects) if j != idx] + [b["bounds"] for b in bays.values()]
        bay = build_bay(
            rect, spec, room["dimensions"]["height"], openings, shared, obstacles,
            room.get("floor_material", "carpet"), room.get("wall_material", "drywall"),
        )
        if bay is None:
            logger.info(f"  ↪ '{room.get('name')}': no room for a {spec['side']} bay window — skipped")
            notes.append(f"{room.get('name')} has no room for a {spec['side']} bay window")
            continue
        openings.append(bay["opening"])
        for w in bay["windows"]:
            windows.append({
                "id": 200 + len(windows) + 1, **w,
                "glass_type": "double_pane", "room": idx + 1, "bay": True,
            })
        bays[idx] = bay
        logger.info(f"  🪟 '{room.get('name')}': {bay['info']['style']} bay window on the {spec['side']}")

    # One window per room, on the longest stretch of exterior wall left over.
    # "window": false leaves it out, {"side": ...} puts it on that side; never in a
    # solid wall, and a kitchen keeps its last clean wall for counters.
    for idx, (room, rect) in enumerate(zip(rooms_m, rects)):
        name = _normalize(room.get("name", ""))
        win = room.get("window", True)
        if win is False or str(win).strip().lower() in ("none", "no", "false", "0"):
            continue
        wanted = _side_set([win.get("side")]) if isinstance(win, dict) else set()
        if idx in bays or (not isinstance(win, dict) and any(k in name for k in _NO_WINDOW_KEYWORDS)):
            continue
        win_w = SMALL_WINDOW_W if any(k in name for k in _SMALL_WINDOW_KEYWORDS) else WINDOW_W
        clean = [
            side_name for side_name, side in zip(_SIDE_NAMES, _room_sides(rect))
            if side[3] - side[2] >= CLEAN_WALL_MIN and not _openings_within(side, openings)
        ]
        keep_clean = any(k in name for k in _CLEAN_WALL_KEYWORDS) and not solid[idx] and len(clean) == 1
        best = None
        for side_name, side in zip(_SIDE_NAMES, _room_sides(rect)):
            if side_name in solid[idx] or (wanted and side_name not in wanted):
                continue
            if keep_clean and side_name == clean[0]:
                continue
            axis, line, _, _ = side
            near_openings = [
                (o["lo"] - EDGE_MARGIN, o["hi"] + EDGE_MARGIN) for o in _opening_on(side, openings)
            ]
            free = [
                piece
                for ext_lo, ext_hi in exterior_intervals(side, shared)
                for piece in _free_intervals(ext_lo, ext_hi, near_openings)
            ]
            for f_lo, f_hi in free:
                if _fits(f_lo, f_hi, win_w) and (best is None or f_hi - f_lo > best[3] - best[2]):
                    best = (axis, line, f_lo, f_hi)
        if best is None:
            if wanted:
                notes.append(f"{room.get('name')} has no room for a window on the {'/'.join(sorted(wanted))}")
            elif keep_clean:
                logger.info(f"  ↪ '{room.get('name')}': no window, to keep its {clean[0]} wall clear for counters")
            continue
        axis, line, f_lo, f_hi = best
        center = (f_lo + f_hi) / 2
        openings.append({
            "axis": axis, "line": line,
            "lo": center - win_w / 2, "hi": center + win_w / 2,
            "bottom": WINDOW_SILL, "top": WINDOW_SILL + WINDOW_H, "kind": "window",
        })
        windows.append({
            "id": 200 + len(windows) + 1,
            "position": _point(axis, line, center, WINDOW_SILL + WINDOW_H / 2),
            "width": win_w,
            "height": WINDOW_H,
            "rotation": 0 if axis == "x" else 90,
            "glass_type": "double_pane",
            "room": idx + 1,
        })

    # Stairs up to the next floor, in rooms that hold them.
    stairs: list[dict] = []
    if rise:
        from .vr_stairs import is_stair_room, plan_stairs

        for idx, (room, rect) in enumerate(zip(rooms_m, rects)):
            if not is_stair_room(room.get("name")):
                continue
            at = [d["position"] for d in doors if idx + 1 in d["rooms"]]
            st = plan_stairs(rect, rise, at, openings)
            st["room"] = idx + 1
            stairs.append(st)
            if st["short"]:
                notes.append(f"{room.get('name')} is short for a full flight of stairs, so its steps are steep")

    rooms_out: list[dict] = []
    for idx, room in enumerate(rooms_m):
        room_id = idx + 1
        rect = rects[idx]
        x_offset = (rect["x0"] + rect["x1"]) / 2
        z_offset = (rect["z0"] + rect["z1"]) / 2
        geom_dims = {
            "length": rect["x1"] - rect["x0"],
            "width": rect["z1"] - rect["z0"],
            "height": room["dimensions"]["height"],
        }
        room_name = room.get("name", f"Room {room_id}")
        logger.info(
            f"  Room {room_id}: '{room_name}' "
            f"{geom_dims['length'] / FT_TO_M:.1f}x{geom_dims['width'] / FT_TO_M:.1f}"
            f"x{geom_dims['height'] / FT_TO_M:.1f} ft "
            f"@ ({x_offset / FT_TO_M:.1f}, 0, {z_offset / FT_TO_M:.1f}) ft → doors to {connected_ids[idx]}"
        )
        bay = bays.get(idx)
        rooms_out.append({
            "id": room_id,
            "name": room_name,
            "position": {"x": x_offset, "y": 0, "z": z_offset},
            # Actual size as built (grid rows stretch rooms to the row's depth).
            "dimensions": {k: round(v, 3) for k, v in geom_dims.items()},
            "bounds": {k: round(v, 4) for k, v in rects[idx].items()},
            "connects_to": connected_ids[idx],
            # Rooms it is open to (no wall between) and the sides it keeps clear of openings.
            "open_to": open_ids[idx],
            "solid_walls": [s for s in _SIDE_NAMES if s in solid[idx]],
            "walls": generate_walls(rects[idx], geom_dims["height"], openings)
            + (bay["walls"] if bay else []),
            # Bump-out outline plus its own floor and ceiling slabs, or null.
            "bay_window": bay["info"] if bay else None,
            "floor": generate_floor(
                geom_dims, x_offset, z_offset, room.get("floor_material", "carpet")
            ),
            "ceiling": generate_ceiling(
                geom_dims, x_offset, z_offset, room.get("wall_material", "drywall")
            ),
        })
        # The floor in pieces round a stair hole from below; the ceilings the levels above leave.
        floor = rooms_out[-1]["floor"]
        v = floor["vertices"]
        whole = {"x0": v[0]["x"], "x1": v[2]["x"], "z0": v[0]["z"], "z1": v[2]["z"]}
        rooms_out[-1]["floors"] = [
            _slab(r["x0"], r["x1"], r["z0"], r["z1"], 0, floor["material"])
            for r in subtract_rects(whole, [h["footprint"] for h in holes])
        ]
        rooms_out[-1]["ceilings"] = [rooms_out[-1]["ceiling"]]

    material_map: dict[str, dict[str, Any]] = {}
    if materials:
        for material in materials:
            mtype = material.get("material_type") if isinstance(material, dict) else getattr(material, "material_type", None)
            mname = material.get("name") if isinstance(material, dict) else getattr(material, "name", None)
            if not mtype:
                continue
            material_map[mtype] = {
                "name": mname or mtype,
                "color": get_material_color(mtype),
                "texture": get_material_texture(mtype),
            }
    if "drywall" not in material_map:
        material_map["drywall"] = {
            "name": "Drywall",
            "color": get_material_color("drywall"),
            "texture": get_material_texture("drywall"),
        }
    if "carpet" not in material_map:
        material_map["carpet"] = {
            "name": "Carpet",
            "color": get_material_color("carpet"),
            "texture": get_material_texture("carpet"),
        }
    logger.info(f"🎨 Material map: {list(material_map.keys())}")

    from .vr_exterior import build_exterior, exterior_spec  # imports this module

    exterior_out = build_exterior(
        exterior_spec(exterior), rects, [r["dimensions"]["height"] for r in rooms_m],
        open_rects, openings, shared, bays, plant_models,
    )

    from .vr_floors import build_finishes
    from .vr_furniture import build_furniture, furniture_spec

    furniture_out, furniture_notes = build_furniture(
        furniture_spec(furniture),
        [{"id": r["id"], "name": r["name"], "bounds": r["bounds"]} for r in rooms_out],
        openings, furniture_models, kitchen_styles,
        blocked=[st["footprint"] for st in stairs + holes],
    )
    notes += furniture_notes
    if stairs or holes:
        from .vr_stairs import railing_mesh, stair_mesh

        furniture_out = furniture_out or {"meshes": {}, "pieces": [], "models": []}
        flights = [(st, st["room"], "stairs", stair_mesh) for st in stairs]
        for hole in holes:
            over = next((r["id"] for r in rooms_out if _overlap_area(r["bounds"], hole["footprint"]) > 0), None)
            if over is not None:
                flights.append((hole, over, "railing", railing_mesh))
        for st, room_id, kind, make in flights:
            mesh, (cx, cz) = make(st)
            key = f"{kind}-L{level}-{room_id}-{len(furniture_out['meshes'])}"
            furniture_out["meshes"][key] = mesh.out()
            fp = st["footprint"]
            furniture_out["pieces"].append({
                "room": room_id, "type": kind,
                "position": {"x": round(cx, 3), "y": 0.025, "z": round(cz, 3)}, "yaw": 0.0,
                "outline": [[round(fp["x0"], 3), round(fp["z0"], 3)], [round(fp["x1"], 3), round(fp["z0"], 3)],
                            [round(fp["x1"], 3), round(fp["z1"], 3)], [round(fp["x0"], 3), round(fp["z1"], 3)]],
                "color": get_material_color("wood") if kind == "stairs" else {"r": 0.23, "g": 0.18, "b": 0.15},
                "mesh": key, "scale": {"x": 1, "y": 1, "z": 1},
            })

    return {
        "project_id": project_id,
        "project_name": project_name,
        "rooms": rooms_out,
        "doors": doors,
        "windows": windows,
        # Walls taken out between open rooms (open_to), as the stretch removed.
        "open_walls": open_walls,
        "materials": material_map,
        # Outdoor parts of the footprint (an L/U/T-shaped house), for drawing the plan.
        "open_areas": [{"bounds": {k: round(v, 4) for k, v in r.items()}} for r in open_rects],
        # Roof meshes, wall finish, ground and landscaping, or null (see vr_exterior.py).
        "exterior": exterior_out,
        # Pieces placed in the rooms, their shared meshes and photo models, or null (vr_furniture.py).
        "furniture": furniture_out,
        # What each floor is finished with (planks, tiles, carpet), drawn over its slabs (vr_floors.py).
        "finishes": build_finishes(rooms_out),
        # Outside the front door (or in front of the entry if it had no room for one).
        "spawn_position": spawn or {
            "x": rooms_out[0]["position"]["x"] if rooms_out else 0.0,
            "y": 1.6,
            "z": -3.0,
        },
        # Requested doors and bay windows that did not fit, e.g.
        # "Hallway has no back outside wall for a sliding glass door".
        "notes": notes,
        # Stair flights the player walks up: where, and how the height runs along them.
        "stairs": [{**st["footprint"], **st["ramp"], "room": st["room"]} for st in stairs],
        "_storey": {"rects": rects, "heights": [r["dimensions"]["height"] for r in rooms_m], "open_rects": open_rects,
                    "openings": openings, "shared": shared, "bays": bays, "flights": stairs},
        "metadata": {
            "total_rooms": len(rooms_out),
            "total_doors": len(doors),
            "total_windows": len(windows),
            "layout": layout_source,
            "platform": target_platform,
            "optimized": optimize_for_vr,
        },
    }


def build_geometry_from_rooms(rooms_ft: list[dict], layout: dict | None = None, **kwargs: Any) -> dict:
    """Build a VR geometry payload from a list of rooms (see ``_build_storey`` for the
    arguments). A rectangle layout whose rooms have a ``level`` is built a storey at a
    time and stacked: every room on a floor with another above it takes that floor's
    height, the upper floor's slab replaces the ceilings under it, stair rooms climb to
    it, and the outside (wall finish per storey, the roof over the top of each stack, one
    yard) is built over the whole house."""
    from .vr_paint import build_paint

    levels = layout_levels(layout) if isinstance(layout, dict) else {0: layout}
    if len(levels) == 1:
        geometry = _build_storey(rooms_ft, layout=layout, **kwargs)
        geometry.pop("_storey")
        geometry["levels"] = [{"level": 0, "y": 0.0, "rooms": [r["id"] for r in geometry["rooms"]]}]
    else:
        geometry = _build_levels(rooms_ft, layout, levels, **kwargs)
    # Painted walls and ceilings, from the finished rooms (lifted, ceilings cut under the floors above).
    geometry["paint"] = build_paint(geometry["rooms"], rooms_ft or [], WALL_T)
    return geometry


def _lift(geometry: dict, dy: float, room_off: int, door_off: int, window_off: int):
    """Move a storey's geometry up ``dy`` metres and renumber its rooms, doors and
    windows after the storeys below (in place)."""
    def up(point: dict):
        point["y"] = round(point.get("y", 0) + dy, 4)

    rid = lambda i: i + room_off  # noqa: E731
    for room in geometry["rooms"]:
        room["id"] = rid(room["id"])
        room["connects_to"] = [rid(i) for i in room["connects_to"]]
        room["open_to"] = [rid(i) for i in room["open_to"]]
        up(room["position"])
        for wall in room["walls"]:
            up(wall["start"])
            up(wall["end"])
        for slab in [room["floor"], room["ceiling"], *room["floors"], *room["ceilings"]] + (
                [room["bay_window"].get("floor"), room["bay_window"].get("ceiling")] if room.get("bay_window") else []):
            for v in (slab or {}).get("vertices", []):
                up(v)
    for n, door in enumerate(geometry["doors"]):
        door["id"] = 100 + door_off + n + 1
        door["rooms"] = [rid(i) for i in door["rooms"]]
        up(door["position"])
    for n, window in enumerate(geometry["windows"]):
        window["id"] = 200 + window_off + n + 1
        window["room"] = rid(window["room"])
        up(window["position"])
    for wall in geometry["open_walls"]:
        wall["rooms"] = [rid(i) for i in wall["rooms"]]
        up(wall["start"])
        up(wall["end"])
    for st in geometry["stairs"]:
        st["room"] = rid(st["room"])
        st["y"] = round(dy, 4)
    furniture, finishes = geometry.get("furniture"), geometry.get("finishes")
    for piece in ((furniture["pieces"] + furniture["models"]) if furniture else []) + (
            finishes["pieces"] if finishes else []):
        piece["room"] = rid(piece["room"])
        up(piece["position"])


def _build_levels(rooms_ft: list[dict], layout: dict, levels: dict[int, dict], **kwargs: Any) -> dict:
    """``build_geometry_from_rooms`` for a house of several storeys."""
    from .layout_check import layout_problems  # it imports this module
    from .vr_exterior import build_exterior, exterior_spec  # imports this module
    from .vr_stairs import is_stair_room

    exterior = kwargs.pop("exterior", None)
    plant_models = kwargs.pop("plant_models", None)
    rooms = [r for r in rooms_ft if isinstance(r, dict) and r.get("name")]
    by_name = {_normalize(r["name"]): r for r in rooms}
    names = {n: [_clean_name(i.get("room") or i.get("name")) for i in lay["rects"]] for n, lay in levels.items()}

    def height_ft(name: str) -> float:
        return _feet(((by_name.get(_normalize(name)) or {}).get("dimensions") or {}).get("height"), 9.0)

    # A storey with another above it is as tall as its tallest room, every room of it.
    level_h = {n: max(height_ft(name) for name in names[n]) for n in levels}
    top = max(levels)
    notes: list[str] = [str(n) for n in _name_list(layout.get("notes"))][:4]
    notes += layout_problems({"layout": layout, "rooms": rooms})[:6]

    storeys, base, below = [], 0.0, []
    for n in sorted(levels):
        on = {_normalize(x) for x in names[n]}
        level_rooms = [
            {**r, "dimensions": {**(r.get("dimensions") or {}), "height": level_h[n]}} if n < top else r
            for r in rooms if _normalize(r["name"]) in on
        ]
        lay = dict(levels[n])
        if n > 0:
            # The way in upstairs: the room the stairs arrive in.
            up_rects = {_normalize(e["room"]): e for e in rect_entries(lay)}
            arrive = next((name for name, e in up_rects.items() for h in below
                           if _overlap_area({k: e[k] * FT_TO_M for k in ("x0", "x1", "z0", "z1")}, h["footprint"]) > 0), None)
            if arrive:
                lay["entry"] = arrive
            elif not below:
                notes.append(f"Nothing leads up to floor {n + 1}: add a room named Stairs under it")
        rise = (level_h[n] * FT_TO_M) if n < top else None
        g = _build_storey(level_rooms, layout=lay, level=n, rise=rise, holes=below, check=False, **kwargs)
        if n < top and not g["_storey"]["flights"]:
            if not any(is_stair_room(x) for x in names[n]):
                notes.append(f"Floor {n + 1} has no stairs up: add a room named Stairs with a room above it")
        storeys.append((n, base, g))
        below = g["_storey"]["flights"]
        base += level_h[n] * FT_TO_M

    # Stack them: lift, renumber, and take each ceiling out where a floor above covers it.
    out = storeys[0][2]
    room_off = door_off = window_off = 0
    all_rooms, doors, windows, open_walls, stairs, levels_out = [], [], [], [], [], []
    meshes, pieces, models, floor_meshes, floor_pieces = {}, [], [], {}, []
    for i, (n, y, g) in enumerate(storeys):
        _lift(g, y, room_off, door_off, window_off)
        above = [{"x0": r["x0"] - WALL_T, "x1": r["x1"] + WALL_T, "z0": r["z0"] - WALL_T, "z1": r["z1"] + WALL_T}
                 for _, _, ga in storeys[i + 1:] for r in ga["_storey"]["rects"]]
        for room in g["rooms"]:
            room["level"] = n
            c = room["ceiling"]
            v = c["vertices"]
            whole = {"x0": v[0]["x"], "x1": v[2]["x"], "z0": v[0]["z"], "z1": v[2]["z"]}
            room["ceilings"] = [_slab(r["x0"], r["x1"], r["z0"], r["z1"], v[0]["y"], c["material"])
                                for r in subtract_rects(whole, above)]
            room["ceiling"] = room["ceilings"][0] if room["ceilings"] else None
            room["floor"] = room["floors"][0] if room["floors"] else None
        all_rooms += g["rooms"]
        doors += g["doors"]
        windows += g["windows"]
        open_walls += g["open_walls"]
        stairs += g["stairs"]
        levels_out.append({"level": n, "y": round(y, 4), "rooms": [r["id"] for r in g["rooms"]]})
        if g.get("finishes"):
            floor_meshes.update({f"L{n}-{k}": v for k, v in g["finishes"]["meshes"].items()})
            floor_pieces += [{**p, "mesh": f"L{n}-{p['mesh']}"} for p in g["finishes"]["pieces"]]
        if g.get("furniture"):
            meshes.update(g["furniture"]["meshes"])
            pieces += g["furniture"]["pieces"]
            models += g["furniture"]["models"]
        if i > 0:
            notes += g["notes"]
        room_off += len(g["rooms"])
        door_off += len(g["doors"])
        window_off += len(g["windows"])
    notes = notes + [x for x in out["notes"] if x not in notes]

    ground = storeys[0][2]["_storey"]
    upper = [{**g["_storey"], "base": y} for _, y, g in storeys[1:]]
    out.update({
        "rooms": all_rooms, "doors": doors, "windows": windows, "open_walls": open_walls, "stairs": stairs,
        "levels": levels_out, "notes": notes,
        "furniture": {"meshes": meshes, "pieces": pieces, "models": models} if meshes or models else None,
        "finishes": {"meshes": floor_meshes, "pieces": floor_pieces} if floor_pieces else None,
        "exterior": build_exterior(exterior_spec(exterior), ground["rects"], ground["heights"], ground["open_rects"],
                                   ground["openings"], ground["shared"], ground["bays"], plant_models, upper=upper),
    })
    out["metadata"].update({"total_rooms": len(all_rooms), "total_doors": len(doors), "total_windows": len(windows),
                            "levels": len(storeys)})
    for _, _, g in storeys:
        g.pop("_storey", None)
    return out
