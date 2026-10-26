"""Explicit bounded blend edge intent, independent of kernel and Blender."""


def validate_edge_pairs(values):
    if type(values) is not list or not 1 <= len(values) <= 64:
        raise ValueError("Select between 1 and 64 distinct edges")
    normalized = []
    for pair in values:
        if (
            type(pair) is not list
            or len(pair) != 2
            or any(
                type(v) is not str
                or not v
                or len(v) > 512
                or v == "NONE"
                or v.startswith(("snapshot:", "pending:"))
                for v in pair
            )
            or pair[0] == pair[1]
        ):
            raise ValueError("Each edge requires two distinct stable semantic face IDs")
        normalized.append(tuple(sorted(pair)))
    if len(set(normalized)) != len(normalized):
        raise ValueError("Select each edge only once")
    return [list(pair) for pair in sorted(normalized)]
