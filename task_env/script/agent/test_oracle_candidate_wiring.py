"""Provider-I/O-substituted preflight for record_candidate and real canonical H5."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harness_compiler
import oracle_candidate
from harness_spec_schema import CandidateSpec


def record_candidate_preflight(spec_path, catalog_path, output):
    """Run the real Oracle orchestration around a deterministic provider-I/O seam.

    Candidate compilation, SelectedReferenceEnv recording/finalization/close,
    canonical H5 storage/load, and the Core H5 inspector remain real. Only the
    env constructor and one provider interval are substituted, so this is an
    S1 wiring check and never a physics result.
    """
    from task_env.artifacts import CanonicalStateView, PoseWorld, ExecutionSpec
    from task_env.artifacts.execution import RealizedInitialState
    from task_env.controllers.canonical.contracts import (
        AppliedCanonicalControl, RequestedAction,
    )
    from task_env.controllers.canonical.feedback import (
        CanonicalControlFeedback, CanonicalGripperFeedback,
    )
    from task_env.controllers.canonical.kinematics import ARM, FINGERS
    from task_env.runtime.sessions.api import PROFILE
    from task_env.tasks.reference_env import SelectedReferenceEnv
    import numpy as np

    spec = CandidateSpec.load(spec_path)
    catalog = json.loads(Path(catalog_path).read_text())
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    candidate_holder = {}

    class ProviderSessionSubstitute:
        def close(self):
            self.closed = True

    class SolutionLifecycleSubstitute:
        def __init__(self, identity):
            self.identity = identity
            self.done = False
            self.failed = False
            self.failure_reason = None

        def outcome_report(self):
            return {}

    def preflight_env_class():
        compiled = candidate_holder['compiled']
        value = compiled.binding.build('mujoco')

        class ProviderIoPreflightEnv(SelectedReferenceEnv):
            def __init__(self, *, provider='mujoco', backend='cpu'):
                self.uid = compiled.artifact.task_id
                self.binding = compiled.binding
                self.artifact = compiled.artifact
                self.provider, self.backend = provider, backend
                self.horizon = compiled.horizon
                self.value = value
                self.controller = value['controller']
                self.solution = SolutionLifecycleSubstitute(value['solution'].identity)
                self._external_solution_owner = None
                self.execution = ExecutionSpec(provider, PROFILE, 'none', 'cpu', 0, 'strict')
                self.session = ProviderSessionSubstitute()
                self._closed = self._stopped = False
                self._execution_fault = None
                self._position_episode_end = None
                self.position_profile = False
                self.recorder = None
                self.recording_path = None
                self.metadata = {'env_id': self.uid, 'task_artifact_hash': self.artifact.identity_hash,
                    'construction_id': 'f00-provider-io-preflight',
                    'control_dt': self.artifact.timebase.control_dt}
                self._episode_mode = 'expert'
                self._stopped = False
                self._sample_seed = None
                self.info = {'is_success': False, 'task_failure': False,
                    'task_metrics': {'task_success': False, 'cube_lift': 0.0,
                        'gripper_opening': 0.076}}
                self.evaluation = SimpleNamespace(reward=0.0, success=False,
                    failure=False, metrics={})
                self.sample = self.realized = self.state = self.feedback = None
                self.obs = {}

            def reset(self, *, seed=None, options=None):
                del options
                self._sample_seed = seed
                self.sample = self.binding.reset_sample(self.artifact, seed)
                joints = dict(self.sample.joint_position)
                opening = sum(joints[name] for name in FINGERS)
                pose = self.controller._arm.model.pose([joints[name] for name in ARM])
                poses = dict(self.sample.poses_world)
                poses.update({'panda-v1/ee': pose,
                    'panda-v1/base': PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))})
                self.state = CanonicalStateView('canonical-state-v0',
                    'SI_right_handed_z_up_wxyz', 0, 0.0, joints,
                    {name: 0.0 for name in joints}, poses)
                self.feedback = CanonicalControlFeedback('canonical-control-feedback-v0',
                    0, 0.0, CanonicalGripperFeedback('panda-v1/gripper', opening, 0.0))
                self.controller.reset(self.state, self.feedback)
                self.realized = RealizedInitialState('realized-initial-state-v0',
                    self.sample.sample_id, self.provider, self.state, 0)
                self.info = {'is_success': False, 'task_failure': False,
                    'task_metrics': {'task_success': False, 'cube_lift': 0.0,
                        'gripper_opening': float(opening)}}
                self.evaluation = SimpleNamespace(reward=0.0, success=False,
                    failure=False, metrics=self.info['task_metrics'])
                self.obs = {'state': {'ee_pose': [*pose.position, *pose.quaternion_wxyz]},
                    'privileged_state': {'cube_v1_body_pose': np.asarray([[
                        *self.sample.poses_world['cube-v1'].position,
                        *self.sample.poses_world['cube-v1'].quaternion_wxyz]], dtype=np.float32)}}
                return self.obs, self.info

            def step_expert(self):
                pose = self.state.pose_world['panda-v1/ee']
                request = RequestedAction('absolute_pose', 'world', 'quaternion_wxyz',
                    tuple(float(value) for value in (*pose.position, *pose.quaternion_wxyz, 1.0)))
                canonical, target = self.controller.compute(self.state, self.feedback, request)
                applied = AppliedCanonicalControl('applied-canonical-control-v0',
                    target.identity_hash, self.provider, dict(target.arm_servo_position),
                    target.gripper.servo_opening_m, target.gripper.force_limit_N,
                    False, 'provider_io_substitute')
                joints = dict(self.state.joint_position)
                joints.update({name: float(target.arm_servo_position[name]) for name in ARM})
                opening = float(target.gripper.servo_opening_m)
                joints.update({name: opening / 2.0 for name in FINGERS})
                ee = self.controller._arm.model.pose([joints[name] for name in ARM])
                cube_z = (spec.scene_config['table_top_z'] + .025
                    + spec.success_config['lift_height_m'])
                poses = dict(self.state.pose_world)
                old_cube = poses['cube-v1']
                poses['cube-v1'] = PoseWorld((old_cube.position[0], old_cube.position[1], cube_z),
                    old_cube.quaternion_wxyz)
                poses['panda-v1/ee'] = ee
                self.state = CanonicalStateView('canonical-state-v0',
                    'SI_right_handed_z_up_wxyz', 1, self.artifact.timebase.control_dt,
                    joints, {name: 0.0 for name in joints}, poses)
                self.feedback = CanonicalControlFeedback('canonical-control-feedback-v0',
                    1, self.state.simulation_time,
                    CanonicalGripperFeedback('panda-v1/gripper', opening, 0.0))
                self.info = {'is_success': True, 'task_failure': False,
                    'task_metrics': {'task_success': True,
                        'cube_lift': float(spec.success_config['lift_height_m']),
                        'cube_world_z_m': cube_z, 'gripper_opening': opening}}
                self.evaluation = SimpleNamespace(reward=1.0, success=True,
                    failure=False, metrics=self.info['task_metrics'])
                self.obs = {'state': {'ee_pose': [*ee.position, *ee.quaternion_wxyz]},
                    'privileged_state': {'cube_v1_body_pose': np.asarray([[
                        *poses['cube-v1'].position, *poses['cube-v1'].quaternion_wxyz]], dtype=np.float32)}}
                self._record_interval(request, canonical, target, applied, 'lift', {},
                    False, False, [])
                self.solution.done = True
                return self.obs, 1.0, False, False, self.info

        return ProviderIoPreflightEnv

    original_compile = oracle_candidate.compile_candidate
    def capture_compile(*args, **kwargs):
        compiled = original_compile(*args, **kwargs)
        candidate_holder['compiled'] = compiled
        return compiled

    with patch.object(oracle_candidate, 'compile_candidate', capture_compile), \
            patch.object(harness_compiler.CompiledTask, 'env_class', lambda _self: preflight_env_class()):
        report = oracle_candidate.record_candidate(spec, catalog, provider='mujoco', seed=0,
            directory=output/'oracle', time_limit_s=120)
    if report.status != 'pass':
        raise AssertionError(json.dumps({'status': report.status,
            'episode': report.details.get('episode'), 'errors': report.details.get('errors')},
            indent=2, ensure_ascii=False))
    # Re-run the production Judge Oracle checks against the actual bytes.
    from judge_package import check_oracle
    check_oracle(output/'oracle', spec.spec_sha256(), report.artifact_hash,
        report.core_commit, 'mujoco')
    return {'status': 'pass', 'preflight_only': True,
        'native_provider_steps': 0,
        'canonical_h5': str(output/'oracle/oracle.h5'),
        'oracle_report': str(output/'oracle/oracle.check.json'),
        'transitions': report.details['recording']['transitions'],
        'boundaries': report.details['recording']['boundaries'],
        'last_boundary_success': True,
        'identity_checks': report.details['storage_identity_checks']}


class OracleCandidateWiringTests(unittest.TestCase):
    def test_helper_is_importable(self):
        self.assertTrue(callable(record_candidate_preflight))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(record_candidate_preflight(args.spec, args.catalog, args.output),
        indent=2, ensure_ascii=False))
