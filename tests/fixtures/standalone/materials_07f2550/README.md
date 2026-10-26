# Historical materials-wrapper source boundary

The two `.py.txt` files are exact, non-importable source bytes from commit
`07f2550`, when the materials wrapper was introduced. Their original SHA-256
values remain unchanged in `test_standalone_package_materials.py`.

`reviewed_platform_changes.json` records only the contextual changes introduced
by `e1dae075` to those two files:

- Separate private candidate staging from the existing no-clobber publication
  wrapper, without turning a failed publication into another publication route.
- Select CPython 3.12.10 for Windows and 3.12.15 for Linux.
- Validate the actual Windows mapped native-image origins and strict private
  native imports before dispatch, including handle-based spelling verification.

The manifest is independently hash-pinned. Its old spans must each occur exactly
once; all remaining bytes must match the current source. Bootstrap project-version
updates are the only additional normalization and require exactly one current
version literal. There is no broad hash replacement or ignored function body.

These fixtures are read only as data, never executed. Current runtime import-edge
and default test-discovery checks still inspect the live checkout. Mutation tests
reject altered historical bytes, altered change manifests, a no-clobber bypass,
a native-origin bypass and unrelated current edits. Historical reproduction does
not establish native platform qualification, licensing clearance or release
readiness.
