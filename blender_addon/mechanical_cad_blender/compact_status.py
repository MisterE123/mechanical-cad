"""Read-only presentation of already qualified CAD evidence.

These labels do not validate caches or promote a solve into a profile/build check.
"""

import json
import textwrap


def sketch_label(report, *, pending=False, current=True):
    if pending:
        return "Check pending", "TIME"
    if not current or report is None:
        return "Unverified · Check sketch", "INFO"
    status = report.get("status")
    if status == "inconsistent":
        return "Conflicting constraints", "ERROR"
    if status == "didnt_converge":
        return "Solve failed · did not converge", "ERROR"
    if status == "too_many_unknowns":
        return "Solve failed · too many unknowns", "ERROR"
    dof = report.get("remaining_dof")
    if status not in {"okay", "redundant_okay"} or type(dof) is not int or dof < 0:
        return "Solve unverified · Check sketch", "INFO"
    label = "Fully defined · 0 DoF" if dof == 0 else f"Underdefined · {dof} DoF"
    if status == "redundant_okay":
        label += " · redundant"
    return label, "CHECKMARK" if dof == 0 else "INFO"


def profile_label(readiness, *, pending=False):
    if pending or readiness is None:
        return "Profile: unchecked", "INFO"
    if readiness.get("ready") is True:
        return "Closed profile available", "CHECKMARK"
    # Callers supply current, bridge-qualified readiness. The native open code
    # is checked against open connectivity, not inferred from solver DoF or counts.
    if readiness.get("ready") is False and (readiness.get("error") or {}).get("code") == "open_profile":
        return "Open sketch · close a loop", "INFO"
    return "Profile unavailable · review boundary", "ERROR"


def geometry_label(status, *, current=False):
    if status == "PASSED" and not current:
        status = "OUTDATED"
    return {
        "PASSED": ("Geometry check passed", "CHECKMARK"),
        "FAILED": ("Geometry check failed · see details", "ERROR"),
        "CHECKING": ("Geometry check pending", "TIME"),
        "OUTDATED": ("Geometry check stale · Check again", "INFO"),
        "UNCHECKED": ("Geometry check: not run", "INFO"),
    }.get(status, ("Geometry: " + status.title(), "INFO"))


def summary(message, width=92):
    """A bounded actionable preview; callers must retain the complete diagnostic."""
    return textwrap.shorten(str(message), width=width, placeholder="…")


def disclosure(layout, state, field, label):
    """Native property toggle; drawing never writes state or canonical data."""
    opened = bool(getattr(state, field, False))
    layout.prop(
        state, field, text=label, emboss=False,
        icon="TRIA_DOWN" if opened else "TRIA_RIGHT",
    )
    return opened


def document_is_empty(document_json):
    """Recognize an explicit empty canonical graph, not a missing history cache."""
    try:
        document = json.loads(document_json)
    except (TypeError, ValueError):
        return False
    return isinstance(document, dict) and document.get("features") == []


def document_is_fresh(state):
    """Conservatively recognize untouched CAD state, not lost/recoverable data."""
    return (
        state.document_json == ""
        and state.status == "EMPTY"
        and len(state.features) == 0
        and getattr(state, "geometry_status", "UNCHECKED") == "UNCHECKED"
        and not any(getattr(state, name, "") for name in (
            "document_name", "document_path", "active_feature", "parameters",
            "last_good_document_id", "last_good_feature_id", "last_good_label",
            "sketch_draft_json", "repair_intent_json", "sketch_notice",
            "error", "last_action_error", "geometry_message",
            "geometry_report_json", "geometry_document_json",
        ))
    )


def part_state_text(status):
    """Plain-language display only; internal lifecycle codes remain unchanged."""
    return {"DIRTY": "Needs rebuild", "BUILDING": "Updating"}.get(status, status.title())


def saved_profile_state(feature):
    """Present a qualified replay output, not solver success or graph admission."""
    if feature.get("status") != "ok":
        return False, "Sketch needs repair · review its error", "ERROR"
    output = feature.get("output") or {}
    if output.get("kind") == "profile":
        return True, "Closed profile available", "CHECKMARK"
    profile = output.get("profile") or {}
    if output.get("kind") == "sketch" and profile.get("state") == "available":
        return True, "Closed profile available", "CHECKMARK"
    reason = (profile.get("reason") or {}).get("message")
    return False, reason or "Profile unavailable · review boundary", "INFO"
