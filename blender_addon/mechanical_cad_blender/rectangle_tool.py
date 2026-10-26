"""Local-plane rectangle construction and strict atomic command verification.

No Blender or kernel dependency. Corners are new coordinates, not implicit snaps
or coincident references to nearby geometry. H/V relations are explicit intent.
"""


def rectangle_corners(first, opposite):
    """Build corners from coordinates validated by the caller boundary."""
    u, v = first
    x, y = opposite
    return ((u, v), (x, v), (x, y), (u, y))


def validate_rectangle_record(command, *, require, keys):
    """Check structure with the caller's validation/error policy, without imports."""
    points, lines, relations = (command[key] for key in ("points", "lines", "constraints"))
    require(
        len(points) == len(lines) == len(relations) == 4 and not command["circles"],
        "A rectangle needs four shared corners, four lines and four H/V relations.",
    )
    for point in points:
        keys(point, {"id", "u", "v"})
    corners = rectangle_corners((points[0]["u"], points[0]["v"]), (points[2]["u"], points[2]["v"]))
    require(
        [(p["u"], p["v"]) for p in points] == list(corners),
        "Rectangle seeds must match the explicit local-plane corners.",
    )
    for index, (line, relation) in enumerate(zip(lines, relations, strict=True)):
        keys(line, {"id", "start", "end"})
        keys(relation, {"id", "kind", "refs"})
        require(
            line["start"] == points[index]["id"]
            and line["end"] == points[(index + 1) % 4]["id"]
            and relation["kind"] == ("horizontal" if index % 2 == 0 else "vertical")
            and relation["refs"] == [line["id"]],
            "Rectangle must be a closed shared-point loop with explicit H/V intent.",
        )
