"""Historical inverse inputs never replace current mass/resource source checks."""

import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_current_primitive_resource_mutation_is_not_hidden_by_history(tmp_path, monkeypatch):
    import test_arc_profile_incidence as incidence

    current = ROOT / "src/mechanical_cad/arc_profile_primitives.py"
    raw = current.read_bytes()
    old = b"MAX_OPERATIONS = 200_000\n"
    assert raw.count(old) == 1
    changed = tmp_path / current.relative_to(ROOT)
    changed.parent.mkdir(parents=True)
    changed.write_bytes(raw.replace(old, b"MAX_OPERATIONS = 200_001\n"))
    # All inverse inputs remain the sealed archive. Only the live resource file
    # resolves through this root, and must reject its changed hard ceiling.
    monkeypatch.setattr(incidence, "ROOT", tmp_path)
    with pytest.raises(AssertionError, match="primitive bytes changed"):
        incidence.test_104_runtime_files_and_primitives_unchanged_with_reviewed_additive_kernel()


def test_mass_tail_extracts_current_kernel_not_the_historical_copy(tmp_path, monkeypatch):
    import test_arc_profile_native_mass_observations as mass

    assert mass.KERNEL == ROOT / "src/mechanical_cad/kernel_ocp.py"
    raw = mass.KERNEL.read_bytes()
    old = b'"raw_face_empirical_area"'
    assert raw.count(old) == 1
    current = tmp_path / "current_kernel.py"
    current.write_bytes(raw.replace(old, b'"current-kernel-routing-probe"'))
    monkeypatch.setattr(mass, "KERNEL", current)
    code = mass.mass_tail("sector_profile")

    def constants(code):
        for item in code.co_consts:
            if isinstance(item, types.CodeType):
                yield from constants(item)
            elif isinstance(item, str):
                yield item

    assert "current-kernel-routing-probe" in set(constants(code))


def test_inventory_collectors_read_current_kernel(monkeypatch):
    import test_arc_profile_native_inventory as inventory

    current = ROOT / "src/mechanical_cad/kernel_ocp.py"
    assert inventory.KERNEL == current
    reads = []

    class ObservedCurrentKernel:
        def read_text(self):
            reads.append(current)
            return current.read_text()

        def __str__(self):
            return str(current)

    monkeypatch.setattr(inventory, "KERNEL", ObservedCurrentKernel())
    collectors = inventory.collectors.__wrapped__()
    assert reads == [current]
    assert callable(collectors.edge_record)


def test_historical_mass_inverse_keeps_current_evidence_comparator(tmp_path, monkeypatch):
    import test_arc_profile_native_mass_observations as mass

    assert mass.EVIDENCE == ROOT / "src/mechanical_cad/arc_profile_native_evidence.py"
    current = tmp_path / "current_evidence.py"
    current.write_bytes(mass.EVIDENCE.read_bytes() + b"\n# unreviewed current mutation\n")
    monkeypatch.setattr(mass, "EVIDENCE", current)
    calls = []
    original = mass._assembly_step_bytes

    def tracked(root, relative):
        calls.append(root)
        return original(root, relative)

    monkeypatch.setattr(mass, "_assembly_step_bytes", tracked)
    with pytest.raises(AssertionError):
        mass.test_every_original_kernel_and_mass_comparator_byte_matches_snapshot5()
    assert calls == [mass.historical_runtime_root()]
    assert calls[0] != ROOT
