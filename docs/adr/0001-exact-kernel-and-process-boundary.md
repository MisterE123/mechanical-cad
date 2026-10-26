# ADR 0001: Exact B-rep kernel in an isolated Python sidecar

Status: accepted for the experimental 0.1 slice, 2026-10-16.

## Context

Blender is a strong host for viewport interaction, object organisation and visual
inspection, but its editable polygon mesh is not a parametric mechanical B-rep
kernel. The supplied cloud Blender has Python 3.13, while the available development
interpreter is Python 3.12. Injecting arbitrary native wheels into Blender's Python
would couple installation, versioning and crash risk to the host.

## Decision

Use Open CASCADE via the pinned `cadquery-ocp-novtk==8.0.1.1.0` wheel in a separate
CPython environment. Use a thin adapter rather than importing CadQuery/build123d
for the first slice, to keep the dependency and model/history surface explicit.
The novtk distribution avoids bringing a second rendering stack into Blender.
Use bounded JSON over a short-lived subprocess. Keep the Blender UI independent
of the native binding and authoritative on-screen unit conversion explicit.

## Consequences

- Exact solids and STEP interoperability are available; display remains mesh-based.
- Blender/native-library ABI mismatches do not require modifying Blender Python.
- Setup needs a separate interpreter and package install. Initial operations are
  synchronous with a timeout; a cancellable worker is a future usability gate.
- The adapter and persisted schema remain ours; no promise is made that OCCT's
  operation history solves arbitrary persistent naming.
- More supported operations require more kernel-level regression fixtures, not
  only new UI buttons.

Alternatives: Blender mesh-only editing cannot meet the canonical exact-solid
requirement. Bundled CAD libraries inside Blender increase dependency/ABI risk.
A full external CAD application bridge introduces a larger external application
and state boundary before the first feature workflow is proven.
