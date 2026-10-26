"""History-level repair dialog using fresh upstream evidence, not stale display."""

import json

from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from . import backend_contracts, backend_runtime, document_state, guarded_transport
from .common import _state
from .history_operators import _HistoryDialog
from .operators import _reject_candidate, _report_result
from .projection_repair import projected_feature, replace_reference, source_document, target_kind
from .sketch_projection import is_solid_projection, projection_groups

_CHOICES = {}


def _choices(key, values):
    key = (key, tuple(values))
    _CHOICES[key] = values or [("NONE", "No matching analytic references", "")]
    return _CHOICES[key]


def _callback_data(self):
    # RNA callbacks may receive a fresh Python wrapper. Only choice labels and
    # default selections live here; Apply revalidates its native receipt.
    try:
        return json.loads(self.choice_data_json)
    except (AttributeError, ValueError, TypeError):
        return {}


def _targets(self, context):
    return _choices("targets", [tuple(row) for row in _callback_data(self).get("targets", [])])


def _sources(self, context):
    rows = _callback_data(self).get("sources", {}).get(self.target, [])
    return _choices(("sources", self.target), [tuple(row) for row in rows])


def _target_changed(self, context):
    default = _callback_data(self).get("defaults", {}).get(self.target)
    if default is not None:
        self.replacement, self.reverse = default


def _choice_data(feature, entries):
    data = {"targets": [], "sources": {}, "defaults": {}}
    for saved in feature["projections"]:
        target = saved["target"]
        kind = target_kind(feature, target)
        data["targets"].append(
            (
                target,
                kind.title() + " · " + target,
                "Preserve this construction entity and all dependent constraints",
            )
        )
        rows = [
            (str(i), e["label"], e["label"])
            for i, e in enumerate(entries)
            if e["kind"] == kind
            and e.get("source_id", feature["inputs"].get("external"))
            == feature["inputs"][saved.get("input", "external")]
        ]
        data["sources"][target] = rows
        binding = {k: v for k, v in saved.items() if k not in {"target", "reverse", "input"}}
        match = next(
            (
                str(i)
                for i, e in enumerate(entries)
                if e["row"] == binding and str(i) in {r[0] for r in rows}
            ),
            None,
        )
        data["defaults"][target] = (
            match if match is not None else rows[0][0] if rows else "NONE",
            saved.get("reverse", False),
        )
    return json.dumps(data)


def draw_projection_repair(layout, context):
    try:
        state = _state(context)
        feature = projected_feature(
            document_state._read_document(state), state.features[state.feature_index].feature_id
        )
    except (ValueError, KeyError, TypeError, IndexError):
        return
    layout.operator(
        "mcad.replace_projection_reference", text="Replace Reference", icon="FILE_REFRESH"
    ).feature_id = feature["id"]


class MCAD_OT_replace_projection_reference(_HistoryDialog, Operator):
    bl_idname = "mcad.replace_projection_reference"
    bl_label = "Replace Projected Reference"
    bl_description = "Replace a construction source without deleting its dimensions or relations"
    bl_options = {"REGISTER", "UNDO"}

    feature_id: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    original_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    staged_token: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    choice_data_json: StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    target: EnumProperty(name="Existing reference", items=_targets, update=_target_changed)
    replacement: EnumProperty(name="Replacement source", items=_sources)
    reverse: BoolProperty(
        name="Flip start and end",
        default=False,
        description="Map the existing start point to the source end, and vice versa",
    )

    def _release(self):
        for name in ("_catalog_evidence", "_plane_evidence"):
            evidence = getattr(self, name, None)
            if evidence is not None:
                evidence.publication.cancel()
                setattr(self, name, None)

    def _review(self, context):
        self._original(context)
        if getattr(self, "staged_token", ""):
            from .staged_edit_ui import validate_review

            validate_review(context, self.staged_token, self.original_json, self._document)
        document_state._assert_binding(context, self._binding)
        return self._catalog_evidence.revalidate(
            backend_runtime.capture(context),
            owner_token=self._binding["owner_token"],
            expected_action="edge_catalog",
            expected_result_version=self._version,
            require_success=True,
        )["result"]

    def invoke(self, context, event):
        try:
            if not self.poll(context):
                raise ValueError("Finish or cancel the active sketch before replacing a reference.")
            state = _state(context)
            self.original_json = state.document_json
            if getattr(self, "staged_token", ""):
                from .staged_edit_ui import review_document

                self._document = review_document(context, self.staged_token, self.original_json)
            else:
                self._document = json.loads(self.original_json)
            if not self.feature_id:
                self.feature_id = state.features[state.feature_index].feature_id
            self._feature = projected_feature(self._document, self.feature_id)
            upstream = source_document(self._document, self.feature_id)
            self._source_id = next(iter(self._feature["inputs"].values()))
            self._version = document_state._result_version(self._document)
            with document_state.replay_guard(context):
                self._binding = document_state._capture_binding(context)
                prepared = backend_contracts.prepare_request(
                    {
                        "protocol_version": 1,
                        "action": "edge_catalog",
                        "result_version": self._version,
                        "document": upstream,
                        "options": {"linear_deflection": self._binding["deflection"], "projection_arcs": True},
                    }
                )
                self._catalog_evidence = guarded_transport.execute(
                    prepared,
                    self._binding["selection"],
                    owner_token=self._binding["owner_token"],
                    current_selection=lambda: backend_runtime.capture(context),
                )
                review = self._review(context)
                self._plane = None
                if "support" in self._feature["inputs"]:
                    self._plane_binding = document_state._capture_binding(context)
                    self._plane_evidence = document_state._run_sidecar(
                        context, self._document, binding=self._plane_binding
                    )
                    full = document_state._evidence_projection(
                        context, self._document, self._plane_evidence, self._plane_binding
                    )["result"]
                    self._plane = next(
                        f for f in full["features"] if f["id"] == self.feature_id
                    ).get("support_plane")
                    if self._plane is None:
                        raise ValueError(
                            "Repair the sketch support first; its plane is unresolved."
                        )
            self._entries = []
            self._source_solved = None
            for port, rows in projection_groups(self._feature["projections"]).items():
                source_id = self._feature["inputs"][port]
                source_solved = None
                if is_solid_projection(rows):
                    for entry in review["catalogs"].get(source_id, []):
                        if "arc" in entry:
                            kind = "arc"
                            row = {"kind": kind, "faces": entry["faces"],
                                   "endpoint_faces": entry["arc"]["endpoint_faces"]}
                            edge = {"kind": kind, "faces": entry["faces"], **entry["arc"]}
                        elif "circle" in entry:
                            kind = "circle"
                            row = {"kind": kind, "faces": entry["faces"]}
                            edge = {**row, **entry["circle"]}
                        elif "endpoint_faces" in entry and len(entry["points"]) == 2:
                            kind = "line"
                            row = {k: entry[k] for k in ("faces", "endpoint_faces")}
                            edge = {**row, "points": entry["points"]}
                        else:
                            continue
                        self._entries.append(
                            {
                                "kind": kind,
                                "source_id": source_id,
                                "source_solved": source_solved,
                                "row": row,
                                "edge": edge,
                                "label": kind.title()
                                + " · "
                                + " / ".join(f.rsplit("/face/", 1)[-1] for f in entry["faces"]),
                            }
                        )
                else:
                    source = next(f for f in review["replay"]["features"] if f["id"] == source_id)
                    source_solved = source["sketch"]["solved"]
                    for kind, collection in (("line", "lines"), ("circle", "circles")):
                        for entity in source_solved[collection]:
                            self._entries.append(
                                {
                                    "kind": kind,
                                    "source_id": source_id,
                                    "source_solved": source_solved,
                                    "row": {"source": entity["id"]},
                                    "label": kind.title() + " · " + entity["id"],
                                }
                            )
            self.choice_data_json = _choice_data(self._feature, self._entries)
            self.target = self._feature["projections"][0]["target"]
            _target_changed(self, context)
            return context.window_manager.invoke_props_dialog(
                self,
                width=700,
                confirm_text="Apply Repair" if getattr(self, "staged_token", "") else "Replace",
            )
        except Exception as exc:
            self._release()
            return _reject_candidate(self, context, str(exc))

    def _candidate(self):
        entry = self._entries[int(self.replacement)]
        return replace_reference(
            self._document,
            self.feature_id,
            self.target,
            entry["row"],
            source_id=entry.get("source_id", self._source_id),
            source_solved=entry.get("source_solved", self._source_solved),
            edge=entry.get("edge"),
            plane=self._plane,
            reverse=self.reverse,
        )

    def draw(self, context):
        layout = self.layout
        staged = bool(getattr(self, "staged_token", ""))
        if staged:
            from .staged_edit_ui import draw_review_notice

            draw_review_notice(layout)
        saved = next(row for row in self._feature["projections"] if row["target"] == self.target)
        source_id = self._feature["inputs"][saved.get("input", "external")]
        source = next(f for f in self._document["features"] if f["id"] == source_id)
        layout.label(text="Source: " + source["label"] + " [" + source_id + "]")
        layout.prop(self, "target")
        layout.prop(self, "replacement")
        try:
            kind = target_kind(self._feature, self.target)
            if kind in {"line", "arc"}:
                layout.prop(self, "reverse")
            candidate = self._candidate()
            sketch = projected_feature(candidate, self.feature_id)["sketch"]
            points = {p["id"]: p for p in sketch["points"]}
            if kind in {"line", "arc"}:
                line = next(e for e in sketch["arcs" if kind == "arc" else "lines"] if e["id"] == self.target)
                for role in ("start", "end"):
                    p = points[line[role]]
                    layout.label(text=f"{role.title()} {p['id']} → ({p['u']:.6g}, {p['v']:.6g}) mm")
            else:
                circle = next(e for e in sketch["circles"] if e["id"] == self.target)
                p = points[circle["center"]]
                layout.label(
                    text=f"Center ({p['u']:.6g}, {p['v']:.6g}) mm; radius {circle['radius']:.6g} mm"
                )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            layout.label(text="Needs review: " + str(exc), icon="ERROR")
        layout.label(
            text="Keeps target identities, dimensions and relations. No nearest-edge guessing."
        )
        if not staged:
            layout.label(
                text="Whole Part must rebuild successfully. Cancel changes nothing; Undo restores."
            )

    def execute(self, context):
        try:
            if not self.poll(context):
                raise ValueError("Finish the active operation before replacing a reference.")
            self._review(context)
            if getattr(self, "_plane_evidence", None) is not None:
                document_state._evidence_projection(
                    context, self._document, self._plane_evidence, self._plane_binding
                )
            candidate = self._candidate()
            if getattr(self, "staged_token", ""):
                from . import staged_edit

                success = staged_edit.accept(context, self.staged_token, candidate)
                if success is None:
                    from .staged_edit_ui import report_repair_kept

                    return report_repair_kept(self, context)
            else:
                success = document_state._commit_candidate(
                    context, candidate, _state(context).document_path
                )
            return _report_result(self, context, success)
        except Exception as exc:
            return _reject_candidate(self, context, str(exc))
        finally:
            self._release()

    def cancel(self, context):
        # Close only this review. The live proposal (even a newer revision), its
        # history and saved intent belong to explicit Discard/lifecycle handling.
        self._release()


CLASSES = (MCAD_OT_replace_projection_reference,)
