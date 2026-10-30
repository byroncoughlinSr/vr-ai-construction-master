"""Recolouring photo models (model_colors.py): the palette, replacing one colour
with shading kept, textures and vertex colours (no network calls)."""

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.services import model_colors

TAN, BLACK, WHITE = "#b49b78", "#1e1e1e", "#ffffff"


def _rgb(hex_color):
    return np.array([int(hex_color[i:i + 2], 16) for i in (1, 3, 5)])


def _textured(path, left=TAN, right=BLACK):
    """A box whose faces sample a texture: the left half ``left`` (with a darker
    groove), the right half ``right``."""
    box = trimesh.creation.box(extents=[1, 1, 1])
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[:, :32] = _rgb(left)
    image[:, 14:18] = (_rgb(left) * 0.6).astype(np.uint8)  # a groove
    image[:, 32:] = _rgb(right)
    # Half the faces sample the left half, the rest the right.
    uv = np.zeros((len(box.vertices), 2))
    uv[:, 0] = np.where(box.vertices[:, 0] < 0, 0.2, 0.8)
    uv[:, 1] = 0.5
    box.visual = trimesh.visual.TextureVisuals(uv=uv, image=Image.fromarray(image))
    trimesh.Scene(box).export(path)
    return path


def _texture(path):
    g = next(iter(trimesh.load(path, force="scene").geometry.values()))
    return np.asarray(g.visual.material.baseColorTexture.convert("RGB")).astype(int)


def test_palette_lists_the_surface_colours(tmp_path):
    colors = model_colors.palette(_textured(tmp_path / "m.glb"))
    found = {c["color"] for c in colors}
    assert any(np.abs(_rgb(c) - _rgb(TAN)).max() < 12 for c in found)
    assert any(np.abs(_rgb(c) - _rgb(BLACK)).max() < 12 for c in found)
    assert sum(c["share"] for c in colors) == pytest.approx(1, abs=0.02)


def test_recolor_changes_one_colour_and_keeps_the_shading(tmp_path):
    src = _textured(tmp_path / "m.glb")
    share = model_colors.recolor(src, tmp_path / "out.glb", TAN, WHITE)
    assert share == pytest.approx(0.5, abs=0.1)
    out = _texture(tmp_path / "out.glb")
    assert out[:, 5].min() > 240  # the tan face is white now
    assert out[:, 15].mean() < out[:, 5].mean() - 30  # the groove is still darker
    assert np.abs(out[:, 50] - _rgb(BLACK)).max() <= 2  # the black half is untouched
    bounds = trimesh.load(tmp_path / "out.glb", force="scene").bounds
    assert np.allclose(bounds, trimesh.load(src, force="scene").bounds)


def test_recolor_of_a_colour_it_does_not_have_writes_nothing(tmp_path):
    src = _textured(tmp_path / "m.glb")
    assert model_colors.recolor(src, tmp_path / "out.glb", "#2050e0", WHITE) == 0
    assert not (tmp_path / "out.glb").exists()


def test_vertex_colours_are_recoloured_too(tmp_path):
    box = trimesh.creation.box(extents=[1, 1, 1])
    box.visual.vertex_colors = np.tile([*_rgb(TAN), 255], (len(box.vertices), 1))
    trimesh.Scene(box).export(tmp_path / "v.glb")
    assert model_colors.recolor(tmp_path / "v.glb", tmp_path / "out.glb", TAN, WHITE) > 0.9
    g = next(iter(trimesh.load(tmp_path / "out.glb", force="scene").geometry.values()))
    assert g.visual.vertex_colors[:, :3].min() > 240

