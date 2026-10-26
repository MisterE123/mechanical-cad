"""Copy-held transient CPU pick projection, never acceptance or scene authority.

Construct only from an already guard-validated successful seed response. The
owner retains exact seed/context/fingerprint and target binding; this class does
not validate live evidence, authorize publication, or inspect foreign Blender
geometry. The owner must reject external-scene occlusion independently. All rays
and exposed geometry use world millimetres, not Blender scene units.
"""

import copy

from .assembly_bridge import fingerprint
from .assembly_insert_face_pick import (
    DEFAULT_TRIANGLE_BUDGET,
    distance_tolerance,
    pick_surface,
    resolve_surface_face,
)
from .assembly_joint_draft import transform_points
from .assembly_source_preview_contract import require_source_preview
from .assembly_validation_common import MAX_INSTANCES, MAX_PARTS, MAX_VERTICES
from .bridge import BridgeError

_IDENTITY = {"xyz_mm": [0, 0, 0], "wxyz": [1, 0, 0, 0]}


def _rows(values, label, limit):
    if type(values) is not list or not 0 < len(values) <= limit:
        raise BridgeError("Pick projection requires complete bounded " + label + ".")
    rows = {}
    for value in values:
        if type(value) is not dict or type(value.get("id")) is not str or not value["id"]:
            raise BridgeError("Pick projection has an invalid " + label + " identity.")
        if value["id"] in rows:
            raise BridgeError("Pick projection has duplicate " + label + " identities.")
        rows[value["id"]] = value
    return rows


class PickProjection:
    """Private posed mesh copies; callers receive no mutable mesh references.

    Geometry is posed/copied once at construction. Per-click CPU ray tests retain
    the helper's bounded mesh checks; no mesh traversal occurs from drawing.
    Target-only mode is an explicit isolation choice, never an automatic fallback.
    """

    __slots__ = ("_meshes", "_budget")

    def __init__(self, response, expected_seed_digest, candidate, *, triangle_budget=24000):
        if type(triangle_budget) is not int or not 1 <= triangle_budget <= DEFAULT_TRIANGLE_BUDGET:
            raise BridgeError("Pick projection requires a total triangle budget of at most 24000.")
        try:
            # Retain only bounded per-instance geometry below, not a second
            # copy of potentially large source feature replay histories.
            require_source_preview(response, expected_seed_digest)
            result = response["result"]
            if type(candidate) is not dict or fingerprint(
                result["canonical_assembly"]
            ) != fingerprint(candidate):
                raise BridgeError("Pick projection does not match the exact insertion candidate.")
            instances = _rows(result["instances"], "instances", MAX_INSTANCES)
            expected_instances = _rows(candidate["instances"], "candidate instances", MAX_INSTANCES)
            if fingerprint(result["instances"]) != fingerprint(candidate["instances"]):
                raise BridgeError("Pick projection instance mapping differs from the candidate.")
            parts = _rows(result["parts"], "parts", MAX_PARTS)
            expected_parts = _rows(candidate["parts"], "candidate parts", MAX_PARTS)
            if set(parts) != set(expected_parts):
                raise BridgeError("Pick projection does not contain every exact candidate part.")
            pose = response["report"]["base_pose"]
            transforms = pose["transforms"]
            if (
                pose.get("status") != "evaluated"
                or type(transforms) is not dict
                or set(transforms) != set(expected_instances)
            ):
                raise BridgeError("Pick projection requires a complete evaluated instance pose.")
            triangles = vertices = 0
            for instance in instances.values():
                part_id = instance["part_id"]
                if type(part_id) is not str or part_id not in parts:
                    raise BridgeError("Pick projection instance has no exact candidate part.")
                mesh = parts[part_id]["mesh"]
                if (
                    type(mesh) is not dict
                    or type(mesh.get("triangles")) is not list
                    or type(mesh.get("vertices")) is not list
                ):
                    raise BridgeError("Pick projection requires complete candidate meshes.")
                triangles += len(mesh["triangles"])
                vertices += len(mesh["vertices"])
            if triangles > triangle_budget or vertices > MAX_VERTICES:
                raise BridgeError("All-instance pick projection exceeds its total mesh budget.")
            meshes = {}
            for identifier, instance in instances.items():
                part = copy.deepcopy(parts[instance["part_id"]])
                part["mesh"]["vertices"] = transform_points(
                    transforms[identifier], part["mesh"]["vertices"]
                )
                # Validate every geometric blocker up front, without qualifying
                # semantic faces. The arbitrary ray result is deliberately unused.
                pick_surface(part, _IDENTITY, [0, 0, 0], [1, 0, 0], max_triangles=triangle_budget)
                meshes[identifier] = part
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise BridgeError("Invalid insertion pick projection: " + str(exc)) from exc
        self._meshes, self._budget = meshes, triangle_budget

    def target_geometry(self, target_id):
        """Return immutable posed vertices/triangles for an optional highlight."""
        if type(target_id) is not str or target_id not in self._meshes:
            raise BridgeError("Pick target is not an exact candidate instance.")
        mesh = self._meshes[target_id]["mesh"]
        return tuple(tuple(v) for v in mesh["vertices"]), tuple(tuple(t) for t in mesh["triangles"])

    def pick(self, target_id, origin_mm, direction, *, target_only=False):
        """Choose geometry across all instances first, then qualify this target.

        No hit on any tested surface returns None. Any nearer/tied non-target
        surface refuses, including coincident reuse instances and curved faces.
        Explicit target_only ignores other candidate geometry but never relaxes
        the selected target's nearest surface/semantic-face checks.
        """
        if type(target_only) is not bool:
            raise BridgeError("Target-only picking must be an explicit boolean choice.")
        if type(target_id) is not str or target_id not in self._meshes:
            raise BridgeError("Pick target is not an exact candidate instance.")
        hits = {}
        for identifier, part in self._meshes.items():
            if target_only and identifier != target_id:
                continue
            hit = pick_surface(part, _IDENTITY, origin_mm, direction, max_triangles=self._budget)
            if hit is not None:
                hits[identifier] = hit
        if not hits:
            return None
        target = hits.get(target_id)
        if target is None:
            raise BridgeError("Pointer hits a different component. Pick the selected target.")
        if any(
            identifier != target_id
            and hit.distance_mm <= target.distance_mm + distance_tolerance(target.distance_mm)
            for identifier, hit in hits.items()
        ):
            raise BridgeError(
                "Another component occludes or overlaps the target. Isolate it explicitly to pick."
            )
        face_id = resolve_surface_face(self._meshes[target_id], target)
        return {
            "instance_id": target_id,
            "face_id": face_id,
            "point_mm": target.point_mm,
            "distance_mm": target.distance_mm,
        }
