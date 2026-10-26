"""Audit a STEP transfer API path, without assigning persistent face identity.

Run with the pinned native sidecar Python. All generated files go into a new
unique temporary directory; no input files or application sources are modified.
"""

import argparse
import hashlib
import importlib.metadata
import json
import tempfile
from pathlib import Path


def probe(output_parent=None):
    import OCP
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
    from OCP.StepShape import StepShape_FaceSurface
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    directory = Path(tempfile.mkdtemp(prefix="mcad-step-transfer-probe-", dir=output_parent))
    path = directory / "plate.step"
    writer = STEPControl_Writer()
    if (
        writer.Transfer(BRepPrimAPI_MakeBox(20, 30, 5).Shape(), STEPControl_AsIs)
        != IFSelect_RetDone
    ):
        raise RuntimeError("Fixture export transfer failed")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError("Fixture export write failed")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {
        "ocp_version": OCP.__version__,
        "packages": {
            item.metadata["Name"]: item.version
            for item in importlib.metadata.distributions()
            if "ocp" in item.metadata["Name"].lower()
        },
        "asset_sha256": digest,
        "fixture": "One native box, 20 x 30 x 5; exported once, imported twice",
        "identity_established": False,
        "runs": [],
    }
    for _ in range(2):
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Fixture bytes changed between imports")
        reader = STEPControl_Reader()
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            raise RuntimeError("Fixture read failed")
        if reader.NbRootsForTransfer() != 1:
            raise RuntimeError("Fixture does not have exactly one transferable root")
        reader.SetSystemLengthUnit(1.0)
        if not reader.TransferRoots():
            raise RuntimeError("Fixture import transfer failed")
        model = reader.StepModel()
        transfer = reader.WS().TransferReader()
        process = transfer.TransientProcess()
        faces = []
        explorer = TopExp_Explorer(reader.OneShape(), TopAbs_FACE)
        while explorer.More():
            faces.append(explorer.Current())
            explorer.Next()
        run = {"output_face_count": len(faces), "model_faces": [], "mapped_faces": []}
        for number in range(1, model.NbEntities() + 1):
            entity = model.Value(number)
            if not isinstance(entity, StepShape_FaceSurface):
                continue
            shape = transfer.ShapeResult(entity)
            run["model_faces"].append(
                {
                    # Diagnostic positions only: never proposed as persistent selectors.
                    "diagnostic_model_position": number,
                    "entity_type": type(entity).__name__,
                    "number_roundtrip": model.Number(entity),
                    "ident_label": model.IdentLabel(entity),
                    "map_index": process.MapIndex(entity),
                    "find_is_none": process.Find(entity) is None,
                    "shape_result_is_null": shape.IsNull(),
                    "exact_output_match_count": sum(
                        not shape.IsNull() and shape.IsSame(face) for face in faces
                    ),
                }
            )
        for number in range(1, process.NbMapped() + 1):
            entity = process.Mapped(number)
            if not isinstance(entity, StepShape_FaceSurface):
                continue
            binder = process.MapItem(number)
            run["mapped_faces"].append(
                {
                    "diagnostic_map_position": number,
                    "number_roundtrip": model.Number(entity),
                    "ident_label": model.IdentLabel(entity),
                    "map_index_roundtrip": process.MapIndex(entity),
                    "find_is_none": process.Find(entity) is None,
                    "shape_result_is_null": transfer.ShapeResult(entity).IsNull(),
                    "binder_python_type": type(binder).__name__,
                    "result_type_name": binder.ResultTypeName(),
                    "multiple": binder.IsMultiple(),
                    "has_next_result": binder.NextResult() is not None,
                    "execution_status": str(binder.StatusExec()),
                    "warnings": binder.Check().NbWarnings(),
                    "failures": binder.Check().NbFails(),
                }
            )
        run["mapped_count"] = process.NbMapped()
        try:
            run["shape_process_flags"] = repr(reader.GetShapeProcessFlags())
        except TypeError as error:
            run["shape_process_flags_error"] = str(error)
        run["shape_fix_parameter_count"] = reader.GetShapeFixParameters().Extent()
        result["runs"].append(run)
    report = directory / "result.json"
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Probe report: {report}", flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-parent", type=Path, help="Existing parent for a NEW output directory"
    )
    arguments = parser.parse_args()
    probe(arguments.output_parent)
