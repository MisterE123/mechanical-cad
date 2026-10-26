# Mechanical CAD: temporary Windows testing source

This `windows-testing` branch contains audited executable project source for scoped Windows testing. It is not the complete development snapshot or a release.

Original local source commit: `1630f4f23e2089b82766a91330b64827274e8d0d`. Every included functional file is byte-identical to that checkpoint.

Included: core Python source, Blender add-on and application assets, build/verification scripts, ordinary test code, project example models, package/dependency configuration, GPL license and third-party notices. No runtime binaries or installers are included.

Omitted: all `docs/`, `research/`, `tests/fixtures/`, historical audit/provenance receipts in those directories, private development history, untracked QA, unfinished development, original full-snapshot README and CI configuration. This notice replaces the README for package metadata. No complete-snapshot equivalence is claimed.

Historical and full-suite checks may fail or be unavailable because fixtures and documentation are intentionally withheld. Use scoped tests that do not require those omitted inputs. Native Windows Blender qualification must be performed on this exact published commit; prior Linux or headless results do not establish it.

The public `main` and `source-transfer` branches are preserved separately. Full-source publication remains pending the separate audit-document scope decision.
