"""Stairs between the levels of a house, metres.

A room on one level whose name says it holds stairs ("Stairs", "Stairwell",
"Stair hall") and that has a room above it on the next level gets a straight
flight: along the room's longer side, against the wall with the fewest doors, its
foot by the room's doorways. The floor above is cut over the flight (``hole``) and
railed round. The flight is sent as a furniture piece (shared meshes, instanced by
the headset like any other); ``ramp`` tells the headset how high the steps are
where the player walks.
"""

from __future__ import annotations

import math
from typing import Any

from .vr_plants import PlantMesh, tube

STAIR_KEYWORDS = ("stair",)
RISER_MAX = 0.19  # metres per step at most
TREAD = 0.28
TREAD_MIN = 0.22  # shallower treads are a note: the room is short for its rise
STAIR_W_MAX = 1.0
RAIL_H = 0.9
TREAD_COLOR = "#a47a52"
RISER_COLOR = "#efece4"
RAIL_COLOR = "#3b2e27"


def is_stair_room(name: Any) -> bool:
    return any(k in str(name or "").lower() for k in STAIR_KEYWORDS)


def plan_stairs(rect: dict, rise: float, doors: list[dict], openings: list[dict]) -> dict:
    """Where the flight goes in ``rect`` (metres) to climb ``rise``: ``footprint``,
    the ``ramp`` (axis, the coordinate at its foot and head) and ``short`` when the
    treads had to be shallower than usual. ``doors`` are the room's door positions,
    ``openings`` every opening cut in the walls (the flight backs onto a wall without one)."""
    along = "x" if rect["x1"] - rect["x0"] >= rect["z1"] - rect["z0"] else "z"
    across = "z" if along == "x" else "x"
    a0, a1 = rect[f"{along}0"], rect[f"{along}1"]
    c0, c1 = rect[f"{across}0"], rect[f"{across}1"]
    n = max(2, math.ceil(rise / RISER_MAX))
    tread = min(TREAD, (a1 - a0 - 0.2) / n)
    run = n * tread
    width = min(STAIR_W_MAX, c1 - c0 - 0.05)
    # The foot by the doors (their mean along the long side), the flight rising away.
    mid = (a0 + a1) / 2
    door_at = [d[along] for d in doors] or [a0]
    up = 1 if sum(door_at) / len(door_at) <= mid else -1
    foot = a0 + 0.1 if up > 0 else a1 - 0.1
    head = foot + up * run

    # Against the long wall with the fewer openings in it.
    def cut(line: float) -> float:
        return sum(o["hi"] - o["lo"] for o in openings
                   if o["axis"] == along and abs(o["line"] - line) < 1e-3 and o["hi"] > a0 and o["lo"] < a1)

    side0 = cut(c0) <= cut(c1)
    s0, s1 = (c0, c0 + width) if side0 else (c1 - width, c1)
    lo, hi = min(foot, head), max(foot, head)
    footprint = {f"{along}0": lo, f"{along}1": hi, f"{across}0": s0, f"{across}1": s1}
    return {
        "footprint": {k: footprint[k] for k in ("x0", "x1", "z0", "z1")},
        "ramp": {"axis": along, "foot": round(foot, 4), "head": round(head, 4), "rise": round(rise, 4)},
        "steps": n,
        "open_side": 1 if side0 else 0,  # which across edge is away from the wall (0 = low, 1 = high)
        "short": tread < TREAD_MIN,
    }


def _box_world(m: PlantMesh, color: str, x0, x1, y0, y1, z0, z1):
    from .vr_furniture import box

    box(m, color, x0, x1, y0, y1, z0, z1)


def stair_mesh(st: dict) -> tuple[PlantMesh, tuple[float, float]]:
    """The flight as one mesh, centred on its footprint (base y = 0), and that centre."""
    fp, ramp = st["footprint"], st["ramp"]
    cx, cz = (fp["x0"] + fp["x1"]) / 2, (fp["z0"] + fp["z1"]) / 2
    along = ramp["axis"]
    n, rise = st["steps"], ramp["rise"]
    step = (ramp["head"] - ramp["foot"]) / n
    riser = rise / n
    m = PlantMesh()
    c_lo, c_hi = (fp["z0"], fp["z1"]) if along == "x" else (fp["x0"], fp["x1"])
    for k in range(n):
        a, b = sorted((ramp["foot"] + k * step, ramp["foot"] + (k + 1) * step))
        top = (k + 1) * riser
        if along == "x":
            _box_world(m, RISER_COLOR, a - cx, b - cx, 0, top - 0.03, c_lo - cz, c_hi - cz)
            _box_world(m, TREAD_COLOR, a - cx - 0.02 * (step > 0), b - cx + 0.02 * (step < 0), top - 0.03, top,
                       c_lo - cz, c_hi - cz)
        else:
            _box_world(m, RISER_COLOR, c_lo - cx, c_hi - cx, 0, top - 0.03, a - cz, b - cz)
            _box_world(m, TREAD_COLOR, c_lo - cx, c_hi - cx, top - 0.03, top,
                       a - cz - 0.02 * (step > 0), b - cz + 0.02 * (step < 0))
    # A handrail on the open side, following the slope.
    edge = c_hi if st["open_side"] else c_lo
    inset = -0.04 if st["open_side"] else 0.04
    foot, head = ramp["foot"], ramp["head"]

    def pt(a: float, y: float) -> tuple[float, float, float]:
        return (a - cx, y, edge + inset - cz) if along == "x" else (edge + inset - cx, y, a - cz)

    tube(m, RAIL_COLOR, pt(foot, RAIL_H), pt(head, rise + RAIL_H), 0.025, 0.025, 6)
    for k in range(0, n + 1, max(1, n // 4)):
        a = foot + k * step
        tube(m, RAIL_COLOR, pt(a, k * riser), pt(a, k * riser + RAIL_H), 0.018, 0.018, 5)
    return m, (cx, cz)


def railing_mesh(st: dict) -> tuple[PlantMesh, tuple[float, float]]:
    """A railing round the hole the flight comes up through, on the floor above
    (base y = 0 there): along both long sides and across the foot end; the head end
    is where the player steps off."""
    fp, ramp = st["footprint"], st["ramp"]
    cx, cz = (fp["x0"] + fp["x1"]) / 2, (fp["z0"] + fp["z1"]) / 2
    along = ramp["axis"]
    a_lo, a_hi = (fp["x0"], fp["x1"]) if along == "x" else (fp["z0"], fp["z1"])
    c_lo, c_hi = (fp["z0"], fp["z1"]) if along == "x" else (fp["x0"], fp["x1"])
    m = PlantMesh()

    def pt(a: float, c: float, y: float) -> tuple[float, float, float]:
        return (a - cx, y, c - cz) if along == "x" else (c - cx, y, a - cz)

    foot_end = a_lo if ramp["foot"] < ramp["head"] else a_hi
    runs = [((a_lo, c_lo), (a_hi, c_lo)), ((a_lo, c_hi), (a_hi, c_hi)), ((foot_end, c_lo), (foot_end, c_hi))]
    for (a0, c0), (a1, c1) in runs:
        tube(m, RAIL_COLOR, pt(a0, c0, RAIL_H), pt(a1, c1, RAIL_H), 0.025, 0.025, 6)
        length = math.hypot(a1 - a0, c1 - c0)
        posts = max(1, round(length / 0.9))
        for k in range(posts + 1):
            t = k / posts
            a, c = a0 + (a1 - a0) * t, c0 + (c1 - c0) * t
            tube(m, RAIL_COLOR, pt(a, c, 0), pt(a, c, RAIL_H), 0.018, 0.018, 5)
    return m, (cx, cz)
