"""Assembly STEP hierarchy and exact placed solids; native imports stay test-local."""

from __future__ import annotations

import ast
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def frame(xyz=(0, 0, 0), wxyz=(1, 0, 0, 0)):
    return {"xyz_mm": list(xyz), "wxyz": list(wxyz)}


def _detached_adapter():
    """Run only the actual adapter's validation against no native imports/handles."""
    source = ROOT / "src/mechanical_cad/kernel_ocp.py"
    tree = ast.parse(source.read_text())
    helpers = {"KernelError", "_query_number", "_profile_plane", "_assembly_step_inputs"}
    nodes = [node for node in tree.body if getattr(node, "name", None) in helpers]
    kernel = next(node for node in tree.body if getattr(node, "name", None) == "OCPKernel")
    method = next(
        node for node in kernel.body if getattr(node, "name", None) == "export_assembly_step"
    )
    nodes.append(method)
    namespace = {"math": math, "Path": Path}
    prefix = ast.parse("from __future__ import annotations").body
    exec(compile(ast.Module(body=prefix + nodes, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("duplicate_part", "Duplicate.*Part"),
        ("duplicate_instance", "Duplicate.*instance"),
        ("missing_part", "Missing.*Part"),
        ("unknown_part_field", "Part fields"),
        ("unknown_instance_field", "instance fields"),
        ("bad_quaternion", "unit length"),
        ("nonfinite_translation", "finite"),
        ("boolean_translation", "finite number"),
        ("extra_frame_field", "exactly"),
        ("empty_instances", "1-16 instance"),
        ("invalid_name", "nonempty text"),
    ],
)
@pytest.mark.parametrize("exists", [False, True])
def test_invalid_records_reject_before_native_work_or_destination_write(
    tmp_path, mutation, match, exists
):
    adapter = _detached_adapter()
    parts = [{"id": "p", "name": "Part", "shape": object()}]
    instances = [{"id": "i", "name": "Instance", "part_id": "p", "frame": frame()}]
    if mutation == "duplicate_part":
        parts.append(dict(parts[0]))
    elif mutation == "duplicate_instance":
        instances.append(dict(instances[0]))
    elif mutation == "missing_part":
        instances[0]["part_id"] = "missing"
    elif mutation == "unknown_part_field":
        parts[0]["extra"] = True
    elif mutation == "unknown_instance_field":
        instances[0]["extra"] = True
    elif mutation == "bad_quaternion":
        instances[0]["frame"]["wxyz"] = [0.5, 0, 0, 0]
    elif mutation == "nonfinite_translation":
        instances[0]["frame"]["xyz_mm"][0] = float("nan")
    elif mutation == "boolean_translation":
        instances[0]["frame"]["xyz_mm"][0] = True
    elif mutation == "extra_frame_field":
        instances[0]["frame"]["scale"] = 2
    elif mutation == "empty_instances":
        instances.clear()
    elif mutation == "invalid_name":
        instances[0]["name"] = "invalid\x00name"
    path = tmp_path / "assembly.step"
    if exists:
        path.write_bytes(b"untouched destination")
    # No kernel object, shape type or native import is available to this method.
    # Reaching solid validation/transfer would itself fail these pure controls.
    with pytest.raises(adapter["KernelError"], match=match):
        adapter["export_assembly_step"](None, "Assembly", parts, instances, path)
    assert path.read_bytes() == b"untouched destination" if exists else not path.exists()


def _read_assembly(path):
    from OCP.collections import Sequence_TDF_Label
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    document = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    XCAFDoc_DocumentTool.SetLengthUnit_s(document, 0.001)
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    assert reader.ReadFile(str(path)) == IFSelect_RetDone
    assert reader.Transfer(document)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    roots = Sequence_TDF_Label()
    shapes.GetFreeShapes(roots)
    assert roots.Length() == 1
    root = roots.Value(1)
    assert XCAFDoc_ShapeTool.IsAssembly_s(root)

    def name(label):
        attribute = TDataStd_Name()
        assert label.FindAttribute(TDataStd_Name.GetID_s(), attribute)
        return attribute.Get().ToExtString()

    components = Sequence_TDF_Label()
    assert XCAFDoc_ShapeTool.GetComponents_s(root, components)
    occurrences = {}
    for index in range(1, components.Length() + 1):
        component = components.Value(index)
        assert XCAFDoc_ShapeTool.IsReference_s(component)
        definition = TDF_Label()
        assert XCAFDoc_ShapeTool.GetReferredShape_s(component, definition)
        assert XCAFDoc_ShapeTool.IsSimpleShape_s(definition)
        occurrences[name(component)] = {
            "label": definition,
            "name": name(definition),
            "shape": XCAFDoc_ShapeTool.GetShape_s(component),
            "local_shape": XCAFDoc_ShapeTool.GetShape_s(definition),
            "location": XCAFDoc_ShapeTool.GetLocation_s(component).Transformation(),
        }
    assert len(occurrences) == components.Length()
    return document, name(root), occurrences


@pytest.mark.kernel
def test_step_roundtrip_preserves_two_definitions_three_named_rigid_instances(tmp_path):
    pytest.importorskip("OCP")
    from mechanical_cad.kernel_ocp import OCPKernel, _shape_bounds
    from mechanical_cad.sketch_model import Arc, Line, Point, Sketch

    kernel = OCPKernel()
    box = kernel.extrude(kernel.rectangle(10, 6), 4)
    sketch = Sketch(
        "quadrant",
        (Point("center", 0, 0), Point("start", 5, 0), Point("end", 0, 5)),
        (Line("first_radius", "center", "start"), Line("second_radius", "center", "end")),
        (),
        schema_version=3,
        arcs=(Arc("quarter_arc", "center", "start", "end", "ccw"),),
    )
    sector = kernel.extrude_sector(kernel.sector_profile(sketch), 3)
    parts = [
        {"id": "base_part", "name": "Base definition", "shape": box},
        {"id": "sector_part", "name": "Sector definition", "shape": sector},
    ]
    q = math.sqrt(0.5)
    instances = [
        {
            "id": "base",
            "name": "Base occurrence",
            "part_id": "base_part",
            "frame": frame((2, -4, 5)),
        },
        {
            "id": "sector_a",
            "name": "Sector A",
            "part_id": "sector_part",
            "frame": frame((20, 10, 2), (q, 0, 0, q)),
        },
        {
            "id": "sector_b",
            "name": "Sector B",
            "part_id": "sector_part",
            "frame": SimpleNamespace(xyz_mm=(0, 20, 10), wxyz=(q, q, 0, 0)),
        },
    ]
    before = [(kernel.inspect(part["shape"]), _shape_bounds(part["shape"])) for part in parts]
    path = tmp_path / "box_sector.step"
    assert kernel.export_assembly_step("Named reusable assembly", parts, instances, path) is None
    assert path.is_file() and path.stat().st_size > 0
    assert list(tmp_path.iterdir()) == [path]  # One STEP file, no external Part files.
    document, assembly_name, imported = _read_assembly(path)
    assert document is not None and assembly_name == "Named reusable assembly"
    assert set(imported) == {"Base occurrence", "Sector A", "Sector B"}
    assert imported["Sector A"]["label"].IsEqual(imported["Sector B"]["label"])
    assert not imported["Sector A"]["label"].IsEqual(imported["Base occurrence"]["label"])
    assert {row["name"] for row in imported.values()} == {"Base definition", "Sector definition"}
    expected = {
        "Base occurrence": (240, (2, -4, 5, 12, 2, 9), (1, 0, 0, 2, 0, 1, 0, -4, 0, 0, 1, 5)),
        "Sector A": (
            75 * math.pi / 4,
            (15, 10, 2, 20, 15, 5),
            (0, -1, 0, 20, 1, 0, 0, 10, 0, 0, 1, 2),
        ),
        "Sector B": (
            75 * math.pi / 4,
            (0, 17, 10, 5, 20, 15),
            (1, 0, 0, 0, 0, 0, -1, 20, 0, 1, 0, 10),
        ),
    }
    for name, (volume, bounds, matrix) in expected.items():
        row = imported[name]
        stats = kernel.inspect(row["shape"])
        assert stats["valid"] and stats["solids"] == 1
        assert stats["volume"] == pytest.approx(volume, rel=1e-9)
        assert _shape_bounds(row["shape"]) == pytest.approx(bounds, abs=1e-7)
        location = tuple(row["location"].Value(i, j) for i in range(1, 4) for j in range(1, 5))
        assert location == pytest.approx(matrix, abs=1e-9)
        assert kernel.inspect(row["local_shape"])["volume"] == pytest.approx(volume, rel=1e-9)
    assert _shape_bounds(imported["Sector A"]["local_shape"]) == pytest.approx(
        (0, 0, 0, 5, 5, 3), abs=1e-7
    )
    flat = kernel.import_step(path)
    assert kernel.inspect(flat)["solids"] == 3
    assert kernel.inspect(flat)["volume"] == pytest.approx(240 + 150 * math.pi / 4, rel=1e-9)
    assert _shape_bounds(flat) == pytest.approx((0, -4, 2, 20, 20, 15), abs=1e-7)
    assert [
        (kernel.inspect(part["shape"]), _shape_bounds(part["shape"])) for part in parts
    ] == before


@pytest.mark.kernel
def test_unused_definition_is_not_an_extra_free_solid(tmp_path):
    pytest.importorskip("OCP")
    from mechanical_cad.kernel_ocp import OCPKernel

    kernel = OCPKernel()
    shape = kernel.extrude(kernel.rectangle(2, 3), 4)
    unused = kernel.extrude(kernel.rectangle(7, 8), 9)
    path = tmp_path / "assembly.step"
    kernel.export_assembly_step(
        "One occurrence",
        [
            {"id": "p", "name": "Used", "shape": shape},
            {"id": "u", "name": "Unused", "shape": unused},
        ],
        [{"id": "i", "name": "Only instance", "part_id": "p", "frame": frame()}],
        path,
    )
    document, name, instances = _read_assembly(path)
    assert document is not None and name == "One occurrence"
    assert set(instances) == {"Only instance"}
    assert instances["Only instance"]["name"] == "Used"
    assert kernel.inspect(kernel.import_step(path))["volume"] == pytest.approx(24)


@pytest.mark.kernel
def test_invalid_unused_solid_rejects_without_writing(tmp_path):
    pytest.importorskip("OCP")
    from mechanical_cad.kernel_ocp import KernelError, OCPKernel

    kernel = OCPKernel()
    shape = kernel.extrude(kernel.rectangle(2, 3), 4)
    path = tmp_path / "existing.step"
    path.write_bytes(b"untouched destination")
    with pytest.raises(KernelError, match="exactly one valid solid"):
        kernel.export_assembly_step(
            "Invalid unused definition",
            [
                {"id": "p", "name": "Used", "shape": shape},
                {"id": "u", "name": "Invalid", "shape": kernel.rectangle(7, 8)},
            ],
            [{"id": "i", "name": "Only instance", "part_id": "p", "frame": frame()}],
            path,
        )
    assert path.read_bytes() == b"untouched destination"


@pytest.mark.kernel
@pytest.mark.parametrize("shared_definition", [False, True])
@pytest.mark.parametrize("coincident", [False, True])
def test_definition_ids_and_occurrences_are_not_inferred_from_shape_identity(
    tmp_path, monkeypatch, shared_definition, coincident
):
    pytest.importorskip("OCP")
    import OCP.BRepBuilderAPI
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    from mechanical_cad.kernel_ocp import OCPKernel, _shape_bounds, _subshapes

    kernel = OCPKernel()
    shape = kernel.extrude(kernel.rectangle(2, 3), 4)
    before = (kernel.inspect(shape), _shape_bounds(shape))
    copies = []
    original_copy = OCP.BRepBuilderAPI.BRepBuilderAPI_Copy

    def observed_copy(original, copy_geometry, copy_mesh):
        assert copy_geometry is False and copy_mesh is False
        builder = original_copy(original, copy_geometry, copy_mesh)
        copies.append((original, builder))
        return builder

    monkeypatch.setattr(OCP.BRepBuilderAPI, "BRepBuilderAPI_Copy", observed_copy)
    parts = [{"id": "a", "name": "Definition A", "shape": shape}]
    if not shared_definition:
        # The service can reuse one replay handle for distinct Part definitions.
        parts.append({"id": "b", "name": "Definition B", "shape": shape})
    path = tmp_path / "identity.step"
    kernel.export_assembly_step(
        "Explicit identity",
        parts,
        [
            {"id": "first", "name": "First", "part_id": "a", "frame": frame()},
            {
                "id": "second",
                "name": "Second",
                "part_id": "a" if shared_definition else "b",
                "frame": frame((0 if coincident else 10, 0, 0)),
            },
        ],
        path,
    )
    document, name, instances = _read_assembly(path)
    assert document is not None and name == "Explicit identity"
    assert set(instances) == {"First", "Second"}
    assert instances["First"]["label"].IsEqual(instances["Second"]["label"]) is shared_definition
    assert instances["First"]["name"] == "Definition A"
    assert instances["Second"]["name"] == ("Definition A" if shared_definition else "Definition B")
    assert all(
        kernel.inspect(row["shape"])["volume"] == pytest.approx(24) for row in instances.values()
    )
    assert (kernel.inspect(shape), _shape_bounds(shape)) == before
    assert len(copies) == (0 if shared_definition else 1)
    for original, builder in copies:
        copied = builder.Shape()
        assert not copied.IsPartner(original)
        assert copied.Location().IsEqual(original.Location())
        assert copied.Orientation() == original.Orientation()
        assert (kernel.inspect(copied), _shape_bounds(copied)) == before
        # The overload with an explicit location returns the underlying native
        # surface, not a freshly transformed surface for a located face.
        for face in _subshapes(original, TopAbs_FACE):
            original_location, copied_location = TopLoc_Location(), TopLoc_Location()
            surface = BRep_Tool.Surface_s(TopoDS.Face(face), original_location)
            mapped_surface = BRep_Tool.Surface_s(
                TopoDS.Face(builder.ModifiedShape(face)), copied_location
            )
            assert mapped_surface is surface
            assert copied_location.IsEqual(original_location)
        for edge in _subshapes(original, TopAbs_EDGE):
            original_location, copied_location = TopLoc_Location(), TopLoc_Location()
            curve = BRep_Tool.Curve_s(TopoDS.Edge(edge), original_location, 0.0, 0.0)
            mapped_curve = BRep_Tool.Curve_s(
                TopoDS.Edge(builder.ModifiedShape(edge)), copied_location, 0.0, 0.0
            )
            assert mapped_curve is curve
            assert copied_location.IsEqual(original_location)
