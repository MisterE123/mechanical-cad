"""Frozen native palette glyphs fail closed before Blender's unchecked decoder."""

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"
SPEC = importlib.util.spec_from_file_location(
    "mcad_palette_shapes_test", ROOT / "palette_shapes.py"
)
shapes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shapes)  # No add-on package initializer or bpy required.
ASSETS = ROOT / "assets/palette_shapes"
MANIFEST = json.loads((ASSETS / "manifest.json").read_text())
NAMES = tuple(MANIFEST["assets"])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(points):
    return bytes(value for point in [*points, points[-1]] for value in point)


TRIANGLE = encode([(0, 0), (255, 0), (0, 255)])
SQUARE = encode([(0, 0), (255, 0), (255, 255), (0, 255)])


@pytest.fixture
def isolated_assets(tmp_path, monkeypatch):
    destination = tmp_path / "palette_shapes"
    shutil.copytree(ASSETS, destination)
    sources = tmp_path / "icons/svg"
    sources.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(ROOT / "assets/icons/svg" / f"{name}.svg", sources / f"{name}.svg")
    monkeypatch.setattr(shapes, "_ROOT", destination)
    return destination


def test_pinned_manifest_and_exact_action_whitelist():
    assert sha(ASSETS / "manifest.json") == shapes._MANIFEST_SHA256
    assert shapes.ACTIONS == (
        "NEW",
        "EDIT",
        "DIMENSIONS",
        "FINISH",
        "CANCEL",
        "EXTRUDE",
        "CUT",
        "CHECK",
        "EXPORT",
    )
    assert MANIFEST["actions"] == dict(shapes._FILES)
    assert len(NAMES) == 8
    assert sum(asset["bytes"] for asset in MANIFEST["assets"].values()) == 3836
    assert MANIFEST["native_draw_tested"] is MANIFEST["native_hit_tooltip_tested"] is False
    assert shapes.load_shape("NEW") == shapes.load_shape("EDIT")


@pytest.mark.parametrize("action", shapes.ACTIONS)
def test_each_action_returns_only_exact_validated_immutable_bytes(action):
    name = MANIFEST["actions"][action]
    asset = MANIFEST["assets"][name]
    data = shapes.load_shape(action)
    assert type(data) is bytes
    assert data == (ASSETS / asset["binary"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == asset["shape_sha256"]
    assert all(value == asset[key] for key, value in shapes._validate_payload(data).items())


@pytest.mark.parametrize("name", NAMES)
def test_each_asset_retains_exact_source_and_licensed_provenance(name):
    asset = MANIFEST["assets"][name]
    source = asset["source_provenance"]
    assert asset["source_svg"] == f"../icons/svg/{name}.svg"
    assert sha(ASSETS / asset["source_svg"]) == asset["source_sha256"]
    license_record = MANIFEST["licenses"][source["license"]]
    assert license_record["file"] == source["license_file"]
    assert sha(ASSETS / license_record["file"]) == license_record["sha256"]
    assert (ASSETS / license_record["file"]).stat().st_size > 1000
    assert asset["safe_binary_framing_verified"] and asset["native_wire_exact_boundary_verified"]
    assert asset["triangle_area_and_boundary_verified"]
    assert asset["planar_nonoverlapping_edges_verified"]
    if source["kind"] == "google":
        assert source["license"] == "Apache-2.0"
        assert source["upstream_commit"] == "49d4db35df873165d6bd6ba09b063c7dafbac2f4"
        raw = (ASSETS / source["upstream_file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == source["upstream_sha256"]
        assert (
            hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
            == (source["upstream_git_blob_sha"])
        )
        assert source["upstream_commit"] in source["url"]
    else:
        assert source["kind"] == "original" and source["license"] == "GPL-3.0-or-later"
        assert (ASSETS / source["source_file"]).is_file()


def test_notices_and_source_pack_identity_are_retained():
    for relative, expected in MANIFEST["notices"].items():
        assert sha(ASSETS / relative) == expected
    assert sha(ROOT / "assets/icons/manifest.json") == MANIFEST["source_pack_manifest_sha256"]


@pytest.mark.parametrize(
    "action", ["", "new", "ASSEMBLY_NEW", "sketch.rectangle", "../NEW", None, {}]
)
def test_unknown_action_never_touches_files(action, monkeypatch):
    def forbidden(*args):
        raise AssertionError("Unknown action attempted a resource read")

    monkeypatch.setattr(shapes, "_read_verified", forbidden)
    assert shapes.load_shape(action) is None


@pytest.mark.parametrize(
    "relative", ["manifest.json", "edit_apply.bin", "../icons/svg/edit_apply.svg"]
)
@pytest.mark.parametrize("damage", ["missing", "corrupt", "oversize"])
def test_missing_corrupt_or_oversize_resources_fall_back(isolated_assets, relative, damage):
    path = isolated_assets / relative
    assert shapes.load_shape("FINISH") is not None
    if damage == "missing":
        path.unlink()
    elif damage == "corrupt":
        raw = bytearray(path.read_bytes())
        raw[0] ^= 1
        path.write_bytes(raw)
    else:
        path.write_bytes(b"x" * (shapes._MAX_MANIFEST_BYTES + 1))
    assert shapes.load_shape("FINISH") is None
    if relative != "manifest.json":
        assert shapes.load_shape("CANCEL") is not None


def test_replacing_payload_and_editing_its_manifest_hash_cannot_repin(isolated_assets):
    (isolated_assets / "edit_apply.bin").write_bytes(TRIANGLE)
    changed = json.loads((isolated_assets / "manifest.json").read_text())
    changed["assets"]["edit_apply"]["shape_sha256"] = hashlib.sha256(TRIANGLE).hexdigest()
    (isolated_assets / "manifest.json").write_text(json.dumps(changed))
    assert shapes.load_shape("FINISH") is None


@pytest.mark.parametrize(
    "data",
    [
        b"",
        TRIANGLE[:-1],
        TRIANGLE[:-2],
        TRIANGLE + b"\0\0",
        TRIANGLE + TRIANGLE[:-2],
        bytes(2050),
        bytearray(TRIANGLE),
        list(TRIANGLE),
        encode([(0, 0), (1, 1)]),
        encode([(0, 0), (1, 1), (2, 2)]),
        encode([(0, 0), (0, 255), (255, 0)]),
        encode([(0, 0), (255, 0), (255, 255), (0, 0)]),
        encode(
            [(0, 0), (10, 0), (20, 0), (30, 0), (30, 10), (30, 20), (20, 20), (10, 20), (0, 20)]
        ),
        TRIANGLE * 193,
        SQUARE * 145,
    ],
)
def test_adversarial_decoder_framing_geometry_and_budgets(data):
    with pytest.raises(ValueError):
        shapes._validate_payload(data)


def test_uint8_bounds_final_sentinels_and_variable_polygon_lengths():
    result = shapes._validate_payload(TRIANGLE + SQUARE)
    assert result == {
        "bytes": 18,
        "encoded_polygons": 2,
        "encoded_vertices": 7,
        "signed_area2": 195075,
        "bounds": [0, 0, 255, 255],
    }
    assert len(shapes.load_shape("EXTRUDE")) % 8 != 0  # Not fixed triangle records.


def test_every_proper_payload_prefix_is_rejected_by_pinned_hash(isolated_assets):
    path = isolated_assets / "edit_apply.bin"
    original = path.read_bytes()
    for length in range(len(original)):
        path.write_bytes(original[:length])
        assert shapes.load_shape("FINISH") is None


def test_read_budget_is_applied_to_the_read_itself():
    class PathProbe:
        def open(self, mode):
            assert mode == "rb"
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, amount):
            assert amount == 17
            return b"x" * amount

    with pytest.raises(ValueError):
        shapes._read_verified(PathProbe(), "unused", 16)
