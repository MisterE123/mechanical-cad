"""Native-free authored design/instance contract; native evidence is separate."""

import importlib.util
import json
import math
from pathlib import Path

from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.model import Document

spec = importlib.util.spec_from_file_location(
    "gearbox_generator", Path(__file__).parents[1] / "generate_reduction_gearbox.py"
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def test_canonical_editable_parts_and_chained_reduction():
    a, docs = generator.build()
    assembly = AssemblyDocument.from_dict(a)
    assert len(a["instances"]) == 9
    assert len(a["parts"]) == 5
    assert all(Document.from_dict(d).to_dict() == d for d in docs)
    housing = docs[0]
    assert any(f["kind"] == "shell" for f in housing["features"])
    assert any(f.get("edge_pairs") for f in housing["features"])
    assert len(housing["features"]) > 50
    initial = evaluate(assembly, {"input_rotation": 0})
    later = evaluate(assembly, {"input_rotation": math.pi})
    assert initial.status == later.status == "evaluated"
    assert math.isclose(
        later.coordinates["middle_rotation"] - initial.coordinates["middle_rotation"], -math.pi / 2
    )
    assert math.isclose(
        later.coordinates["output_rotation"] - initial.coordinates["output_rotation"], math.pi / 4
    )
    assert (
        next(i for i in a["instances"] if i["id"] == "middle_shaft")["part_id"] == "reference_shaft"
    )


def test_parameter_revision_keeps_explicit_frames_and_sources_coherent():
    a, docs = generator.build(
        wall=4.5, width=210, depth=106, spacing=63, teeth_small=21, teeth_large=42
    )
    assembly = AssemblyDocument.from_dict(a)
    assert docs[0]["parameters"]["wall"] == 4.5
    assert docs[-2]["parameters"]["tooth_count"] == 21
    assert docs[-1]["parameters"]["tooth_count"] == 42
    frame = next(f for f in a["parts"][0]["mate_frames"] if f["id"] == "axis_output")
    assert frame["placement"]["xyz_mm"] == [126, 0, 0]
    assert evaluate(assembly, {"input_rotation": 0}).status == "evaluated"


def test_checked_in_canonical_example_matches_authoring_script():
    expected = (
        Path(__file__).parents[2]
        / "examples/reduction_gearbox/reduction_gearbox.mcad-assembly.json"
    )
    assert json.loads(expected.read_text()) == generator.build()[0]
