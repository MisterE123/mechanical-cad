"""Native-compatible point/line offset scaffold; no new canonical constraint kind."""

import math


def perpendicular_foot(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    squared = dx * dx + dy * dy
    if squared < 1e-12:
        raise ValueError("Choose a straight reference line with distinct endpoints.")
    along = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / squared
    foot = (start[0] + along * dx, start[1] + along * dy)
    value = math.dist(point, foot)
    if value < 1e-6:
        raise ValueError("The point is on this line. Use Point on line for a zero offset.")
    return foot, value


def existing_offset(sketch, point_id, line_id):
    """Recognize an exact existing native scaffold, never guess nearby identity."""
    relations = sketch["constraints"]
    for segment in sketch["lines"]:
        if not segment.get("construction") or point_id not in (segment["start"], segment["end"]):
            continue
        foot = segment["end"] if segment["start"] == point_id else segment["start"]
        if not any(
            c["kind"] == "point_on_line" and c["refs"] == [foot, line_id] for c in relations
        ):
            continue
        if not any(
            c["kind"] == "perpendicular" and set(c["refs"]) == {line_id, segment["id"]}
            for c in relations
        ):
            continue
        distance = next(
            (
                c["id"]
                for c in relations
                if c["kind"] == "distance" and set(c["refs"]) == {foot, point_id}
            ),
            None,
        )
        if distance:
            return distance
    return None


def validate_record(record, sketch, *, require, keys):
    require(
        len(record["points"]) == 1
        and len(record["lines"]) == 1
        and not record["circles"]
        and len(record["constraints"]) == 3,
        "An offset needs exactly one construction foot, segment and three relations.",
    )
    foot, segment = record["points"][0], record["lines"][0]
    keys(segment, {"id", "start", "end", "construction"})
    on, normal, distance = record["constraints"]
    keys(on, {"id", "kind", "refs"})
    keys(normal, {"id", "kind", "refs"})
    keys(distance, {"id", "kind", "refs", "value"})
    require(
        on["kind"] == "point_on_line" and len(on["refs"]) == 2,
        "An offset foot must lie on its selected reference line.",
    )
    line_id = on["refs"][1]
    source = next((line for line in sketch["lines"] if line["id"] == line_id), None)
    require(source is not None, "The reference line is unavailable.")
    require(
        segment["construction"] is True
        and segment["start"] == foot["id"]
        and segment["end"] in {p["id"] for p in sketch["points"]}
        and segment["end"] not in (source["start"], source["end"])
        and on["refs"] == [foot["id"], line_id]
        and normal["kind"] == "perpendicular"
        and normal["refs"] == [line_id, segment["id"]]
        and distance["kind"] == "distance"
        and distance["refs"] == [foot["id"], segment["end"]],
        "The offset construction scaffold has inconsistent references.",
    )
