"""Explicit shared-depth edits, detached from Blender and canonical publication."""

from .history_edit import set_parameter
from .parameter_presentation import parameter_usage
from .unit_input import normalize_unit_input


def depth_parameter(document, feature):
    """Only exact existing names in direct, fixed-depth extrusions qualify."""
    if feature.get("kind") not in {"extrude", "extrude_symmetric"}:
        return ""
    value = feature.get("params", {}).get("length")
    return value if isinstance(value, str) and value in document.get("parameters", {}) else ""


def affected_uses(document, name):
    """Include downstream named formulas; cycles are bounded, never evaluated."""
    pending, visited, uses = [name], set(), []
    while pending:
        current = pending.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for usage in parameter_usage(document, current):
            if usage not in uses:
                uses.append(usage)
            if usage.startswith("Parameter: "):
                pending.append(usage.removeprefix("Parameter: "))
    return tuple(uses)


def edit_shared_depth(original, candidate, feature_id, name, value):
    source = next(f for f in original["features"] if f["id"] == feature_id)
    target = next(f for f in candidate["features"] if f["id"] == feature_id)
    if not name or depth_parameter(original, source) != name:
        raise ValueError("The depth parameter link changed; reopen Edit Feature")
    if target["kind"] not in {"extrude", "extrude_symmetric"}:
        raise ValueError("Shared depth requires Blind or Symmetric extrusion")
    if target["params"].get("length") != name:
        raise ValueError("Shared editing must keep the depth parameter linked")
    if str(original["parameters"][name]) == value:
        return candidate  # Preserve untouched numeric types and authored expressions.
    return set_parameter(
        candidate, name, str(normalize_unit_input(value, "length")), replace_existing=True
    )


def edit_shared_linked_depth(original, candidate, feature_id, tool_id, name, value, *, allow_shared=False):
    """Parameter sharing does not authorize changes to a shared extrusion tool."""
    from .linked_extrusion_edit import SharedToolConsentRequired, linked_extrusion

    for document in (original, candidate):
        for identifier in (feature_id, tool_id):
            if sum(f["id"] == identifier for f in document["features"]) != 1:
                raise ValueError("Ambiguous extrusion binding; reopen Edit Feature")
    linked = linked_extrusion(original, feature_id)
    boolean = next(f for f in candidate["features"] if f["id"] == feature_id)
    if linked is None or linked[0]["id"] != tool_id or boolean["inputs"].get("tool") != tool_id:
        raise ValueError("Extrusion tool changed; reopen Edit Feature")
    if name not in original["parameters"]:
        raise ValueError("The depth parameter link changed; reopen Edit Feature")
    if str(original["parameters"][name]) != value and linked[1] and not allow_shared:
        names = ", ".join(f"{item['label']} ({item['id']})" for item in linked[1])
        raise SharedToolConsentRequired(f"Shared extrusion also changes {names}; explicitly allow shared edits")
    return edit_shared_depth(original, candidate, tool_id, name, value)


def pending_tool_consent(document, feature_id, *, parameter_name="", parameter_value="", **tool_options):
    """Read-only dialog hint using the same pure preflight rules as Apply."""
    from .linked_extrusion_edit import SharedToolConsentRequired, edit_linked_extrusion

    try:
        candidate = edit_linked_extrusion(document, document, feature_id, **tool_options)
        if parameter_name:
            edit_shared_linked_depth(
                document, candidate, feature_id, tool_options["tool_id"],
                parameter_name, parameter_value,
            )
    except SharedToolConsentRequired:
        return True
    except (ValueError, KeyError, StopIteration):
        # Unrelated invalid/stale inputs retain their own Apply diagnostics.
        return False
    return False


def parameter_definition_hint(document, name):
    """Bounded display of stored source, not evaluation or pending editor values."""
    parameters = document.get("parameters", {})
    if not name or name not in parameters:
        return ""
    value = parameters[name]
    if isinstance(value, str):
        label = f"Stored expression: {name} = {value}"
    elif type(value) in {int, float}:
        label = f"Stored value: {name} = {value} mm"
    else:
        return ""
    label = " ".join(label.split())
    return label if len(label) <= 70 else label[:69] + "…"
