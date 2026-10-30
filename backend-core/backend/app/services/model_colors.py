"""Changing the colours of a photo model (plant_model_service.py): image-to-3D
models copy the photo's colours, and the photo's light, so white cabinets can come
out tan. ``palette`` lists the colours its surface is mostly made of; ``recolor``
replaces one of them (and the shades near it) with another, keeping the shading
(panel grooves, shadow sides), and writes a new ``.glb``.

Colours live in a base-colour texture (TRELLIS) or in vertex colours (TripoSR);
both are handled. Sizes and placement are left alone: only colours change.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PIL import Image


def _step(x, a: float, b: float):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _rgb(hex_color: str) -> np.ndarray:
    h = hex_color.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float) / 255


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(round(c * 255)):02x}" for c in np.clip(rgb, 0, 1))


def _geometries(path: Path) -> tuple[trimesh.Scene, list[trimesh.Trimesh]]:
    scene = trimesh.load(path, force="scene")
    return scene, [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]


def _texture(g: trimesh.Trimesh) -> Image.Image | None:
    material = getattr(g.visual, "material", None)
    image = getattr(material, "baseColorTexture", None) if material is not None else None
    if image is None and material is not None:
        image = getattr(material, "image", None)
    return image


def _surface_colors(g: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    """Colours of the surface (rgb 0..1) and how much area each stands for: the
    texture at every face's centre (a texture also holds unused padding), else
    the vertex colours."""
    image = _texture(g)
    if image is not None and getattr(g.visual, "uv", None) is not None:
        pixels = np.asarray(image.convert("RGB")).astype(float) / 255
        uv = g.visual.uv[g.faces].mean(axis=1) % 1.0
        x = np.clip((uv[:, 0] * pixels.shape[1]).astype(int), 0, pixels.shape[1] - 1)
        y = np.clip(((1 - uv[:, 1]) * pixels.shape[0]).astype(int), 0, pixels.shape[0] - 1)
        return pixels[y, x], g.area_faces
    if g.visual.kind == "vertex":
        colors = g.visual.vertex_colors[:, :3].astype(float) / 255
        return colors, np.ones(len(colors))
    return np.zeros((0, 3)), np.zeros(0)


def palette(path: Path, n: int = 8) -> list[dict]:
    """The ``n`` colours most of the model's surface is, largest share first."""
    _, geometries = _geometries(path)
    parts = [_surface_colors(g) for g in geometries]
    colors = np.concatenate([c for c, _ in parts]) if parts else np.zeros((0, 3))
    weights = np.concatenate([w for _, w in parts]) if parts else np.zeros(0)
    if len(colors) == 0 or weights.sum() <= 0:
        return []
    # A few rounds of weighted k-means, started from evenly spaced brightnesses.
    order = np.argsort(colors.sum(axis=1))
    k = min(n, len(colors))
    centers = colors[order[np.linspace(0, len(order) - 1, k).astype(int)]]
    for _ in range(12):
        nearest = np.argmin(((colors[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
        for i in range(k):
            w = weights[nearest == i]
            if w.sum() > 0:
                centers[i] = (colors[nearest == i] * w[:, None]).sum(0) / w.sum()
    share = np.array([weights[nearest == i].sum() for i in range(k)]) / weights.sum()
    found = sorted(zip(share, centers.tolist()), key=lambda t: -t[0])
    return [{"color": _hex(c), "share": round(float(s), 3)} for s, c in found if s >= 0.01]


def _weight(rgb: np.ndarray, source: np.ndarray, tolerance: float) -> np.ndarray:
    """How much each colour counts as ``source`` (0..1): close in hue/saturation
    (brightness-free chromaticity) and roughly as bright, wider with ``tolerance``."""
    def chroma(c):
        return c / np.maximum(c.sum(axis=-1, keepdims=True), 1e-6)

    d_chroma = np.linalg.norm(chroma(rgb) - chroma(source), axis=-1)
    d_value = np.abs(rgb.max(axis=-1) - source.max())
    reach = 0.02 + 0.10 * tolerance
    value_reach = 0.15 + 0.35 * tolerance
    return (1 - _step(d_chroma, reach * 0.5, reach)) * (1 - _step(d_value, value_reach * 0.6, value_reach))


def _replace(rgb: np.ndarray, source: np.ndarray, target: np.ndarray, tolerance: float) -> tuple[np.ndarray, np.ndarray]:
    w = _weight(rgb, source, tolerance)
    # Shading kept: a pixel darker than the picked colour stays that much darker.
    shade = np.clip(rgb.max(axis=-1) / max(source.max(), 1e-3), 0.0, 1.0)
    shade = 0.35 + 0.65 * shade if target.max() > source.max() else shade
    out = rgb * (1 - w[..., None]) + (target[None] * shade[..., None]) * w[..., None]
    return out, w


def recolor(src: Path, dst: Path, from_color: str, to_color: str, tolerance: float = 0.5) -> float:
    """Write ``src`` to ``dst`` with ``from_color`` (and what is near it) turned
    ``to_color``. Returns the share of the surface that changed (0 = nothing did)."""
    source, target = _rgb(from_color), _rgb(to_color)
    scene, geometries = _geometries(src)
    changed = total = 0.0
    for g in geometries:
        colors, area = _surface_colors(g)
        if len(colors):
            changed += float((area * (_weight(colors, source, tolerance) > 0.5)).sum())
            total += float(area.sum())
        image = _texture(g)
        if image is not None:
            pixels = np.asarray(image.convert("RGB")).astype(float) / 255
            out, _ = _replace(pixels, source, target, tolerance)
            new = Image.fromarray((out * 255).round().astype(np.uint8))
            if image.mode == "RGBA":
                new.putalpha(image.getchannel("A"))
            material = g.visual.material
            if hasattr(material, "baseColorTexture"):
                material.baseColorTexture = new
            else:
                material.image = new
        elif g.visual.kind == "vertex":
            vc = g.visual.vertex_colors.astype(float) / 255
            out, _ = _replace(vc[:, :3], source, target, tolerance)
            g.visual.vertex_colors = np.concatenate([out, vc[:, 3:]], axis=1) * 255
    share = changed / total if total else 0.0
    if share > 0:
        scene.export(dst)
    return share
