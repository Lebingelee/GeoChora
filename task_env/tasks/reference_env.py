"""Explicit selected-reference adapter, delegating task semantics and policies.

This adapter owns one scalar CPU session. It defines no TaskArtifact or task
success predicate. Expert execution and external-action execution cannot be
mixed in one episode. Rendering and legacy TaskEnv configuration are rejected.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
from typing import Callable
import numpy as np
from gymnasium.spaces import Box, Dict

from ..artifacts import ExecutionSpec
from ..controllers.canonical.contracts import RequestedAction, digest
from ..environment.protocols import TaskEnvironmentComponent
from ..environment.types import ExecutionFaultV1, attach_execution_fault
from ..planners.completion import ExpertExecutionInfo
from ..runtime.sessions.api import PROFILE
from ..runtime.sessions.control import ControlBinding, materialize_control

METADATA = {'action_schema': {'schema_id': 'selected-reference-absolute-pose-v1',
    'schema_version': 1, 'controller_kind': 'absolute_pose', 'reference': 'world',
    'rotation_representation': 'quaternion_wxyz', 'dimension': 8}}


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

    def __post_init__(self):
        if self.interval_mode not in {"grouped", "native"}:
            raise ValueError("unknown selected control-interval requirement")
        if self.recorder_mode not in {"canonical", "execution"}:
            raise ValueError("unknown selected recording requirement")
        if not self.object_poses:
            raise ValueError("selected task binding requires an observation pose")


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

    def __init__(self, *, provider='geophys', backend='cpu', horizon=6000):
        if provider not in {'geophys', 'mujoco'} or backend != 'cpu':
            raise ValueError('selected reference currently admits GeoPhys/MuJoCo scalar CPU only')
        if type(horizon) is not int or not 1 <= horizon <= 6000:
            raise ValueError('selected reference horizon must be an integer in [1, 6000]')
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
        self.controller = self.value['controller']
        self.metadata = {**METADATA, 'action_schema': dict(METADATA['action_schema']), 'env_id': self.uid,
            'task_artifact_hash': self.artifact.identity_hash,
            'construction_id': self.value['construction_id'],
            'control_dt': self.artifact.timebase.control_dt}
        self.action_space = Box(-np.inf, np.inf, (8,), dtype=np.float64)
        keys = [key for _, key in self.binding.object_poses]
        self.observation_space = Dict({'state': Dict({'ee_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32)}),
            'privileged_state': Dict({k + '_body_pose': Box(-np.inf, np.inf, (1, 7), dtype=np.float32) for k in keys})})
        self.session = None
        self._closed = False
        self._episode_mode = None
        self._stopped = True
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

    def reset(self, *, seed=19, options=None):
        if self._closed:
            raise RuntimeError('environment is closed')
        if options:
            raise ValueError('selected reference reset options are not supported')
        if self.recorder is not None and not getattr(self.recorder, 'frozen', getattr(self.recorder, '_frozen', False)):
            raise RuntimeError('finalize current recording before reset')
        self._stopped = True
        previous_session, self.session = self.session, None
        phase = 'reset_close'
        try:
            if previous_session is not None:
                previous_session.close()
            phase = 'selected_reconstruction'
            # A new construction resets all controller/arm-hold/servo owner memory.
            self.value = self.binding.build(self.provider)
            if self.value['artifact'] != self.artifact:
                raise ValueError('selected Artifact changed between construction and reset')
            phase = 'reset_seed'
            seed = self.binding.reset_seed(seed)
            self.solution, self.controller = self.value['solution'], self.value['controller']
            phase = 'reset_sample'
            self.sample = self.binding.reset_sample(self.artifact, seed)
            self.execution = ExecutionSpec(self.provider, PROFILE, 'none', 'cpu', 0, 'strict')
            phase = 'session_materialization'
            self.session = materialize_control(self.artifact, self.execution,
                source=self.value['source'], binding=ControlBinding('panda-v1/gripper', .08))
            phase = 'runtime_reset'
            self.realized = self.session.reset(self.sample)
            phase = 'snapshot_readback'
            self.state = self.session.snapshot()
            phase = 'controller_feedback'
            self.feedback = self.session.control_feedback(self.state)
            self.controller.reset(self.state, self.feedback)
            phase = 'reset_observation'
            self.obs, self.info, self.evaluation = self.observation(self.state)
            if self.state.control_step != 0 or self.state.simulation_time != 0:
                raise ValueError('reference reset must not advance physics')
            phase = 'solution_reset'
            self.solution.reset(self.obs, self.info, self.metadata,
                                **self.binding.reset_expert_kwargs(self))
            phase = 'arm_schedule_reset'
            self.arm_schedule = (self.binding.schedule_factory(self)
                                 if self.binding.schedule_factory is not None else None)
            self._stopped, self._episode_mode = False, None
            self.recorder = None
            self._execution_fault = None
            return self.obs, self.info
        except BaseException as error:
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

    def _execution_info(self):
        return ExpertExecutionInfo('expert-execution-info-v1', self.state.control_step,
            self.state.simulation_time, self.controller.readiness(self.state, self.feedback))

    def observation(self, state):
        evaluation = self.binding.evaluate(state, self.artifact.semantics)
        ee = state.pose_world['panda-v1/ee']
        obs = {'state': {'ee_pose': np.array((*ee.position, *ee.quaternion_wxyz), dtype=np.float32)},
               'privileged_state': {}}
        for semantic, key in self.binding.object_poses:
            pose = state.pose_world[semantic]
            obs['privileged_state'][key + '_body_pose'] = np.array(
                [(*pose.position, *pose.quaternion_wxyz)], dtype=np.float32)
        info = {'is_success': bool(evaluation.success), 'task_failure': bool(evaluation.failure),
            'task_metrics': dict(evaluation.metrics), 'control_step': int(state.control_step),
            'simulation_time_s': float(state.simulation_time)}
        return obs, info, evaluation

    def step(self, action):
        if self._execution_fault is not None:
            fault = self._execution_fault
            raise RuntimeError(
                'selected execution is faulted; reset() is required '
                f"(phase={fault.phase}, physical_progress={fault.physical_progress})"
            )
        if not self.binding.external_actions:
            raise RuntimeError(self.binding.external_action_error)
        if self._episode_mode == 'expert':
            raise RuntimeError('cannot mix external actions with selected expert execution')
        self._episode_mode = 'external'
        return self._step(action)

    def step_expert(self):
        if self._execution_fault is not None:
            fault = self._execution_fault
            raise RuntimeError(
                'selected execution is faulted; reset() is required '
                f"(phase={fault.phase}, physical_progress={fault.physical_progress})"
            )
        if self._stopped or self._episode_mode == 'external':
            raise RuntimeError('reset required; external and expert execution cannot be mixed')
        self._episode_mode = 'expert'
        if self.solution.done or self.solution.failed:
            raise RuntimeError('expert already stopped')
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
        return self._step(proposal.action, proposal=proposal)

    def _step(self, action, *, proposal=None):
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
        requested_mode = 'expert' if proposal is not None else 'external'
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
                    guard_samples.append(self.solution.make_native_guard_sample(state, info, diag))
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
            terminated = bool(self.evaluation.failure)
            truncated = self.state.control_step >= self.horizon
            if proposal is not None:
                phase = 'solution_observation'
                extra = self.binding.observe_expert_kwargs(self, guard_samples)
                self.solution.observe(self.obs, self.evaluation.reward, terminated, truncated, self.info, **extra)
                if hasattr(self.solution, 'outcome_report'):
                    self.info.update(self.solution.outcome_report())
                self.info.update(selected_policy_execution_complete=bool(self.solution.done),
                                 selected_policy_execution_failed=bool(self.solution.failed),
                                 expert_failure_reason=self.solution.failure_reason)
                self._stopped = self.solution.done or self.solution.failed
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
            if self.binding.abort_solution_on_runtime_error:
                try:
                    self.solution.abort('runtime_error')
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
        if self.session is not None:
            self.session.close()
            self.session = None
        self._closed, self._stopped = True, True

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
            'solution_identity': self.solution.identity, 'provider': self.provider,
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
        if self.session is None or self.state.control_step != 0 or self.recorder is not None:
            raise RuntimeError('recording starts exactly once at reset boundary')
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
            source_provenance.update({
                'geochora_revision': str(self.value['source_revision']),
                'artifact_identity': self.artifact.identity_hash,
                'controller_identity': self.controller.identity,
                'solution_identity': self.solution.identity,
            })
            source_provenance.update({f"source_sha256:{name}": value
                for name, value in self.value.get('source_sha256', {}).items()})
        metadata = EpisodeMetadata('canonical-trajectory-metadata-v0', self.artifact.identity_hash,
            self.sample, self.realized, self.execution,
            {'build': str(provider_build_identity(self.provider))},
            source_provenance,
            self.artifact.timebase, self.controller.identity, self.solution.identity,
            digest({'readiness': self.solution.identity}), digest(METADATA), self.sample.task_seed, 'regression')
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
        from ..trajectory.canonical.streaming import save_streaming, verify_roundtrip
        if self.recorder is None or getattr(self.recorder, 'frozen', getattr(self.recorder, '_frozen', False)):
            raise RuntimeError('no active recording')
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
