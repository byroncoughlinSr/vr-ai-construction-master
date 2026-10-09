"""Shared VR geometry builder used by both project-backed and prompt-backed
VR endpoints.

Lifted from the inline code in ``app/api/v1/projects.py`` so the new
``POST /planning/generate-vr-from-prompt`` endpoint and the existing
``GET /projects/{id}/generate-vr`` endpoint share one implementation.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


WALL_T = 0.1  # Half wall thickness — matches Box(..., 0.1f) in HouseGenerator.kt
FT_TO_M = 0.3048  # AI returns dimensions in feet; VR world uses metres (1 unit = 1 m)


def ft_to_m_dims(dims: dict) -> dict:
    """Convert a dimensions dict from feet to metres."""
    return {
        "length": round(dims.get("length", 15.0) * FT_TO_M, 3),
        "width": round(dims.get("width", 12.0) * FT_TO_M, 3),
        "height": round(dims.get("height", 9.0) * FT_TO_M, 3),
    }


def compute_packed_positions(rooms: list, max_cols: int = 3) -> list:
    """
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
        dims = room.get("dimensions", {"length": 15.0, "width": 12.0})
        length = float(dims.get("length", 15.0))
        width = float(dims.get("width", 12.0))

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


def generate_walls(dimensions: dict, x_offset: float, z_offset: float) -> list:
    """Generate wall geometry for a room.

    N/S walls are extended by WALL_T on each end so they wrap around and fill
    the corners where E/W walls meet them, eliminating the corner gaps.
    """
    length = dimensions["length"]
    width = dimensions["width"]
    height = dimensions["height"]
    wt = WALL_T

    return [
        {
            "start": {"x": x_offset - length / 2 - wt, "y": 0, "z": z_offset - width / 2},
            "end":   {"x": x_offset + length / 2 + wt, "y": 0, "z": z_offset - width / 2},
            "height": height,
            "material": "drywall",
        },
        {
            "start": {"x": x_offset + length / 2, "y": 0, "z": z_offset - width / 2 - wt},
            "end":   {"x": x_offset + length / 2, "y": 0, "z": z_offset + width / 2 + wt},
            "height": height,
            "material": "drywall",
        },
        {
            "start": {"x": x_offset + length / 2 + wt, "y": 0, "z": z_offset + width / 2},
            "end":   {"x": x_offset - length / 2 - wt, "y": 0, "z": z_offset + width / 2},
            "height": height,
            "material": "drywall",
        },
        {
            "start": {"x": x_offset - length / 2, "y": 0, "z": z_offset - width / 2 - wt},
            "end":   {"x": x_offset - length / 2, "y": 0, "z": z_offset + width / 2 + wt},
            "height": height,
            "material": "drywall",
        },
    ]


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


def build_geometry_from_rooms(
    rooms_ft: list[dict],
    materials: list[dict] | None = None,
    project_id: int | None = None,
    project_name: str = "Generated House",
    target_platform: str = "quest2",
    optimize_for_vr: bool = True,
) -> dict:
    """Build a VR geometry payload from a list of rooms.

    Args:
        rooms_ft: Rooms with dimensions in FEET. Each dict may include:
            ``name``, ``dimensions`` (``length``/``width``/``height`` in ft),
            ``floor_material`` (default ``"carpet"``),
            ``wall_material`` (default ``"drywall"``).
        materials: Optional list of material dicts with ``material_type`` and
            ``name`` keys (matches the ``Material`` model shape). If omitted,
            the material map falls back to drywall/carpet defaults used by the
            generated walls/floors.
        project_id / project_name: Metadata echoed into the response.
        target_platform / optimize_for_vr: Metadata for the Quest client.

    Returns:
        The same ``geometry`` dict shape produced by the original inline
        implementation in ``projects.py``.
    """
    rooms_m = [
        {**r, "dimensions": ft_to_m_dims(r.get("dimensions", {}))}
        for r in rooms_ft
    ]
    packed_positions = compute_packed_positions(rooms_m)

    rooms_out: list[dict] = []
    doors: list[dict] = []
    windows: list[dict] = []

    for idx, room in enumerate(rooms_m):
        room_id = idx + 1
        dimensions = room["dimensions"]
        x_offset, z_offset, eff_width = packed_positions[idx]
        geom_dims = {**dimensions, "width": eff_width}

        room_name = room.get("name", f"Room {room_id}")
        logger.info(
            f"  Room {room_id}: '{room_name}' "
            f"{dimensions['length']}x{eff_width:.2f}(eff)x{dimensions['height']}m "
            f"@ ({x_offset:.2f}, 0, {z_offset:.2f})"
        )

        rooms_out.append({
            "id": room_id,
            "name": room_name,
            "position": {"x": x_offset, "y": 0, "z": z_offset},
            "dimensions": dimensions,
            "walls": generate_walls(geom_dims, x_offset, z_offset),
            "floor": generate_floor(
                geom_dims, x_offset, z_offset, room.get("floor_material", "carpet")
            ),
            "ceiling": generate_ceiling(
                geom_dims, x_offset, z_offset, room.get("wall_material", "drywall")
            ),
        })

        doors.append({
            "id": 100 + room_id,
            "position": {"x": x_offset + dimensions["length"] / 2, "y": 0, "z": z_offset},
            "width": round(3.0 * FT_TO_M, 3),
            "height": round(6.67 * FT_TO_M, 3),
            "rotation": 90,
            "door_type": "interior",
        })

        windows.append({
            "id": 200 + room_id,
            "position": {"x": x_offset, "y": round(3.0 * FT_TO_M, 3), "z": z_offset + dimensions["width"] / 2},
            "width": round(4.0 * FT_TO_M, 3),
            "height": round(5.0 * FT_TO_M, 3),
            "rotation": 180,
            "glass_type": "double_pane",
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
        "spawn_position": {
            "x": rooms_out[0]["position"]["x"] if rooms_out else 0.0,
            "y": 1.6,
            "z": -3.0,
        },
        "metadata": {
            "total_rooms": len(rooms_out),
            "total_doors": len(doors),
            "total_windows": len(windows),
            "platform": target_platform,
            "optimized": optimize_for_vr,
        },
    }
