# Pre-service native replay closure

`kernel_ocp-30383a1.py.txt` is the exact Git blob at
`30383a1bbaeae02b447bab2c37290d5f3927df8c:src/mechanical_cad/kernel_ocp.py`,
retrieved with `git show` (115844 bytes; SHA-256
`77f3f3033f95cbe72a97dbdab70769f1f0c3d34604f2d2ac036d6e10f78224ac`).
The integration harness checks this digest before constructing the subprocess
and again before lazy execution. Lazy loading preserves native-import error
ordering and permits `-S` non-native request tests.

The original manifest, engine/sidecar snapshots, requests and stdout captures
are unchanged. Their original hashes still gate every comparison. Restoring
only engine and sidecar had accidentally imported today's kernel, contaminating
historical cylinder signatures. Adding this single exact source restores all
six affected native transcripts. Remaining leaves are shared and are checked
by the unchanged golden bytes for these requests; this is not a claim of a
fully archived interpreter/dependency environment.

Current wire differences are narrowly specified in the test, never inferred
from actual current output or removed before comparison:

* `f042d88df8a4617444caf03afd694094f1abd364`, ADR 0009: optional
  diagnostic cylinder `axis_origin`, independently calculated from each request.
  This includes result v1; it does not change persistent identity or hashes.
* The previously reviewed v2 Cut wall change preserves the unmodified tool
  cylinder's stable identity and mesh bindings. Default/v1 retain snapshot IDs.
* `0e27210b1f0f91352ab0e915d978f2372585a179`, FILE_FORMAT Cut ancestry:
  v2/v3 Cut rows carry a typed ledger (null on failure). The plate/hole case has
  unchanged plate sides, modified caps, an unchanged tool cylinder, and deleted
  tool caps. The documented “legacy result version 1 is unchanged” refers to
  this ancestry extension: the test rejects a ledger on default/v1 responses.

Mutations of origins, unrelated signature fields, ledger sources/ports/deletion,
wall identity and mesh bindings must still fail exact comparison. This permits
reviewed additive diagnostic evolution, not arbitrary protocol normalization.
