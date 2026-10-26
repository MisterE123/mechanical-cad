"""Compatibility entry point for the stronger real-RNA chooser regression.

The old SimpleNamespace operator doubles cannot reproduce Blender enum callback
ownership. Keep the existing command/marker while running real RNA coverage.
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name('blender_recovery_rna_smoke.py')), run_name='__main__')
print('RECOVERY_CHOICES_SMOKE_OK', flush=True)
