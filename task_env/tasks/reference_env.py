"""Explicit selected-reference adapter, delegating task semantics and policies.

This adapter owns one scalar CPU session. It defines no TaskArtifact or task
success predicate. Expert execution and external-action execution cannot be
mixed in one episode. Rendering and legacy TaskEnv configuration are rejected.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
from types import SimpleNamespace
from typing import Callable
from uuid import uuid4
import numpy as np
from gymnasium.spaces import Box, Dict

from ..artifacts import ExecutionSpec
from ..controllers.canonical.contracts import RequestedAction, digest
from ..environment.protocols import TaskEnvironmentComponent
from ..environment.types import ExecutionFaultV1, StageUnavailableError, attach_execution_fault
from ..planners.completion import ExpertExecutionInfo
from ..runtime.sessions.api import PROFILE
from ..runtime.sessions.control import ControlBinding, materialize_control

METADATA = {'action_schema': {'schema_id': 'selected-reference-absolute-pose-v1',
    'schema_version': 1, 'controller_kind': 'absolute_pose', 'reference': 'world',
    'rotation_representation': 'quaternion_wxyz', 'dimension': 8}}
_RESET_SEED_UNSET = object()


def _identity_seed(seed):
    return seed


def _no_reset_kwargs(env):
    return {}


def _no_observe_kwargs(env, guard_samples):
    return {}


@dataclass(frozen=True)
class ReferenceTaskBinding:
    """Internal task-to-reference adapter; not a new public task protocol."""

    build: Callable
    reset_sample: Callable
    evaluate: Callable
    object_poses: tuple[tuple[str, str], ...]
    external_actions: bool
    interval_mode: str
    recorder_mode: str
    external_action_error: str = 'selected reference route does not admit external actions'
    reset_seed: Callable = _identity_seed
    reset_expert_kwargs: Callable = _no_reset_kwargs
    observe_expert_kwargs: Callable = _no_observe_kwargs
    schedule_factory: Callable | None = None
    capture_guard_samples: bool = False
    record_native_substeps: bool = False
    abort_solution_on_runtime_error: bool = False
    build_external: Callable | None = None
    validate_external_solution: Callable | None = None

    def __post_init__(self):
        if self.interval_mode not in {"grouped", "native"}:
            raise ValueError("unknown selected control-interval requirement")
        if self.recorder_mode not in {"canonical", "execution"}:
            raise ValueError("unknown selected recording requirement")
        if not self.object_poses:
            raise ValueError("selected task binding requires an observation pose")
        if (self.build_external is None) != (self.validate_external_solution is None):
            raise ValueError('external Solution construction and validation must be supplied together')


class SelectedReferenceEnv(TaskEnvironmentComponent):
    """Advanced reference API. No legacy Gym configuration compatibility claim."""
    binding: ReferenceTaskBinding | None = None

    @classmethod
    def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
        values = {} if config is None else dict(config)
        if kwargs or render_mode is not None:
            raise ValueError('selected reference admits state-only execution without extra kwargs')
        if set(values) - {'provider', 'backend', 'horizon'}:
            raise ValueError('selected reference config admits provider/backend/horizon only; legacy overlays are incompatible')
        return cls(**values)

    @classmethod
    def from_position_candidate(
        cls, binding: ReferenceTaskBinding, *, provider='geophys', backend='cpu', horizon=6000,
    ):
        """Explicitly construct a bounded Position profile through the selected binding."""
        from ..controllers.canonical.position_profile import PandaPositionServoProfileV1

        if not isinstance(binding, ReferenceTaskBinding):
            raise TypeError('PositionServoV1 candidate requires the existing ReferenceTaskBinding')
        from ..controllers.canonical.position_profile import PandaPositionServoProfileV1

        candidate_type = cls
        if not hasattr(cls, 'uid'):
            candidate_type = type(
                'PositionCandidateSelectedReferenceEnv', (cls,),
                {'uid': 'c02b-position-servo-candidate-v1'},
            )
        env = candidate_type(provider=provider, backend=backend, horizon=horizon, _binding=binding)
        profiles = env.position_profiles
        if (not profiles or len(profiles) > 2
                or any(not isinstance(profile, PandaPositionServoProfileV1) for profile in profiles)
                or len({profile.writer_id for profile in profiles}) != len(profiles)
                or len({profile.entity_id for profile in profiles}) != len(profiles)):
            env.close()
            raise TypeError('candidate binding did not construct one or two Entity-bound PositionServoV1 profiles')
        return env

    def _bind_selected_controller(self, value):
        from ..controllers.canonical.position_profile import PandaPositionServoProfileV1

        raw = value['controller']
        profiles = tuple(raw) if isinstance(raw, (tuple, list)) else (raw,)
        if profiles and all(isinstance(item, PandaPositionServoProfileV1) for item in profiles):
            if len(profiles) > 2 or len({item.writer_id for item in profiles}) != len(profiles):
                raise ValueError('selected Position route admits one writer or the bounded two-Entity profile set')
            if len({item.entity_id for item in profiles}) != len(profiles):
                raise ValueError('selected Position writers must bind distinct Entities')
            profiles = tuple(sorted(profiles, key=lambda item: item.entity_id))
            self.position_profiles = profiles
            self.position_profile = True
            # Existing callers of selected-reference metadata continue to see
            # the original Panda profile; dual dispatch uses position_profiles.
            self.controller = profiles[0]
        else:
            if isinstance(raw, (tuple, list)):
                raise TypeError('legacy selected routes do not accept a Controller profile collection')
            self.position_profiles = ()
            self.position_profile = False
            self.controller = raw

    def __init__(self, *, provider='geophys', backend='cpu', horizon=6000, _binding=None):
        if provider not in {'geophys', 'mujoco'} or backend != 'cpu':
            raise ValueError('selected reference currently admits GeoPhys/MuJoCo scalar CPU only')
        if type(horizon) is not int or not 1 <= horizon <= 6000:
            raise ValueError('selected reference horizon must be an integer in [1, 6000]')
        if _binding is not None:
            if not isinstance(self, SelectedReferenceEnv) or not isinstance(_binding, ReferenceTaskBinding):
                raise TypeError('explicit Position binding is only admitted by SelectedReferenceEnv')
            self.binding = _binding
        if not isinstance(self.binding, ReferenceTaskBinding):
            raise TypeError('selected reference requires an explicit task binding')
        self.provider, self.horizon = provider, horizon
        self._execution_fault = None
        try:
            self.value = self.binding.build(provider)
        except BaseException as error:
            fault = ExecutionFaultV1.from_exception(
                'selected_construction', error
            )
            self._execution_fault = fault
            attach_execution_fault(error, fault)
            raise
        self.artifact = self.value['artifact']
        self.solution = self.value['solution']
        self._bind_selected_controller(self.value)
        self.dual_entity_position = len(self.position_profiles) == 2
        self.metadata = {**METADATA, 'action_schema': dict(METADATA['action_schema']), 'env_id': self.uid,
            'task_artifact_hash': self.artifact.identity_hash,
            'construction_id': self.value['construction_id'],
            'control_dt': self.artifact.timebase.control_dt}
        self.action_space = Box(-np.inf, np.inf, (8,), dtype=np.float64)
        keys = [key for _, key in self.binding.object_poses]
        state_spaces = {'ee_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32)}
        if self.position_profile:
            state_spaces.update({
                'joint_position': Box(-np.inf, np.inf, (9,), dtype=np.float32),
                'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
                'boundary_identity_sha256': Box(0, 255, (32,), dtype=np.uint8),
            })
            if self.dual_entity_position:
                state_spaces['entities'] = Dict({
                    profile.entity_id: Dict({
                        'joint_position': Box(-np.inf, np.inf, (9,), dtype=np.float32),
                        'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
                    })
                    for profile in self.position_profiles
                })
        self.observation_space = Dict({'state': Dict(state_spaces),
            'privileged_state': Dict({k + '_body_pose': Box(-np.inf, np.inf, (1, 7), dtype=np.float32) for k in keys})})
        self.session = None
        self._external_solution_owner = None
        self._closed = False
        self._episode_mode = None
        self._stopped = True
        self._position_episode_end = None
        self._published_position_state = None
        self._published_position_typed_state = None
        self._published_position_obs = None
        self._published_position_info = None
        self._published_position_evaluation = None
        self._position_controller_switch_fault_receipt = None
        self._pending_position_switch = None
        self.recorder = None
        self.recording_path = None

    @property
    def execution_fault(self):
        """Return the latched selected-route execution fault, if any."""

        return self._execution_fault

    def _latch_fault(
        self,
        phase,
        error,
        *,
        before_state=None,
        after_state=None,
        interval_attempted=False,
        interval_completed=False,
        observer_confirmed_substeps=None,
        recorder_confirmed_substeps=None,
        native_substeps_expected=None,
        transition_status='not_assessed',
        readback_error=None,
    ):
        fault = ExecutionFaultV1.from_exception(
            phase,
            error,
            control_step_before=(
                None if before_state is None else int(before_state.control_step)
            ),
            control_step_after=(
                None if after_state is None else int(after_state.control_step)
            ),
            simulation_time_before_s=(
                None if before_state is None else before_state.simulation_time
            ),
            simulation_time_after_s=(
                None if after_state is None else after_state.simulation_time
            ),
            expected_control_dt_s=self.artifact.timebase.control_dt,
            interval_attempted=interval_attempted,
            interval_completed=interval_completed,
            observer_confirmed_substeps=observer_confirmed_substeps,
            recorder_confirmed_substeps=recorder_confirmed_substeps,
            native_substeps_expected=native_substeps_expected,
            transition_status=transition_status,
            readback_error=readback_error,
        )
        self._execution_fault = fault
        self._stopped = True
        attach_execution_fault(error, fault)
        return fault

    @property
    def composition_spec(self):
        return self.value['source'].composition

    def _position_requirements(self):
        from ..artifacts import StateRequirements

        if len(self.position_profiles) == 1:
            return self.position_profiles[0].requirements
        return StateRequirements(
            'state-requirements-v1', 'controller', 'c02b-dual-position-dispatch-v1',
            tuple(requirement for profile in self.position_profiles
                  for requirement in profile.requirements.requirements),
        )

    def reset(self, *, seed=_RESET_SEED_UNSET, options=None):
        return self._reset(seed=seed, options=options)

    def reset_for_solution(self, solution, *, seed=_RESET_SEED_UNSET, options=None):
        """Reset this selected route for one caller-owned Solution instance.

        The task binding validates that the supplied mutable Solution matches
        the actual current Artifact/source/readiness configuration before the
        existing RuntimeSession is reconstructed.
        """
        if self.binding.build_external is None or self.binding.validate_external_solution is None:
            raise StageUnavailableError('this selected task has no external Solution lifecycle')
        if self._closed:
            raise RuntimeError('environment is closed')
        self.binding.validate_external_solution(self.value, solution)
        return self._reset(seed=seed, options=options, external_solution=solution)

    def _reset(self, *, seed=_RESET_SEED_UNSET, options=None, external_solution=None):
        if self._closed:
            raise RuntimeError('environment is closed')
        if options:
            raise ValueError('selected reference reset options are not supported')
        if seed is _RESET_SEED_UNSET:
            if getattr(self, 'position_profile', False):
                seed = self.value['reset_plan'].reset_sample.task_seed
            else:
                seed = 19
        if getattr(self, 'position_profile', False):
            # Validate the fixed ResetPlan seed before closing/reconstructing a
            # live RuntimeSession. Legacy selected bindings keep their existing
            # reconstruction-before-seed-validation lifecycle below.
            seed = self.binding.reset_seed(seed)
            reset_plan = self.value.get('reset_plan')
            if reset_plan is None or seed != reset_plan.reset_sample.task_seed:
                raise ValueError('PositionServoV1 reset seed must match its fixed EpisodeResetPlan')
        if self.recorder is not None and not getattr(self.recorder, 'frozen', getattr(self.recorder, '_frozen', False)):
            raise RuntimeError('finalize current recording before reset')
        previous_episode_end = self._position_episode_end
        if (getattr(self, 'position_profile', False) and self.session is not None
                and self._published_position_typed_state is not None
                and previous_episode_end is None):
            previous_episode_end = self.stop('reset')
        if getattr(self, 'position_profile', False):
            self._position_episode_end = None
            self._position_controller_switch_fault_receipt = None
            self._pending_position_switch = None
            self._published_position_state = None
            self._published_position_typed_state = None
            self._published_position_obs = None
            self._published_position_info = None
            self._published_position_evaluation = None
        self._stopped = True
        previous_session, self.session = self.session, None
        phase = 'reset_close'
        try:
            if previous_session is not None:
                previous_session.close()
            phase = 'selected_reconstruction'
            # A new construction resets all controller/arm-hold/servo owner memory.
            self.value = (self.binding.build_external(self.provider)
                          if external_solution is not None else self.binding.build(self.provider))
            if self.value['artifact'] != self.artifact:
                raise ValueError('selected Artifact changed between construction and reset')
            if external_solution is not None:
                self.binding.validate_external_solution(self.value, external_solution)
            phase = 'reset_seed'
            if not getattr(self, 'position_profile', False):
                seed = self.binding.reset_seed(seed)
            self.solution = self.value.get('solution')
            self._external_solution_owner = external_solution
            self._bind_selected_controller(self.value)
            self.dual_entity_position = len(self.position_profiles) == 2
            phase = 'reset_sample'
            if self.position_profile:
                reset_plan = self.value.get('reset_plan')
                if reset_plan is None:
                    raise ValueError('PositionServoV1 selected route requires an EpisodeResetPlanV1')
                self.sample = reset_plan.reset_sample
            else:
                self.sample = self.binding.reset_sample(self.artifact, seed)
                self._selected_episode_id = uuid4().hex
            self.execution = ExecutionSpec(self.provider, PROFILE, 'none', 'cpu', 0, 'strict')
            phase = 'session_materialization'
            if self.position_profile:
                from ..runtime.sessions.control import (
                    ControlBindingPlanV1,
                    compile_control_binding_plan,
                )
                self.position_scene = self.value['source'].scene_definition
                self.position_plan = self.value.get('controller_binding_plan')
                if self.position_plan is None:
                    self.position_plan = compile_control_binding_plan(
                        self.position_scene,
                        tuple(profile.controller_binding() for profile in self.position_profiles),
                    )
                if not isinstance(self.position_plan, ControlBindingPlanV1):
                    raise TypeError('PositionServoV1 selected route requires ControlBindingPlanV1')
                self.position_joint_bindings = {
                    f'{articulation.entity_id}/{joint.joint_id}': joint
                    for articulation in self.position_scene.articulations or ()
                    for joint in articulation.joints
                    if joint.kind != 'fixed'
                }
                from ..artifacts import FrameReference
                self.position_frame_bindings = {
                    semantic: FrameReference(entity, frame)
                    for semantic, (entity, frame) in {
                        name: tuple(name.split('/', 1))
                        for name in (*self.value['source'].bodies, *self.value['source'].frames)
                    }.items()
                }
                self.session = materialize_control(
                    self.artifact, self.execution, source=self.value['source'],
                    binding=ControlBinding('panda-main/gripper', .08),
                    controller_binding_plan=self.position_plan,
                    controller_profile=self.position_profiles,
                )
            else:
                self.position_profile = False
                self.session = materialize_control(self.artifact, self.execution,
                    source=self.value['source'], binding=ControlBinding('panda-v1/gripper', .08))
            phase = 'runtime_reset'
            if self.position_profile:
                reset_plan = self.value.get('reset_plan')
                self.realized = self.session.reset_plan(reset_plan)
            else:
                self.realized = self.session.reset(self.sample)
            phase = 'snapshot_readback'
            self.state = self.session.snapshot()
            if self.position_profile:
                self.typed_state = self.session.snapshot_v1(
                    scene=self.position_scene,
                    joint_bindings=self.position_joint_bindings,
                    frame_bindings=self.position_frame_bindings,
                    requirements=self._position_requirements(),
                )
                for profile in self.position_profiles:
                    profile.reset(self.typed_state, self.position_plan)
                self.feedback = None
            else:
                phase = 'controller_feedback'
                self.feedback = self.session.control_feedback(self.state)
                self.controller.reset(self.state, self.feedback)
            phase = 'reset_observation'
            self.obs, self.info, self.evaluation = self.observation(self.state)
            if not self.position_profile:
                self._publish_execution_info(self.info)
            self._last_position_terminated = False
            self._last_position_truncated = False
            self._last_position_request = None
            if self.position_profile:
                self._position_reset_info = self._position_record_reset_info()
                self.info.update(self._position_reset_info)
                if previous_episode_end is not None:
                    self.info['previous_episode_end_v1'] = previous_episode_end.to_mapping()
            if self.state.control_step != 0 or self.state.simulation_time != 0:
                raise ValueError('reference reset must not advance physics')
            reset_solution = external_solution if external_solution is not None else self.solution
            if reset_solution is not None:
                phase = 'solution_reset'
                reset_solution.reset(self.obs, self.info, self.metadata,
                                    **self.binding.reset_expert_kwargs(self))
            phase = 'arm_schedule_reset'
            self.arm_schedule = (self.binding.schedule_factory(self)
                                 if self.binding.schedule_factory is not None else None)
            self._stopped, self._episode_mode = False, None
            self._position_episode_end = None
            self._published_position_state = self.state
            self._published_position_typed_state = getattr(self, 'typed_state', None)
            self._published_position_obs = self.obs
            self._published_position_info = dict(self.info)
            self._published_position_evaluation = self.evaluation
            self.recorder = None
            self._execution_fault = None
            if external_solution is not None:
                # The caller's instance is the only active mutable Solution
                # owner for this episode; the task value has no active copy.
                self.solution = None
            return self.obs, self.info
        except BaseException as error:
            self._external_solution_owner = None
            failed_session, self.session = self.session, None
            if failed_session is not None:
                try:
                    failed_session.close()
                except BaseException as cleanup_error:
                    add_note = getattr(error, 'add_note', None)
                    if callable(add_note):
                        add_note(f'selected reset cleanup also failed: {cleanup_error!r}')
            self._latch_fault(phase, error)
            raise

    def expert_execution_info(self):
        """Return the required, validated R1 readiness at the current boundary."""
        if (getattr(self, 'state', None) is None or getattr(self, 'feedback', None) is None
                or getattr(self, 'position_profile', False)):
            raise StageUnavailableError('R1 execution readiness is unavailable on this selected route')
        result = ExpertExecutionInfo(
            'expert-execution-info-v1', self.state.control_step,
            self.state.simulation_time, self.controller.readiness(self.state, self.feedback),
        )
        result.validate()
        return result

    # Kept for existing in-module callers while public callers use the named
    # expert_execution_info() contract.
    def _execution_info(self):
        return self.expert_execution_info()

    def _execution_boundary(self, execution_info=None):
        execution_info = self.expert_execution_info() if execution_info is None else execution_info
        source = self.value['source']
        source_id = source.scene_source.source_id
        source_xml_sha256 = hashlib.sha256(source.scene_source.xml.encode()).hexdigest()
        values = {
            'schema_version': 'selected-expert-boundary-v1',
            'episode_id': self._selected_episode_id,
            'task_artifact_hash': self.artifact.identity_hash,
            'source_id': source_id,
            'source_xml_sha256': source_xml_sha256,
            'source_closure_digest': source.source_closure_digest,
            'controller_identity': self.controller.identity,
            'solution_identity': self._active_solution_identity(),
            'reset_sample_id': self.sample.sample_id,
            'control_step': execution_info.control_step,
            'simulation_time_s': execution_info.simulation_time,
        }
        values['identity_hash'] = digest(values)
        return values

    def _publish_execution_info(self, info):
        execution_info = self.expert_execution_info()
        info['expert_execution_info_v1'] = execution_info.to_mapping()
        info['control_readiness_v1'] = execution_info.control_readiness.to_mapping()
        info['expert_execution_boundary_v1'] = self._execution_boundary(execution_info)

    def _publish_control_application(self, info, request, canonical, target, applied,
                                     request_boundary):
        if target.identity_hash != applied.target_hash:
            raise ValueError('applied acknowledgement does not match the computed target')
        if target.task_artifact_hash != self.artifact.identity_hash:
            raise ValueError('applied target belongs to another TaskArtifact')
        if target.controller_identity != self.controller.identity:
            raise ValueError('applied target belongs to another Controller')
        if applied.provider_name != self.provider:
            raise ValueError('applied acknowledgement belongs to another Provider')
        current_info = ExpertExecutionInfo.from_mapping(info['expert_execution_info_v1'])
        evaluation_boundary = self._execution_boundary(current_info)
        if request_boundary is None:
            raise ValueError('control application acknowledgement requires its source boundary')
        receipt = {
            'schema_version': 'selected-control-application-v1',
            'task_artifact_hash': self.artifact.identity_hash,
            'source_id': self.value['source'].scene_source.source_id,
            'controller_identity': self.controller.identity,
            'reset_sample_id': self.sample.sample_id,
            'request_boundary': dict(request_boundary),
            'evaluation_boundary': evaluation_boundary,
            'requested_action': request.to_mapping(),
            'canonical_action': canonical.to_mapping(),
            'target': target.to_mapping(),
            'target_identity_hash': target.identity_hash,
            'applied': applied.to_mapping(),
            'applied_target_hash': applied.target_hash,
        }
        if (receipt['request_boundary']['control_step'] + 1 != current_info.control_step
                or receipt['evaluation_boundary']['control_step'] != current_info.control_step):
            raise ValueError('control acknowledgement does not span exactly one completed boundary')
        expected_dt = self.artifact.timebase.control_dt
        actual_dt = (receipt['evaluation_boundary']['simulation_time_s']
                     - receipt['request_boundary']['simulation_time_s'])
        tolerance = max(
            math.ulp(receipt['evaluation_boundary']['simulation_time_s']),
            math.ulp(receipt['request_boundary']['simulation_time_s']),
            math.ulp(expected_dt),
        )
        if abs(actual_dt - expected_dt) > tolerance:
            raise ValueError('control acknowledgement does not match the selected control timebase')
        info['control_application_v1'] = receipt

    def _require_published_execution_info(self):
        mapping = self.info.get('expert_execution_info_v1')
        if not isinstance(mapping, dict):
            raise ValueError('public expert execution readiness is missing')
        execution_info = ExpertExecutionInfo.from_mapping(mapping)
        execution_info.validate()
        current = self.expert_execution_info()
        if execution_info != current:
            raise ValueError('public expert execution readiness is stale or belongs to another boundary')
        readiness = self.info.get('control_readiness_v1')
        if readiness != execution_info.control_readiness.to_mapping():
            raise ValueError('public control readiness is missing or inconsistent')
        boundary = self.info.get('expert_execution_boundary_v1')
        if boundary != self._execution_boundary(current):
            raise ValueError('public expert execution boundary identity is stale or mismatched')
        return execution_info

    def _active_solution_identity(self):
        owner = self._external_solution_owner if self._external_solution_owner is not None else self.solution
        identity = getattr(owner, 'identity', None)
        if not isinstance(identity, str):
            identity = self.value.get('solution_identity')
        if not isinstance(identity, str):
            raise RuntimeError('selected task has no solution identity for recording')
        return identity

    def _validate_external_solution(self, solution):
        if self.binding.validate_external_solution is None:
            raise StageUnavailableError('this selected task has no external Solution lifecycle')
        self.binding.validate_external_solution(self.value, solution)

    def observation(self, state):
        if getattr(self, 'position_profile', False):
            adapted = self.controller._adapt_publication(self.typed_state)
            evaluation_state = SimpleNamespace(
                control_step=state.control_step,
                simulation_time=state.simulation_time,
                joint_position={**state.joint_position, **adapted.joint_position},
                joint_velocity=state.joint_velocity,
                pose_world={**state.pose_world, **adapted.pose_world},
            )
            evaluation = self.binding.evaluate(evaluation_state, self.artifact.semantics)
            ee = adapted.pose_world['panda-v1/ee']
        else:
            evaluation = self.binding.evaluate(state, self.artifact.semantics)
            ee = state.pose_world['panda-v1/ee']
        state_obs = {'ee_pose': np.array((*ee.position, *ee.quaternion_wxyz), dtype=np.float32)}
        obs = {'state': state_obs, 'privileged_state': {}}
        if getattr(self, 'position_profile', False):
            view = self.typed_state.view
            boundary = view.boundary
            entity_states = {}
            for profile in self.position_profiles:
                joints = {
                    value.joint_id: value for value in view.joints
                    if value.entity_id == profile.entity_id
                }
                hand = next(
                    value for value in view.frames
                    if value.frame.entity_id == profile.entity_id
                    and value.frame.frame_id == profile.hand_frame_id
                )
                entity_states[profile.entity_id] = {
                    'joint_position': np.asarray([
                        joints[name].position[0]
                        for name in (*profile.joint_ids, *profile.finger_joint_ids)
                    ], dtype=np.float32),
                    'hand_pose': np.asarray(
                        (*hand.pose_world.position, *hand.pose_world.quaternion_wxyz),
                        dtype=np.float32,
                    ),
                }
            primary = self.position_profiles[0]
            identity_hex = boundary.boundary_id.removeprefix('state-boundary-')
            state_obs.update({
                'joint_position': entity_states[primary.entity_id]['joint_position'],
                'hand_pose': entity_states[primary.entity_id]['hand_pose'],
                'boundary_identity_sha256': np.frombuffer(bytes.fromhex(identity_hex), dtype=np.uint8).copy(),
            })
            if self.dual_entity_position:
                state_obs['entities'] = entity_states
        for semantic, key in self.binding.object_poses:
            pose = state.pose_world[semantic]
            obs['privileged_state'][key + '_body_pose'] = np.array(
                [(*pose.position, *pose.quaternion_wxyz)], dtype=np.float32)
        info = {'is_success': bool(evaluation.success), 'task_failure': bool(evaluation.failure),
            'task_metrics': dict(evaluation.metrics), 'control_step': int(state.control_step),
            'simulation_time_s': float(state.simulation_time)}
        if getattr(self, 'position_profile', False):
            boundary = self.typed_state.view.boundary
            info['state_boundary_identity'] = boundary.to_mapping()
            info['state_boundary_id'] = boundary.boundary_id
            info['state_sample_clock'] = self.typed_state.view.sample_clock.to_mapping()
        return obs, info, evaluation

    def step(self, action):
        if getattr(self, '_closed', False):
            raise RuntimeError('environment is closed')
        if self._execution_fault is not None:
            fault = self._execution_fault
            raise RuntimeError(
                'selected execution is faulted; reset() is required '
                f"(phase={fault.phase}, physical_progress={fault.physical_progress})"
            )
        if not self.binding.external_actions:
            raise RuntimeError(self.binding.external_action_error)
        if self._episode_mode in {'expert', 'external_solution'}:
            raise RuntimeError('cannot mix external actions with selected Solution execution')
        from ..controllers.canonical.contracts import StructuredActionRequestV1
        if getattr(self, 'position_profile', False):
            if self._stopped or self.session is None:
                raise RuntimeError('reset required or episode already stopped')
            if self.state.control_step >= self.horizon:
                self._stopped = True
                raise RuntimeError('selected PositionServoV1 horizon is exhausted')
            if not isinstance(action, StructuredActionRequestV1):
                raise TypeError('PositionServoV1 requires a StructuredActionRequestV1')
            from ..runtime.sessions.control import prepare_structured_action
            # Reject bad action and plan identities before changing episode mode,
            # Controller memory, Recorder state, or the Provider.
            prepare_structured_action(self.position_plan, action)
            return self._step_position_profile(action)
        if isinstance(action, StructuredActionRequestV1):
            raise TypeError('structured ControllerGroup actions require PositionServoV1')
        self._episode_mode = 'external'
        return self._step(action)

    def step_with_solution(self, solution):
        """Run one caller-owned Solution action through the selected lifecycle.

        The public readiness payload is checked before calling ``act``. The
        same Solution instance receives post-step ``observe`` before any
        canonical Recorder append. The instance remains the sole owner of its
        mutable stage state.
        """
        if self._closed:
            raise RuntimeError('environment is closed')
        if self._execution_fault is not None:
            fault = self._execution_fault
            raise RuntimeError(
                'selected execution is faulted; reset() is required '
                f"(phase={fault.phase}, physical_progress={fault.physical_progress})"
            )
        if self._external_solution_owner is None or solution is not self._external_solution_owner:
            raise ValueError('step_with_solution requires the instance accepted by reset_for_solution')
        self._validate_external_solution(solution)
        if self._stopped or self.session is None:
            raise RuntimeError('reset required or episode already stopped')
        if self._episode_mode in {'expert', 'external'}:
            raise RuntimeError('cannot mix external Solution and other selected execution modes')
        try:
            self._require_published_execution_info()
        except BaseException as error:
            self._latch_fault('public_execution_readiness', error, before_state=self.state)
            raise
        if getattr(solution, 'done', False) or getattr(solution, 'failed', False):
            raise RuntimeError('external Solution already stopped')
        try:
            proposal = solution.act(self.obs, self.info)
            from ..planners.contracts import ExpertAction
            if not isinstance(proposal, ExpertAction):
                raise TypeError('external Solution act() must return ExpertAction')
        except BaseException as error:
            self._latch_fault('external_solution_proposal', error, before_state=self.state)
            if self.binding.abort_solution_on_runtime_error:
                try:
                    solution.abort('runtime_error')
                except BaseException as abort_error:
                    add_note = getattr(error, 'add_note', None)
                    if callable(add_note):
                        add_note(f'external Solution abort after proposal failure also failed: {abort_error!r}')
            raise
        return self._step(proposal.action, proposal=proposal, observer_solution=solution)

    def switch_position_controller(self, candidate):
        """Replace the single Panda Position instance at the current real boundary.

        The existing Generic H5 v3 Recorder is required so the preparation,
        effective identity and boundary are observable. This operation never
        computes, applies, steps or appends a transition; the next ordinary
        ``step`` is the first opportunity for the new instance to control.
        """
        if self._closed:
            raise RuntimeError('cannot switch a closed selected environment')
        if self._execution_fault is not None:
            raise RuntimeError('cannot switch a faulted selected environment; reset() is required')
        if not getattr(self, 'position_profile', False) or self.dual_entity_position:
            raise RuntimeError('Controller instance switching is limited to the single Panda Position candidate')
        if self._stopped or self._position_episode_end is not None:
            raise RuntimeError('Controller switching requires a live, nonterminal episode')
        if getattr(self, '_pending_position_switch', None) is not None:
            raise RuntimeError('the current Controller switch must be applied by one complete step before another switch')
        if self.session is None or self._published_position_typed_state is None:
            raise RuntimeError('Controller switching requires a completed reset boundary')
        if self.state.control_step >= self.horizon:
            raise RuntimeError('Controller switching is not allowed at or beyond the horizon')

        recorder = self.recorder
        if (recorder is None or not recorder.active
                or recorder.config.schema_version != 'v3'):
            raise RuntimeError('Controller switching requires an active Generic H5 v3 recording')
        boundary = self._published_position_typed_state.view.boundary
        clock = self._published_position_typed_state.view.sample_clock
        if (self.typed_state is None
                or self.typed_state.view.boundary.boundary_id != boundary.boundary_id
                or self.state.control_step != boundary.control_step
                or self._published_position_state is None
                or self._published_position_state.control_step != boundary.control_step
                or self._published_position_state.simulation_time != self.state.simulation_time
                or clock.clock_domain != 'evaluation_boundary'
                or clock.sample_index != boundary.control_step
                or getattr(self.session, '_inner_interval_active', False)
                or getattr(self.session, '_position_target_in_flight', None) is not None):
            raise RuntimeError('Controller switching requires the last complete public control boundary')
        if (recorder.transition_count != boundary.control_step
                or recorder.observation_count != recorder.transition_count + 1
                or getattr(recorder, 'pending', None) is not None):
            raise RuntimeError('Controller switching requires a complete recorded T/T+1 boundary')

        current = self.position_profiles[0]
        from ..runtime.sessions.control import (
            _commit_position_profile_replacement,
            _prepare_position_profile_replacement,
        )

        prepared = _prepare_position_profile_replacement(
            self.session, current, candidate, self.position_plan, self.typed_state,
            scene=self.position_scene,
            joint_bindings=self.position_joint_bindings,
            frame_bindings=self.position_frame_bindings,
        )
        from dataclasses import asdict
        from ..trajectory.canonical.episode import BoundaryEventV1

        switch_id = uuid4().hex
        event = BoundaryEventV1(
            'boundary-event-v1', boundary.episode_id, recorder.transition_count,
            recorder.next_boundary_event_sequence(recorder.transition_count),
            f'controller-switch-{switch_id}', 'controller_instance_switch',
            'task_env.selected_reference.position_servo_v1',
            {
                'switch_id': switch_id,
                'request': {
                    'operation': 'replace_position_controller_instance',
                    'requested_profile_id': candidate.profile_id,
                    'requested_writer_id': candidate.writer_id,
                    'requested_controller_identity': candidate.identity,
                    'action_config': asdict(candidate.config),
                },
                'previous_controller': {
                    'profile_id': current.profile_id,
                    'writer_id': current.writer_id,
                    'controller_identity': current.identity,
                    'action_config': asdict(current.config),
                },
                'effective_controller': {
                    'profile_id': candidate.profile_id,
                    'writer_id': candidate.writer_id,
                    'controller_identity': candidate.identity,
                    'action_config': asdict(candidate.config),
                },
                'result': {
                    'preparation': 'validated',
                    'switch': 'effective',
                    'first_control_application': 'pending_next_step',
                },
                'effective_boundary': {
                    **boundary.to_mapping(), 'boundary_id': boundary.boundary_id,
                },
                'effective_clock': clock.to_mapping(),
                'binding_identity_hash': self.position_plan.identity_hash,
                'source_closure_digest': self.value['source'].source_closure_digest,
            },
        )
        event.validate()
        recorder.validate_boundary_event(event)

        before_state = self.state
        committed = False
        try:
            _commit_position_profile_replacement(self.session, prepared)
            committed = True
            self.position_profiles = (candidate,)
            self.controller = candidate
            self.value['controller'] = candidate
            recorder.add_boundary_event(event)
            self._pending_position_switch = {
                'switch_id': switch_id,
                'controller_identity': candidate.identity,
                'effective_boundary_id': boundary.boundary_id,
                'effective_control_step': boundary.control_step,
            }
        except BaseException as error:
            admitted_profiles = getattr(self.session, '_position_profiles_by_writer', None)
            if (not committed and isinstance(admitted_profiles, dict)
                    and admitted_profiles.get(candidate.writer_id) is candidate):
                committed = True
            if not committed:
                raise
            # If a later pointer projection failed after RuntimeSession admitted
            # the candidate, keep the Env and session owners aligned before latching.
            self.position_profiles = (candidate,)
            self.controller = candidate
            self.value['controller'] = candidate
            after_state = None
            readback_error = None
            try:
                after_state = self.session.snapshot()
                self.state = after_state
            except BaseException as snapshot_error:
                readback_error = f'{type(snapshot_error).__name__}: {snapshot_error}'
            fault = self._latch_fault(
                'position_controller_switch_record', error,
                before_state=before_state, after_state=after_state,
                interval_attempted=False, interval_completed=False,
                transition_status='not_assessed', readback_error=readback_error,
            )
            self._position_controller_switch_fault_receipt = {
                'switch_id': switch_id,
                'result': 'committed_but_effective_event_record_failed',
                'request': {
                    'operation': 'replace_position_controller_instance',
                    'requested_profile_id': candidate.profile_id,
                    'requested_writer_id': candidate.writer_id,
                    'requested_controller_identity': candidate.identity,
                    'action_config': asdict(candidate.config),
                },
                'previous_controller': {
                    'profile_id': current.profile_id,
                    'writer_id': current.writer_id,
                    'controller_identity': current.identity,
                    'action_config': asdict(current.config),
                },
                'effective_controller': {
                    'profile_id': candidate.profile_id,
                    'writer_id': candidate.writer_id,
                    'controller_identity': candidate.identity,
                    'action_config': asdict(candidate.config),
                },
                'previous_controller_identity': current.identity,
                'active_controller_identity': self.controller.identity,
                'effective_boundary': {
                    **boundary.to_mapping(), 'boundary_id': boundary.boundary_id,
                },
                'effective_clock': clock.to_mapping(),
                'preparation_succeeded': True,
                'switch_effective': True,
                'effective_event_recorded': False,
                'first_control_application': 'not_attempted',
                'execution_fault': fault.to_mapping(),
            }
            raise
        return event

    def _step_position_profile(self, request):
        """Run one source-bound Position interval through the selected lifecycle latch."""
        if self._execution_fault is not None:
            fault = self._execution_fault
            raise RuntimeError(
                'selected execution is faulted; reset() is required '
                f"(phase={fault.phase}, physical_progress={fault.physical_progress})"
            )
        if not getattr(self, 'position_profile', False) or self.session is None:
            raise RuntimeError('PositionServoV1 reset and RuntimeSession are required')
        if getattr(self, '_closed', False):
            raise RuntimeError('environment is closed')
        if self._stopped or self.state.control_step >= self.horizon:
            self._stopped = True
            raise RuntimeError('reset required or PositionServoV1 horizon is exhausted')
        from ..runtime.sessions.control import execute_position_control_interval

        before_state = self.state
        interval_attempted = False
        interval_completed = False
        transition_counts_before = self._recording_counts(self.recorder)
        record_append_attempted = False
        phase = 'position_control_preflight'
        try:
            interval_attempted = True
            phase = 'position_control_compute_apply_step'
            profiles = tuple(getattr(self, 'position_profiles', (self.controller,)))
            controller_profiles = profiles if len(profiles) == 2 else profiles[0]
            requirements = (
                self._position_requirements()
                if hasattr(self, 'position_profiles')
                else getattr(self.controller, 'requirements', None)
            )
            result = execute_position_control_interval(
                self.session, controller_profiles, self.position_plan, request, self.typed_state,
                scene=self.position_scene,
                joint_bindings=self.position_joint_bindings,
                frame_bindings=self.position_frame_bindings,
                requirements=requirements,
            )
            if self.dual_entity_position:
                position_records, self.state, self.typed_state = result
                canonical = target = applied = None
            else:
                canonical, target, applied, self.state, self.typed_state = result
                position_records = ((canonical, target, applied),)
            interval_completed = True
            self.feedback = None
            self.last_position_transition = (
                position_records if self.dual_entity_position else (canonical, target, applied)
            )
            phase = 'position_observation'
            self.obs, self.info, self.evaluation = self.observation(self.state)
            terminated = bool(self.evaluation.failure)
            truncated = self.state.control_step >= self.horizon
            self._stopped = bool(terminated or truncated)
            self._episode_mode = 'external'
            self._last_position_terminated = terminated
            self._last_position_truncated = truncated
            self._last_position_request = request
            if self.recorder is not None:
                phase = 'record_position_transition'
                record_append_attempted = True
                if self.dual_entity_position:
                    self._record_dual_position_transition(
                        request, position_records, terminated=terminated, truncated=truncated,
                    )
                else:
                    self._record_position_transition(
                        request, canonical, target, applied,
                        terminated=terminated, truncated=truncated,
                    )
            # Publish the boundary only after the complete step and any active
            # recorder append have succeeded. A partially advanced fault is
            # diagnostic evidence, never a synthetic T transition.
            self._published_position_state = self.state
            self._published_position_typed_state = self.typed_state
            self._published_position_obs = self.obs
            self._published_position_info = dict(self.info)
            self._published_position_evaluation = self.evaluation
            if terminated or truncated:
                self._position_episode_end = self._make_position_episode_end(
                    'task_terminal' if terminated else 'horizon_reached',
                    terminated=bool(terminated),
                    truncated=not bool(terminated),
                    bootstrap_allowed=not bool(terminated),
                )
                self.info['episode_end_v1'] = self._position_episode_end.to_mapping()
            return self.obs, float(self.evaluation.reward), terminated, truncated, self.info
        except BaseException as error:
            after_state = None
            readback_error = None
            if interval_attempted:
                try:
                    after_state = self.session.snapshot()
                    self.state = after_state
                except BaseException as snapshot_error:
                    readback_error = f'{type(snapshot_error).__name__}: {snapshot_error}'
            if (after_state is not None and before_state is not None
                    and after_state.control_step == before_state.control_step + 1):
                interval_completed = True
            self._latch_fault(
                phase, error, before_state=before_state, after_state=after_state,
                interval_attempted=interval_attempted,
                interval_completed=interval_completed,
                native_substeps_expected=self.artifact.timebase.control_substeps,
                transition_status=self._fault_transition_status(
                    self.recorder, transition_counts_before,
                    append_attempted=record_append_attempted,
                ),
                readback_error=readback_error,
            )
            raise

    def step_expert(self):
        if self._execution_fault is not None:
            fault = self._execution_fault
            raise RuntimeError(
                'selected execution is faulted; reset() is required '
                f"(phase={fault.phase}, physical_progress={fault.physical_progress})"
            )
        if self._stopped or self._episode_mode in {'external', 'external_solution'}:
            raise RuntimeError('reset required; external and expert execution cannot be mixed')
        if self.solution is None or getattr(self, 'position_profile', False):
            raise RuntimeError('selected PositionServoV1 profile does not provide expert execution')
        self._episode_mode = 'expert'
        if self.solution.done or self.solution.failed:
            raise RuntimeError('expert already stopped')
        if hasattr(self.solution, 'readiness_config'):
            try:
                self._require_published_execution_info()
            except BaseException as error:
                self._latch_fault('public_execution_readiness', error, before_state=self.state)
                raise
        try:
            proposal = self.solution.act()
        except BaseException as error:
            self._latch_fault('expert_proposal', error, before_state=self.state)
            if self.binding.abort_solution_on_runtime_error:
                try:
                    self.solution.abort('runtime_error')
                except BaseException as abort_error:
                    add_note = getattr(error, 'add_note', None)
                    if callable(add_note):
                        add_note(f'expert abort after proposal failure also failed: {abort_error!r}')
            raise
        return self._step(proposal.action, proposal=proposal, observer_solution=self.solution)

    def _step(self, action, *, proposal=None, observer_solution=None):
        if self._execution_fault is not None:
            fault = self._execution_fault
            raise RuntimeError(
                'selected execution is faulted; reset() is required '
                f"(phase={fault.phase}, physical_progress={fault.physical_progress})"
            )
        if self._stopped or self.session is None:
            raise RuntimeError('reset required or episode already stopped')
        try:
            vector = np.asarray(action, dtype=float)
            if vector.shape != (8,) or not np.isfinite(vector).all():
                raise ValueError('finite eight-dimensional absolute pose action required')
        except BaseException as error:
            if proposal is not None:
                self._latch_fault('expert_action_validation', error, before_state=self.state)
            raise
        request = RequestedAction('absolute_pose', 'world', 'quaternion_wxyz', tuple(map(float, vector)))
        if proposal is not None and observer_solution is None:
            observer_solution = self.solution
        requested_mode = (
            'external_solution' if proposal is not None and observer_solution is self._external_solution_owner
            else 'expert' if proposal is not None else 'external'
        )
        if self._episode_mode is not None and self._episode_mode != requested_mode:
            raise RuntimeError('cannot mix external actions with selected expert execution')
        self._episode_mode = requested_mode
        stage = proposal.stage if proposal is not None else 'external'
        diagnostics = dict(proposal.diagnostics) if proposal is not None else {}
        guard_samples = []
        substeps = []
        before_state = self.state
        transition_counts_before = self._recording_counts(self.recorder)
        phase = 'recorder_interval_begin'
        interval_attempted = False
        interval_completed = False
        record_append_attempted = False
        try:
            request_boundary = (
                self._execution_boundary(self.expert_execution_info())
                if not self.position_profile else None
            )
            if self.recorder is not None and self.binding.recorder_mode == 'execution':
                self.recorder.begin(self.state.control_step, self.artifact.timebase.physics_dt,
                                    self.artifact.timebase.control_substeps)
            phase = 'controller_compute'
            canonical, target = self.controller.compute(self.state, self.feedback, request)

            def observe(index, state, feedback, effective, applied, diag):
                substeps.append((index, effective, applied))
                if self.recorder is not None and self.binding.record_native_substeps:
                    self.recorder.applied_substep(index, state, feedback, effective, applied, diag)
                if proposal is not None and stage == 'close_gripper' and self.binding.capture_guard_samples:
                    _, info, _ = self.observation(state)
                    guard_samples.append(observer_solution.make_native_guard_sample(state, info, diag))
            if self.binding.interval_mode == 'native':
                phase = 'physics_step'
                interval_attempted = True
                self.state, target, applied, _ = self.session.step_control_interval(
                    target, self.controller, interval_observer=observe, arm_schedule=self.arm_schedule)
                interval_completed = True
            else:
                # Preserve historical P1.6 grouped control-interval stepping,
                # including the provider's boundary clock accumulation.
                phase = 'control_application'
                applied = self.session.apply_control(target)
                phase = 'physics_step'
                interval_attempted = True
                self.state = self.session.step()
                interval_completed = True
            phase = 'control_feedback'
            self.feedback = self.session.control_feedback(self.state)
            phase = 'observation'
            self.obs, self.info, self.evaluation = self.observation(self.state)
            if not self.position_profile:
                self._publish_execution_info(self.info)
                if canonical is not None and target is not None and applied is not None:
                    self._publish_control_application(
                        self.info, request, canonical, target, applied, request_boundary,
                    )
            terminated = bool(self.evaluation.failure)
            truncated = self.state.control_step >= self.horizon
            if proposal is not None:
                phase = 'solution_observation'
                extra = self.binding.observe_expert_kwargs(self, guard_samples)
                observer_solution.observe(
                    self.obs, self.evaluation.reward, terminated, truncated, self.info, **extra,
                )
                if hasattr(observer_solution, 'outcome_report'):
                    self.info.update(observer_solution.outcome_report())
                self.info.update(
                    selected_policy_execution_complete=bool(observer_solution.done),
                    selected_policy_execution_failed=bool(observer_solution.failed),
                    expert_failure_reason=observer_solution.failure_reason,
                )
                self._stopped = observer_solution.done or observer_solution.failed
            self._stopped = bool(self._stopped or terminated or truncated)
            if self.recorder is not None:
                phase = 'record_interval'
                record_append_attempted = True
                self._record_interval(request, canonical, target, applied, stage, diagnostics,
                                      terminated, truncated, substeps)
            return self.obs, float(self.evaluation.reward), terminated, truncated, self.info
        except BaseException as error:
            after_state = None
            readback_error = None
            if interval_attempted:
                try:
                    after_state = self.session.snapshot()
                    self.state = after_state
                except BaseException as snapshot_error:
                    readback_error = f'{type(snapshot_error).__name__}: {snapshot_error}'
            transition_status = self._fault_transition_status(
                self.recorder,
                transition_counts_before,
                append_attempted=record_append_attempted,
            )
            observer_count = (
                len(substeps) if self.binding.interval_mode == 'native' else None
            )
            recorder_count = self._recorder_substep_count(
                self.recorder, transition_counts_before
            )
            self._latch_fault(
                phase,
                error,
                before_state=before_state,
                after_state=after_state,
                interval_attempted=interval_attempted,
                interval_completed=interval_completed,
                observer_confirmed_substeps=observer_count,
                recorder_confirmed_substeps=recorder_count,
                native_substeps_expected=(
                    self.artifact.timebase.control_substeps
                    if self.binding.interval_mode == 'native'
                    else None
                ),
                transition_status=transition_status,
                readback_error=readback_error,
            )
            failed_solution = observer_solution if observer_solution is not None else self.solution
            if self.binding.abort_solution_on_runtime_error and failed_solution is not None:
                try:
                    failed_solution.abort('runtime_error')
                except BaseException as abort_error:
                    add_note = getattr(error, 'add_note', None)
                    if callable(add_note):
                        add_note(f'expert abort after execution fault also failed: {abort_error!r}')
            # An incomplete interval cannot be finalized as a valid trajectory.
            raise

    @staticmethod
    def _recording_counts(recorder):
        if recorder is None:
            return None
        transition_count = getattr(recorder, 'transition_count', None)
        observation_count = getattr(recorder, 'observation_count', None)
        if type(transition_count) is int and type(observation_count) is int:
            return transition_count, observation_count
        value = getattr(recorder, 'value', None)
        if isinstance(value, dict):
            return len(value.get('transitions', ())), len(value.get('boundaries', ()))
        transitions = getattr(recorder, 'transitions', None)
        boundaries = getattr(recorder, 'boundaries', None)
        if transitions is not None and boundaries is not None:
            return len(transitions), len(boundaries)
        return None

    @classmethod
    def _fault_transition_status(cls, recorder, before, *, append_attempted):
        if recorder is None:
            return 'not_recorded'
        if not append_attempted:
            return 'incomplete'
        after = cls._recording_counts(recorder)
        if before is not None and after == (before[0] + 1, before[1] + 1):
            if getattr(recorder, 'pending', None) is None:
                return 'valid'
        return 'rejected'

    @staticmethod
    def _recorder_substep_count(recorder, transition_counts_before=None):
        def confirmed_count(interval):
            if not isinstance(interval, dict):
                return None
            substeps = interval.get('substeps')
            if not isinstance(substeps, (list, tuple)):
                return None
            count = interval.get('native_step_count')
            if count is not None and (type(count) is not int or count != len(substeps)):
                return None
            return len(substeps)

        pending = getattr(recorder, 'pending', None)
        if isinstance(pending, dict):
            return confirmed_count(pending)
        value = getattr(recorder, 'value', None)
        if isinstance(value, dict) and transition_counts_before is not None:
            transitions = value.get('transitions', ())
            if len(transitions) == transition_counts_before[0] + 1:
                transition = transitions[-1]
                if not isinstance(transition, dict):
                    return None
                interval = transition.get('interval')
                return confirmed_count(interval)
        return None

    def close(self):
        if self._closed:
            return
        if not getattr(self, 'position_profile', False):
            if self.session is not None:
                self.session.close()
                self.session = None
            self._closed, self._stopped = True, True
            return
        first_error = None
        if self._published_position_state is not None:
            try:
                if self._position_episode_end is None:
                    self.stop('environment_close')
                if self.recorder is not None and getattr(self.recorder, 'active', False):
                    self.finish_recording(self._position_episode_end.outcome.end_reason)
            except BaseException as error:
                first_error = error
        try:
            if self.session is not None:
                self.session.close()
                self.session = None
        except BaseException as error:
            if first_error is None:
                first_error = error
        finally:
            self._closed, self._stopped = True, True
        if first_error is not None:
            raise first_error

    def _make_position_episode_end(
        self, end_reason, *, terminated, truncated, bootstrap_allowed,
        task_success=None, payload=None,
    ):
        from ..trajectory.canonical.episode import make_episode_end_v1

        typed = self._published_position_typed_state
        state = self._published_position_state
        if typed is None or state is None:
            raise RuntimeError('Position Stop requires a successfully returned reset boundary')
        boundary = typed.view.boundary
        details = {
            'control_step': int(state.control_step),
            'simulation_time_s': float(state.simulation_time),
            'state_boundary_id': boundary.boundary_id,
            'source_closure_digest': self.value['source'].source_closure_digest,
            'controller_identity': self.controller.identity,
            'profile_id': self.controller.profile_id,
        }
        if self.dual_entity_position:
            details['position_writers'] = tuple({
                'entity_id': profile.entity_id,
                'writer_id': profile.writer_id,
                'controller_identity': profile.identity,
            } for profile in self.position_profiles)
        if self._position_controller_switch_fault_receipt is not None:
            details['controller_switch_fault_receipt'] = dict(
                self._position_controller_switch_fault_receipt,
            )
        if self._pending_position_switch is not None:
            switch_application = {
                **self._pending_position_switch,
            }
            switch_application['status'] = (
                'not_attempted_before_episode_end'
                if (self._execution_fault is None
                    and int(state.control_step) == self._pending_position_switch['effective_control_step'])
                else 'not_confirmed_in_complete_transition'
            )
            last = getattr(self, 'last_position_transition', None)
            if (isinstance(last, tuple) and len(last) == 3
                    and getattr(last[1], 'controller_identity', None)
                    == self._pending_position_switch['controller_identity']
                    and getattr(last[1].source_boundary, 'boundary_id', None)
                    == self._pending_position_switch['effective_boundary_id']
                    and getattr(last[2], 'target_hash', None) == last[1].target.identity_hash):
                switch_application.update({
                    'status': 'target_ack_observed_but_transition_not_recorded',
                    'target_identity_hash': last[1].target.identity_hash,
                    'applied_target_hash': last[2].target_hash,
                    'observed_runtime_boundary': int(self.state.control_step),
                })
            details['pending_controller_switch_application'] = switch_application
        details.update(dict(payload or {}))
        success = (
            bool(self._published_position_evaluation.success)
            if task_success is None and self._published_position_evaluation is not None
            else task_success
        )
        event_sequence = 0
        if self.recorder is not None and getattr(self.recorder, 'active', False):
            event_sequence = self.recorder.next_boundary_event_sequence(int(state.control_step))
        return make_episode_end_v1(
            episode_id=boundary.episode_id,
            final_boundary=int(state.control_step),
            end_reason=end_reason,
            terminated=terminated,
            truncated=truncated,
            bootstrap_allowed=bootstrap_allowed,
            source='task_env.selected_reference.position_servo_v1',
            payload=details,
            event_sequence=event_sequence,
            task_success=success,
        )

    def stop(self, reason='external_stop'):
        """Finish the Position candidate at its last fully returned boundary."""

        if self._closed:
            raise RuntimeError('cannot stop a closed selected environment')
        if not getattr(self, 'position_profile', False):
            raise StageUnavailableError(
                'Stop/Outcome is only admitted for the PositionServoV1 candidate; '
                'legacy selected production-r1 behavior is unchanged'
            )
        if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
            raise ValueError('Stop reason must be a trimmed non-empty string')
        if self._position_episode_end is not None:
            return self._position_episode_end
        if self.session is None or self._published_position_typed_state is None:
            raise RuntimeError('reset() must complete before Stop')
        if self._execution_fault is not None:
            fault = self._execution_fault
            self._position_episode_end = self._make_position_episode_end(
                'execution_fault', terminated=False, truncated=True,
                bootstrap_allowed=False, task_success=None,
                payload={
                    'requested_reason': reason,
                    'fault': fault.to_mapping(),
                    'observed_runtime_clock': {
                        'control_step': int(self.state.control_step),
                        'simulation_time_s': float(self.state.simulation_time),
                    },
                },
            )
        else:
            self._position_episode_end = self._make_position_episode_end(
                'external_stop',
                terminated=False,
                truncated=True,
                bootstrap_allowed=True,
                payload={'requested_reason': reason},
            )
        self._stopped = True
        return self._position_episode_end

    def _boundary(self):
        from ..trajectory.canonical.contracts import BoundaryRecord
        return BoundaryRecord(self.state.control_step, self.state.simulation_time,
            self.state, self.feedback, self.controller.readiness(self.state, self.feedback),
            {k: float(v) for k, v in self.info['task_metrics'].items()},
            bool(self.evaluation.success), bool(self.evaluation.failure))

    def _owners(self):
        # Minimal recording coordinator receipt, explicitly not a D0 checkpoint.
        fields = {'_stage_index': 0, 'execution_mode': self._episode_mode,
                  'task_outcome': self.info}
        result = {'control_step': self.state.control_step, 'simulation_time': self.state.simulation_time,
            'artifact_hash': self.artifact.identity_hash, 'controller_identity': self.controller.identity,
            'solution_identity': self._active_solution_identity(), 'provider': self.provider,
            'owners': {'coordinator': {'version': 'selected-reference-observation-v1',
                'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'fields': {k: {'present': True, 'value': v} for k, v in fields.items()}}}}
        result['integrity_hash'] = digest(result)
        return result

    def start_recording(self, path):
        from ..trajectory.canonical.contracts import EpisodeMetadata
        from ..trajectory.canonical.execution import ExecutionRecorder
        from ..runtime.sessions.provenance import provider_build_identity
        from ..runtime.sessions import common as session_common
        if (self.session is None or self.state.control_step != 0 or self.recorder is not None
                or self._stopped or self._position_episode_end is not None):
            raise RuntimeError('recording starts exactly once at reset boundary')
        if getattr(self, 'position_profile', False):
            from ..recorders import RecorderConfig, TransitionRecorder

            path = Path(path)
            if path.suffix != '.h5':
                path = path.with_name(path.name + '.h5')
            if path.exists():
                raise FileExistsError(path)
            recorder = TransitionRecorder(RecorderConfig(
                schema_version='v3', max_transitions=max(self.horizon, 1),
            ))
            recorder.begin_episode(
                self.obs, dict(self._position_reset_info), self._position_record_metadata(),
            )
            self.recording_path = path
            self.recorder = recorder
            return
        path = Path(path)
        if path.exists():
            raise FileExistsError(path)
        self.recording_path = path
        config = self.value['resolved_configuration']
        source_provenance = {
            'construction': digest(config), 'adapter': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'interval_source': hashlib.sha256(Path(session_common.__file__).read_bytes()).hexdigest(),
            'resolved_configuration_json': json.dumps(config, sort_keys=True),
            'execution_configuration_json': json.dumps({'env_id': self.uid, 'provider': self.provider,
                'backend': 'cpu', 'horizon': self.horizon}, sort_keys=True),
        }
        if 'source_revision' in self.value:
            runtime_source = self.value['source']
            runtime_source_xml = runtime_source.scene_source.xml.encode()
            source_provenance.update({
                'geochora_revision': str(self.value['source_revision']),
                'artifact_identity': self.artifact.identity_hash,
                'controller_identity': self.controller.identity,
                'solution_identity': self._active_solution_identity(),
                'runtime_source_id': runtime_source.scene_source.source_id,
                'runtime_source_xml_sha256': hashlib.sha256(runtime_source_xml).hexdigest(),
            })
            if runtime_source.source_closure_digest is not None:
                source_provenance['runtime_source_closure_digest'] = runtime_source.source_closure_digest
            source_provenance.update({f"source_sha256:{name}": value
                for name, value in self.value.get('source_sha256', {}).items()})
        solution_identity = self._active_solution_identity()
        metadata = EpisodeMetadata('canonical-trajectory-metadata-v0', self.artifact.identity_hash,
            self.sample, self.realized, self.execution,
            {'build': str(provider_build_identity(self.provider))},
            source_provenance,
            self.artifact.timebase, self.controller.identity, solution_identity,
            digest({'readiness': solution_identity}), digest(METADATA), self.sample.task_seed, 'regression')
        owners = self._owners()
        recipe = {'factory': type(self).__module__ + '.' + type(self).__name__,
            'artifact': self.artifact.to_mapping(), 'resolved_configuration': config,
            'execution_configuration': {'env_id': self.uid, 'provider': self.provider, 'backend': 'cpu', 'horizon': self.horizon},
            'stages': ['reference'], 'cadence': 'selected-native-stream-v1',
            'owner_schema': {k: {'version': v['version'], 'source_sha256': v['source_sha256'],
                'fields': list(v['fields'])} for k, v in owners['owners'].items()},
            'd0_reconstructible': False, 'qualification': 'NOT_REQUALIFIED',
            'owner_snapshot_scope': 'observation receipt; controller/expert restoration not implemented'}
        if self.binding.recorder_mode == 'canonical':
            from ..trajectory.canonical.contracts import CanonicalRecorder
            self.recorder = CanonicalRecorder(metadata, self._boundary())
            return
        self.recorder = ExecutionRecorder(metadata, recipe, content_fields=('task_outcome',))
        self.recorder.boundary(self._boundary(), owners, 'reference', self.info['task_metrics'])

    def _record_interval(self, request, canonical, target, applied, stage, diagnostics,
                         terminated, truncated, substeps):
        from ..trajectory.canonical.contracts import TransitionRecord
        count = self.artifact.timebase.control_substeps
        if self.binding.record_native_substeps and (len(substeps) != count or [x[0] for x in substeps] != list(range(count))):
            raise ValueError('missing native application receipts')
        if (self.binding.record_native_substeps and self.recorder is not None
                and self.binding.recorder_mode == 'execution'):
            pending = getattr(self.recorder, 'pending', None)
            recorded = pending.get('substeps') if isinstance(pending, dict) else None
            start_step = self.state.control_step - 1
            expected_native_indices = [start_step * count + index + 1 for index in range(count)]
            required_fields = {
                'index', 'native_step_index', 'native_start_time', 'state',
                'feedback', 'target', 'applied', 'updated',
            }
            if (
                not isinstance(pending, dict)
                or type(pending.get('control_step')) is not int
                or pending.get('control_step') != start_step
                or pending.get('physics_dt') != self.artifact.timebase.physics_dt
                or type(pending.get('control_substeps')) is not int
                or pending.get('control_substeps') != count
                or type(pending.get('native_step_count')) is not int
                or pending.get('native_step_count') != count
                or not isinstance(recorded, list)
                or len(recorded) != count
                or any(not isinstance(item, dict) or not required_fields.issubset(item)
                       for item in recorded)
                or any(type(item['index']) is not int or type(item['native_step_index']) is not int
                       for item in recorded)
                or [item['index'] for item in recorded] != list(range(count))
                or [item['native_step_index'] for item in recorded] != expected_native_indices
            ):
                raise ValueError('incomplete native Recorder application receipts')
        wait = bool(diagnostics.get('readiness_hold', False))
        transition = TransitionRecord(request, canonical, target, applied, float(self.evaluation.reward),
            terminated, truncated, stage, {k: json.dumps(v, sort_keys=True) for k, v in diagnostics.items()}, not wait, wait)
        if self.binding.recorder_mode == 'canonical':
            self.recorder.append(transition, self._boundary())
            return
        self.recorder.append(transition, self._boundary(), self._owners(), 'reference',
            {'observed_native_substeps': len(substeps), 'control_step': self.state.control_step},
            self.info['task_metrics'])

    def finish_recording(self, reason):
        if getattr(self, 'position_profile', False):
            from ..recorders import load_structured_control_records_h5
            if self.recorder is None or not getattr(self.recorder, 'active', False):
                raise RuntimeError('no active recording')
            if self._position_episode_end is None:
                self.stop(str(reason))
            episode_end = self._position_episode_end
            outcome = episode_end.outcome
            allowed_reasons = {
                outcome.end_reason,
                str(episode_end.boundary_event.payload.get('requested_reason', '')),
            }
            if outcome.end_reason == 'horizon_reached':
                allowed_reasons.add('horizon')
            if str(reason) not in allowed_reasons:
                raise ValueError('recording finalization reason disagrees with EpisodeOutcome')

            transition_count = self.recorder.transition_count
            if transition_count != outcome.final_boundary:
                raise RuntimeError(
                    'recording T does not match the last complete Position boundary; '
                    'an incomplete interval cannot be finalized'
                )
            trajectory = self.recorder.end_episode(
                outcome.end_reason,
                outcome=outcome,
                end_event=episode_end.boundary_event,
            )
            output = self.recorder.save_h5(self.recording_path.parent, self.recording_path.name)
            loaded = load_structured_control_records_h5(output)
            if (loaded['transition_count'] != trajectory.transition_count
                    or loaded['observation_count'] != len(trajectory.observations)
                    or loaded['outcome'] != outcome):
                raise ValueError('PositionServoV1 Generic H5 v3 readback mismatch')
            return {
                'schema_id': 'task-env-h5', 'schema_version': 'v3',
                'transition_count': loaded['transition_count'],
                'observation_count': loaded['observation_count'],
                'outcome': outcome.to_mapping(), 'path': str(output),
            }
        from ..trajectory.canonical.streaming import save_streaming, verify_roundtrip
        if self.recorder is None or getattr(self.recorder, 'frozen', getattr(self.recorder, '_frozen', False)):
            raise RuntimeError('no active recording')
        if self.binding.recorder_mode == 'canonical' and self._execution_fault is not None:
            raise RuntimeError(
                'cannot finalize a faulted selected recording as a complete trajectory; '
                'reset is required'
            )
        value = self.recorder.freeze(reason)
        if self.binding.recorder_mode == 'canonical':
            from ..trajectory.canonical.h5 import save, load
            save(self.recording_path, value)
            identical = load(self.recording_path).to_mapping() == value.to_mapping()
            if not identical:
                raise ValueError('P1.6 canonical outer trajectory roundtrip mismatch')
            return {'logical_mapping_exact': identical,
                    'scope': 'canonical-v0 outer boundary; no native-substep or D0 claim'}
        save_streaming(self.recording_path, value)
        return verify_roundtrip(self.recording_path, value)

    def _position_record_reset_info(self):
        plan = self.value['reset_plan']
        boundary = self.typed_state.view.boundary
        return {
            'seed': int(plan.reset_sample.task_seed),
            'options': {},
            'reset_sample_id': plan.reset_sample.sample_id,
            'reset_plan_identity_hash': plan.identity_hash,
            'role_binding_identity_hash': plan.role_binding.identity_hash,
            'state_boundary_identity': boundary.to_mapping(),
            'state_boundary_id': boundary.boundary_id,
            'state_sample_clock': self.typed_state.view.sample_clock.to_mapping(),
            'source_closure_digest': self.value['source'].source_closure_digest,
        }

    def _position_record_metadata(self):
        from dataclasses import asdict

        profile = self.controller
        action_schema = profile.controller_binding().action_schema
        action_contract = asdict(action_schema)
        position_profiles = self.position_profiles
        if self.dual_entity_position:
            action_components = tuple(
                f'{writer_profile.entity_id}/{component}'
                for writer_profile in position_profiles
                for component in writer_profile.controller_binding().action_schema.components
            )
            action_contract.update({
                'schema_id': 'panda-position-dual-entity-action-v1',
                'schema_version': 'structured-action-schema-v1',
                'components': action_components,
            })
        observation_leaf_specs = [
            {'path': 'state.ee_pose', 'semantic': 'hand_origin_tcp_pose'},
            {'path': 'state.joint_position', 'semantic': 'required_panda_joint_position'},
            {'path': 'state.hand_pose', 'semantic': 'provider_measured_panda_hand_pose'},
            {'path': 'state.boundary_identity_sha256', 'semantic': 'state_boundary_identity_sha256'},
        ]
        if self.dual_entity_position:
            for writer_profile in position_profiles:
                observation_leaf_specs.extend((
                    {'path': f'state.entities.{writer_profile.entity_id}.joint_position',
                     'semantic': 'entity_qualified_required_joint_position'},
                    {'path': f'state.entities.{writer_profile.entity_id}.hand_pose',
                     'semantic': 'entity_qualified_provider_measured_hand_pose'},
                ))
        observation_leaf_specs.extend(
            {'path': f'privileged_state.{key}_body_pose', 'semantic': 'scene_body_pose'}
            for _, key in self.binding.object_poses
        )
        env_metadata = {
            'env_name': 'SelectedReferenceEnv.PositionServoV1',
            'task_name': self.artifact.task_id,
            'task_version': self.artifact.artifact_version,
            'scene_uid': self.position_scene.scene_id,
            'agent_uids': tuple(item.entity_id for item in position_profiles),
            'physics_dt': self.artifact.timebase.physics_dt,
            'control_substeps': self.artifact.timebase.control_substeps,
            'control_frequency': 1.0 / self.artifact.timebase.control_dt,
            'action_schema': action_contract,
            'observation_schema': {'leaf_specs': observation_leaf_specs},
            'reference_profile': {
                'profile_id': profile.profile_id,
                'writer_id': profile.writer_id,
                'controller_identity': profile.identity,
                'control_binding_plan_identity_hash': self.position_plan.identity_hash,
                'task_artifact_identity_hash': self.artifact.identity_hash,
                'scene_identity_hash': self.position_scene.identity_hash,
                'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
                'reset_sample_id': self.value['reset_plan'].reset_sample.sample_id,
                'source_closure_digest': self.value['source'].source_closure_digest,
                'tcp_profile': profile.tcp_profile.to_mapping(),
                'force_feedback': 'not_consumed',
            },
        }
        universal_components = tuple(action_schema.components)
        if self.dual_entity_position:
            universal_components = action_components
        universal_schema = {
            'version': 'panda-position-servo-universal-action-v1',
            'dimension': len(universal_components),
            'components': universal_components,
        }
        return {
            'env_metadata': env_metadata,
            'universal_action_schema': universal_schema,
            'resolved_config': {
                'provider': self.provider, 'backend': 'cpu', 'horizon': self.horizon,
                'controller_profile': profile.profile_id,
            },
            'candidate_identity': {
                'task_artifact_identity_hash': self.artifact.identity_hash,
                'source_closure_digest': self.value['source'].source_closure_digest,
                'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
            },
        }
        if self.dual_entity_position:
            env_metadata['candidate_identity']['scene_identity_hash'] = self.position_scene.identity_hash
            env_metadata['reference_profile']['writers'] = tuple({
                'entity_id': item.entity_id,
                'profile_id': item.profile_id,
                'writer_id': item.writer_id,
                'controller_identity': item.identity,
                'required_state': item.requirements.to_mapping(),
            } for item in position_profiles)
            env_metadata['resolved_config']['controller_profiles'] = tuple(
                item.profile_id for item in position_profiles
            )

    def _record_position_transition(self, request, canonical, target, applied, *, terminated, truncated):
        from ..trajectory.canonical.episode import StructuredControlTransitionV1

        schema = self.controller.controller_binding().action_schema
        groups = {(group.entity_id, group.group_id): group for group in request.groups}
        arm = groups[('panda-main', 'arm')]
        gripper = groups[('panda-main', 'gripper')]
        action_values = np.asarray((*arm.values, *gripper.values), dtype=np.float32)
        target_payload = target.target.to_mapping()
        target_hash = target.target.identity_hash
        applied_payload = applied.to_mapping()
        canonical_action = {
            **canonical.to_mapping(),
            'position_target_v1': target.to_mapping(),
            'position_target_identity_hash': target.identity_hash,
        }
        pending_switch = self._pending_position_switch
        if pending_switch is not None:
            if (target.controller_identity != pending_switch['controller_identity']
                    or target.source_boundary.boundary_id != pending_switch['effective_boundary_id']):
                raise ValueError('first post-switch target does not match the committed Controller/boundary')
            canonical_action['controller_switch_application'] = {
                'switch_id': pending_switch['switch_id'],
                'status': 'target_and_applied_ack_recorded',
                'controller_identity': target.controller_identity,
                'effective_boundary_id': pending_switch['effective_boundary_id'],
                'target_identity_hash': target.target.identity_hash,
                'applied_target_hash': applied.target_hash,
            }
        control = StructuredControlTransitionV1(
            'structured-control-transition-v1', request, ({
                'writer_id': self.controller.writer_id,
                'action_schema_id': schema.schema_id,
                'components': tuple(schema.components),
                'groups': (
                    {'entity_id': 'panda-main', 'group_id': 'arm',
                     'action_components': tuple(schema.components[:7])},
                    {'entity_id': 'panda-main', 'group_id': 'gripper',
                     'action_components': (schema.components[7],)},
                ),
                'requested_action': canonical.requested.to_mapping(),
                'canonical_action': canonical_action,
                'controller_target': {
                    'schema_version': target.target.schema_version,
                    'payload': target_payload, 'identity_hash': target_hash,
                },
                'applied_control': {
                    'schema_version': applied.schema_version,
                    'payload': applied_payload, 'target_hash': applied.target_hash,
                },
            },),
        )
        control.validate()
        self.recorder.append_transition(
            action_values, action_values, self.obs, float(self.evaluation.reward),
            bool(self.evaluation.success), bool(terminated), bool(truncated), self.info,
            structured_control=control,
        )
        if pending_switch is not None:
            self._pending_position_switch = None

    def _record_dual_position_transition(self, request, position_records, *, terminated, truncated):
        """Store both Entity writers in the existing Generic H5 v3 transition."""
        from ..trajectory.canonical.episode import StructuredControlTransitionV1

        groups = {(group.entity_id, group.group_id): group for group in request.groups}
        expected_groups = {
            (profile.entity_id, group_id)
            for profile in self.position_profiles for group_id in ('arm', 'gripper')
        }
        if set(groups) != expected_groups or len(position_records) != 2:
            raise ValueError('dual Position recording requires both groups for both admitted Entities')
        action_values = np.asarray(tuple(
            value
            for group_key in sorted(groups)
            for value in groups[group_key].values
        ), dtype=np.float32)
        records_by_writer = {target.writer_id: (canonical, target, applied)
                             for canonical, target, applied in position_records}
        writer_controls = []
        for profile in self.position_profiles:
            canonical, bound_target, applied = records_by_writer[profile.writer_id]
            schema = profile.controller_binding().action_schema
            writer_controls.append({
                'writer_id': profile.writer_id,
                'action_schema_id': schema.schema_id,
                'components': tuple(schema.components),
                'groups': (
                    {'entity_id': profile.entity_id, 'group_id': 'arm',
                     'action_components': tuple(schema.components[:7])},
                    {'entity_id': profile.entity_id, 'group_id': 'gripper',
                     'action_components': (schema.components[7],)},
                ),
                'requested_action': canonical.requested.to_mapping(),
                'canonical_action': {
                    **canonical.to_mapping(),
                    'position_target_v1': bound_target.to_mapping(),
                    'position_target_identity_hash': bound_target.identity_hash,
                },
                'controller_target': {
                    'schema_version': bound_target.target.schema_version,
                    'payload': bound_target.target.to_mapping(),
                    'identity_hash': bound_target.target.identity_hash,
                },
                'applied_control': {
                    'schema_version': applied.schema_version,
                    'payload': applied.to_mapping(),
                    'target_hash': applied.target_hash,
                },
            })
        control = StructuredControlTransitionV1(
            'structured-control-transition-v1', request, tuple(writer_controls),
        )
        control.validate()
        self.recorder.append_transition(
            action_values, action_values, self.obs, float(self.evaluation.reward),
            bool(self.evaluation.success), bool(terminated), bool(truncated), self.info,
            structured_control=control,
        )
