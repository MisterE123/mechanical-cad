"""Native B-rep sampled tooth overlap, never continuous contact certification."""

import importlib
import math
import sys
import types
from pathlib import Path

import pytest
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Quaternion, gp_Trsf, gp_Vec

from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.kernel_ocp import OCPKernel

ROOT = Path(__file__).resolve().parents[2]
package = types.ModuleType("mcad_native_pair")
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
build_pair = importlib.import_module(package.__name__ + ".gear_pair").build_pair


@pytest.mark.kernel
@pytest.mark.parametrize(
    "za,zb,backlash,clearance",
    [
        (20, 40, 0.2, 0.25),
        (19, 37, 0.2, 0.25),
        (20, 37, 0.2, 0.25),
        (19, 40, 0.2, 0.25),
        (18, 60, 0.0, 0.0),
        (18, 200, 0.0, 0.25),
    ],
)
def test_native_sampled_no_positive_tooth_overlap(za, zb, backlash, clearance, record_property):
    candidate = build_pair(
        teeth_a=za, teeth_b=zb, pair_backlash=backlash, clearance=clearance, profile_tolerance=0.01
    )
    assembly = AssemblyDocument.from_dict(candidate)
    kernel = OCPKernel()
    shapes = [
        kernel.spur_gear(**source["document"]["parameters"])
        for source in candidate["part_sources"][1:]
    ]
    for shape in shapes:
        assert kernel.inspect(shape)["solids"] == 1
    volumes = []
    for fraction in (0, 0.17, 0.49, 0.83):
        angle = 2 * math.pi / za * fraction
        pose = evaluate(assembly, {"shaft_a": angle}).to_dict()
        world = []
        for index, shape in enumerate(shapes, 1):
            frame = pose["transforms"][f"instance_{index}"]
            # This regression measures exact tooth overlap. Rigid-copy in OCCT
            # and independently check the B-rep, without repeating the full
            # display-mesh qualification for every static Boolean pose.
            w, x, y, z = frame["wxyz"]
            transform = gp_Trsf()
            transform.SetRotation(gp_Quaternion(x, y, z, w))
            transform.SetTranslationPart(gp_Vec(*frame["xyz_mm"]))
            placed = BRepBuilderAPI_Transform(shape, transform, True).Shape()
            assert kernel.inspect(placed)["solids"] == 1
            world.append(placed)
        operation = BRepAlgoAPI_Common(*world)
        assert operation.IsDone()
        overlap = kernel.inspect(operation.Shape())
        volumes.append(overlap["volume"])
        assert overlap["volume"] <= 1e-9, (za, zb, fraction, overlap)
    record_property("sampled_common_volumes_mm3", repr(volumes))
