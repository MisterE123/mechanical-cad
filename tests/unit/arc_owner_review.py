"""Finite reviewed owner-method seals, not a whole-source historical freeze.

The explicit inventory follows projection/choice (8abf807), guarded line length
(82cfda5), circle diameter (7064045), removal and preview owners. Only these
security-relevant method bodies and version-provenance initializers are sealed.
New calls/changed ownership require an explicit review, never automatic discovery
or a blanket permission for attribute-sourced result versions.
"""

import ast
import hashlib
import json

# Canonical AST hashes reviewed at source 4b31b80; whitespace is not authority.
REVIEWED_METHODS = {
    (
        "solid_projection_picker",
        "SolidProjectionPicker.begin_choice",
    ): "0ca3f951cb834499abc4eafab0459ad73b9c84c27f28daec34156b0980ad0da8",
    (
        "circle_diameter_session",
        "CircleDiameterSession._diameter_read",
    ): "1665362f2bd3a74dcfddc9330266b2fd6c147365f959e37a32799afab5cec154",
    (
        "circle_diameter_session",
        "CircleDiameterSession.complete_circle_diameter",
    ): "f0032918f2dc383d4caf1bfe316fade5f70111452d3dcc8e43e18babd31d105b",
    (
        "direct_edge_pick",
        "BlendEdgePicker.__init__",
    ): "92173d1d167469bc45d9f255736b55162ac3b655054a97c724b3150a0d442734",
    (
        "direct_edge_pick",
        "BlendEdgePicker.hover",
    ): "a9da29bbd744e9995de609591f586112c41281eefa65c05d9c013811adc51402",
    (
        "direct_edge_pick",
        "BlendEdgePicker.poll_catalog",
    ): "683c9ade0ee7b2ebad33d4455eaf72666b877373519e70c1fd81e2f033acc13d",
    (
        "direct_edge_pick",
        "BlendEdgePicker.selected_arguments",
    ): "c3705ea153cdec456b2ed133c6b3a7852cb43fcdd65a37e1027d6c0e276ebf95",
    (
        "extrusion_preview",
        "Preview.tick",
    ): "5927efebb5c7858247c2803e9cbf699a999bb0925190a515cac4db6e1e40d831",
    (
        "general_session",
        "GeneralSession._solid_projection_edges",
    ): "bf61456799154e38d8e8528b9e367c40c2d59c674e143faa6440c2c3aa47b521",
    (
        "general_session",
        "GeneralSession.project_solid_edge",
    ): "b67eefe3611dbea664a9a288bc25e269647aa2be5e46a2f65b2c350399cbc350",
    (
        "line_length_session",
        "LineLengthSession._length_read",
    ): "14ba0db8fde3c089769955e9fcbae75d11a20417c4cbffa3ce4d986e28c9f097",
    (
        "line_length_session",
        "LineLengthSession.complete_line_length",
    ): "571096c268369a070cdf168932c6f8c8dc812ca2dd6609ad0acf1493bfa5fad9",
    (
        "projection_edge_choice",
        "EdgeChoice.__init__",
    ): "d05d6ee1141c3c345d5385c986f877ad813ea1aec94019827cc7e1a1d7805735",
    (
        "projection_edge_choice",
        "EdgeChoice.consume",
    ): "97b51d519c670eaef0d8d30f2db0c0f3f2e89a520d93a9ec8a99040b6f62df39",
    (
        "projection_edge_choice",
        "EdgeChoice.require",
    ): "d821fa53ba0dc8e6501ff80b205d7306869868b7626f20b9b7f501876a78e01a",
    (
        "projection_repair_ui",
        "MCAD_OT_replace_projection_reference._review",
    ): "ce355b819aa50d90db9ef8677bdb05bd540bf58fe1b609be95c78be95b2fea95",
    (
        "projection_repair_ui",
        "MCAD_OT_replace_projection_reference.invoke",
    ): "5a8dfe2872d30154f63a8144a9c43559325765284b15633a0ebb0a6ea07bc4aa",
    (
        "sketch_remove_fillet_session",
        "RemoveFilletSession.complete_fillet_removal",
    ): "ac830803403739ff137c719e98c3c30b32f3d22cbc3ff07edd30dcddf79913f9",
    (
        "solid_projection_picker",
        "SolidProjectionPicker.apply_choice",
    ): "18f4cdff55fd6d7a7cd1002230cfad37278724008fdd3e68a11235ae34c14c13",
    (
        "solid_projection_picker",
        "SolidProjectionPicker.validate_choice",
    ): "3277f24649721193adec0936e1a459daae471572a5ee0a92affefee781a95c79",
}

DYNAMIC_VERSION_METHODS = {
    ("direct_edge_pick", "BlendEdgePicker.poll_catalog"),
    ("direct_edge_pick", "BlendEdgePicker.hover"),
    ("direct_edge_pick", "BlendEdgePicker.selected_arguments"),
    ("projection_repair_ui", "MCAD_OT_replace_projection_reference._review"),
    ("solid_projection_picker", "SolidProjectionPicker.validate_choice"),
    ("line_length_session", "LineLengthSession.complete_line_length"),
    ("circle_diameter_session", "CircleDiameterSession.complete_circle_diameter"),
    ("sketch_remove_fillet_session", "RemoveFilletSession.complete_fillet_removal"),
    ("extrusion_preview", "Preview.tick"),
}

# These AST binders store the bound identifier as text, not ast.Name(Store).
# Type-parameter names matter on 3.12+: a class parameter is visible in methods.
# This is a finite constructor-binding check, not a Python execution sandbox.
CHOICE_STRING_BINDERS = {
    "ExceptHandler": "name",
    "MatchAs": "name",
    "MatchStar": "name",
    "MatchMapping": "rest",
    "TypeVar": "name",
    "ParamSpec": "name",
    "TypeVarTuple": "name",
}


def definitions(tree):
    found = {}

    def walk(node, names=()):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names = (*names, node.name)
            name = ".".join(names)
            assert name not in found, "reviewed owner definition shadowed"
            found[name] = node
        for child in ast.iter_child_nodes(node):
            walk(child, names)

    walk(tree)
    return found


def method_digest(node):
    """Stable across 3.11/3.12+; ignore only absent versus empty type parameters."""

    def canonical(value):
        if isinstance(value, ast.AST):
            return [
                type(value).__name__,
                [
                    [name, canonical(field)]
                    for name, field in sorted(ast.iter_fields(value))
                    if not (name == "type_params" and field == [])
                ],
            ]
        if isinstance(value, list):
            return [canonical(item) for item in value]
        return value

    raw = json.dumps(canonical(node), separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def verify_reviewed_methods(tree, module):
    if not any(owner == module for owner, _name in REVIEWED_METHODS):
        return {}
    functions = definitions(tree)
    if module == "solid_projection_picker":
        # The consume exception also requires the reviewed constructor binding,
        # not a same-named imported authority type or a shadowed local alias.
        assert not any(
            alias.name == "*"
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        ), "wildcard import cannot prove the reviewed choice binding"
        bindings = [
            (node, alias)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if (alias.asname or alias.name) == "EdgeChoice"
        ]
        assert len(bindings) == 1
        imported, alias = bindings[0]
        assert imported.level == 1 and imported.module == "projection_edge_choice"
        assert alias.name == "EdgeChoice" and alias.asname is None
        # `import pkg.child` binds pkg, while `import pkg.child as Name`
        # binds Name. Import aliases are not ast.Name(Store) nodes.
        assert not any(
            (alias.asname or alias.name.split(".")[0]) == "EdgeChoice"
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ), "reviewed choice constructor shadowed by import"
        assert not any(
            getattr(node, CHOICE_STRING_BINDERS[type(node).__name__], None) == "EdgeChoice"
            for node in ast.walk(tree)
            if type(node).__name__ in CHOICE_STRING_BINDERS
        ), "reviewed choice constructor shadowed by string binder"
        parents = {
            id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
        }
        references = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id == "EdgeChoice"
        ]
        assert len(references) == 1 and isinstance(references[0].ctx, ast.Load)
        call = parents[id(references[0])]
        assert isinstance(call, ast.Call) and call.func is references[0]
        assert ast.unparse(call) == "EdgeChoice(self, self.overlap_candidates)"
        assert not any(
            (
                isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "EdgeChoice"
            )
            or (isinstance(node, ast.arg) and node.arg == "EdgeChoice")
            for node in ast.walk(tree)
        )
    for (owner, name), expected in REVIEWED_METHODS.items():
        if owner == module:
            assert name in functions, (module, name, "missing reviewed owner")
            assert method_digest(functions[name]) == expected, (module, name, "owner changed")
    return functions


def reviewed_dynamic_calls(tree, module):
    functions = verify_reviewed_methods(tree, module)
    admitted = set()
    for owner, name in DYNAMIC_VERSION_METHODS:
        if owner != module:
            continue
        calls = [
            node
            for node in ast.walk(functions[name])
            if isinstance(node, ast.Call)
            and any(item.arg == "expected_result_version" for item in node.keywords)
        ]
        assert len(calls) == 1, (module, name, "unexpected authority count")
        admitted.update(calls)
    return admitted
