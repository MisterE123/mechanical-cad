"""Authored selection requirements and real native-free picker behavior."""

import copy
import importlib
import subprocess
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_constraint_selection_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
c = importlib.import_module(PACKAGE + ".constraint_selection")
g = importlib.import_module(PACKAGE + ".general_view_geometry")
commands = importlib.import_module(PACKAGE + ".general_sketch_commands")


def sketch():
    return {
        "schema_version": 2,
        "id": "sketch",
        "units": "mm",
        "plane": {"id": "plane", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [
            {"id": "a", "u": 0, "v": 0},
            {"id": "b", "u": 20, "v": 0},
            {"id": "c", "u": 40, "v": 30},
            {"id": "d", "u": 50, "v": 30},
        ],
        "lines": [{"id": "line", "start": "a", "end": "b"}],
        "circles": [{"id": "circle", "center": "c", "radius": 5}],
        "constraints": [],
    }


def relations():
    return [
        {"id": "horizontal", "kind": "horizontal", "refs": ["line"]},
        {"id": "vertical", "kind": "vertical", "refs": ["line"]},
        {"id": "join", "kind": "coincident", "refs": ["c", "a"]},
        {"id": "anchor", "kind": "fixed", "refs": ["a"], "target": [1, 2.5]},
        {"id": "length", "kind": "distance", "refs": ["b", "a"], "value": " span + 0 "},
        {"id": "radius", "kind": "radius", "refs": ["circle"], "value": 5},
    ]


def selected(*pairs):
    return [{"kind": kind, "id": identifier} for kind, identifier in pairs]


def contract(source, *pairs):
    return c.selection_contract(source, selected(*pairs))


def test_normalization_retains_exact_order_and_is_detached_and_immutable():
    source, selection = sketch(), selected(("point", "b"), ("point", "a"))
    before = copy.deepcopy((source, selection))
    result = c.normalize_selection(source, selection)
    assert result == (c.EntitySelection("point", "b"), c.EntitySelection("point", "a"))
    assert (source, selection) == before
    selection[0]["id"] = "c"
    source["points"][1]["id"] = "renamed"
    assert result[0].id == "b"
    with pytest.raises(FrozenInstanceError):
        result[0].id = "c"


@pytest.mark.parametrize(
    "selection",
    [
        None,
        "point:a",
        {"kind": "point", "id": "a"},
        [("point", "a")],
        [{"kind": "point", "id": "a", "index": 0}],
        [{"kind": "point"}],
        selected(("unknown", "a")),
        selected(("point", "missing")),
        selected(("point", "line")),
        selected(("line", "a")),
        selected(("constraint", "line")),
        selected(("point", "a"), ("point", "a")),
        selected(("point", True)),
        selected(("point", " a")),
        selected(("point", "a" * 129)),
        [{"kind": [], "id": "a"}],
    ],
)
def test_unknown_changed_duplicate_and_malformed_selection_fail_unchanged(selection):
    source = sketch()
    before = copy.deepcopy((source, selection))
    with pytest.raises(ValueError):
        c.selection_contract(source, selection)
    assert (source, selection) == before


def test_selection_and_source_caps_are_checked_before_returning_partial_results():
    source = sketch()
    source["points"].extend({"id": f"p{i}", "u": i, "v": 1} for i in range(33))
    selection = selected(*(("point", f"p{i}") for i in range(c.MAX_SELECTION)))
    result = c.selection_contract(source, selection)
    assert len(result.selection) == 32
    assert all(item.state == "unavailable" for item in result.actions)
    with pytest.raises(ValueError, match="limit"):
        c.selection_contract(source, selection + selected(("point", "p32")))
    source["constraints"] = [
        {"id": f"h{i}", "kind": "horizontal", "refs": ["line"]} for i in range(513)
    ]
    with pytest.raises(ValueError, match="limit"):
        c.relation_descriptors(source)
    source = sketch()
    source["points"].extend({"id": f"p{i}", "u": 0, "v": 0} for i in range(253))
    with pytest.raises(ValueError, match="limit"):
        c.selection_contract(source, [])
    source = sketch()
    source["circles"] *= 257
    with pytest.raises(ValueError, match="limit"):
        c.relation_descriptors(source)


@pytest.mark.parametrize("kind", ["tangent", "equal", None, True, []])
def test_unknown_relation_kinds_are_not_silently_omitted(kind):
    source = sketch()
    source["constraints"] = [{"id": "unknown", "kind": kind, "refs": ["line"]}]
    with pytest.raises(ValueError):
        c.relation_descriptors(source)


def test_all_relation_descriptors_preserve_exact_sources_and_match_reducer_signatures():
    source = sketch()
    source["constraints"] = relations()
    before = copy.deepcopy(source)
    result = c.relation_descriptors(source)
    assert [item.id for item in result] == sorted(item["id"] for item in relations())
    by_id = {item.id: item for item in result}
    assert by_id["length"].refs == ("b", "a")
    assert by_id["length"].source_value == " span + 0 "
    assert type(by_id["radius"].source_value) is int
    assert by_id["anchor"].fixed_target == (1, 2.5)
    assert type(by_id["anchor"].fixed_target[0]) is int
    for relation in relations():
        assert by_id[relation["id"]].signature == commands._relation_signature(relation)
    assert source == before
    source["constraints"][2]["refs"].reverse()
    source["constraints"][3]["target"][0] = 999
    source["constraints"][4]["value"] = "different"
    assert by_id["join"].refs == ("c", "a")
    assert by_id["anchor"].fixed_target == (1, 2.5)
    assert by_id["length"].source_value == " span + 0 "
    with pytest.raises(FrozenInstanceError):
        by_id["length"].source_value = 8


def test_duplicate_signatures_keep_symmetric_refs_numeric_equivalence_and_exact_strings():
    source = sketch()
    source["constraints"] = relations()
    original = {item.id: item for item in c.relation_descriptors(source)}
    for relation in source["constraints"]:
        relation["refs"].reverse()
    source["constraints"][-1]["value"] = 5.0
    reversed_values = {item.id: item for item in c.relation_descriptors(source)}
    assert {key: item.signature for key, item in original.items()} == {
        key: item.signature for key, item in reversed_values.items()
    }
    source["constraints"][-2]["value"] = "span"
    source["constraints"][3]["target"][0] += 1e-12
    changed = {item.id: item for item in c.relation_descriptors(source)}
    assert changed["length"].signature != original["length"].signature
    assert changed["anchor"].signature != original["anchor"].signature


def test_horizontal_vertical_require_one_line_and_surface_exact_existing_ids():
    source = sketch()
    result = contract(source, ("line", "line"))
    assert result.action("horizontal").state == result.action("vertical").state == "eligible"
    assert result.action("horizontal").refs == ("line",)
    source["constraints"] = relations()[:1]
    result = contract(source, ("line", "line"))
    assert result.action("horizontal").state == "existing"
    assert result.action("horizontal").relation_ids == ("horizontal",)
    assert result.action("vertical").state == "eligible"
    for selection in [[], selected(("point", "a")), selected(("line", "line"), ("point", "a"))]:
        result = c.selection_contract(source, selection)
        assert result.action("horizontal").state == result.action("vertical").state == "unavailable"


def test_fix_here_never_uses_authored_positions_and_origin_has_separate_disclosure():
    source = sketch()
    source["points"][0].update(u=1e6, v=-1e6)
    result = contract(source, ("point", "a"))
    here, origin = result.action("fix_here"), result.action("fix_origin")
    assert here.state == origin.state == "eligible"
    assert here.target is None and here.requirements == ("current_successful_solution",)
    assert origin.target == (0, 0) and origin.requirements == ("origin_movement_disclosure",)
    source["points"][0].update(u=0.012345678901234, v=9)
    assert contract(source, ("point", "a")) == result
    with pytest.raises(TypeError):
        c.selection_contract(source, selected(("point", "a")), current_solution={"a": (0, 0)})
    with pytest.raises(ValueError):
        c.selection_contract(g.build_geometry(source, source="authored"), [])


def test_already_fixed_point_exposes_all_exact_fixed_ids_and_never_proposes_a_new_target():
    source = sketch()
    source["constraints"] = [relations()[3]]
    source["constraints"].append(
        {"id": "second_anchor", "kind": "fixed", "refs": ["a"], "target": [1 + 1e-12, 2.5]}
    )
    result = contract(source, ("point", "a"))
    for name in ("fix_here", "fix_origin"):
        action = result.action(name)
        assert action.state == "existing"
        assert action.relation_ids == ("anchor", "second_anchor")
        assert action.target is None
        assert action.requirements == ("explicit_fixed_relation_selection",)
    assert result.relations[0].fixed_target != result.relations[1].fixed_target
    assert contract(source, ("point", "b")).action("fix_here").state == "eligible"


def test_inspection_is_one_hop_authored_incidence_and_exact_constraint_selection():
    source = sketch()
    source["constraints"] = relations()
    assert {item.id for item in contract(source, ("point", "a")).relations} == {
        "anchor",
        "horizontal",
        "vertical",
        "join",
        "length",
    }
    assert {item.id for item in contract(source, ("line", "line")).relations} == {
        "anchor",
        "horizontal",
        "vertical",
        "join",
        "length",
    }
    assert {item.id for item in contract(source, ("circle", "circle")).relations} == {
        "join",
        "radius",
    }
    assert {item.id for item in contract(source, ("point", "c")).relations} == {"join", "radius"}
    for relation in relations():
        result = contract(source, ("constraint", relation["id"]))
        assert tuple(item.id for item in result.relations) == (relation["id"],)
        assert result.action("inspect").state == "eligible"
        remove = result.action("remove_relation")
        assert remove.state == "eligible" and remove.relation_ids == (relation["id"],)
        assert remove.requirements == (
            "current_successful_solution",
            "relation_only_delete_preview",
        )
    assert contract(source, ("point", "a")).action("remove_relation").state == "unavailable"
    multi = contract(source, ("constraint", "anchor"), ("constraint", "horizontal"))
    assert multi.relations == ()
    assert all(item.state == "unavailable" for item in multi.actions)


def test_contract_is_immutable_detached_and_unknown_actions_fail():
    source = sketch()
    source["constraints"] = relations()
    result = contract(source, ("constraint", "anchor"))
    source["constraints"][3]["target"][1] = 123
    assert result.relations[0].fixed_target == (1, 2.5)
    with pytest.raises(FrozenInstanceError):
        result.actions = ()
    with pytest.raises(FrozenInstanceError):
        result.action("remove_relation").state = "enabled"
    for name in ("recover_remove_relation", None, [], "finish"):
        with pytest.raises(ValueError):
            result.action(name)


@pytest.mark.parametrize("scale", [1, 10, 1000])
def test_actual_generic_endpoint_tie_and_explicit_point_route(scale):
    geometry = g.build_geometry(sketch(), source="authored")

    def project(world):
        return world[0] * scale, world[1] * scale

    generic = g.pick_geometry(geometry, (0, 0), project, kinds=c.pick_kinds())
    assert generic.status == "ambiguous" and generic.unique is None
    assert {(item.kind, item.identifier) for item in generic.nearest} == {
        ("point", "a"),
        ("line", "line"),
    }
    point = g.pick_geometry(geometry, (0, 0), project, kinds=c.pick_kinds("point"))
    assert point.status == "unique" and point.unique.identifier == "a"
    assert {item.kind for item in point.candidates} == {"point"}


def test_point_filter_does_not_resolve_distinct_overlapping_ids_or_incomplete_picks():
    source = sketch()
    source["points"].append({"id": "overlap", "u": 0, "v": 0})
    geometry = g.build_geometry(source, source="authored")
    result = g.pick_geometry(geometry, (0, 0), lambda p: p[:2], kinds=c.pick_kinds("point"))
    assert result.status == "ambiguous" and result.unique is None
    assert [item.identifier for item in result.nearest] == ["a", "overlap"]
    incomplete = g.pick_geometry(
        geometry, (0, 0), lambda p: p[:2], kinds=c.pick_kinds("point"), max_project_calls=1
    )
    assert incomplete.status == "incomplete" and incomplete.unique is None


def test_generic_picker_keeps_actual_nearest_line_and_filter_is_explicit():
    geometry = g.build_geometry(sketch(), source="authored")
    generic = g.pick_geometry(geometry, (0.5, 0), lambda p: p[:2], kinds=c.pick_kinds())
    assert generic.unique.kind == "line" and generic.unique.identifier == "line"
    assert any(item.kind == "point" for item in generic.candidates)
    point = g.pick_geometry(geometry, (0.5, 0), lambda p: p[:2], kinds=c.pick_kinds("point"))
    assert point.unique.identifier == "a"
    assert c.pick_kinds() == ("point", "line", "circle", "arc")
    for mode in ("nearest_point", "line", "Point", True, None, []):
        with pytest.raises(ValueError):
            c.pick_kinds(mode)


def test_coincident_is_eligible_without_inventing_identity_from_overlapping_seeds():
    source = sketch()
    source["points"][2].update(u=0, v=0)
    preflight = c.coincident_preflight(source, ["a", "c"])
    assert not preflight.already_connected
    assert preflight.existing_relation_ids == preflight.collapsed_line_ids == ()
    action = contract(source, ("point", "a"), ("point", "c")).action("coincident")
    assert action.state == "eligible" and action.refs == ("a", "c")
    assert action.requirements == (
        "explicit_two_point_selection",
        "native_solve_after_edit",
    )


def test_direct_and_transitive_coincidence_cannot_collapse_a_line():
    source = sketch()
    before = copy.deepcopy(source)
    direct = c.coincident_preflight(source, ("a", "b"))
    assert direct.collapsed_line_ids == ("line",)
    assert (
        contract(source, ("point", "a"), ("point", "b")).action("coincident").state == "unavailable"
    )
    assert source == before
    source["constraints"] = [
        {"id": "ac", "kind": "coincident", "refs": ["a", "c"]},
        {"id": "cd", "kind": "coincident", "refs": ["c", "d"]},
    ]
    before = copy.deepcopy(source)
    transitive = c.coincident_preflight(source, ("d", "b"))
    assert not transitive.already_connected and transitive.collapsed_line_ids == ("line",)
    assert source == before
    connected = c.coincident_preflight(source, ("a", "d"))
    assert connected.already_connected and connected.existing_relation_ids == ()
    assert (
        contract(source, ("point", "a"), ("point", "d")).action("coincident").state == "unavailable"
    )


def test_coincident_exact_duplicates_retain_ids_even_when_reversed_or_authored_invalid():
    source = sketch()
    source["constraints"] = [{"id": "join", "kind": "coincident", "refs": ["a", "b"]}]
    preflight = c.coincident_preflight(source, ["b", "a"])
    assert preflight.collapsed_line_ids == ("line",)
    assert preflight.already_connected and preflight.existing_relation_ids == ("join",)
    action = contract(source, ("point", "b"), ("point", "a")).action("coincident")
    assert action.state == "existing" and action.relation_ids == ("join",)
    assert action.refs == ("b", "a")
    prepared = commands.prepare_command(
        source, commands.AddRelation("coincident", ("b", "a")), 0, {"join"}, 1
    )
    assert prepared.record is None and prepared.constraint_id == "join"


@pytest.mark.parametrize(
    "refs", [[], ["a"], ["a", "a"], ["a", "line"], ["a", "missing"], "ab", [[], "b"]]
)
def test_coincident_preflight_requires_exactly_two_available_distinct_points(refs):
    with pytest.raises(ValueError):
        c.coincident_preflight(sketch(), refs)


def test_schema_one_is_supported_without_migrating_it_or_creating_persisted_state():
    source = sketch()
    source["schema_version"] = 1
    del source["circles"]
    before = copy.deepcopy(source)
    assert contract(source, ("point", "a")).action("fix_origin").target == (0, 0)
    assert source == before


def test_fresh_import_is_a_leaf_without_core_native_owner_renderer_or_command_imports():
    script = f"""
import importlib, importlib.abc, sys, types
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'mechanical_cad', 'bpy', 'mathutils', 'slvs', 'OCP'}}:
            raise AssertionError('Forbidden native/core import: ' + fullname)
        if fullname.startswith('isolated.') and fullname.rsplit('.', 1)[1] not in {{
            'constraint_selection', 'sketch_bridge', 'sketch_relations', 'profile_geometry_checks'
        }}:
            raise AssertionError('Forbidden non-leaf import: ' + fullname)
sys.meta_path.insert(0, Block())
package = types.ModuleType('isolated')
package.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules['isolated'] = package
module = importlib.import_module('isolated.constraint_selection')
result = module.selection_contract({sketch()!r}, [{{'kind': 'point', 'id': 'a'}}])
assert result.action('fix_here').target is None
print('CONSTRAINT_SELECTION_LEAF_OK')
"""
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    assert "CONSTRAINT_SELECTION_LEAF_OK" in run.stdout


def arc_sketch():
    source = sketch()
    source["schema_version"] = 3
    source["arcs"] = [{"id": "arc", "center": "a", "start": "b", "end": "c", "direction": "ccw"}]
    source["constraints"] = relations() + [
        {"id": "arc_radius", "kind": "radius", "refs": ["arc"], "value": " radius + 0 "},
        {"id": "remote", "kind": "fixed", "refs": ["d"], "target": [50, 30]},
    ]
    return source


def test_arc_selection_and_one_hop_center_start_end_relations_preserve_authored_source():
    source = arc_sketch()
    before = copy.deepcopy(source)
    result = contract(source, ("arc", "arc"))
    assert result.selection == (c.EntitySelection("arc", "arc"),)
    assert {item.id for item in result.relations} == {"anchor", "join", "length", "arc_radius"}
    assert (
        next(item for item in result.relations if item.id == "arc_radius").source_value
        == " radius + 0 "
    )
    for identifier in ("a", "b", "c"):
        assert "arc_radius" in {
            item.id for item in contract(source, ("point", identifier)).relations
        }
    assert "arc_radius" not in {item.id for item in contract(source, ("point", "d")).relations}
    assert source == before
    assert result.action("horizontal").state == "unavailable"
    assert result.action("fix_here").state == "unavailable"


@pytest.mark.parametrize("version", [True, 3.0, "3", None, 4, []])
def test_arc_selection_rejects_nonexact_schema_before_any_inspection(version):
    source = arc_sketch()
    source["schema_version"] = version
    before = copy.deepcopy(source)
    with pytest.raises(ValueError):
        contract(source, ("arc", "arc"))
    assert source == before


@pytest.mark.parametrize("mutation", ["missing", "unknown", "role", "direction", "wrong_kind"])
def test_arc_selection_rejects_malformed_or_mismatched_sources(mutation):
    source = arc_sketch()
    selection = selected(("arc", "arc"))
    if mutation == "missing":
        del source["arcs"]
    elif mutation == "unknown":
        source["arcs"][0]["radius"] = 5
    elif mutation == "role":
        source["arcs"][0]["end"] = "a"
    elif mutation == "direction":
        source["arcs"][0]["direction"] = "CCW"
    else:
        selection = selected(("circle", "arc"))
    before = copy.deepcopy((source, selection))
    with pytest.raises(ValueError):
        c.selection_contract(source, selection)
    assert (source, selection) == before


def test_palette_applicability_is_not_execution_authority():
    source = sketch()
    point = selected(("point", "a"))
    line = selected(("line", "line"))
    hint = c.applicability_hint
    assert hint(source, line, "horizontal", has_solution=False, has_retained_evidence=False)
    assert not hint(source, point, "fix_here", has_solution=False, has_retained_evidence=False)
    assert hint(source, point, "fix_here", has_solution=True, has_retained_evidence=False)
    assert hint(source, point, "fix_origin", has_solution=False, has_retained_evidence=False)
    source["constraints"] = [relations()[0]]
    relation = selected(("constraint", "horizontal"))
    assert not hint(
        source, relation, "remove_relation", has_solution=False, has_retained_evidence=False
    )
    assert hint(source, relation, "remove_relation", has_solution=True, has_retained_evidence=True)
    assert hint(
        source, relation, "recover_remove_relation", has_solution=False, has_retained_evidence=False
    )
    assert not hint(
        source, relation, "recover_remove_relation", has_solution=False, has_retained_evidence=True
    )
    assert not hint(
        source, relation, "recover_remove_relation", has_solution=True, has_retained_evidence=False
    )
