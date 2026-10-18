"""Plants for the yard, built from triangles instead of single spheres.

A landscape item names what grows there (``"plant": "coral rose"``, ``"Japanese
maple"``, ``"boxwood"``); ``find_species`` matches that against ``SPECIES``, and
color words in it ("coral", "white") tint the flowers. Each species has a
``form`` (tree, conifer, palm, shrub, grass, rosette, foliage, cactus, perennial,
rock) whose builder makes a low-poly mesh: lumpy faceted canopies in several
shades, tapered trunks and branches, leaf strips, and flowers shaped by
``style`` (rose cups, hydrangea heads, lilac cones, lavender spikes, ...).

Trees and shrubs are drawn as instances: a few variants of each mesh, built in a
unit box (x and z in [-0.5, 0.5], y in [0, 1]) and scaled to each plant's width
and height. Flower beds and hedges are one mesh each, in metres. A mesh is a set
of color groups, each a flat list of triangles (one winding, xyz per corner);
the headset adds the back faces and flat normals. Nothing here is a file: the
description is all that is stored.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

Vec = tuple[float, float, float]


# --- Species -------------------------------------------------------------------

@dataclass(frozen=True)
class Species:
    form: str  # which builder makes it
    height: float  # feet, when the plan gives none
    width: float
    leaf: str
    flower: str | None = None
    style: str | None = None  # how its flowers look
    shape: str = ""  # a variation of the form
    bark: str = "#6b4a2b"
    category: str = "shrub"  # the landscape type it stands for


def _tree(h, w, leaf, flower=None, style=None, shape="round", bark="#6b4a2b"):
    return Species("tree", h, w, leaf, flower, style, shape, bark, "tree")


def _shrub(h, w, leaf, flower=None, style=None, shape="dense"):
    return Species("shrub", h, w, leaf, flower, style, shape)


SPECIES: dict[str, Species] = {
    # Trees
    "shade tree": _tree(16, 12, "#3f7d32"),
    "oak": _tree(25, 25, "#3d6b2a", shape="spreading"),
    "maple": _tree(25, 20, "#4a7d2c"),
    "red maple": _tree(25, 20, "#a63a2a"),
    "japanese maple": _tree(12, 12, "#9c2f24", shape="spreading", bark="#5a3f30"),
    "birch": _tree(25, 12, "#6f9a3a", shape="clump", bark="#e8e4da"),
    "cherry": _tree(18, 18, "#5b8a3a", "#f4b6c8", "blossom", shape="spreading", bark="#5a3a2e"),
    "dogwood": _tree(15, 15, "#4f7f35", "#f4f1ea", "blossom", shape="spreading"),
    "magnolia": _tree(20, 15, "#2f5a2a", "#f3e1e6", "cup"),
    "crape myrtle": _tree(15, 12, "#4f7a35", "#d94f8a", "blossom", shape="clump", bark="#a58d78"),
    "redbud": _tree(18, 18, "#5b8a3a", "#c65b9b", "blossom", shape="spreading"),
    "jacaranda": _tree(25, 25, "#4f8a3a", "#8e6fc6", "blossom", shape="spreading"),
    "willow": _tree(30, 30, "#8aa64a", shape="weeping", bark="#5c4a35"),
    "olive": _tree(15, 15, "#7d8c63", shape="clump", bark="#6e6355"),
    "lemon tree": _tree(12, 10, "#2f6b2a", "#f2d40c", "fruit"),
    "orange tree": _tree(12, 10, "#2f6b2a", "#f2900c", "fruit"),
    "apple tree": _tree(15, 15, "#4a7d2c", "#c0392b", "fruit", shape="spreading"),
    # Conifers
    "pine": Species("conifer", 25, 12, "#2e5a33", shape="tiered", category="pine"),
    "spruce": Species("conifer", 25, 12, "#2f5536", shape="dense", category="pine"),
    "blue spruce": Species("conifer", 25, 12, "#5b7f86", shape="dense", category="pine"),
    "fir": Species("conifer", 30, 12, "#2b4f30", shape="dense", category="pine"),
    "cedar": Species("conifer", 30, 15, "#3a5f34", shape="dense", category="pine"),
    "cypress": Species("conifer", 30, 5, "#2c4a2a", shape="columnar", category="pine"),
    "arborvitae": Species("conifer", 15, 5, "#3a5f2e", shape="columnar", category="pine"),
    "juniper": Species("conifer", 6, 4, "#3f6247", shape="dense"),
    # Palms
    "palm": Species("palm", 18, 10, "#4f8a3a", bark="#8b6d4a", category="palm"),
    "coconut palm": Species("palm", 30, 14, "#5a9a3e", shape="curved", bark="#8b7356", category="palm"),
    "date palm": Species("palm", 20, 14, "#5b7f45", shape="thick", bark="#7a5f42", category="palm"),
    "fan palm": Species("palm", 35, 9, "#58803e", shape="tall", bark="#8b6d4a", category="palm"),
    "sago palm": Species("palm", 4, 5, "#2f5a2a", shape="sago", bark="#5c4a2e"),
    # Shrubs
    "shrub": _shrub(3, 3, "#4f7a35"),
    "boxwood": _shrub(3, 3, "#3e6a2e"),
    "rose": _shrub(4, 3.5, "#3f6b2e", "#d6336c", "rose", "airy"),
    "hydrangea": _shrub(4, 4.5, "#4c7a34", "#8aa9dc", "mophead"),
    "azalea": _shrub(4, 4, "#3d6330", "#e0457b", "blossom"),
    "rhododendron": _shrub(6, 5, "#2f5528", "#b05fb0", "mophead"),
    "gardenia": _shrub(4, 4, "#2e5527", "#f6f3ea", "rose"),
    "camellia": _shrub(8, 6, "#2a4d25", "#d94f6a", "rose"),
    "lilac": _shrub(8, 6, "#4c7a34", "#b49ad6", "panicle", "airy"),
    "holly": _shrub(6, 4, "#23401f", "#b3202a", "fruit"),
    "forsythia": _shrub(6, 6, "#6b8f3a", "#f2c81e", "blossom", "airy"),
    "bougainvillea": _shrub(8, 8, "#3f6b2e", "#c2185b", "blossom", "airy"),
    "hibiscus": _shrub(6, 5, "#2f5a2a", "#d6283a", "star"),
    "oleander": _shrub(8, 6, "#3a5f34", "#e88aa8", "blossom", "airy"),
    # Grasses and low plants
    "lavender": Species("grass", 2, 2.5, "#8a9a7a", "#8e6fc6", "spike", "lavender"),
    "rosemary": Species("grass", 3, 3, "#5f7a5a", "#8fa6d6", "spike", "lavender"),
    "ornamental grass": Species("grass", 3, 3, "#8a9a4a"),
    "pampas grass": Species("grass", 8, 6, "#8a9a5a", "#efe6cf", "plume"),
    "fountain grass": Species("grass", 3, 3, "#9aa25a", "#c9b38a", "plume"),
    "hosta": Species("foliage", 1.5, 3, "#4f8a3a", shape="hosta"),
    "fern": Species("foliage", 2.5, 3, "#4f8a2e", shape="fern"),
    "agave": Species("rosette", 3, 4, "#7a9a8a"),
    "yucca": Species("rosette", 4, 3, "#5a7a4a", shape="yucca"),
    "aloe": Species("rosette", 2, 2, "#6f8f5a"),
    "succulent": Species("rosette", 0.8, 1.2, "#7aa58a"),
    "cactus": Species("cactus", 8, 3, "#4f7a45"),
    "barrel cactus": Species("cactus", 2, 2, "#4f7a45", "#f2c81e", "star", "barrel"),
    # Flowers (also what flower beds are planted with)
    "flowers": Species("perennial", 1.2, 1.2, "#4f7a35", None, "daisy"),
    "tulip": Species("perennial", 1.5, 0.8, "#5f8a45", "#d6283a", "tulip"),
    "daisy": Species("perennial", 1.5, 1.2, "#4f7a35", "#f4f4f0", "daisy"),
    "sunflower": Species("perennial", 6, 2, "#4f7a35", "#f5c518", "sunflower"),
    "marigold": Species("perennial", 1, 1, "#4f7a35", "#f08c2e", "mophead"),
    "petunia": Species("perennial", 1, 1.5, "#4f7a35", "#c2185b", "star"),
    "geranium": Species("perennial", 1.5, 1.2, "#4f7a35", "#d6283a", "mophead"),
    "black eyed susan": Species("perennial", 2, 1.5, "#4f7a35", "#f2b01e", "daisy"),
    "coneflower": Species("perennial", 3, 1.5, "#4f7a35", "#c86a9a", "daisy"),
    "peony": Species("perennial", 3, 3, "#3f6b2e", "#f3a6b8", "rose"),
    "lily": Species("perennial", 3, 1.5, "#4f7a35", "#f08c2e", "star"),
    "iris": Species("perennial", 2.5, 1.5, "#5f8a5a", "#6a5acd", "tulip"),
    "pansy": Species("perennial", 0.6, 0.8, "#4f7a35", "#7d5ba6", "star"),
    "rock": Species("rock", 1.5, 2.5, "#8a8580", category="rock"),
}

_ALIASES = {
    "tree": "shade tree", "elm": "shade tree", "ash": "shade tree", "linden": "shade tree",
    "sycamore": "shade tree", "poplar": "birch", "aspen": "birch", "cherry blossom": "cherry",
    "flowering cherry": "cherry", "sakura": "cherry", "crepe myrtle": "crape myrtle",
    "weeping willow": "willow", "lemon": "lemon tree", "orange": "orange tree", "citrus": "orange tree",
    "apple": "apple tree", "fruit tree": "apple tree", "maple tree": "maple", "oak tree": "oak",
    "evergreen": "spruce", "conifer": "spruce", "christmas tree": "fir", "italian cypress": "cypress",
    "leyland cypress": "cypress", "thuja": "arborvitae", "palm tree": "palm", "queen palm": "palm",
    "royal palm": "fan palm", "washingtonia": "fan palm", "canary palm": "date palm",
    "bush": "shrub", "hedge plant": "boxwood", "privet": "boxwood", "laurel": "boxwood",
    "photinia": "boxwood", "knock out rose": "rose", "rose bush": "rose", "rosebush": "rose",
    "camelia": "camellia", "grass": "ornamental grass", "mondo grass": "ornamental grass",
    "blue fescue": "ornamental grass", "pampas": "pampas grass", "saguaro": "cactus", "cacti": "cactus",
    "flower": "flowers", "wildflower": "flowers", "perennial": "flowers", "annual": "flowers",
    "black-eyed susan": "black eyed susan", "echinacea": "coneflower", "daylily": "lily",
    "boulder": "rock", "stone": "rock",
}

# Extra color words for flowers (vr_exterior.NAMED_COLORS has the rest).
FLOWER_COLORS = {
    "coral": "#f88379", "salmon": "#fa8072", "peach": "#ffb38a", "apricot": "#fbceb1",
    "blush": "#f3c4c8", "magenta": "#c2185b", "fuchsia": "#d1338f", "hot pink": "#e0457b",
    "crimson": "#b0172f", "scarlet": "#d1242a", "lilac": "#c8a2c8", "violet": "#7f4fb3",
    "mauve": "#c08aa8", "golden": "#e8b923",
}
MIXED_FLOWERS = ("#d6336c", "#f5c518", "#f08c2e", "#f4f4f0", "#9b59b6")
_DEFAULT_BY_TYPE = {"tree": "shade tree", "pine": "pine", "palm": "palm", "shrub": "shrub", "rock": "rock"}


def _singular(word: str) -> str:
    if len(word) <= 3:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("sses") or word.endswith(("ches", "shes", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def name_key(text: Any) -> str:
    """Lower-case singular words: "Coral Roses" and "coral rose" give the same key."""
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return " ".join(_singular(w) for w in words)


@lru_cache(maxsize=1)
def _lookup() -> list[tuple[str, str]]:
    names = {name_key(name): name for name in SPECIES}
    names.update({name_key(alias): target for alias, target in _ALIASES.items()})
    return sorted(names.items(), key=lambda kv: -len(kv[0]))


def find_species(text: Any) -> str | None:
    """The species a description names ("two coral Knock Out roses" → rose), or None."""
    key = f" {name_key(text)} "
    for alias, species in _lookup():
        if f" {alias} " in key:
            return species
    return None


def _color_word(text: Any, named: dict[str, str]) -> str | None:
    words = name_key(text)
    colors = {**named, **FLOWER_COLORS}
    for name in sorted(colors, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name_key(name))}\b", words):
            return colors[name]
    return None


def resolve(item: dict, named_colors: dict[str, str]) -> tuple[str, str, str | None]:
    """``(species, leaf color, flower color)`` for a landscape item."""
    text = item.get("plant") or item.get("label") or ""
    species = find_species(text) or find_species(item.get("label")) or _DEFAULT_BY_TYPE.get(item["type"], "shrub")
    if item["type"] == "flower_bed" and SPECIES[species].form != "perennial":
        species = "flowers"
    sp = SPECIES[species]
    leaf = sp.leaf
    flower = item.get("flower_color") or sp.flower
    # "coral rose", "white hydrangea": the color tints the flowers (the leaves when it has none).
    word = _color_word(text, named_colors)
    if word and not item.get("flower_color"):
        if sp.flower or sp.form == "perennial":
            flower = word
        elif sp.form != "rock":
            leaf = word
    if item.get("color"):
        if item["type"] == "flower_bed":
            flower = item["color"]  # a flower bed's color is its flowers'
        else:
            leaf = item["color"]
    return species, leaf, flower


# --- Colors ------------------------------------------------------------------------

def _shade(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    parts = [min(255, max(0, round(int(h[i:i + 2], 16) * factor))) for i in (0, 2, 4)]
    return "#" + "".join(f"{p:02x}" for p in parts)


def _shades(hex_color: str, factors=(0.72, 0.88, 1.04)) -> list[str]:
    """Dark to light: lower and inner faces darker, tops lighter."""
    return [_shade(hex_color, f) for f in factors]


def _rgb(hex_color: str) -> dict:
    h = hex_color.lstrip("#")
    return {k: round(int(h[i:i + 2], 16) / 255, 3) for k, i in (("r", 0), ("g", 2), ("b", 4))}


# --- Mesh building ------------------------------------------------------------------

class PlantMesh:
    """Triangles grouped by color."""

    def __init__(self):
        self.groups: dict[str, list[Vec]] = {}

    def tri(self, color: str, a: Vec, b: Vec, c: Vec):
        self.groups.setdefault(color, []).extend((a, b, c))

    def quad(self, color: str, a: Vec, b: Vec, c: Vec, d: Vec):
        self.tri(color, a, b, c)
        self.tri(color, a, c, d)

    @property
    def triangles(self) -> int:
        return sum(len(p) for p in self.groups.values()) // 3

    def _points(self):
        return (p for pts in self.groups.values() for p in pts)

    def normalize(self):
        """Fit into the unit box: y from 0 to 1, x and z within ±0.5 (the
        footprint keeps its proportions)."""
        pts = list(self._points())
        if not pts:
            return self
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        z0, z1 = min(p[2] for p in pts), max(p[2] for p in pts)
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        sxz = 1.0 / max(x1 - x0, z1 - z0, 1e-6)
        sy = 1.0 / max(y1 - y0, 1e-6)
        for color, pts in self.groups.items():
            self.groups[color] = [((x - cx) * sxz, (y - y0) * sy, (z - cz) * sxz) for x, y, z in pts]
        return self

    def out(self, digits: int = 3) -> dict:
        return {
            "groups": [
                {"color": _rgb(color), "positions": [round(v, digits) for p in pts for v in p]}
                for color, pts in self.groups.items() if pts
            ]
        }


def _add(a: Vec, b: Vec) -> Vec:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec, b: Vec) -> Vec:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(a: Vec, s: float) -> Vec:
    return a[0] * s, a[1] * s, a[2] * s


def _cross(a: Vec, b: Vec) -> Vec:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _unit(a: Vec) -> Vec:
    n = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)
    return (0.0, 1.0, 0.0) if n < 1e-9 else (a[0] / n, a[1] / n, a[2] / n)


def _basis(axis: Vec) -> tuple[Vec, Vec]:
    """Two unit vectors at right angles to ``axis`` and each other."""
    axis = _unit(axis)
    ref = (1.0, 0.0, 0.0) if abs(axis[1]) > 0.9 else (0.0, 1.0, 0.0)
    u = _unit(_cross(axis, ref))
    return u, _cross(axis, u)


def _direction(yaw: float, pitch: float) -> Vec:
    """Unit vector turned ``yaw`` radians around y, raised ``pitch`` radians above level."""
    return math.cos(pitch) * math.cos(yaw), math.sin(pitch), math.cos(pitch) * math.sin(yaw)


@lru_cache(maxsize=4)
def _icosphere(subdiv: int) -> tuple[tuple[Vec, ...], tuple[tuple[int, int, int], ...]]:
    t = (1 + math.sqrt(5)) / 2
    verts = [_unit(v) for v in (
        (-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
        (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1),
    )]
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4),
        (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8),
        (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    for _ in range(subdiv):
        cache: dict[tuple[int, int], int] = {}

        def mid(i: int, j: int) -> int:
            key = (min(i, j), max(i, j))
            if key not in cache:
                cache[key] = len(verts)
                verts.append(_unit(_mul(_add(verts[i], verts[j]), 0.5)))
            return cache[key]

        faces = [
            f for a, b, c in faces
            for ab, bc, ca in [(mid(a, b), mid(b, c), mid(c, a))]
            for f in ((a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca))
        ]
    return tuple(verts), tuple(faces)


def blob(mesh: PlantMesh, rng: random.Random, center: Vec, radius: Vec, shades: list[str],
         subdiv: int = 1, bump: float = 0.18, flatten: float | None = None, mottle: float = 0.3):
    """A lumpy faceted ball: tops in the lighter shades, undersides darker.
    ``flatten`` cuts the bottom off at that fraction of the y radius (rocks)."""
    verts, faces = _icosphere(subdiv)
    pts = []
    for v in verts:
        d = 1 + rng.uniform(-bump, bump)
        y = v[1] * radius[1] * d
        if flatten is not None:
            y = max(y, -radius[1] * flatten)
        pts.append((center[0] + v[0] * radius[0] * d, center[1] + y, center[2] + v[2] * radius[2] * d))
    n = len(shades)
    for a, b, c in faces:
        up = (verts[a][1] + verts[b][1] + verts[c][1]) / 3
        t = (up + 1) / 2 + rng.uniform(-mottle, mottle)
        mesh.tri(shades[min(n - 1, max(0, int(t * n)))], pts[a], pts[b], pts[c])


def tube(mesh: PlantMesh, color: str, a: Vec, b: Vec, r0: float, r1: float, sides: int = 6,
         cap: bool = False):
    """A tapered tube from ``a`` (radius ``r0``) to ``b`` (radius ``r1``)."""
    u, v = _basis(_sub(b, a))
    ring0, ring1 = [], []
    for k in range(sides):
        ang = 2 * math.pi * k / sides
        off = _add(_mul(u, math.cos(ang)), _mul(v, math.sin(ang)))
        ring0.append(_add(a, _mul(off, r0)))
        ring1.append(_add(b, _mul(off, r1)))
    for k in range(sides):
        j = (k + 1) % sides
        mesh.quad(color, ring0[k], ring0[j], ring1[j], ring1[k])
    if cap and r1 > 0:
        for k in range(sides):
            mesh.tri(color, b, ring1[k], ring1[(k + 1) % sides])


def leaf(mesh: PlantMesh, color: str, base: Vec, direction: Vec, length: float, width: float,
         droop: float = 0.3, segments: int = 4, serrate: float = 0.0, fold: float = 0.0,
         shape: str = "lance"):
    """A leaf, blade or frond as a strip bending under its own weight.

    ``shape``: "lance" (widest past the base, pointed), "blade" (narrowing all the
    way), "oval" (round-ended). ``serrate`` notches the edges (feathery fronds),
    ``fold`` raises the midrib (thick agave leaves)."""
    direction = _unit(direction)
    side = _unit(_cross(direction, (0.0, 1.0, 0.0)))
    if abs(direction[1]) > 0.98:
        side = (1.0, 0.0, 0.0)
    normal = _unit(_cross(side, direction))
    spine = []
    for i in range(segments + 1):
        s = i / segments
        p = _add(base, _mul(direction, length * s))
        spine.append((p[0], p[1] - droop * length * s * s, p[2]))
    rows = []
    for i, p in enumerate(spine):
        s = i / segments
        if shape == "blade":
            w = width * (1 - s) ** 0.8
        elif shape == "oval":
            w = width * math.sin(math.pi * min(1.0, 0.12 + s * 0.88)) ** 0.6
        else:
            w = width * math.sin(math.pi * min(1.0, 0.15 + s * 0.85))
        if serrate and 0 < i < segments:
            w *= 1.0 if i % 2 else (1 - serrate)
        half = w / 2
        rows.append((_add(p, _mul(side, -half)), _add(p, _mul(normal, fold * w)), _add(p, _mul(side, half))))
    for i in range(segments):
        l0, m0, r0 = rows[i]
        l1, m1, r1 = rows[i + 1]
        if fold:
            mesh.quad(color, l0, m0, m1, l1)
            mesh.quad(color, m0, r0, r1, m1)
        else:
            mesh.quad(color, l0, r0, r1, l1)


def cone(mesh: PlantMesh, shades: list[str], base: Vec, radius: float, height: float,
         rng: random.Random, points: int = 10, jag: float = 0.3):
    """A star-edged cone (a conifer tier): a ring of jagged points rising to the apex."""
    apex = (base[0], base[1] + height, base[2])
    ring = []
    turn = rng.uniform(0, math.pi)
    for k in range(points * 2):
        ang = turn + math.pi * k / points
        r = radius * (1.0 if k % 2 == 0 else 1 - jag) * rng.uniform(0.9, 1.1)
        dip = -height * 0.08 if k % 2 == 0 else 0.0  # the tips droop
        ring.append((base[0] + r * math.cos(ang), base[1] + dip, base[2] + r * math.sin(ang)))
    under = (base[0], base[1] + height * 0.15, base[2])
    n = len(ring)
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        mesh.tri(shades[1 + (k % 2) * (len(shades) - 2)], a, b, apex)
        mesh.tri(shades[0], b, a, under)


# --- Flowers ----------------------------------------------------------------------

def flower(mesh: PlantMesh, rng: random.Random, style: str, at: Vec, normal: Vec, size: float,
           shades: list[str], center: str):
    """One flower head of ``style`` at ``at``, facing ``normal``, about ``size`` across."""
    u, v = _basis(normal)
    up = _unit(normal)

    def ring_point(ang: float, r: float, rise: float) -> Vec:
        off = _add(_mul(u, math.cos(ang) * r), _mul(v, math.sin(ang) * r))
        return _add(_add(at, off), _mul(up, rise))

    turn = rng.uniform(0, 2 * math.pi)
    if style in ("rose", "cup"):
        # Two rings of cupped petals around a tight middle.
        rings = ((5, 0.5, 0.18, 0), (4, 0.32, 0.3, 1), (3, 0.18, 0.38, 2)) if style == "rose" else ((6, 0.5, 0.45, 1),)
        for count, r, rise, shade in rings:
            for k in range(count):
                a0 = turn + 2 * math.pi * k / count + shade * 0.6
                a1 = a0 + 2 * math.pi / count * 1.2
                base0 = ring_point(a0, r * 0.25 * size, 0)
                base1 = ring_point(a1, r * 0.25 * size, 0)
                tip0 = ring_point(a0, r * size, rise * size)
                tip1 = ring_point(a1, r * size, rise * size)
                mesh.quad(shades[min(shade, len(shades) - 1)], base0, base1, tip1, tip0)
        return
    if style in ("daisy", "star", "sunflower"):
        petals = {"daisy": 10, "star": 5, "sunflower": 14}[style]
        r = size * 0.5
        for k in range(petals):
            ang = turn + 2 * math.pi * k / petals
            w = math.pi / petals * (0.9 if style == "star" else 0.5)
            mesh.tri(shades[k % 2 + 1], ring_point(ang - w, r * 0.2, 0.02 * size),
                     ring_point(ang, r, -0.05 * size if style != "star" else 0.1 * size),
                     ring_point(ang + w, r * 0.2, 0.02 * size))
        disc = r * (0.45 if style == "sunflower" else 0.25)
        dark = "#5a3a1e" if style == "sunflower" else center
        for k in range(6):
            a0, a1 = turn + math.pi * k / 3, turn + math.pi * (k + 1) / 3
            mesh.tri(dark, ring_point(a0, disc, 0.04 * size), ring_point(a1, disc, 0.04 * size),
                     ring_point(0, 0, 0.08 * size))
        return
    if style == "tulip":
        for k in range(5):
            a0 = turn + 2 * math.pi * k / 5
            a1 = a0 + 2 * math.pi / 5 * 1.3
            mesh.quad(shades[k % 2 + 1], ring_point(a0, size * 0.15, 0), ring_point(a1, size * 0.15, 0),
                      ring_point(a1, size * 0.3, size * 0.8), ring_point(a0, size * 0.3, size * 0.8))
        return
    if style == "panicle":
        radius = size * 0.35
        tip = _add(at, _mul(up, size * 1.3))
        for k in range(6):
            a0, a1 = turn + math.pi * k / 3, turn + math.pi * (k + 1) / 3
            mesh.tri(shades[k % len(shades)], ring_point(a0, radius, 0), ring_point(a1, radius, 0), tip)
        return
    if style == "spike":
        for j in range(4):  # little whorls up a stem
            c = _add(at, _mul(up, size * 0.3 * j))
            blob(mesh, rng, c, (size * 0.12, size * 0.16, size * 0.12), shades, subdiv=0, bump=0.1)
        return
    if style == "plume":
        tip = _add(at, _mul(up, size * 1.6))
        for k in range(5):
            a0, a1 = turn + 2 * math.pi * k / 5, turn + 2 * math.pi * (k + 1) / 5
            mid = ring_point(0, 0, size * 0.55)
            p0 = _add(mid, _add(_mul(u, math.cos(a0) * size * 0.2), _mul(v, math.sin(a0) * size * 0.2)))
            p1 = _add(mid, _add(_mul(u, math.cos(a1) * size * 0.2), _mul(v, math.sin(a1) * size * 0.2)))
            mesh.tri(shades[k % len(shades)], at, p1, p0)
            mesh.tri(shades[(k + 1) % len(shades)], p0, p1, tip)
        return
    # mophead, blossom, fruit: round clusters
    scale = {"mophead": 0.5, "blossom": 0.3, "fruit": 0.28}.get(style, 0.35) * size
    blob(mesh, rng, _add(at, _mul(up, scale * 0.3)), (scale, scale * 0.9, scale), shades,
         subdiv=1 if style == "mophead" else 0, bump=0.12 if style != "fruit" else 0.03)


def _surface_point(rng: random.Random, center: Vec, radius: Vec, min_up: float = -0.1) -> tuple[Vec, Vec]:
    """A random point on an ellipsoid's upper part, and the way it faces."""
    while True:
        d = _unit((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
        if d[1] >= min_up:
            break
    p = (center[0] + d[0] * radius[0], center[1] + d[1] * radius[1], center[2] + d[2] * radius[2])
    return p, d


def _flowers_on(mesh: PlantMesh, rng: random.Random, clumps: list[tuple[Vec, Vec]], sp: Species,
                flower_color: str, count: int, size: float, min_up: float = -0.1):
    shades = _shades(flower_color, (0.82, 0.95, 1.08))
    center = _shade(flower_color, 0.7) if sp.style != "daisy" else "#e8b923"
    for _ in range(count):
        c, r = clumps[rng.randrange(len(clumps))]
        p, n = _surface_point(rng, c, (r[0] * 0.97, r[1] * 0.97, r[2] * 0.97), min_up)
        flower(mesh, rng, sp.style or "blossom", p, n, size * rng.uniform(0.8, 1.2), shades, center)


# --- Forms --------------------------------------------------------------------------
# Each builds one plant about 1 unit tall; PlantMesh.normalize fits it to the unit box.

def _tree_form(mesh: PlantMesh, rng: random.Random, sp: Species, leaf_color: str, flower_color: str | None):
    shades = _shades(leaf_color)
    bark = sp.bark
    shape = sp.shape
    if shape == "spreading":
        trunk_h, canopy_c, canopy_r = 0.38, (0, 0.66, 0), (0.62, 0.3, 0.62)
    elif shape == "weeping":
        trunk_h, canopy_c, canopy_r = 0.5, (0, 0.72, 0), (0.5, 0.28, 0.5)
    elif shape == "clump":
        trunk_h, canopy_c, canopy_r = 0.45, (0, 0.68, 0), (0.36, 0.32, 0.36)
    else:
        trunk_h, canopy_c, canopy_r = 0.4, (0, 0.64, 0), (0.42, 0.34, 0.42)

    trunks = 3 if shape == "clump" else 1
    tops = []
    for t in range(trunks):
        lean = (0.0, 0.0) if trunks == 1 else (math.cos(2 * math.pi * t / trunks + rng.uniform(-0.3, 0.3)) * 0.1,
                                               math.sin(2 * math.pi * t / trunks) * 0.1)
        top = (lean[0], trunk_h, lean[1])
        tube(mesh, bark, (lean[0] * 0.2, 0, lean[1] * 0.2), top, 0.05 / math.sqrt(trunks), 0.035 / math.sqrt(trunks), 6)
        tops.append(top)
    if bark == "#e8e4da":  # birch: dark bands
        for top in tops:
            for k in range(3):
                y = trunk_h * (0.2 + 0.25 * k)
                tube(mesh, "#3a3530", (top[0] * y / trunk_h, y, top[2] * y / trunk_h),
                     (top[0] * (y + 0.02) / trunk_h, y + 0.02, top[2] * (y + 0.02) / trunk_h), 0.04, 0.04, 6)

    # Canopy lumps on a shell around the crown, branches out to the bigger ones.
    lumps = [(canopy_c, (canopy_r[0] * 0.7, canopy_r[1] * 0.85, canopy_r[2] * 0.7))]
    n = rng.randint(7, 10)
    for k in range(n):
        ang = 2 * math.pi * k / n + rng.uniform(-0.3, 0.3)
        lift = rng.uniform(-0.55, 0.8)
        dist = math.sqrt(max(0.0, 1 - lift * lift)) * 0.75
        c = (canopy_c[0] + math.cos(ang) * canopy_r[0] * dist, canopy_c[1] + lift * canopy_r[1] * 0.8,
             canopy_c[2] + math.sin(ang) * canopy_r[2] * dist)
        s = rng.uniform(0.42, 0.58)
        lumps.append((c, (canopy_r[0] * s, canopy_r[1] * s * 1.1, canopy_r[2] * s)))
    for c, _ in lumps[1:][:5]:
        top = tops[rng.randrange(len(tops))]
        tube(mesh, bark, top, _add(top, _mul(_sub(c, top), 0.75)), 0.025, 0.012, 5)
    blossom = sp.style == "blossom" and flower_color
    for c, r in lumps:
        lump_shades = shades
        if blossom and rng.random() < 0.35:  # trees in bloom show flower color right through
            lump_shades = [shades[0]] + _shades(flower_color, (0.85, 1.0))
        blob(mesh, rng, c, r, lump_shades, subdiv=1, bump=0.2)
    if shape == "weeping":
        for k in range(18):
            ang = 2 * math.pi * k / 18 + rng.uniform(-0.1, 0.1)
            base = (math.cos(ang) * canopy_r[0] * 0.85, canopy_c[1] + 0.05, math.sin(ang) * canopy_r[2] * 0.85)
            leaf(mesh, shades[k % 3], base, (math.cos(ang) * 0.25, -1.0, math.sin(ang) * 0.25),
                 rng.uniform(0.4, 0.6), 0.1, droop=0.0, segments=3, shape="blade")
    if flower_color and sp.style:
        count = {"blossom": 45, "fruit": 16, "cup": 14}.get(sp.style, 20)
        size = {"blossom": 0.07, "fruit": 0.06, "cup": 0.1}.get(sp.style, 0.08)
        _flowers_on(mesh, rng, lumps, sp, flower_color, count, size, min_up=-0.4 if sp.style == "fruit" else -0.1)


def _conifer_form(mesh: PlantMesh, rng: random.Random, sp: Species, leaf_color: str, flower_color: str | None):
    shades = _shades(leaf_color, (0.68, 0.86, 1.02))
    if sp.shape == "columnar":
        tube(mesh, sp.bark, (0, 0, 0), (0, 0.12, 0), 0.06, 0.05, 5)
        for k in range(6):
            y = 0.12 + k * 0.14
            w = 0.5 * (1 - (k / 6) ** 1.6) + 0.12
            blob(mesh, rng, (rng.uniform(-0.02, 0.02), y + 0.08, rng.uniform(-0.02, 0.02)),
                 (w * 0.5, 0.14, w * 0.5), shades, subdiv=1, bump=0.15)
        return
    tiered = sp.shape == "tiered"
    trunk_h = 0.25 if tiered else 0.1
    tube(mesh, sp.bark, (0, 0, 0), (0, 0.95, 0), 0.05, 0.015, 6)
    tiers = 5 if tiered else 7
    for k in range(tiers):
        frac = k / tiers
        y = trunk_h + (1 - trunk_h) * frac * 0.9
        r = 0.5 * (1 - frac * 0.82)
        h = (1 - trunk_h) / tiers * (1.5 if tiered else 2.0)
        cone(mesh, shades, (0, y, 0), r, h, rng, points=7 if tiered else 9, jag=0.35 if tiered else 0.25)


def _palm_form(mesh: PlantMesh, rng: random.Random, sp: Species, leaf_color: str, flower_color: str | None):
    shades = _shades(leaf_color)
    if sp.shape == "sago":
        tube(mesh, sp.bark, (0, 0, 0), (0, 0.25, 0), 0.12, 0.1, 7, cap=True)
        top, fronds, length = (0, 0.25, 0), 14, 0.55
    else:
        curve = {"curved": 0.18, "tall": 0.03, "thick": 0.02}.get(sp.shape, 0.08)
        radius = {"thick": 0.06, "tall": 0.025}.get(sp.shape, 0.035)
        lean = rng.uniform(0, 2 * math.pi)
        segments = 8
        prev = (0.0, 0.0, 0.0)
        for i in range(1, segments + 1):
            s = i / segments
            off = curve * s * s
            p = (math.cos(lean) * off, 0.82 * s, math.sin(lean) * off)
            # Ring bulges where old fronds were.
            tube(mesh, _shade(sp.bark, 0.85 if i % 2 else 1.0), prev, p, radius * (1.15 - 0.3 * s), radius * (1.05 - 0.3 * s), 6)
            prev = p
        top, fronds, length = prev, 12, 0.55
    for k in range(fronds):
        ang = 2 * math.pi * k / fronds + rng.uniform(-0.15, 0.15)
        pitch = rng.uniform(0.2, 0.7) if k % 2 else rng.uniform(-0.1, 0.35)
        leaf(mesh, shades[k % 3], top, _direction(ang, pitch), length * rng.uniform(0.85, 1.1),
             0.16, droop=0.55, segments=6, serrate=0.7, shape="lance")
    blob(mesh, rng, top, (0.05, 0.04, 0.05), [_shade(sp.bark, 0.7)], subdiv=0, bump=0.05)


def _shrub_form(mesh: PlantMesh, rng: random.Random, sp: Species, leaf_color: str, flower_color: str | None):
    shades = _shades(leaf_color)
    airy = sp.shape == "airy"
    clumps: list[tuple[Vec, Vec]] = []
    if not airy:
        clumps.append(((0, 0.45, 0), (0.42, 0.42, 0.42)))
    n = rng.randint(9, 12) if airy else rng.randint(5, 7)
    for k in range(n):
        ang = 2 * math.pi * k / n + rng.uniform(-0.4, 0.4)
        lift = rng.uniform(0.15, 0.9) if airy else rng.uniform(0.0, 0.6)
        dist = rng.uniform(0.15, 0.38) * (1.2 - lift * 0.5)
        r = rng.uniform(0.16, 0.22) if airy else rng.uniform(0.24, 0.3)
        c = (math.cos(ang) * dist, 0.1 + lift * 0.62, math.sin(ang) * dist)
        clumps.append((c, (r, r * 0.9, r)))
    if airy:  # canes from the ground up into the leaves
        stem = _shade(leaf_color, 0.55)
        for c, _ in clumps[:7]:
            tube(mesh, stem, (c[0] * 0.15, 0, c[2] * 0.15), c, 0.018, 0.01, 4)
    for c, r in clumps:
        blob(mesh, rng, c, r, shades, subdiv=1, bump=0.22)
    if flower_color and sp.style:
        count = {"rose": 22, "mophead": 9, "blossom": 40, "panicle": 14, "fruit": 18, "star": 12}.get(sp.style, 18)
        size = {"rose": 0.13, "mophead": 0.26, "blossom": 0.07, "panicle": 0.16, "fruit": 0.06, "star": 0.15}.get(sp.style, 0.1)
        _flowers_on(mesh, rng, clumps, sp, flower_color, count, size, min_up=0.0)


def _grass_form(mesh: PlantMesh, rng: random.Random, sp: Species, leaf_color: str, flower_color: str | None):
    shades = _shades(leaf_color, (0.75, 0.92, 1.08))
    lavender = sp.shape == "lavender"
    blades = 26 if lavender else 34
    length = 0.55 if lavender else 0.95
    for k in range(blades):
        ang = rng.uniform(0, 2 * math.pi)
        pitch = rng.uniform(0.9, 1.45)
        base = (math.cos(ang) * 0.05, 0, math.sin(ang) * 0.05)
        leaf(mesh, shades[k % 3], base, _direction(ang, pitch), length * rng.uniform(0.7, 1.0),
             0.05 if lavender else 0.045, droop=0.25 if lavender else 0.45, segments=4, shape="blade")
    if flower_color and sp.style:
        shades_f = _shades(flower_color, (0.85, 1.0, 1.1))
        stems = 14 if lavender else 7
        for k in range(stems):
            ang = rng.uniform(0, 2 * math.pi)
            spread = rng.uniform(0.1, 0.4)
            tip = (math.cos(ang) * spread * 0.6, rng.uniform(0.75, 0.95), math.sin(ang) * spread * 0.6)
            tube(mesh, _shade(leaf_color, 0.8), (0, 0, 0), tip, 0.008, 0.005, 3)
            flower(mesh, rng, sp.style, tip, _unit((tip[0], 0.8, tip[2])), 0.12 if lavender else 0.16,
                   shades_f, shades_f[0])


def _rosette_form(mesh: PlantMesh, rng: random.Random, sp: Species, leaf_color: str, flower_color: str | None):
    shades = _shades(leaf_color, (0.8, 0.95, 1.1))
    yucca = sp.shape == "yucca"
    base = (0, 0.35, 0) if yucca else (0, 0, 0)
    if yucca:
        tube(mesh, "#7a6a50", (0, 0, 0), base, 0.06, 0.05, 6)
    rings = ((9, 0.25, 0.9), (7, 0.7, 0.75), (5, 1.15, 0.55))
    for i, (count, pitch, length) in enumerate(rings):
        for k in range(count):
            ang = 2 * math.pi * k / count + i * 0.4 + rng.uniform(-0.1, 0.1)
            leaf(mesh, shades[(k + i) % 3], base, _direction(ang, pitch + rng.uniform(-0.1, 0.1)),
                 length * (0.6 if yucca else 0.55), 0.04 if yucca else 0.12, droop=0.05 if yucca else 0.15,
                 segments=3, fold=0.25 if not yucca else 0.0, shape="blade")


def _foliage_form(mesh: PlantMesh, rng: random.Random, sp: Species, leaf_color: str, flower_color: str | None):
    shades = _shades(leaf_color, (0.78, 0.95, 1.1))
    fern = sp.shape == "fern"
    count = 11 if fern else 13
    for k in range(count):
        ang = 2 * math.pi * k / count + rng.uniform(-0.2, 0.2)
        pitch = rng.uniform(0.6, 1.1) if fern else rng.uniform(0.35, 0.9)
        leaf(mesh, shades[k % 3], (0, 0, 0), _direction(ang, pitch),
             rng.uniform(0.8, 1.0) * (0.85 if fern else 0.6), 0.16 if fern else 0.32,
             droop=0.6 if fern else 0.45, segments=6 if fern else 4, serrate=0.75 if fern else 0.0,
             shape="lance" if fern else "oval")


def _cactus_form(mesh: PlantMesh, rng: random.Random, sp: Species, leaf_color: str, flower_color: str | None):
    shades = _shades(leaf_color, (0.8, 0.95, 1.08))
    if sp.shape == "barrel":
        blob(mesh, rng, (0, 0.45, 0), (0.45, 0.45, 0.45), shades, subdiv=1, bump=0.04, flatten=0.9)
        if flower_color:
            _flowers_on(mesh, rng, [((0, 0.45, 0), (0.45, 0.45, 0.45))], sp, flower_color, 5, 0.18, min_up=0.75)
        return
    sides = 8
    tube(mesh, shades[1], (0, 0, 0), (0, 0.92, 0), 0.1, 0.09, sides)
    blob(mesh, rng, (0, 0.92, 0), (0.09, 0.08, 0.09), shades, subdiv=0, bump=0.02)
    for k in range(rng.randint(1, 2)):
        side = 1 if k == 0 else -1
        y0 = rng.uniform(0.35, 0.5)
        elbow = (side * 0.3, y0 + 0.05, 0)
        tube(mesh, shades[0], (side * 0.05, y0, 0), elbow, 0.07, 0.07, sides)
        tip = (side * 0.3, y0 + rng.uniform(0.25, 0.35), 0)
        tube(mesh, shades[2], elbow, tip, 0.07, 0.06, sides)
        blob(mesh, rng, tip, (0.06, 0.05, 0.06), shades, subdiv=0, bump=0.02)


def _perennial_form(mesh: PlantMesh, rng: random.Random, sp: Species, leaf_color: str, flower_color: str | None):
    shades = _shades(leaf_color)
    colors = [flower_color] if flower_color else list(MIXED_FLOWERS)
    if sp.style == "sunflower":
        for k in range(3):
            ang = 2 * math.pi * k / 3
            tip = (math.cos(ang) * 0.12, rng.uniform(0.85, 1.0), math.sin(ang) * 0.12)
            tube(mesh, shades[0], (math.cos(ang) * 0.04, 0, math.sin(ang) * 0.04), tip, 0.02, 0.015, 4)
            for j in range(2):
                leaf(mesh, shades[1], _mul(tip, 0.4 + 0.25 * j), _direction(ang + j * 2.5, 0.2), 0.25, 0.14,
                     droop=0.4, segments=3, shape="oval")
            facing = _unit((math.cos(ang) * 0.6, 0.5, math.sin(ang) * 0.6))
            fs = _shades(colors[0], (0.9, 1.0, 1.08))
            flower(mesh, rng, "sunflower", tip, facing, 0.35, fs, fs[0])
        return
    # A low mound of leaves with flowers on short stems.
    for k in range(rng.randint(2, 3)):
        ang = rng.uniform(0, 2 * math.pi)
        c = (math.cos(ang) * 0.15, 0.22, math.sin(ang) * 0.15)
        blob(mesh, rng, c, (0.3, 0.22, 0.3), shades, subdiv=0, bump=0.2)
    heads = {"tulip": 5, "mophead": 4, "rose": 3}.get(sp.style or "", 6)
    for k in range(heads):
        ang = 2 * math.pi * k / heads + rng.uniform(-0.3, 0.3)
        r = rng.uniform(0.05, 0.3)
        tip = (math.cos(ang) * r, rng.uniform(0.55, 0.85), math.sin(ang) * r)
        tube(mesh, shades[0], (tip[0] * 0.3, 0.1, tip[2] * 0.3), tip, 0.015, 0.01, 3)
        color = colors[k % len(colors)]
        fs = _shades(color, (0.82, 0.95, 1.08))
        flower(mesh, rng, sp.style or "daisy", tip, _unit((tip[0], 1.0, tip[2])), 0.28, fs,
               "#e8b923" if sp.style == "daisy" else _shade(color, 0.7))


def _rock_form(mesh: PlantMesh, rng: random.Random, sp: Species, leaf_color: str, flower_color: str | None):
    shades = _shades(leaf_color, (0.75, 0.9, 1.05))
    blob(mesh, rng, (0, 0.4, 0), (0.5, 0.45, 0.42), shades, subdiv=1, bump=0.28, flatten=0.55, mottle=0.4)


FORMS = {
    "tree": _tree_form, "conifer": _conifer_form, "palm": _palm_form, "shrub": _shrub_form,
    "grass": _grass_form, "rosette": _rosette_form, "foliage": _foliage_form, "cactus": _cactus_form,
    "perennial": _perennial_form, "rock": _rock_form,
}
VARIANTS = 3


@lru_cache(maxsize=256)
def plant_mesh(species: str, variant: int, leaf_color: str, flower_color: str | None) -> PlantMesh:
    """One variant of a species in the unit box (cached: the same plant twice is one mesh)."""
    sp = SPECIES[species]
    rng = random.Random(f"{species}/{variant}")
    mesh = PlantMesh()
    FORMS[sp.form](mesh, rng, sp, leaf_color, flower_color)
    return mesh.normalize()


def _hash01(*values: float) -> float:
    """A repeatable 0..1 value for a position (same plant, same look, every rebuild)."""
    h = 0
    for v in values:
        h = (h * 1000003 + int(round(v * 1000))) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    return (h ^ (h >> 15)) / 0xFFFFFFFF


# --- Yard -----------------------------------------------------------------------------

def _point_in(mesh: PlantMesh, src: PlantMesh, at: Vec, size: Vec, yaw: float):
    """Copy a unit mesh into ``mesh`` at ``at``, scaled to ``size`` (metres), turned ``yaw`` degrees."""
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    for color, pts in src.groups.items():
        out = mesh.groups.setdefault(color, [])
        for x, y, z in pts:
            x, y, z = x * size[0], y * size[1], z * size[2]
            out.append((at[0] + x * c - z * s, at[1] + y, at[2] + x * s + z * c))


class Yard:
    """Collects the plants of one exterior: shared meshes with their instances,
    plus one baked mesh per flower bed and hedge."""

    MAX_BED_PLANTS = 30
    HEDGE_STEP = 0.9  # metres between the bushes a hedge is made of

    def __init__(self, named_colors: dict[str, str]):
        self.named = named_colors
        self.meshes: dict[str, dict] = {}
        self.plants: list[dict] = []
        self.triangles = 0

    def _mesh_id(self, species: str, variant: int, leaf: str, flower: str | None) -> str:
        key = f"{species.replace(' ', '_')}-{variant}-{leaf.lstrip('#')}" + (f"-{flower.lstrip('#')}" if flower else "")
        if key not in self.meshes:
            mesh = plant_mesh(species, variant, leaf, flower)
            self.meshes[key] = mesh.out()
            self.triangles += mesh.triangles
        return key

    def _instance(self, mesh: str, at: Vec, size: Vec, yaw: float, plan_color: str, item: dict) -> dict:
        plant = {
            "mesh": mesh,
            "position": {"x": round(at[0], 3), "y": round(at[1], 3), "z": round(at[2], 3)},
            "scale": {"x": round(size[0], 3), "y": round(size[1], 3), "z": round(size[2], 3)},
            "yaw": round(yaw, 1),
            # Seen from above on the dashboard's plan.
            "color": _rgb(plan_color),
        }
        if item.get("plant") or item.get("label"):
            plant["name"] = item.get("plant") or item.get("label")
        return plant

    def add_plant(self, item: dict, x: float, y: float, z: float, height: float | None, width: float | None):
        """A tree, shrub or rock standing at (x, y, z) metres; sizes in metres (None: the species')."""
        species, leaf, flower = resolve(item, self.named)
        sp = SPECIES[species]
        jitter = 0.92 + 0.16 * _hash01(x, z, 1)
        h = (height or sp.height * 0.3048) * (1 if height else jitter)
        w = (width or sp.width * 0.3048) * (1 if width else jitter)
        variant = int(_hash01(x, z) * VARIANTS) % VARIANTS
        mesh = self._mesh_id(species, variant, leaf, flower)
        yaw = _hash01(z, x, 2) * 360
        top = flower if flower and sp.form in ("shrub", "perennial") else leaf
        self.plants.append(self._instance(mesh, (x, y, z), (w, h, w), yaw, top, item))

    def add_bed(self, item: dict, cx: float, cz: float, length: float, width: float, yaw: float, top_y: float):
        """Flowers planted over a bed ``length`` × ``width`` metres, as one mesh."""
        species, leaf, flower = resolve(item, self.named)
        sp = SPECIES[species]
        size = min(sp.width * 0.3048, 0.6)
        h = sp.height * 0.3048
        spacing = max(size * 0.9, math.sqrt(length * width / self.MAX_BED_PLANTS))
        nu, nv = max(1, int(length / spacing)), max(1, int(width / spacing))
        colors = [flower] if flower else list(MIXED_FLOWERS)
        mesh = PlantMesh()
        r = math.radians(yaw)
        k = 0
        for i in range(nu):
            for j in range(nv):
                u = -length / 2 + (i + 0.5 + (_hash01(cx, i, j) - 0.5) * 0.4) * length / nu
                v = -width / 2 + (j + 0.5 + (_hash01(cz, j, i) - 0.5) * 0.4) * width / nv
                px, pz = cx + u * math.cos(r) - v * math.sin(r), cz + u * math.sin(r) + v * math.cos(r)
                color = colors[k % len(colors)]
                src = plant_mesh(species, k % VARIANTS, leaf, color)
                scale = 0.85 + 0.3 * _hash01(px, pz)
                _point_in(mesh, src, (px, top_y, pz), (size * scale, h * scale, size * scale), _hash01(pz, px) * 360)
                k += 1
        key = f"bed-{len(self.meshes)}"
        self.meshes[key] = mesh.out()
        self.triangles += mesh.triangles
        self.plants.append(self._instance(key, (0, 0, 0), (1, 1, 1), 0, colors[0], item))
        # The flowers of a bed are drawn on the plan by the bed itself.
        self.plants[-1]["baked"] = True

    def add_hedge(self, item: dict, a: tuple[float, float], b: tuple[float, float], y: float,
                  height: float, width: float, color: str):
        """A hedge from ``a`` to ``b`` (metres): overlapping clipped bushes, as one mesh."""
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 0.1:
            return
        ux, uz = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        yaw = math.degrees(math.atan2(uz, ux))
        count = max(1, round(length / self.HEDGE_STEP))
        step = length / count
        shades = _shades(color, (0.75, 0.9, 1.03))
        mesh = PlantMesh()
        for k in range(count):
            rng = random.Random(f"hedge/{k % 5}")
            unit = PlantMesh()
            blob(unit, rng, (0, 0.5, 0), (0.62, 0.5, 0.5), shades, subdiv=1, bump=0.1, mottle=0.35)
            unit.normalize()
            s = a[0] + ux * step * (k + 0.5), a[1] + uz * step * (k + 0.5)
            _point_in(mesh, unit, (s[0], y, s[1]), (step * 1.35, height, width), yaw)
        key = f"hedge-{len(self.meshes)}"
        self.meshes[key] = mesh.out()
        self.triangles += mesh.triangles
        plant = self._instance(key, (0, 0, 0), (1, 1, 1), 0, color, item)
        plant["baked"] = True
        # For the dashboard's plan: where it runs, metres.
        plant["line"] = {
            "from": {"x": round(a[0], 3), "z": round(a[1], 3)},
            "to": {"x": round(b[0], 3), "z": round(b[1], 3)},
            "width": round(width, 3),
        }
        self.plants.append(plant)

    def out(self) -> dict:
        return {"plant_meshes": self.meshes, "plants": self.plants}
