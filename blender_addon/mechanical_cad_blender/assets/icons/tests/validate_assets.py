#!/usr/bin/env python3
"""Validate this pack using only the standard library and Pillow."""

from __future__ import annotations

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageColor

ROOT = Path(__file__).resolve().parents[1]


def lum(color):
    rgb = ImageColor.getrgb(color)
    channels = [v / 255 for v in rgb]
    channels = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
    return sum(v * w for v, w in zip(channels, (0.2126, 0.7152, 0.0722), strict=True))


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    errors, checks, silhouettes = [], 0, {}

    def check(ok, label):
        nonlocal checks
        checks += 1
        if not ok:
            errors.append(label)

    ids = [a["action_id"] for a in manifest["assets"]]
    check(len(ids) == len(set(ids)), "Unique action IDs")
    check(len(manifest["assets"]) == 44, "Expected 44 action assets")
    png_count = 0
    for asset in manifest["assets"]:
        aid = asset["action_id"]
        check(bool(asset.get("hover_description")), f"{aid}: hover description")
        check(asset["availability"] == "asset_only_unwired", f"{aid}: no readiness claim")
        source = asset["source"]
        check((ROOT / source["license_file"]).is_file(), f"{aid}: license exists")
        if source["kind"] == "google":
            raw = (ROOT / source["upstream_file"]).read_bytes()
            blob_hash = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
            check(
                source["upstream_git_blob_sha"] == blob_hash,
                f"{aid}: pinned upstream blob matches exactly",
            )
            check(
                hashlib.sha256(raw).hexdigest() == source["upstream_sha256"],
                f"{aid}: vendored source hash",
            )
        svg_path = ROOT / asset["svg"]
        root = ET.parse(svg_path).getroot()
        check(root.attrib.get("viewBox") == "0 0 24 24", f"{aid}: normalized 24px viewBox")
        check(
            hashlib.sha256(svg_path.read_bytes()).hexdigest() == asset["svg_sha256"],
            f"{aid}: SVG hash",
        )
        check(
            all(not k.endswith("href") for el in root.iter() for k in el.attrib),
            f"{aid}: no external assets",
        )
        check(
            all(
                el.tag.rsplit("}", 1)[-1] not in {"script", "image", "text", "foreignObject"}
                for el in root.iter()
            ),
            f"{aid}: self-contained vector paths",
        )
        for size in manifest["style"]["sizes"]:
            alpha_by_theme = []
            for theme, ink in manifest["style"]["themes"].items():
                path = ROOT / asset["png"][theme][str(size)]
                im = Image.open(path)
                png_count += 1
                check(im.mode == "RGBA", f"{aid}/{theme}/{size}: RGBA")
                check(im.size == (size, size), f"{aid}/{theme}/{size}: dimensions")
                a = im.getchannel("A")
                bbox = a.getbbox()
                check(
                    bbox is not None and a.getextrema()[0] == 0 and a.getextrema()[1] >= 200,
                    f"{aid}/{theme}/{size}: visible ink and alpha transparency",
                )
                check(
                    all(
                        a.getpixel(p) == 0
                        for p in [(0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)]
                    ),
                    f"{aid}/{theme}/{size}: transparent corners",
                )
                expected = ImageColor.getrgb(ink)
                rgb_colors = im.convert("RGB").getcolors(maxcolors=size * size)
                check(
                    rgb_colors == [(size * size, expected)],
                    f"{aid}/{theme}/{size}: exact monochrome ink",
                )
                alpha_by_theme.append(a.tobytes())
                if size == 32 and theme == "dark":
                    sig = hashlib.sha256(a.tobytes()).hexdigest()
                    check(
                        sig not in silhouettes,
                        f"{aid}: unique 32px silhouette; collides with {silhouettes.get(sig)}",
                    )
                    silhouettes[sig] = aid
            check(alpha_by_theme[0] == alpha_by_theme[1], f"{aid}/{size}: matching theme alpha")
    ratios = {}
    for theme, background in {"dark": "#292A2D", "light": "#FAFAFA"}.items():
        values = sorted([lum(manifest["style"]["themes"][theme]), lum(background)])
        ratio = (values[1] + 0.05) / (values[0] + 0.05)
        ratios[theme] = round(ratio, 2)
        check(ratio >= 7, f"{theme}: ink contrast >= 7:1 on review background")
        check(
            (ROOT / f"review/contact_sheet_{theme}.png").is_file(), f"{theme}: contact sheet exists"
        )
    report = {
        "passed": not errors,
        "checks": checks,
        "svg_count": len(ids),
        "png_count": png_count,
        "unique_32px_silhouettes": len(silhouettes),
        "opaque_ink_contrast_ratios": ratios,
        "errors": errors,
        "limitations": [
            "No Blender UI integration or icon cache loading tested.",
            "Unique pixels do not prove intuitive semantics; contact sheets require human review.",
            "Contrast measurements use the documented sample surfaces, not every possible Blender theme.",
            "Hover descriptions for future tools are proposals and must be reconciled with the implementation before wiring.",
        ],
    }
    (ROOT / "review/validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
