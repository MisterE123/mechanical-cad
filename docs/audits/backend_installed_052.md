# Delivered 0.5.2 compatibility-safety preview

Verification-only receipt, 2026-10-17. This documentation does not alter any
delivered archive. The release is the exact source commit
`df65fb422ca56dafbd217b4251d453a3a863f982`.

## Artifact identity

| Artifact | SHA-256 |
| --- | --- |
| Qualified handoff ZIP | `d644fbce66b843047a6cb3e3cd775c1af8517a7ff82e3f22ce3888b710d1971f` |
| Installable add-on ZIP | `da194f80c9e673f0e93f697e9649a31b1e5737036e7464f7a4f16dc797d89ada` |
| Source ZIP | `6476bd0f9556cdfb198956e70befc9e0f8985957d25144b5d3819ca43b32a7f9` |
| Full local Git history bundle | `b3bbb1bb6450fe5d7b4885f777f5f32f6f6047f508cf4fdf623283f34de89258` |
| Exact installed GUI evidence ZIP | `a4bde8d15207d57b2d5e1750c13b067cab3a51375464c690e9646456a650120f` |

The handoff ZIP is 15,438,157 bytes. Its `distribution/` contains the three
distribution artifacts and their release manifest. Its `evidence/` retains
the automated logs, immutable source maps, independent reviews, installed GUI
report, actual screenshots, saved examples and STEP/STL outputs.

## Automated and independent evidence

- Functional source `61b59fc889b6a772cd24abc662ae0a6384543de0`: Ruff/format,
  4,018 pytest cases plus 19,597 subtests, 45 serial native Blender gates and
  both actual process-exit gates passed.
- Independent exact-source audit: 117 owner-bypass checks over ten sections and
  all nine action families, plus 67 cleanup/retained-outline correction checks.
  All source and aggregate log hashes were independently verified.
- Release metadata changed only the two runtime version literals. All other
  bytes across the 105 runtime Python modules match that functional source.
  The release's 931 source files and 607 packaged/installed add-on files match
  their exact commit. No dependencies or native libraries are bundled.
- Exact release source: Ruff/format, 143 focused identity/version tests, complete
  4,018-case/19,597-subtest pytest rerun, interpreter/source identity and native
  cyclic/acyclic controls, and isolated exact-ZIP installation harness passed.
  Independent review verified these receipts and their source correspondence.

## Actual installed GUI and explicit limits

Ordinary mouse/keyboard input installed the exact ZIP in a fresh profile and
exercised source-root changes, missing-receipt rejection, A→B→A revocation,
explicit recovery, Rectangle/General Cancel and Finish, relation Undo/Redo,
STEP/STL export, Assembly replay/check and genuine second-process save/reopen.
Canonical Part/Assembly and the suspended raw draft survived byte-exact. Saved
reports and DoF remained historical until explicit fresh work. The 20 read-only
post-review assertions independently reproduced; final source hashes were
unchanged and both GUI processes exited normally.

The GUI matrix is bounded: direct Rectangle rejection used old 0.5.1; direct
Part/geometry/export rejection used old 0.5.0. General and Assembly replay/source
capture used both. Assembly Check with a stale display stopped at its visible
replay-required guard, not a native legacy-check round trip. No GUI result is
claimed for the other action×version pairings, alternate-Python/timeout/tolerance
ABA, Assembly pending cancellation or exhaustive redraw instrumentation. The
sealed `GUI_REVIEW.md` records all artifact naming corrections and limits.

This release's claim is mixed-backend rejection and revocation/recovery of
current evidence within the tested boundary. It does not claim arbitrary
malicious-backend resistance, full CAD completion or engineering certification.
The runtime is Linux x86_64, Blender 5.2.2 LTS and CPython 3.12 with the pinned
sidecar dependencies. Other platforms and Blender versions are unqualified.

Arc profiles, result version 3, arc editing journals and arc UI remain unavailable.
Their next slice requires a separate reviewed core/service boundary before UI
exposure. The original 0.4, 0.5 and 0.5.1 deliveries remain immutable.
