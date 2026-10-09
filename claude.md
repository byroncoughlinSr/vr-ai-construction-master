# VR House Geometry — Connectivity Fix

## Problem
The generated VR house had five visible seams/gaps:

1. **Corner gaps** — the outer corners of rooms had uncovered holes where walls met
2. **Walls extended beyond the floor** — wall outer faces stuck out 0.1 units past the floor boundary
3. **Floor gap at walls** — a 0.1-unit visible seam between the floor edge and the inner wall face
4. **Ceiling gap at walls** — same seam at the top of each wall
5. **Doors parallel to walls** — doors were not rotated to match their wall (separate fix, see below)

---

## Root Cause

### Wall Thickness vs. Floor/Ceiling Alignment

Each wall box has a half-thickness of **0.1 units** in its local Z direction (matching `Box(..., 0.1f)` in `HouseGenerator.kt`).

The wall is positioned with its **centerline** on the room boundary.
This means:
- Outer face = boundary + 0.1 → wall sticks past the floor
- Inner face = boundary − 0.1 → there is a 0.1-unit gap between floor edge and wall surface

The floor and ceiling vertices were placed exactly at the wall centerlines, so they ended at the gap rather than at the wall face.

### Corner Gaps

The N/S walls ran from `x_offset - length/2` to `x_offset + length/2` — exactly the room span.
The E/W walls are centred on those same X coordinates.
This left the outer corner (a 0.1 × 0.1 unit L-shaped region) uncovered where the two walls met.

---

## Fix (backend — `projects.py`)

Added constant:
```python
WALL_T = 0.1  # half wall thickness, must match Box(..., 0.1f) in HouseGenerator.kt
```

### `generate_walls()`
Extended **N/S walls** by `WALL_T` on each end in X so they wrap around and fill the corners:

```
SOUTH wall: x = [x_offset - length/2 - WALL_T,  x_offset + length/2 + WALL_T]
NORTH wall: same (reversed direction)
EAST wall:  unchanged  z = [z_offset - width/2,  z_offset + width/2]
WEST wall:  unchanged
```

### `generate_floor()` and `generate_ceiling()`
Extended all four vertices outward by `WALL_T` so the slab runs under the walls:

```
x range: [x_offset - length/2 - WALL_T,  x_offset + length/2 + WALL_T]
z range: [z_offset - width/2  - WALL_T,  z_offset + width/2  + WALL_T]
```

No Kotlin changes required — `HouseGenerator.kt` reads the vertex coordinates directly and the Kotlin box calculations are correct.

---

## Related Fix — Door/Window Rotation (`HouseGenerator.kt`)

Doors and windows were not rotated to match their wall:

- **Wall rotation bug**: `Math.atan2()` returns radians but `Quaternion(pitch, yaw, roll)` expects degrees — all walls were nearly unrotated, making them parallel.
- **Door/window rotation ignored**: the `rotation` field from JSON was read but never applied to the `Transform`.
- **Backend sent wrong rotation values**: doors on the EAST wall (which needs 90°) had `rotation: 0`; windows on the NORTH wall had `rotation: 270` instead of `180`.

### Fixes applied:
| File | Change |
|------|--------|
| `HouseGenerator.kt` `generateWall()` | `Math.toDegrees(Math.atan2(...))` before passing to `Quaternion` |
| `HouseGenerator.kt` `generateDoor()` | Apply `Quaternion(0f, rotationDeg, 0f)` from JSON `rotation` field |
| `HouseGenerator.kt` `generateWindow()` | Same |
| `projects.py` door entries | `"rotation": 90` (EAST wall = 90° Y-rotation) |
| `projects.py` window entries | `"rotation": 180` (NORTH wall = 180° Y-rotation) |

---

## If `WALL_T` Changes

If the wall thickness in `HouseGenerator.kt` is changed from `0.1f`, update `WALL_T` in `projects.py` to match.
The value must be identical in both places for floor/ceiling/corner seams to remain closed.
