"""Finite reviewed authority-call inventory for the atomic General/Part cutover."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest
from arc_owner_review import verify_reviewed_methods

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"

METHODS = {"revalidate", "consume"}


def authority_inventory(raw, module=""):
    tree = ast.parse(raw)
    verify_reviewed_methods(tree, module)
    parents = {
        id(child): parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
    }

    def scope(node):
        names = []
        while id(node) in parents:
            node = parents[id(node)]
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(node.name)
        return ".".join(reversed(names))

    aliases = {}
    alias_nodes = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        references = [
            part
            for part in ast.walk(node.value)
            if isinstance(part, ast.Attribute)
            and part.attr in METHODS
            and not (isinstance(parents.get(id(part)), ast.Call) and parents[id(part)].func is part)
        ]
        if references:
            assert len(targets) == 1 and isinstance(targets[0], ast.Name), (
                "unsupported authority alias target"
            )
            assert isinstance(node.value, (ast.Attribute, ast.IfExp)), (
                "unsupported authority alias expression"
            )
            assert not any(isinstance(part, ast.Call) for part in ast.walk(node.value)), (
                "authority alias may not execute"
            )
            key = scope(node), targets[0].id
            assert key not in aliases, "authority alias reassignment"
            aliases[key] = ast.unparse(node.value)
            alias_nodes.update(id(part) for part in references)
    rows, used = [], set()
    direct_nodes = set()
    choice_nodes = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        direct = isinstance(node.func, ast.Attribute) and node.func.attr in METHODS
        key = (scope(node), node.func.id) if isinstance(node.func, ast.Name) else None
        if not direct and key not in aliases:
            continue
        if (
            module == "solid_projection_picker"
            and scope(node) == "SolidProjectionPicker.apply_choice"
            and ast.unparse(node) == "choice.consume(self)"
        ):
            # The sealed method first validates the choice's guarded evidence;
            # this distinct one-shot UI choice is not EvidencePublication.
            choice_nodes.add(id(node.func))
            continue
        if direct:
            direct_nodes.add(id(node.func))
        else:
            used.add(key)
        assert all(item.arg is not None for item in node.keywords), (
            "authority kwargs must be explicit"
        )
        keywords = {item.arg: ast.unparse(item.value) for item in node.keywords}
        rows.append((scope(node), ast.unparse(node.func), keywords))
    assert used == set(aliases), "unused or untraced authority alias"
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in METHODS:
            assert id(node) in alias_nodes | direct_nodes | choice_nodes, (
                "untraced authority method reference"
            )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
        ):
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                assert node.args[1].value not in METHODS, "dynamic authority method lookup"
    return rows, aliases


# These expressions are separately inspected at their defining owners. Neither
# received result stamps nor a broad version set may select a live contract.
EXPECTED_AUTHORITY_CALLS = (
    ("direct_edge_pick", "BlendEdgePicker.poll_catalog", "self.catalog_version", "'edge_catalog'"),
    ("direct_edge_pick", "BlendEdgePicker.hover", "self.catalog_version", "'edge_catalog'"),
    ("direct_edge_pick", "BlendEdgePicker.selected_arguments", "self.catalog_version", "'edge_catalog'"),
    ("projection_repair_ui", "MCAD_OT_replace_projection_reference._review", "self._version", "'edge_catalog'"),
    ("solid_projection_picker", "SolidProjectionPicker.validate_choice", "self.catalog_version", "'edge_catalog'"),
    ("general_session", "GeneralSession.project_solid_edge", "version", "'edge_catalog'"),
    ("general_session", "GeneralSession._solid_projection_edges", "version", "'edge_catalog'"),
    ("line_length_session", "LineLengthSession.complete_line_length", "prepared.operation_request()['result_version']", "'solve_sketch'"),
    ("circle_diameter_session", "CircleDiameterSession.complete_circle_diameter", "prepared.operation_request()['result_version']", "'solve_sketch'"),
    ("extrusion_preview", "Preview.tick", "operation_contracts.result_version_for(candidate)", "'replay'"),
    ("sketch_remove_fillet_session", "RemoveFilletSession.complete_fillet_removal",
     "prepared.operation_request()['result_version']", "action"),
    ("assembly_display", "_validated", "result_version", "assembly_bridge.ACTIONS"),
    ("assembly_export_owner", "_checked_report", "version", "'assembly_check'"),
    (
        "assembly_export_owner",
        "_historical_projection",
        "prepared.operation_request()['result_version']",
        "ACTION",
    ),
    ("assembly_export_owner", "run_export", "request['result_version']", "ACTION"),
    ("assembly_operator_helpers", "canonical_working_part", "None", "'canonical_snapshot'"),
    ("assembly_state", "_projection", "result_version", "actions"),
    (
        "assembly_state",
        "report_is_current",
        "result_version",
        "{'assembly_check', 'assembly_sample'}",
    ),
    ("document_state", "_evidence_projection", "version", "prepared.action"),
    (
        "general_session",
        "GeneralSession._record_build_failure",
        "prepared.operation_request()['result_version']",
        "'replay'",
    ),
    ("general_session", "GeneralSession.tick", "request['result_version']", "'solve_sketch'"),
    ("general_session", "GeneralSession.tick", "request['result_version']", "'replay'"),
    ("general_sketch_draft", "read_guarded_operation", "version", "action"),
    ("geometry_operations", "_historical_projection", "version", "action"),
    (
        "guarded_evidence",
        "EvidencePublication.consume",
        "expected_result_version",
        "expected_action",
    ),
    ("guarded_operations", "canonical_snapshot_guarded", "None", "part_snapshot_bridge.ACTION"),
    (
        "guarded_transport",
        "GuardedJob.result",
        "self.prepared.operation_request().get('result_version')",
        "self.prepared.action",
    ),
    (
        "sketch_draft",
        "RectangleDraft._guarded_report",
        "2",
        "{'replay', 'check_geometry', 'export_step', 'export_stl'}",
    ),
    (
        "sketch_draft",
        "RectangleDraft.accept_guarded_replay",
        "2",
        "{'replay', 'check_geometry', 'export_step', 'export_stl'}",
    ),
    (
        "sketch_draft",
        "RectangleDraft.accept_guarded_replay",
        "2",
        "{'replay', 'check_geometry', 'export_step', 'export_stl'}",
    ),
)
EXPECTED_ALIASES = {
    ("assembly_display", "_validated", "validate"),
    ("assembly_state", "_projection", "validate"),
    ("document_state", "_evidence_projection", "method"),
    ("sketch_draft", "RectangleDraft.accept_guarded_replay", "validate"),
}
EXPECTED_READ_WRAPPERS = (
    ("circle_diameter_session", "CircleDiameterSession._diameter_read", "pair[1]", "action"),
    ("line_length_session", "LineLengthSession._length_read", "pair[1]", "action"),
    ("sketch_remove_fillet_session", "RemoveFilletSession._removal_read", "pair[1]", "action"),
    (
        "constraint_diagnostics",
        "FailureDiagnostics.from_guarded",
        "expected_prepared",
        "'solve_sketch'",
    ),
    (
        "constraint_diagnostics",
        "GuardedFailureDiagnostics.for_current",
        "self._expected_prepared",
        "'solve_sketch'",
    ),
    (
        "constraint_diagnostics",
        "GuardedBuildFailure._snapshot",
        "expected",
        "'solve_sketch' if index == 0 else 'replay'",
    ),
    ("constraint_diagnostics", "GuardedBuildFailure._snapshot", "replay_prepared", "'replay'"),
    (
        "general_session",
        "GeneralSession.current_solution_response",
        "self.expected_prepared",
        "'solve_sketch'",
    ),
    ("general_session", "GeneralSession.tick", "prepared", "request['action']"),
    ("general_session", "GeneralSession.tick", "prepared", "'solve_sketch'"),
    (
        "general_session",
        "GeneralSession._accepted_driver.verify_acceptance",
        "expected_prepared",
        "'solve_sketch'",
    ),
    (
        "general_sketch_draft",
        "GeneralSketchDraft.record_guarded_solution",
        "expected_prepared",
        "'solve_sketch'",
    ),
    (
        "general_sketch_draft",
        "GeneralSketchDraft.record_guarded_solution",
        "expected_prepared",
        "'solve_sketch'",
    ),
    (
        "general_sketch_draft",
        "GeneralSketchDraft._guarded_current",
        "expected",
        "'solve_sketch' if index == 0 else 'replay'",
    ),
    ("general_sketch_draft", "GeneralSketchDraft.accept_edit", "replay_prepared", "'replay'"),
    ("general_view_geometry", "build_guarded_geometry", "expected_prepared", "'solve_sketch'"),
    ("sketch_pending", "poll", "pending._prepared", "pending._request['action']"),
)


def check_authority_sources(sources, *, complete=True):
    actual, aliases = [], set()
    for filename, source in sorted(sources.items()):
        path = Path(filename)
        calls, assigned = authority_inventory(source, path.stem)
        for scope, _callee, keywords in calls:
            assert "owner_token" in keywords, (path.name, scope)
            assert "expected_result_version" in keywords, (path.name, scope)
            assert "expected_action" in keywords, (path.name, scope)
            actual.append(
                (path.stem, scope, keywords["expected_result_version"], keywords["expected_action"])
            )
        aliases.update((path.stem, scope, name) for scope, name in assigned)
    modules = {Path(name).stem for name in sources}
    expected = EXPECTED_AUTHORITY_CALLS if complete else (
        row for row in EXPECTED_AUTHORITY_CALLS if row[0] in modules
    )
    expected_aliases = EXPECTED_ALIASES if complete else {
        row for row in EXPECTED_ALIASES if row[0] in modules
    }
    assert Counter(actual) == Counter(expected)
    assert aliases == expected_aliases


def test_every_authority_sink_and_alias_has_explicit_reviewed_version_and_action():
    check_authority_sources({path.name: path.read_text() for path in ADDON.glob("*.py")})


def test_assembly_version_selection_uses_exact_source_policy_not_received_stamp():
    expected = {
        ("assembly_display", "_validated"): (
            "operation_contracts.result_version_for_assembly("
            "operation.get('assembly'), action=operation.get('action'))"
        ),
        ("assembly_state", "_projection"): (
            "_preflight_assembly(operation.get('assembly'), operation.get('action'))"
        ),
        ("assembly_state", "_prepare_operation"): "_preflight_assembly(assembly, action)",
        ("assembly_state", "report_is_current"): (
            "_preflight_assembly(read_assembly(state), evidence.operation_request().get('action'))"
        ),
    }
    for (module, name), expression in expected.items():
        tree = ast.parse((ADDON / (module + ".py")).read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assignments = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "result_version"
                for target in node.targets
            )
        ]
        assert len(assignments) == 1
        assert ast.unparse(assignments[0].value) == expression


def reject_untraced_read_wrapper(tree):
    parents = {
        id(child): parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "read_guarded_operation":
                    assert alias.asname is None, "renamed guarded read helper"
        reference = (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "read_guarded_operation"
        ) or (isinstance(node, ast.Attribute) and node.attr == "read_guarded_operation")
        if reference:
            parent = parents.get(id(node))
            assert isinstance(parent, ast.Call) and parent.func is node, (
                "untraced guarded read helper reference"
            )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) > 1
        ):
            if isinstance(node.args[1], ast.Constant):
                assert node.args[1].value != "read_guarded_operation", "dynamic guarded read helper"


@pytest.mark.parametrize(
    "source",
    [
        "from .general_sketch_draft import read_guarded_operation as read\nread(e,p,s)",
        "from .general_sketch_draft import read_guarded_operation\nr=read_guarded_operation\nr(e,p,s)",
        "from . import general_sketch_draft as d\nr=d.read_guarded_operation\nr(e,p,s)",
        "from . import general_sketch_draft as d\ngetattr(d,'read_guarded_operation')(e,p,s)",
    ],
)
def test_untraced_general_read_helper_references_reject(source):
    with pytest.raises(AssertionError):
        reject_untraced_read_wrapper(ast.parse(source))


def test_all_general_read_wrappers_supply_independent_prepared_request():
    actual = []
    for path in sorted(ADDON.glob("*.py")):
        tree = ast.parse(path.read_text())
        reject_untraced_read_wrapper(tree)
        parents = {
            id(child): parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if name != "read_guarded_operation":
                continue
            names, parent = [], node
            while id(parent) in parents:
                parent = parents[id(parent)]
                if isinstance(parent, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.append(parent.name)
            keywords = {item.arg: ast.unparse(item.value) for item in node.keywords}
            assert len(node.args) == 3 and "owner_token" in keywords and "action" in keywords
            actual.append(
                (
                    path.stem,
                    ".".join(reversed(names)),
                    ast.unparse(node.args[1]),
                    keywords["action"],
                )
            )
    assert Counter(actual) == Counter(EXPECTED_READ_WRAPPERS)


def factory_inventory(raw, module):
    tree = ast.parse(raw)
    bindings, factory_imports = {}, []
    protected = {
        "guarded_evidence.accept_response",
        "guarded_evidence.GuardedEvidence",
        "guarded_evidence.EvidencePublication",
    }
    if module == "guarded_evidence":
        bindings.update(
            {
                name: "guarded_evidence." + name
                for name in ("GuardedEvidence", "EvidencePublication", "accept_response")
            }
        )

    def resolve(node):
        if isinstance(node, ast.Name):
            return bindings.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return resolve(node.value) + "." + node.attr
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports = [alias.name for alias in node.names]
            for alias in node.names:
                if alias.name.split(".")[-1] == "guarded_evidence":
                    bindings[alias.asname or alias.name] = "guarded_evidence"
        elif isinstance(node, ast.ImportFrom):
            imports = [node.module or "", *(alias.name for alias in node.names)]
            for alias in node.names:
                if alias.name == "guarded_evidence":
                    bindings[alias.asname or alias.name] = "guarded_evidence"
                if (node.module or "").split(".")[-1] == "guarded_evidence":
                    bindings[alias.asname or alias.name] = "guarded_evidence." + alias.name
                    if alias.name == "accept_response":
                        factory_imports.append((module, alias.name, alias.asname))
        else:
            imports = []
        for imported in imports:
            parts = imported.split(".")
            assert not any(
                part == "service_v3" or part in {"tests", "fixtures"} or part.startswith("test_")
                for part in parts
            ), (module, imported)

    # Bound alias propagation handles module/class assignments as well as import
    # aliases. The exact full source hash remains the separate ultimate boundary.
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
    ]
    for _ in range(len(assignments) + 1):
        changed = False
        for node in assignments:
            value = resolve(node.value)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if value == "guarded_evidence" or value in protected:
                for target in targets:
                    if isinstance(target, ast.Name) and bindings.get(target.id) != value:
                        bindings[target.id] = value
                        changed = True
        if not changed:
            break
    else:
        raise AssertionError("unbounded factory alias resolution")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = resolve(node.func)
        if resolved in protected:
            if resolved.endswith(".accept_response"):
                assert (
                    module == "guarded_transport"
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "accept_response"
                )
            else:
                assert module == "guarded_evidence"
        if isinstance(node.func, ast.Attribute) and node.func.attr == "accept_response":
            raise AssertionError("unreviewed module-qualified evidence factory")
        if isinstance(node.func, ast.Attribute) and node.func.attr == "__new__":
            if any(resolve(arg) in protected for arg in node.args):
                assert module == "guarded_evidence"
        if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) > 1:
            if isinstance(node.args[1], ast.Constant):
                assert node.args[1].value not in {
                    "accept_response",
                    "GuardedEvidence",
                    "EvidencePublication",
                }
    return factory_imports


def test_runtime_cannot_import_test_ports_or_data_only_jobs_or_add_evidence_factories():
    factory_imports = []
    for path in sorted(ADDON.glob("*.py")):
        factory_imports.extend(factory_inventory(path.read_text(), path.stem))
    assert factory_imports == [("guarded_transport", "accept_response", None)]


@pytest.mark.parametrize(
    "source",
    [
        "from . import guarded_evidence as g\ng.accept_response(a,b,c)",
        "import addon.guarded_evidence as g\nh = g\nh.accept_response(a,b,c)",
        "from .guarded_evidence import GuardedEvidence as G\nG()",
        "from .guarded_evidence import GuardedEvidence as G\nH=G\nobject.__new__(H)",
        "from . import guarded_evidence as g\nC=g.EvidencePublication\nC(e)",
        "from . import guarded_evidence as g\ngetattr(g,'accept_response')(a,b,c)",
    ],
)
def test_factory_inventory_follows_import_and_assignment_aliases(source):
    with pytest.raises(AssertionError):
        factory_inventory(source, "unauthorized_owner")


@pytest.mark.parametrize(
    "source",
    [
        "def f(e):\n    escaped = (e.revalidate,)\n    return escaped[0]()",
        "def f(e):\n    escaped = e.revalidate\n    other = escaped\n    return other()",
        "def f(e):\n    return wrapper(e.revalidate)",
        "def f(e):\n    return getattr(e, 'revalidate')()",
        "def f(e):\n    method = e.revalidate\n    return method(**options)",
    ],
)
def test_inventory_rejects_untraced_authority_aliases(source):
    with pytest.raises(AssertionError):
        authority_inventory(source)


def test_inventory_detects_direct_and_conditional_alias_calls():
    source = "def f(e, consume):\n    method = e.publication.consume if consume else e.revalidate\n    return method(owner_token=o, expected_action='replay', expected_result_version=2)"
    calls, aliases = authority_inventory(source)
    assert len(calls) == 1 and aliases == {
        ("f", "method"): "e.publication.consume if consume else e.revalidate"
    }
    assert calls[0][2]["expected_result_version"] == "2"


def test_export_authority_uses_source_policy_and_preserves_display_action_trio():
    for module, variable in (
        ("assembly_validation_common", "ACTIONS"),
        ("operation_contracts", "_ASSEMBLY_ACTIONS"),
    ):
        tree = ast.parse((ADDON / (module + ".py")).read_text())
        value = next(
            node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == variable for target in node.targets
            )
        )
        assert (
            ast.unparse(value)
            == "frozenset({'assembly_replay', 'assembly_check', 'assembly_sample'})"
        )
    tree = ast.parse((ADDON / "assembly_export_bridge.py").read_text())
    source_policy = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "result_version_for"
    )
    expected_policy = ast.parse("""
candidate = request_contracts.snapshot_request(assembly)
_require(
    candidate.get("kind") == "assembly"
    and type(candidate.get("assembly_schema_version")) is int
    and candidate["assembly_schema_version"] == 1
    and type(candidate.get("part_sources")) is list,
    "unsupported Assembly source envelope",
)
selected = 2
for source in candidate["part_sources"]:
    _require(type(source) is dict and "document" in source, "missing Assembly Part source")
    document = source["document"]
    canonical = part_snapshot_bridge._expected_document(document)
    result_v3._graph(canonical, replay=True)
    if part_snapshot_bridge._uses_schema3(document):
        selected = 3
return selected
""")
    assert ast.dump(
        ast.Module(body=source_policy.body[1:], type_ignores=[]), include_attributes=False
    ) == ast.dump(expected_policy, include_attributes=False)
    tree = ast.parse((ADDON / "assembly_export_owner.py").read_text())
    action = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "ACTION" for target in node.targets)
    ]
    assert len(action) == 1 and ast.literal_eval(action[0]) == "assembly_export_step"
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for function, variable, expression in (
        ("_checked_report", "assembly", "assembly_state.read_assembly(state)"),
        ("_checked_report", "version", "assembly_export_bridge.result_version_for(assembly)"),
        ("_historical_projection", "prepared", "snapshot.get('prepared')"),
        (
            "run_export",
            "request",
            "assembly_export_bridge.build_request(snapshot['assembly'], path)",
        ),
    ):
        stores = [
            node
            for node in ast.walk(functions[function])
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == variable
        ]
        assert len(stores) == 1
        assignments = [
            node
            for node in ast.walk(functions[function])
            if isinstance(node, ast.Assign) and node.targets == stores
        ]
        assert len(assignments) == 1 and ast.unparse(assignments[0].value) == expression


@pytest.mark.parametrize(
    "module,before,after",
    [
        ("solid_projection_picker", "choice = self.validate_choice(context)", "choice = self.edge_choice"),
        ("solid_projection_picker", "from .projection_edge_choice import EdgeChoice, freeze_candidates", "from .projection_edge_choice import freeze_candidates\nfrom .guarded_evidence import EvidencePublication as EdgeChoice"),
        ("solid_projection_picker", "self.edge_choice = EdgeChoice(self, self.overlap_candidates)", "self.edge_choice = self.catalog_evidence"),
        ("solid_projection_picker", "source, entry = choice.consume(self)", "source, entry = choice.evidence.publication.consume(self)"),
        ("solid_projection_picker", "source, entry = choice.consume(self)", "consume = choice.consume\n        source, entry = consume(self)"),
        ("solid_projection_picker", "owner_token=choice.catalog_token", "owner_token=self.owner_token"),
        ("solid_projection_picker", 'expected_action="edge_catalog"', 'expected_action="replay"'),
        ("projection_edge_choice", "self.retired = True", "self.retired = False"),
        ("projection_edge_choice", "picker.edge_choice is not self", "False"),
        ("line_length_session", "owner_token=self.owner_token", "owner_token=None"),
        ("circle_diameter_session", 'expected_action="solve_sketch"', 'expected_action="replay"'),
    ],
)
def test_reviewed_choice_and_new_owner_bodies_cannot_hide_authority_mutations(module, before, after):
    # Positive local admission prevents a partial-inventory mismatch from making
    # a mutation test pass vacuously; the full live inventory is checked above.
    sources = {module + ".py": (ADDON / (module + ".py")).read_text()}
    check_authority_sources(sources, complete=False)
    original = sources[module + ".py"]
    assert before in original
    sources[module + ".py"] = original.replace(before, after, 1)
    with pytest.raises(AssertionError):
        check_authority_sources(sources, complete=False)


@pytest.mark.parametrize(
    "extra",
    [
        "def rogue(choice):\n    return choice.consume(self)\n",
        "def rogue(evidence):\n    return evidence.consume(owner_token=o, expected_result_version=2, expected_action='replay')\n",
        "def rogue(evidence):\n    consume = evidence.consume\n    return consume(owner_token=o, expected_result_version=2, expected_action='replay')\n",
        "def rogue(evidence):\n    return getattr(evidence, 'consume')()\n",
    ],
)
def test_choice_exception_never_admits_extra_direct_alias_or_dynamic_authority(extra):
    sources = {"solid_projection_picker.py": (ADDON / "solid_projection_picker.py").read_text()}
    check_authority_sources(sources, complete=False)
    sources["solid_projection_picker.py"] += "\n" + extra
    with pytest.raises(AssertionError):
        check_authority_sources(sources, complete=False)


def test_method_seals_are_portable_without_ignoring_real_type_parameters():
    from arc_owner_review import method_digest

    function = ast.parse("def f(value):\n    return value\n").body[0]
    expected = method_digest(function)
    # Python 3.11 has no type_params field; Python 3.12+ adds its empty list.
    function._fields = tuple(name for name in function._fields if name != "type_params")
    assert method_digest(function) == expected
    function._fields = (*function._fields, "type_params")
    function.type_params = []
    assert method_digest(function) == expected
    function.type_params = [ast.Name(id="T", ctx=ast.Load())]
    assert method_digest(function) != expected


@pytest.mark.parametrize(
    "statement",
    [
        "import types as EdgeChoice",
        "import json.decoder as EdgeChoice",
        "import EdgeChoice",
        "import EdgeChoice.shadow",
    ],
)
def test_choice_constructor_rejects_plain_and_dotted_import_shadows(statement):
    source = (ADDON / "solid_projection_picker.py").read_text()
    check_authority_sources({"solid_projection_picker.py": source}, complete=False)
    with pytest.raises(AssertionError, match="constructor shadowed by import"):
        check_authority_sources(
            {"solid_projection_picker.py": source + "\n" + statement + "\n"}, complete=False
        )


def test_choice_import_rule_uses_actual_python_bound_name_not_dotted_suffix():
    source = (ADDON / "solid_projection_picker.py").read_text()
    # This spelling binds unrelated_package, not the EdgeChoice suffix. No code
    # executes; the scanner must distinguish binding from a textual name match.
    check_authority_sources(
        {"solid_projection_picker.py": source + "\nimport unrelated_package.EdgeChoice\n"},
        complete=False,
    )


@pytest.mark.parametrize(
    "statement",
    [
        "try:\n    pass\nexcept Exception as EdgeChoice:\n    pass\n",
        "match value:\n    case EdgeChoice:\n        pass\n",
        "match value:\n    case [*EdgeChoice]:\n        pass\n",
        "match value:\n    case {**EdgeChoice}:\n        pass\n",
    ],
)
def test_choice_constructor_rejects_exception_and_pattern_capture_binders(statement):
    source = (ADDON / "solid_projection_picker.py").read_text()
    check_authority_sources({"solid_projection_picker.py": source}, complete=False)
    with pytest.raises(AssertionError, match="constructor shadowed by string binder"):
        check_authority_sources(
            {"solid_projection_picker.py": source + "\n" + statement}, complete=False
        )


@pytest.mark.parametrize("kind", ["TypeVar", "ParamSpec", "TypeVarTuple"])
def test_choice_constructor_rejects_class_type_parameter_binders_on_supported_ast_schemas(kind):
    from arc_owner_review import definitions

    tree = ast.parse((ADDON / "solid_projection_picker.py").read_text())
    verify_reviewed_methods(tree, "solid_projection_picker")
    owner = definitions(tree)["SolidProjectionPicker"]
    # Represent the exact name-bearing 3.12+ AST shape also on 3.11, where this
    # syntax cannot be parsed. No generated code is compiled or executed.
    binder = type(kind, (ast.AST,), {"_fields": ("name",)})(name="EdgeChoice")
    owner._fields = (*tuple(name for name in owner._fields if name != "type_params"), "type_params")
    owner.type_params = [binder]
    with pytest.raises(AssertionError, match="constructor shadowed by string binder"):
        verify_reviewed_methods(tree, "solid_projection_picker")


def test_unrelated_pattern_capture_does_not_shadow_the_reviewed_constructor():
    source = (ADDON / "solid_projection_picker.py").read_text()
    check_authority_sources(
        {"solid_projection_picker.py": source + "\nmatch value:\n    case harmless:\n        pass\n"},
        complete=False,
    )


def test_wildcard_import_cannot_claim_an_unrelated_constructor_binding():
    source = (ADDON / "solid_projection_picker.py").read_text()
    check_authority_sources({"solid_projection_picker.py": source}, complete=False)
    with pytest.raises(AssertionError, match="wildcard import cannot prove"):
        check_authority_sources(
            {"solid_projection_picker.py": source + "\nfrom .unreviewed import *\n"}, complete=False
        )
