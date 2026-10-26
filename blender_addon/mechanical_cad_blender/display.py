"""Disposable Blender display geometry and last-good cache management.

This module never edits canonical document JSON. All owned-object mutation is
scene-aware; unrelated or separately linked scene geometry is preserved."""

import json
import math
import struct
from contextvars import ContextVar

import bpy

from . import bridge, operation_contracts, workspace
from .common import DOCUMENT_KEY, FEATURE_KEY, MM_TO_METERS, OWNER_KEY, _state
from .sketch_contracts_v3 import validate_output_v3
from .sketch_display import solved_line_wire

# Only the synchronous publication section binds this context. Exact created
# datablock identities are recorded before mutable RNA/tag callbacks can run.
_PUBLICATION = ContextVar("mechanical_cad_display_publication", default=None)


def _track_created(scene, *, obj=None, mesh=None):
    transaction = _PUBLICATION.get()
    if transaction is not None and transaction.scene == scene:
        if obj is not None:
            transaction.created_objects.append(obj)
        if mesh is not None:
            transaction.created_meshes.append(mesh)


def _owned_objects(scene):
    owner = scene.mechanical_cad.owner_id
    if not owner:
        return []
    return [obj for obj in scene.objects if obj.get(OWNER_KEY) == owner]


def _scene_collections(scene):
    collections = set()

    def visit(collection):
        if collection in collections:
            return
        collections.add(collection)
        for child in collection.children:
            visit(child)

    visit(scene.collection)
    return collections


def _unlink_owned_object(scene, obj):
    """Detach from this scene without deleting another scene's linked object."""
    ours = _scene_collections(scene)
    linked_here = [collection for collection in obj.users_collection if collection in ours]
    other_collections = set()
    for other_scene in bpy.data.scenes:
        if other_scene != scene:
            other_collections.update(_scene_collections(other_scene))
    if any(collection in other_collections for collection in linked_here):
        raise bridge.BridgeError(
            "CAD display belongs to a collection shared by multiple scenes. Unlink that shared collection from this scene before regenerating."
        )
    mesh = obj.data if obj.type == "MESH" else None
    for collection in linked_here:
        collection.objects.unlink(obj)
    if not obj.users_collection and obj.users == 0:
        bpy.data.objects.remove(obj)
    if mesh is not None and mesh.users == 0 and mesh.get(OWNER_KEY):
        bpy.data.meshes.remove(mesh)


def _preflight_owned_display(scene):
    """Reject shared-collection mutation before changing authoritative data."""
    ours = _scene_collections(scene)
    elsewhere = set()
    for other_scene in bpy.data.scenes:
        if other_scene != scene:
            elsewhere.update(_scene_collections(other_scene))
    for obj in _owned_objects(scene):
        if any(
            collection in ours and collection in elsewhere for collection in obj.users_collection
        ):
            raise bridge.BridgeError(
                "CAD display belongs to a collection shared by multiple scenes. Unlink that shared collection from this scene before replacing or regenerating it."
            )


def _remove_owned(scene):
    for obj in _owned_objects(scene):
        _unlink_owned_object(scene, obj)


def _hide_owned(scene):
    for obj in _owned_objects(scene):
        # hide_viewport/hide_render are global object properties. Never change
        # them on another scene's linked display.
        if len(obj.users_scene) <= 1:
            obj.hide_viewport = True
            obj.hide_render = True
        for layer in scene.view_layers:
            if obj.name in layer.objects:
                obj.hide_set(True, view_layer=layer)


def _reset_display_transform(obj, origin):
    obj.parent = None
    obj.constraints.clear()
    obj.modifiers.clear()
    obj.animation_data_clear()
    obj.matrix_parent_inverse.identity()
    obj.rotation_mode = "XYZ"
    obj.delta_location = (0, 0, 0)
    obj.delta_rotation_euler = (0, 0, 0)
    obj.delta_rotation_quaternion = (1, 0, 0, 0)
    obj.delta_scale = (1, 1, 1)
    obj.location = origin
    obj.rotation_euler = (0, 0, 0)
    obj.scale = (1, 1, 1)


def _clear_last_good(scene):
    state = scene.mechanical_cad
    previous = state.last_good_mesh
    state.last_good_mesh = None
    if previous is not None and previous.users == 0 and previous.get(OWNER_KEY):
        bpy.data.meshes.remove(previous)


def _restore_last_good(scene):
    """Restore a private immutable-by-display copy, not a user-edited mesh."""
    state = scene.mechanical_cad
    if state.last_good_mesh is None:
        _hide_owned(scene)
        return []
    owned = _owned_objects(scene)
    for obj in owned:
        if len(obj.users_scene) > 1:
            try:
                _unlink_owned_object(scene, obj)
            except bridge.BridgeError:
                _hide_owned(scene)
                state.error += " Shared display cache remains hidden to protect other scenes."
                return []
    owned = _owned_objects(scene)
    obj = next((item for item in owned if item.type == "MESH"), None)
    restored = state.last_good_mesh.copy()
    restored[OWNER_KEY] = state.owner_id
    if obj is None:
        obj = bpy.data.objects.new("Last-good CAD cache", restored)
        scene.collection.objects.link(obj)
    else:
        previous = obj.data
        obj.data = restored
        if previous.users == 0 and previous.get(OWNER_KEY):
            bpy.data.meshes.remove(previous)
    obj[OWNER_KEY] = state.owner_id
    obj[DOCUMENT_KEY] = state.last_good_document_id
    obj[FEATURE_KEY] = state.last_good_feature_id
    obj["mechanical_cad_display_only"] = True
    obj.name = "STALE · last-good · " + state.last_good_label
    _reset_display_transform(obj, tuple(state.last_good_origin))
    return [obj]


def _set_failure(scene, message):
    state = scene.mechanical_cad
    state.status = "FAILED"
    if state.geometry_report_json:
        state.geometry_status = "OUTDATED"
        state.geometry_message = "The current CAD replay or display is unverified. Fix the error, then run Check Geometry again."
    state.error = str(message)
    state.volume = 0.0
    # Keep the last successful output inspectable as a conspicuously stale
    # wireframe cache. It is never the current CAD result or a render/export.
    for obj in _restore_last_good(scene):
        obj["mechanical_cad_stale"] = True
        if not obj.name.startswith("STALE · last-good · "):
            obj.name = "STALE · last-good · " + obj.name
        obj.display_type = "WIRE"
        obj.show_in_front = True
        obj.color = (1.0, 0.24, 0.02, 1.0)
        obj.hide_viewport = False
        obj.hide_render = True
        for layer in scene.view_layers:
            if obj.name in layer.objects:
                obj.hide_set(False, view_layer=layer)
    for row in state.features:
        if row.status in {"ok", "pending"}:
            row.status = "unverified"
            if row.sketch_report_json:
                row.sketch_report_status = "OUTDATED"


def _mesh_payload(feature, scale=MM_TO_METERS, *, source=None, result_version=2):
    if type(result_version) is not int or result_version not in (2, 3):
        raise bridge.BridgeError("Display requires explicit typed result 2 or 3.")
    if result_version == 3:
        try:
            validate_output_v3(feature, source)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
            raise bridge.BridgeError(f"Invalid result-3 display evidence: {exc}") from exc
    elif isinstance(source, dict) and source.get("sketch", {}).get("schema_version") == 3:
        raise bridge.BridgeError("Schema-3 display requires result version 3.")
    output = feature.get("output")
    if (
        isinstance(output, dict)
        and output.get("kind") == "sketch"
        and (output.get("profile", {}).get("state") == "unavailable")
    ):
        try:
            wire = solved_line_wire(feature, source, scale, result_version=result_version)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise bridge.BridgeError(f"Invalid solved sketch display: {exc}") from exc
        return wire["vertices"], wire["triangles"], wire["edges"]
    mesh = feature.get("mesh")
    if mesh is None:
        # Wire previews are disposable display geometry from sidecar-resolved
        # dimensions. They do not implement or alter kernel sketch geometry.
        params = feature.get("resolved_params") or {}
        kind = feature.get("kind")
        if kind not in {"sketch_rectangle", "sketch_circle"} or not params:
            return None
        x, y, z = (float(params.get(key, 0)) for key in ("x", "y", "z"))
        if kind == "sketch_rectangle":
            width, height = params["width"], params["height"]
            points = [(x, y, z), (x + width, y, z), (x + width, y + height, z), (x, y + height, z)]
        else:
            radius = params["radius"]
            points = [
                (
                    x + radius * math.cos(i * math.tau / 96),
                    y + radius * math.sin(i * math.tau / 96),
                    z,
                )
                for i in range(96)
            ]
        vertices = [tuple(value * scale for value in point) for point in points]
        return vertices, [], [(i, (i + 1) % len(vertices)) for i in range(len(vertices))]
    if not isinstance(mesh, dict):
        raise bridge.BridgeError("Sidecar supplied invalid display mesh data.")
    vertices = mesh.get("vertices")
    triangles = mesh.get("triangles")
    if not isinstance(vertices, list) or not isinstance(triangles, list):
        raise bridge.BridgeError("Sidecar display mesh has no vertex/triangle arrays.")
    if len(vertices) > 2_000_000 or len(triangles) > 4_000_000:
        raise bridge.BridgeError("Display mesh is too large for the MVP viewport limit.")
    scaled = []
    for point in vertices:
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 3
            or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                for v in point
            )
        ):
            raise bridge.BridgeError("Sidecar supplied a non-finite or malformed mesh vertex.")
        scaled.append(tuple(float(v) * scale for v in point))
    for triangle in triangles:
        if (
            not isinstance(triangle, (list, tuple))
            or len(triangle) != 3
            or not all(type(i) is int and 0 <= i < len(vertices) for i in triangle)
        ):
            raise bridge.BridgeError("Sidecar supplied an invalid triangle index.")
    return scaled, triangles, []


def _display_feature(context, document, feature, *, result_version=2):
    try:
        selected = operation_contracts.result_version_for(document, action="replay")
        if type(result_version) is not int or result_version != selected:
            raise ValueError("Display result version differs from the complete candidate.")
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise bridge.BridgeError(f"Invalid display candidate: {exc}") from exc
    scene = context.scene
    state = _state(context)
    scene_scale = max(float(scene.unit_settings.scale_length), 1e-9)
    source = next((item for item in document["features"] if item["id"] == feature["id"]), None)
    payload = _mesh_payload(
        feature, MM_TO_METERS / scene_scale, source=source, result_version=result_version
    )
    output = feature.get("output") or {}
    open_sketch = output.get("kind") == "sketch" and (
        output.get("profile", {}).get("state") == "unavailable"
    )
    if payload is None:
        _remove_owned(scene)
        return
    vertices, triangles, edges = payload
    if vertices:
        bounds_min = [min(point[axis] for point in vertices) for axis in range(3)]
        bounds_max = [max(point[axis] for point in vertices) for axis in range(3)]
        # Blender mesh positions are float32. Centre in local coordinates before
        # transfer so a tiny part far from global origin retains its dimensions.
        # Choose a float32-representable origin; residuals stay in the vertices.
        origin = tuple(
            struct.unpack("f", struct.pack("f", (low + high) / 2))[0]
            for low, high in zip(bounds_min, bounds_max, strict=True)
        )
        vertices = [tuple(point[axis] - origin[axis] for axis in range(3)) for point in vertices]
    else:
        origin = (0.0, 0.0, 0.0)
        bounds_min = bounds_max = [0.0, 0.0, 0.0]
    if not vertices or (not triangles and not edges):
        raise bridge.BridgeError("Active output has an empty display mesh.")
    mesh = bpy.data.meshes.new(f"CAD {document['name']} display")
    _track_created(scene, mesh=mesh)
    mesh[OWNER_KEY] = state.owner_id
    if open_sketch:
        # A disposable index map for inspection only, never a saved CAD reference.
        wire = solved_line_wire(
            feature, source, MM_TO_METERS / scene_scale, result_version=result_version
        )
        mesh["mechanical_cad_point_ids"] = json.dumps(wire["point_ids"])
        mesh["mechanical_cad_line_ids"] = json.dumps(wire["line_ids"])
    try:
        mesh.from_pydata(vertices, edges, triangles)
        mesh.update()
        if mesh.validate(verbose=False):
            raise bridge.BridgeError(
                "Blender repaired invalid CAD display mesh data; regeneration was rejected."
            )
        owned = _owned_objects(scene)
        existing = next((obj for obj in owned if obj.type == "MESH"), None)
        for other in owned:
            if other != existing:
                _unlink_owned_object(scene, other)
        if existing is not None and len(existing.users_scene) > 1:
            _unlink_owned_object(scene, existing)
            existing = None
        if existing is None:
            existing = bpy.data.objects.new(f"CAD · {document['name']}", mesh)
            _track_created(scene, obj=existing)
            scene.collection.objects.link(existing)
        else:
            if existing.mode != "OBJECT":
                raise bridge.BridgeError("Leave Edit Mode before regenerating the CAD display.")
            old_mesh = existing.data
            existing.data = mesh
            if old_mesh.users == 0 and old_mesh.get(OWNER_KEY):
                bpy.data.meshes.remove(old_mesh)
        existing[OWNER_KEY] = state.owner_id
        existing[DOCUMENT_KEY] = document["id"]
        existing[FEATURE_KEY] = feature["id"]
        existing["mechanical_cad_display_only"] = True
        existing["mechanical_cad_stale"] = False
        existing["mechanical_cad_output_kind"] = output.get("kind", "")
        existing["mechanical_cad_profile_state"] = output.get("profile", {}).get("state", "")
        existing.display_type = "WIRE" if open_sketch else "TEXTURED"
        existing.show_in_front = False
        existing.color = (0.18, 0.42, 0.58, 1.0)
        existing["mechanical_cad_units"] = "mm (display respects scene scale)"
        existing["mechanical_cad_scene_scale"] = scene_scale
        existing.name = f"CAD · {document['name']} · {feature['id']}"
        # Meshes and their object transforms are disposable caches. Remove
        # Blender-side deformation so READY always matches canonical CAD size.
        _reset_display_transform(existing, origin)
        existing["mechanical_cad_display_origin_mm"] = [
            value * scene_scale / MM_TO_METERS for value in origin
        ]
        existing.show_wire = feature.get("kind", "").startswith("sketch_")
        existing.show_all_edges = existing.show_wire
        existing.hide_viewport = False
        existing.hide_render = open_sketch
        existing.hide_set(False)
        for obj in context.selected_objects:
            obj.select_set(False)
        existing.select_set(True)
        context.view_layer.objects.active = existing
        positive_extents = [
            high - low for low, high in zip(bounds_min, bounds_max, strict=True) if high > low
        ]
        world_precision = max(abs(value) for value in origin) * 2**-23
        warning = ""
        if positive_extents and world_precision > min(positive_extents) * 0.01:
            warning = "Large global coordinates limit Blender viewport placement precision. Local part dimensions are preserved; CAD geometry retains full precision."
        existing["mechanical_cad_precision_warning"] = warning
        previous_cache = state.last_good_mesh
        state.last_good_mesh = mesh.copy()
        _track_created(scene, mesh=state.last_good_mesh)
        state.last_good_mesh.name = f"CAD last-good cache · {state.owner_id[:8]}"
        state.last_good_mesh[OWNER_KEY] = state.owner_id
        state.last_good_origin = origin
        state.last_good_document_id = document["id"]
        state.last_good_feature_id = feature["id"]
        state.last_good_label = existing.name
        if (
            previous_cache is not None
            and previous_cache.users == 0
            and previous_cache.get(OWNER_KEY)
        ):
            bpy.data.meshes.remove(previous_cache)
    except Exception:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise


class _CandidateDisplay:
    """Retain untouched old datablocks until a candidate's whole publication succeeds.

    Detached objects are still live Blender datablocks. No copied mesh or edited
    transform is used to reconstruct the old display on rollback. Regular replay
    keeps its existing object reuse path; only candidate publication is staged.
    """

    def __init__(self, context):
        self.scene = context.scene
        self.state = self.scene.mechanical_cad
        _preflight_owned_display(self.scene)
        ours = _scene_collections(self.scene)
        self.links = [
            (obj, [collection for collection in obj.users_collection if collection in ours])
            for obj in _owned_objects(self.scene)
        ]
        self.cache = self.state.last_good_mesh
        self.view_layer = context.view_layer
        self.selected = list(context.selected_objects)
        self.active = context.view_layer.objects.active
        self.created_objects = []
        self.created_meshes = []
        self._token = None

    def detach(self):
        # Prevent _display_feature / the empty-document path from discarding the
        # previous cache while its owning state is still rollbackable.
        if _PUBLICATION.get() is not None:
            raise bridge.BridgeError("Another display publication is already active.")
        self._token = _PUBLICATION.set(self)
        self.state.last_good_mesh = None
        for obj, collections in self.links:
            for collection in collections:
                collection.objects.unlink(obj)

    def _detach_tracking(self):
        token, self._token = self._token, None
        if token is not None:
            _PUBLICATION.reset(token)

    def hide_rejected(self):
        """Hide only identities created by this rejected transaction."""
        for obj in self.created_objects:
            try:
                if obj.name not in self.scene.objects:
                    continue
                if len(obj.users_scene) <= 1:
                    obj.hide_viewport = obj.hide_render = True
                    obj["mechanical_cad_stale"] = True
                for layer in self.scene.view_layers:
                    if obj.name in layer.objects:
                        obj.hide_set(True, view_layer=layer)
            except ReferenceError:
                continue  # Already removed by a successful cleanup step.

    def rollback(self):
        self._detach_tracking()
        failures = []

        def recover(label, operation):
            try:
                operation()
            except Exception as exc:
                failures.append(label + ": " + str(exc))

        # Never rediscover candidates through mutable owner/document tags or a
        # state cache pointer. Those can change in the very callback we reject.
        for obj in self.created_objects:
            try:
                _name = obj.name
            except ReferenceError:
                continue
            recover("Candidate unlink", lambda obj=obj: _unlink_owned_object(self.scene, obj))
        recover("Cache pointer", lambda: setattr(self.state, "last_good_mesh", self.cache))
        for mesh in self.created_meshes:
            try:
                _name = mesh.name
            except ReferenceError:
                continue

            def remove_created_mesh(mesh=mesh):
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)

            recover("Candidate mesh cleanup", remove_created_mesh)
        # Independent original links are restored even when candidate cleanup
        # fails. Canonical restoration and revocation of trust belong to caller.
        for obj, collections in self.links:
            for collection in collections:

                def relink(obj=obj, collection=collection):
                    if obj.name not in collection.objects:
                        collection.objects.link(obj)

                recover("Original object relink", relink)
        for obj in self.selected:
            if obj.name in self.view_layer.objects:
                recover(
                    "Selection", lambda obj=obj: obj.select_set(True, view_layer=self.view_layer)
                )
        if self.active is not None and self.active.name in self.view_layer.objects:
            recover(
                "Active object", lambda: setattr(self.view_layer.objects, "active", self.active)
            )
        if failures:
            raise bridge.BridgeError("; ".join(failures))

    def finalize(self):
        self._detach_tracking()
        # Cleanup is after acceptance. An orphan-cleanup error cannot turn a
        # published document into a falsely reported rejection.
        for obj, _collections in self.links:
            try:
                mesh = obj.data if obj.type == "MESH" else None
                if not obj.users_collection and obj.users == 0:
                    bpy.data.objects.remove(obj)
                if mesh is not None and mesh.users == 0 and mesh.get(OWNER_KEY):
                    bpy.data.meshes.remove(mesh)
            except (ReferenceError, RuntimeError):
                pass
        try:
            if self.cache is not None and self.cache.users == 0 and self.cache.get(OWNER_KEY):
                bpy.data.meshes.remove(self.cache)
        except (ReferenceError, RuntimeError):
            pass


def _focus_display(context, whole_scene=False):
    """Frame the current Part display through the common local-view helper."""
    return _focus_objects(context, _owned_objects(context.scene), whole_scene=whole_scene)


def _lower_focus_clip(context, space, objects):
    """Keep a CAD close-up in front of the near plane, in scene display units."""
    if not workspace.is_cad_workspace(context):
        return
    # Use geometry, not view_distance: native framing can still be animating.
    # Subtract translations before transforming bounds in Python double precision
    # so a small, locally centred part far from the origin keeps its extent.
    origin = tuple(float(objects[0].matrix_world[axis][3]) for axis in range(3))
    points = []
    for obj in objects:
        matrix = obj.matrix_world
        for corner in obj.bound_box:
            points.append(
                tuple(
                    math.fsum(
                        [float(matrix[axis][j]) * float(corner[j]) for j in range(3)]
                        + [float(matrix[axis][3]) - origin[axis]]
                    )
                    for axis in range(3)
                )
            )
    low = tuple(min(point[axis] for point in points) for axis in range(3))
    high = tuple(max(point[axis] for point in points) for axis in range(3))
    extent = math.dist(low, high)
    if not math.isfinite(extent) or extent <= 0:
        return
    # Bounds already include 0.001 / scene.scale_length from CAD display. Keep
    # a 1000:1 extent/near-plane margin, respecting Blender's actual RNA floor
    # (1e-6 scene units in 5.2) and any finer setting the user already chose.
    minimum = space.bl_rna.properties["clip_start"].hard_min
    target = max(minimum, extent / 1000)
    if space.clip_start > target:
        space.clip_start = target


def _focus_objects(context, objects, whole_scene=False):
    """Frame explicit CAD objects; never hide or delete unrelated scene objects."""
    if bpy.app.background or context.screen is None:
        return False
    area = (
        context.area
        if context.area and context.area.type == "VIEW_3D"
        else next((area for area in context.screen.areas if area.type == "VIEW_3D"), None)
    )
    if area is None:
        return False
    region = next((region for region in area.regions if region.type == "WINDOW"), None)
    if region is None:
        return False
    space = area.spaces.active
    with context.temp_override(area=area, region=region):
        if whole_scene:
            if space.local_view:
                bpy.ops.view3d.localview(frame_selected=False)
            bpy.ops.view3d.view_all(center=False)
            return True
        objects = list(objects)
        if not objects:
            return False
        context.view_layer.update()
        _lower_focus_clip(context, space, objects)
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        context.view_layer.objects.active = objects[0]
        if not space.local_view:
            bpy.ops.view3d.localview(frame_selected=True)
        else:
            for obj in context.view_layer.objects:
                obj.local_view_set(space, obj in objects)
            bpy.ops.view3d.view_selected(use_all_regions=False)
    return True
