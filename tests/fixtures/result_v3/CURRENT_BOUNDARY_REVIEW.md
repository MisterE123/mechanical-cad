# Historical result-v3 preservation and current boundary policy

The original `protected_30383a1.json` and dispatch fixture hashes are unchanged.
They record a historical byte-preservation guarantee, not a permanent prohibition
on later documented modeling features. The old combined tests accidentally used
those hashes against an evolving checkout and stopped before examining current
import and ownership boundaries.

## Historical inputs

`result_history_root()` starts with the separately sealed `db8cac4` source fixture.
It adds only the 527 non-Python baseline assets missing from that fixture, after
checking their exact original size and SHA-256 from `protected_30383a1.json`.
Those assets are byte-identical in the current checkout. No current Python module
is copied into historical reconstruction. Existing inverses then prove all 637
protected baseline files and three dispatch originals unchanged. Mutations start
from a positively verified original before checking rejection.

This historical check does not qualify current runtime behavior or safety.
Historical UI/import assertions also use only reconstructed historical inputs.

## Current inputs

`current_boundary_policy.json` is an explicit, hash-pinned review artifact for
source `a15bdbf107116b8ebd6f5f2a547144b6eef3a225`. Tests never regenerate it from the
working tree, Git history, or test output. It records:

- All 249 runtime paths added since the old 640-file baseline, each with its actual
  introduction commit and subject. Introduction provenance is not a qualification
  claim. Exactly the baseline plus this finite set must exist today, including
  non-Python assets; missing paths, extra files and basename impostors reject.
- The exact 40-module current dependency map into the result-v3/authoring leaves,
  now scanned across all add-on Python files, including newly introduced owners
  and the leaves themselves. Twenty-two original importer mappings are unchanged.
  The shared validation extraction relocates the old command import to
  `general_sketch_validation`, rather than exempting it.
- The exact thirteen-class current General viewport registry. Missing, extra,
  duplicate, undefined and dynamically constructed registrations reject.

The path provenance covers 106 introduction commits. Representative documented
families are:

| Family | Representative commits | Current description |
| --- | --- | --- |
| Arc result/authoring leaves | `ce5b50b`, `bef37be`, `cc130e6` | Architecture and integrated modeling |
| Connected solid histories and analytic regions | `36daecd`, `9305237`, `ff8b014` | `INTEGRATED_MODELING.md` |
| Edge picking, projection and support ancestry | `538f1a8`, `77e557a`, `0e27210` | Integrated modeling and topology regression documentation |
| Guarded Windows runtime | `e1dae075`, `270aa795` | Runtime/package architecture |
| Stable annotations, fillets and restoration | `fa62ccd`, `ad11192`, `241b85e` | `RELEASE_125.md`, `RELEASE_126.md`, `RELEASE_127.md` |
| Assembly source/insertion/mating previews | `1630f4f`, `088d185`, `e7c2e3e` | Assembly preview workflow documentation |
| Dependency-cycle refactoring | `505ac3c`, `aafb2bf`, `0bd086d` | Architecture; preserved APIs and explicit owner registries |
| Semantic glyphs | `15b0524`, `07ce234`, `c794cf6` | Modeling palette/UI documentation; 82 added glyph assets |

The seven newer General entries come from principal planes/normal view (`3324be4`),
attached face sketches (`7b6e5e3`), copied face planes (`34c5e17`), projection
(`979eda1`), corner fillets (`5bfb6db`, completed by `fa62ccd`), and guarded removal
(`ad11192`). The original six entries remain explicitly listed.

Static dependency checks retain ordinary import aliases and reject unreviewed
import-loader aliases/dynamic calls. The only current dynamic import is the exact
existing `registration` call for `.standalone_launch_constants`; it grants no
result-v3 import exemption. These static checks are not a general Python sandbox.
AST facts are cached only under exact immutable source-byte keys; every changed
mutation is parsed and checked independently. Independent architecture,
guarded-owner, schema and native geometry tests still
establish their respective current behavior contracts.

## Narrow legacy sketch-output extension

The original `_sketch_output` span hash is retained. Commit `36daecd` added exactly
the `ProfileRegions` import and the native `kernel.region_profile` branch needed
for documented regions/holes. The current test requires those exact two additions
once, removes only those bytes, and checks the unchanged original span hash.
Negative controls reject a missing branch, changed kernel call or boundary IDs,
wrong import, and unrelated function edits. This is not a generic AST filter.

No production files change here. A new legitimate feature must update the
explicit relevant policy after review; future additions are not automatically
admitted just because they exist in the checkout.
