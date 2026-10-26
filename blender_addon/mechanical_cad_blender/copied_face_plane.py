"""One-shot current native face sampling, never persistent topology identity.

Unknown imported IDs may identify a face only inside the captured exact replay.
The only value handed to the sketch is an ordinary literal plane. No triangle,
face selector, support input or source geometry is saved with that plane.
"""

from . import workspace
from .assembly_frame_evidence import face_frame
from .common import _state
from .face_pick import FacePicker

DISCLOSURE = "Fixed plane copied from this face. Does not follow source edits."
_PENDING = {}


def resolve_sample(feature, index):
    mesh = feature.get("mesh") or {}
    ids = mesh.get("triangle_face_ids", [])
    if len(ids) != len(mesh.get("triangles", [])):
        raise ValueError("The display face map is incomplete. Rebuild the Part.")
    if type(index) is not int or not 0 <= index < len(ids):
        raise ValueError("No exact CAD face under the pointer.")
    matches = [face for face in feature.get("topology", []) if face.get("id") == ids[index]]
    if not ids[index] or len(matches) != 1 or matches[0].get("kind") != "face":
        raise ValueError("This current face has no unambiguous native geometry.")
    if (matches[0].get("signature") or {}).get("surface") != "plane":
        raise ValueError("Choose a planar face, not a curved or unknown surface.")
    face_frame(matches[0]["signature"])  # Strict analytic geometry, not mesh normals.
    return matches[0]


def literal_plane(face):
    frame = face_frame(face["signature"])
    if any(abs(value) > 1e6 for value in frame["xyz_mm"]):
        raise ValueError("Copied plane origin is outside the supported sketch range.")
    return {"id": "copied_plane", "origin": list(frame["xyz_mm"]), "quaternion": frame["wxyz"]}


class PlaneCapture:
    """Transient receipt, consumed before the draft starts, not restored from disk."""

    def __init__(self, context, picker):
        if not picker.current(context) or picker.hit is None:
            raise ValueError("Select a current planar face again.")
        self.snapshot = picker.snapshot
        self.obj = picker.hover_object
        self.index = picker.sample_index
        self.window, self.scene = context.window, context.scene
        self.draft = _state(context).sketch_draft_json
        self.plane(context)  # Acceptance requires a fresh receipt and complete display match.

    def plane(self, context):
        from .viewport_sketch import _can_start_sketch

        if (
            context.window != self.window
            or context.scene != self.scene
            or _state(context).sketch_draft_json != self.draft
            or not _can_start_sketch(context)
        ):
            raise ValueError("The sketch context changed. Select the face again.")
        feature = self.snapshot.bound_feature(
            context, self.obj, self.snapshot.result(context, accepting=True)
        )
        return literal_plane(resolve_sample(feature, self.index))


def consume(context, token):
    capture = _PENDING.pop(token, None)
    if capture is None:
        raise ValueError("Copied plane selection expired. Select the face again.")
    return capture.plane(context)


class CopiedPlanePicker(FacePicker):
    describe_support = False

    def resolve_face(self, feature, index):
        face = resolve_sample(feature, index)
        self.sample_index = index
        return face

    def begin(self, context):
        # Capture before closing: the original picker must still be current.
        capture = PlaneCapture(context, self)
        self.close()

        def ready(active_context):
            import uuid

            import bpy

            # Revalidate after workspace transition. Token cannot supply arbitrary
            # plane JSON or survive replay; the owner consumes it synchronously.
            capture.plane(active_context)
            token = uuid.uuid4().hex
            _PENDING[token] = capture
            try:
                bpy.ops.mcad.general_sketch("INVOKE_DEFAULT", copied_plane_token=token)
            finally:
                _PENDING.pop(token, None)

        workspace.request_workspace(context, "SKETCH", on_ready=ready)
