"""Native-free fixtures with source-qualified sketch and solid references."""

import copy

from staged_edit_cases import feature, same_sketch_projection_case


def two_sketch_sources():
    data, _ = same_sketch_projection_case()
    second = copy.deepcopy(feature(data, "source"))
    second["id"] = "source_two"
    second["sketch"]["id"] = "second_source_geometry"
    second["sketch"]["constraints"][-1]["value"] = 6
    second["sketch"]["constraints"][2]["target"] = [25, 5]
    data["features"].insert(1, second)
    target = feature(data, "target")
    target["inputs"]["external_2"] = "source_two"
    target["projections"][1]["input"] = "external_2"
    return data


def mixed_sources():
    data = two_sketch_sources()
    data["features"] = [f for f in data["features"] if f["id"] != "source_two"]
    data["features"][1:1] = [
        {
            "id": "rim_profile",
            "kind": "sketch_circle",
            "label": "Rim profile",
            "params": {"radius": 10, "x": -12},
            "inputs": {},
        },
        {
            "id": "rim",
            "kind": "extrude",
            "label": "Rim solid",
            "params": {"length": 10},
            "inputs": {"profile": "rim_profile"},
        },
    ]
    target = feature(data, "target")
    target["inputs"]["external_2"] = "rim"
    target["projections"][1] = {
        "input": "external_2",
        "kind": "circle",
        "faces": ["rim/face/cap.end", "rim/face/side.circle"],
        "target": "reference2",
    }
    return data


def two_solid_sources():
    data = mixed_sources()
    data["features"] = [f for f in data["features"] if f["id"] != "source"]
    data["features"][2:2] = [
        {
            "id": name,
            "kind": "transform",
            "label": name,
            "params": {"x": x},
            "inputs": {"base": "rim"},
        }
        for name, x in (("moved_one", 20), ("moved_two", 40))
    ]
    target = feature(data, "target")
    target["inputs"] = {"external": "moved_one", "external_2": "moved_two"}
    target["projections"][0] = {
        "kind": "circle",
        "faces": ["rim/face/cap.end", "rim/face/side.circle"],
        "target": "reference",
    }
    return data


def multiple_source_repairs():
    base = two_sketch_sources()
    target = feature(base, "target")
    target["projections"].append({"source": "ring2", "target": "reference3"})
    sketch = target["sketch"]
    sketch["points"].append({"id": "q3", "u": 14, "v": 3})
    sketch["circles"].append(
        {"id": "reference3", "center": "q3", "radius": 2, "construction": True}
    )
    sketch["constraints"].extend(
        [
            {"id": "anchor3", "kind": "fixed", "refs": ["q3"], "target": [14, 3]},
            {"id": "size3", "kind": "radius", "refs": ["reference3"], "value": 2},
        ]
    )
    proposed = copy.deepcopy(base)
    source = feature(proposed, "source")["sketch"]
    for row in source["circles"]:
        row["id"] = "replacement_" + row["id"]
    for row in source["constraints"]:
        if row["kind"] == "radius":
            row["refs"] = ["replacement_" + row["refs"][0]]
    source["constraints"][1]["value"] = "r + 1"
    return base, proposed
