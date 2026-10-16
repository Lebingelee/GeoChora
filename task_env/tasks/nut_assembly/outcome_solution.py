"""Selected task-owned outcome execution; no diagnostic coordinator or native I/O.

The original Guarded V2/V5/R3 remains unchanged. This solution admits one
measured, bounded height warning and owns ordinary authored stage progression.
"""
from copy import deepcopy
import hashlib
import math
from numbers import Real
from pathlib import Path

import numpy as np

from ...controllers.canonical.contracts import digest
from ...utils.rotation import quat_angle_wxyz, quat_multiply_wxyz, quat_wxyz_to_matrix
from .guarded_authorization_candidate_v2 import NutAssemblyGuardedAuthorizationCandidateV2

OUTCOME_POLICY_ID = 'nutassembly-outcome-oriented-completion-v1'


class NutAssemblyOutcomeSolutionV1(NutAssemblyGuardedAuthorizationCandidateV2):
    version = 'nutassembly-r5-v5-guarded-outcome-solution-v1'
    # Additional admission bound; the original strict 0.1mm gate is untouched.
    height_warning_limit_m = .0003
    capture_stages = frozenset({'verify_lift', 'raise_for_transport',
        'move_above_square_peg', 'align_nut_yaw', 'descend_to_peg_top', 'lower_nut_to_table'})
    outcome_state_fields = ('_readiness_warnings', '_stage_receipts', '_pending_action',
                            '_task_success', '_runtime_error')

    def __init__(self, **kwargs):
        if abs(float(kwargs['control_dt']) - .01) > 1e-12:
            raise ValueError('outcome completion v1 admits only 100Hz')
        config = kwargs['config']
        if (config.capture_translation_slip_m != .008 or config.capture_rotation_slip_rad != .15
                or config.pose_position_ready_m != .007 or config.pose_rotation_ready_rad != .06
                or config.action_budget_s != 60.):
            raise ValueError('selected outcome policy requires unchanged physical limits and budget')
        self._clear_outcome()
        super().__init__(**kwargs)
        self.original_solution_identity = NutAssemblyGuardedAuthorizationCandidateV2(**kwargs).identity
        self.outcome_policy_mapping = {
            'policy_id': OUTCOME_POLICY_ID, 'rate_hz': 100,
            'allowlist': [{'stage': 'descend_to_handle', 'reason': 'stable_height_mismatch',
                'maximum_occurrences': 1, 'maximum_height_residual_m': self.height_warning_limit_m,
                'pose_position_ready_m': self.config.pose_position_ready_m,
                'pose_rotation_ready_rad': self.config.pose_rotation_ready_rad,
                'minimum_pose_wait_s': self.minimum_pose_wait_s, 'window_s': self.pose_window_s,
                'minimum_samples': self._ticks(self.pose_window_s),
                'axis_span_m': self.pose_span_m, 'speed_m_s': self.pose_speed_m_s}],
            'strict_height_tolerance_m': self.stable_height_tolerance_m,
            'capture_translation_slip_m': self.config.capture_translation_slip_m,
            'capture_rotation_slip_rad': self.config.capture_rotation_slip_rad,
            'close_authorization_policy_identity': self.policy_identity,
            'force_target_and_cap_N': 10., 'action_budget_s': self.config.action_budget_s,
            'ordered_stages': list(self.STAGES),
            'completion': 'all authored actions and endpoint gates including retreat; final inserted_on_peg AND released_nut',
            'fail_closed': ['unlisted_or_repeated_failure', 'invalid_state_or_clock',
                'capture_violation', 'task_failure', 'runtime_error', 'terminated',
                'truncated', 'action_budget_exhausted', 'incomplete_plan_or_retreat'],
            'diagnostic_shadow_override': False,
        }
        self.outcome_policy_identity = digest(self.outcome_policy_mapping)
        self.identity = digest({'original_solution_identity': self.original_solution_identity,
            'version': self.version, 'outcome_policy_identity': self.outcome_policy_identity,
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

    def _clear_outcome(self):
        self._readiness_warnings = []
        self._stage_receipts = []
        self._pending_action = None
        self._task_success = False
        self._runtime_error = None
        self._observing = False

    @property
    def failed(self):
        return self._runtime_error is not None or super().failed

    @property
    def failure_reason(self):
        return self._runtime_error or super().failure_reason

    @property
    def done(self):
        return super().done and not self.failed

    @property
    def readiness_warnings(self):
        return deepcopy(self._readiness_warnings)

    @property
    def task_success(self):
        return self._task_success

    @property
    def planned_trajectory_completed(self):
        return (len(self._stage_receipts) == len(self.STAGES)
            and [r['stage'] for r in self._stage_receipts] == list(self.STAGES)
            and all(r['endpoint_pass'] and r['planned_actions'] > 0
                    and r['planned_actions_executed'] == r['planned_actions']
                    for r in self._stage_receipts))

    @property
    def outcome_complete(self):
        return self.done and self.task_success and self.planned_trajectory_completed

    @property
    def original_expert_lifecycle_status(self):
        # A strict-gate audit of this execution, not a parallel historical replay.
        warning = next(iter(self._readiness_warnings), None)
        return {'policy': 'original-guarded-v2-v5-strict-gates',
            'assessment': 'strict gate evaluated on current execution; not historical qualification',
            'expert_complete': bool(not warning and self.done),
            'expert_failed': bool(warning or self.failed),
            'failure_reason': warning['reason'] if warning else self.failure_reason,
            'failure_step': warning['control_step'] if warning else None}

    def outcome_report(self):
        return {'completion_policy_id': OUTCOME_POLICY_ID,
            'completion_policy_identity': self.outcome_policy_identity,
            'task_success': self.task_success,
            'planned_trajectory_completed': self.planned_trajectory_completed,
            'outcome_complete': self.outcome_complete,
            'readiness_warnings': self.readiness_warnings,
            'original_expert_lifecycle_status': self.original_expert_lifecycle_status,
            'execution_lifecycle_status': self.lifecycle.to_mapping()['status'],
            'stage_execution_receipts': deepcopy(self._stage_receipts),
            'runtime_error': self._runtime_error, 'unapproved_override_used': False}

    @staticmethod
    def _finite(value):
        if isinstance(value, dict):
            return all(NutAssemblyOutcomeSolutionV1._finite(v) for v in value.values())
        if isinstance(value, (list, tuple, np.ndarray)):
            return all(NutAssemblyOutcomeSolutionV1._finite(v) for v in value)
        if isinstance(value, (Real, np.bool_)):
            return math.isfinite(float(value))
        return value is None or isinstance(value, str)

    def _validate(self, obs, info, reward=0., readiness=None, samples=()):
        if not self._finite((obs, info, reward, samples)):
            raise ValueError('nonfinite state or evidence')
        for pose in (self._ee(obs), self._body(obs, 'square_nut_v1'), self._body(obs, 'square_peg_v1')):
            if not np.isfinite(pose).all() or not .99 <= np.linalg.norm(pose[3:]) <= 1.01:
                raise ValueError('invalid pose quaternion')
        metrics = info['task_metrics']
        if not all(isinstance(v, (bool, np.bool_)) for v in (
                metrics['inserted_on_peg'], metrics['released_nut'],
                metrics['task_success'], info['is_success'], info.get('task_failure', False))):
            raise ValueError('canonical outcome predicates must be boolean')
        success = bool(metrics['inserted_on_peg'] and metrics['released_nut'])
        if success != bool(info['is_success']) or success != bool(metrics['task_success']):
            raise ValueError('inconsistent canonical task success')
        # opening_range_m bounds commands. Do not invent a tighter measured
        # joint hard-stop: the retained native route has finite soft-limit
        # overshoot. Canonical measured release and force/capture gates remain.
        if readiness is not None and not self._finite(readiness.to_mapping()):
            raise ValueError('nonfinite readiness')
        if readiness is not None and abs(readiness.gripper.force_limit_N - 10.) > 1e-12:
            raise ValueError('selected controller force cap changed')
        return success

    def reset(self, obs, info, metadata):
        self._clear_outcome()
        try:
            self._validate(obs, info)
            if type(info.get('control_step')) is not int or info.get('control_step') != 0 or info.get('simulation_time_s') != 0.:
                raise ValueError('reset clock must be zero')
        except (ValueError, KeyError, TypeError):
            self._lifecycle.reset()
            self._last_observed_step, self._last_observed_time_s = 0, 0.
            self._fail('invalid_state_or_clock')
            return
        super().reset(obs, info, metadata)
        self._task_success = bool(info['is_success'])

    def _plan(self, obs):
        super()._plan(obs)
        if len(self._stage_receipts) != self._stage_index:
            raise RuntimeError('outcome stage sequence mismatch')
        self._stage_receipts.append({'stage': self.stage, 'planned_actions': len(self._actions),
            'planned_actions_executed': 0, 'actions_executed': 0,
            'entry_step': self._emitted, 'completed_step': None, 'endpoint_pass': False})

    def abort(self, reason='runtime_error'):
        self._runtime_error = str(reason)
        if not self.lifecycle.terminal:
            self._fail(str(reason))

    def act(self):
        if self._pending_action is not None:
            self.abort('missing_execution_boundary')
        if self._emitted >= self._ticks(self.config.action_budget_s) and not self.failed:
            self._fail('canonical_solution_action_budget')
        if self.failed or self.done:
            raise RuntimeError('cannot act after outcome execution terminal')
        planned = self._index < len(self._actions)
        action = super().act()
        self._pending_action = {'stage': action.stage, 'planned': planned}
        action.diagnostics.update(completion_policy_id=OUTCOME_POLICY_ID,
            readiness_warning_count=len(self._readiness_warnings))
        return action

    def _capture_valid(self, obs):
        ee, nut = self._ee(obs), self._body(obs, 'square_nut_v1')
        relative = quat_wxyz_to_matrix(ee[3:]).T @ (nut[:3] - ee[:3])
        inverse = ee[3:].copy(); inverse[1:] *= -1
        rotation = quat_multiply_wxyz(inverse, nut[3:])
        return (np.linalg.norm(relative-self._captured_position) <= self.config.capture_translation_slip_m
                and quat_angle_wxyz(rotation, self._captured_rotation) <= self.config.capture_rotation_slip_rad)

    def observe(self, obs, reward, terminated, truncated, info, *, readiness=None, transition_samples=None):
        if self.done or self.failed:
            raise RuntimeError('cannot observe terminal outcome execution')
        try:
            success = self._validate(obs, info, reward, readiness, transition_samples or ())
            step, now = self._clock(info)
            if (self._pending_action is None or step != self._emitted
                    or step != self._last_observed_step + 1
                    or not math.isfinite(now) or abs(now-step*self.control_dt) > 1e-7):
                raise ValueError('invalid execution clock or missing action')
            if readiness is not None:
                readiness.require_boundary(step, now)
        except (ValueError, KeyError, TypeError):
            self._task_success = False
            self._fail('invalid_state_or_clock')
            return
        self._task_success = success
        receipt = self._stage_receipts[-1]
        receipt['actions_executed'] += 1
        receipt['planned_actions_executed'] += int(self._pending_action['planned'])
        self._pending_action = None
        self._last_observed_step, self._last_observed_time_s = step, now
        if terminated and truncated:
            self._fail('invalid_runtime_terminal_flags'); return
        if self._emitted > self._ticks(self.config.action_budget_s):
            self._fail('canonical_solution_action_budget'); return
        if terminated or truncated or info.get('task_failure', False):
            # Use the existing lifecycle's original runtime outcome semantics.
            self.lifecycle.observe_task_outcome(task_success=success,
                task_failure=bool(info.get('task_failure', False)),
                terminated=bool(terminated), truncated=bool(truncated),
                control_step=step, simulation_time_s=now)
            return
        if self.stage in self.capture_stages and not self._capture_valid(obs):
            self._fail('capture_constraint_violation'); return
        self._observing = True
        try:
            super().observe(obs, reward, terminated, truncated, info,
                readiness=readiness, transition_samples=transition_samples)
        finally:
            self._observing = False
        if self.stage != receipt['stage'] or self.done:
            receipt.update(endpoint_pass=True, completed_step=step)

    def _observe_stage(self, obs, info, readiness):
        receipt = self._stage_receipts[-1]
        if (self._index != receipt['planned_actions_executed']
                or self.stage == 'release_retreat' and not all(
                    r['endpoint_pass'] for r in self._stage_receipts[:-1])):
            self._fail('incomplete_planned_trajectory'); return
        super()._observe_stage(obs, info, readiness)

    def _stable_height_ready(self, achieved_z, expected_z):
        if super()._stable_height_ready(achieved_z, expected_z):
            return True
        if not self._observing or self.stage != 'descend_to_handle' or self._readiness_warnings:
            return False
        now = self._emitted * self.control_dt
        window = [x for x in self._pose_history if x[0] >= now-self.pose_window_s-1e-8]
        pose = window[-1][1]
        span = np.ptp(np.array([x[1][:3] for x in window]), axis=0)
        speeds = [np.linalg.norm(b[1][:3]-a[1][:3])/(b[0]-a[0]) for a,b in zip(window,window[1:])]
        position = float(np.linalg.norm(pose[:3]-self._goal[:3]))
        rotation = float(quat_angle_wxyz(pose[3:], self._goal[3:]))
        measurements = {'control_step': self._emitted, 'simulation_time_s': now,
            'stage': self.stage, 'reason': 'stable_height_mismatch',
            'achieved_z_m': float(achieved_z), 'strict_expected_z_m': float(expected_z),
            'height_residual_m': float(achieved_z-expected_z),
            'strict_tolerance_m': self.stable_height_tolerance_m,
            'admission_limit_m': self.height_warning_limit_m, 'sample_count': len(window),
            'wait_s': now-self._stability.start, 'position_error_m': position,
            'rotation_error_rad': rotation, 'axis_span_m': span.tolist(),
            'maximum_speed_m_s': float(max(speeds, default=math.inf))}
        admitted = (self._finite(measurements) and self._index == len(self._actions)
            and abs(achieved_z-expected_z) <= self.height_warning_limit_m
            and position <= self.config.pose_position_ready_m
            and rotation <= self.config.pose_rotation_ready_rad
            and measurements['wait_s'] >= self.minimum_pose_wait_s
            and len(window) >= self._ticks(self.pose_window_s)
            and max(span) <= self.pose_span_m and measurements['maximum_speed_m_s'] <= self.pose_speed_m_s)
        self.events.append({'event': 'readiness_warning' if admitted else 'readiness_warning_rejected',
                            't': now, **measurements})
        if admitted:
            self._readiness_warnings.append({**measurements, 'policy_id': OUTCOME_POLICY_ID,
                                            'policy_identity': self.outcome_policy_identity})
        return bool(admitted)
