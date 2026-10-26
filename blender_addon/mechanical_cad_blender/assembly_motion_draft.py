"""Detached independent revolute/slider motion intent, never a pose evaluator.

Only the selected scalar changes. The sidecar resolves frames and evaluates the
whole assembly, including gear-coupled branches, before anything can be shown.
"""

import copy
import math

from .assembly_coordinates import coordinate_specs
from .assembly_gears import controlling_joint, saved_coordinates


class MotionDraft:
    def __init__(self, assembly, joint_id):
        self._assembly = copy.deepcopy(assembly)
        joints = {joint["id"]: joint for joint in assembly["joints"]}
        if joint_id not in joints:
            raise ValueError("Select an existing independent revolute or slider driver.")
        joint = joints[joint_id]
        if joint["kind"] not in {"revolute", "slider"}:
            raise ValueError("Viewport driver motion supports independent revolute or slider joints only.")
        if joint["coordinate"] is None:
            if joint["kind"] == "slider":
                raise ValueError("Slider displacement requires an independent numeric coordinate.")
            driver = joints[controlling_joint(assembly, joint_id)]
            raise ValueError(
                "This angle is gear-controlled (read-only). Preview driver: " + driver["name"]
            )
        self.joint_id = joint_id
        self.parent_id, self.child_id = joint["parent"], joint["child"]
        self.name, self.kind = joint["name"], joint["kind"]
        self.coordinate = joint["coordinate"]
        self.candidate()

    def candidate(self):
        value = self.coordinate
        candidate = copy.deepcopy(self._assembly)
        joint = next(j for j in candidate["joints"] if j["id"] == self.joint_id)
        bound = coordinate_specs(joint)[self.joint_id][2]
        label, unit = ("Driver angle", "radians") if joint["kind"] == "revolute" else ("Slider displacement", "mm")
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > bound:
            raise ValueError(f"{label} must be finite and within ±{bound:.0f} {unit}.")
        limits = joint.get("limits")
        if limits is not None and not limits[0] <= value <= limits[1]:
            raise ValueError(f"{label} is outside its authored limits.")
        joint["coordinate"] = value
        if saved_coordinates(candidate) is None:
            raise ValueError(
                "Driver angle puts a gear-controlled joint outside its limits or range."
            )
        return candidate

    def effective_coordinates(self):
        return saved_coordinates(self.candidate())
