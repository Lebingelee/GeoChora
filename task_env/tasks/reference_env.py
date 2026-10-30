"""Explicit selected-reference adapter, delegating task semantics and policies.

This adapter owns one scalar CPU session. It defines no TaskArtifact or task
success predicate. Expert execution and external-action execution cannot be
mixed in one episode. Rendering and legacy TaskEnv configuration are rejected.
"""
from dataclasses import dataclass
from collections import OrderedDict
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


def _boundary_interval_clock_tolerance(start_time_s, end_time_s, expected_dt_s,
                                       physics_dt_s, native_steps):
    """Bound binary clock drift from native increments plus boundary subtraction."""
    clock_ulp = max(
        math.ulp(float(start_time_s)), math.ulp(float(end_time_s)),
        math.ulp(float(expected_dt_s)), math.ulp(float(physics_dt_s)),
    )
    return (int(native_steps) + 2) * clock_ulp


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
    native_sample_factory: Callable | None = None
    native_interval_receipt_factory: Callable | None = None
    control_request_required: bool = False
    expert_uses_public_observation: bool = False
    build_external: Callable | None = None
    validate_external_solution: Callable | None = None
    runtime_episode_identity: bool = False
    build_gripper_cadence_diagnostic: Callable | None = None

    def __post_init__(self):
        if self.interval_mode not in {"grouped", "native"}:
            raise ValueError("unknown selected control-interval requirement")
        if self.recorder_mode not in {"canonical", "execution"}:
            raise ValueError("unknown selected recording requirement")
        if not self.object_poses:
            raise ValueError("selected task binding requires an observation pose")
        if (self.build_external is None) != (self.validate_external_solution is None):
            raise ValueError('external Solution construction and validation must be supplied together')
        if (self.native_sample_factory is None) != (self.native_interval_receipt_factory is None):
            raise ValueError('native sample and interval receipt factories must be supplied together')
        if self.control_request_required and self.native_sample_factory is None:
            raise ValueError('native controller requests require the selected native sample contract')


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
        camera_observation_config=None, execution_spec=None,
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
        if execution_spec is not None:
            from ..artifacts import ExecutionSpecV1
            if type(execution_spec) is not ExecutionSpecV1:
                raise TypeError('versioned Position candidate requires ExecutionSpecV1')
            execution_spec.validate()
            if (provider, backend) != (
                    execution_spec.physics_provider, execution_spec.physics_backend):
                raise ValueError('Position candidate provider/backend differs from ExecutionSpecV1')
        env = candidate_type(
            provider=provider, backend=backend, horizon=horizon, _binding=binding,
            camera_observation_config=camera_observation_config,
            _execution_spec_v1=execution_spec,
        )
        profiles = env.position_profiles
        if (not profiles or len(profiles) > 2
                or any(not isinstance(profile, PandaPositionServoProfileV1) for profile in profiles)
                or len({profile.writer_id for profile in profiles}) != len(profiles)
                or len({profile.entity_id for profile in profiles}) != len(profiles)):
            env.close()
            raise TypeError('candidate binding did not construct one or two Entity-bound PositionServoV1 profiles')
        if camera_observation_config is not None and len(profiles) != 1:
            env.close()
            raise ValueError('R04a camera observation is bounded to the existing single Panda Position source')
        return env

    @classmethod
    def from_leaf_position_candidate(cls, binding, *, provider='mujoco', backend='cpu', horizon=64,
                                     fixed_attachment=False):
        """Construct the explicitly opted-in R02c Arm/Hand leaf candidate."""
        if not isinstance(binding, ReferenceTaskBinding):
            raise TypeError('leaf Position candidate requires the existing ReferenceTaskBinding')
        if provider != 'mujoco' or backend != 'cpu':
            raise ValueError('R02c leaf Position candidate is limited to MuJoCo CPU')
        if fixed_attachment:
            candidate_type = type('AttachedLeafSelectedReferenceEnv', (cls,),
                                  {'uid': 'r03c-attached-entity-leaf-candidate-v1'})
        else:
            candidate_type = cls
        if not fixed_attachment and not hasattr(cls, 'uid'):
            candidate_type = type('LeafPositionSelectedReferenceEnv', (cls,),
                                  {'uid': 'r02c-independent-position-leaf-candidate-v1'})
        env = candidate_type(provider=provider, backend=backend, horizon=horizon,
                             _binding=binding, _leaf_position_candidate=True,
                             _fixed_attachment_leaf_position_candidate=fixed_attachment)
        if not getattr(env, 'leaf_position_profile', False):
            env.close()
            raise TypeError('leaf candidate binding did not provide an effective compiled leaf plan')
        if bool(getattr(env, 'fixed_attachment_leaf_position_profile', False)) != bool(fixed_attachment):
            env.close()
            raise TypeError('leaf candidate attachment opt-in was not preserved by the selected environment')
        return env

    def _bind_selected_controller(self, value):
        from ..controllers.canonical.position_profile import PandaPositionServoProfileV1

        leaf_plan = value.get('leaf_plan')
        if leaf_plan is not None:
            from ..controllers.canonical.leaf_plan import EffectiveLeafPlanV1
            if type(leaf_plan) is not EffectiveLeafPlanV1 or not leaf_plan._compiled:
                raise TypeError('leaf Position route requires a compiled EffectiveLeafPlanV1')
            if (leaf_plan.provider_name, leaf_plan.backend) != (self.provider, self.backend):
                raise ValueError('leaf plan provider/backend differs from the selected environment')
            self.leaf_position_profile = True
            self.leaf_plan = leaf_plan
            self.position_profiles = ()
            self.position_profile = True
            self.controller = None
            return
        self.leaf_position_profile = False
        self.leaf_plan = None

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

    def __init__(self, *, provider='geophys', backend='cpu', horizon=6000,
                 _binding=None, _diagnostic_gripper_control_hz=None,
                 camera_observation_config=None, _leaf_position_candidate=False,
                 _fixed_attachment_leaf_position_candidate=False,
                 _execution_spec_v1=None):
        if type(horizon) is not int or not 1 <= horizon <= 6000:
            raise ValueError('selected reference horizon must be an integer in [1, 6000]')
        if camera_observation_config is not None:
            from ..observations.canonical_camera.consumer import CameraObservationConfigV1

            if not isinstance(camera_observation_config, CameraObservationConfigV1):
                raise TypeError('camera observation opt-in requires CameraObservationConfigV1')
            camera_observation_config.validate_production_envelope()
            camera_observation_config.capacity(horizon)
        if _binding is not None:
            if not isinstance(self, SelectedReferenceEnv) or not isinstance(_binding, ReferenceTaskBinding):
                raise TypeError('explicit Position binding is only admitted by SelectedReferenceEnv')
            self.binding = _binding
        self.leaf_position_profile = False
        self.fixed_attachment_leaf_position_profile = bool(_fixed_attachment_leaf_position_candidate)
        if _leaf_position_candidate and (provider, backend) != ('mujoco', 'cpu'):
            raise ValueError('leaf Position candidate admits MuJoCo CPU only')
        if _fixed_attachment_leaf_position_candidate and not _leaf_position_candidate:
            raise ValueError('fixed Attachment leaf route requires the explicit leaf Position opt-in')
        if not isinstance(self.binding, ReferenceTaskBinding):
            raise TypeError('selected reference requires an explicit task binding')
        if _execution_spec_v1 is not None:
            from ..artifacts import ExecutionSpecV1
            if type(_execution_spec_v1) is not ExecutionSpecV1:
                raise TypeError('versioned selected construction requires ExecutionSpecV1')
            _execution_spec_v1.validate()
            if (provider, backend) != (
                    _execution_spec_v1.physics_provider, _execution_spec_v1.physics_backend):
                raise ValueError('selected construction provider/backend differs from ExecutionSpecV1')
            execution_route = (
                _execution_spec_v1.physics_provider, _execution_spec_v1.physics_backend,
                _execution_spec_v1.physics_device, _execution_spec_v1.determinism_mode,
                _execution_spec_v1.physics_profile,
            )
            allowed_versioned_routes = {
                ('isaacsim', 'cuda', 'cuda:0', 'best_effort', 'physx-gpu-f03-s1'),
                ('isaacsim', 'cuda', 'cuda:0', 'best_effort', 'isaac-gpu-physx-f04-position-v1'),
                ('geophys', 'cpu', 'cpu', 'best_effort', 'geophys-usd-position-f05-s1-v1'),
            }
            if execution_route not in allowed_versioned_routes:
                raise ValueError('versioned Position construction has an unsupported provider execution route')
        self._declared_execution_spec_v1 = _execution_spec_v1
        if _diagnostic_gripper_control_hz is None:
            if (_execution_spec_v1 is None
                    and (provider not in {'geophys', 'mujoco'} or backend != 'cpu')):
                raise ValueError('selected reference currently admits GeoPhys/MuJoCo scalar CPU only')
            self._diagnostic_profile = None
            build_value = lambda: self.binding.build(provider)
        else:
            if (provider != 'geophys' or backend not in {'cpu', 'cuda'}
                    or type(_diagnostic_gripper_control_hz) is not int
                    or _diagnostic_gripper_control_hz not in {100, 500}
                    or self.binding.build_gripper_cadence_diagnostic is None):
                raise ValueError(
                    'gripper cadence diagnostic requires the opted-in GeoPhys NutAssembly binding, '
                    'CPU/CUDA, and 100/500 Hz'
                )
            self._diagnostic_profile = 'nutassembly-gripper-cadence-v1'
            self._diagnostic_gripper_control_hz = _diagnostic_gripper_control_hz
            build_value = lambda: self.binding.build_gripper_cadence_diagnostic(
                provider, backend, _diagnostic_gripper_control_hz, True,
            )
        self.provider, self.backend, self.horizon = provider, backend, horizon
        self._execution_fault = None
        try:
            self.value = build_value()
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
        if camera_observation_config is not None and not self.position_profile:
            raise ValueError('the R04a camera consumer is admitted only by the existing Position candidate')
        self.camera_observation_config = camera_observation_config
        self._camera_consumer = None
        self._camera_session_factory = None
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
            elif self.fixed_attachment_leaf_position_profile and self.leaf_plan is not None:
                state_spaces['entities'] = Dict({
                    'panda-arm': Dict({
                        'joint_position': Box(-np.inf, np.inf, (7,), dtype=np.float32),
                        'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
                    }),
                    'panda-hand': Dict({
                        'joint_position': Box(-np.inf, np.inf, (2,), dtype=np.float32),
                        'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
                    }),
                })
        observation_spaces = OrderedDict((
            ('state', Dict(state_spaces)),
            ('privileged_state', Dict({
                k + '_body_pose': Box(-np.inf, np.inf, (1, 7), dtype=np.float32)
                for k in keys
            })),
        ))
        if camera_observation_config is not None:
            from ..observations.state import camera_observation_field_specs
            from ..environment.types import ObservationFieldSpec, ObservationSchema

            camera_groups = OrderedDict((name, OrderedDict()) for name in ('rgb', 'depth', 'entity_mask'))
            for field in camera_observation_field_specs(camera_observation_config):
                group, camera_id = field.name.split('.', 1)
                if group == 'rgb':
                    camera_groups[group][camera_id] = Box(0.0, 1.0, field.shape, dtype=np.float32)
                elif group == 'depth':
                    camera_groups[group][camera_id] = Box(0.0, np.inf, field.shape, dtype=np.float32)
                else:
                    camera_groups[group][camera_id] = Box(
                        0, np.iinfo(np.uint32).max, field.shape, dtype=np.uint32,
                    )
            observation_spaces.update((name, Dict(values)) for name, values in camera_groups.items())
            schema_fields = [
                ObservationFieldSpec('state.ee_pose', (7,), 'float32', 'hand-origin TCP pose',
                                     'm + unit quaternion', 'world'),
                ObservationFieldSpec('state.joint_position', (9,), 'float32',
                                     'required Panda joint positions', 'rad + m', 'canonical joint coordinates'),
                ObservationFieldSpec('state.hand_pose', (7,), 'float32',
                                     'provider-measured Panda hand pose', 'm + unit quaternion', 'world'),
                ObservationFieldSpec('state.boundary_identity_sha256', (32,), 'uint8',
                                     'state boundary identity digest', 'uint8[0,255]', 'identity'),
            ]
            schema_fields.extend(
                ObservationFieldSpec(
                    f'privileged_state.{key}_body_pose', (1, 7), 'float32',
                    f'{key} measured world pose', 'm + unit quaternion', 'world',
                ) for _, key in self.binding.object_poses
            )
            schema_fields.extend(camera_observation_field_specs(camera_observation_config))
            self.camera_observation_schema = ObservationSchema(
                'position-camera-observation-v1', tuple(schema_fields),
                groups=('state', 'privileged_state', 'rgb', 'depth', 'entity_mask'),
            )
            self.metadata['observation_schema'] = {
                'schema_version': 'position-camera-observation-v1',
                'leaf_specs': tuple({
                    'path': field.name,
                    'shape': field.shape,
                    'dtype': field.dtype,
                    'semantic': field.semantic,
                    'unit': field.unit,
                    'frame': field.frame,
                    'time_reference': field.time_reference,
                } for field in self.camera_observation_schema.fields),
            }
            self.metadata['camera_observation_schema'] = 'camera-observation-boundary-v1'
            self.metadata['info_schema'] = {
                'camera_observation_v1': {
                    'schema_version': 'camera-observation-boundary-v1',
                    'required': True,
                    'same_boundary_as_observation': True,
                },
            }
        self.observation_space = Dict(observation_spaces)
        self.session = None
        self._external_solution_owner = None
        self._active_native_interval_receipt = None
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

        if getattr(self, 'leaf_position_profile', False):
            requirements = tuple(
                requirement
                for entry in self.leaf_plan.leaves
                for requirement in entry.binding.required_state.state_requirements.requirements
            )
            return StateRequirements(
                'state-requirements-v1', 'controller',
                ('r03c-attached-entity-position-leaves-v1'
                 if self.fixed_attachment_leaf_position_profile
                 else 'r02c-independent-position-leaves-v1'),
                requirements,
            )

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
        previous_session_close_attempted = False
        phase = 'camera_reset_close'
        try:
            self._close_camera_consumer()
            phase = 'reset_close'
            if previous_session is not None:
                previous_session_close_attempted = True
                previous_session.close()
            phase = 'selected_reconstruction'
            # A new construction resets all controller/arm-hold/servo owner memory.
            if self._diagnostic_profile is not None:
                self.value = self.binding.build_gripper_cadence_diagnostic(
                    self.provider, self.backend, self._diagnostic_gripper_control_hz,
                    external_solution is None,
                )
            else:
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
            versioned_execution = self.value.get('execution_spec_v1')
            if versioned_execution is not None:
                from ..artifacts import ExecutionSpecV1
                if (type(versioned_execution) is not ExecutionSpecV1
                        or self._declared_execution_spec_v1 is None
                        or versioned_execution.identity_hash != self._declared_execution_spec_v1.identity_hash):
                    raise ValueError('SelectedReferenceEnv rebuild changed its declared ExecutionSpecV1')
                self.execution = versioned_execution
            else:
                if self._declared_execution_spec_v1 is not None:
                    raise ValueError('SelectedReferenceEnv rebuild dropped its declared ExecutionSpecV1')
                self.execution = ExecutionSpec(self.provider, PROFILE, 'none', self.backend, 0, 'strict')
            phase = 'session_materialization'
            if self.position_profile:
                from ..runtime.sessions.control import (
                    ControlBindingPlanV1,
                    compile_control_binding_plan,
                )
                self.position_scene = self.value['source'].scene_definition
                self.position_plan = self.value.get('controller_binding_plan')
                if self.leaf_position_profile:
                    if self.position_plan is not None:
                        raise ValueError('leaf route cannot carry a legacy ControllerBindingPlan')
                else:
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
                    if joint.kind in {'revolute', 'continuous', 'prismatic'}
                }
                from ..runtime.sessions.source import UsdRuntimeSourceV1
                if type(self.value['source']) is UsdRuntimeSourceV1:
                    # Reset poses are keyed by their canonical Frame semantic
                    # name. Resolve each such key through the already-bound
                    # TaskArtifact FrameReference to the unique Scene floating
                    # Joint whose child frame it names; never infer a Joint ID
                    # from a provider/native string.
                    for reset_frame_name in self.value['source'].free_joints:
                        frame_reference = self.artifact.legacy_frame_bindings.get(reset_frame_name)
                        if frame_reference is None:
                            raise ValueError('USD free-body reset key lacks an Artifact Frame binding')
                        candidates = tuple(
                            joint
                            for articulation in self.position_scene.articulations or ()
                            if articulation.entity_id == frame_reference.entity_id
                            for joint in articulation.joints
                            if joint.kind == 'floating' and joint.child_frame == frame_reference
                        )
                        if len(candidates) != 1:
                            raise ValueError('USD reset Frame must resolve to exactly one Scene floating Joint')
                        if reset_frame_name in self.position_joint_bindings:
                            raise ValueError('USD free-body reset Joint binding overlaps a scalar binding')
                        self.position_joint_bindings[reset_frame_name] = candidates[0]
                from ..artifacts import FrameReference
                self.position_frame_bindings = {
                    semantic: FrameReference(entity, frame)
                    for semantic, (entity, frame) in {
                        name: tuple(name.split('/', 1))
                        for name in (*self.value['source'].bodies, *self.value['source'].frames)
                    }.items()
                }
                if self.leaf_position_profile:
                    control_binding = ('panda-hand/hand-position'
                                       if self.fixed_attachment_leaf_position_profile
                                       else 'panda-main/gripper')
                    self.session = materialize_control(
                        self.artifact, self.execution, source=self.value['source'],
                        binding=ControlBinding(control_binding, .08),
                        leaf_plan=self.leaf_plan,
                    )
                else:
                    self.session = materialize_control(
                        self.artifact, self.execution, source=self.value['source'],
                        binding=ControlBinding('panda-main/gripper', .08),
                        controller_binding_plan=self.position_plan,
                        controller_profile=self.position_profiles,
                    )
            else:
                self.position_profile = False
                self.session = materialize_control(self.artifact, self.execution,
                    source=self.value['source'], binding=ControlBinding('panda-v1/gripper', .08),
                    diagnostic_profile=(self._diagnostic_profile
                                        if self.backend == 'cuda' else None))
            phase = 'runtime_reset'
            if self.position_profile:
                reset_plan = self.value.get('reset_plan')
                self.realized = self.session.reset_plan(reset_plan)
            else:
                self.realized = self.session.reset(self.sample)
            if self.binding.runtime_episode_identity:
                # Native task samples and the published Solution boundary
                # must share the RuntimeSession's actual episode identity.
                self._selected_episode_id = self.session.episode_id
            phase = 'snapshot_readback'
            self.state = self.session.snapshot()
            if self.position_profile:
                self.typed_state = self.session.snapshot_v1(
                    scene=self.position_scene,
                    joint_bindings=self.position_joint_bindings,
                    frame_bindings=self.position_frame_bindings,
                    requirements=self._position_requirements(),
                )
                if self.leaf_position_profile:
                    self.leaf_materialization = self.session.leaf_materialization_receipt
                else:
                    for profile in self.position_profiles:
                        profile.reset(self.typed_state, self.position_plan)
                self.feedback = None
            else:
                phase = 'controller_feedback'
                self.feedback = self.session.control_feedback(self.state)
                self.controller.reset(self.state, self.feedback)
            phase = 'reset_observation'
            self.obs, self.info, self.evaluation = self.observation(self.state)
            self.info['provider'] = self.provider
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
            if all(callable(getattr(self.controller, name, None))
                   for name in ('begin', 'target', 'applied')):
                # The Controller itself owns acknowledged arm hold/ramp memory.
                self.arm_schedule = self.controller
            else:
                self.arm_schedule = (self.binding.schedule_factory(self)
                                     if self.binding.schedule_factory is not None else None)
            self._active_native_interval_receipt = None
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
            try:
                self._close_camera_consumer()
            except BaseException as cleanup_error:
                add_note = getattr(error, 'add_note', None)
                if callable(add_note):
                    add_note(f'selected reset camera cleanup also failed: {cleanup_error!r}')
            failed_session, self.session = self.session, None
            if failed_session is not None:
                try:
                    failed_session.close()
                except BaseException as cleanup_error:
                    add_note = getattr(error, 'add_note', None)
                    if callable(add_note):
                        add_note(f'selected reset cleanup also failed: {cleanup_error!r}')
            if previous_session is not None and not previous_session_close_attempted:
                previous_session_close_attempted = True
                try:
                    previous_session.close()
                except BaseException as cleanup_error:
                    add_note = getattr(error, 'add_note', None)
                    if callable(add_note):
                        add_note(f'selected prior-session reset cleanup also failed: {cleanup_error!r}')
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
            'provider_materialization_id': self.session.provider_materialization_id,
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
        tolerance = _boundary_interval_clock_tolerance(
            receipt['request_boundary']['simulation_time_s'],
            receipt['evaluation_boundary']['simulation_time_s'],
            expected_dt,
            self.artifact.timebase.physics_dt,
            self.artifact.timebase.control_substeps,
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
            if getattr(self, 'leaf_position_profile', False):
                evaluation = self.binding.evaluate(state, self.artifact.semantics)
                frame_values = {
                    (item.frame.entity_id, item.frame.frame_id): item
                    for item in self.typed_state.view.frames
                }
                ee_key = (('panda-arm', 'link7')
                          if self.fixed_attachment_leaf_position_profile
                          else ('panda-main', 'link7'))
                ee_value = frame_values[ee_key].pose_world
                ee = ee_value
            else:
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
            if getattr(self, 'leaf_position_profile', False):
                if self.fixed_attachment_leaf_position_profile:
                    arm_joints = {value.joint_id: value for value in view.joints
                                  if value.entity_id == 'panda-arm'}
                    hand_joints = {value.joint_id: value for value in view.joints
                                   if value.entity_id == 'panda-hand'}
                    arm_pose = frame_values[('panda-arm', 'link7')].pose_world
                    hand_pose = frame_values[('panda-hand', 'hand')].pose_world
                    entity_states['panda-arm'] = {
                        'joint_position': np.asarray([
                            arm_joints[name].position[0] for name in (
                                'joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6', 'joint7',
                            )
                        ], dtype=np.float32),
                        'hand_pose': np.asarray((*arm_pose.position, *arm_pose.quaternion_wxyz), dtype=np.float32),
                    }
                    entity_states['panda-hand'] = {
                        'joint_position': np.asarray([
                            hand_joints[name].position[0] for name in ('finger_joint1', 'finger_joint2')
                        ], dtype=np.float32),
                        'hand_pose': np.asarray((*hand_pose.position, *hand_pose.quaternion_wxyz), dtype=np.float32),
                    }
                else:
                    entity_id = 'panda-main'
                    joints = {value.joint_id: value for value in view.joints if value.entity_id == entity_id}
                    hand = frame_values[(entity_id, 'hand')]
                    entity_states[entity_id] = {
                        'joint_position': np.asarray([
                            *(joints[name].position[0] for name in (
                                'joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6', 'joint7',
                            )),
                            joints['finger_joint1'].position[0], joints['finger_joint2'].position[0],
                        ], dtype=np.float32),
                        'hand_pose': np.asarray(
                            (*hand.pose_world.position, *hand.pose_world.quaternion_wxyz), dtype=np.float32,
                        ),
                    }
            else:
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
            primary_entity = (
                'panda-arm' if self.fixed_attachment_leaf_position_profile else 'panda-main'
            ) if self.leaf_position_profile else self.position_profiles[0].entity_id
            identity_hex = boundary.boundary_id.removeprefix('state-boundary-')
            if self.fixed_attachment_leaf_position_profile:
                state_obs['joint_position'] = np.concatenate((
                    entity_states['panda-arm']['joint_position'],
                    entity_states['panda-hand']['joint_position'],
                )).astype(np.float32, copy=False)
                state_obs['hand_pose'] = entity_states['panda-hand']['hand_pose']
                state_obs['entities'] = entity_states
            else:
                state_obs.update({
                    'joint_position': entity_states[primary_entity]['joint_position'],
                    'hand_pose': entity_states[primary_entity]['hand_pose'],
                })
            state_obs['boundary_identity_sha256'] = np.frombuffer(
                bytes.fromhex(identity_hex), dtype=np.uint8,
            ).copy()
            if self.dual_entity_position and not self.fixed_attachment_leaf_position_profile:
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
            if (self.value.get('f04_position_input') is not None
                    or self.value.get('f05_position_input') is not None):
                # Versioned USD state-only routes expose the Core-owned typed
                # publication used by observations and Position control.
                info['canonical_state_view_v1'] = self.typed_state.view.to_mapping()
            if self.camera_observation_config is not None:
                from ..observations.capture import DynamicCameraObservationConsumerV1

                if self._camera_consumer is None:
                    self._camera_consumer = DynamicCameraObservationConsumerV1(
                        config=self.camera_observation_config,
                        task_artifact_hash=self.artifact.identity_hash,
                        runtime_source=self.value['source'],
                        horizon=self.horizon,
                        session_factory=self._camera_session_factory,
                    )
                leaves, capture_boundary = self._camera_consumer.capture(self.typed_state.view)
                obs.update(leaves)
                info['camera_observation_v1'] = capture_boundary.to_mapping()
                self.camera_observation_schema.validate(obs)
        return obs, info, evaluation

    def _close_camera_consumer(self):
        consumer, self._camera_consumer = self._camera_consumer, None
        if consumer is not None:
            consumer.close()

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
            if getattr(self, 'leaf_position_profile', False):
                if self.fixed_attachment_leaf_position_profile:
                    from .position_candidate.attached_leaf_candidate import AttachedLeafActionSetV1
                    action_set_type = AttachedLeafActionSetV1
                else:
                    from .position_candidate.leaf_candidate import LeafPositionActionSetV1
                    action_set_type = LeafPositionActionSetV1
                if type(action) is not action_set_type:
                    raise TypeError('leaf Position route requires its typed Arm and Hand action-set')
                action.structured_request(self.position_scene, self.leaf_plan)
                return self._step_leaf_position(action)
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

    def _step_leaf_position(self, action):
        """Dispatch one real R02b two-leaf interval through the selected lifecycle."""
        if not getattr(self, 'leaf_position_profile', False) or self.session is None:
            raise RuntimeError('R02c leaf plan and RuntimeSession are required')
        if self._closed or self._stopped or self.state.control_step >= self.horizon:
            raise RuntimeError('reset required or R02c leaf episode is stopped')
        from ..runtime.sessions.leaf_control import (
            LeafActionRequestV1, LeafControlIntervalRequestV1,
            dispatch_leaf_control_interval,
        )
        if getattr(self, 'fixed_attachment_leaf_position_profile', False):
            from .position_candidate.attached_leaf_candidate import ARM_WRITER_ID, HAND_WRITER_ID
        else:
            from .position_candidate.leaf_candidate import ARM_WRITER_ID, HAND_WRITER_ID

        request = action.structured_request(self.position_scene, self.leaf_plan)
        leaf_request = LeafControlIntervalRequestV1(
            'leaf-control-interval-request-v1', self.leaf_plan.identity_sha256,
            self.session.leaf_materialization_receipt, self.typed_state,
            self.session.leaf_configuration_revision,
            (
                LeafActionRequestV1('leaf-action-request-v1', ARM_WRITER_ID, action.arm),
                LeafActionRequestV1('leaf-action-request-v1', HAND_WRITER_ID, action.hand),
            ),
        )
        before_state = self.state
        transition_counts_before = self._recording_counts(self.recorder)
        append_attempted = False
        phase = 'leaf_control_preflight'
        completed = False
        try:
            result = dispatch_leaf_control_interval(
                self.leaf_plan, leaf_request, scene=self.position_scene, runtime=self.session,
            )
            self.state = self.session.snapshot()
            self.typed_state = result.next_publication
            completed = True
            self.feedback = None
            self.last_leaf_transition = (action, result)
            phase = 'leaf_observation'
            self.obs, self.info, self.evaluation = self.observation(self.state)
            self.info.update({
                'provider': self.provider,
                'leaf_effective_plan_identity_sha256': self.leaf_plan.identity_sha256,
                'leaf_materialization_identity_sha256': self.session.leaf_materialization_receipt.identity_sha256,
            })
            terminated = bool(self.evaluation.failure)
            truncated = self.state.control_step >= self.horizon
            self._stopped = bool(terminated or truncated)
            self._episode_mode = 'external'
            self._last_position_terminated = terminated
            self._last_position_truncated = truncated
            self._last_position_request = request
            if self.recorder is not None:
                phase = 'record_leaf_transition'
                append_attempted = True
                self._record_leaf_position_transition(action, request, result,
                                                      terminated=terminated, truncated=truncated)
            self._published_position_state = self.state
            self._published_position_typed_state = self.typed_state
            self._published_position_obs = self.obs
            self._published_position_info = dict(self.info)
            self._published_position_evaluation = self.evaluation
            if terminated or truncated:
                self._position_episode_end = self._make_position_episode_end(
                    'task_terminal' if terminated else 'horizon_reached',
                    terminated=terminated, truncated=not terminated,
                    bootstrap_allowed=not terminated,
                )
                self.info['episode_end_v1'] = self._position_episode_end.to_mapping()
            return self.obs, float(self.evaluation.reward), terminated, truncated, self.info
        except BaseException as error:
            after_state = None
            readback_error = None
            try:
                after_state = self.session.snapshot()
                self.state = after_state
            except BaseException as snapshot_error:
                readback_error = f'{type(snapshot_error).__name__}: {snapshot_error}'
            completed = completed or (
                after_state is not None and after_state.control_step == before_state.control_step + 1
            )
            self._latch_fault(
                phase, error, before_state=before_state, after_state=after_state,
                interval_attempted=True, interval_completed=completed,
                native_substeps_expected=self.artifact.timebase.control_substeps,
                transition_status=self._fault_transition_status(
                    self.recorder, transition_counts_before, append_attempted=append_attempted,
                ), readback_error=readback_error,
            )
            self._stopped = True
            raise

    def _record_leaf_position_transition(self, action, request, result, *, terminated, truncated):
        from dataclasses import asdict
        from ..trajectory.canonical.episode import StructuredControlTransitionV1
        if getattr(self, 'fixed_attachment_leaf_position_profile', False):
            from .position_candidate.attached_leaf_candidate import ARM_WRITER_ID, HAND_WRITER_ID
        else:
            from .position_candidate.leaf_candidate import ARM_WRITER_ID, HAND_WRITER_ID

        groups = {(item.entity_id, item.group_id): item for item in request.groups}
        commands = {item.writer_id: item for item in result.prepared_commands}
        applied = {item.writer_id: item for item in result.apply_results}
        entries = {entry.binding.writer_id: entry for entry in self.leaf_plan.leaves}
        writer_controls = []
        request_groups = {(item.entity_id, item.group_id): item for item in request.groups}
        for writer_id, typed_action in ((ARM_WRITER_ID, action.arm), (HAND_WRITER_ID, action.hand)):
            entry = entries[writer_id]
            entity_id, group_id = entry.binding.entity_id, entry.binding.control_group_id
            if (entity_id, group_id) not in request_groups:
                raise ValueError('typed leaf request omits its exact Entity/ControlGroup')
            command = commands[writer_id]
            applied_result = applied[writer_id]
            is_arm = entry.binding.profile_kind == 'arm_position'
            components = (tuple(item.joint_id for item in entry.binding.joint_order)
                          if is_arm else ('opening_m',))
            values = tuple(typed_action.position_rad) if is_arm else (float(typed_action.opening_m),)
            requested_group = request_groups[(entity_id, group_id)]
            if (requested_group.action_schema_id != entry.binding.action_schema_id
                    or tuple(requested_group.values) != values):
                raise ValueError('typed leaf request Group schema/values differ from its writer Action')
            ack = applied_result.ack
            target = command.target
            writer_controls.append({
                'writer_id': writer_id,
                'action_schema_id': entry.binding.action_schema_id,
                'components': components,
                'groups': ({
                    'entity_id': entry.binding.entity_id,
                    'group_id': group_id,
                    'action_components': components,
                },),
                'requested_action': {
                    'schema_version': typed_action.schema_version,
                    'values': values,
                    'payload': typed_action.to_mapping(),
                    'unit': 'radian' if is_arm else 'meter_total_opening',
                },
                'canonical_action': {
                    'schema_version': 'leaf-canonical-action-v1',
                    'interpreted_values': values,
                    'target_identity_sha256': target.identity_hash,
                    'command_identity_sha256': command.command_identity_sha256,
                    'prepared_command': asdict(command),
                    'application_ack': ack.to_mapping(),
                    'source_boundary': target.source_boundary.to_mapping(),
                    'application_boundary': ack.application_boundary.to_mapping(),
                    'next_boundary': result.next_publication.view.boundary.to_mapping(),
                    'source_closure_sha256': self.value['source'].source_closure_digest,
                    'configuration_identity_sha256': entry.effective_configuration_identity_sha256,
                    'effective_plan_identity_sha256': self.leaf_plan.identity_sha256,
                    'materialization_identity_sha256': self.session.leaf_materialization_receipt.identity_sha256,
                },
                'controller_target': {
                    'schema_version': target.schema_version,
                    'payload': target.to_mapping(),
                    'identity_hash': target.identity_hash,
                },
                'applied_control': {
                    'schema_version': applied_result.schema_version,
                    'payload': asdict(applied_result),
                    'target_hash': target.identity_hash,
                },
            })
        control = StructuredControlTransitionV1(
            'structured-control-transition-v1', request, tuple(writer_controls),
        )
        control.validate()
        action_values = np.asarray(tuple(
            value for key in sorted(groups) for value in groups[key].values
        ), dtype=np.float32)
        self.recorder.append_transition(
            action_values, action_values, self.obs, float(self.evaluation.reward),
            bool(self.evaluation.success), bool(terminated), bool(truncated), self.info,
            structured_control=control,
        )

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
            try:
                self._close_camera_consumer()
            except BaseException as cleanup_error:
                add_note = getattr(error, 'add_note', None)
                if callable(add_note):
                    add_note(f'camera consumer cleanup after Position fault also failed: {cleanup_error!r}')
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
            proposal = (self.solution.act(self.obs, self.info)
                        if self.binding.expert_uses_public_observation
                        else self.solution.act())
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
        if (requested_mode == 'external_solution' and proposal is not None
                and proposal.control_request is not None):
            control_request = proposal.control_request
            diagnostics['arm_execution_request_v1'] = {
                'schema_version': control_request.schema_version,
                'profile_id': control_request.profile_id,
                'mode': control_request.mode,
            }
        native_samples = []
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
            if (self.binding.native_sample_factory is not None
                    and not callable(getattr(self.session, 'native_control_feedback_sample', None))):
                raise RuntimeError('selected Provider RuntimeSession does not expose the required native feedback sample contract')
            if self.binding.control_request_required:
                phase = 'controller_control_request_validation'
                if proposal is None or proposal.control_request is None:
                    raise ValueError('selected NutAssembly control requires its versioned arm execution request')
                validate_request = getattr(self.controller, 'validate_arm_execution_request', None)
                if not callable(validate_request):
                    raise RuntimeError('selected Controller does not own the admitted arm execution request')
                validate_request(proposal.control_request)
            elif proposal is not None and getattr(proposal, 'control_request', None) is not None:
                validate_request = getattr(self.controller, 'validate_arm_execution_request', None)
                if not callable(validate_request):
                    raise ValueError('selected Controller does not admit this Solution control request')
                validate_request(proposal.control_request)
            if self.recorder is not None and self.binding.recorder_mode == 'execution':
                phase = 'recorder_interval_begin'
                self.recorder.begin(self.state.control_step, self.artifact.timebase.physics_dt,
                                    self.artifact.timebase.control_substeps)
            if proposal is not None and getattr(proposal, 'control_request', None) is not None:
                phase = 'controller_control_request'
                self.controller.request_arm_execution(proposal.control_request)
            phase = 'controller_compute'
            canonical, target = self.controller.compute(self.state, self.feedback, request)

            def observe(index, state, feedback, effective, applied, diag,
                        provider_feedback_sample=None):
                observed_diagnostics = dict(diag)
                if self.binding.native_sample_factory is not None:
                    if proposal is None or request_boundary is None:
                        raise RuntimeError('native sample publication requires a source-bound Solution action')
                    if provider_feedback_sample is None:
                        raise ValueError('selected native interval lacks Provider force-sample provenance')
                    native_sample = self.binding.native_sample_factory(
                        self, stage, index, state, feedback, effective, applied,
                        observed_diagnostics, provider_feedback_sample, request_boundary,
                    )
                    native_samples.append(native_sample)
                    observed_diagnostics['native_feedback_sample_v1'] = native_sample.to_mapping()
                substeps.append((index, effective, applied))
                if self.recorder is not None and self.binding.record_native_substeps:
                    self.recorder.applied_substep(index, state, feedback, effective, applied,
                                                   observed_diagnostics)
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
            self.info['provider'] = self.provider
            if not self.position_profile:
                self._publish_execution_info(self.info)
                if canonical is not None and target is not None and applied is not None:
                    self._publish_control_application(
                        self.info, request, canonical, target, applied, request_boundary,
                    )
            interval_receipt = None
            if self.binding.native_interval_receipt_factory is not None:
                phase = 'native_interval_receipt'
                evaluation_boundary = self._execution_boundary(self.expert_execution_info())
                interval_receipt = self.binding.native_interval_receipt_factory(
                    self, request_boundary, evaluation_boundary, tuple(native_samples), tuple(substeps),
                )
                interval_receipt.validate()
                self._active_native_interval_receipt = interval_receipt
                self.info['native_interval_receipt_v1'] = interval_receipt.to_mapping()
            terminated = bool(self.evaluation.failure)
            truncated = self.state.control_step >= self.horizon
            if proposal is not None:
                phase = 'solution_observation'
                extra = (self.binding.observe_expert_kwargs(self, native_samples, interval_receipt)
                         if interval_receipt is not None
                         else self.binding.observe_expert_kwargs(self, native_samples))
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
            first_error = None
            session, self.session = self.session, None
            if session is not None:
                try:
                    session.close()
                except BaseException as error:
                    first_error = error
                try:
                    close_owner = getattr(session, 'close_runtime_owner', None)
                    if callable(close_owner):
                        close_owner()
                except BaseException as error:
                    if first_error is None:
                        first_error = error
                    else:
                        add_note = getattr(first_error, 'add_note', None)
                        if callable(add_note):
                            add_note(
                                'Runtime owner close after session close also failed: '
                                f'{type(error).__name__}: {error}'
                            )
            self._closed, self._stopped = True, True
            if first_error is not None:
                raise first_error
            return
        first_error = None

        def retain_cleanup_error(primary, label, cleanup_error):
            if primary is None:
                return cleanup_error
            add_note = getattr(primary, 'add_note', None)
            if callable(add_note):
                add_note(f'{label} also failed: {type(cleanup_error).__name__}: {cleanup_error}')
            return primary

        if self._published_position_state is not None:
            try:
                if self._position_episode_end is None:
                    self.stop('environment_close')
                if self.recorder is not None and getattr(self.recorder, 'active', False):
                    self.finish_recording(self._position_episode_end.outcome.end_reason)
            except BaseException as error:
                first_error = error
        try:
            self._close_camera_consumer()
        except BaseException as error:
            first_error = retain_cleanup_error(
                first_error, 'camera consumer close after Position finalization', error,
            )
        try:
            session, self.session = self.session, None
            if session is not None:
                try:
                    session.close()
                except BaseException as error:
                    first_error = retain_cleanup_error(
                        first_error, 'RuntimeSession close after Position finalization', error,
                    )
                try:
                    close_owner = getattr(session, 'close_runtime_owner', None)
                    if callable(close_owner):
                        close_owner()
                except BaseException as error:
                    first_error = retain_cleanup_error(
                        first_error, 'Runtime owner close after Position finalization', error,
                    )
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
        }
        if getattr(self, 'leaf_position_profile', False):
            details.update({
                'effective_leaf_plan_identity_sha256': self.leaf_plan.identity_sha256,
                'leaf_materialization_identity_sha256': self.session.leaf_materialization_receipt.identity_sha256,
                'leaf_writers': tuple({
                    'writer_id': entry.binding.writer_id,
                    'binding_identity_sha256': entry.binding.identity_hash,
                    'configuration_identity_sha256': entry.effective_configuration_identity_sha256,
                } for entry in self.leaf_plan.leaves),
            })
        else:
            details.update({
                'controller_identity': self.controller.identity,
                'profile_id': self.controller.profile_id,
            })
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
                max_buffer_bytes=(
                    self.camera_observation_config.max_recording_buffer_bytes
                    if self.camera_observation_config is not None
                    else RecorderConfig().max_buffer_bytes
                ),
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
            from ..recorders import (
                load_leaf_control_records_h5, load_structured_control_records_h5,
            )
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
            loaded = (load_leaf_control_records_h5(output) if self.leaf_position_profile
                      else load_structured_control_records_h5(output))
            if (loaded['transition_count'] != trajectory.transition_count
                    or loaded['observation_count'] != len(trajectory.observations)
                    or loaded['outcome'] != outcome):
                raise ValueError('PositionServoV1 Generic H5 v3 readback mismatch')
            camera_result = None
            if self.camera_observation_config is not None:
                from ..recorders import load_camera_observations_h5

                camera_result = load_camera_observations_h5(output)
                if camera_result['observation_count'] != len(trajectory.observations):
                    raise ValueError('Position camera metadata reader T/T+1 count mismatch')
            return {
                'schema_id': 'task-env-h5', 'schema_version': 'v3',
                'transition_count': loaded['transition_count'],
                'observation_count': loaded['observation_count'],
                **({'camera_observation_schema': camera_result['schema_version']}
                   if camera_result is not None else {}),
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
        info = {
            'seed': int(plan.reset_sample.task_seed),
            'options': {},
            'reset_sample_id': plan.reset_sample.sample_id,
            'reset_plan_identity_hash': plan.identity_hash,
            'role_binding_identity_hash': plan.role_binding.identity_hash,
            'state_boundary_identity': boundary.to_mapping(),
            'state_boundary_id': boundary.boundary_id,
            'state_sample_clock': self.typed_state.view.sample_clock.to_mapping(),
            'source_closure_digest': self.value['source'].source_closure_digest,
            **({
                # Persist the public snapshot used to produce the reset
                # observation. Generic H5 v3 consumes this only for the
                # bounded F05 typed-state extension.
                'canonical_state_view_v1': self.info['canonical_state_view_v1'],
            } if self.value.get('f05_position_input') is not None else {}),
            **({
                'camera_observation_v1': self.info['camera_observation_v1'],
            } if self.camera_observation_config is not None else {}),
        }
        if getattr(self, 'leaf_position_profile', False):
            info.update({
                'effective_leaf_plan_identity_sha256': self.leaf_plan.identity_sha256,
                'leaf_materialization_identity_sha256': self.session.leaf_materialization_receipt.identity_sha256,
                'leaf_configuration_revision': self.session.leaf_configuration_revision,
            })
            if self.fixed_attachment_leaf_position_profile:
                info.update({
                    'fixed_attachment_plan_identity_sha256': self.value['fixed_attachment_plan'].identity_hash,
                    'fixed_attachment_receipt_identity_sha256': self.session.fixed_attachment_receipt[
                        'receipt_identity_sha256'
                    ],
                })
        return info

    def _attached_leaf_record_metadata(self, asdict):
        attachment = self.session.fixed_attachment_receipt
        leaf_receipt = self.session.leaf_materialization_receipt
        writers = tuple({
            'writer_id': entry.binding.writer_id,
            'profile_kind': entry.binding.profile_kind,
            'action_schema_id': entry.binding.action_schema_id,
            'binding_identity_sha256': entry.binding.identity_hash,
            'effective_configuration_identity_sha256': entry.effective_configuration_identity_sha256,
            'member_path': entry.binding.member_path,
            'entity_id': entry.binding.entity_id,
            'control_group_id': entry.binding.control_group_id,
            'joint_order': tuple((ref.entity_id, ref.joint_id) for ref in entry.binding.joint_order),
            'actuator_order': tuple((ref.entity_id, ref.actuator_id) for ref in entry.binding.actuator_order),
            'tcp_frame': (entry.binding.tcp_frame.entity_id, entry.binding.tcp_frame.frame_id),
        } for entry in self.leaf_plan.leaves)
        profile = {
            'schema_version': 'leaf-position-recording-profile-v1',
            'profile_id': 'r03c-attached-entity-position-leaves-v1',
            'task_artifact_identity_hash': self.artifact.identity_hash,
            'task_source_identity_sha256': self.artifact.task_source_identity_hash,
            'scene_identity_hash': self.position_scene.identity_hash,
            'source_id': self.value['source'].scene_source.source_id,
            'source_closure_digest': self.value['source'].source_closure_digest,
            'effective_leaf_plan_identity_sha256': self.leaf_plan.identity_sha256,
            'preset_identity_sha256': self.value['leaf_preset'].identity_sha256,
            'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
            'reset_sample_id': self.value['reset_plan'].reset_sample.sample_id,
            'provider': self.provider,
            'provider_version': self.leaf_plan.provider_version,
            'provider_build_sha256': self.leaf_plan.provider_build_sha256,
            'backend': self.backend,
            'physics_dt_s': self.leaf_plan.physics_dt_s,
            'control_substeps': self.leaf_plan.control_substeps,
            'control_dt_s': self.artifact.timebase.control_dt,
            'materialization_identity_sha256': leaf_receipt.identity_sha256,
            'configuration_revision': self.session.leaf_configuration_revision,
            'attachment_plan_identity_sha256': self.value['fixed_attachment_plan'].identity_hash,
            'assembly_identity_sha256': self.value['fixed_attachment_plan'].logical_content_sha256,
            'attachment_receipt': attachment,
            'attachment_receipt_identity_sha256': attachment['receipt_identity_sha256'],
            'leaf_materialization_receipt': asdict(leaf_receipt),
            'leaf_materialization_receipt_identity_sha256': leaf_receipt.identity_sha256,
            'provider_materialization_id': leaf_receipt.materialization_id,
            'episode_id': self.value['resolved_configuration'].get('episode_id'),
            'arm_active': self.value['resolved_configuration'].get('arm_active'),
            'hand_active': self.value['resolved_configuration'].get('hand_active'),
            'writers': writers,
        }
        env_metadata = {
            'env_name': 'SelectedReferenceEnv.R03cAttachedLeafPositionV1',
            'task_name': self.artifact.task_id,
            'task_version': self.artifact.artifact_version,
            'scene_uid': self.position_scene.scene_id,
            'agent_uids': ('panda-arm', 'panda-hand'),
            'physics_dt': self.artifact.timebase.physics_dt,
            'control_substeps': self.artifact.timebase.control_substeps,
            'control_frequency': 1.0 / self.artifact.timebase.control_dt,
            'action_schema': {
                'schema_id': 'r03c-attached-leaf-action-set-v1',
                'components': tuple(ref.joint_id for ref in next(
                    item for item in self.leaf_plan.leaves
                    if item.binding.profile_kind == 'arm_position'
                ).binding.joint_order) + ('opening_m',),
                'units': ('radian',) * 7 + ('meter_total_opening',),
            },
            'observation_schema': {'leaf_specs': (
                {'path': 'state.ee_pose', 'semantic': 'panda_arm_link7_pose_world'},
                {'path': 'state.entities.panda-arm.joint_position', 'semantic': 'panda_arm_joint_positions'},
                {'path': 'state.entities.panda-hand.joint_position', 'semantic': 'panda_hand_finger_positions'},
                {'path': 'state.entities.panda-hand.hand_pose', 'semantic': 'panda_hand_pose_world'},
                {'path': 'state.boundary_identity_sha256', 'semantic': 'state_boundary_identity_sha256'},
            )},
            'leaf_position_v1': profile,
            'reference_profile': profile,
        }
        return {
            'env_metadata': env_metadata,
            'universal_action_schema': {
                'version': 'r03c-attached-leaf-action-set-v1',
                'dimension': 8,
                'components': env_metadata['action_schema']['components'],
            },
            'resolved_config': {
                'provider': self.provider, 'backend': self.backend, 'horizon': self.horizon,
                'effective_leaf_plan': self.leaf_plan.identity_sha256,
                'preset_identity_sha256': self.value['leaf_preset'].identity_sha256,
                'override_paths': tuple(item.member_path for item in self.value['leaf_overrides']),
            },
            'candidate_identity': {
                'task_artifact_identity_hash': self.artifact.identity_hash,
                'scene_identity_hash': self.position_scene.identity_hash,
                'source_closure_digest': self.value['source'].source_closure_digest,
                'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
                'effective_leaf_plan_identity_sha256': self.leaf_plan.identity_sha256,
                'attachment_plan_identity_sha256': self.value['fixed_attachment_plan'].identity_hash,
                'attachment_receipt_identity_sha256': attachment['receipt_identity_sha256'],
            },
        }

    def _position_record_metadata(self):
        from dataclasses import asdict

        f03_input = self.value.get('f03_position_input')
        f04_input = self.value.get('f04_position_input')
        f05_input = self.value.get('f05_position_input')
        if f03_input is not None or f04_input is not None or f05_input is not None:
            f04_route = f04_input is not None
            f05_route = f05_input is not None
            versioned_input = f05_input if f05_route else f04_input if f04_route else f03_input
            source = self.value['source']
            source_scene = source.scene_source
            loaded = source_scene.loaded_delivery
            delivery = loaded.delivery
            representation = source_scene.representation
            drive_receipt = (getattr(self.session, '_drive_receipt', None)
                             if f04_route or f05_route else self.value['native_drive_receipt'])
            native_metadata = self.session._native_io_metadata
            reset_receipt = self.session._reset_write_receipt
            if reset_receipt is None:
                raise RuntimeError('versioned USD recording requires the successful Core reset write receipt')
            f04_native = bool(f04_route and drive_receipt is not None
                              and drive_receipt.provenance_kind == 'native_runtime')
            expected_provenance = 'native_runtime' if f04_native else 'synthetic_fixture'
            if (drive_receipt is None or drive_receipt.provenance_kind != expected_provenance):
                raise RuntimeError('versioned USD recording receipt provenance differs from its execution route')
            if f04_native:
                if not (source.scene_source.source_verified or source.scene_source.locally_validated):
                    raise RuntimeError('F04 recording requires a loader-verified upstream or fixed local production delivery')
                bootstrap = self.session._native_io.bootstrap_receipt()
            else:
                bootstrap = None
            action_schema = self.controller.controller_binding().action_schema
            profile = {
                'schema_version': (
                    'f04-isaac-core-position-recording-profile-v1' if f04_native else
                    'f04-core-position-synthetic-io-s1-profile-v1' if f04_route else
                    'f05-geophys-position-synthetic-io-s1-profile-v1' if f05_route else
                    'f03-core-call-chain-recording-profile-v1'
                ),
                'profile_id': (
                    'f04-isaac-panda-position-native-v1' if f04_native else
                    'f04-local-source-synthetic-io-s1-v1' if f04_route else
                    'f05-geophys-usd-position-synthetic-io-s1-v1' if f05_route else
                    'f03-versioned-usd-position-synthetic-s1-v1'
                ),
                'provenance_kind': 'native_runtime' if f04_native else 'synthetic_fixture',
                'runtime_admitted': bool(f04_native),
                'source_verified': bool(source_scene.source_verified),
                'source_validation_provenance_kind': delivery.provenance_kind,
                'task_source_identity_sha256': versioned_input.task_source.identity_hash,
                'task_artifact_identity_sha256': self.artifact.identity_hash,
                'scene_identity_sha256': self.position_scene.identity_hash,
                'source_id': source.source_id,
                'source_closure_sha256': source.source_closure_digest,
                'usd_delivery': {
                    'asset_identity_sha256': delivery.asset_identity_hash,
                    'delivery_sha256': loaded.delivery_sha256,
                    'closure_sha256': loaded.closure_sha256,
                    'provenance_kind': delivery.provenance_kind,
                    'source_revision': delivery.source_revision,
                    'entry_file': delivery.entry_file,
                    'entry_prim': delivery.entry_prim,
                    'variant_selections': dict(delivery.variant_selections),
                    'validation_report_path': delivery.validation_report_path,
                    'validation_report_sha256': delivery.validation_report_sha256,
                    'validation_report_payload_sha256': hashlib.sha256(loaded.report_bytes).hexdigest(),
                    'validation_report_id': loaded.report.report_id,
                    'validation_report_passed': loaded.report.passed,
                    'validation_report_provenance_kind': loaded.report.provenance_kind,
                    'locally_validated': bool(getattr(loaded, 'locally_validated', False)),
                    **({
                        'source_closure_sha256': delivery.source_closure_sha256,
                        'source_manifest_sha256': delivery.source_manifest_sha256,
                        'source_variant_selections': dict(delivery.source_variant_selections),
                        'source_variant_selection_sha256': delivery.source_variant_selection_sha256,
                        'recipe_sha256': delivery.recipe_sha256,
                        'checker_sha256': delivery.checker_sha256,
                    } if getattr(loaded, 'locally_validated', False) else {}),
                },
                'representation': {
                    'identity_sha256': representation.identity_hash,
                    'provider': representation.provider,
                    'provider_build_identity': representation.provider_build_identity,
                    'requested_target_build_identity': representation.provider_build_identity,
                    'decision': representation.decision,
                    'runtime_admitted': representation.runtime_admitted,
                    'source_verified': representation.source_verified,
                },
                'execution_spec_v1': self.execution.to_mapping(),
                'execution_identity_sha256': self.execution.identity_hash,
                'device': self.execution.physics_device,
                'backend': self.execution.physics_backend,
                'provider_build_identity': native_metadata.provider_build_identity,
                **({
                    'requested_target_build_identity': versioned_input.host_model_producer_identity.requested_target_build_identity,
                    'host_model_producer_identity_sha256': versioned_input.host_model_producer_identity.identity_sha256,
                    'host_model_producer_identity': versioned_input.host_model_producer_identity.to_mapping(),
                } if f05_route else {}),
                'timebase': {
                    'physics_dt_s': self.artifact.timebase.physics_dt,
                    'control_substeps': self.artifact.timebase.control_substeps,
                    'control_dt_s': self.artifact.timebase.control_dt,
                    'clock_domain': 'evaluation_boundary',
                },
                'reset_plan_identity_sha256': self.value['reset_plan'].identity_hash,
                'reset_sample_id': self.value['reset_plan'].reset_sample.sample_id,
                'reset_write_receipt': reset_receipt.to_mapping(),
                'controller_identity_sha256': self.controller.identity,
                'control_binding_plan_identity_sha256': self.position_plan.identity_hash,
                'native_position_drive_receipt_identity_sha256': drive_receipt.identity_sha256,
                'native_position_drive_receipt': asdict(drive_receipt),
                **({'public_model_identity_sha256': drive_receipt.public_model_identity_sha256} if f05_route else {}),
                'native_runtime_io_metadata': native_metadata.to_mapping(),
                **({'native_public_bootstrap_receipt': bootstrap} if f04_native else {}),
                'native_source_mappings': {
                    'joints': dict(source.joints), 'bodies': dict(source.bodies),
                    'frames': dict(source.frames), 'free_joints': dict(source.free_joints),
                    'joint_targets': dict(source.joint_targets),
                },
                ('source_calibrated_kinematics_source_sha256' if f04_route or f05_route
                 else 'static_kinematics_source_sha256'): versioned_input.kinematics_source_sha256,
                'reset_sample_clock': self.typed_state.view.sample_clock.to_mapping(),
                **({'typed_state_h5_witness_schema_version': 'f05-public-typed-state-witness-v1'}
                   if f05_route else {}),
                'recording_scope': (
                    'F04 exact Isaac 6.2.0.0 cuda:0 GPU PhysX Position execution'
                    if f04_native else
                    'F05 public GeoPhys host-model synthetic S1; no provider solver or physics admission'
                    if f05_route else 'Core synthetic S1 conformance; no provider physics or native admission'
                ),
            }
            action_components = tuple(action_schema.components)
            return {
                'env_metadata': {
                    'env_name': (
                        'SelectedReferenceEnv.F04IsaacPandaPosition' if f04_native else
                        'SelectedReferenceEnv.F04LocalSourceSyntheticIOS1' if f04_route else
                        'SelectedReferenceEnv.F05GeoPhysUsdSyntheticIOS1' if f05_route else
                        'SelectedReferenceEnv.F03VersionedPositionS1'
                    ),
                    'task_name': self.artifact.task_id,
                    'task_version': self.artifact.artifact_version,
                    'scene_uid': self.position_scene.scene_id,
                    'agent_uids': ('panda-main',),
                    'physics_dt': self.artifact.timebase.physics_dt,
                    'control_substeps': self.artifact.timebase.control_substeps,
                    'control_frequency': 1.0 / self.artifact.timebase.control_dt,
                    'action_schema': asdict(action_schema),
                    'observation_schema': {'leaf_specs': (
                        {'path': 'state.ee_pose', 'semantic': 'hand_origin_tcp_pose_world'},
                        {'path': 'state.joint_position', 'semantic': 'named_arm_then_finger_joint_positions'},
                        {'path': 'state.hand_pose', 'semantic': 'measured_hand_frame_pose_world'},
                        {'path': 'state.boundary_identity_sha256', 'semantic': 'state_boundary_identity_sha256'},
                        {'path': 'privileged_state.target_body_pose', 'semantic': 'floating_target_body_pose_world'},
                    )},
                    'reference_profile': profile,
                },
                'universal_action_schema': {
                    'version': ('f04-isaac-core-position-action-v1'
                                if f04_route else 'f03-core-call-chain-position-action-v1'),
                    'dimension': len(action_components), 'components': action_components,
                },
                'resolved_config': {
                    'provider': self.provider, 'backend': self.backend,
                    'device': self.execution.physics_device, 'horizon': self.horizon,
                    'controller_profile': self.controller.profile_id,
                    'execution_identity_sha256': self.execution.identity_hash,
                },
                'candidate_identity': {
                    'task_artifact_identity_hash': self.artifact.identity_hash,
                    'task_source_identity_sha256': versioned_input.task_source.identity_hash,
                    'scene_identity_hash': self.position_scene.identity_hash,
                    'source_id': source.source_id,
                    'source_closure_digest': source.source_closure_digest,
                    'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
                    'execution_identity_sha256': self.execution.identity_hash,
                    'controller_identity_sha256': self.controller.identity,
                    'native_position_drive_receipt_identity_sha256': drive_receipt.identity_sha256,
                    **({'host_model_producer_identity_sha256': versioned_input.host_model_producer_identity.identity_sha256}
                       if f05_route else {}),
                },
            }

        if getattr(self, 'leaf_position_profile', False):
            if self.fixed_attachment_leaf_position_profile:
                return self._attached_leaf_record_metadata(asdict)
            arm_entry = next(item for item in self.leaf_plan.leaves if item.binding.profile_kind == 'arm_position')
            hand_entry = next(item for item in self.leaf_plan.leaves if item.binding.profile_kind == 'hand_position')
            action_components = tuple(item.joint_id for item in arm_entry.binding.joint_order) + ('opening_m',)
            observation_leaf_specs = (
                {'path': 'state.ee_pose', 'semantic': 'panda_main_link7_pose_world'},
                {'path': 'state.joint_position', 'semantic': 'panda_main_arm_then_two_finger_positions'},
                {'path': 'state.hand_pose', 'semantic': 'panda_main_hand_pose_world'},
                {'path': 'state.boundary_identity_sha256', 'semantic': 'state_boundary_identity_sha256'},
            )
            env_metadata = {
                'env_name': 'SelectedReferenceEnv.R02cLeafPositionV1',
                'task_name': self.artifact.task_id,
                'task_version': self.artifact.artifact_version,
                'scene_uid': self.position_scene.scene_id,
                'agent_uids': ('panda-main',),
                'physics_dt': self.artifact.timebase.physics_dt,
                'control_substeps': self.artifact.timebase.control_substeps,
                'control_frequency': 1.0 / self.artifact.timebase.control_dt,
                'action_schema': {
                    'schema_id': 'leaf-position-action-set-v1',
                    'components': action_components,
                    'units': ('radian',) * 7 + ('meter_total_opening',),
                },
                'observation_schema': {'leaf_specs': observation_leaf_specs},
                'leaf_position_v1': {
                    'scene_identity_sha256': self.position_scene.identity_hash,
                    'task_artifact_identity_sha256': self.artifact.identity_hash,
                    'task_source_identity_sha256': self.artifact.task_source_identity_hash,
                    'source_id': self.value['source'].scene_source.source_id,
                    'source_xml_sha256': hashlib.sha256(self.value['source'].scene_source.xml.encode()).hexdigest(),
                    'source_closure_sha256': self.value['source'].source_closure_digest,
                    'effective_plan_identity_sha256': self.leaf_plan.identity_sha256,
                    'preset_identity_sha256': self.value['leaf_preset'].identity_sha256,
                    'provider': self.provider, 'provider_version': self.leaf_plan.provider_version,
                    'provider_build_sha256': self.leaf_plan.provider_build_sha256,
                    'backend': self.backend, 'physics_dt_s': self.leaf_plan.physics_dt_s,
                    'control_substeps': self.leaf_plan.control_substeps,
                    'materialization_identity_sha256': self.session.leaf_materialization_receipt.identity_sha256,
                    'configuration_revision': self.session.leaf_configuration_revision,
                    'writers': tuple({
                        'writer_id': entry.binding.writer_id,
                        'profile_kind': entry.binding.profile_kind,
                        'action_schema_id': entry.binding.action_schema_id,
                        'binding_identity_sha256': entry.binding.identity_hash,
                        'effective_configuration_identity_sha256': entry.effective_configuration_identity_sha256,
                        'member_path': entry.binding.member_path,
                        'entity_id': entry.binding.entity_id,
                        'control_group_id': entry.binding.control_group_id,
                        'joint_order': tuple(ref.joint_id for ref in entry.binding.joint_order),
                        'actuator_order': tuple(ref.actuator_id for ref in entry.binding.actuator_order),
                    } for entry in self.leaf_plan.leaves),
                },
                'reference_profile': {
                    'schema_version': 'leaf-position-recording-profile-v1',
                    'profile_id': 'r02c-independent-position-leaves-v1',
                    'task_artifact_identity_hash': self.artifact.identity_hash,
                    'task_source_identity_sha256': self.artifact.task_source_identity_hash,
                    'scene_identity_hash': self.position_scene.identity_hash,
                    'source_id': self.value['source'].scene_source.source_id,
                    'source_closure_digest': self.value['source'].source_closure_digest,
                    'effective_leaf_plan_identity_sha256': self.leaf_plan.identity_sha256,
                    'preset_identity_sha256': self.value['leaf_preset'].identity_sha256,
                    'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
                    'reset_sample_id': self.value['reset_plan'].reset_sample.sample_id,
                    'provider': self.provider,
                    'provider_version': self.leaf_plan.provider_version,
                    'provider_build_sha256': self.leaf_plan.provider_build_sha256,
                    'backend': self.backend,
                    'physics_dt_s': self.leaf_plan.physics_dt_s,
                    'control_substeps': self.leaf_plan.control_substeps,
                    'control_dt_s': self.artifact.timebase.control_dt,
                    'materialization_identity_sha256': self.session.leaf_materialization_receipt.identity_sha256,
                    'configuration_revision': self.session.leaf_configuration_revision,
                    'writers': tuple({
                        'writer_id': entry.binding.writer_id,
                        'profile_kind': entry.binding.profile_kind,
                        'action_schema_id': entry.binding.action_schema_id,
                        'binding_identity_sha256': entry.binding.identity_hash,
                        'effective_configuration_identity_sha256': entry.effective_configuration_identity_sha256,
                        'member_path': entry.binding.member_path,
                        'entity_id': entry.binding.entity_id,
                        'control_group_id': entry.binding.control_group_id,
                        'joint_order': tuple(ref.joint_id for ref in entry.binding.joint_order),
                        'actuator_order': tuple(ref.actuator_id for ref in entry.binding.actuator_order),
                    } for entry in self.leaf_plan.leaves),
                },
            }
            return {
                'env_metadata': env_metadata,
                'universal_action_schema': {
                    'version': 'r02c-leaf-position-action-set-v1',
                    'dimension': 8, 'components': action_components,
                },
                'resolved_config': {
                    'provider': self.provider, 'backend': self.backend,
                    'horizon': self.horizon, 'effective_leaf_plan': self.leaf_plan.identity_sha256,
                    'preset_identity_sha256': self.value['leaf_preset'].identity_sha256,
                    'override_paths': tuple(item.member_path for item in self.value['leaf_overrides']),
                },
                'candidate_identity': {
                    'task_artifact_identity_hash': self.artifact.identity_hash,
                    'scene_identity_hash': self.position_scene.identity_hash,
                    'source_closure_digest': self.value['source'].source_closure_digest,
                    'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
                    'effective_leaf_plan_identity_sha256': self.leaf_plan.identity_sha256,
                },
            }

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
        if self.camera_observation_config is not None:
            from ..observations.state import camera_observation_field_specs

            observation_leaf_specs.extend({
                'path': field.name,
                'shape': field.shape,
                'dtype': field.dtype,
                'semantic': field.semantic,
                'unit': field.unit,
                'frame': field.frame,
                'time_reference': field.time_reference,
            } for field in camera_observation_field_specs(self.camera_observation_config))
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
                **({'camera_observation': self.camera_observation_config.to_mapping()}
                   if self.camera_observation_config is not None else {}),
            },
            'candidate_identity': {
                'task_artifact_identity_hash': self.artifact.identity_hash,
                'source_closure_digest': self.value['source'].source_closure_digest,
                'reset_plan_identity_hash': self.value['reset_plan'].identity_hash,
            },
            **({
                'camera_observation_contract_v1': self.camera_observation_config.to_mapping(),
            } if self.camera_observation_config is not None else {}),
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
        f03_input = self.value.get('f03_position_input')
        f04_input = self.value.get('f04_position_input')
        f05_input = self.value.get('f05_position_input')
        if f03_input is not None or f04_input is not None or f05_input is not None:
            native_ack = getattr(self.session, '_last_native_position_ack', None)
            native_advances = getattr(self.session, '_last_interval_advances', ())
            advance_attempts = getattr(self.session, '_last_interval_advance_attempts', None)
            if native_ack is None or len(native_advances) != self.artifact.timebase.control_substeps:
                raise ValueError('versioned USD recording requires a complete native Position Ack and interval receipts')
            applied_payload['native_position_write_ack_v1'] = native_ack.to_mapping()
            applied_payload['native_interval_advance_receipts_v1'] = list(native_advances)
            applied_payload['native_interval_advance_attempts'] = advance_attempts
            if f04_input is not None or f05_input is not None:
                native_io = getattr(self.session, '_native_io', None)
                provenance = getattr(native_io, 'execution_provenance_kind', None)
                if provenance == 'native_runtime':
                    execution_class = 'native_runtime_accepted_physics'
                elif provenance == 'synthetic_fixture':
                    execution_class = 'synthetic_fixture_no_physics'
                else:
                    raise ValueError(
                        'F04 Position recording requires an explicit native-I/O execution provenance'
                    )
            else:
                execution_class = 'synthetic_fixture_no_physics'
            applied_payload['native_io_execution_class'] = execution_class
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
