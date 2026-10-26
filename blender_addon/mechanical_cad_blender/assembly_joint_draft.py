"""Detached visual joint candidates and non-authoritative rigid previews.

The accepted pose is supplied by the guarded owner. This module neither reads
Blender objects nor certifies geometry. Every Apply still needs fresh sidecar
validation and the existing atomic Assembly publication transaction.
"""

from __future__ import annotations

import copy
import math

from .assembly_coordinates import EXTRA_COORDINATES, NO_SCALAR_COORDINATE, extra_names
from .assembly_edit import identity, origin_frame
from .assembly_frame_evidence import face_frame
from .assembly_validation_common import MAX_FRAMES, MAX_VERTICES, _frame, _number, _text
from .bridge import BridgeError

JOINT_KINDS = {"fixed", "slider", "revolute", "cylindrical", "planar", "spherical"}


def _checked_frame(frame):
    try:
        _frame(frame)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise BridgeError("Connector requires a finite, bounded literal unit frame.") from exc
    return copy.deepcopy(frame)


def _finite(value, label, *, bound=1e6):
    try:
        return _number(value, bound=bound)
    except (ValueError, TypeError, OverflowError) as exc:
        raise BridgeError(f"{label} must be finite and within +/-{bound:g}.") from exc


def _quaternion(value):
    _checked_frame({"xyz_mm": [0.0, 0.0, 0.0], "wxyz": list(value)})
    length = math.sqrt(sum(v * v for v in value))
    return [v / length for v in value]


def _multiply(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return [
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ]


def rotate(wxyz, point):
    """Rotate a finite vector using double precision and a temporary unit value."""
    try:
        if len(point) != 3:
            raise ValueError("Expected three coordinates.")
        p = [_finite(v, "Vector component", bound=1e100) for v in point]
        w, x, y, z = q = _quaternion(wxyz)
    except (TypeError, ValueError) as exc:
        raise BridgeError("Rotation requires a unit WXYZ quaternion and three numbers.") from exc
    return _multiply(_multiply(q, [0.0, *p]), [w, -x, -y, -z])[1:]


def transform_points(frame, points):
    """Bounded display-only batch; validate the frame once for a whole mesh."""
    frame = _checked_frame(frame)
    if type(points) not in (list, tuple) or len(points) > MAX_VERTICES:
        raise BridgeError("Connector preview requires at most 100,000 finite mesh points.")
    w, x, y, z = _quaternion(frame["wxyz"])
    matrix = (
        (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
    )
    result = []
    for point in points:
        if type(point) not in (list, tuple) or len(point) != 3:
            raise BridgeError("Connector preview mesh points require three finite coordinates.")
        a, b, c = [_finite(v, "Mesh point component", bound=1e100) for v in point]
        result.append(
            [
                row[0] * a + row[1] * b + row[2] * c + offset
                for row, offset in zip(matrix, frame["xyz_mm"], strict=True)
            ]
        )
    return result


def _compose(a, b):
    """Unbounded intermediate translation; only completed frames are bounded."""
    q = _multiply(_quaternion(a["wxyz"]), _quaternion(b["wxyz"]))
    offset = rotate(a["wxyz"], b["xyz_mm"])
    return {
        "xyz_mm": [x + y for x, y in zip(a["xyz_mm"], offset, strict=True)],
        "wxyz": q,
    }


def _inverse(frame):
    w, x, y, z = _quaternion(frame["wxyz"])
    q = [w, -x, -y, -z]
    return {"xyz_mm": rotate(q, [-v for v in frame["xyz_mm"]]), "wxyz": q}


def compose(a, b):
    """Compose two literal frames, bounding the completed result."""
    return _checked_frame(_compose(_checked_frame(a), _checked_frame(b)))


def inverse(frame):
    return _checked_frame(_inverse(_checked_frame(frame)))


def world_to_local(instance_world, connector_world):
    """Convert from accepted world mm into literal definition-local coordinates."""
    return _checked_frame(
        _compose(_inverse(_checked_frame(instance_world)), _checked_frame(connector_world))
    )


def local_to_world(instance_world, connector_local):
    return compose(instance_world, connector_local)


def _axis(axis):
    if type(axis) is int and 0 <= axis <= 2:
        return axis
    if type(axis) is str and axis.upper() in {"X", "Y", "Z"}:
        return "XYZ".index(axis.upper())
    raise BridgeError("Choose the X, Y or Z connector axis.")


def quarter_turn(frame, axis, turns=1):
    """Rotate about a connector-local axis, preserving its position."""
    result = _checked_frame(frame)
    index = _axis(axis)
    if type(turns) is not int or abs(turns) > 1_000_000:
        raise BridgeError("Quarter turns require a bounded integer.")
    turns %= 4
    if not turns:
        return result
    half = turns * math.pi / 4
    rotation = [math.cos(half), 0.0, 0.0, 0.0]
    rotation[index + 1] = math.sin(half)
    result["wxyz"] = _multiply(_quaternion(result["wxyz"]), rotation)
    return _checked_frame(result)


def axis_orientation(axis):
    """Orient connector +Z along a signed instance-local cardinal direction."""
    if type(axis) is not str:
        raise BridgeError("Choose +X, -X, +Y, -Y, +Z or -Z.")
    axis = axis.upper()
    h = math.sqrt(0.5)
    choices = {
        "X": [h, 0.0, h, 0.0],
        "+X": [h, 0.0, h, 0.0],
        "-X": [h, 0.0, -h, 0.0],
        "Y": [h, -h, 0.0, 0.0],
        "+Y": [h, -h, 0.0, 0.0],
        "-Y": [h, h, 0.0, 0.0],
        "Z": [1.0, 0.0, 0.0, 0.0],
        "+Z": [1.0, 0.0, 0.0, 0.0],
        "-Z": [0.0, 1.0, 0.0, 0.0],
    }
    if axis not in choices:
        raise BridgeError("Choose +X, -X, +Y, -Y, +Z or -Z.")
    return choices[axis]


def surface_frame(point_mm, normal):
    """Literal snapshot frame: +Z follows a sampled display surface normal.

    No face identity or persistent attachment is stored. Tessellated normals are
    suggestions; users can adjust coordinates/orientation before Apply.
    """
    point = [_finite(v, "Surface point") for v in point_mm]
    vector = [_finite(v, "Surface normal") for v in normal]
    if len(point) != 3 or len(vector) != 3:
        raise BridgeError("Surface point and normal require three coordinates.")
    length = math.sqrt(sum(v * v for v in vector))
    if length < 1e-12:
        raise BridgeError("The sampled surface normal is degenerate.")
    x, y, z = [v / length for v in vector]
    if z < -1 + 1e-12:
        quaternion = [0.0, 1.0, 0.0, 0.0]
    else:
        quaternion = _quaternion(
            [math.sqrt((1 + z) / 2), -y / math.sqrt(2 * (1 + z)), x / math.sqrt(2 * (1 + z)), 0.0]
        )
    return _checked_frame({"xyz_mm": point, "wxyz": quaternion})


def motion_frame(joint):
    motion = origin_frame()
    angle = joint.get(
        "rotation", joint.get("coordinate", 0.0) if joint["kind"] == "revolute" else 0.0
    )
    if joint["kind"] in {"revolute", "cylindrical", "planar", "spherical"}:
        motion["wxyz"] = [math.cos(angle / 2), 0.0, 0.0, math.sin(angle / 2)]
    if joint["kind"] in {"slider", "cylindrical"}:
        motion["xyz_mm"][2] = joint.get("coordinate", 0.0)
    elif joint["kind"] == "planar":
        motion["xyz_mm"] = [joint["translation_x"], joint["translation_y"], 0.0]
    elif joint["kind"] == "spherical":
        x, y = joint["rotation_x"] / 2, joint["rotation_y"] / 2
        motion["wxyz"] = _multiply(
            motion["wxyz"],
            _multiply([math.cos(y), 0, math.sin(y), 0], [math.cos(x), math.sin(x), 0, 0]),
        )
    return motion


class JointDraft:
    """One child incoming-edge edit bound to detached accepted Assembly data.

    Existing instances already form a rooted tree. A placement replaces the
    child's existing incoming edge, retaining its stable joint ID. Shared frame
    edits are copy-on-write so unrelated reused instances cannot move.
    """

    def __init__(self, assembly, transforms, parent_id, child_id, joint_id=None, *, parts=None):
        if assembly.get("gear_relations"):
            raise BridgeError(
                "Gear-coupled assemblies use named Mate Frame edits and joint angle dialogs; "
                "visual connector editing is unavailable. Use Preview Driver Motion for independent angles."
            )
        self._original = copy.deepcopy(assembly)
        self._transforms = copy.deepcopy(transforms)
        self._parent_id, self._child_id = parent_id, child_id
        self._instances = {i["id"]: i for i in self._original["instances"]}
        self._parts = {p["id"]: p for p in self._original["parts"]}
        if parent_id not in self._instances or child_id not in self._instances:
            raise BridgeError("Choose two existing Assembly instances.")
        if parent_id == child_id:
            raise BridgeError("Choose two distinct Assembly instances.")
        if child_id == self._original["grounded_instance"]:
            raise BridgeError("The grounded root cannot be a joint child.")
        if set(self._transforms) != set(self._instances):
            raise BridgeError("Visual placement requires a complete accepted instance pose.")
        for placement in self._transforms.values():
            _checked_frame(placement)
        joints = self._original["joints"]
        incoming = [j for j in joints if j["child"] == child_id]
        if len(incoming) != 1:
            raise BridgeError("The selected child requires exactly one existing incoming joint.")
        self._joint = incoming[0]
        if joint_id is not None and joint_id != self._joint["id"]:
            raise BridgeError("The selected joint is not the child's incoming joint.")
        descendants = {child_id}
        for _ in self._instances:
            descendants.update(j["child"] for j in joints if j["parent"] in descendants)
        if parent_id in descendants:
            raise BridgeError("The parent cannot lie inside the child's descendant subtree.")
        self._subtree_ids = tuple(i for i in self._instances if i in descendants)
        self._joint_id = self._joint["id"]
        self.name = self._joint["name"]
        self._frame_sources = {}
        self._evidence = copy.deepcopy(parts or {})
        self._supports = {"parent": None, "child": None}
        self._generated = {end: identity("frame") for end in ("parent", "child")}
        self.extra_coordinates = {
            name: copy.deepcopy(self._joint.get(name, 0.0))
            for names in EXTRA_COORDINATES.values()
            for name in names
        }
        self.extra_limits = {
            name: copy.deepcopy(self._joint.get(name + "_limits"))
            for name in self.extra_coordinates
        }
        same_pair = self._joint["parent"] == parent_id
        if same_pair:
            self.kind = self._joint["kind"]
            self.coordinate = self._joint.get("coordinate", 0.0)
            self.limits = copy.deepcopy(self._joint.get("limits"))
            for end in ("parent", "child"):
                part = self._part(end)
                frame_id = self._joint[end + "_frame"]
                frame = next((f for f in part["mate_frames"] if f["id"] == frame_id), None)
                if frame is None:
                    raise BridgeError("The incoming joint references a missing literal frame.")
                self._frame_sources[end] = frame_id
                placement = frame["placement"]
                if "support_face" in frame:
                    support = self._support(end, frame["support_face"])
                    self._supports[end] = support
                    placement = compose(face_frame(support["signature"]), placement)
                setattr(self, end + "_frame", _checked_frame(placement))
        else:
            # Preserve the existing motion and accepted child pose on reparent.
            # Offset the new parent connector by the inverse authored motion.
            self.kind = self._joint["kind"]
            self.coordinate = self._joint.get("coordinate", 0.0)
            self.limits = copy.deepcopy(self._joint.get("limits"))
            self.parent_frame = compose(
                world_to_local(self._transforms[parent_id], self._transforms[child_id]),
                inverse(motion_frame(self._joint)),
            )
            self.child_frame = origin_frame()
            self._frame_sources = {"parent": None, "child": None}
        self._initial_frames = {
            end: copy.deepcopy(getattr(self, end + "_frame")) for end in ("parent", "child")
        }

        self._initial_supports = copy.deepcopy(self._supports)

    def _support(self, end, face_id):
        row = self._evidence.get(self._part(end)["id"], {})
        matches = [face for face in row.get("topology", []) if face.get("id") == face_id]
        if len(matches) != 1:
            raise BridgeError(
                "Face attachment has no current unambiguous replay evidence. Rebuild Assembly."
            )
        face = matches[0]
        if face.get("provenance", {}).get("semantic_status") != "stable":
            raise BridgeError(
                "This face has no stable semantic identity; use literal placement instead."
            )
        if face.get("signature", {}).get("surface") != "plane":
            raise BridgeError(
                "Mate by Faces requires a planar face; use literal placement for curved faces."
            )
        face_frame(face["signature"])
        return copy.deepcopy(face)

    def attach_face(self, end, face_id, *, preserve_offset=False):
        end = self._end(end)
        support = self._support(end, face_id)
        offset = origin_frame()
        if preserve_offset and self._supports[end] is not None:
            offset = world_to_local(
                face_frame(self._supports[end]["signature"]), getattr(self, end + "_frame")
            )
        self._supports[end] = support
        setattr(self, end + "_frame", compose(face_frame(support["signature"]), offset))

    def attach_face_pair(self, parent_face, child_face):
        """New contact pair: centroids coincide and outward normals oppose.

        This is an explicit authoring default, not collision/contact verification.
        Existing joints reopen without invoking this initialization.
        """
        self.attach_face("parent", parent_face)
        self.attach_face("child", child_face)
        self.turn_connector("child", "X", 2)

    def support_id(self, end):
        support = self._supports[self._end(end)]
        return support["id"] if support else None

    @property
    def original(self):
        return copy.deepcopy(self._original)

    @property
    def original_joint(self):
        return copy.deepcopy(self._joint)

    @property
    def parent_id(self):
        return self._parent_id

    @property
    def child_id(self):
        return self._child_id

    @property
    def joint_id(self):
        return self._joint_id

    @property
    def subtree_ids(self):
        return self._subtree_ids

    def _part(self, end):
        return self._parts[self._instances[getattr(self, end + "_id")]["part_id"]]

    @staticmethod
    def _end(end):
        if end not in ("parent", "child"):
            raise BridgeError("Choose the parent or child connector.")
        return end

    def _values(self):
        frames = {end: _checked_frame(getattr(self, end + "_frame")) for end in ("parent", "child")}
        if self.kind not in JOINT_KINDS:
            raise BridgeError("Choose a supported Assembly joint kind.")
        try:
            _text(self.name)
        except (ValueError, TypeError) as exc:
            raise BridgeError("Give the joint a nonempty name up to 256 characters.") from exc
        coordinate, limits = 0.0, None
        if self.kind not in NO_SCALAR_COORDINATE:
            bound = 1e4 if self.kind == "revolute" else 1e6
            coordinate = _finite(self.coordinate, "Motion coordinate", bound=bound)
            if self.limits is not None:
                if type(self.limits) not in (list, tuple) or len(self.limits) != 2:
                    raise BridgeError(
                        "Motion limits require lower and upper values (radians for revolute, mm for slider)."
                    )
                limits = [_finite(v, "Motion limit", bound=bound) for v in self.limits]
                if not limits[0] < limits[1] or not limits[0] <= coordinate <= limits[1]:
                    raise BridgeError(
                        "Motion limits must increase and contain the coordinate; values are not clamped."
                    )
        for name in extra_names(self.kind):
            value = _finite(
                self.extra_coordinates[name],
                name,
                bound=1e6 if name.startswith("translation") else 1e4,
            )
            bounds = self.extra_limits[name]
            if bounds is not None:
                if type(bounds) not in (list, tuple) or len(bounds) != 2:
                    raise BridgeError("Named motion limits require two finite values.")
                bounds = [
                    _finite(
                        v, name + " limit", bound=1e6 if name.startswith("translation") else 1e4
                    )
                    for v in bounds
                ]
            if bounds is not None and (
                len(bounds) != 2 or not bounds[0] < bounds[1] or not bounds[0] <= value <= bounds[1]
            ):
                raise BridgeError("Named motion limits must increase and contain the coordinate.")
        return frames, coordinate, limits

    def change_kind(self, kind):
        if kind not in JOINT_KINDS:
            raise BridgeError("Choose a supported joint kind.")
        if kind == self.kind:
            return
        scalar_compatible = self.kind in {"slider", "cylindrical"} and kind in {
            "slider",
            "cylindrical",
        }
        if not scalar_compatible and (self.coordinate != 0 or self.limits is not None):
            raise BridgeError(
                "Kind change would discard motion or limits. Use the existing joint Edit controls to explicitly clear them first."
            )
        for name in extra_names(self.kind):
            if name not in extra_names(kind) and (
                self.extra_coordinates[name] != 0 or self.extra_limits[name] is not None
            ):
                raise BridgeError(
                    "Kind change would discard named motion or limits. Explicitly clear them in joint Edit first."
                )
        self.kind = kind

    def _frame_reference_count(self, part_id, frame_id):
        return sum(
            self._instances[j[end]]["part_id"] == part_id and j[end + "_frame"] == frame_id
            for j in self._original["joints"]
            for end in ("parent", "child")
        )

    def candidate(self):
        frames, coordinate, limits = self._values()
        candidate = copy.deepcopy(self._original)
        parts = {p["id"]: p for p in candidate["parts"]}
        joint = next(j for j in candidate["joints"] if j["id"] == self.joint_id)
        for end in ("parent", "child"):
            part = parts[self._part(end)["id"]]
            source = self._frame_sources[end]
            support = self._supports[end]
            placement = frames[end]
            if support is not None:
                placement = world_to_local(face_frame(support["signature"]), placement)
            record = {"placement": placement}
            if support is not None:
                record["support_face"] = support["id"]
            unchanged = (
                source is not None
                and frames[end] == self._initial_frames[end]
                and support == self._initial_supports[end]
            )
            reusable = (
                source is not None
                and source != "origin"
                and self._frame_reference_count(part["id"], source) == 1
            )
            if unchanged:
                frame_id = source
            elif reusable:
                frame_id = source
                target = next(f for f in part["mate_frames"] if f["id"] == source)
                target.pop("support_face", None)
                target.update(record)
            else:
                frame_id = self._generated[end]
                part["mate_frames"].append(
                    {
                        "id": frame_id,
                        "name": f"{self.name} · {end.title()} connector"[:256],
                        **record,
                    }
                )
            joint[end] = getattr(self, end + "_id")
            joint[end + "_frame"] = frame_id
        joint.update(name=self.name, kind=self.kind)
        if self.kind in NO_SCALAR_COORDINATE:
            joint.pop("coordinate", None)
            joint.pop("limits", None)
        else:
            joint["coordinate"] = coordinate
            # Retain omission in a genuinely unchanged legacy input.
            if limits is not None or "limits" in self._joint or self._joint["kind"] != self.kind:
                joint["limits"] = limits
            else:
                joint.pop("limits", None)
        for name in self.extra_coordinates:
            if name in extra_names(self.kind):
                joint[name] = self.extra_coordinates[name]
                if (
                    name + "_limits" in self._joint
                    or self.extra_limits[name] is not None
                    or self.kind != self._joint["kind"]
                ):
                    joint[name + "_limits"] = copy.deepcopy(self.extra_limits[name])
                else:
                    joint.pop(name + "_limits", None)
            else:
                joint.pop(name, None)
                joint.pop(name + "_limits", None)
        if sum(len(p["mate_frames"]) for p in candidate["parts"]) > MAX_FRAMES:
            raise BridgeError("Visual placement would exceed the Assembly's 128 literal frames.")
        return candidate

    def preview_transforms(self):
        frames, coordinate, _limits = self._values()
        # Keep untouched coordinates/quaternion signs byte-for-byte for no-op
        # display. Otherwise bound only complete poses, not intermediate products.
        candidate = self.candidate()
        if (
            self.parent_id == self._joint["parent"]
            and self.kind == self._joint["kind"]
            and coordinate == self._joint.get("coordinate", 0.0)
            and all(
                self.extra_coordinates[name] == self._joint.get(name, 0.0)
                for name in extra_names(self.kind)
            )
            and frames == self._initial_frames
        ):
            return copy.deepcopy(self._transforms)
        joint = next(j for j in candidate["joints"] if j["id"] == self.joint_id)
        motion = motion_frame(joint)
        child = _compose(
            _compose(_compose(self._transforms[self.parent_id], frames["parent"]), motion),
            _inverse(frames["child"]),
        )
        child = _checked_frame(child)
        delta = _compose(child, _inverse(self._transforms[self.child_id]))
        transforms = copy.deepcopy(self._transforms)
        for instance_id in self.subtree_ids:
            transforms[instance_id] = _checked_frame(_compose(delta, self._transforms[instance_id]))
        # Avoid avoidable cancellation at the primary edited child.
        transforms[self.child_id] = child
        return transforms

    def connector_world(self, end, *, preview=False):
        end = self._end(end)
        transforms = self.preview_transforms() if preview else self._transforms
        return local_to_world(transforms[getattr(self, end + "_id")], getattr(self, end + "_frame"))

    def set_connector_world(self, end, frame):
        end = self._end(end)
        original = getattr(self, end + "_frame")
        if _checked_frame(frame) == self.connector_world(end):
            return  # Preserve authored local values, including quaternion sign.
        local = world_to_local(self._transforms[getattr(self, end + "_id")], frame)
        setattr(self, end + "_frame", local if local != original else copy.deepcopy(original))

    def translate_connector(self, end, axis, distance_mm, *, space="local"):
        end, index = self._end(end), _axis(axis)
        distance = _finite(distance_mm, "Connector translation")
        frame = _checked_frame(getattr(self, end + "_frame"))
        if space not in {"local", "world"}:
            raise BridgeError("Connector translation space must be local or world.")
        if not distance:
            return
        offset = [0.0, 0.0, 0.0]
        offset[index] = distance
        if space == "local":
            offset = rotate(frame["wxyz"], offset)
        else:
            world_q = self._transforms[getattr(self, end + "_id")]["wxyz"]
            w, x, y, z = world_q
            offset = rotate([w, -x, -y, -z], offset)
        frame["xyz_mm"] = [x + y for x, y in zip(frame["xyz_mm"], offset, strict=True)]
        setattr(self, end + "_frame", _checked_frame(frame))

    def turn_connector(self, end, axis, quarter_turns=1):
        end = self._end(end)
        setattr(
            self, end + "_frame", quarter_turn(getattr(self, end + "_frame"), axis, quarter_turns)
        )

    def align_connector(self, end, axis):
        end = self._end(end)
        frame = _checked_frame(getattr(self, end + "_frame"))
        orientation = axis_orientation(axis)
        if frame["wxyz"] == orientation or frame["wxyz"] == [-v for v in orientation]:
            return
        frame["wxyz"] = orientation
        setattr(self, end + "_frame", frame)
