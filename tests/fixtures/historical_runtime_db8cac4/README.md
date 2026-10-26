# Exact historical runtime guard inputs

Historical source-integrity and mutation-test input only. This fixture does
not approve the current runtime. Exact source commit:
`db8cac466c8b7dad3a17d2107b66128180be395e`. Every file was compared with
its Git object before inclusion; tests do not require Git at runtime.

The manifest is the minimal existing copy_python_guard_tree closure (404
files), plus four existing primitive/dispatch/baseline fixtures required by
the original 104-file mutation checks. Content-addressed .txt objects are
inert functional source/tests. Existing identical immutable fixtures are
reused by path and verified by size and SHA-256. No Git history, private
operational reports, or runtime binaries are included.

Original inverse manifests, expected digests and mutation assertions are
unchanged. The original 259-path protected digest remains
`f1c9a006975a48a8ef3fb051709eb4ac75a0dadc207090c27783902034e939b7`.
The loader independently pins the full manifest and rejects missing, corrupt
or unexpected objects before creating a temporary source snapshot.

Historical inverse helpers read this snapshot. Live import/Windows boundary
tests continue reading the current checkout and addon; current-source
mutation tests remain independent. Historical success is not current-source,
native-installer, Windows or GUI release qualification.
