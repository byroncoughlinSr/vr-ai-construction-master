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
MIN_PART = 1.2


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


# Opening sizes, metres. A door or window is only placed where the wall leaves at
# least EDGE_MARGIN of solid wall on each side, so openings never eat into corners.
DOOR_W = round(3.0 * FT_TO_M, 3)
DOOR_H = round(6.67 * FT_TO_M, 3)
WINDOW_W = round(4.0 * FT_TO_M, 3)
SMALL_WINDOW_W = round(2.0 * FT_TO_M, 3)
WINDOW_H = round(4.0 * FT_TO_M, 3)
WINDOW_SILL = round(3.0 * FT_TO_M, 3)
EDGE_MARGIN = 0.25
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


def _fits(lo: float, hi: float, opening_w: float) -> bool:
    return hi - lo >= opening_w + 2 * EDGE_MARGIN


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


def plan_connections(rooms: list[dict], shared: dict) -> list[tuple[int, int]]:
    """Decide which pairs of rooms get a doorway.

    Honours each room's ``connects_to`` where the two rooms actually share
    enough wall for a door, then adds doors until every room is reachable from
    the entry (room 0), preferring to connect through circulation spaces.
    """
    names = [_normalize(r.get("name", "")) for r in rooms]
    pairs: list[tuple[int, int]] = []

    for i, room in enumerate(rooms):
        targets = room.get("connects_to") or []
        if isinstance(targets, str):  # a lone name instead of a list
            targets = [targets]
        for target in targets:
            j = _resolve_room(target, names)
            if j is None or j == i:
                logger.info(f"  ↪ '{room.get('name')}' connects_to '{target}': no such room")
                continue
            pair = (min(i, j), max(i, j))
            if pair in pairs:
                continue
            wall = shared.get(pair)
            if wall is None or not _fits(wall[2], wall[3], DOOR_W):
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
            for a, b in pairs:
                nxt = b if a == cur else a if b == cur else None
                if nxt is not None and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    seen = reachable()
    while len(seen) < len(rooms):
        candidates = []
        for (a, b), (_, _, lo, hi) in shared.items():
            if (a in seen) == (b in seen) or not _fits(lo, hi, DOOR_W):
                continue
            inside = a if a in seen else b
            is_circulation = any(k in names[inside] for k in _CIRCULATION_KEYWORDS)
            candidates.append((is_circulation, hi - lo, (a, b)))
        if not candidates:
            stranded = [rooms[i].get("name") for i in range(len(rooms)) if i not in seen]
            logger.warning(f"⚠️  No wall wide enough to reach: {stranded}")
            break
        pair = max(candidates)[2]
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
        "opening": {"axis": axis, "line": line, "lo": lo, "hi": hi, "bottom": 0.0, "top": height + 1.0},
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
            logger.info(f"📐 Using nested-split layout: {len(rooms)} rooms, entry '{rooms[entry]['name']}'")
            return [rooms[i] for i in order], [rects[i] for i in order], open_rects, "split"
        except LayoutError as e:
            logger.warning(f"⚠️  Layout tree rejected ({e}) — falling back to grid layout")

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


def build_geometry_from_rooms(
    rooms_ft: list[dict],
    materials: list[dict] | None = None,
    project_id: int | None = None,
    project_name: str = "Generated House",
    target_platform: str = "quest2",
    optimize_for_vr: bool = True,
    layout: dict | None = None,
) -> dict:
    """Build a VR geometry payload from a list of rooms.

    Args:
        rooms_ft: Rooms with dimensions in FEET. Each dict may include:
            ``name``, ``dimensions`` (``length``/``width``/``height`` in ft),
            ``floor_material`` (default ``"carpet"``),
            ``wall_material`` (default ``"drywall"``),
            ``connects_to`` (names of rooms reached through a doorway).
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

    Returns:
        The ``geometry`` dict sent to the Quest. Walls are pre-split around door
        and window openings (each piece's ``start.y`` is its base height); doors
        list the ``rooms`` they join and rooms list the ids they ``connects_to``.
    """
    rooms_m, rects, open_rects, layout_source = _rooms_and_rects(rooms_ft, layout)
    shared = find_shared_walls(rects)
    connections = plan_connections(rooms_m, shared)

    openings: list[dict] = []
    doors: list[dict] = []
    windows: list[dict] = []
    connected_ids: dict[int, list[int]] = {i: [] for i in range(len(rooms_m))}

    def add_door(axis: str, line: float, center: float, room_ids: list[int], door_type: str):
        openings.append({
            "axis": axis, "line": line,
            "lo": center - DOOR_W / 2, "hi": center + DOOR_W / 2,
            "bottom": 0.0, "top": DOOR_H,
        })
        doors.append({
            "id": 100 + len(doors) + 1,
            "position": _point(axis, line, center),
            "width": DOOR_W,
            "height": DOOR_H,
            "rotation": 0 if axis == "x" else 90,
            "door_type": door_type,
            "rooms": room_ids,
        })

    # Front door: on the entry's (room 0's) outside wall, street side first.
    # Spawn the player a few metres outside it.
    spawn = None
    if rects:
        front, east, back, west = _room_sides(rects[0])
        # Each side with the direction pointing out of the house, street side first.
        for side, (dx, dz) in ((front, (0, -1)), (east, (1, 0)), (west, (-1, 0)), (back, (0, 1))):
            spans = [iv for iv in exterior_intervals(side, shared) if _fits(*iv, DOOR_W)]
            if not spans:
                continue
            lo, hi = max(spans, key=lambda iv: iv[1] - iv[0])
            center = (lo + hi) / 2
            add_door(side[0], side[1], center, [1], "exterior")
            door = doors[-1]["position"]
            step = _spawn_distance(door["x"], door["z"], dx, dz, rects[1:])
            spawn = {"x": door["x"] + dx * step, "y": 1.6, "z": door["z"] + dz * step}
            break

    for a, b in connections:
        axis, line, lo, hi = shared[(a, b)]
        add_door(axis, line, (lo + hi) / 2, [a + 1, b + 1], "interior")
        connected_ids[a].append(b + 1)
        connected_ids[b].append(a + 1)

    # Bay windows, where the plan asks for them. They replace the room's ordinary window.
    bays: dict[int, dict] = {}
    for idx, (room, rect) in enumerate(zip(rooms_m, rects)):
        spec = bay_spec(room)
        if spec is None:
            continue
        obstacles = [r for j, r in enumerate(rects) if j != idx] + [b["bounds"] for b in bays.values()]
        bay = build_bay(
            rect, spec, room["dimensions"]["height"], openings, shared, obstacles,
            room.get("floor_material", "carpet"), room.get("wall_material", "drywall"),
        )
        if bay is None:
            logger.info(f"  ↪ '{room.get('name')}': no room for a {spec['side']} bay window — skipped")
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
    for idx, (room, rect) in enumerate(zip(rooms_m, rects)):
        name = _normalize(room.get("name", ""))
        if idx in bays or any(k in name for k in _NO_WINDOW_KEYWORDS):
            continue
        win_w = SMALL_WINDOW_W if any(k in name for k in _SMALL_WINDOW_KEYWORDS) else WINDOW_W
        best = None
        for side in _room_sides(rect):
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
            continue
        axis, line, f_lo, f_hi = best
        center = (f_lo + f_hi) / 2
        openings.append({
            "axis": axis, "line": line,
            "lo": center - win_w / 2, "hi": center + win_w / 2,
            "bottom": WINDOW_SILL, "top": WINDOW_SILL + WINDOW_H,
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
            f"{geom_dims['length']:.2f}x{geom_dims['width']:.2f}x{geom_dims['height']}m "
            f"@ ({x_offset:.2f}, 0, {z_offset:.2f}) → doors to {connected_ids[idx]}"
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

    return {
        "project_id": project_id,
        "project_name": project_name,
        "rooms": rooms_out,
        "doors": doors,
        "windows": windows,
        "materials": material_map,
        # Outdoor parts of the footprint (an L/U/T-shaped house), for drawing the plan.
        "open_areas": [{"bounds": {k: round(v, 4) for k, v in r.items()}} for r in open_rects],
        # Outside the front door (or in front of the entry if it had no room for one).
        "spawn_position": spawn or {
            "x": rooms_out[0]["position"]["x"] if rooms_out else 0.0,
            "y": 1.6,
            "z": -3.0,
        },
        "metadata": {
            "total_rooms": len(rooms_out),
            "total_doors": len(doors),
            "total_windows": len(windows),
            "layout": layout_source,
            "platform": target_platform,
            "optimized": optimize_for_vr,
        },
    }
