"""Generate two oblique native STEP boxes for copied-plane smoke tests."""

import os

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

rotation = gp_Trsf()
rotation.SetRotation(gp_Ax1(gp_Pnt(), gp_Dir(1, 1, 0)), 0.6)
shape = BRepBuilderAPI_Transform(BRepPrimAPI_MakeBox(10, 20, 30).Shape(), rotation, True).Shape()
for name, offset in (("MCAD_COPIED_STEP", 0), ("MCAD_COPIED_STEP_CHANGED", 100)):
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(offset, offset, offset))
    writer = STEPControl_Writer()
    writer.Transfer(BRepBuilderAPI_Transform(shape, move, True).Shape(), STEPControl_AsIs)
    writer.Write(os.environ[name])
