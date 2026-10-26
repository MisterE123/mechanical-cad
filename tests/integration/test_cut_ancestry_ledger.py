"""Current Cut ancestry records every native face claim without naming faces."""

import copy

import pytest

pytest.importorskip("OCP")
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer

from mechanical_cad.kernel_ocp import KernelError, OCPKernel


def box(kernel, name, width, height, *, x=0, y=0, z=0, length=10):
    shape = kernel.extrude(kernel.rectangle(width, height, x, y, z), length)
    kernel.topology(shape, name, "", {})
    return shape


def split_block():
    kernel = OCPKernel(cut_tool_lineage=True)
    base = box(kernel, "block", 20, 20)
    tool = box(kernel, "slot_tool", 2, 22, x=9, y=-1, z=7, length=5)
    split = kernel.cut(base, tool)
    kernel.topology(split, "first", "", {})
    return kernel, base, tool, split


def native_faces(shape):
    faces = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = explorer.Current()
        if not any(face.IsSame(previous) for previous in faces):
            faces.append(face)
        explorer.Next()
    return faces


def assert_exact_native_ledger(kernel, shape):
    """Compare the complete receipt with fresh queries of the retained builder."""
    ledger = kernel.cut_ancestry(shape)
    operation = kernel._operations[id(shape)]
    assert set(ledger) == {"version", "sources"}
    assert type(ledger["version"]) is int and ledger["version"] == 1
    expected_keys = set()
    for port in ("base", "tool"):
        operand = operation.inputs[port]
        source_faces = kernel._operations[id(operand)].faces
        assert len(source_faces) == len(native_faces(operand))
        for source in native_faces(operand):
            candidates = [candidate for face, candidate in source_faces if face.IsSame(source)]
            assert len(candidates) == 1
            source_id = candidates[0]["id"]
            expected_keys.add((port, source_id))
            rows = [
                row
                for row in ledger["sources"]
                if row["port"] == port and row["source_id"] == source_id
            ]
            assert len(rows) == 1
            row = rows[0]
            assert set(row) == {
                "port",
                "source_id",
                "deleted",
                "modified",
                "generated",
                "unchanged",
            }
            assert type(row["deleted"]) is bool
            assert row["deleted"] is bool(operation.builder.IsDeleted(source))
            for relation, history in (
                ("modified", list(operation.builder.Modified(source))),
                ("generated", list(operation.builder.Generated(source))),
                ("unchanged", [] if row["deleted"] else [source]),
            ):
                expected = {
                    candidate["id"]
                    for output, candidate in operation.faces
                    if any(output.IsSame(image) for image in history)
                }
                assert set(row[relation]) == expected
                assert len(row[relation]) == len(expected)
    actual_keys = [(row["port"], row["source_id"]) for row in ledger["sources"]]
    assert len(actual_keys) == len(expected_keys)
    assert set(actual_keys) == expected_keys
    return ledger


@pytest.mark.parametrize("second_action", ["split", "partial_delete"])
def test_split_then_split_or_partial_deletion_uses_current_fragment_handles(second_action):
    kernel, _, _, first = split_block()
    first_ledger = assert_exact_native_ledger(kernel, first)
    original = next(
        row for row in first_ledger["sources"] if row["source_id"] == "block/face/cap.end"
    )
    fragments = set(original["modified"])
    assert len(fragments) == 2
    assert all(identifier.startswith("snapshot:first:face:") for identifier in fragments)
    if second_action == "split":
        tool = box(kernel, "second_tool", 22, 2, x=-1, y=9, z=8, length=4)
    else:
        tool = box(kernel, "second_tool", 11, 22, x=-1, y=-1, z=6, length=6)
    second = kernel.cut(first, tool)
    topology = kernel.topology(second, "second", "", {})
    ledger = assert_exact_native_ledger(kernel, second)
    fragment_rows = [
        row for row in ledger["sources"] if row["port"] == "base" and row["source_id"] in fragments
    ]
    assert len(fragment_rows) == 2
    assert not any(row["source_id"] == "block/face/cap.end" for row in ledger["sources"])
    if second_action == "split":
        assert all(not row["deleted"] and len(row["modified"]) == 2 for row in fragment_rows)
        descendants = {identifier for row in fragment_rows for identifier in row["modified"]}
        assert len(descendants) == 4
        assert kernel.inspect(second)["volume"] == pytest.approx(3808)
    else:
        deleted = next(row for row in fragment_rows if row["deleted"])
        retained = next(row for row in fragment_rows if not row["deleted"])
        assert deleted["modified"] == deleted["generated"] == deleted["unchanged"] == []
        assert retained["modified"] == retained["generated"] == []
        assert len(retained["unchanged"]) == 1
        descendants = set(retained["unchanged"])
        assert kernel.inspect(second)["volume"] == pytest.approx(3140)
    assert all(
        row["id"].startswith("snapshot:second:face:")
        and row["provenance"]["semantic_status"] != "stable"
        for row in topology
        if row["id"] in descendants
    )
    assert kernel.inspect(second)["valid"]


@pytest.mark.parametrize("z,length,relation", [(-1, 12, "modified"), (5, 5, "unchanged")])
@pytest.mark.parametrize("typed_lineage", [False, True])
def test_tool_claims_use_actual_output_handles_without_changing_stable_ids(
    z, length, relation, typed_lineage
):
    kernel = OCPKernel(cut_tool_lineage=typed_lineage)
    base = box(kernel, "block", 20, 20)
    tool = kernel.extrude(kernel.circle(2, 10, 10, z), length)
    kernel.topology(tool, "drill", "", {})
    cut = kernel.cut(base, tool)
    topology = kernel.topology(cut, "cut", "", {})
    before = copy.deepcopy(topology)
    ledger = assert_exact_native_ledger(kernel, cut)
    tool_rows = [row for row in ledger["sources"] if row["port"] == "tool"]
    assert len(tool_rows) == 3
    wall = next(row for row in tool_rows if row["source_id"] == "drill/face/side.circle")
    assert not wall["deleted"] and len(wall[relation]) == 1
    wall_id = wall[relation][0]
    assert wall_id == (
        "drill/face/side.circle"
        if typed_lineage
        else next(row["id"] for row in topology if row["role"] == "cut.wall")
    )
    assert any(row["deleted"] for row in tool_rows)
    source_face = next(
        face
        for face, candidate in kernel._operations[id(tool)].faces
        if candidate["id"] == wall["source_id"]
    )
    output_face = next(
        face for face, candidate in kernel._operations[id(cut)].faces if candidate["id"] == wall_id
    )
    assert source_face.Orientation() != output_face.Orientation()
    assert topology == before
    assert kernel.topology(cut, "cut", "", {}) == before
    # Receipts are detached data, not mutable aliases into native topology.
    ledger["sources"].clear()
    assert assert_exact_native_ledger(kernel, cut)["sources"]


@pytest.mark.parametrize("deleted", [False, True])
def test_overlapping_builder_relations_are_independent(monkeypatch, deleted):
    kernel, base, _, cut = split_block()
    operation = kernel._operations[id(cut)]
    original_builder = operation.builder
    source = next(
        face
        for face, candidate in kernel._operations[id(base)].faces
        if candidate["id"] == "block/face/cap.start"
    )
    assert any(source.IsSame(face) for face, _ in operation.faces)

    class OverlappingHistory:
        """Instrument real native faces to exercise overlapping history claims."""

        def Modified(self, face):
            return [source] if face.IsSame(source) else original_builder.Modified(face)

        def Generated(self, face):
            return [source] if face.IsSame(source) else original_builder.Generated(face)

        def IsDeleted(self, face):
            return deleted if face.IsSame(source) else original_builder.IsDeleted(face)

    monkeypatch.setattr(operation, "builder", OverlappingHistory())
    ledger = kernel.cut_ancestry(cut)
    row = next(row for row in ledger["sources"] if row["source_id"] == "block/face/cap.start")
    assert row["modified"] == row["generated"] == ["block/face/cap.start"]
    assert row["unchanged"] == ([] if deleted else ["block/face/cap.start"])
    assert row["deleted"] is deleted


def test_reordered_current_catalogs_do_not_turn_positions_into_identity():
    kernel, _, _, first = split_block()
    tool = box(kernel, "second_tool", 22, 2, x=-1, y=9, z=8, length=4)
    second = kernel.cut(first, tool)
    kernel.topology(second, "second", "", {})
    original = kernel.cut_ancestry(second)
    renamed = {}
    for shape in (first, second):
        operation = kernel._operations[id(shape)]
        operation.faces.reverse()
        for index, (_, candidate) in enumerate(operation.faces):
            if candidate["id"].startswith("snapshot:"):
                replacement = f"snapshot:relabeled_{id(shape)}:face:{index}"
                renamed[candidate["id"]] = replacement
                candidate["id"] = replacement
    current = assert_exact_native_ledger(kernel, second)
    expected = copy.deepcopy(original)
    for row in expected["sources"]:
        row["source_id"] = renamed.get(row["source_id"], row["source_id"])
        for relation in ("modified", "generated", "unchanged"):
            row[relation] = [renamed.get(identifier, identifier) for identifier in row[relation]]
    assert current == expected


@pytest.mark.parametrize(
    "missing",
    [
        "base_catalog",
        "tool_catalog",
        "output_catalog",
        "source_face",
        "source_operation",
        "output_duplicate_face",
        "output_duplicate_id",
        "catalog_budget",
    ],
)
def test_missing_or_ambiguous_native_mapping_fails_closed(missing):
    kernel, base, tool, cut = split_block()
    operations = kernel._operations
    if missing.endswith("_catalog"):
        shape = {"base_catalog": base, "tool_catalog": tool, "output_catalog": cut}[missing]
        operations[id(shape)].faces = []
    elif missing == "source_face":
        operations[id(base)].faces.pop()
    elif missing == "source_operation":
        del operations[id(tool)]
    elif missing == "output_duplicate_face":
        operations[id(cut)].faces[-1] = operations[id(cut)].faces[0]
    elif missing == "output_duplicate_id":
        operations[id(cut)].faces[-1][1]["id"] = operations[id(cut)].faces[0][1]["id"]
    else:
        operations[id(base)].faces = [operations[id(base)].faces[0]] * 200_001
    with pytest.raises(KernelError, match="Cut ancestry"):
        kernel.cut_ancestry(cut)


def test_only_ordinary_cut_has_a_ledger():
    kernel, base, tool, _ = split_block()
    profile = kernel.rectangle(2, 2)
    moved = kernel.transform(base, x=1)
    patterned = kernel.linear_cut_pattern(base, tool, 2, dx=5)
    for shape in (base, tool, profile, moved, patterned, base.Located(base.Location())):
        assert kernel.cut_ancestry(shape) is None
