# Stored parameter context in local dimension edits

The local-edit choices for primitive circle radius, direct extrusion depth and
linked Boolean-tool depth show the referenced parameter's stored definition.
Numeric definitions say `Stored value` with mm; strings say `Stored expression`,
not an evaluated result. This reads the original canonical document, never a
pending shared-edit widget. It adds no evaluator, backend request or model change.

The hint is bounded to70 characters with an ellipsis for longer definitions;
the Shared parameter tab still exposes the full editable definition and usage.
This is context, not a live geometric preview or validation receipt.

Verification:38 focused tests pass, including six draw-body cases spanning all
three branches with numeric/formula sources and poisoned pending values. Ruff
passes. Actual Blender5.2.2 GUI screenshots cover all3 branches. A pending shared
value100 did not replace the canonical10 cue after switching back to local.
Cancel left canonical document bytes, active output and volume unchanged.
This is source-only; frozen1.28 and existing qualification limits are unchanged.
