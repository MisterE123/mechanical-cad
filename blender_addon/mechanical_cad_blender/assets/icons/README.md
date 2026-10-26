# Mechanical CAD icon pack, next-version preview

Standalone offline assets. This folder does not change the current add-on,
stage1 baseline, or any installed Blender settings. It does not implement or
enable the actions pictured here.

## Contents

- `svg/`: 44 normalized, monochrome 24-unit SVGs using `currentColor`
- `png/dark/`: light ink (`#E8EAED`) on transparency, for dark surfaces
- `png/light/`: dark ink (`#202124`) on transparency, for light surfaces
- Both PNG families include 16, 24, 32, 48, and 64 pixel square images
- `manifest.json`: stable proposed action IDs, captions, plain hover descriptions,
  exact source and license, hashes, modifications, and generated file paths
- `review/contact_sheet_dark.png` and `contact_sheet_light.png`: actual-size
  16 / 24 / 32 px previews for semantic and contrast review
- `review/validation.json`: reproducible automated asset checks
- `vendor/google/`: Google's original source files and pinned provenance
- `original_geometry.json`: editable original mechanical vector geometry

20 common controls use official Google Material Symbols Outlined, weight 400,
fill 0, grade 0, optical size 24. 24 mechanical or format-specific controls are
original vector drawings. They avoid scissors for solid subtraction, preserve
closed-profile versus solid distinctions, and distinguish assembly motion from
sketch constraints.

## Integration contract

1. Wire only actions the implementation actually supports. Every manifest entry
   is `asset_only_unwired`; existence of an asset is never a capability claim.
2. Prefer the 32px PNG as the standard `bpy.utils.previews` image input and 64px
   for high-DPI surfaces. Assets must ship with the add-on, not load from Google
   Fonts at runtime. No network, font installation, or new dependency is needed
   when using these prebuilt PNGs.
3. Select the ink family against the actual panel background. Blender preview
   PNGs must not be assumed to automatically recolor with themes. Avoid tinting
   an already light/dark PNG a second time.
4. Use the action label as the operator name and the hover description as a
   starting `bl_description`. Preserve an accessible name even on icon-only
   buttons. Adapt hover text to real prerequisites, units, direction, and limits.
   For context-specific operators, generate that detail from current selection.
5. Keep dimensions, operand names, feature history, failure explanations,
   last-good/stale status, and verification evidence as visible text. Hover-only
   warnings are inadequate. An icon must not turn a failed/stale result into a
   success appearance.
6. Use visible `STEP` and `STL` captions on the respective export controls. The
   solid and mesh drawings help distinguish them, but shape alone is not a
   reliable way to communicate a file format. Pair unfamiliar constraints and
   mates with optional novice captions or a tool-name reveal.
7. Use `file.export` for a single format chooser, or `file.export_step` and
   `file.export_stl` for two explicit commands. Avoid placing all three side by
   side. Similarly, the generic check and passed status have different roles.
8. Preserve the source SVGs, manifest, NOTICE, and relevant licenses when
   packaging the assets. Apache-2.0 applies to the Google artwork; original
   artwork and tooling follow this GPL-3.0-or-later project.
9. Theme switching, preview collection registration/unregistration, tooltip
   display, enabled/disabled state, and high-DPI scale need actual Blender UI
   validation at integration time. This pack deliberately does not modify the
   add-on or claim those runtime checks have passed.

Operator hints are pointers to known stage1 names, not an auto-registration map.
IDs without operator hints are deliberate future UI proposals. Confirm the
semantics with the implementation owner before connecting them.

## Rebuild and verify offline

Requires Python 3, Pillow, and the locally installed official Inkscape renderer.
No network is used by either command.

```sh
python tools/build_assets.py
python tests/validate_assets.py
```

SVGs are rasterized to a 256px alpha mask and downsampled with Lanczos, then
recolored without changing alpha. This keeps theme geometry exactly identical.
The 24px Google optical outlines are also used at other sizes; the 16px copies
are usability fallbacks, not claims of manually pixel-hinted optical redesign.

## Verification boundaries

Automated checks cover dimensions, RGBA transparency, monochrome color, matching
alpha between themes, nonempty silhouettes, unique 32px pixel geometry,
self-contained SVGs, pinned Google source identity, manifest/hash/license
completeness, and foreground contrast on the review backgrounds. They cannot
prove that a new user will identify every operation without a tooltip.

The initial visual review simplified the circle radius marker to distinguish it
from regenerate/history and replaced the fixed-mate center mark with a padlock
to distinguish it from clearance. Retain these distinctions in future edits.

## Official sources

- [Google Material Symbols guide](https://developers.google.com/fonts/docs/material_symbols)
- [Google's official repository](https://github.com/google/material-design-icons)
- [Pinned Apache license](https://github.com/google/material-design-icons/blob/49d4db35df873165d6bd6ba09b063c7dafbac2f4/LICENSE)

Checked 2026-10-16. Google's guide explicitly lists SVG/PNG availability and
Apache-2.0 licensing. The repo identifies Material Symbols as the current set;
the older Material Icons set is not used here.
