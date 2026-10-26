"""Bounded screen-overlap choices; never a topology resolver or saved authority."""

import json

from .sketch_projection import validate_endpoint_faces

MAX_CHOICES = 6


def projection_kind(entry):
    if "arc" in entry:
        return "Arc"
    if "circle" in entry:
        return "Circle"
    if len(entry.get("points", ())) == 2 and "endpoint_faces" in entry:
        return "Line"
    return None


def freeze_candidates(candidates, catalog):
    """Admit only distinct catalog identities, not geometric identity guesses."""
    if len(candidates) > MAX_CHOICES:
        raise ValueError("Too many edges here. Zoom in or orbit, then click again.")
    rows, seen = [], set()
    for _, source, entry, _points, _obj in candidates:
        key = (source, tuple(entry["faces"]))
        matches = [e for e in catalog.get(source, ()) if e["faces"] == entry["faces"]]
        if key in seen or len(matches) != 1 or matches[0] != entry:
            raise ValueError("An edge lacks unique topology identity. Choose another edge.")
        kind = projection_kind(entry)
        if kind in {"Arc", "Line"}:
            endpoints = entry.get("arc", entry).get("endpoint_faces")
            validate_endpoint_faces(endpoints, entry["faces"])
        if kind is None:
            raise ValueError("An overlapping curve lacks supported stable endpoints. Zoom or orbit.")
        seen.add(key)
        rows.append((source, json.dumps(entry, sort_keys=True)))
    if len(rows) < 2:
        raise ValueError("Choose Edge requires multiple distinct proven edges.")
    return tuple(rows)


class EdgeChoice:
    """One picker-owned, one-shot choice. Copies and retired instances refuse."""

    def __init__(self, picker, candidates):
        self.rows = freeze_candidates(candidates, picker.catalog)
        self.picker = picker
        self.catalog_token = picker.catalog_token
        self.evidence = picker.catalog_evidence
        self.objects = tuple(row[4] for row in candidates)
        self.points = tuple(tuple(row[3]) for row in candidates)
        self.selected = None
        self.released = False
        self.retired = False

    def require(self, picker):
        if (self.retired or picker is not self.picker
                or picker.edge_choice is not self
                or picker.catalog_token is not self.catalog_token
                or picker.catalog_evidence is not self.evidence):
            raise ValueError("Choose Edge expired. Click the source again.")

    def select(self, picker, index):
        self.require(picker)
        if not self.released or type(index) is not int or not 0 <= index < len(self.rows):
            raise ValueError("Choose a displayed edge explicitly before Apply.")
        self.selected = index

    def consume(self, picker):
        self.require(picker)
        if self.selected is None:
            raise ValueError("Choose an edge before Apply.")
        self.retired = True
        source, raw = self.rows[self.selected]
        return source, json.loads(raw)
