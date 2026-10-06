"""Versioned public readiness expert. Legacy PickCubeSolution remains unchanged."""
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_CEILING
import json
from ...controllers.canonical.contracts import digest
from ...planners import ExpertAction
from ...planners.completion import StageCompletionPolicy, ExpertExecutionInfo
from .solution import PickCubeSolution, PickCubeSolutionConfig, _COLLECTION_LIFT_MARGIN


@dataclass(frozen=True)
class PickCubeReadinessConfig:
    base: PickCubeSolutionConfig
    control_dt: float
    policies: tuple[StageCompletionPolicy, ...]
    profile_identity: str
    timeout_derivation: str
    version: str = 'pick-cube-readiness-v1'

    def __post_init__(self):
        if self.version != 'pick-cube-readiness-v1' or self.control_dt <= 0:
            raise ValueError('invalid readiness configuration')
        if len(self.policies) != 4 or tuple(p.kind for p in self.policies) != ('pose_ready', 'pose_ready', 'gripper_ready', 'task_outcome'):
            raise ValueError('invalid stage policy order')
        if self.base.close_transition_steps != 20:
            raise ValueError('readiness-v1 requires the existing 20-step close primitive')

    @classmethod
    def from_source(cls, artifact, source):
        if source.task_artifact_hash != artifact.identity_hash:
            raise ValueError('source/Artifact mismatch')
        action, gripper = source.config.action, source.config.robot.gripper
        if gripper.kind != 'experimental_rate_limited':
            raise ValueError('readiness-v1 requires resolved experimental gripper profile')
        base = PickCubeSolutionConfig()
        dt = Decimal(str(artifact.timebase.control_dt))
        ceil = lambda v: int(v.to_integral_value(rounding=ROUND_CEILING))
        pose = Decimal('1.0') / dt
        if pose != pose.to_integral_value():
            raise ValueError('pose timeout must resolve to whole control boundaries')
        opening = Decimal(str(action.gripper_opening_range_m))
        rate = ceil(opening / Decimal(str(gripper.opening_step_m)))
        force = ceil(opening / Decimal(str(gripper.force_adjust_step_m)))
        margin = ceil(Decimal('0.2') / dt)
        total_close = max(rate, force) + margin
        holds = total_close - base.close_transition_steps
        if holds < 0:
            raise ValueError('gripper horizon shorter than transition')
        def policy(kind, ticks, reason):
            return StageCompletionPolicy('stage-completion-v1', kind, ticks,
                action.ik_position_deadband, action.ik_rotation_deadband,
                _COLLECTION_LIFT_MARGIN, 'panda-v1/gripper', reason)
        profile = {'gripper': asdict(gripper), 'opening_range_m': action.gripper_opening_range_m,
            'position_stiffness_N_per_m': action.gripper_position_stiffness_N_per_m,
            'pose_threshold_authority': 'resolved ActionConfig',
            'position_deadband': action.ik_position_deadband, 'rotation_deadband': action.ik_rotation_deadband}
        derivation = {'rate_ticks': rate, 'force_adjust_ticks': force, 'common_dynamics_margin_s': .2,
            'margin_ticks': margin, 'total_close_ticks': total_close, 'transition_ticks': base.close_transition_steps,
            'pose_timeout_s': 1., 'formula': 'max(ceil(range/opening_step),ceil(range/force_adjust_step))+ceil(margin/control_dt)'}
        return cls(base, float(dt), (policy('pose_ready', int(pose), 'above_pose_readiness_timeout'),
            policy('pose_ready', int(pose), 'descend_pose_readiness_timeout'),
            policy('gripper_ready', holds, 'gripper_readiness_timeout'),
            policy('task_outcome', int(pose), 'lift_outcome_timeout')),
            digest(profile), json.dumps(derivation, sort_keys=True))

    @property
    def global_safety_cap(self):
        return self.base.action_budget + sum(p.hold_ticks for p in self.policies)

    @property
    def identity(self):
        return digest({'version': self.version, 'base': asdict(self.base), 'control_dt': self.control_dt,
            'policies': [p.to_mapping() for p in self.policies], 'profile_identity': self.profile_identity,
            'timeout_derivation': self.timeout_derivation, 'global_safety_cap': self.global_safety_cap})


class PickCubeReadinessSolution(PickCubeSolution):
    """Same geometric primitives, additive completion/counter lifecycle.

    Public execution_info is separate from task info/metrics. No environment,
    controller or runtime object is accepted. Only immutable readiness metadata.
    """
    version = 'pick-cube-readiness-v1'

    def __init__(self, *, config: PickCubeReadinessConfig):
        self.readiness_config = config
        super().__init__(config=config.base)
        self.identity = digest({'version': self.version, 'config': config.identity})

    def _execution(self, execution_info, *, reset=False):
        if not isinstance(execution_info, ExpertExecutionInfo):
            raise TypeError('ExpertExecutionInfo required separately from task metrics')
        if not reset:
            if execution_info.control_step != self._boundary_step + 1:
                raise ValueError('stale/skipped execution boundary')
            expected = self._boundary_time + self.readiness_config.control_dt
            import math
            if abs(execution_info.simulation_time - expected) > max(math.ulp(expected), math.ulp(execution_info.simulation_time)):
                raise ValueError('stale execution time')
        self._boundary_step = execution_info.control_step
        self._boundary_time = execution_info.simulation_time

    def reset(self, observation, info, metadata, *, execution_info):
        self._execution(execution_info, reset=True)
        self.planned_actions_emitted = 0
        self.readiness_wait_actions_emitted = 0
        self.total_control_actions_emitted = 0
        self._wait_count = 0
        self.completion_events = []
        super().reset(observation, info, metadata)
        # Reset success at 10cm is not the new collection endpoint.
        if self._done:
            self._done = bool(info.get('is_success')) and float(info.get('task_metrics', {}).get('cube_lift', 0.)) >= _COLLECTION_LIFT_MARGIN
            if not self._done:
                self._refresh_current_segment(observation, info)

    def act(self, observation=None, info=None):
        if self.done or self.failed or self._awaiting_observation:
            raise RuntimeError('invalid expert act lifecycle')
        if self.total_control_actions_emitted >= self.readiness_config.global_safety_cap:
            self._fail('global_control_safety_cap')
            raise RuntimeError('global control safety cap reached')
        segment = self._segments[self._segment_index]
        self._last_wait = self._action_index >= len(segment.plan.actions)
        action = segment.plan.actions[-1] if self._last_wait else segment.plan.actions[self._action_index]
        diagnostics = {'expert_version': self.version, 'readiness_hold': self._last_wait,
            'planned_actions_emitted': self.planned_actions_emitted,
            'readiness_wait_actions_emitted': self.readiness_wait_actions_emitted,
            'total_control_actions_emitted': self.total_control_actions_emitted,
            'planned_segment_steps': len(segment.plan.actions), 'stage_wait_ticks': self._wait_count}
        self._awaiting_observation = True
        return ExpertAction(action=action, stage=segment.name, diagnostics=diagnostics)

    next_action = act

    def observe(self, observation, reward, terminated, truncated, info, *, execution_info):
        if not self._awaiting_observation:
            raise RuntimeError('observe requires preceding act')
        self._execution(execution_info)
        self._awaiting_observation = False
        self.total_control_actions_emitted += 1
        if self._last_wait:
            self.readiness_wait_actions_emitted += 1
            self._wait_count += 1
        else:
            self._action_index += 1
            self.planned_actions_emitted += 1
        # Legacy plan_lift uses this counter; readiness waits never enter it.
        self._actions_emitted = self.planned_actions_emitted
        policy = self.readiness_config.policies[self._segment_index]
        plan = self._segments[self._segment_index].plan
        exhausted = self._action_index >= len(plan.actions)
        ready = policy.evaluate(self._ee_pose(observation), plan.target_pose, info, execution_info)
        if policy.kind == 'task_outcome' and ready:
            self.completion_events.append({'stage': self.stage, 'control_step': self._boundary_step, 'wait_ticks': self._wait_count, 'kind': policy.kind})
            self._done = True
            return
        if truncated or terminated or info.get('task_failure', False):
            self._fail('episode_truncated' if truncated else 'environment_terminated')
            return
        if not exhausted:
            return
        if ready:
            self.completion_events.append({'stage': self.stage, 'control_step': self._boundary_step, 'wait_ticks': self._wait_count, 'kind': policy.kind})
            self._segment_index += 1
            self._action_index = 0
            self._wait_count = 0
            self._refresh_current_segment(observation, info)
        elif self._wait_count >= policy.hold_ticks:
            self._fail(policy.failure_reason)
