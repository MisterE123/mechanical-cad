"""Bounded explicit opening identities; no mesh indices or inferred face repair."""

import json


def opening_ids(encoded, legacy=""):
    """Keep the legacy singleton scripting argument, but never accept an empty list."""
    values = json.loads(encoded) if encoded else [legacy]
    if (
        not isinstance(values, list)
        or not 1 <= len(values) <= 64
        or any(not isinstance(value, str) or not value or value == "NONE" for value in values)
    ):
        raise ValueError("Choose between 1 and 64 stable planar opening faces")
    if len(set(values)) != len(values):
        raise ValueError("Choose each opening face only once")
    return values


def toggle_opening(selected, source, hit):
    """A multi-pick stays on one explicit input body and toggles unique identities."""
    base, face = hit
    if source and base != source:
        raise ValueError("Pick all openings on the same input body")
    values = list(selected)
    if face in values:
        values.remove(face)
    elif len(values) == 64:
        raise ValueError("A shell supports at most 64 opening faces")
    else:
        values.append(face)
    return base, values
