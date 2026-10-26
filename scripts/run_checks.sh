#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${MCAD_PYTHON:-$ROOT/.venv/bin/python}"
cd "$ROOT"
"$PYTHON" -m ruff check .
"$PYTHON" -m ruff format --check .
"$PYTHON" -m pytest -q
TESTS=(
  tests/blender_version_gate.py
  tests/blender_smoke.py
  tests/blender_module_smoke.py
  tests/blender_backend_lifecycle_smoke.py
  tests/blender_geometry_actions_smoke.py
  tests/blender_viewport_sketch_smoke.py
  tests/blender_draft_suspension_smoke.py
  tests/blender_shared_sketch_owner_smoke.py
  tests/blender_general_authoring_owner_smoke.py
  tests/blender_typed_sketch_display_smoke.py
  tests/blender_part_publication_smoke.py
  tests/blender_part_capability_smoke.py
  tests/blender_execution_lease_smoke.py
  tests/blender_sketch_job_lifecycle_smoke.py
  tests/blender_general_overlay_smoke.py
  tests/blender_general_click_smoke.py
  tests/blender_general_point_drag_smoke.py
  tests/blender_dimension_placement_smoke.py
  tests/blender_face_pick_smoke.py
  tests/blender_blend_face_pick_smoke.py
  tests/blender_direct_edge_pick_smoke.py
  tests/blender_direct_edge_projection_smoke.py
  tests/blender_extrusion_preview_smoke.py
  tests/blender_general_session_smoke.py
  tests/blender_general_capability_smoke.py
  tests/blender_arc_owner_smoke.py
  tests/blender_arc_editor_smoke.py
  tests/blender_point_picker_rna_smoke.py
  tests/blender_arc_persistence_smoke.py
  tests/blender_general_failure_smoke.py
  tests/blender_sketch_annotation_smoke.py
  tests/blender_sketch_view_presentation_smoke.py
  tests/blender_general_view_isolation_smoke.py
  tests/blender_general_dispatch_smoke.py
  tests/blender_constraint_diagnostics_smoke.py
  tests/blender_constraint_selection_smoke.py
  tests/blender_constraint_actions_smoke.py
  tests/blender_constraint_ui_smoke.py
  tests/blender_constraint_history_busy_smoke.py
  tests/blender_constraint_launch_failure_smoke.py
  tests/blender_constraint_selection_release_smoke.py
  tests/blender_dof_cycle_guard_smoke.py
  tests/blender_ui_icon_contract.py
  tests/blender_palette_positions_smoke.py
  tests/blender_constrained_persistence.py
  tests/blender_assembly_display_smoke.py
  tests/blender_assembly_state_smoke.py
  tests/blender_assembly_capability_smoke.py
  tests/blender_assembly_authoring_smoke.py
  tests/blender_assembly_schema2_capture.py
  tests/blender_assembly_report_smoke.py
  tests/blender_assembly_pending_smoke.py
  tests/blender_assembly_job_ui_smoke.py
  tests/blender_assembly_job_load_smoke.py
  tests/blender_assembly_job_undo_smoke.py
  scripts/blender_workspace_smoke.py
)
if [[ -n "${BLENDER:-}" ]]; then
  for TEST in "${TESTS[@]}"; do
    MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" "$BLENDER" --background --factory-startup --python-exit-code 1 --python "$TEST"
  done
  FEATURE_OUTPUT="$(mktemp -d -t mcad-current-features.XXXXXX)"
  for FEATURE in through_all symmetric_extrusion; do
    MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" MCAD_SMOKE_OUTPUT="$FEATURE_OUTPUT/$FEATURE.blend" \
      "$BLENDER" --background --factory-startup --python-exit-code 1 \
      --python "tests/blender_${FEATURE}_smoke.py"
    MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" MCAD_SMOKE_INPUT="$FEATURE_OUTPUT/$FEATURE.blend" \
      MCAD_SMOKE_OUTPUT="$FEATURE_OUTPUT/$FEATURE.blend" \
      "$BLENDER" --background --factory-startup --python-exit-code 1 \
      --python "tests/blender_${FEATURE}_smoke.py"
  done
  for PHASE in save reopen; do
    MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" MCAD_SHELL_BLEND="$FEATURE_OUTPUT/shell.blend" \
      MCAD_SHELL_PHASE="$PHASE" "$BLENDER" --background --factory-startup --python-exit-code 1 \
      --python tests/blender_open_shell_smoke.py
    MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" MCAD_SHELL_BLEND="$FEATURE_OUTPUT/multiple-shell.blend" \
      MCAD_SHELL_PHASE="$PHASE" "$BLENDER" --background --factory-startup --python-exit-code 1 \
      --python tests/blender_multiple_shell_smoke.py
    MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" MCAD_FACE_DIRECTORY="$FEATURE_OUTPUT/face-mates" \
      MCAD_FACE_PHASE="$PHASE" "$BLENDER" --background --factory-startup --python-exit-code 1 \
      --python tests/blender_face_mating_smoke.py
  done
  if [[ "$(uname -s)" == "Linux" ]]; then
    PROJECT_OUTPUT="$(mktemp -d -t mcad-box-sector.XXXXXX)/project"
    for PHASE in save reopen; do
      MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" MCAD_SECTOR_ASSEMBLY_DIRECTORY="$PROJECT_OUTPUT" \
        MCAD_SECTOR_ASSEMBLY_PHASE="$PHASE" "$BLENDER" --background --factory-startup \
        --python-exit-code 1 --python-expr 'import sys; sys.dont_write_bytecode = True' \
        --python tests/blender_sector_assembly_workflow_smoke.py
    done
    printf 'Editable box/sector project and individual exports: %s\n' "$PROJECT_OUTPUT"
    ASSEMBLY_OUTPUT="$(mktemp -d -t mcad-assembly-step.XXXXXX)/project"
    for PHASE in save reopen; do
      MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" MCAD_ASSEMBLY_STEP_DIRECTORY="$ASSEMBLY_OUTPUT" \
        MCAD_ASSEMBLY_STEP_PHASE="$PHASE" "$BLENDER" --background --factory-startup \
        --python-exit-code 1 --python-expr 'import sys; sys.dont_write_bytecode = True' \
        --python tests/blender_assembly_step_export_smoke.py
    done
    PYTHONPATH="$ROOT/src" "$PYTHON" tests/integration/test_assembly_step_workflow.py \
      --read-owner "$ASSEMBLY_OUTPUT"
    printf 'Placed reusable Assembly STEP and editable project: %s\n' "$ASSEMBLY_OUTPUT"
    VISUAL_OUTPUT="$(mktemp -d -t mcad-visual-joints.XXXXXX)/project"
    for PHASE in save reopen; do
      MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" MCAD_VISUAL_JOINT_DIRECTORY="$VISUAL_OUTPUT" \
        MCAD_VISUAL_JOINT_PHASE="$PHASE" "$BLENDER" --background --factory-startup \
        --python-exit-code 1 --python-expr 'import sys; sys.dont_write_bytecode = True' \
        --python tests/blender_visual_joint_smoke.py
    done
    PYTHONPATH="$ROOT/src" "$PYTHON" tests/integration/test_assembly_step_workflow.py \
      --read-owner "$VISUAL_OUTPUT"
    printf 'Visual joint edits, reopened project and checked STEP: %s\n' "$VISUAL_OUTPUT"
    MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" BLENDER="$BLENDER" "$PYTHON" tests/blender_assembly_job_exit_smoke.py
    MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" BLENDER="$BLENDER" "$PYTHON" tests/blender_sketch_job_exit_smoke.py
  else
    printf "Owned-sidecar exit process gate NOT RUN; Linux /proc required.\n"
  fi
else
  printf '\nBlender integration NOT RUN; set BLENDER=/path/to/blender to run it.\n'
fi
if [[ -n "${MCAD_BPY_PYTHON:-}" ]]; then
  for TEST in "${TESTS[@]}"; do
    MCAD_ROOT="$ROOT" MCAD_PYTHON="$PYTHON" "$MCAD_BPY_PYTHON" "$TEST"
  done
else
  printf 'Standalone bpy LTS test NOT RUN; set MCAD_BPY_PYTHON to its interpreter.\n'
fi
