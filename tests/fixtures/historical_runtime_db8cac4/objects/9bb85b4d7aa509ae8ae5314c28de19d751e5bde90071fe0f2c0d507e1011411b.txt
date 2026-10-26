"""Genuine Sketch adapter for the bounded shared source-sector certificate.

This adapter retains full numeric Sketch JSON/hash, unchanged core results and
the independently qualified incidence report. The shared geometry certificate
has its own distinct geometry digest. It does not validate a full Sketch, solve
constraints, certify a native face, or authorize publication. Public records do
not self-authenticate: check_sector_certificate recomputes from the bound Sketch.

All prerequisite, shared-policy and checker work uses one caller-supplied,
non-resetting PrimitiveContext. Carry that context into later native preparation;
starting a fresh context internally is not a way to evade the aggregate cap.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from .arc_profile_incidence import (
    AuthoredArc,
    BoundaryLedger,
    EndpointGap,
    IncidenceReport,
    NominalJoin,
    incidence_preflight,
)
from .arc_profile_primitives import (
    MAX_INTEGER_BITS,
    MAX_OPERATIONS,
    PrimitiveContext,
    PrimitiveError,
)
from .arc_profile_sector_policy import (
    MAX_CERTIFICATE_BYTES,
    MAX_REFINEMENTS,
    OuterDisk,
    ResourceUsage,
    RootAssignment,
    SectorInputError,
    _context,
    _record_bytes,
    classify_sector_geometry,
)
from .arc_profile_sector_policy import ExactRatio as ExactRatio
from .arc_profile_sector_policy import SectorCertificate as GeometryCertificate
from .arc_profile_sector_policy import extrusion_preflight as extrusion_preflight
from .arc_profile_sector_source import (
    SectorArc,
    SectorCircle,
    SectorGeometrySource,
    SectorLine,
    SectorPoint,
)
from .sketch_model import Sketch, validate


@dataclass(frozen=True, slots=True)
class SectorCertificate:
    """Full-Sketch binding around one independently computed shared certificate."""

    version: int
    source_json: str
    source_sha256: str
    incidence: IncidenceReport
    geometry: GeometryCertificate
    resources: ResourceUsage

    @property
    def boundary(self):
        return self.geometry.boundary

    @property
    def assignments(self):
        return self.geometry.assignments

    @property
    def gap_enclosures(self):
        return self.geometry.gap_enclosures

    @property
    def source_cell_radius(self):
        return self.geometry.source_cell_radius

    @property
    def cells(self):
        return self.geometry.cells

    @property
    def outer_proxies(self):
        return self.geometry.outer_proxies

    @property
    def center_proxy(self):
        return self.geometry.center_proxy

    @property
    def clearance(self):
        return self.geometry.clearance

    @property
    def jordan(self):
        return self.geometry.jordan

    @property
    def area(self):
        return self.geometry.area


@dataclass(frozen=True, slots=True)
class SectorResult:
    status: str
    stage: str
    code: str
    incidence: IncidenceReport
    certificate: SectorCertificate | None
    assignments: tuple[RootAssignment, ...]
    cells: tuple[OuterDisk, ...]
    outer_proxies: tuple[OuterDisk, ...]
    resources: ResourceUsage


@dataclass(frozen=True, slots=True)
class CertificateCheck:
    accepted: bool
    code: str
    recomputed: SectorResult | None


_EXTRA_RECORD_TYPES = (
    SectorCertificate,
    AuthoredArc,
    BoundaryLedger,
    EndpointGap,
    IncidenceReport,
    NominalJoin,
)


def certificate_bytes(certificate: SectorCertificate) -> bytes:
    """Type-sensitive encoding of the entire bound certificate, capped at 1 MiB."""
    if type(certificate) is not SectorCertificate:
        raise SectorInputError("invalid_certificate")
    encoded = _record_bytes(certificate, extra_record_types=_EXTRA_RECORD_TYPES)
    if len(encoded) > MAX_CERTIFICATE_BYTES:
        raise SectorInputError("certificate_limit")
    return encoded


def sector_geometry_source(sketch: Sketch) -> SectorGeometrySource:
    """Project genuine validated source geometry; never reinterpret sketch schema.

    This conversion independently calls the unchanged exact-type Sketch validator. Constraints, workplane and units stay in the full source binding,
    while all original points (including unused ones) and curves enter the shared
    geometry record. Coincidence relations never supply geometry or shared IDs.
    """
    validate(sketch)
    return SectorGeometrySource(
        points=tuple(SectorPoint(p.id, p.u, p.v) for p in sketch.points),
        lines=tuple(SectorLine(line.id, line.start, line.end) for line in sketch.lines),
        arcs=tuple(
            SectorArc(arc.id, arc.center, arc.start, arc.end, arc.direction) for arc in sketch.arcs
        ),
        circles=tuple(
            SectorCircle(circle.id, circle.center, circle.radius) for circle in sketch.circles
        ),
    )


def _prerequisite_bytes(report: object) -> bytes:
    # Full coefficients, all support roots and isolating bounds, multiplicities,
    # independent finite memberships, identities and core outputs participate.
    # The distinct source namespace and absolute budget offsets do not.
    payload = tuple(
        getattr(report, name)
        for name in (
            "status",
            "stage",
            "code",
            "core_arcs",
            "arc",
            "form",
            "ray_dot",
            "gaps",
            "boundaries",
            "nominal_joins",
            "intended_ledger_count",
            "ledgers_complete",
        )
    )
    return _record_bytes(payload, extra_record_types=_EXTRA_RECORD_TYPES)


def classify_sector(sketch: Sketch, *, context: PrimitiveContext | None = None) -> SectorResult:
    """Classify one bound numeric Sketch using qualified and shared prerequisites.

    The existing incidence API requires height: its fixed 1 is solely an adapter
    prerequisite, never a requested extrusion height. extrusion_preflight is the
    separate nominal height check. There is one full shared classification; only
    the small root prerequisite is deliberately recomputed for the cross-check.
    """
    context = _context(context)
    start = context.operations
    report = incidence_preflight(sketch, 1, context=context)
    usage = ResourceUsage(start, context.operations, context.max_bits, context.max_operations, 0)
    if report.form == "chord":
        return SectorResult(
            "unsupported", "GRAPH", "unsupported_profile_form", report, None, (), (), (), usage
        )
    if report.status in ("unsupported", "numerical_ambiguity"):
        return SectorResult(
            report.status, report.stage, report.code, report, None, (), (), (), usage
        )
    source = sector_geometry_source(sketch)
    actual = classify_sector_geometry(source, context=context)
    usage = ResourceUsage(
        start,
        context.operations,
        context.max_bits,
        context.max_operations,
        actual.resources.refinements,
    )
    certificate = None
    status, stage, code = actual.status, actual.stage, actual.code
    if actual.certificate is not None:
        if _prerequisite_bytes(report) != _prerequisite_bytes(actual.incidence):
            status, stage, code = (
                "numerical_ambiguity",
                "PREREQUISITE_CROSSCHECK",
                "incidence_crosscheck_mismatch",
            )
        else:
            certificate = SectorCertificate(
                1,
                report.source_json,
                hashlib.sha256(report.source_json.encode("utf-8")).hexdigest(),
                report,
                actual.certificate,
                usage,
            )
            try:
                certificate_bytes(certificate)
            except SectorInputError as exc:
                certificate = None
                status, stage, code = "numerical_ambiguity", "CERTIFICATE", exc.code
    return SectorResult(
        status,
        stage,
        code,
        report,
        certificate,
        actual.assignments,
        actual.cells,
        actual.outer_proxies,
        usage,
    )


def _shift_certificate(certificate: SectorCertificate, offset: int) -> SectorCertificate:
    def report_shift(report):
        return replace(
            report,
            operations_start=report.operations_start + offset,
            operations_end=report.operations_end + offset,
        )

    def usage_shift(usage):
        return replace(
            usage,
            operations_start=usage.operations_start + offset,
            operations_end=usage.operations_end + offset,
        )

    return replace(
        certificate,
        incidence=report_shift(certificate.incidence),
        geometry=replace(
            certificate.geometry,
            incidence=report_shift(certificate.geometry.incidence),
            resources=usage_shift(certificate.geometry.resources),
        ),
        resources=usage_shift(certificate.resources),
    )


def check_sector_certificate(
    sketch: Sketch, certificate: SectorCertificate, *, context: PrimitiveContext | None = None
) -> CertificateCheck:
    """Recompute the entire bound certificate in the continuing aggregate context.

    Only absolute operation placement is normalized. Every exact operation delta,
    resource ceiling, refinement, full source byte, geometry digest and witness
    must match a fresh computation from the genuine Sketch. Bool/int encodings
    differ. Invalid or exhausted recomputation is nonpassing, never cached success.
    """
    context = _context(context)
    try:
        supplied = certificate_bytes(certificate)
        resources = certificate.resources
        if type(resources) is not ResourceUsage or any(
            type(value) is not int
            for value in (
                resources.operations_start,
                resources.operations_end,
                resources.max_bits,
                resources.max_operations,
                resources.refinements,
                resources.max_refinements,
                resources.max_certificate_bytes,
            )
        ):
            return CertificateCheck(False, "invalid_certificate_resources", None)
        if not (
            0
            <= resources.operations_start
            < resources.operations_end
            <= resources.max_operations
            <= MAX_OPERATIONS
            and 1 <= resources.max_bits <= MAX_INTEGER_BITS
            and 1 <= resources.refinements <= MAX_REFINEMENTS
            and resources.max_refinements == MAX_REFINEMENTS
            and resources.max_certificate_bytes == MAX_CERTIFICATE_BYTES
            and resources.max_bits == context.max_bits
            and resources.max_operations == context.max_operations
        ):
            return CertificateCheck(False, "invalid_certificate_resources", None)
        actual = classify_sector(sketch, context=context)
        if actual.certificate is None:
            return CertificateCheck(False, actual.code, actual)
        normalized = _shift_certificate(
            actual.certificate, resources.operations_start - actual.resources.operations_start
        )
        if certificate_bytes(normalized) != supplied:
            return CertificateCheck(False, "certificate_mismatch", actual)
        return CertificateCheck(True, "verified_sector_certificate", actual)
    except (SectorInputError, PrimitiveError, AttributeError, TypeError) as exc:
        return CertificateCheck(False, getattr(exc, "code", "invalid_certificate"), None)
