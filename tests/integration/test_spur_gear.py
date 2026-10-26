"""Printable gear design bounds, native topology, history and export evidence."""

import math

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.errors import CADException
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document
from mechanical_cad.sidecar import process_request
from mechanical_cad.spur_gear import _segment_counts, gear_spec, profile_points


def params(**changes):
    return dict(module=2, tooth_count=20, thickness=5, bore_diameter=5, **changes)


def document():
    return dict(
        schema_version=2,
        id="gear_part",
        name="Spur gear",
        units="mm",
        parameters={"size": 2},
        active_feature="gear",
        features=[
            dict(
                id="gear",
                kind="spur_gear",
                params=dict(module="size", tooth_count=20, thickness=5, bore_diameter=5),
            )
        ],
    )


def test_dimensions_and_pitch_thickness():
    s = gear_spec(**params())
    assert (s.pitch_radius, s.root_radius, s.tip_radius, s.min_tooth_count) == (20, 17.5, 22, 18)
    assert 2 * s.pitch_radius * s.half_tooth_angle == pytest.approx(math.pi - 0.1)
    assert s.base_radius == pytest.approx(20 * math.cos(math.radians(20)))


@pytest.mark.parametrize(
    "change",
    [
        {"module": 0},
        {"module": float("nan")},
        {"tooth_count": 17},
        {"tooth_count": 20.5},
        {"tooth_count": True},
        {"tooth_count": 201},
        {"pressure_angle": 14},
        {"pressure_angle": 31},
        {"thickness": 0},
        {"bore_diameter": 32},
        {"bore_diameter": -1},
        {"backlash": -0.1},
        {"backlash": 1.1},
        {"clearance": -0.1},
        {"clearance": 0.6},
        {"profile_tolerance": 0},
        {"profile_tolerance": 0.2},
    ],
)
def test_reject_unsupported_or_unphysical(change):
    p = params()
    p.update(change)
    with pytest.raises(CADException):
        gear_spec(**p)


@pytest.mark.parametrize("z,angle", [(18, 20), (20, 20), (40, 20), (32, 14.5), (8, 30), (200, 30)])
def test_simple_angular_profile_and_error_bound(z, angle):
    s = gear_spec(module=2, tooth_count=z, thickness=5, pressure_angle=angle)
    points = profile_points(s)
    angles = [math.atan2(y, x) for x, y in points]
    differences = [
        (b - a) % (2 * math.pi) for a, b in zip(angles, angles[1:] + angles[:1], strict=False)
    ]
    # Radial joins can have zero angle; no edge goes backwards or winds twice.
    differences = [0 if d > 2 * math.pi - 1e-12 else d for d in differences]
    assert sum(differences) == pytest.approx(2 * math.pi)
    assert max(differences) < math.pi
    nf, nt, nr = _segment_counts(s)
    assert (
        s.base_radius
        * math.sqrt(1 + s.end_parameter**2)
        * ((s.end_parameter - s.start_parameter) / nf) ** 2
        / 8
        <= s.profile_tolerance
    )
    assert s.tip_radius * (2 * s.tip_half_angle / nt) ** 2 / 8 <= s.profile_tolerance
    assert (
        s.root_radius * ((2 * math.pi / z - 2 * s.root_half_angle) / nr) ** 2 / 8
        <= s.profile_tolerance
    )

    # Independent dense interpolation checks on actual involute segments.
    def inv(t):
        return (
            s.base_radius * (math.cos(t) + t * math.sin(t)),
            s.base_radius * (math.sin(t) - t * math.cos(t)),
        )

    for i in range(nf):
        a = s.start_parameter + (s.end_parameter - s.start_parameter) * i / nf
        b = s.start_parameter + (s.end_parameter - s.start_parameter) * (i + 1) / nf
        pa, pb = inv(a), inv(b)
        for j in range(11):
            u = j / 10
            q = inv(a + (b - a) * u)
            chord = tuple(pa[k] * (1 - u) + pb[k] * u for k in (0, 1))
            assert math.dist(q, chord) <= s.profile_tolerance * (1 + 1e-10)


def test_native_watertight_bore_caps_and_exports(tmp_path):
    k = OCPKernel()
    solid = k.spur_gear(**params())
    stats = k.inspect(solid)
    assert stats["valid"] and stats["solids"] == 1
    s = gear_spec(**params())
    # Independent integral of the nominal involute/circular outline. Cubic
    # flanks approximate it; matching the former polygon volume is incorrect.
    area = s.tooth_count * (
        s.base_radius**2 * (s.end_parameter**3 - s.start_parameter**3) / 3
        + s.tip_radius**2 * s.tip_half_angle
        + s.root_radius**2 * (math.pi / s.tooth_count - s.root_half_angle)
    )
    assert stats["volume"] == pytest.approx((area - math.pi * 2.5**2) * 5, abs=0.1)
    assert stats["faces"] < len(profile_points(s)) / 2
    topology = k.topology(solid, "gear", "spur_gear", params())
    stable = {f["id"] for f in topology if f["provenance"]["semantic_status"] == "stable"}
    assert stable == {"gear/face/cap.start", "gear/face/cap.end", "gear/face/side.bore"}
    step = tmp_path / "gear.step"
    stl = tmp_path / "gear.stl"
    k.export_step(solid, step)
    k.export_stl(solid, stl, 0.02)
    restored = k.import_step(step)
    assert k.inspect(restored)["volume"] == pytest.approx(stats["volume"], rel=1e-8)
    assert stl.stat().st_size > 100


@pytest.mark.parametrize("version", [1, 2, 3])
def test_sidecar_saved_replay_and_edit(version):
    source = document()
    saved = Document.from_json(Document.from_dict(source).to_json())
    response = process_request(
        dict(protocol_version=1, result_version=version, action="replay", document=saved.to_dict())
    )
    assert response["ok"], response
    assert response["result"]["status"] == "ok", response
    first = response["result"]["features"][0]["stats"]["volume"]
    source["parameters"]["size"] = 2.5
    changed = regenerate(Document.from_dict(source), OCPKernel())
    assert changed.ok and changed.result["features"][0]["stats"]["volume"] > first


def test_invalid_edit_blocks_export_not_last_good(tmp_path):
    source = document()
    source["features"][0]["params"]["tooth_count"] = 12
    response = process_request(
        dict(
            protocol_version=1,
            action="export_step",
            document=source,
            destination=str(tmp_path / "bad.step"),
        )
    )
    assert not response["ok"]
    assert not (tmp_path / "bad.step").exists()
