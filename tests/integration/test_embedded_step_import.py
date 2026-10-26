"""Immutable single-Part exchange data, replayed entirely in the sidecar."""

import copy

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.step_asset import MAX_STEP_BYTES, decode_step, encode_step


def step_bytes(tmp_path):
    kernel = OCPKernel()
    shape = kernel.extrude(kernel.rectangle(10, 10), 10)
    path = tmp_path / "source.step"
    kernel.export_step(shape, path)
    return path.read_bytes()


def test_embedded_step_reopen_modify_and_export_without_original_file(tmp_path):
    data = step_bytes(tmp_path)
    (tmp_path / "source.step").unlink()
    original = Document(
        "import",
        "Imported part",
        {},
        (
            Feature("part", "import_step", "Imported", {}, {}, step_data=encode_step(data)),
            Feature("moved", "transform", "Moved", {"x": 20}, {"base": "part"}),
            Feature("rounded", "fillet", "Rounded", {"radius": 1}, {"base": "moved"}),
        ),
        "rounded",
    )
    document = Document.from_json(original.to_json())
    assert decode_step(dict(document.features[0].step_data)) == data
    kernel = OCPKernel()
    replay = regenerate(document, kernel, result_version=2)
    assert replay.ok, replay.result
    imported = replay.result["features"][0]
    assert imported["stats"]["volume"] == pytest.approx(1000)
    assert all(f["provenance"]["semantic_status"] == "unknown" for f in imported["topology"])
    assert all(f["id"].startswith("snapshot:") for f in imported["topology"])
    assert kernel.manufacturing_check(replay.shapes["rounded"])["mesh"]["watertight"]
    path = tmp_path / "roundtrip.step"
    kernel.export_step(replay.shapes["rounded"], path)
    reopened = kernel.import_step_data(encode_step(path.read_bytes()))
    assert kernel.inspect(reopened)["volume"] == pytest.approx(
        replay.result["features"][-1]["stats"]["volume"]
    )


def test_step_declared_centimetres_are_converted_to_document_mm(tmp_path):
    data = step_bytes(tmp_path)
    assert b"SI_UNIT(.MILLI.,.METRE.)" in data
    data = data.replace(b"SI_UNIT(.MILLI.,.METRE.)", b"SI_UNIT(.CENTI.,.METRE.)")
    kernel = OCPKernel()
    shape = kernel.import_step_data(encode_step(data))
    assert kernel.inspect(shape)["volume"] == pytest.approx(1000000)


def test_corrupt_checksum_noncanonical_base64_and_oversize_are_rejected(tmp_path):
    asset = encode_step(step_bytes(tmp_path))
    bad = copy.deepcopy(asset)
    bad["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        decode_step(bad)
    bad = copy.deepcopy(asset)
    bad["data"] += "\n"
    with pytest.raises(ValueError, match="base64"):
        decode_step(bad)
    with pytest.raises(ValueError, match="512 KiB"):
        encode_step(b" " * (MAX_STEP_BYTES + 1))


def test_single_component_wrapper_preserves_placement_but_open_surface_rejects(tmp_path):
    kernel = OCPKernel()
    shape = kernel.extrude(kernel.rectangle(10, 20), 5)
    path = tmp_path / "assembly.step"
    kernel.export_assembly_step(
        "Assembly",
        [{"id": "p", "name": "Part", "shape": shape}],
        [
            {
                "id": "i",
                "name": "Occurrence",
                "part_id": "p",
                "frame": {"xyz_mm": [7, 11, 13], "wxyz": [2**-0.5, 0, 0, 2**-0.5]},
            }
        ],
        path,
    )
    imported = kernel.import_step_data(encode_step(path.read_bytes()))
    assert kernel.inspect(imported)["volume"] == pytest.approx(1000)
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    explorer = TopExp_Explorer(imported, TopAbs_VERTEX)
    points = []
    while explorer.More():
        point = BRep_Tool.Pnt_s(TopoDS.Vertex(explorer.Current()))
        points.append((point.X(), point.Y(), point.Z()))
        explorer.Next()
    assert [min(p[i] for p in points) for i in range(3)] == pytest.approx([-13, 11, 13])
    assert [max(p[i] for p in points) for i in range(3)] == pytest.approx([7, 21, 18])
    # Construct an external surface-only STEP file, bypassing our solid export policy.
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    writer = STEPControl_Writer()
    writer.Transfer(kernel.rectangle(10, 10), STEPControl_AsIs)
    writer.Write(str(path))
    with pytest.raises(Exception, match="solid"):
        kernel.import_step_data(encode_step(path.read_bytes()))


def test_multiple_solid_roots_are_rejected(tmp_path):
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    kernel = OCPKernel()
    box = kernel.extrude(kernel.rectangle(10, 10), 10)
    writer = STEPControl_Writer()
    writer.Transfer(box, STEPControl_AsIs)
    writer.Transfer(kernel.transform(box, x=30), STEPControl_AsIs)
    path = tmp_path / "multiple.step"
    writer.Write(str(path))
    with pytest.raises(Exception, match="one transferable|one valid solid"):
        kernel.import_step_data(encode_step(path.read_bytes()))


def test_repeated_assembly_occurrences_are_not_silently_deduplicated(tmp_path):
    kernel = OCPKernel()
    shape = kernel.extrude(kernel.rectangle(10, 10), 10)
    path = tmp_path / "repeated.step"
    kernel.export_assembly_step(
        "Repeated",
        [{"id": "p", "name": "Part", "shape": shape}],
        [
            {
                "id": str(i),
                "name": str(i),
                "part_id": "p",
                "frame": {"xyz_mm": [0, 0, 0], "wxyz": [1, 0, 0, 0]},
            }
            for i in range(2)
        ],
        path,
    )
    with pytest.raises(Exception, match="one valid solid"):
        kernel.import_step_data(encode_step(path.read_bytes()))
