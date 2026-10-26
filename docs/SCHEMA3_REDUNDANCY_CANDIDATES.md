# Schema-3 redundancy diagnostic candidates

The schema-3 client accepts the existing bounded, unique authored constraint IDs
in `failed_constraints` only when a successful solver report has exact status
`redundant_okay`. Exact `okay` still requires that list to be empty. The field is
preserved unchanged, including order; no IDs are moved to `redundant_constraints`,
which records separately skipped duplicate constraints.

In SolveSpace 3.2, a converged redundant solve can populate `badList` with
constraints whose removal would restore Jacobian rank. The list therefore does
not establish that their equations are unsatisfied. See the
[primary system implementation](https://github.com/solvespace/solvespace/blob/v3.2/src/system.cpp)
(`System::FindWhichToRemoveToFixJacobian` and `System::Solve`) and
[library result mapping](https://github.com/solvespace/solvespace/blob/v3.2/src/slvs/lib.cpp)
(`Slvs_SolveSketch`).

Every other admission check remains independent: exact source and solved intent,
topology and entity identities, finite bounded DoF, reported residual at most
1e-7 mm, and independently measured residual at most 1e-7 mm and no more than
reported residual plus 1e-12 mm. Failure statuses cannot carry solved geometry
or DoF. Embedded schema 1/2 still delegates to the unchanged legacy validator.
No solver, native construction, replay, authority or publication change is made.

The regression retains the exact request and stdout of service attempt O010,
plus its original observed response, client rejection and failed case record.
That all-three-points-fixed noncardinal sector has radius sqrt(1010) mm, height
7 mm, zero DoF and residual, with the three fixed relations named as candidates.
Offline validation of those retained bytes is a client regression only. The
original required-positive service attempt remains failed; a fresh independently
frozen service gate is still required.

Before any user-facing release, Gate C must display these successful-report IDs
as “Redundancy candidates”, without describing them as proven conflicts. The
existing workspace UI is deliberately unchanged in this client-only correction.
