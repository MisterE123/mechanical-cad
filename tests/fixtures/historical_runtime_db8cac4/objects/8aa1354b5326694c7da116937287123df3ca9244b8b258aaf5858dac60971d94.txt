"""Minimal native-free host ports around unchanged production owner modules.

Only Blender storage, display resources and viewport base-session mechanics are
faked. Admission, current readers, replay transactions, publication, rollback,
Rectangle methods, geometry fallbacks and Assembly validation remain original.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_result3_owner_boundary_tests"


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


def noop(*_args, **_kwargs):
    return None


class Properties(list):
    def __getitem__(self, key):
        return (
            next(item for item in self if item.identifier == key)
            if type(key) is str
            else super().__getitem__(key)
        )


class Storage(types.SimpleNamespace):
    @property
    def bl_rna(self):
        return types.SimpleNamespace(
            properties=Properties(
                types.SimpleNamespace(
                    identifier=key,
                    type="COLLECTION" if isinstance(value, Rows) else "VALUE",
                    is_array=False,
                )
                for key, value in vars(self).items()
            )
        )

    def as_pointer(self):
        return id(self)


class Rows(list):
    def __init__(self, defaults):
        super().__init__()
        self.defaults = defaults

    def add(self):
        result = Storage(**self.defaults)
        self.append(result)
        return result


class CandidateDisplay:
    events = []

    def __init__(self, context):
        self.context = context

    def detach(self):
        self.events.append("detach")

    def rollback(self):
        self.events.append("rollback")

    def finalize(self):
        self.events.append("finalize")

    def hide_rejected(self):
        self.events.append("hide_rejected")


class SessionPort:
    def __init__(self, context, draft, *, restored=False):
        self.scene, self.window, self.workspace = context.scene, context.window, context.workspace
        self.draft = draft
        self.alive = True
        self.stored_snapshot = context.scene.mechanical_cad.sketch_draft_json
        self.session_id = "owner-fake-session"

    def valid_context(self):
        return self.alive and self.scene.mechanical_cad.document_json == self.draft.document_json

    def cleanup(self):
        self.alive = False


def load_owners():
    if PACKAGE + ".document_state" in sys.modules:
        return sys.modules[PACKAGE]._owner_modules
    package = module(PACKAGE)
    package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
    sys.modules[PACKAGE] = package
    bpy = module("bpy", data=types.SimpleNamespace(scenes=[]), context=None)
    bpy_props = module(
        "bpy.props", **{name: noop for name in ("BoolProperty", "IntProperty", "StringProperty")}
    )
    bpy_types = module("bpy.types", Operator=type("Operator", (), {}))
    bpy_extras = module("bpy_extras", view3d_utils=module("view3d_utils"))
    bpy_io = module("bpy_extras.io_utils", ExportHelper=type("ExportHelper", (), {}))
    display = module(
        PACKAGE + ".display",
        _CandidateDisplay=CandidateDisplay,
        _owned_objects=lambda _scene: [],
        _mesh_payload=noop,
    )
    for name in (
        "_clear_last_good",
        "_display_feature",
        "_focus_display",
        "_hide_owned",
        "_preflight_owned_display",
        "_remove_owned",
    ):
        setattr(display, name, noop)

    def set_failure(scene, message):
        scene.mechanical_cad.status = "FAILED"
        scene.mechanical_cad.error = message

    display._set_failure = set_failure
    workspace = module(
        PACKAGE + ".workspace",
        active_draft=lambda _context=None: None,
        has_draft=lambda _context: False,
        request_workspace=noop,
        owned_view_layer=lambda _context: None,
    )
    session = module(PACKAGE + ".sketch_session", SketchSession=SessionPort)
    for name in (
        "_discard_stored",
        "_tag_redraw",
        "active_session",
        "editor_operator",
        "suspended_draft",
        "after_file_load",
        "after_history_change",
        "before_history_change",
        "cancel_active",
        "checkpoint_active",
        "draft_recovery_notice",
        "suspend_active",
    ):
        setattr(session, name, noop)
    stubs = {
        "bpy": bpy,
        "bpy.props": bpy_props,
        "bpy.types": bpy_types,
        "bpy_extras": bpy_extras,
        "bpy_extras.io_utils": bpy_io,
        PACKAGE + ".display": display,
        PACKAGE + ".workspace": workspace,
        PACKAGE + ".common": module(
            PACKAGE + ".common",
            _state=lambda context: context.scene.mechanical_cad,
            MM_TO_METERS=0.001,
        ),
        PACKAGE + ".sketch_session": session,
        PACKAGE + ".sketch_overlay": module(PACKAGE + ".sketch_overlay"),
        PACKAGE + ".workspace_ui": module(PACKAGE + ".workspace_ui"),
        PACKAGE + ".help_ui": module(
            PACKAGE + ".help_ui",
            _draw_feature_help=noop,
            _feature_help_next=noop,
            _feature_help_previous=noop,
        ),
    }
    names = (
        "backend_contracts",
        "backend_selection",
        "backend_runtime",
        "guarded_evidence",
        "guarded_transport",
        "sidecar_job",
        "bridge",
        "part_result_bridge",
        "sketch_action_bridge",
        "part_snapshot_bridge",
        "assembly_bridge",
        "general_sketch_draft",
        "general_view_geometry",
        "constraint_diagnostics",
        "sketch_draft",
        "draft_store",
        "draft_dispatch",
        "document_state",
        "part_publication",
        "viewport_sketch",
        "geometry_operations",
        "assembly_display",
        "assembly_state",
    )
    with patch.dict(sys.modules, stubs):
        owners = types.SimpleNamespace(
            **{name: importlib.import_module(PACKAGE + "." + name) for name in names}
        )
        loaded = {key: value for key, value in sys.modules.items() if key.startswith(PACKAGE + ".")}
    sys.modules.update(loaded)
    owners.bpy, owners.workspace, owners.display = bpy, workspace, display
    package._owner_modules = owners
    return owners


def context_for(owners, document, selected):
    parameters = Rows(
        dict(
            key="",
            value=0.0,
            is_expression=False,
            expression="",
            resolved_text="",
            resolved_expression="",
        )
    )
    features = Rows(
        dict(
            feature_id="",
            label="",
            kind="",
            status="pending",
            error="",
            sketch_report_json="",
            sketch_document_json="",
            sketch_report_status="UNVERIFIED",
        )
    )
    state = Storage(
        document_json=json.dumps(document, allow_nan=False),
        document_path="",
        document_name=document["name"],
        owner_id="test-part-owner",
        status="DIRTY",
        error="",
        volume=0.0,
        sketch_draft_json="",
        sketch_annotation_json="",
        sketch_notice="",
        last_action_error="",
        geometry_report_json="",
        geometry_document_json="",
        geometry_status="UNCHECKED",
        geometry_message="",
        parameters=parameters,
        features=features,
        active_feature="",
        feature_index=0,
    )
    assembly = Storage(**{name: "" for name in owners.assembly_state._STATE_FIELDS})
    scene = Storage(
        mechanical_cad=state,
        mechanical_cad_assembly=assembly,
        unit_settings=types.SimpleNamespace(scale_length=0.001),
        objects=[],
    )
    prefs = types.SimpleNamespace(
        project_root=selected.project_root,
        python_executable=selected.python_executable,
        timeout_seconds=selected.timeout,
        linear_deflection=0.1,
    )
    context = types.SimpleNamespace(
        scene=scene,
        window=Storage(),
        workspace=Storage(),
        view_layer=Storage(),
        mode="OBJECT",
        preferences=types.SimpleNamespace(
            addons={PACKAGE: types.SimpleNamespace(preferences=prefs)}
        ),
    )
    owners.bpy.context = context
    owners.bpy.data.scenes = [scene]
    owners.document_state._populate_document(scene, document)
    return context


def forge_evidence(owners, prepared, raw, selected, owner):
    """Adversarial exact-class reconstruction; never accepted by the factory."""
    evidence_type = owners.guarded_evidence.GuardedEvidence
    evidence = object.__new__(evidence_type)
    values = {
        "_prepared": prepared,
        "_response_payload": owners.backend_contracts._encode(raw),
        "_projection_payload": owners.backend_contracts._encode(
            owners.backend_contracts.project_response(raw), compact=True
        ),
        "selection": selected,
        "_owner_token": owner,
    }
    for key, value in values.items():
        object.__setattr__(evidence, key, value)
    object.__setattr__(
        evidence, "_publication", owners.guarded_evidence.EvidencePublication(evidence)
    )
    return evidence
