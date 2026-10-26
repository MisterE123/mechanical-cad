"""Native-free exact-history naming, not geometric correspondence."""

import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.blend_selection import selected_surface_role, unique_generated_images


class Shape:
    def __init__(self, identity):
        self.identity = identity

    def IsSame(self, other):
        return self.identity == other.identity


def test_pair_names_are_order_independent_unambiguous_and_bounded():
    pair = ["a/face/side.x", "b/face/cap.end"]
    role = selected_surface_role(pair, 2)
    assert role == selected_surface_role(pair[::-1], 64)
    assert len(role) == len("blend.surface.") + 64
    assert selected_surface_role(pair, 1) == "blend.surface"
    assert selected_surface_role(["a|b", "c"], 2) != selected_surface_role(["a", "b|c"], 2)
    assert selected_surface_role(["a", "b"], 2) != selected_surface_role(["a", "c"], 2)
    package = types.ModuleType("blend_identity_client")
    package.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    sys.modules[package.__name__] = package
    client = importlib.import_module(package.__name__ + ".topology_evidence")
    assert client._blend_surface_role(pair, 2) == role
    feature = {"kind": "fillet", "edge_pairs": [pair, ["a", "b"]]}
    assert role in client._roles(feature, {})
    assert "blend.surface" not in client._roles(feature, {})


def test_disjoint_generated_faces_follow_sources_not_output_order():
    e1, e2, f1, f2 = map(Shape, ("e1", "e2", "f1", "f2"))
    claims = [(e2, [f2]), (e1, [Shape("f1")])]
    assert list(unique_generated_images([e1, e2], [f2, f1], claims)) == [(e1, f1), (e2, f2)]


@pytest.mark.parametrize("failure", ["missing", "split", "merged", "vertex", "face", "duplicate"])
def test_ambiguous_histories_never_choose_a_face(failure):
    edge, output, other = map(Shape, ("edge", "output", "other"))
    claims = [(edge, [output])]
    outputs = [output]
    if failure == "missing":
        claims = [(edge, [])]
    elif failure == "split":
        outputs.append(other)
        claims = [(edge, outputs)]
    elif failure == "duplicate":
        claims.append((Shape("edge"), [output]))
    else:
        claims.append((Shape(failure), [Shape("output")]))
    assert list(unique_generated_images([edge], outputs, claims)) == []
