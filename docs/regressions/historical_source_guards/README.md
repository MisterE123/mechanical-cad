# Historical source-freeze audits

The 0.7 milestone required the complete Python tree to remain byte-identical,
except for explicitly enumerated inverse patches. The 0.9 feature work deliberately
changes that architecture and functionality. Such hashes are not runtime security
checks, model validation, native geometry evidence, or backwards compatibility.

`arc_profile_native_end_cap_0_7.py.txt` preserves the complete pre-maintenance audit
source and its original expected hashes. The historical source-freeze test functions
are retired from current pytest collection, rather than repinned to declare new
code equivalent to old code. Inverse helpers remain in the active test module
for dependent audit tooling. Existing fixtures and original failing snapshot logs
are not changed.

All end-cap observation, exact arithmetic, malformed input, evidence budgets,
collector, constructor order, mass, and native-registration assertions remain
active. This retirement does not make other historical audit suites green and
does not waive any current geometry or persistence behavior failure.
