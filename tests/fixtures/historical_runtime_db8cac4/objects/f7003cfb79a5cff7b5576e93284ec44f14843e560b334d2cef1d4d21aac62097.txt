"""Pure advisory regularity controls; no native imports or native-success claim.

The fixture augments detached generated records locally. Metadata never supplies
an analytic support, a finite trace, a pcurve, a root, a cell or a mass witness.
"""

from __future__ import annotations

import copy
import importlib.abc
import math
import sys
from fractions import Fraction

import pytest
from test_arc_profile_native_generated_trace import (
    curve,
    generated_record,
    location,
    mutate,
    planar_branches,
)
from test_arc_profile_native_generated_trace import (
    names as old_mutations,
)

from mechanical_cad.arc_profile_native_evidence import (
    _generated_inventory,
    bounded_evidence_bytes,
    check_masses,
    mass_check_record,
    validate_generated_trace_observation,
)
from mechanical_cad.arc_profile_native_plan import (
    NativeEndpointObservation,
    NativePlane,
    NativePlanError,
    NativeRadialDirection,
    _continue_actual_support_for_vertices,
    _continue_vertex_representation,
    entry_context,
    plan_bytes,
    prepare_native_geometry,
    transform,
)
from mechanical_cad.arc_profile_primitives import PrimitiveContext, PrimitiveError
from mechanical_cad.arc_profile_sector_source import (
    SectorArc,
    SectorGeometrySource,
    SectorLine,
    SectorPoint,
)

CONTINUITIES = (
    "GeomAbs_C0",
    "GeomAbs_G1",
    "GeomAbs_C1",
    "GeomAbs_G2",
    "GeomAbs_C2",
    "GeomAbs_C3",
    "GeomAbs_CN",
)


class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"OCP", "OCC", "cadquery", "slvs", "bpy"}:
            raise AssertionError(f"native import forbidden: {fullname}")
        if fullname == "mechanical_cad.kernel_ocp":
            raise AssertionError("the native kernel must not be imported")


@pytest.fixture(autouse=True)
def no_native_imports():
    blocker = NoNative()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


def generated_schema(record):
    """Only generated entries gain these fields; source inventory is unchanged."""
    for edge in record["edges"]:
        for item in edge["representations"]:
            item.setdefault("is_regularity", item["is_closed_surface"])
            item.setdefault("regularity", None)
    return record


def fixture(*, kind="semicircle", present=True, value=6, reverse=False, branches=False, limit=None):
    y = {"semicircle": 0.0, "near_above": 2**-22, "near_below": -(2**-22)}[kind]
    source = SectorGeometrySource(
        (SectorPoint("c", 0.0, 0.0), SectorPoint("a", 5.0, 0.0), SectorPoint("b", -5.0, y)),
        (SectorLine("ra", "c", "a"), SectorLine("rb", "c", "b")),
        (SectorArc("arc", "c", "a", "b", "ccw"),),
    )
    c = entry_context(None if limit is None else PrimitiveContext(max_operations=limit))
    p = prepare_native_geometry(source, NativePlane(), context=c)
    directions = tuple(
        NativeRadialDirection(line.entity_id, transform(p.frame, line.direction))
        for line in p.lines
    )
    p, ticket = _continue_actual_support_for_vertices(p, directions, c)
    observations = tuple(
        NativeEndpointObservation(
            pid,
            parameter,
            transform(p.frame, (p.radius * math.cos(parameter), p.radius * math.sin(parameter))),
        )
        for pid, parameter in zip(("a", "b"), p.parameters, strict=True)
    )
    q = _continue_vertex_representation(p, observations, c, continuation=ticket)
    r = generated_record(p, q)
    if branches:
        planar_branches(p, q, r)
    generated_schema(r)
    if present:
        add_regularity(r, value=value, reverse=reverse)
    return p, q, r, c


def center_edge(r):
    return next(edge for edge in r["edges"] if edge["role"] == "vertical.c")


def add_regularity(r, *, value=6, reverse=False, edge=None):
    edge = center_edge(r) if edge is None else edge
    faces = [face for face in r["faces"] if face["surface_fields"]["kind"] == "Geom_Plane"]
    if reverse:
        faces.reverse()
    registry = {
        item["owner_roles"]: item["surface_index"]
        for item in edge["representations"]
        if item["surface_index"] is not None
    }
    slots = []
    for face in faces:
        roles = (face["role"],)
        if roles not in registry:
            registry[roles] = len(registry)
        slots.append(
            {
                "surface_index": registry[roles],
                "owner_roles": roles,
                "surface_fields": copy.deepcopy(face["surface_fields"]),
            }
        )
    item = {
        "index": len(edge["representations"]),
        "representation_type": "BRep_CurveOn2Surfaces",
        "is_curve3d": False,
        "is_on_surface": False,
        "is_closed_surface": False,
        "is_regularity": True,
        "regularity": {
            "surface1": slots[0],
            "surface2": slots[1],
            "location2": location(),
            "continuity_value": value,
            "continuity_name": CONTINUITIES[value],
            "continuity_type": {"module": "OCP.OCP.GeomAbs", "qualname": "GeomAbs_Shape"},
        },
        "surface_index": None,
        "surface_is_retained": False,
        "surface_fields": None,
        "location": location(),
        "range": (),
        "curve3d": None,
        "pcurves": (),
        "owner_roles": (),
    }
    edge["representations"] += (item,)
    return item


def metadata(r):
    return center_edge(r)["representations"][-1]


def check(p, q, r, c):
    return validate_generated_trace_observation(p, q, r, height=r["height"], context=c)


def geometric_result(result):
    return {key: value for key, value in result.items() if not key.startswith("operations_")}


@pytest.mark.parametrize("kind", ("semicircle", "near_above", "near_below"))
@pytest.mark.parametrize("value", range(7))
@pytest.mark.parametrize("reverse", (False, True))
@pytest.mark.parametrize("branches", (False, True))
def test_all_advisory_values_and_pair_orders_preserve_every_geometric_result(
    kind, value, reverse, branches
):
    p, q, r, c = fixture(kind=kind, present=False, branches=branches)
    before = plan_bytes(p)
    source, radius = p.source, p.final_cell_radius
    roots = (p.retained_root_count, p.accepted_support.retained_root_count)
    original = copy.deepcopy(r)
    plain = check(p, q, r, c)
    area = 25.0 * (p.parameters[1] - p.parameters[0]) / 2.0
    plain_mass = mass_check_record(check_masses(p, area, height=7.0, volume=area * 7.0, context=c))
    add_regularity(r, value=value, reverse=reverse)
    raw = copy.deepcopy(r)
    annotated = check(p, q, r, c)
    assert geometric_result(annotated) == geometric_result(plain)
    assert annotated["operations_end"] - annotated["operations_start"] == (
        plain["operations_end"] - plain["operations_start"] + 21
    )
    assert (
        mass_check_record(check_masses(p, area, height=7.0, volume=area * 7.0, context=c))
        == plain_mass
    )
    assert r == raw and plan_bytes(p) == before
    assert p.source is source and p.final_cell_radius is radius
    assert roots == (p.retained_root_count, p.accepted_support.retained_root_count)
    assert c.operations <= 200000
    assert annotated["operations_end"] - annotated["operations_start"] <= 32768
    assert len(annotated["inferred_planar_projections"]) == (0 if branches else 16)
    # Presence changes only the complete retained inventory, never source data.
    center_edge(r)["representations"] = center_edge(r)["representations"][:-1]
    assert r == original
    u, v = (line.direction for line in p.accepted_support.lines)
    exact_cross = Fraction(u[0]) * Fraction(v[1]) - Fraction(u[1]) * Fraction(v[0])
    assert (exact_cross == 0) == (kind == "semicircle")


@pytest.mark.parametrize("slot", ("surface1", "surface2"))
@pytest.mark.parametrize(
    "change",
    (
        "foreign",
        "cap",
        "cylinder",
        "multi",
        "duplicate_role",
        "duplicate_index",
        "index_skip",
        "index_bool",
        "kind",
        "fields",
        "null",
    ),
)
def test_actual_distinct_radial_owner_associations_are_required(slot, change):
    p, q, r, c = fixture()
    reg = metadata(r)["regularity"]
    owner = reg[slot]
    other = reg["surface2" if slot == "surface1" else "surface1"]
    if change == "foreign":
        owner["owner_roles"] = ()
    elif change == "cap":
        owner["owner_roles"] = ("retained_profile_plane",)
    elif change == "cylinder":
        face = next(
            face
            for face in r["faces"]
            if face["surface_fields"]["kind"] == "Geom_CylindricalSurface"
        )
        owner["owner_roles"] = (face["role"],)
        owner["surface_fields"] = copy.deepcopy(face["surface_fields"])
    elif change == "multi":
        owner["owner_roles"] += other["owner_roles"]
    elif change == "duplicate_role":
        owner["owner_roles"] = other["owner_roles"]
    elif change == "duplicate_index":
        owner["surface_index"] = other["surface_index"]
    elif change == "index_skip":
        owner["surface_index"] = 7
    elif change == "index_bool":
        owner["surface_index"] = False
    elif change == "kind":
        owner["surface_fields"]["kind"] = "Geom_BSplineSurface"
    elif change == "fields":
        owner["surface_fields"]["origin"] = (0.0, 0.0, 1.0)
    else:
        reg[slot] = None
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


@pytest.mark.parametrize("after", (False, True))
def test_same_owner_role_cannot_have_inconsistent_native_handle_indices(after):
    p, q, r, c = fixture(branches=True)
    e = center_edge(r)
    reg = metadata(r)
    owner = reg["regularity"]["surface1"]
    owner["surface_index"] = 2
    if not after:
        e["representations"] = (e["representations"][0], reg, *e["representations"][1:-1])
        # Metadata first owns indices 0/1, then a geometric claim for the same
        # actual side under a distinct index is inconsistent, not a new owner.
        reg["regularity"]["surface1"]["surface_index"] = 0
        reg["regularity"]["surface2"]["surface_index"] = 1
        e["representations"][2]["surface_index"] = 2
    for index, entry in enumerate(e["representations"]):
        entry["index"] = index
    with pytest.raises(NativePlanError, match="native_generated_owner_changed"):
        check(p, q, r, c)


@pytest.mark.parametrize("where", ("first", "second", "edge", "face_surface", "face_shape"))
@pytest.mark.parametrize("change", ("translation", "rotation", "shear", "identity_flag"))
def test_identity_predicates_full_matrices_and_paired_placements_all_remain_required(where, change):
    p, q, r, c = fixture()
    reg = metadata(r)
    face = next(
        face
        for face in r["faces"]
        if face["role"] == reg["regularity"]["surface1"]["owner_roles"][0]
    )
    loc = {
        "first": reg["location"],
        "second": reg["regularity"]["location2"],
        "edge": center_edge(r)["location"],
        "face_surface": face["surface_location"],
        "face_shape": face["shape_location"],
    }[where]
    if change == "identity_flag":
        loc["identity"] = False
    else:
        rows = [list(row) for row in loc["matrix"]]
        rows[0][3 if change == "translation" else 0 if change == "rotation" else 1] = 0.25
        loc["matrix"] = tuple(tuple(row) for row in rows)
        if change == "translation":
            loc["identity"] = False
    with pytest.raises(NativePlanError, match="native_generated_location_changed"):
        check(p, q, r, c)


@pytest.mark.parametrize("value", (True, False, -1, 7, 2.0, "2", None))
def test_continuity_requires_exact_builtin_finite_enum_value(value):
    p, q, r, c = fixture()
    metadata(r)["regularity"]["continuity_value"] = value
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


@pytest.mark.parametrize(
    "field,value",
    (
        ("continuity_name", "GeomAbs_C0"),
        ("continuity_name", "CN"),
        ("continuity_name", "x" * 129),
        ("continuity_name", 6),
        ("continuity_type", None),
        ("continuity_type", {}),
        ("continuity_type", {"module": "OCP", "qualname": "GeomAbs_Shape", "extra": "bad"}),
        ("continuity_type", {"module": "", "qualname": "GeomAbs_Shape"}),
        ("continuity_type", {"module": "OCP", "qualname": ""}),
        ("continuity_type", {"module": "x" * 129, "qualname": "GeomAbs_Shape"}),
        ("continuity_type", {"module": "OCP", "qualname": "x" * 129}),
        ("continuity_type", {"module": 5, "qualname": "GeomAbs_Shape"}),
    ),
)
def test_continuity_name_and_observed_type_metadata_are_strict(field, value):
    p, q, r, c = fixture()
    metadata(r)["regularity"][field] = value
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


def test_observed_type_text_is_bounded_data_and_does_not_forge_native_enum_type():
    p, q, r, c = fixture()
    metadata(r)["regularity"]["continuity_type"] = {"module": "m" * 128, "qualname": "q" * 128}
    check(p, q, r, c)


@pytest.mark.parametrize(
    "field",
    ("surface1", "surface2", "location2", "continuity_value", "continuity_name", "continuity_type"),
)
@pytest.mark.parametrize("change", ("missing", "extra"))
def test_regularity_record_has_exact_keys(field, change):
    p, q, r, c = fixture()
    reg = metadata(r)["regularity"]
    if change == "missing":
        del reg[field]
    else:
        reg[field + "_extra"] = reg[field]
    with pytest.raises(NativePlanError, match="native_evidence_incomplete"):
        check(p, q, r, c)


@pytest.mark.parametrize(
    "field,value",
    (
        ("representation_type", "BRep_CurveOnSurface"),
        ("representation_type", "BRep_CurveOnClosedSurface"),
        ("representation_type", "ForeignRegularity"),
        ("is_regularity", False),
        ("is_regularity", 1),
        ("is_curve3d", True),
        ("is_on_surface", True),
        ("is_closed_surface", True),
        ("range", (0.0, 7.0)),
        ("range", []),
        ("range", None),
        ("pcurves", ({},)),
        ("pcurves", []),
        ("curve3d", {}),
        ("owner_roles", ("side.line.ra",)),
        ("surface_index", 0),
        ("surface_fields", {}),
        ("surface_is_retained", True),
        ("regularity", None),
    ),
)
def test_metadata_variant_cannot_claim_geometric_fields_or_other_flags(field, value):
    p, q, r, c = fixture()
    metadata(r)[field] = value
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


@pytest.mark.parametrize("target", ("is_regularity", "regularity"))
@pytest.mark.parametrize("kind", ("curve3d", "pcurve"))
def test_plain_geometry_requires_new_false_null_fields(target, kind):
    p, q, r, c = fixture()
    item = r["edges"][0]["representations"][0 if kind == "curve3d" else 1]
    item[target] = True if target == "is_regularity" else metadata(r)["regularity"]
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


@pytest.mark.parametrize(
    "change", ("missing_is_regularity", "missing_regularity", "extra", "duplicate_index")
)
def test_every_generated_entry_has_exact_new_schema(change):
    p, q, r, c = fixture()
    item = metadata(r)
    if change.startswith("missing_"):
        del item[change.removeprefix("missing_")]
    elif change == "extra":
        item["extra"] = None
    else:
        item["index"] = 0
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


@pytest.mark.parametrize(
    "where", ("record", "slot", "roles", "name", "value", "type", "module", "matrix")
)
def test_callback_capable_metadata_never_runs_user_methods(where):
    class BadDict(dict):
        def __eq__(self, other):
            raise AssertionError("callback")

    class BadTuple(tuple):
        def __iter__(self):
            raise AssertionError("callback")

    class BadStr(str):
        def __eq__(self, other):
            raise AssertionError("callback")

    class BadInt(int):
        def __int__(self):
            raise AssertionError("callback")

    p, q, r, c = fixture()
    item = metadata(r)
    reg = item["regularity"]
    if where == "record":
        item["regularity"] = BadDict(reg)
    elif where == "slot":
        reg["surface1"] = BadDict(reg["surface1"])
    elif where == "roles":
        reg["surface1"]["owner_roles"] = BadTuple(reg["surface1"]["owner_roles"])
    elif where == "name":
        reg["continuity_name"] = BadStr(reg["continuity_name"])
    elif where == "value":
        reg["continuity_value"] = BadInt(6)
    elif where == "type":
        reg["continuity_type"] = BadDict(reg["continuity_type"])
    elif where == "module":
        reg["continuity_type"]["module"] = BadStr("OCP")
    else:
        item["location"]["matrix"] = BadTuple(item["location"]["matrix"])
    with pytest.raises(NativePlanError, match="invalid_native_evidence"):
        check(p, q, r, c)


@pytest.mark.parametrize("target", ("base.line.ra", "top.line.rb", "vertical.a", "vertical.b"))
def test_regularity_is_allowed_only_on_actual_source_center_vertical_edge(target):
    p, q, r, c = fixture(present=False)
    add_regularity(r, edge=next(edge for edge in r["edges"] if edge["role"] == target))
    with pytest.raises(NativePlanError, match="native_generated_regularity_edge_changed"):
        check(p, q, r, c)


@pytest.mark.parametrize(
    "change", ("wrong_center", "endpoint", "split", "second_same", "second_other")
)
def test_center_identity_topology_and_one_record_graph_limit_remain_strict(change):
    p, q, r, c = fixture()
    edge = center_edge(r)
    if change == "wrong_center":
        edge["role"] = "vertical.foreign"
    elif change == "endpoint":
        edge["endpoint_ids"] = ("base.a", "top.a")
    elif change == "split":
        r["edges"] += (copy.deepcopy(edge),)
    elif change == "second_same":
        extra = copy.deepcopy(metadata(r))
        extra["index"] = 2
        edge["representations"] += (extra,)
    else:
        other = next(edge for edge in r["edges"] if edge["role"] == "vertical.a")
        add_regularity(r, edge=other)
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


def foreign_entry(index, surface_index, ran, *, closed=False):
    return {
        "index": index,
        "representation_type": "BRep_CurveOnClosedSurface" if closed else "BRep_CurveOnSurface",
        "is_curve3d": False,
        "is_on_surface": True,
        "is_closed_surface": closed,
        "is_regularity": closed,
        "regularity": None,
        "surface_index": surface_index,
        "surface_is_retained": False,
        "surface_fields": {
            "kind": "Geom_Plane",
            "origin": (0.0, 0.0, 0.0),
            "u": (1.0, 0.0, 0.0),
            "v": (0.0, 1.0, 0.0),
            "normal": (0.0, 0.0, 1.0),
            "radius": None,
        },
        "location": location(),
        "range": ran,
        "curve3d": None,
        "pcurves": tuple(
            curve("line", (0.0, 0.0), (1.0, 0.0), ran) for _ in range(2 if closed else 1)
        ),
        "owner_roles": (),
    }


@pytest.mark.parametrize("closed", (False, True))
def test_eight_entries_and_eight_handles_including_both_metadata_owners_are_allowed(closed):
    p, q, r, c = fixture(present=False)
    edge = center_edge(r)
    edge["representations"] += tuple(
        foreign_entry(k + 1, k, edge["range"], closed=closed) for k in range(6)
    )
    item = add_regularity(r)
    # The foreign owners have no semantic labels; retain their six distinct
    # observed handle indices before registering the two actual radial planes.
    item["regularity"]["surface1"]["surface_index"] = 6
    item["regularity"]["surface2"]["surface_index"] = 7
    before = copy.deepcopy(r)
    check(p, q, r, c)
    assert r == before
    assert len(edge["representations"]) == 8


@pytest.mark.parametrize("which", ("entry", "handle_first", "handle_second"))
def test_ninth_entry_or_either_ninth_handle_rejects(which):
    p, q, r, c = fixture(present=False)
    edge = center_edge(r)
    if which == "entry":
        edge["representations"] += tuple(foreign_entry(k + 1, k, edge["range"]) for k in range(7))
        add_regularity(r)
    else:
        metadata_item = add_regularity(r)
        metadata_item["regularity"]["surface1" if which == "handle_first" else "surface2"][
            "surface_index"
        ] = 8
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


def test_closed_surface_stays_geometric_two_branch_data_even_with_regularity_flag():
    p, q, r, c = fixture()
    edge = center_edge(r)
    seam = foreign_entry(2, 2, edge["range"], closed=True)
    edge["representations"] += (seam,)
    _, geometric, advisory = _generated_inventory(
        c, edge, ("side.arc.arc", "side.line.ra", "side.line.rb", "retained_profile_plane")
    )
    assert len(advisory) == 1 and len(geometric) == 2
    assert geometric[-1][0] is seam and len(seam["pcurves"]) == 2
    check(p, q, r, c)
    seam["pcurves"] = seam["pcurves"][:1]
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


@pytest.mark.parametrize(
    "change",
    (
        "missing_3d",
        "duplicate_3d",
        "missing_cylinder_pcurve",
        "metadata_as_pcurve",
        "closed_as_metadata",
    ),
)
def test_metadata_cannot_satisfy_or_hide_any_geometric_inventory_obligation(change):
    p, q, r, c = fixture()
    edge = center_edge(r)
    if change == "missing_3d":
        edge["representations"] = edge["representations"][1:]
        edge["representations"][0]["index"] = 0
    elif change == "duplicate_3d":
        extra = copy.deepcopy(edge["representations"][0])
        extra["index"] = 2
        edge["representations"] += (extra,)
    elif change == "missing_cylinder_pcurve":
        r["edges"][0]["representations"] = r["edges"][0]["representations"][:1]
    elif change == "metadata_as_pcurve":
        metadata(r)["owner_roles"] = ("side.arc.arc",)
    else:
        seam = foreign_entry(2, 2, edge["range"], closed=True)
        seam["regularity"] = copy.deepcopy(metadata(r)["regularity"])
        edge["representations"] += (seam,)
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


@pytest.mark.parametrize("name", old_mutations)
def test_fake_cn_cannot_rescue_any_original_whole_trace_mutation(name):
    p, q, r, c = fixture()
    mutate(name, r)
    # The old seam adversary was authored before IsRegularity became observed.
    # Supply the correct new flag so the original geometric gate still rejects.
    if name == "seam":
        r["edges"][0]["representations"][1]["is_regularity"] = True
    with pytest.raises(NativePlanError):
        check(p, q, r, c)


@pytest.mark.parametrize("which", ("area", "volume"))
def test_fake_cn_cannot_rescue_original_mass_rejection(which):
    p, q, r, c = fixture()
    check(p, q, r, c)
    area = math.pi * 25.0 / 2.0
    with pytest.raises(NativePlanError, match="native_(area|volume)_r0_failure"):
        check_masses(
            p,
            area + (1.0 if which == "area" else 0.0),
            height=7.0,
            volume=area * 7.0 + (1.0 if which == "volume" else 0.0),
            context=c,
        )


@pytest.mark.parametrize("present", (False, True))
def test_exact_continuing_operation_limit_and_one_short_fail_closed(present):
    p, q, r, c = fixture(present=present)
    check(p, q, r, c)
    limit = c.operations
    p, q, r, c = fixture(present=present, limit=limit)
    check(p, q, r, c)
    assert c.operations == limit
    p, q, r, c = fixture(present=present, limit=limit - 1)
    with pytest.raises(PrimitiveError, match="operation_limit"):
        check(p, q, r, c)
    assert c.operations == limit - 1


def test_complete_evidence_byte_boundary_counts_unshortened_regularity_data():
    _, _, r, c = fixture()
    observation = {"operation": "curve_profile", "operations_start": c.operations, "events": [r]}
    raw = bounded_evidence_bytes(observation)
    padded = {**observation, "failure": ""}
    padded["failure"] = "x" * (1048576 - len(bounded_evidence_bytes(padded)))
    assert len(bounded_evidence_bytes(padded)) == 1048576
    padded["failure"] += "x"
    with pytest.raises(NativePlanError, match="native_evidence_limit"):
        bounded_evidence_bytes(padded)
    assert b'"continuity_name":"GeomAbs_CN"' in raw
    assert b'"surface2"' in raw


@pytest.mark.parametrize("slot", ("surface1", "surface2"))
@pytest.mark.parametrize("field", ("surface_index", "owner_roles", "surface_fields"))
@pytest.mark.parametrize("change", ("missing", "extra"))
def test_owner_slots_retain_exact_field_grammar(slot, field, change):
    p, q, r, c = fixture()
    record = metadata(r)["regularity"][slot]
    if change == "missing":
        del record[field]
    else:
        record[field + "_extra"] = record[field]
    with pytest.raises(NativePlanError, match="native_evidence_incomplete"):
        check(p, q, r, c)


def test_ninth_handle_rejects_before_missing_geometric_support_can_mask_it():
    p, q, r, c = fixture(present=False)
    edge = center_edge(r)
    edge["representations"] = tuple(foreign_entry(k, k, edge["range"]) for k in range(7))
    reg = add_regularity(r)["regularity"]
    reg["surface1"]["surface_index"] = 7
    reg["surface2"]["surface_index"] = 8
    with pytest.raises(NativePlanError, match="invalid_native_representation"):
        check(p, q, r, c)


def test_metadata_locations_exchange_is_same_observation_but_owner_only_exchange_rejects():
    p, q, r, c = fixture()
    item = metadata(r)
    reg = item["regularity"]
    item["location"], reg["location2"] = reg["location2"], item["location"]
    check(p, q, r, c)
    # Swap labels without their exact observed fields; this changes association.
    a, b = reg["surface1"], reg["surface2"]
    a["owner_roles"], b["owner_roles"] = b["owner_roles"], a["owner_roles"]
    with pytest.raises(NativePlanError, match="native_generated_owner_changed"):
        check(p, q, r, c)


@pytest.mark.parametrize("over", (0, 1))
def test_generated_stage_limit_still_checks_the_late_metadata_work(monkeypatch, over):
    import mechanical_cad.arc_profile_native_evidence as evidence

    p, q, r, c = fixture()
    out = check(p, q, r, c)
    cost = out["operations_end"] - out["operations_start"]
    original = evidence._generated_regularity_placement

    def charged_placement(*args):
        original(*args)
        for _ in range(32768 - cost + over):
            args[0]._tick()

    monkeypatch.setattr(evidence, "_generated_regularity_placement", charged_placement)
    p, q, r, c = fixture()
    start = c.operations
    if over:
        with pytest.raises(NativePlanError, match="native_generated_trace_operation_limit"):
            check(p, q, r, c)
    else:
        check(p, q, r, c)
    assert c.operations - start == 32768 + over


def test_complete_metadata_counts_toward_exact_node_and_event_limits():
    _, _, r, c = fixture()
    observation = {"operation": "curve_profile", "operations_start": c.operations, "events": [r]}

    def nodes(value):
        if type(value) is dict:
            return 1 + sum(nodes(child) for child in value.values())
        if type(value) in (tuple, list):
            return 1 + sum(nodes(child) for child in value)
        return 1

    padded = {**observation, "failure": []}
    remaining = 8192 - nodes(padded)
    while remaining:
        count = min(256, remaining - 1)
        padded["failure"].append([None] * count)
        remaining -= count + 1
    assert nodes(padded) == 8192
    bounded_evidence_bytes(padded)
    # An empty extra group adds exactly its own node.
    padded["failure"].append([])
    assert nodes(padded) == 8193
    with pytest.raises(NativePlanError, match="native_evidence_limit"):
        bounded_evidence_bytes(padded)
    events = {**observation, "events": [r, *([None] * 63)]}
    bounded_evidence_bytes(events)
    events["events"].append(None)
    with pytest.raises(NativePlanError, match="native_evidence_limit"):
        bounded_evidence_bytes(events)
