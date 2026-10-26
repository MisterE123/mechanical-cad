"""Guarded operation adapters above the native-free legacy validators.

Validators never import this module or guarded transport. Each adapter retains
fresh operation evidence; canonical capture remains serialization authority only.
"""

from . import (
    assembly_bridge,
    backend_contracts,
    bridge,
    guarded_transport,
    operation_contracts,
    part_snapshot_bridge,
)
from .guarded_evidence import GuardedEvidence


def assembly_action_guarded(
    assembly,
    action="assembly_replay",
    *,
    selection,
    owner_token,
    current_selection,
    **arguments,
):
    """Production entry: retain guarded evidence from one captured backend.

    Legacy assembly_action/AssemblyResponse remain presentation and tooling APIs;
    only this retained envelope can authorize a production display or report.
    """
    version = operation_contracts.result_version_for_assembly(assembly, action=action)
    if "result_version" in arguments:
        raise bridge.BridgeError("Guarded assembly result version is selected from every source.")
    request = assembly_bridge.build_request(assembly, action, result_version=version, **arguments)
    prepared = backend_contracts.prepare_request(request)
    return guarded_transport.execute(
        prepared,
        selection,
        owner_token=owner_token,
        current_selection=current_selection,
    )


def canonical_snapshot_guarded(document, *, selection, owner_token, current_selection):
    """Production capture retains guarded authority through its consuming owner."""
    operation_contracts.result_version_for(document, action=part_snapshot_bridge.ACTION)
    prepared = backend_contracts.prepare_request(
        {
            "protocol_version": 1,
            "action": part_snapshot_bridge.ACTION,
            "document": document,
        }
    )
    part_snapshot_bridge._expected_document(prepared.operation_request()["document"])
    evidence = guarded_transport.execute(
        prepared,
        selection,
        owner_token=owner_token,
        current_selection=current_selection,
    )
    if (
        type(evidence) is not GuardedEvidence
        or backend_contracts.request_fingerprint(evidence.guarded_request()) != prepared.fingerprint
    ):
        raise bridge.BridgeError("Canonical capture requires its exact guarded completion.")
    evidence.revalidate(
        current_selection(),
        owner_token=owner_token,
        expected_action=part_snapshot_bridge.ACTION,
        expected_result_version=None,
        require_success=True,
    )
    return evidence
