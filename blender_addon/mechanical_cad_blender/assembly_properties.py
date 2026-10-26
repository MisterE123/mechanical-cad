"""Separate assembly RNA storage; registration belongs to registration.py.

Persisted report bytes are historical evidence, never a trusted current display.
"""

from bpy.props import BoolProperty, StringProperty
from bpy.types import PropertyGroup

from .assembly_state import document_changed


class MCAD_AssemblyState(PropertyGroup):
    show_parts: BoolProperty(name="Reusable Parts & mate frames", default=False)
    show_joints: BoolProperty(name="Joints & motion", default=False)
    show_checks: BoolProperty(name="Check policy & detailed report", default=False)
    show_options: BoolProperty(name="Assembly options", default=False)
    owner_id: StringProperty(options={"HIDDEN"})
    document_json: StringProperty(options={"HIDDEN"}, update=document_changed)
    document_path: StringProperty(name="Assembly document", subtype="FILE_PATH")
    document_name: StringProperty(name="Assembly name")
    status: StringProperty(default="EMPTY")
    error: StringProperty()
    last_action_error: StringProperty()
    display_status: StringProperty(default="EMPTY")
    verification_status: StringProperty(default="UNCHECKED")
    verification_message: StringProperty()
    report_json: StringProperty(options={"HIDDEN"})
    report_document_json: StringProperty(options={"HIDDEN"})
    report_request_json: StringProperty(options={"HIDDEN"})
    report_working_part_json: StringProperty(options={"HIDDEN"})
    report_preset_id: StringProperty(options={"HIDDEN"})
    export_receipt_json: StringProperty(options={"HIDDEN"})
    export_message: StringProperty()
    selected_part_id: StringProperty(options={"HIDDEN"})
    selected_instance_id: StringProperty(options={"HIDDEN"})
    selected_joint_id: StringProperty(options={"HIDDEN"})


CLASSES = (MCAD_AssemblyState,)
