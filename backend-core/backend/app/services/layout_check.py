"""What is wrong with a planner's floor plan, in words the planner can fix.

``layout_problems`` checks a ``project_structure`` (``layout`` + ``rooms``, feet) the
way ``vr_geometry_service`` will build it: rooms that overlap or leave slivers
between them, a split whose parts don't add up, rooms the layout draws at other
sizes than the room list gives, rooms missing from the layout and doorways asked
for between rooms that don't touch. ``ai_planning_service`` sends the problems back
to the planner once; whatever is left is shown with the house (``geometry.notes``).
"""

from __future__ import annotations

from typing import Any

from .vr_geometry_service import (
    DOOR_EDGE_MARGIN,
    DOOR_W,
    FT_TO_M,
    LayoutError,
    _clean_name,
    _name_list,
    _normalize,
    _walk_layout,
    find_shared_walls,
    is_rect_layout,
    layout_levels,
    rect_entries,
    rect_overlaps,
    uncovered_rects,
)

# A gap between rooms narrower than this (feet) is a mistake, not a yard or a porch.
SLIVER_FT = 3.0
# Sizes further than this from what the room list says are reported (and at least 1 ft).
SIZE_TOLERANCE = 0.15
# Parts of a split may add up to this far from its extent (and at least 1 ft).
SUM_TOLERANCE = 0.05


def _ft(metres: float) -> float:
    return round(metres / FT_TO_M, 1)


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _off(actual: float, wanted: float, tolerance: float) -> bool:
    return abs(actual - wanted) > max(1.0, tolerance * wanted)


def _split_sums(layout: dict) -> list[str]:
    """Splits whose parts' sizes don't add up to the space the tree gives them (feet)."""
    problems: list[str] = []

    def leaves(node: Any) -> list[str]:
        if not isinstance(node, dict):
            return []
        if node.get("room"):
            return [_clean_name(node["room"])]
        if node.get("open"):
            return ["open area"]
        return [n for part in node.get("parts") or [] for n in leaves(part)]

    def walk(node: Any, length: float, width: float) -> None:
        if not isinstance(node, dict) or node.get("split") not in ("x", "z"):
            return
        parts = [p for p in node.get("parts") or [] if isinstance(p, dict)]
        sizes = [_num(p.get("size")) or 0.0 for p in parts]
        total = sum(sizes)
        extent = length if node["split"] == "x" else width
        if total and _off(total, extent, SUM_TOLERANCE):
            names = [n for p in parts for n in leaves(p)]
            shown = ", ".join(names[:4]) + (", …" if len(names) > 4 else "")
            direction = "left to right" if node["split"] == "x" else "front to back"
            problems.append(
                f"The parts holding {shown} add up to {total:g} ft {direction}, "
                f"but they have {extent:g} ft (everything gets squeezed or stretched to fit)"
            )
        for part, size in zip(parts, sizes):
            share = extent * size / total if total else 0.0
            if node["split"] == "x":
                walk(part, share, width)
            else:
                walk(part, length, share)

    length, width = _num(layout.get("length")), _num(layout.get("width"))
    if length and width:
        walk(layout, length, width)
    return problems


def _between_rooms(gap: dict, entries: list[dict], axis: str) -> bool:
    """Whether rooms sit on both sides of a narrow ``gap`` across ``axis``: a slit
    between rooms, not a jog in the outside wall."""
    lo, hi = ("x0", "x1") if axis == "x" else ("z0", "z1")
    a0, a1 = ("z0", "z1") if axis == "x" else ("x0", "x1")

    def beside(edge: str, at: float) -> bool:
        return any(
            abs(e[edge] - at) < 0.01 and min(e[a1], gap[a1]) - max(e[a0], gap[a0]) > 0.01
            for e in entries
        )

    return beside(hi, gap[lo]) and beside(lo, gap[hi])


def _in_front_of_entry(entry: Any, entries: list[dict]) -> list[str]:
    """Rooms between the entry and the street (its front door would face them)."""
    if not entry:
        return []
    key = _normalize(_clean_name(entry))
    door = next((e for e in entries if _normalize(e["room"]) == key), None)
    if door is None:
        return []
    return [
        f"{e['room']} is in front of the entry ({door['room']}), between its front door and the street: "
        f"move it beside the entry or make another room the entry"
        for e in entries
        if e is not door and e["z1"] <= door["z0"] + 0.01
        and min(e["x1"], door["x1"]) - max(e["x0"], door["x0"]) > 0.5
    ]


def layout_problems(structure: Any) -> list[str]:
    """Everything wrong with ``structure``'s floor plan, most serious first; [] if it is fine."""
    if not isinstance(structure, dict):
        return []
    layout = structure.get("layout")
    rooms = [r for r in structure.get("rooms") or [] if isinstance(r, dict) and r.get("name")]
    if not isinstance(layout, dict):
        return []

    levels = layout_levels(layout)
    if len(levels) > 1:
        # Each floor on its own (the ground floor has the entry), then rooms on none.
        problems: list[str] = []
        placed_names: set[str] = set()
        for n, lay in levels.items():
            on = {_normalize(_clean_name(i.get("room") or i.get("name"))) for i in lay["rects"]}
            placed_names |= on
            found = layout_problems({"layout": lay, "rooms": [r for r in rooms if _normalize(r["name"]) in on]})
            problems += [f"Floor {n + 1}: {p}" if n else p for p in found]
        missing = [r["name"] for r in rooms if _normalize(r["name"]) not in placed_names]
        if missing:
            problems.append(f"In the room list but not in the layout (left out of the house): {', '.join(missing)}")
        return problems

    problems = []
    rect_format = is_rect_layout(layout)
    if rect_format:
        try:
            entries = rect_entries(layout)
        except LayoutError as e:
            return [f"The layout can't be built: {e}"]
        for a, b, dx, dz in rect_overlaps(entries):
            problems.append(f"{a} and {b} overlap by {dx:.1f} x {dz:.1f} ft")
        if problems:
            # Nothing else can be judged until the rooms stop overlapping.
            return problems
    else:
        problems += _split_sums(layout)

    try:
        placed, _open = _walk_layout(layout)
    except LayoutError as e:
        return problems + [f"The layout can't be built: {e}"]
    names = [_normalize(n) for n, _ in placed]
    by_name = {_normalize(r["name"]): r for r in rooms}

    if rect_format:
        for gap in uncovered_rects(entries):
            w, d = gap["x1"] - gap["x0"], gap["z1"] - gap["z0"]
            if min(w, d) < SLIVER_FT and _between_rooms(gap, entries, "x" if w < d else "z"):
                problems.append(
                    f"A {w:.1f} x {d:.1f} ft gap is left between rooms at x {gap['x0']:g}-{gap['x1']:g}, "
                    f"z {gap['z0']:g}-{gap['z1']:g} ft: move the rooms together or make one bigger"
                )

    if rect_format:
        problems += _in_front_of_entry(layout.get("entry"), entries)

    for (name, rect) in placed:
        dims = (by_name.get(_normalize(name)) or {}).get("dimensions") or {}
        wanted = sorted(v for v in (_num(dims.get("length")), _num(dims.get("width"))) if v)
        if len(wanted) != 2:
            continue
        actual = sorted((_ft(rect["x1"] - rect["x0"]), _ft(rect["z1"] - rect["z0"])))
        if any(_off(a, w, SIZE_TOLERANCE) for a, w in zip(actual, wanted)):
            problems.append(
                f"{name} is {actual[0]:g} x {actual[1]:g} ft in the layout but "
                f"{wanted[0]:g} x {wanted[1]:g} ft in the room list"
            )

    missing = [r["name"] for r in rooms if _normalize(r["name"]) not in names]
    if missing:
        problems.append(f"In the room list but not in the layout (left out of the house): {', '.join(missing)}")

    entry = layout.get("entry")
    if entry and _normalize(_clean_name(entry)) not in names:
        problems.append(f"The entry '{entry}' is not a room in the layout")

    # Doorways and open walls need the two rooms to share enough wall.
    shared = find_shared_walls([r for _, r in placed])
    reported: set[tuple[int, int]] = set()
    for i, (name, _) in enumerate(placed):
        room = by_name.get(names[i]) or {}
        for key in ("connects_to", "open_to"):
            for target in _name_list(room.get(key)):
                j = names.index(_normalize(target)) if _normalize(target) in names else None
                if j is None or j == i:
                    continue
                pair = (min(i, j), max(i, j))
                wall = shared.get(pair)
                if pair in reported or (wall and wall[3] - wall[2] >= DOOR_W + 2 * DOOR_EDGE_MARGIN):
                    continue
                reported.add(pair)
                how = "don't touch" if wall is None else f"share only {_ft(wall[3] - wall[2]):g} ft of wall"
                problems.append(f"{name} and {placed[j][0]} {how}, so there can't be a doorway between them")
    return problems
