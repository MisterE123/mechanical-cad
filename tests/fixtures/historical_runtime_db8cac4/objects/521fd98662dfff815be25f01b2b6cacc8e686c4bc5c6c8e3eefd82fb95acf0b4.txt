#!/usr/bin/env python3
"""Offline, deterministic SVG normalization, PNG generation, and review sheets."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 24, 32, 48, 64)
THEMES = {"dark": "#E8EAED", "light": "#202124"}
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_google(name):
    source = ET.parse(ROOT / "vendor/google" / f"{name}.svg").getroot()
    root = ET.Element(
        f"{{{NS}}}svg",
        {"width": "24", "height": "24", "viewBox": "0 0 24 24", "fill": "currentColor"},
    )
    # Google's exact 24px outlines use a 960-unit negative-Y viewBox.
    group = ET.SubElement(root, f"{{{NS}}}g", {"transform": "translate(0 24) scale(0.025)"})
    for child in source:
        group.append(child)
    return ET.tostring(root, encoding="unicode") + "\n"


def original_svg(body):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">\n'
        + body
        + "\n</svg>\n"
    )


def write_review(assets, theme):
    cols, cellw, cellh = 5, 236, 132
    rows = (len(assets) + cols - 1) // cols
    bg = "#292A2D" if theme == "dark" else "#FAFAFA"
    fg = THEMES[theme]
    muted = "#BDC1C6" if theme == "dark" else "#5F6368"
    sheet = Image.new("RGB", (cols * cellw, rows * cellh + 88), bg)
    d = ImageDraw.Draw(sheet)

    def font(size):
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)

    d.text((20, 14), f"Mechanical CAD | {theme} background | asset review", fill=fg, font=font(22))
    d.text(
        (20, 47),
        "Actual-size previews: 16 / 24 / 32 px. Assets only; availability depends on the host UI.",
        fill=muted,
        font=font(14),
    )
    for i, asset in enumerate(assets):
        x, y = (i % cols) * cellw, 88 + (i // cols) * cellh
        d.line((x, y, x + cellw, y), fill="#45464A" if theme == "dark" else "#DDDDDD")
        cursor = x + 18
        for size in (16, 24, 32):
            icon = Image.open(ROOT / f"png/{theme}/{size}/{asset['file_stem']}.png")
            sheet.paste(icon, (cursor, y + 19 + (32 - size) // 2), icon)
            cursor += 48
        d.text((x + 18, y + 63), asset["label"], fill=fg, font=font(14))
        d.text((x + 18, y + 85), asset["action_id"], fill=muted, font=font(11))
        d.text(
            (x + 18, y + 104),
            "Google Material Symbols"
            if asset["source"]["kind"] == "google"
            else "Original CAD geometry",
            fill=muted,
            font=font(10),
        )
    sheet.save(ROOT / "review" / f"contact_sheet_{theme}.png")


def main():
    catalog = json.loads((ROOT / "catalog.json").read_text())
    vendor = json.loads((ROOT / "vendor/google/metadata.json").read_text())
    byname = {x["name"]: x for x in vendor["assets"]}
    originals = json.loads((ROOT / "original_geometry.json").read_text())
    output = []
    with tempfile.TemporaryDirectory(prefix="cad-icons-") as td:
        temp = Path(td)
        env = os.environ.copy()
        env["INKSCAPE_PROFILE_DIR"] = str(temp / "inkscape-profile")
        # Export one 256px alpha mask per shape; recolor without changing its alpha.
        for entry in catalog:
            entry = dict(entry)
            stem = entry["action_id"].replace(".", "_")
            entry["file_stem"] = stem
            entry["availability"] = "asset_only_unwired"
            if "google_symbol" in entry:
                name = entry.pop("google_symbol")
                meta = byname[name]
                svg = normalize_google(name)
                entry["source"] = {
                    "kind": "google",
                    "name": "Google Material Symbols Outlined",
                    "symbol": name,
                    "license": "Apache-2.0",
                    "license_file": "licenses/Apache-2.0.txt",
                    "url": f"https://github.com/google/material-design-icons/blob/{vendor['commit']}/{meta['path']}",
                    "upstream_commit": vendor["commit"],
                    "upstream_git_blob_sha": meta["sha"],
                    "upstream_file": f"vendor/google/{name}.svg",
                    "upstream_sha256": sha(ROOT / "vendor/google" / f"{name}.svg"),
                    "modifications": "Normalized coordinates to a 24-unit viewBox; currentColor; theme recolor; PNG rasterization. Path geometry unchanged.",
                }
            else:
                svg = original_svg(originals[entry["action_id"]])
                entry["source"] = {
                    "kind": "original",
                    "name": "Mechanical CAD original vector geometry",
                    "license": "GPL-3.0-or-later",
                    "license_file": "licenses/GPL-3.0-or-later.txt",
                    "source_file": "original_geometry.json",
                    "created_on": "2026-10-16",
                    "modifications": "Original repository-native vector geometry created for this project; no third-party CAD artwork used.",
                }
            path = ROOT / "svg" / f"{stem}.svg"
            path.write_text(svg)
            entry["svg"] = str(path.relative_to(ROOT))
            entry["svg_sha256"] = sha(path)
            temp_svg = temp / f"{stem}.svg"
            temp_svg.write_text(svg.replace("currentColor", "#000000"))
            mask_path = temp / f"{stem}.png"
            subprocess.run(
                [
                    "inkscape",
                    str(temp_svg),
                    "--export-type=png",
                    f"--export-filename={mask_path}",
                    "--export-width=256",
                    "--export-height=256",
                    "--export-background-opacity=0",
                ],
                check=True,
                env=env,
                capture_output=True,
            )
            mask = Image.open(mask_path).convert("RGBA").getchannel("A")
            entry["png"] = {}
            for theme, color in THEMES.items():
                entry["png"][theme] = {}
                for size in SIZES:
                    dest = ROOT / f"png/{theme}/{size}/{stem}.png"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    alpha = mask.resize((size, size), Image.Resampling.LANCZOS)
                    image = Image.new("RGBA", (size, size), color)
                    image.putalpha(alpha)
                    image.save(dest, optimize=False)
                    entry["png"][theme][str(size)] = str(dest.relative_to(ROOT))
            output.append(entry)
    manifest = {
        "schema_version": 1,
        "pack_version": "0.1.0-next-preview",
        "created_on": "2026-10-16",
        "scope": "Offline icon assets for the next Mechanical CAD UI. No add-on integration, product readiness, or action availability is implied.",
        "style": {
            "grid": 24,
            "sizes": list(SIZES),
            "themes": THEMES,
            "theme_meaning": "dark = light ink for dark surfaces; light = dark ink for light surfaces",
            "google_variant": "Outlined, weight 400, fill 0, grade 0, optical size 24",
            "original_stroke_width": 1.8,
        },
        "assets": output,
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for theme in THEMES:
        write_review(output, theme)
    print(f"Built {len(output)} SVGs and {len(output) * len(THEMES) * len(SIZES)} PNGs")


if __name__ == "__main__":
    main()
