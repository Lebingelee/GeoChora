"""Explicit selected-reference adapter, delegating task semantics and policies.

This adapter owns one scalar CPU session. It defines no TaskArtifact or task
success predicate. Expert execution and external-action execution cannot be
mixed in one episode. Rendering and legacy TaskEnv configuration are rejected.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from gymnasium.spaces import Box, Dict

from ..artifacts import ExecutionSpec
from ..controllers.canonical.contracts import RequestedAction, digest
from ..environment.protocols import TaskEnvironmentComponent
from ..planners.completion import ExpertExecutionInfo
from ..runtime.sessions.api import PROFILE
from ..runtime.sessions.control import ControlBinding, materialize_control

METADATA = {'action_schema': {'schema_id': 'selected-reference-absolute-pose-v1',
    'schema_version': 1, 'controller_kind': 'absolute_pose', 'reference': 'world',
    'rotation_representation': 'quaternion_wxyz', 'dimension': 8}}


class SelectedReferenceEnv(TaskEnvironmentComponent):
    """Advanced reference API. No legacy Gym configuration compatibility claim."""
    task_kind = None

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
        self.provider, self.horizon = provider, horizon
        self.value = self.build(provider)
        self.artifact = self.value['artifact']
        self.solution = self.value['solution']
        self.controller = self.value['controller']
        self.metadata = {**METADATA, 'action_schema': dict(METADATA['action_schema']), 'env_id': self.uid,
            'task_artifact_hash': self.artifact.identity_hash,
            'construction_id': self.value['construction_id'],
            'control_dt': self.artifact.timebase.control_dt}
        self.action_space = Box(-np.inf, np.inf, (8,), dtype=np.float64)
        keys = (['cube_v1'] if self.task_kind == 'pick_cube' else ['square_nut_v1', 'square_peg_v1'])
        self.observation_space = Dict({'state': Dict({'ee_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32)}),
            'privileged_state': Dict({k + '_body_pose': Box(-np.inf, np.inf, (1, 7), dtype=np.float32) for k in keys})})
        self.session = None
        self._closed = False
        self._episode_mode = None
        self._stopped = True
        self.recorder = None
        self.recording_path = None

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
        if self.session is not None:
            self.session.close()
        self.session = None
        self._stopped = True
        # A new construction resets all controller/arm-hold/servo owner memory.
        self.value = self.build(self.provider)
        if self.value['artifact'] != self.artifact:
            raise ValueError('selected Artifact changed between construction and reset')
        if self.task_kind == 'nut_assembly' and seed not in (19, None):
            raise ValueError('selected NutAssembly NA-S0 has fixed provenance seed19')
        seed = 19 if seed is None else seed
        self.solution, self.controller = self.value['solution'], self.value['controller']
        self.sample = self.reset_sample(self.artifact, seed)
        self.execution = ExecutionSpec(self.provider, PROFILE, 'none', 'cpu', 0, 'strict')
        self.session = materialize_control(self.artifact, self.execution,
            source=self.value['source'], binding=ControlBinding('panda-v1/gripper', .08))
        try:
            self.realized = self.session.reset(self.sample)
            self.state = self.session.snapshot()
            self.feedback = self.session.control_feedback(self.state)
            self.controller.reset(self.state, self.feedback)
            self.obs, self.info, self.evaluation = self.observation(self.state)
            if self.state.control_step != 0 or self.state.simulation_time != 0:
                raise ValueError('reference reset must not advance physics')
            extra = ({'execution_info': self._execution_info()} if self.task_kind == 'pick_cube' else {})
            self.solution.reset(self.obs, self.info, self.metadata, **extra)
            self.arm_schedule = None
            if self.task_kind == 'nut_assembly':
                from .nut_assembly.reference_execution import ReferenceArmSchedule
                self.arm_schedule = ReferenceArmSchedule(self.solution, self.value['_arm_schedule_memory'])
            self._stopped, self._episode_mode = False, None
            self.recorder = None
            return self.obs, self.info
        except BaseException:
            self.session.close()
            self.session = None
            raise

    def _execution_info(self):
        return ExpertExecutionInfo('expert-execution-info-v1', self.state.control_step,
            self.state.simulation_time, self.controller.readiness(self.state, self.feedback))

    def observation(self, state):
        if self.task_kind == 'pick_cube':
            from .pick_cube.canonical_semantics import evaluate
            poses = [('cube-v1', 'cube_v1')]
        else:
            from .nut_assembly.canonical_semantics import evaluate
            poses = [('square-nut-v1', 'square_nut_v1'), ('square-peg-v1', 'square_peg_v1')]
        evaluation = evaluate(state, self.artifact.semantics)
        ee = state.pose_world['panda-v1/ee']
        obs = {'state': {'ee_pose': np.array((*ee.position, *ee.quaternion_wxyz), dtype=np.float32)},
               'privileged_state': {}}
        for semantic, key in poses:
            pose = state.pose_world[semantic]
            obs['privileged_state'][key + '_body_pose'] = np.array(
                [(*pose.position, *pose.quaternion_wxyz)], dtype=np.float32)
        info = {'is_success': bool(evaluation.success), 'task_failure': bool(evaluation.failure),
            'task_metrics': dict(evaluation.metrics), 'control_step': int(state.control_step),
            'simulation_time_s': float(state.simulation_time)}
        return obs, info, evaluation

    def step(self, action):
        if self.task_kind == 'nut_assembly':
            raise RuntimeError('selected NutAssembly requires step_expert; unguarded external actions are not admitted')
        if self._episode_mode == 'expert':
            raise RuntimeError('cannot mix external actions with selected expert execution')
        self._episode_mode = 'external'
        return self._step(action)

    def step_expert(self):
        if self._stopped or self._episode_mode == 'external':
            raise RuntimeError('reset required; external and expert execution cannot be mixed')
        self._episode_mode = 'expert'
        if self.solution.done or self.solution.failed:
            raise RuntimeError('expert already stopped')
        proposal = self.solution.act()
        return self._step(proposal.action, proposal=proposal)

    def _step(self, action, *, proposal=None):
        if self._stopped or self.session is None:
            raise RuntimeError('reset required or episode already stopped')
        vector = np.asarray(action, dtype=float)
        if vector.shape != (8,) or not np.isfinite(vector).all():
            raise ValueError('finite eight-dimensional absolute pose action required')
        request = RequestedAction('absolute_pose', 'world', 'quaternion_wxyz', tuple(map(float, vector)))
        stage = proposal.stage if proposal is not None else 'external'
        diagnostics = dict(proposal.diagnostics) if proposal is not None else {}
        guard_samples = []
        substeps = []
        if self.recorder is not None and self.task_kind == 'nut_assembly':
            self.recorder.begin(self.state.control_step, self.artifact.timebase.physics_dt,
                                self.artifact.timebase.control_substeps)
        try:
            canonical, target = self.controller.compute(self.state, self.feedback, request)
            def observe(index, state, feedback, effective, applied, diag):
                substeps.append((index, effective, applied))
                if self.recorder is not None:
                    self.recorder.applied_substep(index, state, feedback, effective, applied, diag)
                if proposal is not None and stage == 'close_gripper' and self.task_kind == 'nut_assembly':
                    _, info, _ = self.observation(state)
                    guard_samples.append(self.solution.make_native_guard_sample(state, info, diag))
            if self.task_kind == 'nut_assembly':
                self.state, target, applied, _ = self.session.step_control_interval(
                    target, self.controller, interval_observer=observe, arm_schedule=self.arm_schedule)
            else:
                # Preserve historical P1.6 grouped control-interval stepping,
                # including the provider's boundary clock accumulation.
                applied = self.session.apply_control(target)
                self.state = self.session.step()
            self.feedback = self.session.control_feedback(self.state)
            self.obs, self.info, self.evaluation = self.observation(self.state)
            terminated = bool(self.evaluation.failure)
            truncated = self.state.control_step >= self.horizon
            if proposal is not None:
                extra = ({'execution_info': self._execution_info()} if self.task_kind == 'pick_cube'
                         else {'readiness': self.controller.readiness(self.state, self.feedback),
                               'transition_samples': guard_samples})
                self.solution.observe(self.obs, self.evaluation.reward, terminated, truncated, self.info, **extra)
                if self.task_kind == 'nut_assembly':
                    self.info.update(self.solution.outcome_report())
                self.info.update(selected_policy_execution_complete=bool(self.solution.done),
                                 selected_policy_execution_failed=bool(self.solution.failed),
                                 expert_failure_reason=self.solution.failure_reason)
                self._stopped = self.solution.done or self.solution.failed
            self._stopped = bool(self._stopped or terminated or truncated)
            if self.recorder is not None:
                self._record_interval(request, canonical, target, applied, stage, diagnostics,
                                      terminated, truncated, substeps)
            return self.obs, float(self.evaluation.reward), terminated, truncated, self.info
        except BaseException:
            self._stopped = True
            if self.task_kind == 'nut_assembly':
                self.solution.abort('runtime_error')
            # An incomplete interval cannot be finalized as a valid trajectory.
            raise

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
        metadata = EpisodeMetadata('canonical-trajectory-metadata-v0', self.artifact.identity_hash,
            self.sample, self.realized, self.execution,
            {'build': str(provider_build_identity(self.provider))},
            {'construction': digest(config), 'adapter': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'interval_source': hashlib.sha256(Path(session_common.__file__).read_bytes()).hexdigest(),
             'resolved_configuration_json': json.dumps(config, sort_keys=True),
             'execution_configuration_json': json.dumps({'env_id': self.uid, 'provider': self.provider,
                 'backend': 'cpu', 'horizon': self.horizon}, sort_keys=True)},
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
        if self.task_kind == 'pick_cube':
            from ..trajectory.canonical.contracts import CanonicalRecorder
            self.recorder = CanonicalRecorder(metadata, self._boundary())
            return
        self.recorder = ExecutionRecorder(metadata, recipe, content_fields=('task_outcome',))
        self.recorder.boundary(self._boundary(), owners, 'reference', self.info['task_metrics'])

    def _record_interval(self, request, canonical, target, applied, stage, diagnostics,
                         terminated, truncated, substeps):
        from ..trajectory.canonical.contracts import TransitionRecord
        count = self.artifact.timebase.control_substeps
        if self.task_kind == 'nut_assembly' and (len(substeps) != count or [x[0] for x in substeps] != list(range(count))):
            raise ValueError('missing native application receipts')
        wait = bool(diagnostics.get('readiness_hold', False))
        transition = TransitionRecord(request, canonical, target, applied, float(self.evaluation.reward),
            terminated, truncated, stage, {k: json.dumps(v, sort_keys=True) for k, v in diagnostics.items()}, not wait, wait)
        if self.task_kind == 'pick_cube':
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
        if self.task_kind == 'pick_cube':
            from ..trajectory.canonical.h5 import save, load
            save(self.recording_path, value)
            identical = load(self.recording_path).to_mapping() == value.to_mapping()
            if not identical:
                raise ValueError('P1.6 canonical outer trajectory roundtrip mismatch')
            return {'logical_mapping_exact': identical,
                    'scope': 'canonical-v0 outer boundary; no native-substep or D0 claim'}
        save_streaming(self.recording_path, value)
        return verify_roundtrip(self.recording_path, value)
