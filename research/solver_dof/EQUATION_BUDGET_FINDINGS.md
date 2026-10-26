# Historical native equation-budget experiment

This is retained research context, **not a 0.5.1 feature/resource-limit change**.
The original arc investigation exposed native DoF corruption in a large case;
the later line/coincidence minimizations prove the released 0.5 adapter is also
affected. The 0.5.1 correction adds no arcs or v3 schema and does not depend on
these proposed arc limits.

## Bounded resource probes

The standalone harness retains 15 original cases with subprocess isolation and
a 20-second timeout per case. It proposes a research-only structural upper bound:

`2*(fixed + coincident) + horizontal + vertical + distance + radius + arcs`

The research ceilings are 256 points, 512 active scalars, 256 total curves,
512 authored constraints and 1024 equations. Counts precede exact authored
relation deduplication. An arc contributes one intrinsic radial-equality equation
and no scalar beyond its referenced point coordinates.

- 1023/1024-equation structured examples finish under pinned slvs 3.2, including
  512 active scalars and 256 arcs. This is execution evidence, not a proof of
  arbitrary-system speed, accuracy, rank or convergence.
- 1025/1280 candidates reject at the research gate before importing/calling slvs.
  This is the harness gate, not evidence that production adopts that policy.
- Complementary arcs alone produce `REDUNDANT_OKAY / 5`; a center anchor and
  radius leave 2 DoF. The incompatible radius case is inconsistent and names
  the authored radius handle, not a fabricated removable intrinsic constraint.
- Repeated coincidence equations can produce false zero DoF; exact authored
  deduplication restores the specific repeated-pair control to 255 DoF.

## Distinct cycle result

With 64 groups of four coincident points and all six distinct pairwise relations
per group, 128 free coordinates remain. The 256 complementary arcs use the same
three point groups and supply one independent radial equation, leaving **127**
DoF. Native output is `REDUNDANT_OKAY / 0`, with no failed authored handles.
Distinct pairs survive exact deduplication. A legal 0–512 count range does not
catch this error. A successful harness assertion here intentionally reproduces
that defect; it does not certify the result.

See `equation_budget_evidence.json` for all input counts, raw returns, fixed-point
residuals, failed IDs, timing and resource metrics. Linux peak RSS is KiB; the
portable field is named `max_rss_native_units` because other platforms differ.
The `resource` module is optional outside POSIX; no non-Linux qualification was
performed. All **18/18** bounded harness checks pass in this capture.

The earlier scratch probe additionally evaluated a separate 89-case arc numeric
policy and embedded two entire adapter matrices. Those unrelated arc-policy data
are deliberately not a prerequisite here. The retained harness preserves the
15 native budget cases and separates the released/guarded adapter evidence.
Original scratch file hashes and transformations are in `provenance.json`.
See [the DoF findings and reproduction commands](README.md) for the bounded
active-coordinate guard, fixed-group distinction and broader limitations.
