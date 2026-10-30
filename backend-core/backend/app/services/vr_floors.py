"""Floor finishes, metres: what a room's ``floor_material`` says it is ("white oak
hardwood", "gray 24 inch porcelain tile", "beige carpet", "polished concrete"),
drawn as a thin surface on its floor: planks in staggered rows along the room's
longer side, tiles in a grid with grout lines, or one even colour.

The result is ``{"meshes", "pieces"}`` like the furniture's (shared low-poly meshes
placed by instances, ``vr_furniture``/``MeshInstances.kt``): one mesh per floor slab.
"""

from __future__ import annotations

import random
import re
from typing import Any

from .vr_exterior import color_hex
from .vr_plants import PlantMesh, _shade

FINISH_Y = 0.027  # just over the floor slab's top (0.025)

# Kind, colour and (planks: width, tiles: size) in metres, by the first word found.
_MATERIALS: list[tuple[str, str, str, float]] = [
    ("white oak", "planks", "#c8b08a", 0.18),
    ("walnut", "planks", "#5d4330", 0.15),
    ("maple", "planks", "#d6b98c", 0.13),
    ("cherry", "planks", "#8b4a2b", 0.13),
    ("hickory", "planks", "#a57c52", 0.15),
    ("bamboo", "planks", "#c9a86b", 0.12),
    ("oak", "planks", "#b08a5a", 0.15),
    ("hardwood", "planks", "#a98764", 0.15),
    ("wood", "planks", "#a98764", 0.15),
    ("laminate", "planks", "#a98764", 0.19),
    ("vinyl", "planks", "#b39b7e", 0.18),
    ("lvp", "planks", "#b39b7e", 0.18),
    ("plank", "planks", "#a98764", 0.15),
    ("marble", "tiles", "#ece9e4", 0.6),
    ("travertine", "tiles", "#d8c7a8", 0.4),
    ("slate", "tiles", "#5a5f63", 0.4),
    ("porcelain", "tiles", "#d9d4cc", 0.45),
    ("ceramic", "tiles", "#d9d4cc", 0.3),
    ("tile", "tiles", "#d9d4cc", 0.3),
    ("stone", "tiles", "#8a8279", 0.45),
    ("brick", "tiles", "#9c5a3c", 0.2),
    ("terrazzo", "plain", "#d7d2c8", 0.0),
    ("concrete", "plain", "#9e9e9a", 0.0),
    ("cement", "plain", "#9e9e9a", 0.0),
    ("epoxy", "plain", "#8f9499", 0.0),
    ("carpet", "plain", "#a89a88", 0.0),
    ("rug", "plain", "#a89a88", 0.0),
    ("linoleum", "plain", "#c9c2b0", 0.0),
]
_DEFAULT = ("plain", "#a89a88", 0.0)  # carpet, as the plans default to


def floor_finish(material: Any) -> dict:
    """``{"kind": planks|tiles|plain, "color", "size"}`` for a floor described in words.
    A colour word ("gray", "white") tints it; "12 inch" / "24in" sizes the tiles."""
    text = " ".join(re.findall(r"[a-z0-9]+", str(material or "").lower()))
    kind, color, size = next(((k, c, s) for word, k, c, s in _MATERIALS if re.search(rf"\b{word}", text)), _DEFAULT)
    tinted = color_hex(text, "") if text else ""
    if tinted:
        color = tinted
    inches = re.search(r"\b(\d{1,2})\s*(inch|in)\b", text)
    if kind == "tiles" and inches:
        size = max(0.1, min(1.2, int(inches.group(1)) * 0.0254))
    return {"kind": kind, "color": color, "size": size}


def _quad(m: PlantMesh, color: str, x0: float, x1: float, z0: float, z1: float, y: float):
    m.quad(color, (x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0))  # facing up, as box() tops


def finish_mesh(finish: dict, w: float, d: float, seed: str) -> PlantMesh:
    """The surface of one ``w`` × ``d`` slab, centred on its middle, at y = 0."""
    m = PlantMesh()
    color, kind = finish["color"], finish["kind"]
    if kind == "plain":
        _quad(m, color, -w / 2, w / 2, -d / 2, d / 2, 0)
        return m
    rng = random.Random(seed)
    if kind == "tiles":
        size, grout = finish["size"], 0.004
        _quad(m, _shade(color, 0.7), -w / 2, w / 2, -d / 2, d / 2, 0)
        shades = [color, _shade(color, 0.96), _shade(color, 1.03)]
        x = -w / 2
        while x < w / 2 - 0.01:
            z = -d / 2
            while z < d / 2 - 0.01:
                _quad(m, rng.choice(shades), x + grout, min(x + size, w / 2) - grout,
                      z + grout, min(z + size, d / 2) - grout, 0.001)
                z += size
            x += size
        return m
    # Planks along the longer side, rows of staggered lengths, each a shade of the wood.
    along_x = w >= d
    length, across = (w, d) if along_x else (d, w)
    width = finish["size"]
    shades = [color, _shade(color, 0.9), _shade(color, 1.08), _shade(color, 0.95), _shade(color, 1.04)]
    seam = _shade(color, 0.6)
    _quad(m, seam, -w / 2, w / 2, -d / 2, d / 2, 0)
    c = -across / 2
    while c < across / 2 - 0.01:
        c1 = min(c + width, across / 2)
        a = -length / 2 - rng.uniform(0, 1.0)
        while a < length / 2:
            b = a + rng.uniform(0.8, 1.6)
            a0, a1 = max(a, -length / 2) + 0.002, min(b, length / 2) - 0.002
            if a1 > a0:
                if along_x:
                    _quad(m, rng.choice(shades), a0, a1, c + 0.002, c1 - 0.002, 0.001)
                else:
                    _quad(m, rng.choice(shades), c + 0.002, c1 - 0.002, a0, a1, 0.001)
            a = b
        c = c1
    return m


def build_finishes(rooms: list[dict]) -> dict | None:
    """The finish on every room's floor slabs (``rooms`` as built: ``id``, ``floors``,
    each slab with its ``material``)."""
    meshes: dict[str, dict] = {}
    pieces: list[dict] = []
    for room in rooms:
        for n, slab in enumerate(room.get("floors") or []):
            v = slab["vertices"]
            x0, x1 = sorted((v[0]["x"], v[2]["x"]))
            z0, z1 = sorted((v[0]["z"], v[2]["z"]))
            w, d = x1 - x0, z1 - z0
            if w < 0.05 or d < 0.05:
                continue
            finish = floor_finish(slab.get("material"))
            key = f"floor-{room['id']}-{n}-{finish['kind']}-{finish['color'].lstrip('#')}"
            meshes[key] = finish_mesh(finish, w, d, key).out()
            pieces.append({
                "room": room["id"], "type": "floor",
                "position": {"x": round((x0 + x1) / 2, 4), "y": round(v[0]["y"] + FINISH_Y, 4), "z": round((z0 + z1) / 2, 4)},
                "yaw": 0.0, "mesh": key, "scale": {"x": 1, "y": 1, "z": 1},
            })
    return {"meshes": meshes, "pieces": pieces} if pieces else None
