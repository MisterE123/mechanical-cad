"""Finite bundled Windows default; saved values and currentness stay authoritative."""

import ast
import types

import pytest
from test_windows_live_capture import runtime, windows_host
from test_windows_runtime import ROOT, Fixture, selection


@pytest.mark.parametrize(
    "platform,package,expected",
    [
        ("win32", "bl_ext.private.mechanical_cad", 240.0),
        ("linux", "bl_ext.private.mechanical_cad", 60.0),
        ("darwin", "bl_ext.private.mechanical_cad", 60.0),
        ("win32", "mechanical_cad_blender", 60.0),
        ("linux", "mechanical_cad_blender", 60.0),
    ],
)
def test_rna_declares_profile_default_without_writing_preferences(platform, package, expected):
    source = ROOT / "blender_addon/mechanical_cad_blender/properties.py"
    tree = ast.parse(source.read_bytes())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MCAD_Preferences")
    annotation = next(node for node in cls.body if isinstance(node, ast.AnnAssign) and node.target.id == "timeout_seconds")
    value = eval(
        compile(ast.Expression(annotation.annotation), str(source), "eval"),
        {"FloatProperty": lambda **kwargs: kwargs, "sys": types.SimpleNamespace(platform=platform),
         "__package__": package, "default_timeout_seconds": selection.default_timeout_seconds,
         "_backend_settings_changed": object()},
    )
    assert value["default"] == expected and value["min"] == 1 and value["max"] == 300


def test_omitted_windows_bundled_capture_uses_finite_default(monkeypatch):
    windows_host(monkeypatch)
    selected = selection.BackendSelection.capture_bundled(
        Fixture().policy(), generation=0, lifetime_id="default"
    )
    assert selected.timeout == 240 and selected.launch_environment() == {}


@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf")])
def test_explicit_invalid_timeout_never_becomes_a_default(monkeypatch, value):
    windows_host(monkeypatch)
    with pytest.raises(selection.SelectionError, match="finite"):
        selection.BackendSelection.capture_bundled(
            Fixture().policy(), value, generation=0, lifetime_id="invalid"
        )


def setup_runtime(monkeypatch, preferences):
    windows_host(monkeypatch)
    monkeypatch.setattr(runtime, "_preferences", lambda context: preferences)
    for name, value in dict(
        _BUNDLE_REQUIRED=True, _BUNDLE_ENABLED=True, _BUNDLE_POLICY=Fixture().policy(),
        _OBSERVED=None, _GENERATION=0, _LIFETIME="timeout-default", _INVALIDATE=None,
    ).items():
        monkeypatch.setattr(runtime, name, value)


@pytest.mark.parametrize("saved", [None, 60.0, 17.5, 180.0, 240.0, 300.0])
def test_live_capture_defaults_only_without_preferences_and_preserves_saved_values(monkeypatch, saved):
    preferences = None if saved is None else types.SimpleNamespace(timeout_seconds=saved, linear_deflection=0.1)
    before = None if preferences is None else vars(preferences).copy()
    setup_runtime(monkeypatch, preferences)
    selected = runtime.capture(object())
    assert selected.timeout == (240 if preferences is None else saved)
    assert runtime.assert_current(selected, object()) == selected
    assert (None if preferences is None else vars(preferences)) == before


def test_authored_timeout_replaces_default_and_aba_cannot_revive_old_selection(monkeypatch):
    preferences = types.SimpleNamespace(timeout_seconds=240.0, linear_deflection=0.1)
    setup_runtime(monkeypatch, preferences)
    old = runtime.capture(object())
    preferences.timeout_seconds = 60.0
    runtime.revoke("Authored timeout changed")
    assert runtime.capture(object()).timeout == 60
    assert not runtime.is_current(old, object())
    preferences.timeout_seconds = 240.0
    runtime.revoke("Authored timeout restored")
    assert runtime.capture(object()).timeout == 240
    assert not runtime.is_current(old, object())
