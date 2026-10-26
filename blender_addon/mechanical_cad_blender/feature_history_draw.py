"""One synchronous UIList draw's immutable labels, never action authority."""

import json
from dataclasses import dataclass

from . import compact_status, document_state
from .common import _state
from .support_intent_edit import attached_feature, support_decision
from .support_presentation import support_text

_SCOPES = []
_UNVERIFIED = ("DOT", False)


@dataclass(frozen=True)
class _FeatureDetail:
    feature_id: str
    status: str
    sketch_label: tuple | None
    failed_detail: str
    failed_detail_icon: str
    redundant_detail: str
    profile_state: tuple = (False, "Rebuild to check the sketch profile", "INFO")


@dataclass(frozen=True)
class _DrawScope:
    scene: object
    state: object
    items: tuple
    rows: tuple
    current: object
    details: tuple = ()
    volume_label: str = ""
    support: tuple | None = None

    def _matches(self, context):
        return (
            context.scene == self.scene
            and _state(context) == self.state
            and self.state.status == "READY"
            and tuple(self.state.features) == self.items
        )

    def is_current(self, context):
        try:
            return self._matches(context) and self.current() and self._matches(context)
        except (ValueError, ReferenceError, AttributeError, RuntimeError, TypeError, KeyError):
            return False

    def selected_detail(self, context, feature_id):
        def selected():
            index = self.state.feature_index
            return 0 <= index < len(self.items) and self.items[index].feature_id == feature_id

        try:
            if not selected() or not self.is_current(context) or not selected():
                return None
            return next((item for item in self.details if item.feature_id == feature_id), None)
        except (ValueError, ReferenceError, AttributeError, RuntimeError, TypeError, KeyError):
            return None

    def selected_support(self, context, feature):
        # Bind the disclosure source to the captured selection and exact policy.
        # The existing guard also binds canonical JSON and runtime source.
        if self.support is None:
            return None
        identifier, source_json, values = self.support

        def matches():
            return (
                feature.get("id") == identifier
                and json.dumps(feature, sort_keys=True) == source_json
                and 0 <= self.state.feature_index < len(self.items)
                and self.items[self.state.feature_index].feature_id == identifier
            )

        try:
            if matches() and self.is_current(context) and matches():
                return values
        except (ValueError, ReferenceError, AttributeError, RuntimeError, TypeError, KeyError):
            pass
        return None

    def volume_text(self, context):
        return self.volume_label if self.is_current(context) else None

    def row(self, context, data, item, index):
        def matches():
            return (
                context.scene == self.scene
                and _state(context) == self.state
                and data == self.state
                and self.state.status == "READY"
                and 0 <= index < len(self.items)
                and item == self.items[index]
                and tuple(self.state.features) == self.items
            )

        if not matches() or not self.current() or not matches():
            return _UNVERIFIED
        identifier, icon, assumed = self.rows[index]
        return (icon, assumed) if item.feature_id == identifier else _UNVERIFIED


def _capture(context):
    state = _state(context)
    items = tuple(state.features)
    projection = document_state._runtime_projection(
        context, document_state._RUNTIME, with_current_check=True
    )
    if projection is None or state.status != "READY":
        return _DrawScope(context.scene, state, items, (), lambda: False)
    _, response, current = projection
    result = response["result"]
    sources = {f["id"]: f for f in document_state._read_document(state)["features"]}
    features = {f["id"]: f for f in result["features"]}
    rows = []
    details = []
    for item in items:
        feature = features.get(item.feature_id, {})
        icon = {"ok": "CHECKMARK", "failed": "ERROR", "blocked": "CANCEL"}.get(
            feature.get("status"), "DOT"
        )
        assumed = False
        source = sources.get(item.feature_id, {})
        if "support_intent" in source:
            try:
                assumed = support_decision(source, result)["status"] == "assumed"
            except (ValueError, KeyError, StopIteration):
                pass
        rows.append((item.feature_id, icon, assumed))
        report = feature.get("sketch")
        failed = report.get("failed_constraints", []) if report is not None else []
        redundant = report.get("redundant_constraints", []) if report is not None else []
        prefix = (
            "Redundancy candidates: "
            if report is not None and report.get("status") == "redundant_okay"
            else "Conflict candidates: "
        )
        details.append(
            _FeatureDetail(
                item.feature_id,
                feature.get("status", "unverified"),
                compact_status.sketch_label(report) if report is not None else None,
                prefix + ", ".join(failed) if failed else "",
                "INFO"
                if report is not None and report.get("status") == "redundant_okay"
                else "ERROR",
                "Redundant constraints: " + ", ".join(redundant) if redundant else "",
                compact_status.saved_profile_state(feature),
            )
        )
    support = None
    if 0 <= state.feature_index < len(items):
        identifier = items[state.feature_index].feature_id
        try:
            source = attached_feature({"features": list(sources.values())}, identifier)
        except (ValueError, KeyError, TypeError, IndexError):
            pass
        else:
            support = (identifier, json.dumps(source, sort_keys=True), support_text(source, result))
    active = features.get(result.get("active_feature"), {})
    volume = (active.get("stats") or {}).get("volume", 0.0)
    return _DrawScope(
        context.scene, state, items, tuple(rows), current, tuple(details),
        f"Volume: {volume:,.3f} mm³",
        support,
    )


def capture_presentation(context):
    """One panel-local immutable presentation, captured with its original guard.

    It exposes only derived text/icons, never a Part result or action authority.
    Do not retain it beyond the synchronous panel draw.
    """
    return _capture(context)


def row_presentation(context, data, item, index):
    """Outside a matching live scope use a fresh proof, never an earlier draw."""
    scope = _SCOPES[-1] if _SCOPES else _capture(context)
    try:
        return scope.row(context, data, item, index)
    except (ValueError, ReferenceError, AttributeError, RuntimeError, TypeError, KeyError):
        return _UNVERIFIED


def draw_history(layout, context, list_id, *, rows, presentation=None):
    """Blender draws UIList rows synchronously within template_list()."""
    state = _state(context)
    if presentation is not None and type(presentation) is not _DrawScope:
        raise ValueError("History presentation must come from the panel's captured read.")
    scope = _capture(context) if presentation is None else presentation
    _SCOPES.append(scope)
    try:
        layout.template_list(
            "MCAD_UL_features", list_id, state, "features", state, "feature_index", rows=rows
        )
    finally:
        # Nested draws have their own scope; never leave a snapshot for a later
        # redraw or extend its lifetime if a host defers a callback.
        assert _SCOPES[-1] is scope
        _SCOPES.pop()
