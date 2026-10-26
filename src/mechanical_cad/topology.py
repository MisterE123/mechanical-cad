"""Conservative topology references, independent of Blender and the B-rep kernel.

A kernel's face number is a snapshot-local handle, never a persistent name.
Only an adapter-declared stable semantic role can resolve a persistent reference.
Geometry ranks visible repair proposals; it never authorizes a rebind.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import dist, hypot, isclose, isfinite, sqrt
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class TopologyReference:
    """A saved semantic selection; ``id`` belongs to the document, not the kernel.

    ``signature`` is optional evidence from the selection's original geometry.
    Coordinates must be canonical millimetres, areas square millimetres, normals
    dimensionless. Semantic identity does not depend on this evidence.
    """

    feature_id: str
    role: str
    kind: str = "face"
    body_id: str | None = None
    signature: Mapping[str, Any] = field(default_factory=dict)
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TopologyCandidate:
    """One entity in the current successful rebuild's topology snapshot.

    ``id`` must be unique within that snapshot. Resolving requires an explicit
    ``provenance['semantic_status'] == 'stable'`` assertion by the adapter.
    Other provenance fields can retain source IDs, operation ID and evolution.
    """

    id: str
    feature_id: str
    role: str
    kind: str = "face"
    body_id: str | None = None
    signature: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TopologySuggestion:
    """A heuristic proposal, never an accepted or persistent reference.

    ``score`` orders proposals; it is not a calibrated confidence probability.
    ``tied_with_best`` prevents deterministic display ordering looking like a
    meaningful distinction between geometrically equivalent proposals.
    """

    candidate: TopologyCandidate
    score: float
    evidence: tuple[str, ...]
    tied_with_best: bool = False
    inferred: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Resolution:
    """Fail-closed resolution result with a machine-readable reason code."""

    status: str
    candidate: TopologyCandidate | None = None
    candidates: tuple[TopologyCandidate, ...] = ()
    suggestions: tuple[TopologySuggestion, ...] = ()
    reason: str = ""
    inferred: bool = False

    @property
    def resolved(self) -> bool:
        return self.status == "resolved"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _require_text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _validate(entity: TopologyReference | TopologyCandidate) -> None:
    for name in ("feature_id", "role", "kind"):
        _require_text(getattr(entity, name), name)
    if entity.body_id is not None:
        _require_text(entity.body_id, "body_id")
    if entity.id is not None:
        _require_text(entity.id, "id")
    if isinstance(entity, TopologyCandidate) and entity.id is None:
        raise ValueError("candidate id must be a nonempty string")
    if not isinstance(entity.signature, Mapping):
        raise ValueError("signature must be a mapping")
    if isinstance(entity, TopologyCandidate) and not isinstance(entity.provenance, Mapping):
        raise ValueError("provenance must be a mapping")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except OverflowError:
        return None
    return result if isfinite(result) else None


def _vector(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    vector = tuple(_number(component) for component in value)
    if any(component is None for component in vector):
        return None
    return vector  # type: ignore[return-value]


def _geometry_score(
    reference: Mapping[str, Any], candidate: Mapping[str, Any]
) -> tuple[float, tuple[str, ...]] | None:
    # An explicit unit mismatch is not comparable. Omitted units mean canonical
    # mm under this module's contract; conversion belongs to the input boundary.
    if reference.get("units", "mm") != "mm" or candidate.get("units", "mm") != "mm":
        return None
    parts: list[tuple[float, float]] = []
    evidence: list[str] = []
    ref_surface, cand_surface = reference.get("surface"), candidate.get("surface")
    if isinstance(ref_surface, str) and isinstance(cand_surface, str):
        # A plane and cylinder are not useful repair alternatives for one another.
        if ref_surface != cand_surface:
            return None
        parts.append((0.25, 1.0))
        evidence.append(f"same surface type: {ref_surface}")
    ref_area, cand_area = _number(reference.get("area")), _number(candidate.get("area"))
    if ref_area is not None and cand_area is not None and ref_area > 0 and cand_area > 0:
        relative_delta = abs(ref_area - cand_area) / max(ref_area, cand_area)
        parts.append((0.25, 1.0 - relative_delta))
        evidence.append(f"relative area difference: {relative_delta:.6g}")
    ref_center, cand_center = _vector(reference.get("centroid")), _vector(candidate.get("centroid"))
    if ref_center is not None and cand_center is not None:
        distance = dist(ref_center, cand_center)
        scale = max(sqrt(ref_area), 1e-9) if ref_area is not None and ref_area > 0 else 1.0
        parts.append((0.4, 1.0 / (1.0 + distance / scale)))
        evidence.append(f"centroid distance: {distance:.6g} mm")
    ref_normal, cand_normal = _vector(reference.get("normal")), _vector(candidate.get("normal"))
    if ref_normal is not None and cand_normal is not None:
        ref_length = hypot(*ref_normal)
        cand_length = hypot(*cand_normal)
        if 0 < ref_length < float("inf") and 0 < cand_length < float("inf"):
            cosine = sum(
                (left / ref_length) * (right / cand_length)
                for left, right in zip(ref_normal, cand_normal, strict=True)
            )
            cosine = max(-1.0, min(1.0, cosine))
            parts.append((0.1, (cosine + 1.0) / 2.0))
            evidence.append(f"oriented normal cosine: {cosine:.6g}")
    if not parts:
        return None
    score = sum(weight * value for weight, value in parts) / sum(weight for weight, _ in parts)
    return score, tuple(evidence)


def _suggestions(
    reference: TopologyReference, candidates: Iterable[TopologyCandidate]
) -> tuple[TopologySuggestion, ...]:
    scored: list[tuple[TopologyCandidate, float, tuple[str, ...]]] = []
    for candidate in candidates:
        if candidate.kind != reference.kind:
            continue
        if reference.body_id is not None and candidate.body_id != reference.body_id:
            continue
        score = _geometry_score(reference.signature, candidate.signature)
        if score is not None:
            scored.append((candidate, score[0], score[1]))
    # IDs only stabilize the presentation order, never resolve a score tie.
    scored.sort(key=lambda item: (-item[1], item[0].id))
    best = scored[0][1] if scored else None
    best_count = sum(isclose(score, best, rel_tol=0.0, abs_tol=1e-9) for _, score, _ in scored)
    return tuple(
        TopologySuggestion(
            candidate=candidate,
            score=score,
            evidence=evidence,
            tied_with_best=best_count > 1 and isclose(score, best, rel_tol=0.0, abs_tol=1e-9),
        )
        for candidate, score, evidence in scored
    )


def resolve_reference(
    reference: TopologyReference | Mapping[str, Any],
    candidates: Iterable[TopologyCandidate | Mapping[str, Any]],
) -> Resolution:
    """Resolve supported semantic identity or return a reviewable failure.

    Use only candidates from the *current*, successful rebuild. A caller must
    discard stale candidates after rollback, suppression or failed evaluation.
    Candidate IDs, array position, and geometric similarity never confer identity.
    Duplicate candidate IDs are invalid adapter input and raise ``ValueError``.
    """
    if not isinstance(reference, TopologyReference):
        reference = TopologyReference(**dict(reference))
    _validate(reference)
    current = tuple(
        candidate
        if isinstance(candidate, TopologyCandidate)
        else TopologyCandidate(**dict(candidate))
        for candidate in candidates
    )
    seen: set[str] = set()
    for candidate in current:
        _validate(candidate)
        if candidate.id in seen:
            raise ValueError(f"duplicate snapshot candidate id: {candidate.id}")
        seen.add(candidate.id)
    matches = tuple(
        sorted(
            (
                candidate
                for candidate in current
                if candidate.feature_id == reference.feature_id
                and candidate.role == reference.role
                and candidate.kind == reference.kind
                and (reference.body_id is None or candidate.body_id == reference.body_id)
            ),
            key=lambda candidate: candidate.id,
        )
    )
    if len(matches) == 1 and matches[0].provenance.get("semantic_status") == "stable":
        return Resolution(
            status="resolved",
            candidate=matches[0],
            candidates=matches,
            reason="unique_stable_semantic_match",
        )
    if len(matches) > 1:
        return Resolution(
            status="ambiguous",
            candidates=matches,
            suggestions=_suggestions(reference, current),
            reason="multiple_semantic_matches",
        )
    if matches:
        return Resolution(
            status="ambiguous",
            candidates=matches,
            suggestions=_suggestions(reference, current),
            reason="untrusted_semantic_provenance",
        )
    return Resolution(
        status="missing",
        suggestions=_suggestions(reference, current),
        reason="no_semantic_match",
    )
