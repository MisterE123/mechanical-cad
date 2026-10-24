# Mechanical CAD: exact source transfer

This branch contains a complete Git bundle of the sanitized public source snapshot, not an installer. The normal source branch is being populated separately.

## Reconstruct source

Download `mechanical-cad-public.bundle`, then run:

```sh
git clone -b public-linux-1.16 mechanical-cad-public.bundle mechanical-cad
cd mechanical-cad
git rev-parse HEAD
git rev-parse HEAD^{tree}
```

Expected commit: `855790a973bdb8ba0b452f5d2e67414f96878a44`

Expected tree: `82ae39c864cfd4c80cc2cddb65cc1baa93b2ac82`

The bundle contains one independent root commit and all 1,707 source files. Original private Git history is excluded. Development source, tests, fixtures, and assets are preserved; five documents were privacy-cleaned. See `docs/PUBLIC_SNAPSHOT_PROVENANCE.md` in the reconstructed source. Runtime installers are not included.
