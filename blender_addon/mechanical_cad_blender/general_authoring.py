"""Bounded pure presentation intent around an unchanged GeneralSketchDraft.

A proposal is an observed, unfinished operation, never an accepted command or a
pointer lease. The live command draft is explicit at ``command_draft``. UI edits
never invoke it, invalidate its evidence, or change manufacturing meaning.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from .general_sketch_commands import (
    PointRef,
    PointSeed,
    _coordinate,
    _identifier,
    _integer,
    _json,
    _keys,
    _point,
    _require,
    _successor,
)
from .general_sketch_draft import GeneralSketchDraft

UI_VERSION = 1
ARC_UI_VERSION = 2
MAX_SELECTION = 32
MAX_ANNOTATIONS = 512
TOOLS = frozenset({"Select", "Line", "Rectangle", "Circle", "Dimension"})
ARC_TOOLS = TOOLS | {"Arc"}
_COLLECTIONS = {
    "point": "points",
    "line": "lines",
    "circle": "circles",
    "constraint": "constraints",
}
_ARC_COLLECTIONS = {**_COLLECTIONS, "arc": "arcs"}
_PREFIXES = {"p": "point", "l": "line", "c": "circle", "r": "constraint", "a": "arc"}
_GENERATED_ID = re.compile(r"([plcra])_d([1-9][0-9]*)")
_POINT_ROLES = {"line": {"start", "end"}, "circle": {"center"}, "arc": {"center", "start", "end"}}


@dataclass(frozen=True)
class BindingStatus:
    """Deterministic UI availability; never successful solver evidence."""

    scope: str
    identifier: str | None
    state: str

    @property
    def available(self):
        return self.state == "available"


@dataclass(frozen=True)
class AuthoringStatus:
    command_revision: int
    ui_revision: int
    proposal: BindingStatus | None
    selection: tuple[BindingStatus, ...]
    annotations: tuple[BindingStatus, ...]

    @property
    def conflicts(self):
        values = () if self.proposal is None else (self.proposal,)
        return tuple(
            item for item in values + self.selection + self.annotations if not item.available and item.state != "retired"
        )


def _journal_version(ui_version):
    _require(
        type(ui_version) is int and ui_version in (UI_VERSION, ARC_UI_VERSION),
        "Unsupported authoring UI capability.",
    )
    return 2 if ui_version == UI_VERSION else 3


def empty_ui(*, ui_version=UI_VERSION):
    """Explicit opt-in editor defaults; never a command-checkpoint migration."""
    _journal_version(ui_version)
    return {
        "schema_version": ui_version,
        "revision": 0,
        "tool": "Select",
        "selection": [],
        "proposal": None,
        "annotations": {},
    }


class _Bindings:
    """Bounded identity evidence from the audited checkpoint, not proximity.

    Original and retained records prove kind/refs. The permanent ID ledger can
    prove only the kind of a generated, no-longer-observable identity. It cannot
    prove a removed relation's old refs; such annotations stay quarantined.
    """

    def __init__(self, draft, ui_version):
        self.ui_version = ui_version
        self.collections = _COLLECTIONS if ui_version == UI_VERSION else _ARC_COLLECTIONS
        checkpoint = draft.checkpoint_payload()
        original = GeneralSketchDraft(
            draft.document_json,
            draft.feature_id,
            draft.is_edit,
            journal_version=_journal_version(ui_version),
        ).sketch
        history = checkpoint["journal"]
        sketches = [original, history["anchor"], checkpoint["accepted_sketch"]]
        for entry in history["entries"]:
            sketches.extend((entry["before"], entry["after"]))
        self.records = {}
        for sketch in sketches:
            for kind, collection in self.collections.items():
                for record in sketch.get(collection, []):
                    self.records.setdefault(record["id"], {}).setdefault(kind, []).append(record)
        self.plane_id = checkpoint["accepted_sketch"]["plane"]["id"]
        self.allocated = set(checkpoint["allocated_ids"])
        self.current = {
            record["id"]: (kind, record)
            for kind, collection in self.collections.items()
            for record in checkpoint["accepted_sketch"].get(collection, [])
        }

    def require_identity(self, kind, identifier):
        _require(type(kind) is str and kind in self.collections, "Unknown UI binding kind.")
        _identifier(identifier)
        _require(identifier in self.allocated, "UI binding has an unreserved stable identity.")
        records = self.records.get(identifier)
        if records is not None:
            _require(kind in records, "UI binding identity has the wrong entity kind.")
        else:
            generated = _GENERATED_ID.fullmatch(identifier)
            _require(
                generated is not None and _PREFIXES[generated[1]] == kind,
                "UI binding kind has no retained identity provenance.",
            )

    def entity_status(self, scope, kind, identifier):
        current = self.current.get(identifier)
        state = "missing" if current is None else "available" if current[0] == kind else "changed"
        return BindingStatus(scope, identifier, state)

    def relation_observed(self, identifier, binding):
        return any(
            record["kind"] == binding["kind"] and record["refs"] == binding["refs"]
            for record in self.records.get(identifier, {}).get("constraint", [])
        )

    def require_annotation(self, identifier, binding):
        from .reference_dimensions import is_reference, validate_reference

        if "retirement" in binding:
            from .annotation_retirement import validate_retirement

            _require(self.ui_version == ARC_UI_VERSION, "Retirement requires UI capability 2.")
            validate_retirement(identifier, binding)
            return  # Historical display intent only; it reserves no model identities.
        if is_reference(binding):
            validate_reference(identifier, binding)
            # Missing read-only metadata is retained, never given geometric
            # authority. Newly authored references require a current target below.
            return
        self.require_identity("constraint", identifier)
        _keys(binding, {"kind", "refs", "display", "offset"})
        kind, refs = binding["kind"], binding["refs"]
        _require(
            type(kind) is str and kind in {"distance", "radius", "angle"},
            "Unsupported annotation kind.",
        )
        _require(
            type(refs) is list and len(refs) == (2 if kind in {"distance", "angle"} else 1),
            "Invalid annotation references.",
        )
        for identifier_ref in refs:
            if kind == "angle":
                self.require_identity("line", identifier_ref)
            elif kind == "distance":
                self.require_identity("point", identifier_ref)
            else:
                self.require_radius_target(identifier_ref)
        _require(len(set(refs)) == len(refs), "Duplicate annotation references.")
        _require(
            (binding["display"] == kind or (kind == "radius" and binding["display"] == "diameter")), "Annotation display must match the driving dimension kind."
        )
        _require(type(binding["offset"]) is list, "Expected stored annotation offset coordinates.")
        _point(binding["offset"])
        # A retained record makes a false claimed signature detectable. A ledger
        # tombstone alone cannot; it is preserved as unverified, never rebound.
        _require(
            identifier not in self.records or self.relation_observed(identifier, binding),
            "Annotation kind/refs have no matching retained relation provenance.",
        )

    def require_radius_target(self, identifier):
        """Resolve the actual source kind; a role or caller guess is not identity."""
        _identifier(identifier)
        allowed = {"circle"} if self.ui_version == UI_VERSION else {"circle", "arc"}
        records = self.records.get(identifier, {})
        kinds = set(records).intersection(allowed)
        if not records:
            generated = _GENERATED_ID.fullmatch(identifier)
            if generated is not None and _PREFIXES[generated[1]] in allowed:
                kinds.add(_PREFIXES[generated[1]])
        _require(len(kinds) == 1, "Radius annotation target has no curve-kind provenance.")
        self.require_identity(next(iter(kinds)), identifier)

    def existing_point(self, point_id, *, source_kind=None, source_id=None, role=None):
        self.require_identity("point", point_id)
        _require(
            self.entity_status("point input", "point", point_id).available,
            "The chosen point is unavailable.",
        )
        if any(value is not None for value in (source_kind, source_id, role)):
            _require(
                type(source_kind) is str
                and source_kind in _POINT_ROLES
                and source_kind in self.collections,
                "Unsupported point source kind.",
            )
            _require(
                type(role) is str and role in _POINT_ROLES[source_kind],
                "The source kind does not have that point role.",
            )
            self.require_identity(source_kind, source_id)
            source = self.current.get(source_id)
            _require(
                source is not None and source[0] == source_kind,
                "The chosen point source is unavailable.",
            )
            _require(source[1][role] == point_id, "The chosen point has the wrong source role.")
        return PointRef(point_id)

    def annotation_status(self, identifier, binding):
        from .reference_dimensions import is_reference, reference_status

        if "retirement" in binding:
            from .annotation_retirement import retired_status

            return BindingStatus("annotation", identifier, retired_status(
                identifier, binding, set(self.current) | {self.plane_id}))
        if is_reference(binding):
            state = reference_status(
                binding, {key: value[0] for key, value in self.current.items()}
            )
            return BindingStatus("annotation", identifier, state)
        if not self.relation_observed(identifier, binding):
            return BindingStatus("annotation", identifier, "unverified")
        current = self.current.get(identifier)
        if current is None:
            state = "missing"
        elif (
            current[0] != "constraint"
            or current[1]["kind"] != binding["kind"]
            or current[1]["refs"] != binding["refs"]
        ):
            state = "changed"
        else:
            allowed = (
                {"point"}
                if binding["kind"] == "distance"
                else ({"circle"} if self.ui_version == UI_VERSION else {"circle", "arc"})
            )
            state = "available"
            for target in binding["refs"]:
                source = self.current.get(target)
                if source is None:
                    state = "missing"
                    break
                if source[0] not in allowed:
                    state = "changed"
                    break
        return BindingStatus("annotation", identifier, state)


def _anchor_payload(anchor):
    if type(anchor) is PointRef:
        return {"kind": "existing", "point_id": _identifier(anchor.id)}
    _require(type(anchor) is PointSeed, "Choose an explicit point ID or new XY coordinate.")
    return {"kind": "new", "position": _point((anchor.u, anchor.v))}


def _validate_anchor(anchor, bindings):
    _require(type(anchor) is dict, "Invalid proposal anchor.")
    if anchor.get("kind") == "existing":
        _keys(anchor, {"kind", "point_id"})
        bindings.require_identity("point", anchor["point_id"])
    else:
        _keys(anchor, {"kind", "position"})
        _require(anchor["kind"] == "new", "Unsupported proposal anchor kind.")
        _require(type(anchor["position"]) is list, "Expected stored XY coordinates.")
        _point(anchor["position"])


def _proposal_status(proposal, bindings):
    if proposal is None:
        return None
    anchors = (
        (proposal["center"], proposal["start"], proposal["observation"])
        if proposal["kind"] == "arc"
        else (proposal["anchor"],)
    )
    available = BindingStatus("proposal", None, "available")
    for anchor in anchors:
        if anchor is not None and anchor["kind"] == "existing":
            status = bindings.entity_status("proposal", "point", anchor["point_id"])
            if not status.available:
                return status
            available = status
    return available


def _observed_radius(value):
    # Zero is a legitimate first observed pointer radius, not a valid circle
    # command. Acceptance remains exclusively the command draft's responsibility.
    _coordinate(value)
    _require(value >= 0, "Observed radius must be between 0 and 1,000,000 mm.")
    return value


def _validate_arc_proposal(proposal, bindings):
    _keys(proposal, {"kind", "phase", "center", "start", "observation", "direction"})
    _require(proposal["kind"] == "arc", "Unsupported arc proposal kind.")
    _require(
        type(proposal["phase"]) is str and proposal["phase"] in {"start", "end"},
        "Unsupported arc proposal phase.",
    )
    _require(
        type(proposal["direction"]) is str and proposal["direction"] in {"ccw", "cw"},
        "Unsupported arc direction.",
    )
    _validate_anchor(proposal["center"], bindings)
    if proposal["phase"] == "start":
        _require(proposal["start"] is None, "An arc start is not chosen in start phase.")
    else:
        _validate_anchor(proposal["start"], bindings)
        center, start = proposal["center"], proposal["start"]
        _require(
            center["kind"] != "existing"
            or start["kind"] != "existing"
            or center["point_id"] != start["point_id"],
            "Arc center and start must have distinct point IDs.",
        )
    if proposal["observation"] is not None:
        # A rejected endpoint is retained exactly, including repeated existing IDs.
        # It is an observation, not a selected/accepted arc role or a command.
        _validate_anchor(proposal["observation"], bindings)


def _validate_ui(ui, bindings, *, expected_ui_version=UI_VERSION):
    fields = {"schema_version", "revision", "tool", "selection", "proposal", "annotations"}
    _keys(ui, fields | ({"pending_length"} if "pending_length" in ui else set()) | ({"pending_diameter"} if "pending_diameter" in ui else set()))
    _require(
        type(ui["schema_version"]) is int and ui["schema_version"] == expected_ui_version,
        "Unsupported authoring UI version.",
    )
    _integer(ui["revision"])
    tools = TOOLS if expected_ui_version == UI_VERSION else ARC_TOOLS
    _require(type(ui["tool"]) is str and ui["tool"] in tools, "Unsupported sketch tool.")
    selection = ui["selection"]
    _require(
        type(selection) is list and len(selection) <= MAX_SELECTION, "UI selection is too large."
    )
    selected = set()
    for binding in selection:
        _keys(binding, {"kind", "id"})
        bindings.require_identity(binding["kind"], binding["id"])
        _require(binding["id"] not in selected, "Duplicate selection identity.")
        selected.add(binding["id"])
    proposal = ui["proposal"]
    if proposal is not None:
        _require(type(proposal) is dict, "Invalid unfinished proposal.")
        if proposal.get("kind") == "arc":
            _require(
                expected_ui_version == ARC_UI_VERSION, "Arc proposals require UI capability 2."
            )
            _validate_arc_proposal(proposal, bindings)
        elif proposal.get("kind") in {"line", "rectangle"}:
            _keys(proposal, {"kind", "anchor", "endpoint"})
            if proposal["endpoint"] is not None:
                _require(
                    type(proposal["endpoint"]) is list, "Expected stored endpoint coordinates."
                )
                _point(proposal["endpoint"])
        else:
            _keys(proposal, {"kind", "anchor", "radius"})
            _require(proposal["kind"] == "circle", "Unsupported unfinished proposal kind.")
            if proposal["radius"] is not None:
                _observed_radius(proposal["radius"])
        if proposal["kind"] == "rectangle":
            _require(proposal["anchor"].get("kind") == "new", "Rectangle needs new corners.")
        if proposal["kind"] != "arc":
            _validate_anchor(proposal["anchor"], bindings)
    if "pending_length" in ui:
        from .pending_line_length import validate_pending

        validate_pending(ui["pending_length"], proposal, bindings)
    if "pending_diameter" in ui:
        from .pending_circle_diameter import validate_pending
        _require(ui["tool"] == "Circle", "Pending diameter requires the Circle tool.")
        validate_pending(ui["pending_diameter"], proposal, bindings)
    _require(not ("pending_length" in ui and "pending_diameter" in ui), "Only one driving field can be pending.")
    annotations = ui["annotations"]
    _require(
        type(annotations) is dict and len(annotations) <= MAX_ANNOTATIONS,
        "Too many annotation placements.",
    )
    for identifier, binding in annotations.items():
        bindings.require_annotation(identifier, binding)
    _json(ui)  # Bound expansion and reject invalid Unicode before taking ownership.
    return copy.deepcopy(ui)


class GeneralSketchAuthoringState:
    """An owned command draft plus independent, strictly bounded UI intent.

    Construction snapshots the caller's draft and drops transient evidence. The
    owned ``command_draft`` is live and explicit: adapters use its audited APIs for
    commands/Undo/driver validation. Status is derived afresh after those changes.
    All returned UI dictionaries and constructor inputs are detached copies.
    """

    def __init__(self, command_draft: GeneralSketchDraft, ui=None, *, ui_version=UI_VERSION):
        _require(
            type(command_draft) is GeneralSketchDraft, "Expected a general sketch command draft."
        )
        journal_version = _journal_version(ui_version)
        _require(
            command_draft.journal_version == journal_version,
            "Authoring UI and journal capabilities do not match.",
        )
        owned = GeneralSketchDraft.from_checkpoint_payload(
            command_draft.checkpoint_payload(),
            expected_journal_version=journal_version,
        )
        bindings = _Bindings(owned, ui_version)
        validated = _validate_ui(
            empty_ui(ui_version=ui_version) if ui is None else ui,
            bindings,
            expected_ui_version=ui_version,
        )
        _require(
            not ((validated.get("pending_length") is not None or validated.get("pending_diameter") is not None) and owned.pending_edit is not None),
            "Only one driving field can be pending at a time.",
        )
        self._command_draft, self._ui = owned, validated
        self._binding_revision, self._binding_value = owned.revision, bindings

    @classmethod
    def from_v1_draft(cls, command_draft):
        """Explicit editor selection: unchanged v1 command intent, empty UI defaults."""
        return cls(command_draft, empty_ui())

    def promote_arc_capability(self):
        """Stage explicit UI2/journal3 capability, without accepting an owner checkpoint.

        The caller owns disclosure and atomic saved-slot replacement. Geometry,
        pending text, revisions, selection, history and allocation are unchanged;
        runtime evidence and input capture are never transferred by this codec.
        """
        ui = self.ui_payload()
        ui["schema_version"] = ARC_UI_VERSION
        return type(self)(
            self.command_draft.promote_arc_capability(),
            ui,
            ui_version=ARC_UI_VERSION,
        )

    @property
    def ui_version(self):
        return self._ui["schema_version"]

    @property
    def tools(self):
        return TOOLS if self.ui_version == UI_VERSION else ARC_TOOLS

    @property
    def command_draft(self):
        return self._command_draft

    @property
    def document_json(self):
        return self.command_draft.document_json

    @property
    def feature_id(self):
        return self.command_draft.feature_id

    @property
    def is_edit(self):
        return self.command_draft.is_edit

    @property
    def base_hash(self):
        return self.command_draft.base_hash

    @property
    def revision(self):
        """Command revision only; use ui_revision for presentation changes."""
        return self.command_draft.revision

    @property
    def ui_revision(self):
        return self._ui["revision"]

    @property
    def tool(self):
        return self._ui["tool"]

    @property
    def selection(self):
        return copy.deepcopy(self._ui["selection"])

    @property
    def proposal(self):
        return copy.deepcopy(self._ui["proposal"])

    @property
    def pending_diameter(self):
        return copy.deepcopy(self._ui.get("pending_diameter"))

    @property
    def pending_length(self):
        return copy.deepcopy(self._ui.get("pending_length"))

    @property
    def annotations(self):
        return copy.deepcopy(self._ui["annotations"])

    @property
    def retired_annotation_ids(self):
        """Current bounded identity check only; never replay/dump history to draw."""
        from .annotation_retirement import retired_status

        marked = {key: binding for key, binding in self._ui["annotations"].items()
                  if "retirement" in binding}
        if not marked:
            return ()
        sketch = self.command_draft.sketch
        occupied = {sketch["plane"]["id"], *(record["id"]
                    for name in ("points", "lines", "circles", "arcs", "constraints")
                    for record in sketch.get(name, []))}
        return tuple(key for key, binding in marked.items()
                     if retired_status(key, binding, occupied) == "retired")

    @property
    def display_annotations(self):
        """Exclude expected retirement only; real binding failures stay visible."""
        retired = set(self.retired_annotation_ids)
        return {key: binding for key, binding in self.annotations.items() if key not in retired}

    def ui_payload(self):
        return copy.deepcopy(self._ui)

    def candidate(self):
        return self.command_draft.candidate()

    def require_current(self, document_json):
        self.command_draft.require_current(document_json)

    def _bindings(self):
        # Accepted commands and Undo/Redo advance the audited revision. Pending
        # text/evidence do not change identity. Avoid copying retained history on
        # every pointer observation without hiding command-side invalidation.
        if self._binding_revision != self.revision:
            bindings = _Bindings(self.command_draft, self.ui_version)
            self._binding_value, self._binding_revision = bindings, self.revision
        return self._binding_value

    def _update(self, **changes):
        # Reserve the successor and validate the entire detached value before
        # replacing anything; failure never changes UI, command state or evidence.
        candidate = self.ui_payload()
        if self.pending_length is not None and changes.get("pending_length", False) is not None:
            _require(
                all(
                    key == "pending_length" or value == candidate.get(key)
                    for key, value in changes.items()
                ),
                "Accept or cancel the pending Line length first.",
            )
        if self.pending_diameter is not None and changes.get("pending_diameter", False) is not None:
            _require(all(key == "pending_diameter" or value == candidate.get(key)
                         for key, value in changes.items()), "Accept or cancel the pending Circle diameter first.")
        candidate.update(changes)
        if candidate.get("pending_diameter", False) is None:
            candidate.pop("pending_diameter", None)
        if candidate.get("pending_length", False) is None:
            candidate.pop("pending_length", None)
        bindings = self._bindings()
        validated = _validate_ui(candidate, bindings, expected_ui_version=self.ui_version)
        if _json(validated) == _json(self._ui):
            return False
        validated["revision"] = _successor(self.ui_revision, "UI revision")
        self._ui = validated
        return True

    @property
    def status(self):
        bindings = self._bindings()
        return AuthoringStatus(
            self.revision,
            self.ui_revision,
            _proposal_status(self._ui["proposal"], bindings),
            tuple(
                bindings.entity_status("selection", item["kind"], item["id"])
                for item in self._ui["selection"]
            ),
            tuple(
                bindings.annotation_status(key, self._ui["annotations"][key])
                for key in sorted(self._ui["annotations"])
            ),
        )

    def select_tool(self, tool):
        return self._update(tool=tool)

    def select(self, targets):
        """Replace explicit stable-ID selection; new selections must exist now."""
        _require(
            type(targets) in (tuple, list) and len(targets) <= MAX_SELECTION,
            "UI selection is too large.",
        )
        bindings = self._bindings()
        selection = []
        for target in targets:
            _require(
                type(target) in (tuple, list) and len(target) == 2, "Invalid selection target."
            )
            kind, identifier = target
            bindings.require_identity(kind, identifier)
            _require(
                bindings.entity_status("selection", kind, identifier).available,
                "Selection target is unavailable.",
            )
            selection.append({"kind": kind, "id": identifier})
        return self._update(selection=selection)

    def discard_selection(self, targets):
        """Forget only explicitly named bindings; keep all other UI intent exact.

        A command owner uses this after intentional removal in its staged copy.
        Other missing identities and annotations remain retained, never rebound.
        """
        _require(
            type(targets) in (tuple, list) and len(targets) <= MAX_SELECTION,
            "UI selection is too large.",
        )
        bindings = self._bindings()
        removed = set()
        for target in targets:
            _require(
                type(target) in (tuple, list) and len(target) == 2, "Invalid selection target."
            )
            kind, identifier = target
            bindings.require_identity(kind, identifier)
            removed.add((kind, identifier))
        return self._update(
            selection=[item for item in self.selection if (item["kind"], item["id"]) not in removed]
        )

    def _begin(self, proposal, tool):
        _require(self._ui["proposal"] is None, "Continue or cancel the unfinished proposal first.")
        _require(
            self.command_draft.pending_edit is None, "Accept or cancel the driving field first."
        )
        bindings = self._bindings()
        if proposal["kind"] == "arc":
            _require(self.ui_version == ARC_UI_VERSION, "Arc proposals require UI capability 2.")
            _validate_arc_proposal(proposal, bindings)
        else:
            _validate_anchor(proposal["anchor"], bindings)
        _require(_proposal_status(proposal, bindings).available, "Proposal anchor is unavailable.")
        return self._update(proposal=proposal, tool=tool)

    def begin_line(self, anchor, endpoint=None):
        return self._begin(
            {
                "kind": "line",
                "anchor": _anchor_payload(anchor),
                "endpoint": None if endpoint is None else _point(endpoint),
            },
            "Line",
        )

    def begin_rectangle(self, first, opposite=None):
        _require(type(first) is PointSeed, "Rectangle needs a new local-plane corner.")
        return self._begin(
            {
                "kind": "rectangle",
                "anchor": _anchor_payload(first),
                "endpoint": None if opposite is None else _point(opposite),
            },
            "Rectangle",
        )

    def update_rectangle(self, opposite):
        proposal = self.resume_proposal()
        _require(proposal["kind"] == "rectangle", "No unfinished rectangle proposal.")
        proposal["endpoint"] = _point(opposite)
        return self._update(proposal=proposal)

    def begin_circle(self, anchor, radius=None):
        return self._begin(
            {
                "kind": "circle",
                "anchor": _anchor_payload(anchor),
                "radius": None if radius is None else _observed_radius(radius),
            },
            "Circle",
        )

    @property
    def point_input_phase(self):
        """Pure phase descriptor for a later exact-ID picker; it grants no lease."""
        proposal = self._ui["proposal"]
        if proposal is not None:
            if proposal["kind"] == "arc":
                return ("arc", proposal["phase"])
            if proposal["kind"] == "line":
                return ("line", "end")
            return None
        if self.tool == "Line":
            return ("line", "start")
        if self.tool == "Arc":
            return ("arc", "center")
        return None

    def existing_point(self, point_id, *, source_kind=None, source_id=None, role=None):
        """Validate an exact current PointRef without selecting or accepting it.

        Source kind/ID/role are all-or-none and checked against actual current
        records. The eventual picker owner must still compare source/revisions,
        phase, saved slot, owner/backend identity and inactive pointer capture.
        """
        return self._bindings().existing_point(
            point_id,
            source_kind=source_kind,
            source_id=source_id,
            role=role,
        )

    def begin_arc(self, center, *, direction="ccw"):
        """Record the first explicit point input; no ID or geometry is allocated."""
        return self._begin(
            {
                "kind": "arc",
                "phase": "start",
                "center": _anchor_payload(center),
                "start": None,
                "observation": None,
                "direction": direction,
            },
            "Arc",
        )

    def choose_arc_start(self, start):
        """Choose the second explicit PointInput; the end remains an observation."""
        proposal = self.resume_proposal()
        _require(
            proposal["kind"] == "arc" and proposal["phase"] == "start",
            "No arc proposal is waiting for its start point.",
        )
        anchor = _anchor_payload(start)
        bindings = self._bindings()
        _validate_anchor(anchor, bindings)
        if anchor["kind"] == "existing":
            _require(
                bindings.entity_status("proposal", "point", anchor["point_id"]).available,
                "The chosen arc start point is unavailable.",
            )
        proposal.update(phase="end", start=anchor, observation=None)
        return self._update(proposal=proposal)

    def observe_arc(self, observation):
        """Retain raw new XY or an explicitly chosen existing observation verbatim.

        No circle projection or structural acceptance is performed. A rejected
        existing end observation is still persistable for explicit correction.
        """
        proposal = self.resume_proposal()
        _require(proposal["kind"] == "arc", "No unfinished arc proposal.")
        proposal["observation"] = None if observation is None else _anchor_payload(observation)
        return self._update(proposal=proposal)

    def reverse_arc_proposal(self):
        """Toggle only provisional direction; accepted arcs use their typed command."""
        proposal = self.resume_proposal()
        _require(proposal["kind"] == "arc", "No unfinished arc proposal.")
        proposal["direction"] = "cw" if proposal["direction"] == "ccw" else "ccw"
        return self._update(proposal=proposal)

    def resume_proposal(self):
        """Return detached Continue intent; never capture input or replay a click."""
        _require(self._ui["proposal"] is not None, "No unfinished proposal to continue.")
        _require(self.pending_diameter is None, "Accept or cancel the pending Circle diameter first.")
        _require(self.pending_length is None, "Accept or cancel the pending Line length first.")
        _require(
            self.command_draft.pending_edit is None, "Accept or cancel the driving field first."
        )
        _require(
            self.status.proposal.available,
            "Proposal anchor is unavailable; restore its exact ID or cancel.",
        )
        return self.proposal

    def update_line(self, endpoint):
        proposal = self.resume_proposal()
        _require(proposal["kind"] == "line", "No unfinished line proposal.")
        proposal["endpoint"] = _point(endpoint)
        return self._update(proposal=proposal)

    def update_circle(self, radius):
        proposal = self.resume_proposal()
        _require(proposal["kind"] == "circle", "No unfinished circle proposal.")
        proposal["radius"] = _observed_radius(radius)
        return self._update(proposal=proposal)

    def cancel_proposal(self):
        """Abandon only unfinished UI intent, preserving every accepted command."""
        return self._update(proposal=None, pending_length=None, pending_diameter=None)

    def begin_pending_length(self, endpoint, points, *, axis=None, raw_text=""):
        from .pending_line_length import begin_intent

        intent = begin_intent(self, endpoint, points, axis=axis, raw_text=raw_text)
        return self._update(pending_length=intent)

    def update_pending_length(self, raw_text):
        from .pending_line_length import validate_raw

        intent = self.pending_length
        _require(intent is not None, "No pending Line length.")
        validate_raw(raw_text)
        if raw_text == intent["raw_text"]:
            return False
        intent["raw_text"] = raw_text
        intent["input_revision"] = _successor(
            intent["input_revision"], "Line length input revision"
        )
        return self._update(pending_length=intent)

    def cancel_pending_length(self):
        """Cancel only the field, preserving the exact original Line proposal."""
        return self._update(pending_length=None)

    def begin_pending_diameter(self, points, *, raw_text=""):
        from .pending_circle_diameter import begin_intent
        return self._update(pending_diameter=begin_intent(self, points, raw_text=raw_text))

    def update_pending_diameter(self, raw_text):
        from .pending_line_length import validate_raw
        intent = self.pending_diameter
        _require(intent is not None, "No pending Circle diameter.")
        validate_raw(raw_text)
        if raw_text == intent["raw_text"]:
            return False
        intent["raw_text"] = raw_text
        intent["input_revision"] = _successor(intent["input_revision"], "Circle diameter input revision")
        return self._update(pending_diameter=intent)

    def cancel_pending_diameter(self):
        return self._update(pending_diameter=None)

    def place_annotation(self, constraint_id, offset, *, display=None):
        _identifier(constraint_id)
        relation = next(
            (
                item
                for item in self.command_draft.sketch["constraints"]
                if item["id"] == constraint_id
            ),
            None,
        )
        _require(
            relation is not None and relation["kind"] in {"distance", "radius", "angle"},
            "Choose an existing distance, radius or angle driver.",
        )
        annotations = self.annotations
        annotations[constraint_id] = {
            "kind": relation["kind"],
            "refs": list(relation["refs"]),
            "display": relation["kind"] if display is None else display,
            "offset": _point(offset),
        }
        return self._update(annotations=annotations)

    def place_reference(self, kind, source_kind, source_id, offset):
        from .reference_dimensions import make_reference

        bindings = self._bindings()
        bindings.require_identity(source_kind, source_id)
        _require(
            bindings.entity_status("reference", source_kind, source_id).available,
            "Choose a current authored line, circle or arc for the reference.",
        )
        identifier, binding = make_reference(kind, source_kind, source_id, offset)
        annotations = self.annotations
        if identifier in annotations:
            return identifier, False
        annotations[identifier] = binding
        return identifier, self._update(annotations=annotations)

    def move_annotation(self, constraint_id, offset):
        _identifier(constraint_id)
        annotations = self.annotations
        _require(constraint_id in annotations, "No saved placement for this annotation.")
        status = self._bindings().annotation_status(constraint_id, annotations[constraint_id])
        _require(
            status.available,
            "Annotation binding is unavailable; restore its exact relation or remove the placement.",
        )
        annotations[constraint_id]["offset"] = _point(offset)
        return self._update(annotations=annotations)

    def remove_annotation(self, constraint_id):
        _identifier(constraint_id)
        annotations = self.annotations
        _require(constraint_id in annotations, "No saved placement for this annotation.")
        del annotations[constraint_id]
        return self._update(annotations=annotations)
