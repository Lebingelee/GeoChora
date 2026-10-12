"""Explicit height-gate removal diagnostic; no default solution migration."""
import hashlib
from pathlib import Path

from ....controllers.canonical.contracts import digest
from ....tasks.nut_assembly.stable_grasp_candidate import NutAssemblyStableGraspCandidate


class StableGraspWithoutHeightGate(NutAssemblyStableGraspCandidate):
    version = 'nutassembly-r5-10n-no-absolute-height-gate-diagnostic-v1'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.identity = digest({'base_identity': self.identity,
            'absolute_height_gate': 'removed',
            'measured_pose_stability': 'unchanged',
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

    def _stable_height_ready(self, achieved_z, expected_z):
        # Retain actual/expected geometry as evidence, never a readiness input.
        self.events.append({'event': 'absolute_height_gate_skipped',
            't': self._emitted * self.control_dt,
            'actual_z_m': float(achieved_z), 'frozen_expected_z_m': float(expected_z),
            'signed_error_m': float(achieved_z - expected_z)})
        return True
