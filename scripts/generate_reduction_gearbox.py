"""Author editable two-stage demonstrator; native evidence is an explicit opt-in.

Run with this checkout's src and the established native dependencies on PYTHONPATH.
Generated user files stay outside Git. No file content is executable model data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.model import Document


def f(id, kind, params=None, inputs=None, **extra):
    return dict(
        id=id,
        kind=kind,
        label=id.replace("_", " ").title(),
        params=params or {},
        inputs=inputs or {},
        **extra,
    )


def doc(id, name, p, fs):
    return Document.from_dict(
        dict(
            schema_version=1,
            id=id,
            name=name,
            units="mm",
            parameters=p,
            features=fs,
            active_feature=fs[-1]["id"],
        )
    ).to_dict()


def cylinder(fs, id, radius, x, y, z, length):
    fs.extend(
        [
            f(id + "_profile", "sketch_circle", dict(radius=radius, x=x, y=y, z=z)),
            f(id, "extrude", dict(length=length), dict(profile=id + "_profile")),
        ]
    )
    return id


def housing(*, wall=4, width=200, depth=100, spacing=60):
    p = dict(
        wall=wall,
        width=width,
        depth=depth,
        height=42,
        spacing=spacing,
        edge_radius=8,
        bore_radius=4.3,
        mount_radius=2.6,
    )
    fs = [
        f(
            "stock_profile",
            "sketch_rectangle",
            dict(width="width", height="depth", x=-30, y="-depth/2"),
        ),
        f("stock", "extrude", dict(length="height"), dict(profile="stock_profile")),
        f(
            "outer_blends",
            "fillet",
            dict(radius="edge_radius"),
            dict(base="stock"),
            edge_pairs=[
                [f"stock/face/side.x_{x}", f"stock/face/side.y_{y}"]
                for x in ("min", "max")
                for y in ("min", "max")
            ],
        ),
        f(
            "open_shell",
            "shell",
            dict(thickness="wall"),
            dict(base="outer_blends"),
            opening_faces=["stock/face/cap.end"],
        ),
    ]
    last = "open_shell"
    for i, (x, y) in enumerate([(-30, -40), (-30, 40), ("width-30", -40), ("width-30", 40)]):
        cylinder(fs, f"ear_{i}", 8, x, y, 0, 6)
        fs.append(f(f"ear_union_{i}", "union", inputs=dict(base=last, tool=f"ear_{i}")))
        last = f"ear_union_{i}"
        cylinder(fs, f"mount_hole_{i}", "mount_radius", x, y, -1, 8)
        fs.append(f(f"mount_cut_{i}", "cut", inputs=dict(base=last, tool=f"mount_hole_{i}")))
        last = f"mount_cut_{i}"
    # Four internal screw pillars support the cover, deliberately outside gears.
    for i, (x, y) in enumerate([(-20, -39), (-20, 39), ("width-40", -39), ("width-40", 39)]):
        cylinder(fs, f"pillar_{i}", 5, x, y, "wall-1", "height-wall+1")
        fs.append(f(f"pillar_union_{i}", "union", inputs=dict(base=last, tool=f"pillar_{i}")))
        last = f"pillar_union_{i}"
        cylinder(fs, f"screw_{i}", 1.7, x, y, 5, "height")
        fs.append(f(f"screw_cut_{i}", "cut", inputs=dict(base=last, tool=f"screw_{i}")))
        last = f"screw_cut_{i}"
    for i, x in enumerate((0, "spacing", "2*spacing")):
        cylinder(fs, f"bearing_{i}", "bore_radius", x, 0, -1, "wall+2")
        fs.append(f(f"bearing_cut_{i}", "cut", inputs=dict(base=last, tool=f"bearing_{i}")))
        last = f"bearing_cut_{i}"
    return doc("gearbox_housing", "Shelled housing with screw pillars and mounting ears", p, fs)


def cover(*, width=200, depth=100, spacing=60):
    p = dict(width=width, depth=depth, thickness=5, spacing=spacing, bore_radius=4.3)
    fs = [
        f(
            "plate_profile",
            "sketch_rectangle",
            dict(width="width", height="depth", x=-30, y="-depth/2"),
        ),
        f("plate", "extrude", dict(length="thickness"), dict(profile="plate_profile")),
        f(
            "cover_blends",
            "fillet",
            dict(radius=2),
            dict(base="plate"),
            edge_pairs=[
                [f"plate/face/side.x_{x}", f"plate/face/side.y_{y}"]
                for x in ("min", "max")
                for y in ("min", "max")
            ],
        ),
    ]
    last = "cover_blends"
    for i, (x, y, r) in enumerate(
        [
            (0, 0, "bore_radius"),
            ("spacing", 0, "bore_radius"),
            ("2*spacing", 0, "bore_radius"),
            (-20, -39, 2),
            (-20, 39, 2),
            ("width-40", -39, 2),
            ("width-40", 39, 2),
        ]
    ):
        cylinder(fs, f"hole_{i}", r, x, y, -1, "thickness+2")
        fs.append(f(f"hole_cut_{i}", "cut", inputs=dict(base=last, tool=f"hole_{i}")))
        last = f"hole_cut_{i}"
    return doc("gearbox_cover", "Removable bored cover", p, fs)


def gear(id, teeth):
    p = dict(
        module=2,
        tooth_count=teeth,
        thickness=8,
        bore_diameter=8.4,
        pressure_angle=20,
        backlash=0.1,
        clearance=0.25,
        profile_tolerance=0.01,
    )
    return doc(id, f"{teeth}-tooth module-2 gear", p, [f("gear", "spur_gear", {k: k for k in p})])


def shaft():
    fs = []
    cylinder(fs, "shaft", 4, 0, 0, -5, 57)
    return doc("reference_shaft", "Reference 8 mm shaft — NOT FOR PRINT", {}, fs)


def frame(x=0, y=0, z=0):
    return dict(xyz_mm=[float(x), float(y), float(z)], wxyz=[1.0, 0.0, 0.0, 0.0])


def build(*, wall=4, width=200, depth=100, spacing=60, teeth_small=20, teeth_large=40):
    docs = [
        housing(wall=wall, width=width, depth=depth, spacing=spacing),
        cover(width=width, depth=depth, spacing=spacing),
        shaft(),
        gear("pinion", teeth_small),
        gear("wheel", teeth_large),
    ]
    sources = []
    parts = []
    frames = {
        "gearbox_housing": [
            ("origin", frame()),
            ("cover", frame(z=42)),
            ("axis_input", frame()),
            ("axis_middle", frame(spacing)),
            ("axis_output", frame(2 * spacing)),
        ],
        "gearbox_cover": [("origin", frame())],
        "reference_shaft": [
            ("origin", frame()),
            ("stage_one", frame(z=8)),
            ("stage_two", frame(z=24)),
        ],
        "pinion": [("origin", frame())],
        "wheel": [("origin", frame())],
    }
    for d in docs:
        digest = hashlib.sha256(
            (json.dumps(d, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        ).hexdigest()
        sources.append(dict(source_document_id=d["id"], source_digest=digest, document=d))
        parts.append(
            dict(
                id=d["id"],
                name=d["name"],
                source_document_id=d["id"],
                source_digest=digest,
                output_feature_id=d["active_feature"],
                mate_frames=[
                    dict(id=i, name=i.replace("_", " ").title(), placement=p)
                    for i, p in frames[d["id"]]
                ],
            )
        )
    instances = [
        dict(id=i, name=n, part_id=p)
        for i, n, p in [
            ("housing", "Printable shelled housing", "gearbox_housing"),
            ("cover", "Printable removable cover", "gearbox_cover"),
            ("input_shaft", "Input shaft reference NOT FOR PRINT", "reference_shaft"),
            (
                "middle_shaft",
                "Shared intermediate shaft reference NOT FOR PRINT",
                "reference_shaft",
            ),
            ("output_shaft", "Output shaft reference NOT FOR PRINT", "reference_shaft"),
            ("input_gear", "Stage 1 input pinion", "pinion"),
            ("middle_wheel", "Stage 1 intermediate wheel", "wheel"),
            ("middle_pinion", "Stage 2 intermediate pinion", "pinion"),
            ("output_wheel", "Stage 2 output wheel", "wheel"),
        ]
    ]
    joints = []

    def joint(id, parent, child, pf, kind="fixed", coordinate=0):
        j = dict(
            id=id,
            name=id.replace("_", " ").title(),
            kind=kind,
            parent=parent,
            child=child,
            parent_frame=pf,
            child_frame="origin",
        )
        if kind != "fixed":
            j.update(coordinate=coordinate, limits=None)
        joints.append(j)

    joint("cover_fixed", "housing", "cover", "cover")
    for n in ("input", "middle", "output"):
        joint(
            n + "_rotation",
            "housing",
            n + "_shaft",
            "axis_" + n,
            "revolute",
            0 if n == "input" else None,
        )
    for id, shaft_, gear_, level in [
        ("input_gear_fixed", "input_shaft", "input_gear", "stage_one"),
        ("middle_wheel_fixed", "middle_shaft", "middle_wheel", "stage_one"),
        ("middle_pinion_fixed", "middle_shaft", "middle_pinion", "stage_two"),
        ("output_wheel_fixed", "output_shaft", "output_wheel", "stage_two"),
    ]:
        joint(id, shaft_, gear_, level)
    # Both meshes lie on +X centerlines. Shaft-local zero aligns all tooth zeros.
    a = dict(
        kind="assembly",
        assembly_schema_version=1,
        id="two_stage_reduction",
        name="Two-stage 4:1 spur reduction demonstrator",
        length_unit="mm",
        angle_unit="rad",
        part_sources=sources,
        parts=parts,
        instances=instances,
        joints=joints,
        grounded_instance="housing",
        ground=frame(),
        gear_relations=[
            dict(
                id="stage_" + str(i + 1),
                name="External stage " + str(i + 1),
                driver_joint=driver + "_rotation",
                driven_joint=driven + "_rotation",
                ratio=-teeth_small / teeth_large,
                offset_rad=math.pi + math.pi / teeth_large,
            )
            for i, (driver, driven) in enumerate([("input", "middle"), ("middle", "output")])
        ],
        verification_presets=[],
        active_verification_preset=None,
    )
    return AssemblyDocument.from_dict(a).to_dict(), docs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    a, ds = build()
    (args.out / "reduction_gearbox.mcad-assembly.json").write_text(json.dumps(a, indent=2) + "\n")
    for d in ds:
        (args.out / (d["id"] + ".mcad.json")).write_text(json.dumps(d, indent=2) + "\n")
    if args.check:
        from mechanical_cad.engine import regenerate
        from mechanical_cad.kernel_ocp import OCPKernel

        k = OCPKernel()
        reports = {}
        for d in ds:
            r = regenerate(Document.from_dict(d), k, result_version=3)
            if not r.ok:
                print(json.dumps(r.result, indent=2))
                raise RuntimeError(d["id"])
            reports[d["id"]] = k.inspect(r.shapes[d["active_feature"]])
            print(d["id"], reports[d["id"]], flush=True)
        (args.out / "initial_geometry_report.json").write_text(json.dumps(reports, indent=2) + "\n")


if __name__ == "__main__":
    main()
