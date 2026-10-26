"""Deterministic local-to-planar-support placement, without native imports."""

from __future__ import annotations

import math

from .errors import CADException


def _unit(values):
    norm = math.hypot(*values)
    if not math.isfinite(norm) or norm < 1e-12:
        raise CADException(
            "invalid_support_plane", "Support frame must be finite and nondegenerate."
        )
    return tuple(value / norm for value in values)


def _quaternion(u, v, n):
    matrix = tuple((u[i], v[i], n[i]) for i in range(3))
    trace = sum(matrix[i][i] for i in range(3))
    if trace > 0:
        scale = math.sqrt(trace + 1) * 2
        result = (
            scale / 4,
            (matrix[2][1] - matrix[1][2]) / scale,
            (matrix[0][2] - matrix[2][0]) / scale,
            (matrix[1][0] - matrix[0][1]) / scale,
        )
    else:
        i = max(range(3), key=lambda index: matrix[index][index])
        j, k = (i + 1) % 3, (i + 2) % 3
        scale = math.sqrt(1 + matrix[i][i] - matrix[j][j] - matrix[k][k]) * 2
        vector = [0.0, 0.0, 0.0]
        vector[i] = scale / 4
        vector[j] = (matrix[j][i] + matrix[i][j]) / scale
        vector[k] = (matrix[k][i] + matrix[i][k]) / scale
        result = ((matrix[k][j] - matrix[j][k]) / scale, *vector)
    q = _unit(result)
    # q and -q are equal rotations; canonical sign simplifies independent checks.
    return tuple(-v for v in q) if next((v for v in q if abs(v) > 1e-15), 1) < 0 else q


def multiply_quaternions(a, b):
    w, x, y, z = a
    W, X, Y, Z = b
    return _unit(
        (
            w * W - x * X - y * Y - z * Z,
            w * X + x * W + y * Z - z * Y,
            w * Y - x * Z + y * W + z * X,
            w * Z + x * Y - y * X + z * W,
        )
    )


def rotate(q, point):
    w, x, y, z = q
    a, b, c = point
    return (
        (1 - 2 * (y * y + z * z)) * a + 2 * (x * y - w * z) * b + 2 * (x * z + w * y) * c,
        2 * (x * y + w * z) * a + (1 - 2 * (x * x + z * z)) * b + 2 * (y * z - w * x) * c,
        2 * (x * z - w * y) * a + 2 * (y * z + w * x) * b + (1 - 2 * (x * x + y * y)) * c,
    )


def support_frame(signature):
    """Logical anchor/normal, with explicit tangent or legacy projected-world axes."""
    if signature.get("surface") != "plane":
        raise CADException("nonplanar_support", "Sketch support must be planar.")
    normal = _unit(signature["normal"])
    if "tangent" in signature:
        from .support_intent import frame_basis

        u, _, _ = frame_basis(signature)
        u = _unit(u)
    else:
        reference = (0, 1, 0) if abs(normal[0]) > 0.9 else (1, 0, 0)
        dot = sum(reference[i] * normal[i] for i in range(3))
        u = _unit(tuple(reference[i] - dot * normal[i] for i in range(3)))
    v = (
        normal[1] * u[2] - normal[2] * u[1],
        normal[2] * u[0] - normal[0] * u[2],
        normal[0] * u[1] - normal[1] * u[0],
    )
    origin = tuple(signature["centroid"])
    if len(origin) != 3 or any(not math.isfinite(value) for value in origin):
        raise CADException("invalid_support_plane", "Support centroid must be finite.")
    return origin, _quaternion(u, v, normal)


def resolve_plane(signature, local_plane):
    """Compose immutable authored local plane onto this exact support face."""
    origin, rotation = support_frame(signature)
    translated = rotate(rotation, local_plane["origin"])
    return {
        "id": local_plane["id"],
        "origin": [origin[i] + translated[i] for i in range(3)],
        "quaternion": list(multiply_quaternions(rotation, local_plane["quaternion"])),
    }
