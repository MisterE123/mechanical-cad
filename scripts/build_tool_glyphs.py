"""Rebuild original CAD menu glyph PNGs (Pillow is an offline build dependency)."""

import hashlib
import importlib.util
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
spec = importlib.util.spec_from_file_location("tool_glyphs", ADDON / "tool_glyphs.py")
glyphs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(glyphs)


def render(action, size=48, color=(232, 234, 237, 255)):
    scale = size * 4 / 24
    image = Image.new("RGBA", (size * 4, size * 4))
    draw = ImageDraw.Draw(image)
    for polygon in glyphs.polygons(action):
        draw.polygon([(x * scale, (24 - y) * scale) for x, y in polygon], fill=color)
    return image.resize((size, size), Image.Resampling.LANCZOS)


# Focused original designs; SVG is an inspectable export of the same code-owned
# polygons used by Blender, not another parser or a second source of truth.
DESIGNED_ACTIONS = ("LOFT", "SWEEP", "HOLE", "SHELL")


def svg(action):
    polygons = []
    for polygon in glyphs.polygons(action):
        points = " ".join(f"{x:.6f},{24 - y:.6f}" for x, y in polygon)
        polygons.append(f'    <polygon points="{points}"/>')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">\n'
        f"  <title>{action.title()} — original Mechanical CAD glyph</title>\n"
        '  <g fill="currentColor">\n' + "\n".join(polygons) + "\n  </g>\n</svg>\n"
    )


def write_design_exports(root):
    target = root / "svg"
    target.mkdir(parents=True, exist_ok=True)
    assets = []
    for action in DESIGNED_ACTIONS:
        path = target / f"{action}.svg"
        path.write_text(svg(action), encoding="utf-8")
        files = [path] + [root / theme / f"{action}.png" for theme in ("dark", "light")]
        assets.append(
            {
                "action": action,
                "author": "Mechanical CAD contributors",
                "license": "GPL-3.0-or-later",
                "source": "../../tool_glyphs.py",
                "files": {
                    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in files
                },
            }
        )
    manifest = {
        "description": "Original targeted CAD designs; no upstream artwork copied",
        "generator": "scripts/build_tool_glyphs.py",
        "assets": assets,
    }
    (root / "design_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main():
    root = ADDON / "assets/tool_glyphs"
    for theme, color in (("dark", (232, 234, 237, 255)), ("light", (32, 33, 36, 255))):
        target = root / theme
        target.mkdir(parents=True, exist_ok=True)
        for action in glyphs.STROKES:
            render(action, color=color).save(target / f"{action}.png")
    write_design_exports(root)


if __name__ == "__main__":
    main()
