"""One detached insertion intent with stable IDs, never replay/publication authority.

Arguments are already parsed canonical units. Existing edit helpers construct the
candidate; the guarded full-assembly replay must still validate it before preview
or publication. Access never regenerates IDs or mutates accepted/source inputs.
"""

import copy

from . import assembly_edit as edit


class InsertPreviewDraft:
    def __init__(self, accepted, part_id, *, working_part=None, **insert_arguments):
        original = copy.deepcopy(accepted)
        candidate = copy.deepcopy(original)
        if working_part is not None:
            candidate, part_id = edit.capture_definition(
                candidate, copy.deepcopy(working_part)
            )
        candidate = edit.insert_instance(
            candidate, part_id, **copy.deepcopy(insert_arguments)
        )
        # Capture and insertion are one construction: no intermediate orphan is
        # exposed if either helper fails. Copy even helper-retained argument data.
        self._original = original
        self._candidate = copy.deepcopy(candidate)

    @property
    def part_id(self):
        return self._candidate["instances"][-1]["part_id"]

    @property
    def instance_id(self):
        return self._candidate["instances"][-1]["id"]

    @property
    def joint_id(self):
        return self._candidate["joints"][-1]["id"]

    def original(self):
        """Return the accepted input snapshot, not a live document reference."""
        return copy.deepcopy(self._original)

    def candidate(self):
        """Return the same detached candidate and identities for each replay."""
        return copy.deepcopy(self._candidate)
