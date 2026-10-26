"""Explicit, detached reference replacement; never an automatic topology repair."""

from copy import deepcopy

from .sketch_projection import (
    is_solid_projection,
    project_sketch,
    project_solid_edges,
    projection_input_types,
    validate_projections,
)


def projected_feature(document, feature_id):
    feature = next((f for f in document["features"] if f["id"] == feature_id), None)
    if not feature or feature["kind"] != "sketch_constrained" or not feature.get("projections"):
        raise ValueError("Select a saved sketch with projected construction references.")
    return feature


def source_document(document, feature_id):
    """Read-only source ancestry, independent of a broken downstream sketch."""
    feature = projected_feature(document, feature_id)
    source_ids = [
        feature["inputs"][port] for port in projection_input_types(feature["projections"])
    ]
    source_id = source_ids[0]
    lookup = {f["id"]: f for f in document["features"]}
    keep, pending = set(), list(source_ids)
    while pending:
        identifier = pending.pop()
        if identifier == feature_id:
            raise ValueError("A projection source cannot depend on its target sketch.")
        if identifier not in keep:
            keep.add(identifier)
            pending.extend(lookup[identifier]["inputs"].values())
    result = deepcopy(document)
    result["features"] = [f for f in result["features"] if f["id"] in keep]
    result["active_feature"] = source_id
    return result


def target_kind(feature, target):
    for kind, collection in (("line", "lines"), ("circle", "circles"), ("arc", "arcs")):
        if any(e["id"] == target and e.get("construction") for e in feature["sketch"].get(collection, [])):
            return kind
    raise ValueError("Reference target must remain a construction line, circle or arc.")


def replace_reference(
    document,
    feature_id,
    target,
    replacement,
    *,
    source_id,
    source_solved=None,
    edge=None,
    plane=None,
    reverse=False,
):
    """Change exactly one source row and its evaluated managed driver values.

    Evidence must be fresh and independently verified by the caller. The result
    is only intent: ordinary full replay remains required before publication.
    """
    candidate = deepcopy(document)
    feature = projected_feature(candidate, feature_id)
    rows = feature["projections"]
    matches = [i for i, row in enumerate(rows) if row["target"] == target]
    if len(matches) != 1:
        raise ValueError("Choose exactly one existing projected target.")
    saved = rows[matches[0]]
    if feature["inputs"][saved.get("input", "external")] != source_id:
        raise ValueError("Replacement must use the same bound source feature and input port.")
    kind = target_kind(feature, target)
    if type(reverse) is not bool or (kind == "circle" and reverse):
        raise ValueError("Only a line or arc can have an explicit endpoint reversal.")
    if type(replacement) is not dict or {"target", "reverse", "input"} & set(replacement):
        raise ValueError("Choose source fields separately from the target and endpoint direction.")
    row = {**deepcopy(replacement), "target": target}
    if kind in {"line", "arc"} and reverse:
        row["reverse"] = True
    validate_projections([row])
    if is_solid_projection([saved]) != is_solid_projection([row]):
        raise ValueError("Keep the existing solid-edge or sketch-source reference type.")
    sketch = deepcopy(feature["sketch"])
    if "support" in feature["inputs"]:
        if plane is None:
            raise ValueError("Repair the sketch support first; its current plane is unresolved.")
        sketch["plane"] = deepcopy(plane)
    if is_solid_projection([saved]):
        if kind != row.get("kind", "line"):
            raise ValueError("Replacement must have the same analytic kind.")
        evaluated = project_solid_edges(sketch, [edge], [row])
    else:
        evaluated = project_sketch(sketch, source_solved, [row])
    # The canonical local support plane is intent, not the evaluated world frame.
    evaluated["plane"] = deepcopy(feature["sketch"]["plane"])
    feature["sketch"] = evaluated
    rows[matches[0]] = {**row, **({"input": saved["input"]} if "input" in saved else {})}
    validate_projections(rows)
    return candidate
