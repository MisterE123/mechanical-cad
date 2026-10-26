"""Valid ruled duct Boolean survives optional OCCT seam-cleanup failure."""

import math

import pytest

from mechanical_cad.kernel_ocp import KernelError, OCPKernel


def duct(kernel, inset=0):
    return kernel.loft_sections(
        [
            kernel.circle(r - inset, x=50, y=35, z=z)
            for r, z in [(24, -1), (24, 5), (20, 24), (16, 43)]
        ],
        ruled=1,
    )


def test_ruled_duct_plate_union_and_downstream_airway_exact_manifold(tmp_path):
    k = OCPKernel()
    plate = k.extrude(k.rectangle(100, 70), 3.6)
    outer = duct(k)
    joined = k.union(plate, outer)
    expected = (
        25200
        + math.pi
        * (24**2 * 6 + 19 / 3 * (24**2 + 24 * 20 + 20**2) + 19 / 3 * (20**2 + 20 * 16 + 16**2))
        - math.pi * 24**2 * 3.6
    )
    assert k.inspect(joined)["volume"] == pytest.approx(expected, rel=1e-8)
    result = k.cut(joined, duct(k, 2))
    check = k.manufacturing_check(result)
    assert check["brep"]["valid"] and check["brep"]["solids"] == 1
    assert check["mesh"]["watertight"] and check["mesh"]["vertex_manifold"]
    assert check["mesh"]["consistently_oriented"]
    assert check["brep"]["volume"] == pytest.approx(29492.672201865084, rel=1e-8)
    k.export_step(result, str(tmp_path / "duct.step"))
    k.export_stl(result, str(tmp_path / "duct.stl"))


def test_legacy_simple_cleanup_and_disconnected_refusal_remain():
    k = OCPKernel()
    a = k.extrude(k.rectangle(10, 10), 10)
    b = k.extrude(k.rectangle(10, 10, x=5), 10)
    joined = k.union(a, b)
    assert k.inspect(joined)["volume"] == pytest.approx(1500)
    assert k.inspect(joined)["faces"] == 6
    assert k.inspect(k.intersection(a, b))["volume"] == pytest.approx(500)
    far = k.extrude(k.rectangle(10, 10, x=50), 10)
    with pytest.raises(KernelError, match="one connected solid"):
        k.union(a, far)


def test_cleanup_rebuild_retains_only_proven_source_identity():
    from mechanical_cad.engine import regenerate
    from mechanical_cad.loft_sections import set_sections
    from mechanical_cad.model import Document

    features = [
        dict(id="p", kind="sketch_rectangle", params=dict(width=100, height=70)),
        dict(id="plate", kind="extrude", params=dict(length=3.6), inputs=dict(profile="p")),
    ]
    for i, (radius, z) in enumerate([(24, -1), (24, 5), (20, 24), (16, 43)]):
        features.append(
            dict(id=f"s{i}", kind="sketch_circle", params=dict(radius=radius, x=50, y=35, z=z))
        )
    loft = dict(id="duct", kind="loft", params=dict(ruled=1))
    set_sections(loft, [f"s{i}" for i in range(4)])
    features.extend([loft, dict(id="joined", kind="union", inputs=dict(base="plate", tool="duct"))])
    doc = Document.from_dict(
        dict(
            schema_version=1,
            id="cleanup",
            name="Cleanup repro",
            units="mm",
            parameters={},
            features=features,
            active_feature="joined",
        )
    )
    k = OCPKernel()
    r = regenerate(doc, k, result_version=3)
    assert r.ok, r.result
    row = r.result["features"][-1]
    stable = [f for f in row["topology"] if f["provenance"]["semantic_status"] == "stable"]
    assert stable
    assert all(f["feature_id"] == "plate" for f in stable)
    # Loft surfaces have no persistent semantic role even after recovery.
    assert not any(f["feature_id"] == "duct" for f in stable)
    k.face_circle(r.shapes["joined"], "plate/face/side.x_min", 1)


def brep_bytes(shape):
    from io import BytesIO

    from OCP.BRepTools import BRepTools

    stream = BytesIO()
    BRepTools.Write_s(shape, stream)
    return stream.getvalue()


def test_real_cleanup_failure_does_not_mutate_operands_or_retry_sources(monkeypatch):
    import mechanical_cad.kernel_ocp as module

    k = OCPKernel()
    plate = k.extrude(k.rectangle(100, 70), 3.6)
    outer = duct(k)
    originals = (plate, outer)
    before = [brep_bytes(shape) for shape in originals]
    native = module.BRepAlgoAPI_Fuse
    attempts, failures = [], []

    class TrackingFuse:
        def __init__(self, a, b):
            assert [brep_bytes(shape) for shape in originals] == before
            assert not a.IsSame(plate) and not b.IsSame(outer)
            if attempts:
                assert not a.IsSame(attempts[0][0]) and not b.IsSame(attempts[0][1])
                assert [brep_bytes(a), brep_bytes(b)] == attempts[0][2]
            attempts.append((a, b, [brep_bytes(a), brep_bytes(b)]))
            self.native = native(a, b)

        def __getattr__(self, name):
            return getattr(self.native, name)

        def SimplifyResult(self, *args):
            try:
                self.native.SimplifyResult(*args)
            except module.Standard_Failure:
                failures.append(True)
                raise

    monkeypatch.setattr(module, "BRepAlgoAPI_Fuse", TrackingFuse)
    result = k.union(plate, outer)
    assert failures == [True] and len(attempts) == 2
    assert k.inspect(result)["valid"]
    assert [brep_bytes(shape) for shape in originals] == before


@pytest.mark.parametrize(
    "kind,factory", [("union", "BRepAlgoAPI_Fuse"), ("intersection", "BRepAlgoAPI_Common")]
)
@pytest.mark.parametrize(
    "mode",
    [
        "recover",
        "retry_not_done",
        "retry_build_error",
        "initial_build_error",
        "unexpected_cleanup",
        "disconnected",
    ],
)
def test_cleanup_recovery_is_bounded_and_preserves_failure_gates(monkeypatch, kind, factory, mode):
    import mechanical_cad.kernel_ocp as module

    k = OCPKernel()
    a = k.extrude(k.rectangle(10, 10), 10)
    b = k.extrude(k.rectangle(10, 10, x=50 if mode == "disconnected" else 5), 10)
    before = [brep_bytes(a), brep_bytes(b)]
    native = getattr(module, factory)
    attempts = []

    class Injected:
        def __init__(self, left, right):
            self.number = len(attempts)
            attempts.append(self)
            self.native = native(left, right)

        def __getattr__(self, name):
            return getattr(self.native, name)

        def Build(self):
            if (mode == "initial_build_error" and self.number == 0) or (
                mode == "retry_build_error" and self.number == 1
            ):
                raise module.Standard_Failure("build failed")
            self.native.Build()

        def IsDone(self):
            return False if mode == "retry_not_done" and self.number == 1 else self.native.IsDone()

        def SimplifyResult(self, *args):
            if mode == "unexpected_cleanup":
                raise RuntimeError("unexpected cleanup")
            raise module.Standard_Failure("cleanup failed")

    monkeypatch.setattr(module, factory, Injected)
    if mode == "recover":
        result = getattr(k, kind)(a, b)
        assert k.inspect(result)["volume"] == pytest.approx(1500 if kind == "union" else 500)
    else:
        error = (
            module.Standard_Failure
            if "build_error" in mode
            else RuntimeError
            if mode == "unexpected_cleanup"
            else KernelError
        )
        with pytest.raises(error):
            getattr(k, kind)(a, b)
    assert len(attempts) == (1 if mode in {"initial_build_error", "unexpected_cleanup"} else 2)
    assert [brep_bytes(a), brep_bytes(b)] == before


@pytest.mark.parametrize("history", ["missing", "split", "generated"])
def test_copy_ancestry_never_promotes_unresolved_boolean_history(history):
    import mechanical_cad.kernel_ocp as module

    k = OCPKernel()
    a = k.extrude(k.rectangle(10, 10), 10)
    k.topology(a, "a", "extrude", {})
    b = k.extrude(k.rectangle(10, 10, x=5), 10)
    result = k.union(a, b)
    operation = k._operations[id(result)]
    original = next(
        face
        for face, candidate in k._operations[id(a)].faces
        if candidate["id"] == "a/face/side.x_min"
    )
    copied = next(image for source, image in operation.boolean_copies if source.IsSame(original))
    if history == "missing":
        operation.boolean_copies = [
            (source, image)
            for source, image in operation.boolean_copies
            if not source.IsSame(original)
        ]
        with pytest.raises(KernelError, match="unresolved copy ancestry"):
            k.topology(result, "joined", "union", {})
        return
    native = operation.builder
    output_faces = module._subshapes(result, module.TopAbs_FACE)

    class History:
        def __getattr__(self, name):
            return getattr(native, name)

        def Modified(self, face):
            if face.IsSame(copied):
                return output_faces[:2] if history == "split" else []
            return native.Modified(face)

        def Generated(self, face):
            if face.IsSame(copied):
                return output_faces[:1] if history == "generated" else []
            return native.Generated(face)

        def IsDeleted(self, face):
            return True if face.IsSame(copied) else native.IsDeleted(face)

    operation.builder = History()
    topology = k.topology(result, "joined", "union", {})
    assert not any(
        row["id"] == "a/face/side.x_min" and row["provenance"]["semantic_status"] == "stable"
        for row in topology
    )


@pytest.mark.parametrize("mode", ["missing", "multiple", "unchanged"])
def test_unproven_native_copy_mapping_is_rejected_before_boolean(monkeypatch, mode):
    import mechanical_cad.kernel_ocp as module

    native = module.BRepBuilderAPI_Copy

    class Copy:
        def __init__(self, *args):
            self.native = native(*args)

        def __getattr__(self, name):
            return getattr(self.native, name)

        def Modified(self, face):
            images = list(self.native.Modified(face))
            return [] if mode == "missing" else images * 2 if mode == "multiple" else [face]

    monkeypatch.setattr(module, "BRepBuilderAPI_Copy", Copy)
    k = OCPKernel()
    a = k.extrude(k.rectangle(10, 10), 10)
    b = k.extrude(k.rectangle(10, 10, x=5), 10)
    before = [brep_bytes(a), brep_bytes(b)]
    with pytest.raises(KernelError, match="unresolved face history"):
        k.union(a, b)
    assert [brep_bytes(a), brep_bytes(b)] == before
