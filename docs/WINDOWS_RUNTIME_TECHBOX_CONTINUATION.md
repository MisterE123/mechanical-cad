# Windows runtime preparation: historical identity blocker

This public summary preserves the technical finding from an earlier development report. It is not a successful Windows runtime qualification.

Windows package filesystem virtualization can make the logical per-user application-data location differ from the physical location returned by a retained handle. The existing strict identity validator rejected that mismatch before cache ownership or a CAD child was accepted. A new diagnostic distinguishes this redirected-location failure from a remote-filesystem or ACL failure.

The safe implementation must select an authoritative OS-registered package-cache provider, retain original handles and identities, and verify unchanged registration through every owner. It must not adopt an observed alias, bypass the platform guard, repair permissions or substitute an arbitrary cache root.

See [the registered package cache design](WINDOWS_PACKAGE_CACHE_TECHBOX.md) and [later guarded capture qualification](WINDOWS_BUNDLED_CAPTURE_CANDIDATE.md). Historical failures and headless results do not establish installed GUI parity. Private transfer receipts, machine paths and operational notes are omitted from this public summary.
