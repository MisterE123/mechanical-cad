"""Offline UI resources have reproducible artwork, source, and license evidence."""

import hashlib
import json
import struct
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender/assets/icons"


def test_icon_catalog_has_licensed_sources_and_original_svg_hashes():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assets = manifest["assets"]
    assert len(assets) == len({a["action_id"] for a in assets}) == 44
    assert {a["source"]["license"] for a in assets} == {"Apache-2.0", "GPL-3.0-or-later"}
    for asset in assets:
        assert asset["hover_description"] and asset["label"]
        assert asset["availability"] == "asset_only_unwired"
        source = asset["source"]
        assert (ROOT / source["license_file"]).stat().st_size > 1000
        svg = (ROOT / asset["svg"]).read_bytes()
        assert hashlib.sha256(svg).hexdigest() == asset["svg_sha256"]
        parsed = ElementTree.fromstring(svg)
        assert parsed.attrib["viewBox"] == "0 0 24 24"
        assert all(e.tag.split("}")[-1] not in {"script", "image"} for e in parsed.iter())
        if source["kind"] == "google":
            raw = (ROOT / source["upstream_file"]).read_bytes()
            assert source["upstream_commit"] == "49d4db35df873165d6bd6ba09b063c7dafbac2f4"
            assert hashlib.sha256(raw).hexdigest() == source["upstream_sha256"]
            assert (
                hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
                == source["upstream_git_blob_sha"]
            )
    assert (ROOT / "NOTICE.txt").is_file()


def test_offline_preview_images_have_declared_sizes_and_alpha():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    for asset in manifest["assets"]:
        for theme in ("light", "dark"):
            for size in (16, 24, 32, 48, 64):
                raw = (ROOT / asset["png"][theme][str(size)]).read_bytes()
                assert raw[:8] == b"\x89PNG\r\n\x1a\n"
                assert raw[12:16] == b"IHDR"
                width, height, bits, color = struct.unpack(">IIBB", raw[16:26])
                assert (width, height, bits, color) == (size, size, 8, 6)


def test_integrated_asset_checksums_cover_every_delivered_resource():
    declared = {}
    for line in (ROOT / "SHA256SUMS.txt").read_text().splitlines():
        checksum, relative = line.split("  ", 1)
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        declared[relative] = checksum
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == checksum
    actual = {
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob("*")
        if p.is_file() and p.name != "SHA256SUMS.txt" and "__pycache__" not in p.parts
    }
    assert actual == set(declared)
