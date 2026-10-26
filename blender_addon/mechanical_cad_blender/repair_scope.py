"""Pure allowlisted proposal transitions; no native evidence or publication."""


def _same(a, b):
    """Intent equality retains literal types, not Python's 1 == 1.0 coercion."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    return a == b


def repair_target(before, after):
    """Limit changes to one binding and its managed driver values."""
    old_projections = before.get("projections", [])
    new_projections = after.get("projections", [])
    changed = [b for a, b in zip(old_projections, new_projections, strict=True) if a != b]
    if not changed:
        if not all(
            "support" in f.get("inputs", {}) and f.get("support_face") for f in (before, after)
        ):
            raise ValueError("Repair must retain the sketch's explicit support binding.")
        if before["sketch"] != after["sketch"]:
            raise ValueError("Repair of support must preserve local sketch geometry.")
        return None
    if len(changed) != 1 or any(
        before.get(key) != after.get(key) for key in ("inputs", "support_face", "support_intent")
    ):
        raise ValueError("Repair must change one reference binding at a time.")
    target = changed[0]["target"]
    original = next(row for row in old_projections if row["target"] == target)
    if original.get("input", "external") != changed[0].get("input", "external"):
        raise ValueError("Repair cannot switch a reference's bound source port.")
    old, new = before["sketch"], after["sketch"]
    collections = {"points", "lines", "circles", "arcs", "constraints"}
    if any(old.get(k) != new.get(k) for k in set(old) | set(new) if k not in collections):
        raise ValueError("Repair cannot change sketch plane or source metadata.")
    points = set()
    for row in old.get("lines", []) + old.get("circles", []) + old.get("arcs", []):
        if row["id"] == target:
            points.update(row[k] for k in ("start", "end", "center") if k in row)
    for collection in collections:
        for a, b in zip(old.get(collection, []), new.get(collection, []), strict=True):
            allowed = set()
            if collection == "points" and a["id"] in points:
                allowed = {"u", "v"}
            elif collection == "circles" and a["id"] == target:
                allowed = {"radius"}
            elif collection == "arcs" and a["id"] == target:
                allowed = {"direction"}
            elif collection == "constraints":
                if a.get("kind") == "fixed" and a.get("refs") in [[p] for p in points]:
                    allowed = {"target"}
                elif a.get("kind") == "radius" and a.get("refs") == [target]:
                    allowed = {"value"}
            if any(a.get(k) != b.get(k) for k in set(a) | set(b) if k not in allowed):
                raise ValueError("Repair changed unrelated sketch geometry or formulas.")
    return target


def validate_transition(before, candidate, edited_feature_id, failed_ids):
    # The review may revise one supported reference consumer only. All retained
    # upstream edits and unrelated features remain byte-for-byte model values.
    if any(
        not _same(before.get(k), candidate.get(k))
        for k in set(before) | set(candidate)
        if k != "features"
    ):
        raise ValueError("Repair cannot change the proposed Part envelope.")
    old = before["features"]
    new = candidate.get("features", [])
    if len(old) != len(new):
        raise ValueError("Repair cannot add or delete dependent features.")
    changed = [(a, b) for a, b in zip(old, new, strict=True) if not _same(a, b)]
    if len(changed) != 1 or changed[0][0].get("kind") not in {
        "sketch_constrained",
        "extrude_to_face",
    }:
        raise ValueError("Repair must explicitly revise one supported reference consumer.")
    a, b = changed[0]
    if a["id"] == edited_feature_id or a["id"] not in failed_ids:
        raise ValueError("Repair must target a failed downstream consumer, not the upstream edit.")
    if a["kind"] == "extrude_to_face":
        from .end_face_repair import eligible_target_ids

        if any(
            not _same(a.get(k), b.get(k))
            for k in set(a) | set(b)
            if k not in {"inputs", "end_face"}
        ):
            raise ValueError(
                "End-face repair must preserve profile, direction, offset and other extrusion data."
            )
        if (
            set(a.get("inputs", {})) != {"profile", "target"}
            or set(b.get("inputs", {})) != {"profile", "target"}
            or a["inputs"]["profile"] != b["inputs"]["profile"]
            or b["inputs"]["target"] not in eligible_target_ids(before, a["id"])
        ):
            raise ValueError(
                "End-face repair requires an earlier dependency-safe target and the original profile."
            )
        face = b.get("end_face")
        if (
            not isinstance(face, str)
            or not face
            or len(face) > 512
            or face.startswith(("snapshot:", "pending:"))
        ):
            raise ValueError("End-face repair requires an explicit stable semantic face.")
        return a["id"], None
    allowed = {"inputs", "support_face", "support_intent", "projections", "sketch"}
    if any(a.get(k) != b.get(k) for k in set(a) | set(b) if k not in allowed):
        raise ValueError("Repair changed unrelated sketch data.")
    if any(
        a.get("inputs", {}).get(key) != b.get("inputs", {}).get(key)
        for key in set(a.get("inputs", {})) | set(b.get("inputs", {}))
        if key != "support"
    ):
        raise ValueError("Repair must retain the existing external reference source.")
    if [row["target"] for row in a.get("projections", [])] != [
        row["target"] for row in b.get("projections", [])
    ]:
        raise ValueError("Repair cannot remove or reorder projected construction entities.")
    for collection in ("points", "lines", "circles", "arcs", "constraints"):
        old_rows = a["sketch"].get(collection, [])
        new_rows = b["sketch"].get(collection, [])
        if [row["id"] for row in old_rows] != [row["id"] for row in new_rows]:
            raise ValueError("Repair must preserve sketch entity and relation identities.")
        if collection == "constraints" and any(
            old.get("kind") != new.get("kind") or old.get("refs") != new.get("refs")
            for old, new in zip(old_rows, new_rows, strict=True)
        ):
            raise ValueError("Repair must preserve dependent sketch relations.")

    return a["id"], repair_target(a, b)
