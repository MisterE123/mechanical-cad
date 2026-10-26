"""Compact, non-authoritative labels for frozen edge choices (pure Python)."""

import json

from .projection_edge_choice import projection_kind


def choice_labels(rows, base):
    features = {f["id"]: f.get("label") or f["id"]
                for f in json.loads(base)["features"]}
    entries = [(source, json.loads(raw)) for source, raw in rows]
    labels = []
    for source, entry in entries:
        primary = f"{features.get(source, source)} · {projection_kind(entry)}"
        context = []
        for face in entry["faces"]:
            suffix = face.split("/face/", 1)[-1]
            context.append({"cap.start": "Start cap", "cap.end": "End cap"}.get(
                suffix, "Curved side" if suffix.startswith(("side.arc", "side.circle"))
                else "Straight side" if suffix.startswith("side.line") else suffix))
        labels.append((primary, " · ".join(context)))
    # Friendly names are presentation, not identity. If they collide, expose the
    # exact frozen source/face identity instead of numbering indistinguishable rows.
    return [label if labels.count(label) == 1 else
            (label[0], f"{source} · " + " · ".join(entry["faces"]))
            for label, (source, entry) in zip(labels, entries, strict=True)]
