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


def selected_surface_role(pair, count):
    """Hash authored face identity, never geometry or native enumeration."""
    from hashlib import sha256
    from json import dumps

    if count == 1:
        return "blend.surface"
    return (
        "blend.surface."
        + sha256(dumps(sorted(pair), ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
    )


def unique_generated_images(selected, outputs, claims):
    """Yield (source, output) only for exact, exclusive one-image history.

    Shapes implement IsSame; claims contain every source's native images,
    including unknown face, edge and vertex sources. No geometry is inspected.
    """
    for source in selected:
        own = [images for other, images in claims if source.IsSame(other)]
        if len(own) != 1:
            continue
        images = [face for face in outputs if any(face.IsSame(item) for item in own[0])]
        if len(images) != 1:
            continue
        output = images[0]
        if any(
            not source.IsSame(other) and any(output.IsSame(item) for item in items)
            for other, items in claims
        ):
            continue
        yield source, output
