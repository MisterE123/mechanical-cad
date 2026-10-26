"""Run with the sidecar Python before the two native Blender STEP smoke scripts."""

from pathlib import Path

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

for name, count in (("valid", 1), ("multiple", 2)):
    writer = STEPControl_Writer()
    for index in range(count):
        writer.Transfer(BRepPrimAPI_MakeBox(10 + 10 * index, 20, 30).Shape(), STEPControl_AsIs)
    writer.Write("/tmp/mcad_import_" + name + ".step")
Path("/tmp/mcad_import_bad.step").write_bytes(b"not STEP")
Path("/tmp/mcad_import_oversize.step").write_bytes(b"X" * (512 * 1024 + 1))
