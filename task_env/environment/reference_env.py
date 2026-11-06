"""Explicit selected-reference adapter, delegating task semantics and policies.

This adapter owns one scalar CPU session. It defines no TaskArtifact or task
success predicate. Expert execution and external-action execution cannot be
mixed in one episode. Rendering and legacy TaskEnv configuration are rejected.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from typing import Any
from collections.abc import Mapping
from pathlib import Path
import hashlib
from types import SimpleNamespace
from uuid import uuid4
import numpy as np
from .gym_compat import Box, Dict

from ..observations.selected_reference import _position_task_evaluation_state
from ..controllers.canonical.contracts import RequestedAction, REFERENCE_POSE_ACTION_SCHEMA, digest
from ..controllers.canonical.feedback import (
    boundary_interval_clock_tolerance as _boundary_interval_clock_tolerance,
    selected_control_application_receipt,
)
from .protocols import TaskEnvironmentComponent
from .gym_compat import GymEnvBase
from .configuration import resolve_env_config, resolve_execution_plan
from .config import ResolvedEnvConfig
from .metadata import TaskEnvMetadata, build_stage0_metadata, gym_metadata_dict, validate_task_info
from ..registry import AGENT_REGISTRY, OBJECT_REGISTRY, SCENE_REGISTRY
from .reference_binding import ReferenceTaskBinding
from .types import ExecutionFaultV1, StageUnavailableError, attach_execution_fault
from .lifecycle import EpisodeExecutionState, SingleTaskLifecycleAdapter, TaskLifecycleAdapter
from .types import ControlCommand, SnapshotRequest, TaskCompositionSpec, TaskEvaluation
from ..planners.completion import ExpertExecutionInfo
from ..runtime.sessions.api import close_session_and_runtime_owner, materialize
from ..runtime.sessions.control import ControlBinding, materialize_control
from ..runtime.sessions.source import (
    position_frame_bindings_from_artifact as _position_frame_bindings_from_artifact,
)

METADATA = {'action_schema': REFERENCE_POSE_ACTION_SCHEMA}
_RESET_SEED_UNSET = object()
_INFER_POSITION_TASK_SUCCESS = object()


def _artifact_for_reset(current_artifact, rebuilt_value, runtime_input=None):
    """Keep the reset Artifact identity bound to a versioned runtime input."""
    rebuilt_artifact = rebuilt_value['artifact']
    if rebuilt_artifact != current_artifact:
        raise ValueError('selected Artifact changed between construction and reset')
    if runtime_input is None:
        return current_artifact
    exact_artifact = runtime_input.artifact
    if rebuilt_artifact is not exact_artifact:
        raise ValueError('reset Artifact is not identical to its exact RuntimeInput artifact')
    return exact_artifact


def _json_value(value: Any) -> Any:
    """Copy public metadata into JSON-compatible builtin values."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


class SelectedReferenceEnv(GymEnvBase, TaskEnvironmentComponent):
    """Scalar task environment assembled from task and runtime components."""
    binding: ReferenceTaskBinding | None = None
    uid = 'base-task-env'
    task_uid = 'base-task-v1'
    scene_uid = 'tabletop-v1'
    agent_uids: tuple[str, ...] = ()
    object_uids: tuple[str, ...] = ()
    success_definition = 'none'
    supports_structured_control_recording = False
    metadata = {'render_modes': [], 'stage': 'stage4_gym_contract'}
    render_mode = None
    action_space = None
    observation_space = None

    @property
    def _last_episode_end(self):
        return self._episode_execution_state().episode_end

    @_last_episode_end.setter
    def _last_episode_end(self, value):
        self._episode_execution_state().episode_end = value

    def _build_runtime_with_rollback(self) -> None:
        try:
            from ..runtime import bootstrap_task_runtime

            self._reset_sampler = self.create_reset_sampler()
            self._runtime_assembly = bootstrap_task_runtime(
                config=self.config,
                composition=self._composition_spec,
                scene=self.scene,
                agents=self.agents,
                objects=self.objects,
                scene_composer=self.create_scene_composer(),
                reset_sampler=self._reset_sampler,
                create_render_source=self.render_mode is not None,
            )
            self._runtime = self._runtime_assembly.boundary
            compiled_scene = self._runtime_assembly.compiled_scene
            # Task definitions are created before action/observation binding so
            # the three task extension points are the only task-owned factories.
            self._task_definition = self.create_task_definition(compiled_scene)
            if self.config.render.camera_obs:
                from ..observations import CameraObservationProvider, CameraSensor

                self._camera_sensors = tuple(
                    CameraSensor(
                        spec=spec,
                        references=self._runtime_assembly.compiled_scene.references,
                    )
                    for spec in self.config.render.cameras
                )
                self._sensor_provider = CameraObservationProvider(
                    render_source=self._runtime_assembly.render_source,
                    config=self.config.render,
                    camera_sensors=self._camera_sensors,
                )
            resolved_agents = compiled_scene.references.agents
            if len(resolved_agents) > 1:
                raise StageUnavailableError(
                    "Stage 10b supports env.robot only for a single resolved robot; "
                    "multi-robot controller ownership is not implemented."
                )
            resolved_agent = next(
                (agent for agent in self.agents if agent.uid in resolved_agents), None,
            )
            bind_runtime = getattr(resolved_agent, 'bind_runtime', None)
            if callable(bind_runtime):
                self._robot, action_spec = bind_runtime(
                    references=resolved_agents[resolved_agent.uid], config=self.config,
                    boundary=self._runtime_assembly.boundary,
                )
                self._env_metadata = replace(self._env_metadata, external_action=action_spec)
                self.action_space = self._robot.controller.action_space
            else:
                task_action_factory = getattr(
                    self._task_definition,
                    "create_action_adapter",
                    None,
                )
                if callable(task_action_factory):
                    self._action_adapter = task_action_factory(compiled_scene)
                else:
                    self._action_adapter = self.create_action_adapter(compiled_scene)
                if self._action_adapter is not None:
                    self.action_space = self._action_adapter.action_space
                    action_contract = getattr(self._action_adapter, "action_contract", None)
                    if action_contract is None:
                        raise StageUnavailableError(
                            "non-robot action adapters must expose action_contract"
                        )
                    self._env_metadata = replace(
                        self._env_metadata,
                        external_action=action_contract,
                    )
                else:
                    self.action_space = Box(
                        low=-1.0,
                        high=1.0,
                        shape=(0,),
                        dtype=np.float32,
                    )

            if self._action_adapter is None and not self.config.agents.agent_uids:
                self.action_space = Box(
                    low=-1.0,
                    high=1.0,
                    shape=(0,),
                    dtype=np.float32,
                )
            task_observation_factory = getattr(
                self._task_definition,
                "create_observation_builder",
                None,
            )
            if callable(task_observation_factory):
                self._observation_builder = task_observation_factory(
                    compiled_scene,
                    observation_config=self.config.observation,
                    render_config=self.config.render,
                )
            else:
                self._observation_builder = self.create_observation_builder(
                    compiled_scene
                )
            self.observation_space = self._observation_builder.observation_space
            self.metadata = gym_metadata_dict(
                self._env_metadata,
                observation_schema=self._observation_builder.schema,
                stage="stage4_gym_contract",
            )
            self._configure_render_metadata()
            reference_profile = _json_value(self.reference_profile())
            if reference_profile:
                self.metadata["reference_profile"] = reference_profile
            self._task_lifecycle = SingleTaskLifecycleAdapter(
                runtime=self._runtime,
                episode_state=self._episode_execution_state(),
                task_definition=self._task_definition,
                control_substeps=self.config.runtime.control_substeps,
                expected_control_dt_s=(
                    self.config.runtime.physics_dt
                    * self.config.runtime.control_substeps
                ),
                horizon=self.config.episode.horizon,
                ignore_done=self.config.episode.ignore_done,
                sample_reset_state=self._sample_episode_reset_state_for_lifecycle,
                snapshot_request=self._snapshot_request,
                reset_components=self._reset_episode_components,
                convert_action=self._convert_action,
                observation_fallback=self._build_observation_fallback,
                episode_limits=lambda: (
                    self.config.episode.horizon,
                    self.config.episode.ignore_done,
                ),
            )
        except BaseException as construction_error:
            attach_execution_fault(
                construction_error,
                ExecutionFaultV1.from_exception(
                    "runtime_construction",
                    construction_error,
                ),
            )
            try:
                self.close()
            except BaseException as cleanup_error:
                add_note = getattr(construction_error, "add_note", None)
                if callable(add_note):
                    add_note(f"construction rollback also failed: {cleanup_error!r}")
            raise

    @classmethod
    def default_config(cls) -> ResolvedEnvConfig:
        return resolve_env_config(
            task_uid=cls.task_uid,
            scene_uid=cls.scene_uid,
            agent_uids=cls.agent_uids,
            object_uids=cls.object_uids,
            success_definition=cls.success_definition,
        )

    @classmethod
    def default_config_path(cls) -> Path | None:
        """Return the task-owned public default YAML, when the task has one."""

        task_dir = cls.task_uid.rsplit("-v", 1)[0].replace("-", "_")
        candidate = Path(__file__).resolve().parents[1] / "tasks" / task_dir / "default.yaml"
        return candidate if candidate.is_file() else None

    def placement_notes(self) -> tuple[str, ...]:
        return ()

    def reference_profile(self) -> dict[str, Any]:
        """Return the versioned task physics/semantic profile for metadata.

        The base task has no reference profile.  Non-arm classic-control tasks
        override this hook so the profile travels with Gym metadata and H5
        ``env_meta`` without adding task-specific branches to the base class.
        """

        return {}

    def create_scene_composer(self):
        return None

    def create_reset_sampler(self):
        return None

    def create_action_adapter(self, compiled_scene):
        """Create a neutral native-action adapter for non-robot tasks."""

        del compiled_scene
        return None

    def create_observation_builder(self, compiled_scene):
        """Create the task observation builder after scene references resolve."""

        from ..observations import StateObservationBuilder

        return StateObservationBuilder(
            references=compiled_scene.references,
            config=self.config.observation,
            render_config=self.config.render,
        )

    def create_task_definition(self, compiled_scene):
        del compiled_scene
        return None

    @property
    def execution_plan(self):
        """Return the static plan resolved before provider construction."""

        return self._execution_plan

    @property
    def robot(self):
        """The single resolved robot owned by this environment runtime."""

        self._require_runtime()
        if self._robot is None:
            raise StageUnavailableError(
                "This environment does not expose a single resolved robot."
            )
        return self._robot

    def get_env_metadata(self) -> TaskEnvMetadata:
        return self._env_metadata

    def create_ui_render_provider(self):
        """Create the optional UI backend without involving camera sensors."""

        if self.render_mode is None:
            return None
        if self._ui_render_provider is None:
            render_source = getattr(self._runtime_assembly, "render_source", None)
            if render_source is None:
                raise StageUnavailableError(
                    "UI rendering was requested but the runtime did not expose a render source"
                )
            from ..render import TaskEnvRenderProvider

            self._ui_render_provider = TaskEnvRenderProvider(
                render_source=render_source,
                config=self.config.render,
            )
        return self._ui_render_provider

    def _configure_render_metadata(self) -> None:
        if self.render_mode is None:
            self.metadata["render_modes"] = []
            self.metadata.pop("render_mode", None)
            return
        self.metadata["render_modes"] = ["human", "rgb_array"]
        self.metadata["render_mode"] = self.render_mode
        self.metadata["render_backend"] = self.config.render.backend
        self.metadata["render_resolution"] = (
            int(self.config.render.width),
            int(self.config.render.height),
        )

    def render(self, mode: str | None = None):
        """Render the configured single-environment UI frame.

        This intentionally does not return a camera observation. RGB/depth policy
        observations are captured by ``task_env.observations`` during reset/step.
        """

        from ..render import RenderUnavailableError, normalize_render_mode

        requested_mode = mode
        if requested_mode is None:
            requested_mode = self.render_mode or "human"
        normalized_mode = normalize_render_mode(requested_mode)
        if self.render_mode is not None and normalized_mode.value != self.render_mode:
            raise ValueError(
                "TaskEnv render mode is fixed at construction: "
                f"{self.render_mode!r}, got {normalized_mode.value!r}"
            )
        provider = self.create_ui_render_provider()
        if provider is None:
            raise RenderUnavailableError(
                "UI rendering is not configured for this TaskEnv; camera observations "
                "are available through observation/sensor configuration instead."
            )
        return provider.render(mode=normalized_mode, snapshot=self._last_snapshot)

    @property
    def task_references(self):
        self._require_runtime()
        return self._runtime_assembly.compiled_scene.references

    def _require_runtime(self):
        if self._runtime is None:
            raise StageUnavailableError(
                "TaskEnv runtime was not built; construct with build_runtime=True."
            )
        return self._runtime

    def _require_task_lifecycle(self) -> SingleTaskLifecycleAdapter:
        if self._task_lifecycle is None:
            raise StageUnavailableError(
                "TaskEnv scalar lifecycle was not built; construct with build_runtime=True."
            )
        return self._task_lifecycle

    @property
    def episode_end(self):
        """Return the most recent immutable Event/Outcome finalizer result."""

        lifecycle = getattr(self, '_task_lifecycle', None)
        if lifecycle is not None and lifecycle.episode_end is not None:
            return lifecycle.episode_end
        return self._last_episode_end

    def _snapshot_request(self) -> SnapshotRequest:
        return SnapshotRequest(
            site_jacobians=self._robot is not None,
            actuator_force=(
                self._robot is not None
                and self.config.robot.gripper.kind == "experimental_rate_limited"
            ),
            contact_summary=bool(
                getattr(self._task_definition, "requires_contact_summary", False)
            ),
            simulation_time=True,
        )

    def _reset_episode_components(self, snapshot) -> None:
        if self._robot is not None:
            self._robot.controller.reset(snapshot)
            reset_gripper = getattr(self._robot.gripper, "reset", None)
            if callable(reset_gripper):
                reset_gripper(snapshot)
        if self._action_adapter is not None:
            self._action_adapter.reset(snapshot)
        if self._sensor_provider is not None:
            self._sensor_provider.reset()

    def _convert_action(self, action, snapshot):
        if self._robot is None and self._action_adapter is None and self.config.agents.agent_uids:
            raise StageUnavailableError(
                "This environment has no Stage 2 ActionAdapter."
            )
        if self._action_adapter is not None:
            return self._action_adapter.convert(action, snapshot)
        if self._robot is None:
            requested = np.asarray(action, dtype=np.float32)
            if requested.shape != (0,):
                raise ValueError(f"action shape must be {(0,)}, got {requested.shape}")
            if not np.isfinite(requested).all():
                raise ValueError("action must contain only finite values")
            ctrl = (
                np.zeros(0, dtype=np.float32)
                if snapshot.ctrl is None
                else np.asarray(snapshot.ctrl, dtype=np.float32).copy()
            )
            return ControlCommand(
                actuator_ctrl=ctrl,
                external_action=requested,
                requested_action=requested,
                controller_target=ctrl,
                universal_action=np.zeros(0, dtype=np.float32),
                mode="no_op",
            )
        return self._robot.controller.convert(action, snapshot)

    def _build_observation_fallback(self, snapshot):
        if self._observation_builder is None:
            raise StageUnavailableError("This environment has no Stage 3 ObservationBuilder.")
        self._last_camera_metadata = {}
        sensor_observation = None
        if self._sensor_provider is not None:
            sensor_observation = self._sensor_provider.capture(snapshot)
            self._last_camera_metadata = dict(sensor_observation.camera_metadata)
        return self._observation_builder.build(snapshot, sensor_observation)

    @staticmethod
    def _require_simulation_time_s(snapshot) -> float:
        value = getattr(snapshot, "simulation_time", None)
        if value is None or not np.isfinite(float(value)):
            raise ValueError("TaskEnv info requires finite simulation_time_s from RuntimeSnapshot")
        return float(value)

    def _camera_capture_info(self, *, elapsed_steps: int, simulation_time_s: float):
        if not self._last_camera_metadata:
            return None
        cameras = {
            str(name): _json_value(asdict(value) if is_dataclass(value) else value)
            for name, value in self._last_camera_metadata.items()
        }
        return {
            "source": "SensorObservation.camera_metadata",
            "observation_boundary": {
                "elapsed_steps": int(elapsed_steps),
                "simulation_time_s": float(simulation_time_s),
            },
            "cameras": cameras,
        }

    def _format_step_result(self, lifecycle, result):
        snapshot = result.snapshot
        evaluation = result.evaluation
        command = result.command
        applied = result.applied
        self._last_snapshot = snapshot
        self._elapsed_steps = result.elapsed_steps
        action_info = {
            "requested": command.requested_action,
            "external": command.external_action,
            "controller_target": command.controller_target,
            "requested_ctrl": applied.requested_ctrl,
            "applied_ctrl": applied.applied_ctrl,
            "mode": command.mode,
        }
        if self.config.observation.include_diagnostics:
            action_info.update(
                {
                    "clipped": bool(command.action_clipped or applied.clipped),
                    "action_clipped": command.action_clipped,
                    "ctrl_clipped": applied.clipped,
                }
            )
        simulation_time_s = self._require_simulation_time_s(snapshot)
        info = {
            "is_success": evaluation.success,
            "elapsed_steps": self._elapsed_steps,
            "task_metrics": evaluation.metrics,
            "reward_terms": evaluation.reward_terms,
            "task_reward": evaluation.reward,
            "task_failure": evaluation.failure,
            "action": action_info,
            "success_definition": self.config.task.success_definition,
            "requested_action": command.requested_action,
            "external_action": command.external_action,
            "controller_target": command.controller_target,
            "requested_ctrl": applied.requested_ctrl,
            "applied_ctrl": applied.applied_ctrl,
            "observation_schema": self._observation_builder.schema,
            "simulation_time_s": simulation_time_s,
        }
        if result.episode_end is not None:
            self._last_episode_end = result.episode_end
            info["episode_end_v1"] = result.episode_end.to_mapping()
        if self.config.observation.include_diagnostics:
            info["action_clipped"] = command.action_clipped
            info["ctrl_clipped"] = applied.clipped
        # ``universal_action`` is the one canonical action after the
        # controller/native adapter boundary.  Its schema is task-family
        # specific: Panda keeps its historical eight-dimensional layout,
        # while native non-arm tasks expose their runtime actuator vector.
        info["universal_action"] = command.universal_action
        action_info["universal_action"] = command.universal_action
        camera_capture = self._camera_capture_info(
            elapsed_steps=self._elapsed_steps,
            simulation_time_s=simulation_time_s,
        )
        if camera_capture is not None:
            info["camera_capture"] = camera_capture
        validate_task_info(info, phase="step")
        return result.observation, evaluation.reward, result.terminated, result.truncated, info

    def _placeholder_evaluation(self) -> TaskEvaluation:
        return TaskLifecycleAdapter.placeholder_evaluation()

    def _reset_task_evaluation(self, snapshot) -> TaskEvaluation:
        if self._task_lifecycle is None:
            return self._placeholder_evaluation()
        evaluation = self._task_lifecycle.reset_task(
            state=snapshot,
            reset_mask=np.ones(1, dtype=np.bool_),
            legacy_snapshot=snapshot,
        )
        return TaskLifecycleAdapter.coerce_scalar_evaluation(evaluation)

    def _sample_episode_reset_state_for_lifecycle(
        self,
        seed: int | None,
        rng: np.random.Generator,
    ):
        return self._sample_episode_reset_state(seed=seed, rng=rng)

    def _sample_episode_reset_state(
        self,
        *,
        seed: int | None,
        rng: np.random.Generator | None = None,
    ):
        """Resolve one episode reset without changing the compiled baseline.

        A task sampler may opt into per-episode state sampling with
        ``sample_episode_state``.  The hook is deliberately at the public
        reset boundary: it receives only the immutable compiled scene and the
        Gym RNG, returns a value-object state, and cannot advance physics.
        Existing task samplers that only implement construction-time
        ``resolve_initial_state`` keep their original deterministic behavior.
        """

        runtime = self._require_runtime()
        sampler = self._reset_sampler
        reset_rng = self.np_random if rng is None else rng
        sample_state = getattr(sampler, "sample_episode_state", None)
        if not callable(sample_state):
            return runtime.initial_state, {}
        state, parameters = sample_state(
            compiled_scene=self._runtime_assembly.compiled_scene,
            initial_state=runtime.initial_state,
            rng=reset_rng,
            seed=seed,
        )
        if not isinstance(parameters, dict):
            raise TypeError("episode reset sampler must return a dict of parameters")
        return state, _json_value(parameters)

    def _evaluate_task(self, previous_snapshot, action, snapshot) -> TaskEvaluation:
        if self._task_lifecycle is None:
            return self._placeholder_evaluation()
        evaluation = self._task_lifecycle.evaluate_task(
            state=snapshot,
            action=action,
            elapsed_steps=int(self._elapsed_steps),
            previous_state=previous_snapshot,
            legacy_previous_snapshot=previous_snapshot,
            legacy_current_snapshot=snapshot,
        )
        return TaskLifecycleAdapter.coerce_scalar_evaluation(evaluation)

    @staticmethod
    def _coerce_scalar_evaluation(evaluation: Any) -> TaskEvaluation:
        return TaskLifecycleAdapter.coerce_scalar_evaluation(evaluation)

    def _build_observation(self, snapshot):
        if self._task_lifecycle is None:
            raise StageUnavailableError("This environment has no task lifecycle adapter.")
        return self._task_lifecycle.build_observation(
            snapshot,
            fallback=lambda: self._build_observation_fallback(snapshot),
        )


    @classmethod
    def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
        values = {} if config is None else dict(config)
        if kwargs or render_mode is not None:
            raise ValueError('selected reference admits state-only execution without extra kwargs')
        if set(values) - {'provider', 'backend', 'horizon'}:
            raise ValueError('selected reference config admits provider/backend/horizon only; legacy overlays are incompatible')
        return cls(**values)

    @classmethod
    def from_resolved_config(cls, config, *, render_mode=None, **kwargs):
        """Assemble a selected task that supplies its own binding for a config."""
        from .config import ResolvedSelectedConfig

        if type(config) is not ResolvedSelectedConfig or config.task_uid != cls.uid:
            raise TypeError('selected construction requires its own resolved configuration')
        # Direct advanced callers must pass through the same validation as the
        # public factory; a fabricated resolved value is not an admission token.
        from .configuration import resolve_task_env_config
        config = resolve_task_env_config(cls, config)
        if kwargs or render_mode is not None:
            raise ValueError('selected reference admits state-only execution without extra kwargs')
        binding = cls.selected_binding(config)
        env = cls(provider=config.physics_provider, backend=config.environment.runtime.backend,
                  horizon=config.environment.episode.horizon, _binding=binding)
        env.resolved_public_config = config
        return env

    @classmethod
    def from_position_candidate(
        cls, binding: ReferenceTaskBinding, *, provider='geophys', backend='cpu', horizon=6000,
        camera_observation_config=None, execution_spec=None,
    ):
        """Explicitly construct a bounded Position profile through the selected binding."""
        if not isinstance(binding, ReferenceTaskBinding):
            raise TypeError('PositionServoV1 candidate requires the existing ReferenceTaskBinding')
        from ..runtime.sessions.control import is_admitted_position_profile_set

        candidate_type = cls
        if getattr(cls, 'uid', None) == 'base-task-env':
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
        if not is_admitted_position_profile_set(profiles):
            env.close()
            raise TypeError('candidate binding did not construct one or two Entity-bound PositionServoV1 profiles')
        if camera_observation_config is not None and len(profiles) != 1:
            env.close()
            raise ValueError('R04a camera observation is bounded to the existing single Panda Position source')
        if (provider, backend) == ('mujoco', 'cpu') and camera_observation_config is None:
            from .configuration import resolve_candidate_execution_selection
            try:
                env._candidate_execution_selection = resolve_candidate_execution_selection(
                    provider=provider, backend=backend, source=env.value['source'], execution_spec=execution_spec)
            except BaseException:
                env.close()
                raise
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
        if not fixed_attachment and getattr(cls, 'uid', None) == 'base-task-env':
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
        from .configuration import resolve_candidate_execution_selection
        try:
            env._candidate_execution_selection = resolve_candidate_execution_selection(
                provider=provider, backend=backend, source=env.value['source'])
        except BaseException:
            env.close()
            raise
        return env

    def _selected_execution_context(self):
        resolved = getattr(self, 'resolved_public_config', None)
        if resolved is not None:
            return resolved.execution_spec_v2, resolved.requested_execution_json
        return getattr(self, '_candidate_execution_selection', None), None

    @classmethod
    def from_mixed_control_candidate(cls, binding, *, provider='mujoco', backend='cpu', horizon=6000):
        """Construct a typed source-bound mixed-control candidate through the existing route."""
        if not isinstance(binding, ReferenceTaskBinding):
            raise TypeError('mixed-control candidate requires the existing ReferenceTaskBinding owner')
        if provider not in {'mujoco', 'geophys'} or backend != 'cpu':
            raise ValueError('mixed-control candidate currently admits MuJoCo or GeoPhys CPU')
        if (binding.build_mixed_control_profile is None
                or binding.reset_sample_with_options is None
                or binding.prepare_mixed_control is None
                or binding.observe_mixed_control is None
                or binding.mixed_record_metadata is None):
            raise TypeError('binding does not own the complete mixed-control lifecycle hooks')
        candidate_type = cls
        if getattr(cls, 'uid', None) == 'base-task-env':
            candidate_type = type(
                'MixedControlSelectedReferenceEnv', (cls,),
                {'uid': 'selected-reference-mixed-control-v1'},
            )
        env = candidate_type(
            provider=provider, backend=backend, horizon=horizon,
            _binding=binding, _mixed_control_candidate=True,
        )
        if not getattr(env, 'mixed_control_profile', False):
            env.close()
            raise TypeError('candidate did not construct its typed mixed-control profile')
        return env

    def _bind_selected_controller(self, value):
        from ..runtime.sessions.control import bind_selected_controller

        selected = bind_selected_controller(
            value, binding=self.binding, provider=self.provider, backend=self.backend,
        )
        self.mixed_control_profile = selected.mixed
        self.leaf_plan = selected.leaf_plan
        self.leaf_position_profile = selected.leaf_plan is not None
        self.position_profiles = selected.position_profiles
        self.position_profile = selected.position
        self.controller = selected.controller

    def _episode_execution_state(self):
        state = self.__dict__.get('_episode_state')
        if state is None:
            state = self.__dict__['_episode_state'] = EpisodeExecutionState()
        return state

    @property
    def _closed(self):
        return self._episode_execution_state().closed

    @_closed.setter
    def _closed(self, value):
        self._episode_execution_state().closed = value

    @property
    def _stopped(self):
        return self._episode_execution_state().stopped

    @_stopped.setter
    def _stopped(self, value):
        self._episode_execution_state().stopped = value

    @property
    def _position_episode_end(self):
        if getattr(self, '_mixed_control_candidate', False):
            return None
        return self._episode_execution_state().episode_end

    @_position_episode_end.setter
    def _position_episode_end(self, value):
        if not getattr(self, '_mixed_control_candidate', False):
            self._episode_execution_state().episode_end = value
        elif value is not None:
            raise ValueError('Position episode end is not valid for mixed control')

    @property
    def _mixed_episode_end(self):
        if not getattr(self, '_mixed_control_candidate', False):
            return None
        return self._episode_execution_state().episode_end

    @_mixed_episode_end.setter
    def _mixed_episode_end(self, value):
        if getattr(self, '_mixed_control_candidate', False):
            self._episode_execution_state().episode_end = value
        elif value is not None:
            raise ValueError('mixed episode end is not valid for Position control')

    @property
    def _selected_episode_id(self):
        return self._episode_execution_state().episode_id

    @_selected_episode_id.setter
    def _selected_episode_id(self, value):
        self._episode_execution_state().episode_id = value

    @property
    def _execution_fault(self):
        return self._episode_execution_state().fault

    @_execution_fault.setter
    def _execution_fault(self, value):
        self._episode_execution_state().fault = value

    def _format_component_reset(self, lifecycle, result, seed):
        snapshot = result.snapshot
        evaluation = result.evaluation
        reset_parameters = result.reset_parameters
        self._last_snapshot = snapshot
        self._elapsed_steps = lifecycle.elapsed_steps
        self._last_episode_end = None
        try:
            simulation_time_s = self._require_simulation_time_s(snapshot)
            info = {
                "seed": seed,
                "reset_parameters": reset_parameters,
                "task_uid": self.config.task.task_uid,
                "stage": "stage4_gym_contract",
                "is_success": evaluation.success,
                "elapsed_steps": self._elapsed_steps,
                "task_metrics": evaluation.metrics,
                "reward_terms": evaluation.reward_terms,
                "task_reward": evaluation.reward,
                "task_failure": evaluation.failure,
                "success_definition": self.config.task.success_definition,
                "resolved_control_metadata": self.metadata["action_schema"],
                "observation_schema": self._observation_builder.schema,
                "simulation_time_s": simulation_time_s,
                "episode_id": lifecycle.episode_id,
                "termination_policy": lifecycle.termination_policy.to_mapping(),
            }
            if result.previous_episode_end is not None:
                info["previous_episode_end_v1"] = result.previous_episode_end.to_mapping()
            camera_capture = self._camera_capture_info(
                elapsed_steps=self._elapsed_steps,
                simulation_time_s=simulation_time_s,
            )
            if camera_capture is not None:
                info["camera_capture"] = camera_capture
            validate_task_info(info, phase="reset")
            return result.observation, info
        except BaseException as error:
            lifecycle._latch_fault(
                "gymnasium_reset_result",
                error,
                after_snapshot=snapshot,
                control_step_before=0,
                control_step_after=0,
            )
            raise

    def _format_component_step(self, lifecycle, result):
        try:
            return self._format_step_result(lifecycle, result)
        except BaseException as error:
            lifecycle.revoke_unpublished_step(result)
            lifecycle._latch_fault(
                "gymnasium_result",
                error,
                before_snapshot=result.previous_snapshot,
                after_snapshot=result.snapshot,
                control_step_before=max(0, result.elapsed_steps - 1),
                control_step_after=result.elapsed_steps,
                interval_attempted=True,
                interval_completed=True,
            )
            self._last_snapshot = result.snapshot
            self._elapsed_steps = result.elapsed_steps
            raise

    def _component_record_metadata(self) -> dict[str, Any]:
        """Return the JSON-compatible public projection used by recorders only."""
        metadata = {
            "env_metadata": _json_value(self.metadata),
            "resolved_config": _json_value(asdict(self.config)),
        }
        metadata["universal_action_schema"] = _json_value(
            self.metadata.get("universal_action_schema", {})
        )
        return metadata

    def _close_component_resources(self) -> None:
        # Runtime lifecycle may already be closed independently.  The Env
        # still owns auxiliary UI/sensor resources and must release them once.
        if getattr(self, "_resources_closed", False):
            return
        ui_provider = getattr(self, "_ui_render_provider", None)
        sensor_provider = getattr(self, "_sensor_provider", None)
        lifecycle = getattr(self, "_task_lifecycle", None)
        runtime = getattr(self, "_runtime", None)
        self._ui_render_provider = None
        self._sensor_provider = None
        self._task_lifecycle = None
        self._runtime = None
        self._runtime_assembly = None

        owners = [ui_provider, sensor_provider]
        # SingleTaskLifecycleAdapter is the sole closer of the RuntimeBoundary.
        # Before it exists (including partial construction), the environment
        # falls back to closing a boundary that was already returned by bootstrap.
        owners.append(lifecycle if lifecycle is not None else runtime)
        first_error: BaseException | None = None
        for owner in owners:
            close = getattr(owner, "close", None)
            if not callable(close):
                continue
            try:
                close()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        episode_end = getattr(lifecycle, "episode_end", None)
        if episode_end is not None:
            self._last_episode_end = episode_end
        self._resources_closed = True
        if first_error is not None:
            raise first_error

    def _has_component_assembly(self):
        return getattr(self, '_uses_component_assembly',
                       getattr(type(self), 'uses_component_task_config', False)
                       or '_task_lifecycle' in self.__dict__)

    def _initialize_components(
        self,
        config: ResolvedEnvConfig | None = None,
        *,
        render_mode=None,
        build_runtime: bool = True,
    ) -> None:
        self._closed = False
        self._last_episode_end = None
        self.config = config if config is not None else self.default_config()
        # Import only the lightweight render contract during environment
        # construction. Concrete renderer backends stay out of the physics
        # bootstrap.
        from ..render.base.contracts import normalize_render_mode

        self.render_mode = (
            None
            if render_mode is None
            else normalize_render_mode(render_mode).value
        )
        self._ui_render_provider = None
        self.scene = SCENE_REGISTRY.create(self.config.scene.scene_uid)
        self.agents = tuple(
            AGENT_REGISTRY.create(uid) for uid in self.config.agents.agent_uids
        )
        self.objects = tuple(
            OBJECT_REGISTRY.create(uid) for uid in self.config.objects.object_uids
        )
        self._composition_spec = TaskCompositionSpec(
            task_uid=self.config.task.task_uid,
            scene_uid=self.config.scene.scene_uid,
            agent_uids=self.config.agents.agent_uids,
            object_uids=self.config.objects.object_uids,
            placement_notes=self.placement_notes(),
            success_definition=self.config.task.success_definition,
        )
        self._execution_plan = resolve_execution_plan(
            type(self),
            self.config,
            agents=self.agents,
            render_mode=self.render_mode,
        )
        self._env_metadata = build_stage0_metadata(self.uid, self.config)
        self._runtime_assembly = None
        self._runtime = None
        self._reset_sampler = None
        self._robot = None
        self._action_adapter = None
        self._observation_builder = None
        self._task_definition = None
        self._task_lifecycle = None
        self._camera_sensors = ()
        self._sensor_provider = None
        self._last_camera_metadata = {}
        self._last_snapshot = None
        self._elapsed_steps = 0
        self.metadata = gym_metadata_dict(self._env_metadata, stage="stage4_gym_contract")
        reference_profile = _json_value(self.reference_profile())
        if reference_profile:
            self.metadata["reference_profile"] = reference_profile
        self._configure_render_metadata()
        if build_runtime:
            self._build_runtime_with_rollback()


    def _initialize_selected_value(self, *, mixed_control_candidate, camera_observation_config):
        """Initialize task-declared metadata before the selected Env is published."""
        self.artifact = self.value['artifact']
        self.solution = self.value['solution']
        self._bind_selected_controller(self.value)
        self._mixed_initial_value_pending = bool(mixed_control_candidate)
        self.dual_entity_position = len(self.position_profiles) == 2
        if not self.position_profile and not mixed_control_candidate:
            if type(self.binding.scalar_control_binding) is not ControlBinding:
                raise TypeError('selected scalar control requires its declared ControlBinding')
        if camera_observation_config is not None and not self.position_profile:
            raise ValueError('the R04a camera consumer is admitted only by the existing Position candidate')
        self.camera_observation_config = camera_observation_config
        self._camera_consumer = None
        self._camera_session_factory = None
        self.metadata = {'env_id': self.uid,
            'task_artifact_hash': self.artifact.identity_hash,
            'construction_id': self.value['construction_id'],
            'control_dt': self.artifact.timebase.control_dt}
        self.supports_structured_control_recording = bool(mixed_control_candidate)
        if mixed_control_candidate:
            action_schema = self.value.get('action_schema')
            if not isinstance(action_schema, Mapping):
                raise TypeError('mixed-control task binding must supply its typed action schema')
            self.metadata['action_schema'] = dict(action_schema)
            self.action_space = self.value.get('action_space')
            self.observation_space = self.value.get('observation_space')
            if self.action_space is None or self.observation_space is None:
                raise TypeError('mixed-control task binding must supply task-owned spaces')
        else:
            self.metadata['action_schema'] = dict(self.binding.action_schema)
            self.action_space = self.binding.action_space_factory()
        if not mixed_control_candidate:
            observation_spaces = self.binding.observation_space_factory(self)
        if camera_observation_config is not None:
            from ..observations.selected_reference import position_camera_observation_declaration

            camera_spaces, self.camera_observation_schema = position_camera_observation_declaration(
                self.binding, camera_observation_config,
            )
            observation_spaces.update(camera_spaces)
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
        if not mixed_control_candidate:
            self.observation_space = Dict(observation_spaces)

    def __init__(self, config=None, *, render_mode=None, build_runtime=True,
                 provider='geophys', backend='cpu', horizon=6000,
                 _binding=None,
                 _native_feedback_request=None,
                 camera_observation_config=None, _leaf_position_candidate=False,
                 _fixed_attachment_leaf_position_candidate=False,
                 _execution_spec_v1=None, _mixed_control_candidate=False,
                 _initial_value=None):
        self._uses_component_assembly = bool(
            getattr(type(self), 'uses_component_task_config', False)
            or config is not None
            or (_binding is None and self.binding is None
                and getattr(type(self).from_reference_config, '__func__', None)
                is SelectedReferenceEnv.from_reference_config.__func__)
        )
        if self._uses_component_assembly:
            self._initialize_components(config, render_mode=render_mode, build_runtime=build_runtime)
            return
        if render_mode is not None or build_runtime is not True:
            raise ValueError('selected reference rendering and component runtime options require a component task')
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
        if _mixed_control_candidate and (
            (provider not in {'mujoco', 'geophys'} or backend != 'cpu')
            or self.binding.build_mixed_control_profile is None
        ):
            raise ValueError('mixed-control candidate requires its scalar CPU task binding')
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
            from ..runtime.sessions.api import validate_selected_position_route
            validate_selected_position_route(_execution_spec_v1)
        self._declared_execution_spec_v1 = _execution_spec_v1
        diagnostic_profile = self.binding.diagnostic_profile
        if diagnostic_profile is not None and (provider != 'geophys' or backend not in {'cpu', 'cuda'}):
            raise ValueError('selected diagnostic profile requires GeoPhys CPU/CUDA')
        if sum((bool(_mixed_control_candidate), diagnostic_profile is not None,
                _native_feedback_request is not None)) > 1:
            raise ValueError('diagnostic, native-feedback, and mixed-control profiles are mutually exclusive')
        self._diagnostic_profile = diagnostic_profile
        self._native_feedback_profile = None
        self._native_feedback_request = None
        self._mixed_control_candidate = bool(_mixed_control_candidate)
        if _mixed_control_candidate:
            build_value = lambda: self.binding.build_mixed_control_profile(provider, backend)
        elif _native_feedback_request is None:
            if (diagnostic_profile is None and _execution_spec_v1 is None
                    and (provider not in {'geophys', 'mujoco'} or backend != 'cpu')):
                raise ValueError('selected reference currently admits GeoPhys/MuJoCo scalar CPU only')
            if self.binding.build_seeded is not None:
                build_value = lambda: self.binding.build_seeded(provider, backend, 31, horizon)
            else:
                build_value = lambda: self.binding.build_for_provider(provider)
        else:
            if self.binding.admit_native_feedback_profile is None:
                raise ValueError(
                    'normal native-feedback profile requires an opted-in task binding'
                )
            self._native_feedback_profile = self.binding.admit_native_feedback_profile(
                provider, backend, _native_feedback_request,
            )
            if type(self._native_feedback_profile) is not str or not self._native_feedback_profile:
                raise ValueError('native-feedback admission must return a nonempty profile identifier')
            self._native_feedback_request = _native_feedback_request
            build_value = lambda: self.binding.build_native_feedback_profile(
                provider, backend, _native_feedback_request, False,
            )
        self.provider, self.backend, self.horizon = provider, backend, horizon
        self._execution_fault = None
        try:
            if _initial_value is not None:
                if (_execution_spec_v1 is None or not isinstance(_initial_value, dict)
                        or _initial_value.get('execution_spec_v1') != _execution_spec_v1):
                    raise ValueError('precompiled selected value must match its execution specification')
                self.value = _initial_value
            else:
                self.value = build_value()
        except BaseException as error:
            fault = ExecutionFaultV1.from_exception(
                'selected_construction', error
            )
            self._execution_fault = fault
            attach_execution_fault(error, fault)
            raise
        try:
            self._initialize_selected_value(
                mixed_control_candidate=_mixed_control_candidate,
                camera_observation_config=camera_observation_config,
            )
        except BaseException as error:
            def close_source():
                source = self.value.get('source') if isinstance(self.value, Mapping) else None
                receipt = getattr(source, 'execution_source_receipt', None)
                if receipt is not None:
                    receipt.close()

            for label, cleanup in (
                ('source', close_source),
                ('task resource', self.binding.close_task_resources),
            ):
                if callable(cleanup):
                    try:
                        cleanup()
                    except BaseException as cleanup_error:
                        error.add_note(f'{label} cleanup after selected construction failed: {cleanup_error!r}')
            fault = ExecutionFaultV1.from_exception('selected_construction', error)
            self._execution_fault = fault
            attach_execution_fault(error, fault)
            raise
        self.session = None
        self._external_solution_owner = None
        self._active_native_interval_receipt = None
        self._closed = False
        self._episode_mode = None
        self._stopped = True
        self._position_episode_end = None
        self._mixed_episode_end = None
        self._mixed_close_receipt = None
        self._mixed_reset_context = None
        self._mixed_record_metadata = None
        self._mixed_reset_plan = None
        self._compiled_layout_pre_reset = None
        self._compiled_layout_post_reset = None
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

    @property
    def reset_failure_receipt(self):
        """Return an owned record of reset effects; unknown writes are not rollback."""
        from copy import deepcopy
        return deepcopy(getattr(self, '_reset_failure_receipt', None))

    def get_runtime_progress_receipt(self):
        if not getattr(self, 'mixed_control_profile', False) or self.session is None:
            raise StageUnavailableError('mixed runtime progress is unavailable on this selected route')
        return self.session.runtime_progress_receipt

    @property
    def close_receipt(self):
        if not getattr(self, 'mixed_control_profile', False):
            raise StageUnavailableError('mixed-control close evidence is unavailable on this selected route')
        if self._mixed_close_receipt is None:
            raise RuntimeError('mixed-control selected environment close has not completed')
        return dict(self._mixed_close_receipt)

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
        self._episode_execution_state().latch_fault(fault, stop=True)
        attach_execution_fault(error, fault)
        return fault

    @property
    def composition_spec(self):
        if self._has_component_assembly():
            return self._composition_spec
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
        self._episode_execution_state().require_open('environment is closed')
        component_lifecycle = None
        if self._has_component_assembly():
            seed = None if seed is _RESET_SEED_UNSET else seed
            GymEnvBase.reset(self, seed=seed)
            self._last_camera_metadata = {}
            component_lifecycle = self._require_task_lifecycle()
            operations = component_lifecycle.prepare_reset(seed=seed, options=options, rng=self.np_random)
        else:
            operations = self._prepare_reference_reset(seed=seed, options=options)
        result = self._episode_execution_state().execute_reset(**operations)
        if component_lifecycle is not None:
            return self._format_component_reset(component_lifecycle, result, seed)
        return result

    def reset_for_solution(self, solution, *, seed=_RESET_SEED_UNSET, options=None):
        """Reset this selected route for one caller-owned Solution instance.

        The task binding validates that the supplied mutable Solution matches
        the actual current Artifact/source/readiness configuration before the
        existing RuntimeSession is reconstructed.
        """
        if self.binding.build_external is None or self.binding.validate_external_solution is None:
            raise StageUnavailableError('this selected task has no external Solution lifecycle')
        self._episode_execution_state().require_open('environment is closed')
        self.binding.validate_external_solution(self.value, solution)
        operations = self._prepare_reference_reset(seed=seed, options=options, external_solution=solution)
        return self._episode_execution_state().execute_reset(**operations)

    def _prepare_reference_reset(self, *, seed=_RESET_SEED_UNSET, options=None, external_solution=None):
        self._episode_execution_state().require_open('environment is closed')
        from .reference_binding import prepare_selected_reset
        if self.binding.physical_control_profile is not None and (
                (self.provider, self.backend) != ('mujoco', 'cpu')
                or not self.position_profile):
            raise StageUnavailableError('physical-control RuntimeSession adapter is not implemented')
        if self.binding.physical_control_profile is not None:
            from ..runtime.sessions.mujoco_physical import preflight_physical_mujoco
            preflight_physical_mujoco(self.binding.physical_control_profile(self),
                                      self.artifact, self.value['source'])
        if self.recorder is not None and not getattr(self.recorder, 'frozen', getattr(self.recorder, '_frozen', False)):
            raise RuntimeError('finalize current recording before reset')
        switch_candidate = None
        candidate_value = None
        candidate_binding = self.binding
        resolved = getattr(self, 'resolved_public_config', None)
        switching = getattr(resolved, 'reset_profile', None) == 'pickcube-state-only-switch-v1'
        if switching:
            from .reset_switch import prepare_switch_reset
            if options is not None and (not isinstance(options, Mapping) or set(options) - {'execution'}):
                raise ValueError('reset options support only execution')
            target = None if options is None else options.get('execution')
            requested_seed = None if seed is _RESET_SEED_UNSET else seed
            rng_state = getattr(self, '_switch_rng_state', None)
            switch_candidate = prepare_switch_reset(type(self), resolved, requested_seed, rng_state, target)
            seed = switch_candidate.task_seed
            options, mixed_reset_plan, mixed_reset_sample = {}, None, None
            candidate_binding = type(self).selected_binding(switch_candidate.config)
            selection = switch_candidate.config.execution_spec_v2
            requested_json = switch_candidate.config.requested_execution_json
            if selection.deployment == 'isolated_worker':
                from ..runtime.sessions.provenance import preflight_interpreter_before_source
                import json
                preflight_interpreter_before_source(selection, requested=json.loads(requested_json), task_uid=self.uid)
            candidate_value = candidate_binding.build_seeded(
                switch_candidate.config.physics_provider,
                switch_candidate.config.environment.runtime.backend, seed, self.horizon)
        else:
            seed, options, mixed_reset_plan, mixed_reset_sample = prepare_selected_reset(
                self.binding, seed=seed, seed_unset=_RESET_SEED_UNSET, options=options,
                mixed=self._mixed_control_candidate, position=getattr(self, 'position_profile', False),
                has_session=self.session is not None, previous_sample=getattr(self, 'sample', None),
                artifact=self.artifact, value=self.value,
            )
            selection, requested_json = self._selected_execution_context()
        deployment_receipt = None
        if selection is not None:
            import json
            from ..runtime.sessions.provenance import (
                DeploymentPreflightError, describe_execution_selection, preflight_selected_deployment,
            )
            requested = None if requested_json is None else json.loads(requested_json)
            if getattr(getattr(self, 'resolved_public_config', None), 'gravity_compensation', False):
                requested = dict(requested or {})
                requested['controller'] = {'gravity_compensation': True}
            preflight_value = candidate_value if switching else self.value
            facts = dict(requested=requested, task_uid=self.uid, artifact=preflight_value['artifact'],
                         source=preflight_value['source'],
                         controller=preflight_value.get('controller', preflight_value.get('leaf_plan')), seed=seed)
            if selection.deployment == 'isolated_worker':
                if (self._mixed_control_candidate or self.leaf_position_profile
                        or self.dual_entity_position or self._diagnostic_profile is not None
                        or self._native_feedback_profile is not None):
                    receipt = describe_execution_selection(selection, **facts)
                    receipt['phase'] = 'static_preflight'
                    raise DeploymentPreflightError('worker_profile_not_implemented', receipt)
            try:
                deployment_receipt = preflight_selected_deployment(
                    selection, **facts, binding=candidate_binding, value=preflight_value)
            except BaseException as error:
                if switching:
                    receipt = getattr(candidate_value.get('source'), 'execution_source_receipt', None)
                    if receipt is not None:
                        try:
                            receipt.close()
                        except BaseException as cleanup_error:
                            error.add_note(f'candidate source cleanup also failed: {cleanup_error!r}')
                raise
        previous_episode_end = self._position_episode_end
        if (getattr(self, 'position_profile', False) and self.session is not None
                and self._published_position_typed_state is not None
                and previous_episode_end is None):
            try:
                previous_episode_end = self.stop('reset')
            except BaseException as error:
                if switching:
                    receipt = getattr(candidate_value.get('source'), 'execution_source_receipt', None)
                    if receipt is not None:
                        try:
                            receipt.close()
                        except BaseException as cleanup_error:
                            error.add_note(f'candidate source cleanup also failed: {cleanup_error!r}')
                raise
        if switching or getattr(self, 'position_profile', False):
            self._position_episode_end = None
            self._position_controller_switch_fault_receipt = None
            self._pending_position_switch = None
            self._published_position_state = None
            self._published_position_typed_state = None
            self._published_position_obs = None
            self._published_position_info = None
            self._published_position_evaluation = None
            self.last_position_transition = None
        if self._mixed_control_candidate:
            # Publish a candidate reset plan only after the replacement begins.
            self._mixed_reset_plan = mixed_reset_plan
        previous_session, self.session = self.session, None
        previous_value = self.value
        previous_session_close_attempted = False
        reset_effects = {'schema_version': 'selected-reset-failure-effects-v1',
                         'previous_session_present': previous_session is not None,
                         'previous_session_close_attempted': False,
                         'previous_session_close_completed': False,
                         'replacement_materialization_attempted': False,
                         'reset_write_attempted': False, 'reset_write_status': 'not_attempted',
                         'replacement_session_close_attempted': False,
                         'replacement_session_close_completed': False}
        failure_phase = 'camera_reset_close'

        def prepare():
            nonlocal seed, previous_session_close_attempted, failure_phase
            if switching:
                self._reset_failure_receipt = None
                self._switch_rng_state = switch_candidate.rng_state
                self._switch_task_seed = switch_candidate.task_seed
                self._switch_provider_seed = switch_candidate.provider_seed
                self._switch_generation = getattr(self, '_switch_generation', 0) + 1
                if (not hasattr(self, '_switch_topology_generation')
                        or self.provider != switch_candidate.config.physics_provider):
                    self._switch_topology_generation = getattr(self, '_switch_topology_generation', 0) + 1
            self._deployment_receipt = deployment_receipt
            self._close_camera_consumer()
            failure_phase = 'reset_close'
            if previous_session is not None:
                previous_session_close_attempted = True
                reset_effects['previous_session_close_attempted'] = True
                previous_session.close()
                reset_effects['previous_session_close_completed'] = True
                if self._mixed_control_candidate:
                    self._mixed_close_receipt = previous_session.close_receipt
            previous_receipt = getattr(previous_value.get('source'), 'execution_source_receipt', None)
            failure_phase = 'selected_reconstruction'
            # A new construction resets all controller/arm-hold/servo owner memory.
            if switching:
                self.binding = candidate_binding
                self.resolved_public_config = switch_candidate.config
                self.provider = switch_candidate.config.physics_provider
                self.backend = switch_candidate.config.environment.runtime.backend
                self.value = candidate_value
                self.artifact = candidate_value['artifact']
                self._declared_execution_spec_v1 = candidate_value.get('execution_spec_v1')
            elif self._mixed_control_candidate and self._mixed_initial_value_pending:
                self._mixed_initial_value_pending = False
            elif self._mixed_control_candidate:
                self.value = self.binding.build_mixed_control_profile(self.provider, self.backend)
            elif self._native_feedback_profile is not None:
                self.value = self.binding.build_native_feedback_profile(
                    self.provider, self.backend, self._native_feedback_request, False,
                )
            else:
                if external_solution is not None:
                    self.value = self.binding.build_external(self.provider)
                elif self.binding.build_seeded is not None:
                    self.value = self.binding.build_seeded(
                        self.provider, self.backend, seed, self.horizon,
                    )
                else:
                    self.value = self.binding.build_for_provider(self.provider)
            replacement_receipt = getattr(
                self.value.get('source'), 'execution_source_receipt', None,
            )
            if deployment_receipt is not None:
                from ..runtime.sessions.transport import source_binding_facts
                if (getattr(self.value.get('source'), 'source_closure_digest', None)
                        != deployment_receipt['identity_facts']['source_closure']
                        or source_binding_facts(self.value['source'])
                        != deployment_receipt['identity_facts']['source_bindings']):
                    raise ValueError('selected source closure or bindings changed after preflight')
            if previous_receipt is not None and previous_receipt is not replacement_receipt:
                previous_receipt.close()
            if self._mixed_control_candidate or self._native_feedback_profile is not None:
                if self.value['artifact'] != self.artifact:
                    raise ValueError('selected Artifact changed between construction and reset')
            else:
                select_runtime_input = getattr(self.binding, 'reset_runtime_input', None)
                runtime_input = select_runtime_input(self.value) if select_runtime_input else None
                self.artifact = _artifact_for_reset(self.artifact, self.value, runtime_input)
            if external_solution is not None:
                self.binding.validate_external_solution(self.value, external_solution)
            failure_phase = 'reset_seed'
            if self._mixed_control_candidate:
                seed = self.binding.reset_seed(seed)
            self.solution = self.value.get('solution')
            if self._native_feedback_profile is not None and self.solution is not None:
                self.binding.validate_external_solution(self.value, self.solution)
            self._external_solution_owner = external_solution
            self._bind_selected_controller(self.value)
            if deployment_receipt is not None:
                from ..runtime.sessions.api import assess_selected_request
                from ..runtime.sessions.provenance import describe_execution_selection
                rebuilt = describe_execution_selection(
                    selection, requested=requested, task_uid=self.uid, artifact=self.artifact,
                    source=self.value['source'],
                    controller=self.value.get('controller', self.value.get('leaf_plan')), seed=seed)
                if (rebuilt['identity_facts']['artifact_identity'] != deployment_receipt['identity_facts']['artifact_identity']
                        or rebuilt['identity_facts']['controller_identities'] != deployment_receipt['identity_facts']['controller_identities']):
                    raise ValueError('selected Artifact or Controller changed after preflight')
                reassessed = assess_selected_request(
                    selection=selection, artifact=self.artifact, source=self.value['source'],
                    value=self.value, binding=self.binding,
                    dependency_status=deployment_receipt['dependency']['status'],
                    request_identity=deployment_receipt['request_identity'])
                plan = self.value.get('controller_binding_plan') or self.value.get('leaf_plan')
                if (reassessed.to_mapping()['rows'] != deployment_receipt['identity_facts']['assessment_rows']
                        or (None if plan is None else getattr(plan, 'identity_hash', None) or plan.identity_sha256)
                        != deployment_receipt['identity_facts']['control_binding_plan']):
                    raise ValueError('selected declarations or Controller plan changed after preflight')
            self.dual_entity_position = len(self.position_profiles) == 2
            failure_phase = 'reset_sample'
            if self.position_profile:
                reset_plan = self.value.get('reset_plan')
                if reset_plan is None:
                    raise ValueError('PositionServoV1 selected route requires an EpisodeResetPlanV1')
                self.sample = reset_plan.reset_sample
            elif self._mixed_control_candidate:
                self.sample = mixed_reset_sample
                self._selected_episode_id = uuid4().hex
            else:
                self.sample = self.binding.reset_sample(self.artifact, seed)
                self._selected_episode_id = uuid4().hex
            from .reference_binding import resolve_reset_execution
            self.execution = resolve_reset_execution(
                self.binding, self.value, self._declared_execution_spec_v1,
                seed=seed, provider=self.provider, backend=self.backend,
            )
            if switching:
                from dataclasses import replace
                self.execution = replace(self.execution, provider_seed=switch_candidate.provider_seed)

        def materialize_runtime():
            nonlocal failure_phase
            failure_phase = 'session_materialization'
            if switching:
                reset_effects['replacement_materialization_attempted'] = True

            def start_worker():
                from ..runtime.sessions.transport import (
                    request_identity, source_execution_facts, start_selected_worker,
                )
                from ..utils._paths import GEOCHORA_ROOT, GEOPHYS_PROVIDER_ROOT
                replay = self._recorded_execution_configuration()
                config = {key: value for key, value in replay.items() if key != 'env_id'}
                # The worker uses the original adapter in its own process; its
                # deployment itself is already represented by this request.
                for name in ('host', 'engine', 'solver_family', 'solver_algorithm', 'coupler',
                             'batch_layout', 'deployment', 'interpreter', 'native_dt'):
                    config['execution'].pop(name, None)
                payload = {
                    'uid': self.uid, 'config': config, 'seed': seed,
                    'selection': selection.to_mapping(), 'execution': self.execution.to_mapping(),
                    'facts': source_execution_facts(self.artifact, self.execution,
                                                    self.value['source'], self.value['controller']),
                    'preflight_request_identity': deployment_receipt['request_identity'],
                    'preflight_identity_facts': deployment_receipt['identity_facts'],
                    'core_root': str(GEOCHORA_ROOT), 'geophys_src': str(GEOPHYS_PROVIDER_ROOT / 'src'),
                    'environment': deployment_receipt['environment'],
                }
                # SDK App startup includes loading Kit and PhysX.  Keep the
                # worker deadline finite while allowing that selected route's
                # cold start to finish inside the enclosing run budget.
                session = start_selected_worker(selection.interpreter, payload,
                    timeout=300.0 if selection.physics_provider == 'isaacsim' else 30.0)
                deployment_receipt['worker_request_identity'] = request_identity(payload)
                return session
            if self.position_profile:
                from ..runtime.sessions.control import prepare_position_control_materialization
                self.position_scene = self.value['source'].scene_definition
                select_binding = self.binding.position_control_binding
                (self.position_plan, self.position_joint_bindings,
                 self.position_frame_bindings, position_binding) = prepare_position_control_materialization(
                    source=self.value['source'], artifact=self.artifact,
                    profiles=self.position_profiles, leaf_position=self.leaf_position_profile,
                    plan=self.value.get('controller_binding_plan'),
                    select_binding=select_binding, value=self.value,
                )
                if selection is not None and selection.deployment == 'isolated_worker':
                    self.session = start_worker()
                elif self.leaf_position_profile:
                    self.session = materialize_control(
                        self.artifact, self.execution, source=self.value['source'],
                        binding=position_binding,
                        leaf_plan=self.leaf_plan,
                    )
                else:
                    self.session = materialize_control(
                        self.artifact, self.execution, source=self.value['source'],
                        binding=position_binding,
                        controller_binding_plan=self.position_plan,
                        controller_profile=self.position_profiles,
                        session_admission_input=self.value.get('session_admission_input'),
                    )
                # Preserve what was actually materialized; the task binding can
                # later be replaced independently of this live session.
                self._materialized_position_control_binding = position_binding
                self._materialized_position_control_selector = select_binding
                if self.binding.physical_control_profile is not None:
                    profile = self.binding.physical_control_profile(self)
                    bind_physical = getattr(self.session, 'bind_physical_control', None)
                    if not callable(bind_physical):
                        raise StageUnavailableError('RuntimeSession does not expose a physical-control build port')
                    bind_physical(profile)
            elif self._mixed_control_candidate:
                self.position_profile = False
                self.session = materialize(
                    self.artifact, self.execution, source=self.value['source'],
                )
                self.session.bind_mixed_controller(self.controller.identity)
                if self.binding.pre_reset_session_validator is None:
                    raise ValueError('mixed-control candidate requires compiled-layout validation before reset')
                self._compiled_layout_pre_reset = self.binding.pre_reset_session_validator(
                    self.session, self.value,
                )
            else:
                self.position_profile = False
                if type(self.binding.scalar_control_binding) is not ControlBinding:
                    raise TypeError('selected scalar control requires its declared ControlBinding')
                if selection is not None and selection.deployment == 'isolated_worker':
                    self.session = start_worker()
                    return
                self.session = materialize_control(self.artifact, self.execution,
                    source=self.value['source'], binding=self.binding.scalar_control_binding,
                    diagnostic_profile=(self._diagnostic_profile
                                        if self.backend == 'cuda' else None),
                    native_feedback_profile=self._native_feedback_profile,
                    selected_controller=(self.controller
                                         if self._native_feedback_profile is not None else None),
                    native_feedback_gripper_control_hz=(
                        self.value['resolved_configuration'].get('gripper_control_hz')
                        if self._native_feedback_profile is not None else None
                    ))
            if getattr(getattr(self, 'resolved_public_config', None), 'gravity_compensation', False):
                if self.uid not in ('pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1'):
                    raise ValueError('gravity compensation is limited to the selected Panda tasks')
                self.session.configure_gravity_compensation()

        def reset_runtime():
            nonlocal failure_phase
            if deployment_receipt is not None:
                from ..runtime.sessions.provenance import bind_selected_build_checks
                failure_phase = 'build_layout_receipt'
                bind_selected_build_checks(deployment_receipt, self.session.build_layout_facts,
                    materialization_id=self.session.provider_materialization_id)
            failure_phase = 'runtime_reset'
            if switching:
                reset_effects['reset_write_attempted'] = True
                reset_effects['reset_write_status'] = 'unknown'
            if self.position_profile:
                reset_plan = self.value.get('reset_plan')
                self.realized = self.session.reset_plan(reset_plan)
            elif self._mixed_control_candidate and self._mixed_reset_plan is not None:
                self.realized = self.session.reset_plan(self._mixed_reset_plan)
            else:
                self.realized = self.session.reset(self.sample)
            if switching:
                reset_effects['reset_write_status'] = 'completed'
            self._compiled_layout_post_reset = None
            if self.binding.post_reset_session_validator is not None:
                self._compiled_layout_post_reset = self.binding.post_reset_session_validator(
                    self.session, self.value,
                )
            if self.binding.runtime_episode_identity:
                # Native task samples and the published Solution boundary
                # must share the RuntimeSession's actual episode identity.
                self._selected_episode_id = self.session.episode_id

        def read_state():
            nonlocal failure_phase
            failure_phase = 'snapshot_readback'
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
            elif self.mixed_control_profile:
                self.feedback = None
                self.controller.reset(self.state)
            else:
                failure_phase = 'controller_feedback'
                self.feedback = self.session.control_feedback(self.state)
                self.controller.reset(self.state, self.feedback)
            return self.state

        def observe(_state):
            nonlocal failure_phase
            failure_phase = 'reset_observation'
            self.obs, self.info, self.evaluation = self.observation(self.state)
            self.info['provider'] = self.provider
            if switching:
                self.info['reset_switch_v1'] = {
                    'schema_version': 'pickcube-reset-switch-receipt-v1',
                    'task_seed': switch_candidate.task_seed,
                    'provider_seed': self.execution.provider_seed,
                    'task_seed_algorithm': switch_candidate.seed_algorithm,
                    'provider_seed_algorithm': 'pickcube-provider-seed-task-identity-v1',
                    'provider': self.provider,
                    'configuration_generation': self._switch_generation,
                    'topology_generation': self._switch_topology_generation,
                }
            if self.mixed_control_profile:
                realization = self.value['reset_realizations'].get(self.sample.sample_id)
                if not isinstance(realization, dict):
                    raise ValueError('mixed-control reset sample has no matching source-derived realization receipt')
                reset_readback = self.session.reset_readback_v1
                reset_readback_mapping = (
                    reset_readback.to_mapping()
                    if callable(getattr(reset_readback, 'to_mapping', None))
                    else dict(reset_readback)
                )
                self._mixed_reset_context = {
                    'reset_sample_v1': self.sample.to_mapping(),
                    'reset_realization_v1': realization,
                    'reset_readback_v1': reset_readback_mapping,
                }
                self.info.update({
                    **self._mixed_reset_context,
                    'compiled_model_layout_v1': self.session.compiled_layout_receipt,
                    'pre_reset_compiled_validation_v1': self._compiled_layout_pre_reset,
                })
                if self._compiled_layout_post_reset is not None:
                    self.info['post_reset_compiled_validation_v1'] = self._compiled_layout_post_reset
                compiled_model_options = getattr(
                    self.session, 'compiled_model_options_receipt_v1', None,
                )
                if compiled_model_options is not None:
                    self.info['compiled_model_options_v1'] = compiled_model_options
                if self._mixed_reset_plan is not None:
                    plan_receipt = {
                        'reset_plan_v1': self._mixed_reset_plan.to_mapping(),
                        'reset_plan_identity_sha256': self._mixed_reset_plan.identity_hash,
                        'reset_plan_evidence_v1': self.session.reset_plan_evidence,
                    }
                    self._mixed_reset_context.update(plan_receipt)
                    self.info.update(plan_receipt)
                # Freeze task-owned metadata at the reset boundary. Later
                # observations replace ``info``; record metadata must retain
                # the source-derived realization/readback that opened this
                # episode rather than re-reading a transition-only mapping.
                self._mixed_record_metadata = dict(
                    self.binding.mixed_record_metadata(self),
                )
            if not self.position_profile and not self.mixed_control_profile:
                self._publish_execution_info(self.info)
            self._last_position_terminated = False
            self._last_position_truncated = False
            self._last_position_request = None
            if self.position_profile:
                from ..recorders.position_metadata import position_record_reset_info
                self._position_reset_info = position_record_reset_info(self)
                self.info.update(self._position_reset_info)
                self._publish_task_position_execution_info(self.info)
                if previous_episode_end is not None:
                    self.info['previous_episode_end_v1'] = previous_episode_end.to_mapping()
            if self.state.control_step != 0 or self.state.simulation_time != 0:
                raise ValueError('reference reset must not advance physics')
            reset_solution = external_solution if external_solution is not None else self.solution
            if reset_solution is not None:
                failure_phase = 'solution_reset'
                reset_solution.reset(self.obs, self.info, self.metadata,
                                    **self.binding.reset_expert_kwargs(self))
            return self.obs

        def publish(_state, _observation):
            nonlocal failure_phase
            failure_phase = 'arm_schedule_reset'
            if self.mixed_control_profile:
                self.arm_schedule = None
            elif all(callable(getattr(self.controller, name, None))
                   for name in ('begin', 'target', 'applied')):
                # The Controller itself owns acknowledged arm hold/ramp memory.
                self.arm_schedule = self.controller
            else:
                self.arm_schedule = (self.binding.schedule_factory(self)
                                     if self.binding.schedule_factory is not None else None)
            self._active_native_interval_receipt = None
            self._episode_mode = None
            self._position_episode_end = None
            self._mixed_episode_end = None
            self._published_position_state = self.state
            self._published_position_typed_state = getattr(self, 'typed_state', None)
            self._published_position_obs = self.obs
            self._published_position_info = dict(self.info)
            self._published_position_evaluation = self.evaluation
            self.recorder = None
            if external_solution is not None:
                # The caller's instance is the only active mutable Solution
                # owner for this episode; the task value has no active copy.
                self.solution = None
            return self.obs, self.info

        def on_failure(_phase, error):
            nonlocal previous_session_close_attempted
            self._external_solution_owner = None
            try:
                self._close_camera_consumer()
            except BaseException as cleanup_error:
                add_note = getattr(error, 'add_note', None)
                if callable(add_note):
                    add_note(f'selected reset camera cleanup also failed: {cleanup_error!r}')
            failed_session, self.session = self.session, None
            if failed_session is not None:
                if switching:
                    reset_effects['replacement_session_close_attempted'] = True
                try:
                    failed_session.close()
                    if switching:
                        reset_effects['replacement_session_close_completed'] = True
                except BaseException as cleanup_error:
                    add_note = getattr(error, 'add_note', None)
                    if callable(add_note):
                        add_note(f'selected reset cleanup also failed: {cleanup_error!r}')
            if previous_session is not None and not previous_session_close_attempted:
                previous_session_close_attempted = True
                if switching:
                    reset_effects['previous_session_close_attempted'] = True
                try:
                    previous_session.close()
                    if switching:
                        reset_effects['previous_session_close_completed'] = True
                except BaseException as cleanup_error:
                    add_note = getattr(error, 'add_note', None)
                    if callable(add_note):
                        add_note(f'selected prior-session reset cleanup also failed: {cleanup_error!r}')
            if switching:
                self._reset_failure_receipt = {**reset_effects, 'failure_phase': failure_phase}
                error.reset_failure_receipt = self.reset_failure_receipt
                # A candidate can own a source lease even if closing the old
                # session fails before it is installed on this environment.
                seen = set()
                for value in (candidate_value, previous_value):
                    receipt = getattr(value.get('source'), 'execution_source_receipt', None)
                    if receipt is None or id(receipt) in seen:
                        continue
                    seen.add(id(receipt))
                    try:
                        receipt.close()
                    except BaseException as cleanup_error:
                        error.add_note(f'selected reset source cleanup also failed: {cleanup_error!r}')
            self._latch_fault(failure_phase, error)

        return dict(
            prepare=prepare, materialize=materialize_runtime, reset_runtime=reset_runtime,
            read_state=read_state, observe=observe, publish=publish, on_failure=on_failure,
        )

    def expert_execution_info(self):
        """Return the required, validated R1 readiness at the current boundary."""
        if getattr(self, 'position_profile', False):
            binding = getattr(self, 'binding', None)
            project = getattr(binding, 'position_execution_info', None)
            result = project(self) if project is not None else None
            if result is not None:
                return result
        if (getattr(self, 'state', None) is None or getattr(self, 'feedback', None) is None
                or getattr(self, 'position_profile', False)):
            raise StageUnavailableError('R1 execution readiness is unavailable on this selected route')
        result = ExpertExecutionInfo(
            'expert-execution-info-v1', self.state.control_step,
            self.state.simulation_time, self.controller.readiness(self.state, self.feedback),
        )
        result.validate()
        return result

    def _publish_task_position_execution_info(self, info):
        binding = getattr(self, 'binding', None)
        project = getattr(binding, 'position_execution_info', None)
        if project is not None:
            value = project(self)
            if value is not None:
                info[binding.position_execution_info_key] = value.to_mapping()

    # Kept for existing in-module callers while public callers use the named
    # expert_execution_info() contract.
    def _execution_info(self):
        return self.expert_execution_info()

    def _source_xml_sha256(self):
        xml = self.value['source'].scene_source.xml
        cached = getattr(self, '_boundary_xml_snapshot', None)
        if cached is None or cached[0] != xml:
            cached = (xml, hashlib.sha256(xml.encode()).hexdigest())
            self._boundary_xml_snapshot = cached
        return cached[1]

    def _execution_boundary(self, execution_info=None):
        execution_info = self.expert_execution_info() if execution_info is None else execution_info
        source = self.value['source']
        source_id = source.scene_source.source_id
        source_xml_sha256 = self._source_xml_sha256()
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
        def read_evaluation_boundary():
            current_info = ExpertExecutionInfo.from_mapping(info['expert_execution_info_v1'])
            return current_info.control_step, self._execution_boundary(current_info)

        info['control_application_v1'] = selected_control_application_receipt(
            request=request, canonical=canonical, target=target, applied=applied,
            request_boundary=request_boundary, read_evaluation_boundary=read_evaluation_boundary,
            artifact=self.artifact,
            controller_identity=self.controller.identity, provider=self.provider,
            source_id=self.value['source'].scene_source.source_id,
            reset_sample_id=self.sample.sample_id,
        )

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
        if self.mixed_control_profile:
            from ..observations.selected_reference import build_selected_observation
            observation, info, evaluation = build_selected_observation(self, state)
        else:
            observation, info, evaluation = self.binding.observation_projection(self, state)
        if self._selected_execution_context()[0] is not None:
            info = dict(info)
            info['execution_configuration_v1'] = self.get_execution_receipt()
        return observation, info, evaluation

    def _close_camera_consumer(self):
        consumer, self._camera_consumer = self._camera_consumer, None
        if consumer is not None:
            consumer.close()

    def step(self, action):
        component_lifecycle = None
        if self._has_component_assembly():
            self._episode_execution_state().require_open("environment is closed")
            component_lifecycle = self._require_task_lifecycle()
            self._last_camera_metadata = {}
            operations = component_lifecycle.prepare_step(action)
        else:
            operations = self._prepare_selected_step(action)
        result = self._episode_execution_state().execute_interval(**operations)
        if component_lifecycle is not None:
            return self._format_component_step(component_lifecycle, result)
        return result

    def _prepare_selected_step(self, action):
        self._episode_execution_state().require_step(
            closed_message='environment is closed',
            fault_prefix='selected execution is faulted; reset() is required',
        )
        from ..planners.contracts import ExpertAction, validate_caller_solution_action
        if self.binding.external_solution_actions and type(action) is ExpertAction:
            if self._episode_mode in {'expert', 'external_solution'}:
                raise RuntimeError('cannot mix caller actions with selected Solution execution')
            if self.solution is not None or self._external_solution_owner is not None:
                raise RuntimeError('caller actions require reset without an Env-owned Solution')
            if self._stopped or self.session is None:
                raise RuntimeError('reset required or episode already stopped')
            if getattr(self, 'position_profile', False):
                if self.binding.position_execution_info is None or len(self.position_profiles) != 1:
                    raise StageUnavailableError('caller-driven Solution actions are unavailable on this Position profile')
                validate_caller_solution_action(
                    action, boundary=lambda: self.info.get('state_boundary_identity'),
                    state_boundary=lambda: self.typed_state.view.boundary.to_mapping(),
                    solution_identity=self.value.get('solution_identity'),
                    control_request_mode='position',
                )
                from ..runtime.sessions.control import single_position_action_request
                request = single_position_action_request(
                    action.action, scene=self.position_scene, plan=self.position_plan,
                    profile=self.position_profiles[0],
                )
                return self._prepare_position_profile(request, proposal=action, caller_driven=True)
            self._require_published_execution_info()
            validate_caller_solution_action(
                action, boundary=self.info['expert_execution_boundary_v1'],
                solution_identity=self.value.get('solution_identity'),
                control_request_mode=('required' if self.binding.control_request_required
                                      else 'forbidden'),
            )
            return self._prepare_reference_step(action.action, proposal=action, caller_driven=True)
        if not self.binding.external_actions:
            raise RuntimeError(self.binding.external_action_error)
        if self._episode_mode in {'expert', 'external_solution'}:
            raise RuntimeError('cannot mix external actions with selected Solution execution')
        if self.binding.physical_control_profile is not None:
            return self._prepare_physical_control(action)
        if getattr(self, 'mixed_control_profile', False):
            return self._prepare_mixed_control(action)
        from ..controllers.canonical.contracts import StructuredActionRequestV1
        if getattr(self, 'position_profile', False):
            if self._stopped or self.session is None:
                raise RuntimeError('reset required or episode already stopped')
            if self.state.control_step >= self.horizon:
                self._stopped = True
                raise RuntimeError('selected PositionServoV1 horizon is exhausted')
            if getattr(self, 'leaf_position_profile', False):
                if self.fixed_attachment_leaf_position_profile:
                    from ..controllers.canonical.leaf_actions import AttachedLeafActionSetV1
                    action_set_type = AttachedLeafActionSetV1
                else:
                    from ..controllers.canonical.leaf_actions import LeafPositionActionSetV1
                    action_set_type = LeafPositionActionSetV1
                if type(action) is not action_set_type:
                    raise TypeError('leaf Position route requires its typed Arm and Hand action-set')
                action.structured_request(self.position_scene, self.leaf_plan)
                return self._prepare_leaf_position(action)
            if (not isinstance(action, StructuredActionRequestV1)
                    and self.value.get('f06_pickcube_isaac_input') is not None
                    and len(self.position_profiles) == 1):
                from ..runtime.sessions.control import single_position_action_request
                action = single_position_action_request(
                    action, scene=self.position_scene, plan=self.position_plan,
                    profile=self.position_profiles[0],
                )
            if not isinstance(action, StructuredActionRequestV1):
                raise TypeError('PositionServoV1 requires a StructuredActionRequestV1')
            from ..runtime.sessions.control import prepare_structured_action
            # Reject bad action and plan identities before changing episode mode,
            # Controller memory, Recorder state, or the Provider.
            prepare_structured_action(self.position_plan, action)
            return self._prepare_position_profile(action)
        if isinstance(action, StructuredActionRequestV1):
            raise TypeError('structured ControllerGroup actions require PositionServoV1')
        self._episode_mode = 'external'
        return self._prepare_reference_step(action)

    def _prepare_physical_control(self, action):
        """Prepare one named physical interval through the selected session."""
        from ..artifacts.state import CanonicalStatePublicationV1, CanonicalStatePublicationV2
        from ..controllers.canonical.physical_commands import PhysicalCommandContextV1, PhysicalControlReceiptV1
        from ..runtime.sessions.physical_control import PhysicalControlExecutionV1, prepare_physical_command_batch

        if self._stopped or self.session is None:
            raise RuntimeError('reset required or episode already stopped')
        if self.state.control_step >= self.horizon:
            raise RuntimeError('selected physical-control horizon is exhausted')
        if self.recorder is not None and getattr(self.recorder, 'active', False):
            raise StageUnavailableError('physical-control recording is not yet admitted')
        profile = self.binding.physical_control_profile(self)
        if type(profile) is not PhysicalControlExecutionV1:
            raise TypeError('selected physical route requires an admitted physical execution profile')
        plan = profile.compiled.binding
        source = self.value['source']
        if (self.artifact.identity_hash != plan.artifact_sha256
                or getattr(source, 'source_id', None) != plan.source_id
                or getattr(source, 'source_closure_digest', None) != plan.source_closure_sha256):
            raise ValueError('selected physical execution source or Artifact differs from binding')
        assess = getattr(self.session, 'assess_physical_control', None)
        write = getattr(self.session, 'apply_physical_command_batch', None)
        if not callable(assess) or not callable(write):
            raise StageUnavailableError('RuntimeSession does not expose an admitted physical-control port')
        if getattr(self.session, 'physical_control_generation', None) != profile.generation:
            raise ValueError('physical-control session generation differs from profile')
        publication = self.session.snapshot_v2(scene=profile.scene,
            joint_bindings=profile.joint_bindings, frame_bindings=profile.frame_bindings,
            requirements=profile.requirements)
        if type(publication) is not CanonicalStatePublicationV2:
            raise TypeError('physical Controller needs a typed state publication')
        if not publication.lifetime.may_be_retained:
            raise ValueError('physical Controller requires an owned state snapshot')
        view = publication.view
        if view.boundary != self.session.state_boundary_identity():
            raise ValueError('physical Controller state is stale')
        view.validate_against_scene(profile.scene)
        view.validate_requirements(profile.requirements)
        clock_tolerance = _boundary_interval_clock_tolerance(
            self.state.simulation_time, view.sample_clock.simulation_time_s,
            self.artifact.timebase.control_dt, self.artifact.timebase.control_dt, 1)
        if (self.state.control_step != view.boundary.control_step
                or abs(float(self.state.simulation_time) - view.sample_clock.simulation_time_s) > clock_tolerance):
            raise ValueError('selected and typed state clocks differ')
        context = PhysicalCommandContextV1('physical-command-context-v1', plan.source_id,
            plan.source_closure_sha256, plan.artifact_sha256, view.boundary, view.sample_clock,
            0, profile.generation, self.artifact.timebase.control_dt, self.artifact.timebase.control_dt)
        if getattr(self, '_last_physical_submission', None) == context.identity_hash:
            raise ValueError('physical command interval was already submitted')
        assessment = assess(plan)
        if getattr(assessment, 'phase', None) not in {'native_build', 'runtime'}:
            raise ValueError('physical session write requires native-build or runtime capability assessment')
        if len(profile.controllers) == 1 and not isinstance(action, Mapping):
            actions = {profile.controllers[0].identity: action}
        elif isinstance(action, Mapping):
            actions = dict(action)
        else:
            raise TypeError('multiple physical Controllers require identity-keyed actions')
        if set(actions) != {controller.identity for controller in profile.controllers}:
            raise ValueError('physical action must cover every bound Controller exactly once')
        from ..controllers.canonical.physical_commands import PhysicalCommandBatchV1
        parts = tuple(controller.compute(actions[controller.identity], view, context)
                      for controller in profile.controllers)
        if any(type(part) is not PhysicalCommandBatchV1 or part.context != context for part in parts):
            raise ValueError('physical Controller returned a foreign or untyped batch')
        for controller, part in zip(profile.controllers, parts, strict=True):
            if any(item.contribution.owner_id != controller.writer_id
                   for item in (*part.joint_efforts, *part.body_wrenches, *part.extensions)):
                raise ValueError('physical Controller contribution owner differs from binding')
        batch = PhysicalCommandBatchV1('physical-command-batch-v1', context,
            tuple(item for part in parts for item in part.joint_efforts),
            tuple(item for part in parts for item in part.body_wrenches),
            tuple(item for part in parts for item in part.extensions))
        submitted = PhysicalControlReceiptV1('physical-control-receipt-v1', context,
            batch.identity_hash, 'submitted', tuple(item.contribution.contribution_id
            for item in (*batch.joint_efforts, *batch.body_wrenches, *batch.extensions)),
            'core-selected', 'per-channel')
        buffer_policy = None
        if any(item.contribution.persistence == 'hold_reapply'
               for item in (*batch.joint_efforts, *batch.body_wrenches)):
            get_buffer_policy = getattr(self.session, 'physical_buffer_policy', None)
            if not callable(get_buffer_policy):
                raise StageUnavailableError('RuntimeSession has no held-load buffer policy')
            buffer_policy = get_buffer_policy(plan)
        joint_receipt = None
        if batch.joint_efforts:
            get_joint_receipt = getattr(self.session, 'physical_joint_build_receipt', None)
            if not callable(get_joint_receipt):
                raise StageUnavailableError('RuntimeSession has no verified physical joint mapping')
            joint_receipt = get_joint_receipt(plan)
        body_receipt = None
        if batch.body_wrenches:
            get_body_receipt = getattr(self.session, 'physical_body_build_receipt', None)
            if not callable(get_body_receipt):
                raise StageUnavailableError('RuntimeSession has no verified physical body mapping')
            body_receipt = get_body_receipt(plan)
        if any(getattr(receipt, 'provenance', None) != 'native_build'
               for receipt in (joint_receipt, body_receipt) if receipt is not None):
            raise ValueError('synthetic mapping cannot authorize a session write')
        resolved = prepare_physical_command_batch(profile.compiled, batch, expected_context=context,
                                                   assessment=assessment, state=view,
                                                   body_build_receipt=body_receipt,
                                                   joint_build_receipt=joint_receipt,
                                                   buffer_policy=buffer_policy)
        before = self.state
        attempted = False
        completed = False
        ack = None

        def apply_control():
            nonlocal attempted, ack
            # Mark before the one session write; a partial failure cannot be replayed.
            self._last_physical_submission = context.identity_hash
            attempted = True
            ack = write(resolved)
            if (type(ack) is not PhysicalControlReceiptV1 or ack.stage != 'native_write_ack'
                    or ack.context != context or ack.batch_sha256 != batch.identity_hash
                    or ack.contribution_ids != resolved.accepted_receipt.contribution_ids):
                raise ValueError('physical RuntimeSession returned an invalid write acknowledgement')
            return ack

        def advance(_ack):
            nonlocal completed
            self.state = self.session.step()
            completed = True
            if getattr(self, 'position_profile', False):
                # The existing selected observation consumes the Position
                # publication. Refresh it at the new boundary instead of
                # projecting the pre-command snapshot after the interval.
                publication_after = self.session.snapshot_v1(
                    scene=self.position_scene, joint_bindings=self.position_joint_bindings,
                    frame_bindings=self.position_frame_bindings,
                    requirements=self._position_requirements())
                if (type(publication_after) is not CanonicalStatePublicationV1
                        or not publication_after.lifetime.may_be_retained
                        or publication_after.view.boundary != self.session.state_boundary_identity()
                        or publication_after.view.boundary.control_step != self.state.control_step
                        or abs(publication_after.view.sample_clock.simulation_time_s
                               - float(self.state.simulation_time)) > clock_tolerance):
                    raise ValueError('physical control post-step publication is stale or foreign')
                self.typed_state = publication_after

        def evaluate(_state):
            self.obs, self.info, self.evaluation = self.observation(self.state)
            self.info = dict(self.info)
            self.info['physical_control_v1'] = {
                'submitted_batch': batch.to_mapping(),
                'submitted': submitted.to_mapping(),
                'accepted': resolved.accepted_receipt.to_mapping(),
                'native_write_ack': ack.to_mapping(),
            }
            return self.evaluation

        def publish(_control, _state, _evaluation, _observation):
            terminated, truncated = self._episode_execution_state().step_outcome(
                task_terminated=bool(self.evaluation.failure), task_truncated=False,
                control_step=self.state.control_step, horizon=self.horizon)
            self._episode_mode = 'external'
            self._episode_execution_state().finish_step(terminated=terminated, truncated=truncated)
            if getattr(self, 'position_profile', False):
                self._published_position_state = self.state
                self._published_position_typed_state = self.typed_state
                self._published_position_obs = self.obs
                self._published_position_info = dict(self.info)
                self._published_position_evaluation = self.evaluation
            return self.obs, float(self.evaluation.reward), terminated, truncated, self.info

        def on_failure(phase, error):
            abort = getattr(self.session, 'abort_physical_control', None)
            if attempted and callable(abort):
                try:
                    abort()
                except BaseException as cleanup_error:
                    error.add_note('physical batch cleanup also failed: '
                                   f'{type(cleanup_error).__name__}: {cleanup_error}')
            self._latch_fault(phase, error, before_state=before, after_state=None,
                interval_attempted=attempted, interval_completed=completed,
                native_substeps_expected=self.artifact.timebase.control_substeps,
                transition_status='not_recorded')

        return dict(apply_control=apply_control, advance=advance, read_state=lambda: self.state,
                    evaluate=evaluate, observe=lambda _state: self.obs,
                    publish=publish, on_failure=on_failure)

    def _step_mixed_control(self, action, *, proposal=None, observer_solution=None):
        operations = self._prepare_mixed_control(action, proposal=proposal, observer_solution=observer_solution)
        return self._episode_execution_state().execute_interval(**operations)

    def _prepare_mixed_control(self, action, *, proposal=None, observer_solution=None):
        """Run one task-prepared named command through the existing RuntimeSession."""
        from ..controllers.canonical.contracts import AppliedMixedActuatorCommandV1
        from ..runtime.sessions.control import (
            mixed_stepwise_receipt, mixed_substep_controller, validate_mixed_control_preparation,
        )
        from ..recorders.recorder import mixed_control_transition

        if self._stopped or self.session is None:
            raise RuntimeError('reset required or mixed-control episode already stopped')
        if self.state.control_step >= self.horizon:
            self.stop('horizon_reached')
            raise RuntimeError('selected mixed-control horizon is exhausted')
        if (proposal is None) != (observer_solution is None):
            raise ValueError('mixed Solution actions require both proposal and Solution owner')
        if proposal is not None:
            from ..planners.contracts import ExpertAction
            if type(proposal) is not ExpertAction:
                raise TypeError('mixed-control Solution must return the existing ExpertAction contract')
            if self._external_solution_owner is None or observer_solution is not self._external_solution_owner:
                raise ValueError('mixed-control Solution does not own the selected episode')
            if not np.array_equal(np.asarray(action), proposal.action):
                raise ValueError('mixed-control Solution proposal action was changed before preparation')
        before = self.state
        prepared = self.binding.prepare_mixed_control(self, action, before)
        stepwise = self.binding.prepare_mixed_control_substep is not None
        action_values, universal_action, request, target, writer_control = validate_mixed_control_preparation(
            prepared, stepwise=stepwise, source=self.value['source'], artifact=self.artifact,
            session=self.session, sample=self.sample, before=before,
        )
        applied = None
        applied_payload = None
        stepwise_receipt = None
        interval_attempted = False
        interval_completed = False
        failure_phase = 'mixed_control_application'

        def apply_control():
            nonlocal interval_attempted, interval_completed, applied
            nonlocal applied_payload, stepwise_receipt, failure_phase
            interval_attempted = True
            if stepwise:
                failure_phase = 'mixed_physics_substep_interval'
                stepwise_session = getattr(self.session, 'step_mixed_actuator_interval', None)
                if not callable(stepwise_session):
                    raise StageUnavailableError(
                        'selected RuntimeSession does not support physics-rate mixed actuator control'
                    )
                make_substep_command, controller_receipts = mixed_substep_controller(
                    self.binding.prepare_mixed_control_substep, self, prepared,
                )
                self.state, stepwise_receipt = stepwise_session(make_substep_command)
                stepwise_receipt, applied_payload = mixed_stepwise_receipt(
                    stepwise_receipt, controller_receipts,
                    substeps=self.artifact.timebase.control_substeps, target=target,
                )
                interval_completed = True
            else:
                applied = self.session.apply_mixed_actuator_command(target)
                if type(applied) is not AppliedMixedActuatorCommandV1:
                    raise TypeError('RuntimeSession returned an untyped mixed-control acknowledgement')
                applied_payload = applied.to_mapping()
            return applied_payload

        def advance(_applied):
            nonlocal failure_phase, interval_completed
            if not stepwise:
                failure_phase = 'mixed_physics_step'
                self.state = self.session.step()
                interval_completed = True

        def evaluate(_state):
            nonlocal failure_phase
            failure_phase = 'mixed_observation'
            self.obs, self.info, self.evaluation = self.observation(self.state)
            self.info.update({
                'provider': self.provider,
                'external_action': action_values,
                'universal_action': universal_action,
                'mixed_actuator_command_v1': target.to_mapping(),
                'applied_mixed_actuator_command_v1': applied_payload,
            })
            if stepwise_receipt is not None:
                self.info['physics_rate_control_v1'] = stepwise_receipt
            return self.evaluation

        def publish(_control, _state, _evaluation, _observation):
            nonlocal failure_phase
            if proposal is not None:
                failure_phase = 'mixed_solution_observation'
                extra = self.binding.observe_expert_kwargs(self, ())
                if not isinstance(extra, Mapping):
                    raise TypeError('mixed Solution observation kwargs must be a mapping')
                observer_solution.observe(
                    self.obs, float(self.evaluation.reward), bool(self.evaluation.failure),
                    bool(self.state.control_step >= self.horizon), self.info, **dict(extra),
                )
                if hasattr(observer_solution, 'outcome_report'):
                    report = observer_solution.outcome_report()
                    if not isinstance(report, Mapping):
                        raise TypeError('mixed Solution outcome_report() must return a mapping')
                    self.info.update(dict(report))
                self.info.update(
                    selected_policy_execution_complete=bool(observer_solution.done),
                    selected_policy_execution_failed=bool(observer_solution.failed),
                    expert_failure_reason=getattr(observer_solution, 'failure_reason', None),
                    selected_solution_action_v1={
                        'solution_identity': getattr(observer_solution, 'identity', None),
                        'stage': proposal.stage,
                        'diagnostics': dict(proposal.diagnostics),
                    },
                )
                if bool(observer_solution.done) and bool(observer_solution.failed):
                    raise ValueError('mixed Solution cannot be complete and failed at one boundary')
            transition = mixed_control_transition(
                request, writer_control, target, applied_payload, stepwise_receipt,
            )
            terminated, truncated = self._episode_execution_state().step_outcome(
                task_terminated=bool(self.evaluation.failure) if proposal is not None else False,
                task_truncated=False, control_step=self.state.control_step, horizon=self.horizon,
            )
            if proposal is not None and observer_solution.done:
                terminated = False
                truncated = False
            if proposal is not None and observer_solution.failed and not truncated:
                terminated = True
            if self.recorder is not None and getattr(self.recorder, 'active', False):
                failure_phase = 'mixed_recorder_append'
                self.recorder.append_transition(
                    action_values, universal_action, self.obs, float(self.evaluation.reward),
                    bool(self.evaluation.success), terminated, truncated, self.info,
                    structured_control=transition,
                )
            self._episode_mode = 'external_solution' if proposal is not None else 'external'
            if proposal is not None and observer_solution.done:
                self.stop('solution_completed')
                self.info['episode_end_v1'] = self._mixed_episode_end.to_mapping()
            elif proposal is not None and observer_solution.failed and not truncated:
                self.stop('solution_failed')
                self.info['episode_end_v1'] = self._mixed_episode_end.to_mapping()
            elif truncated:
                self.stop('horizon_reached')
                self.info['episode_end_v1'] = self._mixed_episode_end.to_mapping()
            return self.obs, float(self.evaluation.reward), terminated, truncated, self.info

        def on_failure(_phase, error):
            after = None
            readback_error = None
            if interval_attempted:
                try:
                    after = self.session.snapshot()
                    self.state = after
                except BaseException as snapshot_error:
                    readback_error = f'{type(snapshot_error).__name__}: {snapshot_error}'
            self._latch_fault(
                failure_phase, error, before_state=before, after_state=after,
                interval_attempted=interval_attempted,
                interval_completed=interval_completed,
                native_substeps_expected=self.artifact.timebase.control_substeps,
                transition_status='not_recorded', readback_error=readback_error,
            )

        return dict(
            apply_control=apply_control, advance=advance,
            read_state=lambda: self.state, evaluate=evaluate,
            observe=lambda _state: self.obs, publish=publish, on_failure=on_failure,
        )

    def step_with_solution(self, solution):
        """Run one caller-owned Solution action through the selected lifecycle.

        The public readiness payload is checked before calling ``act``. The
        same Solution instance receives post-step ``observe`` before any
        canonical Recorder append. The instance remains the sole owner of its
        mutable stage state.
        """
        self._episode_execution_state().require_step(
            closed_message='environment is closed',
            fault_prefix='selected execution is faulted; reset() is required',
        )
        if self._external_solution_owner is None or solution is not self._external_solution_owner:
            raise ValueError('step_with_solution requires the instance accepted by reset_for_solution')
        self._validate_external_solution(solution)
        if self._stopped or self.session is None:
            raise RuntimeError('reset required or episode already stopped')
        if self._episode_mode in {'expert', 'external'}:
            raise RuntimeError('cannot mix external Solution and other selected execution modes')
        if getattr(solution, 'done', False) or getattr(solution, 'failed', False):
            raise RuntimeError('external Solution already stopped')
        if getattr(self, 'mixed_control_profile', False):
            try:
                proposal = solution.act(self.obs, self.info)
                from ..planners.contracts import ExpertAction
                if type(proposal) is not ExpertAction:
                    raise TypeError('mixed external Solution act() must return ExpertAction')
            except BaseException as error:
                self._latch_fault('mixed_external_solution_proposal', error, before_state=self.state)
                if self.binding.abort_solution_on_runtime_error:
                    try:
                        solution.abort('runtime_error')
                    except BaseException as abort_error:
                        add_note = getattr(error, 'add_note', None)
                        if callable(add_note):
                            add_note(f'mixed external Solution abort also failed: {abort_error!r}')
                raise
            return self._step_mixed_control(
                proposal.action, proposal=proposal, observer_solution=solution,
            )
        try:
            self._require_published_execution_info()
        except BaseException as error:
            self._latch_fault('public_execution_readiness', error, before_state=self.state)
            raise
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
        from ..recorders.position_metadata import position_switch_event

        switch_id = uuid4().hex
        event = position_switch_event(
            switch_id=switch_id, boundary=boundary, clock=clock,
            transition_count=recorder.transition_count,
            sequence=recorder.next_boundary_event_sequence(recorder.transition_count),
            current=current, candidate=candidate,
            binding_identity=self.position_plan.identity_hash,
            source_closure=self.value['source'].source_closure_digest,
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
            from ..recorders.position_metadata import position_switch_fault_receipt
            self._position_controller_switch_fault_receipt = position_switch_fault_receipt(
                switch_id=switch_id, boundary=boundary, clock=clock,
                current=current, candidate=candidate,
                active_controller_identity=self.controller.identity, fault=fault,
            )
            raise
        return event

    def _step_leaf_position(self, action):
        operations = self._prepare_leaf_position(action)
        return self._episode_execution_state().execute_interval(**operations)

    def _prepare_leaf_position(self, action):
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
            from ..controllers.canonical.leaf_actions import ARM_WRITER_ID, HAND_WRITER_ID
        else:
            from ..controllers.canonical.leaf_actions import MAIN_ARM_WRITER_ID as ARM_WRITER_ID, MAIN_HAND_WRITER_ID as HAND_WRITER_ID

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
        completed = False

        def apply_control():
            return dispatch_leaf_control_interval(
                self.leaf_plan, leaf_request, scene=self.position_scene, runtime=self.session,
            )

        def advance(result):
            nonlocal completed
            self.state = self.session.snapshot()
            self.typed_state = result.next_publication
            completed = True
            self.feedback = None
            self.last_leaf_transition = (action, result)

        def evaluate(state):
            self.obs, self.info, self.evaluation = self.observation(state)
            self.info.update({
                'provider': self.provider,
                'leaf_effective_plan_identity_sha256': self.leaf_plan.identity_sha256,
                'leaf_materialization_identity_sha256': self.session.leaf_materialization_receipt.identity_sha256,
            })
            return self.evaluation

        def publish(result, state, evaluation, observation):
            nonlocal append_attempted
            terminated, truncated = self._episode_execution_state().step_outcome(
                task_terminated=evaluation.failure, task_truncated=False,
                control_step=state.control_step, horizon=self.horizon,
            )
            self._episode_execution_state().finish_step(
                terminated=terminated, truncated=truncated,
            )
            self._episode_mode = 'external'
            self._last_position_terminated = terminated
            self._last_position_truncated = truncated
            self._last_position_request = request
            if self.recorder is not None:
                append_attempted = True
                from ..recorders.position_metadata import record_leaf_position_transition
                record_leaf_position_transition(
                    self, action, request, result, terminated=terminated, truncated=truncated,
                )
            self._published_position_state = state
            self._published_position_typed_state = self.typed_state
            self._published_position_obs = observation
            self._published_position_info = dict(self.info)
            self._published_position_evaluation = evaluation
            if terminated or truncated:
                self._position_episode_end = self._make_position_episode_end(
                    'task_terminal' if terminated else 'horizon_reached',
                    terminated=terminated, truncated=not terminated,
                    bootstrap_allowed=not terminated,
                )
                self.info['episode_end_v1'] = self._position_episode_end.to_mapping()
            return observation, float(evaluation.reward), terminated, truncated, self.info

        def on_failure(phase, error):
            nonlocal completed
            if append_attempted:
                phase = 'record_leaf_transition'
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

        return dict(
            apply_control=apply_control, advance=advance,
            read_state=lambda: self.state, evaluate=evaluate,
            observe=lambda _state: self.obs, publish=publish, on_failure=on_failure,
            phases=('leaf_control_preflight', 'leaf_control_preflight',
                    'leaf_control_preflight', 'leaf_observation',
                    'leaf_observation', 'leaf_observation'),
        )

    def _record_leaf_position_transition(self, action, request, result, *, terminated, truncated):
        # Retained for diagnostic consumers of the historical internal method.
        from ..recorders.position_metadata import record_leaf_position_transition
        return record_leaf_position_transition(
            self, action, request, result, terminated=terminated, truncated=truncated,
        )

    def _step_position_profile(self, request, *, proposal=None, observer_solution=None):
        operations = self._prepare_position_profile(request, proposal=proposal, observer_solution=observer_solution)
        return self._episode_execution_state().execute_interval(**operations)

    def _prepare_position_profile(self, request, *, proposal=None, observer_solution=None, caller_driven=False):
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
        from ..controllers.canonical.contracts import StructuredActionRequestV1
        if isinstance(request, StructuredActionRequestV1):
            from ..runtime.sessions.control import prepare_structured_action
            prepare_structured_action(self.position_plan, request)
        elif proposal is not None:
            raise TypeError('PositionServoV1 expert requires a StructuredActionRequestV1')

        before_state = self.state
        interval_attempted = False
        interval_completed = False
        transition_counts_before = self._recording_counts(self.recorder)
        record_append_attempted = False
        publication_phase = 'position_observation'

        def apply_control():
            nonlocal interval_attempted
            interval_attempted = True
            profiles = tuple(getattr(self, 'position_profiles', (self.controller,)))
            controller_profiles = profiles if len(profiles) == 2 else profiles[0]
            requirements = (
                self._position_requirements()
                if hasattr(self, 'position_profiles')
                else getattr(self.controller, 'requirements', None)
            )
            return execute_position_control_interval(
                self.session, controller_profiles, self.position_plan, request, self.typed_state,
                scene=self.position_scene,
                joint_bindings=self.position_joint_bindings,
                frame_bindings=self.position_frame_bindings,
                requirements=requirements,
            )

        def advance(result):
            nonlocal interval_completed
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

        def evaluate(state):
            self.obs, self.info, self.evaluation = self.observation(state)
            if getattr(getattr(self, 'resolved_public_config', None), 'gravity_compensation', False):
                self.info['gravity_compensation_v1'] = self.session.gravity_compensation_receipt
            return self.evaluation

        def publish(result, state, evaluation, observation):
            nonlocal record_append_attempted, publication_phase
            if self.dual_entity_position:
                position_records = result[0]
                canonical = target = applied = None
            else:
                canonical, target, applied = result[:3]
                position_records = ((canonical, target, applied),)
            terminated, truncated = self._episode_execution_state().step_outcome(
                task_terminated=evaluation.failure, task_truncated=False,
                control_step=state.control_step, horizon=self.horizon,
            )
            self._episode_execution_state().finish_step(
                terminated=terminated, truncated=truncated,
            )
            self._episode_mode = 'expert' if proposal is not None and not caller_driven else 'external'
            self._last_position_terminated = terminated
            self._last_position_truncated = truncated
            self._last_position_request = request
            self._publish_task_position_execution_info(self.info)
            if proposal is not None and not caller_driven:
                publication_phase = 'position_solution_observation'
                solution_owner = self.solution if observer_solution is None else observer_solution
                extra = self.binding.observe_expert_kwargs(self, None)
                solution_owner.observe(
                    observation, evaluation.reward, terminated, truncated, self.info, **extra,
                )
                if hasattr(solution_owner, 'outcome_report'):
                    self.info.update(solution_owner.outcome_report())
                self.info.update(
                    selected_policy_execution_complete=bool(solution_owner.done),
                    selected_policy_execution_failed=bool(solution_owner.failed),
                    expert_failure_reason=solution_owner.failure_reason,
                )
                self._stopped = bool(solution_owner.done or solution_owner.failed
                                     or terminated or truncated)
            if self.recorder is not None:
                publication_phase = 'record_position_transition'
                record_append_attempted = True
                if self.dual_entity_position:
                    from ..recorders.position_metadata import record_dual_position_transition
                    record_dual_position_transition(self,
                        request, position_records, terminated=terminated, truncated=truncated,
                    )
                else:
                    from ..recorders.position_metadata import record_position_transition
                    record_position_transition(self,
                        request, canonical, target, applied,
                        terminated=terminated, truncated=truncated,
                    )
            # No boundary is published until the active recorder append succeeds.
            self._published_position_state = state
            self._published_position_typed_state = self.typed_state
            self._published_position_obs = observation
            self._published_position_info = dict(self.info)
            self._published_position_evaluation = evaluation
            if terminated or truncated:
                self._position_episode_end = self._make_position_episode_end(
                    'task_terminal' if terminated else 'horizon_reached',
                    terminated=bool(terminated),
                    truncated=not bool(terminated),
                    bootstrap_allowed=not bool(terminated),
                )
                self.info['episode_end_v1'] = self._position_episode_end.to_mapping()
            return observation, float(evaluation.reward), terminated, truncated, self.info

        def on_failure(phase, error):
            nonlocal interval_completed
            if phase == 'position_publication':
                phase = publication_phase
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

        return dict(
            apply_control=apply_control, advance=advance,
            read_state=lambda: self.state, evaluate=evaluate,
            observe=lambda _state: self.obs, publish=publish, on_failure=on_failure,
            phases=('position_control_compute_apply_step', 'position_control_compute_apply_step',
                    'position_control_compute_apply_step', 'position_observation',
                    'position_observation', 'position_publication'),
        )

    def prepare_expert(self):
        """Create and reset the task Solution on demand after an environment reset."""
        if self._execution_fault is not None or self._stopped or self._episode_mode in {'external', 'external_solution'}:
            raise RuntimeError('reset required before preparing expert execution')
        if self.solution is None:
            factory = self.value.get('solution_factory')
            if not callable(factory):
                raise RuntimeError('selected profile does not provide expert execution')
            try:
                solution = factory()
                if getattr(solution, 'identity', None) != self.value.get('solution_identity'):
                    raise ValueError('constructed Solution identity differs from compiled task')
                if self._native_feedback_profile is not None:
                    self.binding.validate_external_solution(self.value, solution)
                solution.reset(self.obs, self.info, self.metadata,
                               **self.binding.reset_expert_kwargs(self))
            except BaseException as error:
                self._latch_fault('solution_reset', error, before_state=self.state)
                raise
            self.solution = solution
        return self.solution

    def step_expert(self):
        if self._execution_fault is not None:
            fault = self._execution_fault
            raise RuntimeError(
                'selected execution is faulted; reset() is required '
                f"(phase={fault.phase}, physical_progress={fault.physical_progress})"
            )
        if self._stopped or self._episode_mode in {'external', 'external_solution'}:
            raise RuntimeError('reset required; external and expert execution cannot be mixed')
        self.prepare_expert()
        self._episode_mode = 'expert'
        if self.solution.done or self.solution.failed:
            raise RuntimeError('expert already stopped')
        if getattr(self, 'position_profile', False):
            admit_legacy = self.binding.legacy_position_expert_admission
            if admit_legacy is None or not admit_legacy(self.value):
                raise RuntimeError('selected PositionServoV1 profile does not provide expert execution')
        elif hasattr(self.solution, 'readiness_config'):
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
        if getattr(self, 'position_profile', False):
            from ..runtime.sessions.control import single_position_action_request
            try:
                request = single_position_action_request(
                    proposal.action, scene=self.position_scene, plan=self.position_plan,
                    profile=self.position_profiles[0],
                )
            except BaseException as error:
                self._latch_fault('expert_action_validation', error, before_state=self.state)
                raise
            return self._step_position_profile(
                request, proposal=proposal, observer_solution=self.solution,
            )
        return self._step(proposal.action, proposal=proposal, observer_solution=self.solution)

    def _step(self, action, *, proposal=None, observer_solution=None, caller_driven=False):
        operations = self._prepare_reference_step(action, proposal=proposal, observer_solution=observer_solution, caller_driven=caller_driven)
        return self._episode_execution_state().execute_interval(**operations)

    def _prepare_reference_step(self, action, *, proposal=None, observer_solution=None, caller_driven=False):
        if self._execution_fault is not None:
            fault = self._execution_fault
            raise RuntimeError(
                'selected execution is faulted; reset() is required '
                f"(phase={fault.phase}, physical_progress={fault.physical_progress})"
            )
        if self._stopped or self.session is None:
            raise RuntimeError('reset required or episode already stopped')
        try:
            request = self.binding.prepare_action(action)
            if not isinstance(request, RequestedAction):
                raise TypeError('selected action binding must return RequestedAction')
            request.validate()
        except BaseException as error:
            if proposal is not None:
                self._latch_fault('expert_action_validation', error, before_state=self.state)
            raise
        if proposal is not None and observer_solution is None and not caller_driven:
            observer_solution = self.solution
        requested_mode = (
            'external' if caller_driven else
            'external_solution' if proposal is not None and observer_solution is self._external_solution_owner
            else 'expert' if proposal is not None else 'external'
        )
        if self._episode_mode is not None and self._episode_mode != requested_mode:
            raise RuntimeError('cannot mix external actions with selected expert execution')
        self._episode_mode = requested_mode
        stage = proposal.stage if proposal is not None else 'external'
        diagnostics = dict(proposal.diagnostics) if proposal is not None else {}
        if (requested_mode in {'external_solution', 'external'} and proposal is not None
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
        failure_phase = 'recorder_interval_begin'
        interval_attempted = False
        interval_completed = False
        record_append_attempted = False
        canonical = target = applied = request_boundary = interval_receipt = None

        def apply_control():
            nonlocal failure_phase, interval_attempted, interval_completed
            nonlocal canonical, target, applied, request_boundary
            request_boundary = (
                self._execution_boundary(self.expert_execution_info())
                if not self.position_profile else None
            )
            if (self.binding.native_sample_factory is not None
                    and not callable(getattr(self.session, 'native_control_feedback_sample', None))):
                raise RuntimeError('selected Provider RuntimeSession does not expose the required native feedback sample contract')
            if self.binding.control_request_required:
                failure_phase = 'controller_control_request_validation'
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
                failure_phase = 'recorder_interval_begin'
                self.recorder.begin(self.state.control_step, self.artifact.timebase.physics_dt,
                                    self.artifact.timebase.control_substeps)
            if proposal is not None and getattr(proposal, 'control_request', None) is not None:
                failure_phase = 'controller_control_request'
                self.controller.request_arm_execution(proposal.control_request)
            failure_phase = 'controller_compute'
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
                failure_phase = 'physics_step'
                interval_attempted = True
                self.state, target, applied, _ = self.session.step_control_interval(
                    target, self.controller, interval_observer=observe, arm_schedule=self.arm_schedule)
                interval_completed = True
            else:
                # Preserve historical P1.6 grouped control-interval stepping,
                # including the provider's boundary clock accumulation.
                failure_phase = 'control_application'
                applied = self.session.apply_control(target)
            return applied

        def advance(_applied):
            nonlocal failure_phase, interval_attempted, interval_completed
            if self.binding.interval_mode != 'native':
                failure_phase = 'physics_step'
                interval_attempted = True
                self.state = self.session.step()
                interval_completed = True

        def evaluate(_state):
            nonlocal failure_phase, interval_receipt
            failure_phase = 'control_feedback'
            self.feedback = self.session.control_feedback(self.state)
            failure_phase = 'observation'
            self.obs, self.info, self.evaluation = self.observation(self.state)
            self.info['provider'] = self.provider
            if getattr(getattr(self, 'resolved_public_config', None), 'gravity_compensation', False):
                self.info['gravity_compensation_v1'] = self.session.gravity_compensation_receipt
            if not self.position_profile:
                self._publish_execution_info(self.info)
                if canonical is not None and target is not None and applied is not None:
                    self._publish_control_application(
                        self.info, request, canonical, target, applied, request_boundary,
                    )
                    if self.binding.control_request_required and proposal is not None:
                        control_request = proposal.control_request
                        self.info['control_application_v1'].update({
                            'solution_stage': proposal.stage,
                            'arm_execution_request_v1': {
                                'schema_version': control_request.schema_version,
                                'profile_id': control_request.profile_id,
                                'mode': control_request.mode,
                            },
                        })
            interval_receipt = None
            if self.binding.native_interval_receipt_factory is not None:
                failure_phase = 'native_interval_receipt'
                evaluation_boundary = self._execution_boundary(self.expert_execution_info())
                interval_receipt = self.binding.native_interval_receipt_factory(
                    self, request_boundary, evaluation_boundary, tuple(native_samples), tuple(substeps),
                )
                interval_receipt.validate()
                self._active_native_interval_receipt = interval_receipt
                self.info['native_interval_receipt_v1'] = interval_receipt.to_mapping()
            return self.evaluation

        def publish(_control, _state, _evaluation, _observation):
            nonlocal failure_phase, record_append_attempted, diagnostics
            terminated, truncated = self._episode_execution_state().step_outcome(
                task_terminated=self.evaluation.failure, task_truncated=False,
                control_step=self.state.control_step, horizon=self.horizon,
            )
            if proposal is not None and not caller_driven:
                failure_phase = 'solution_observation'
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
            self._episode_execution_state().finish_step(
                terminated=terminated, truncated=truncated, preserve_stop=True,
            )
            if self.recorder is not None:
                failure_phase = 'record_interval'
                record_append_attempted = True
                if 'gravity_compensation_v1' in self.info:
                    diagnostics = {**diagnostics, 'gravity_compensation_v1': self.info['gravity_compensation_v1']}
                self._record_interval(request, canonical, target, applied, stage, diagnostics,
                                      terminated, truncated, substeps)
            return self.obs, float(self.evaluation.reward), terminated, truncated, self.info

        def on_failure(_phase, error):
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
                failure_phase,
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

        return dict(
            apply_control=apply_control, advance=advance,
            read_state=lambda: self.state, evaluate=evaluate,
            observe=lambda _state: self.obs, publish=publish, on_failure=on_failure,
        )

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
        component = self._has_component_assembly()
        cleanup = self._close_component_resources if component else self._close_reference_resources
        return self._episode_execution_state().execute_close(
            cleanup, stop=not component,
            allow_closed=component and not getattr(self, '_resources_closed', False),
        )

    def _close_reference_resources(self):
        if getattr(self, 'mixed_control_profile', False):
            first_error = None
            try:
                # A latched interval fault can leave the Recorder at the
                # prior complete T/T+1 boundary. Do not synthesize a stop
                # event or try to freeze that incomplete trajectory; retain
                # the original fault and proceed with resource cleanup.
                if (self.session is not None and self._mixed_episode_end is None
                        and self._execution_fault is None):
                    self.stop('environment_close')
                if (self.recorder is not None and getattr(self.recorder, 'active', False)
                        and self._execution_fault is None):
                    reason = (self._mixed_episode_end.outcome.end_reason
                              if self._mixed_episode_end is not None else 'environment_close')
                    self.finish_recording(reason)
            except BaseException as error:
                first_error = error
            session_was_materialized = self.session is not None
            active_session, self.session = self.session, None
            if active_session is not None:
                first_error, self._mixed_close_receipt = close_session_and_runtime_owner(
                    active_session, first_error=first_error,
                    session_error_label='mixed-control session close',
                    owner_error_label='mixed-control Runtime owner close',
                    capture_close_receipt=True,
                )
            receipt = getattr(self.value.get('source'), 'execution_source_receipt', None)
            try:
                if receipt is not None:
                    receipt.close()
            except BaseException as error:
                if first_error is None:
                    first_error = error
                else:
                    first_error.add_note(f'mixed-control source receipt cleanup also failed: {type(error).__name__}: {error}')
            task_resource_receipt = None
            task_resource_error = None
            try:
                if self.binding.close_task_resources is not None:
                    task_resource_receipt = self.binding.close_task_resources()
            except BaseException as error:
                task_resource_error = error
                if first_error is None:
                    first_error = error
                else:
                    first_error.add_note(
                        f'mixed-control task resource cleanup also failed: {type(error).__name__}: {error}'
                    )
            if not session_was_materialized and self._mixed_close_receipt is None:
                source = self.value.get('source')
                fault = self._execution_fault
                self._mixed_close_receipt = {
                    'schema_version': 'mixed-control-selected-close-v1',
                    # No RuntimeSession was published. The selected environment
                    # and its receipt-owned source snapshot have still completed
                    # their cleanup attempt; keep that distinct from a native
                    # RuntimeSession close receipt.
                    'session_closed': True,
                    'session_materialized': False,
                    'session_close_status': 'not_materialized',
                    'environment_closed': True,
                    'cleanup_completed': first_error is None,
                    'cleanup_error': None if first_error is None else {
                        'type': type(first_error).__name__, 'message': str(first_error),
                    },
                    'source_id': (
                        None if source is None else source.scene_source.source_id
                    ),
                    'source_closure_digest': (
                        None if source is None else source.source_closure_digest
                    ),
                    'execution_fault_phase': None if fault is None else fault.phase,
                    'execution_fault_message': None if fault is None else fault.message,
                }
            if self._mixed_close_receipt is not None:
                self._mixed_close_receipt = dict(self._mixed_close_receipt)
                if task_resource_receipt is not None:
                    self._mixed_close_receipt['task_resource_close_receipt'] = task_resource_receipt
                if task_resource_error is not None:
                    self._mixed_close_receipt['task_resource_close_error'] = {
                        'type': type(task_resource_error).__name__,
                        'message': str(task_resource_error),
                    }
            if first_error is not None:
                raise first_error
            return
        if not getattr(self, 'position_profile', False):
            first_error = None
            session, self.session = self.session, None
            first_error, _ = close_session_and_runtime_owner(
                session, first_error=first_error,
                session_error_label='session close',
                owner_error_label='Runtime owner close after session close',
            )
            receipt = getattr(self.value.get('source'), 'execution_source_receipt', None)
            try:
                if receipt is not None:
                    receipt.close()
            except BaseException as error:
                if first_error is None:
                    first_error = error
                else:
                    first_error.add_note(
                        f'execution source receipt cleanup also failed: {type(error).__name__}: {error}'
                    )
            task_resource_receipt = None
            try:
                if self.binding.close_task_resources is not None:
                    task_resource_receipt = self.binding.close_task_resources()
            except BaseException as error:
                if first_error is None:
                    first_error = error
                else:
                    first_error.add_note(
                        f'task resource cleanup also failed: {type(error).__name__}: {error}'
                    )
            if getattr(self, 'mixed_control_profile', False) and self._mixed_close_receipt is not None:
                self._mixed_close_receipt = dict(self._mixed_close_receipt)
                if task_resource_receipt is not None:
                    self._mixed_close_receipt['task_resource_close_receipt'] = task_resource_receipt
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

        if self._published_position_state is not None and self._execution_fault is None:
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
        session, self.session = self.session, None
        first_error, _ = close_session_and_runtime_owner(
            session, first_error=first_error,
            session_error_label='RuntimeSession close after Position finalization',
            owner_error_label='Runtime owner close after Position finalization',
        )
        if first_error is not None:
            raise first_error

    def _make_position_episode_end(
        self, end_reason, *, terminated, truncated, bootstrap_allowed,
        task_success=_INFER_POSITION_TASK_SUCCESS, payload=None,
    ):
        from ..trajectory.canonical.episode import make_episode_end_v1

        typed = self._published_position_typed_state
        state = self._published_position_state
        if typed is None or state is None:
            raise RuntimeError('Position Stop requires a successfully returned reset boundary')
        boundary = typed.view.boundary
        from ..recorders.position_metadata import position_episode_end_payload
        leaf = getattr(self, 'leaf_position_profile', False)
        details = position_episode_end_payload(
            state=state, boundary=boundary,
            source_closure_digest=self.value['source'].source_closure_digest,
            controller=None if leaf else self.controller,
            leaf_plan=self.leaf_plan if leaf else None,
            leaf_receipt=self.session.leaf_materialization_receipt if leaf else None,
            position_profiles=self.position_profiles if self.dual_entity_position else None,
            switch_fault_receipt=self._position_controller_switch_fault_receipt,
            pending_switch=self._pending_position_switch,
            execution_fault=self._execution_fault if self._pending_position_switch is not None else None,
            last_transition=getattr(self, 'last_position_transition', None),
            runtime_step=lambda: self.state.control_step, payload=payload,
        )
        if task_success is _INFER_POSITION_TASK_SUCCESS:
            success = (None if self._published_position_evaluation is None
                       else bool(self._published_position_evaluation.success))
        else:
            success = task_success
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
        """Finish once at the last fully published boundary."""
        state = self._episode_execution_state()
        state.require_open('cannot stop a closed environment')
        component_lifecycle = None
        if self._has_component_assembly():
            component_lifecycle = self._require_task_lifecycle()
            operations = component_lifecycle.prepare_stop(reason)
        else:
            operations = self._prepare_reference_stop(reason)
        result = state.execute_stop(reason, **operations)
        if component_lifecycle is not None:
            self._last_episode_end = result
        return result

    def _prepare_reference_stop(self, reason):
        state = self._episode_execution_state()
        if getattr(self, 'mixed_control_profile', False):
            def ensure_boundary():
                if self.session is None or getattr(self, 'state', None) is None:
                    raise RuntimeError('mixed-control reset must complete before Stop')

            def create_end():
                from ..trajectory.canonical.episode import make_episode_end_v1
                fault = self._execution_fault
                solution = self._external_solution_owner
                solution_done = bool(getattr(solution, 'done', False)) if solution is not None else None
                solution_failed = bool(getattr(solution, 'failed', False)) if solution is not None else None
                if reason == 'solution_completed' and solution_done is not True:
                    raise ValueError('solution_completed requires the active caller-owned Solution to be done')
                if reason == 'solution_failed' and solution_failed is not True:
                    raise ValueError('solution_failed requires the active caller-owned Solution to be failed')
                end_reason, terminated, truncated, bootstrap_allowed = state.stop_outcome(
                    reason, selected_reasons=True,
                )
                success = None if fault is not None else bool(self.evaluation.success)
                event_sequence = 0
                if self.recorder is not None and getattr(self.recorder, 'active', False):
                    event_sequence = self.recorder.next_boundary_event_sequence(int(self.state.control_step))
                payload = {
                    'requested_reason': reason,
                    'control_step': int(self.state.control_step),
                    'simulation_time_s': float(self.state.simulation_time),
                    'source_id': self.value['source'].scene_source.source_id,
                    'source_closure_digest': self.value['source'].source_closure_digest,
                    'reset_sample_id': self.sample.sample_id,
                    'controller_identity': self.controller.identity,
                    'task_evaluation_success': success,
                }
                if solution is not None:
                    payload['solution_identity'] = getattr(solution, 'identity', None)
                    payload['solution_done'] = solution_done
                    payload['solution_failed'] = solution_failed
                    payload['solution_failure_reason'] = getattr(solution, 'failure_reason', None)
                if fault is not None:
                    payload['fault'] = fault.to_mapping()
                self._mixed_episode_end = make_episode_end_v1(
                    episode_id=self.session.episode_id,
                    final_boundary=int(self.state.control_step),
                    end_reason=end_reason,
                    terminated=terminated,
                    truncated=truncated,
                    bootstrap_allowed=bootstrap_allowed,
                    source='task_env.selected_reference.mixed_control_v1',
                    payload=payload,
                    event_sequence=event_sequence,
                    task_success=(None if fault is not None else success),
                    solution_completed=(
                        None if solution is None else
                        bool(solution_done and not solution_failed)
                    ),
                )
                return self._mixed_episode_end

            return dict(closed_message='cannot stop a closed selected environment',
                        ensure_boundary=ensure_boundary, create_end=create_end)
        if not getattr(self, 'position_profile', False):
            raise StageUnavailableError(
                'Stop/Outcome is only admitted for the PositionServoV1 candidate; '
                'legacy selected production-r1 behavior is unchanged'
            )

        def ensure_boundary():
            if self.session is None or self._published_position_typed_state is None:
                raise RuntimeError('reset() must complete before Stop')

        def create_end():
            end_reason, terminated, truncated, bootstrap_allowed = state.stop_outcome(reason)
            if self._execution_fault is not None:
                fault = self._execution_fault
                self._position_episode_end = self._make_position_episode_end(
                    end_reason, terminated=terminated, truncated=truncated,
                    bootstrap_allowed=bootstrap_allowed,
                    task_success=_INFER_POSITION_TASK_SUCCESS,
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
                    end_reason, terminated=terminated, truncated=truncated,
                    bootstrap_allowed=bootstrap_allowed,
                    payload={'requested_reason': reason},
                )
            return self._position_episode_end


        return dict(closed_message='cannot stop a closed selected environment',
                    ensure_boundary=ensure_boundary, create_end=create_end)

    def _boundary(self):
        from ..trajectory.canonical.contracts import BoundaryRecord
        return BoundaryRecord(self.state.control_step, self.state.simulation_time,
            self.state, self.feedback, self.controller.readiness(self.state, self.feedback),
            {k: float(v) for k, v in self.info['task_metrics'].items()},
            bool(self.evaluation.success), bool(self.evaluation.failure))

    def _owners(self):
        from ..recorders.reference_provenance import coordinator_receipt

        return coordinator_receipt(
            step=self.state.control_step, time=self.state.simulation_time,
            artifact_hash=self.artifact.identity_hash,
            controller_identity=self.controller.identity,
            solution_identity=self._active_solution_identity(), provider=self.provider,
            execution_mode=self._episode_mode, task_outcome=self.info,
            source_sha256=self._recording_adapter_source_sha256,
        )

    def get_execution_receipt(self):
        """Return JSON-safe requested/resolved facts, without native-readback claims."""
        import json
        from ..runtime.sessions.transport import request_identity
        if self._has_component_assembly():
            plan = self.execution_plan
            selection = plan.execution_spec_v2
            facts = {'plan': plan.to_mapping(), 'selection': selection.to_mapping()}
            receipt = {'schema_version': 'deployment-preflight-v1', 'phase': 'static_config',
                       'request_identity': request_identity(facts), 'requested': None,
                       'resolved': selection.to_mapping(), 'identity_facts': facts,
                       'dependency': {'status': 'unknown', 'reason': 'not checked'},
                       'native_effective': {'status': 'unknown', 'reason': 'native readback not available'},
                       'evidence': 'none', 'status': 'selection_only'}
        else:
            receipt = getattr(self, '_deployment_receipt', None)
            if receipt is None:
                selection, requested_json = self._selected_execution_context()
                if selection is None:
                    raise StageUnavailableError('execution receipt is unavailable on this compatibility route')
                from ..runtime.sessions.provenance import describe_execution_selection
                requested = None if requested_json is None else json.loads(requested_json)
                receipt = describe_execution_selection(
                    selection, requested=requested, task_uid=self.uid,
                    artifact=self.artifact, source=self.value['source'],
                    controller=self.value.get('controller', self.value.get('leaf_plan')), seed=None,
                )
        result = json.loads(json.dumps(receipt, sort_keys=True, allow_nan=False))
        if getattr(getattr(self, 'resolved_public_config', None), 'reset_profile', None) == 'pickcube-state-only-switch-v1' and hasattr(self, '_switch_generation'):
            result['reset_switch_v1'] = {
                'configuration_generation': self._switch_generation,
                'topology_generation': self._switch_topology_generation,
                'task_seed': self._switch_task_seed,
                'provider_seed': self._switch_provider_seed,
                'task_seed_algorithm': 'pickcube-reset-seed-v1',
                'provider_seed_algorithm': 'pickcube-provider-seed-task-identity-v1',
            }
        return result

    def _recorded_execution_configuration(self):
        from ..recorders.reference_provenance import recorded_execution_configuration
        return recorded_execution_configuration(
            uid=self.uid, provider=self.provider, backend=self.backend, horizon=self.horizon,
            resolved=getattr(self, 'resolved_public_config', None),
        )

    def start_recording(self, path):
        from ..trajectory.canonical.execution import ExecutionRecorder
        if (self.session is None or self.state.control_step != 0 or self.recorder is not None
                or self._stopped or self._position_episode_end is not None
                or self._mixed_episode_end is not None):
            raise RuntimeError('recording starts exactly once at reset boundary')
        if getattr(self, 'mixed_control_profile', False):
            from ..recorders.recorder import begin_structured_recording
            self.recording_path, self.recorder = begin_structured_recording(
                path, horizon=self.horizon, observation=self.obs, reset_info=self.info,
                metadata_factory=self.get_record_metadata,
            )
            return
        if getattr(self, 'position_profile', False):
            from ..recorders.recorder import begin_structured_recording
            from ..recorders.position_metadata import position_control_binding_provenance
            def metadata_factory():
                record_metadata = self._position_record_metadata()
                record_metadata['resolved_config']['position_control_binding_provenance'] = (
                    position_control_binding_provenance(
                        self._materialized_position_control_binding,
                        self._materialized_position_control_selector,
                    )
                )
                return record_metadata
            self.recording_path, self.recorder = begin_structured_recording(
                path, horizon=self.horizon, observation=self.obs,
                reset_info=self._position_reset_info, metadata_factory=metadata_factory,
                max_buffer_bytes=(
                    self.camera_observation_config.max_recording_buffer_bytes
                    if self.camera_observation_config is not None else None
                ),
            )
            return
        path = Path(path)
        if path.exists():
            raise FileExistsError(path)
        from ..recorders.reference_provenance import (
            selected_recording_metadata, selected_source_provenance,
        )
        execution_configuration = self._recorded_execution_configuration()
        solution_identity = self._active_solution_identity()
        self._recording_adapter_source_sha256, source_provenance = selected_source_provenance(
            adapter_path=__file__, binding=self.binding, value=self.value, artifact=self.artifact,
            controller_identity=self.controller.identity, solution_identity=solution_identity,
            execution_configuration=execution_configuration,
            execution_receipt=(self.get_execution_receipt()
                               if getattr(self, 'resolved_public_config', None) is not None else None),
        )
        owners = self._owners()
        metadata, recipe = selected_recording_metadata(
            artifact=self.artifact, sample=self.sample, realized=self.realized,
            execution=self.execution, provider=self.provider, source_provenance=source_provenance,
            controller_identity=self.controller.identity, solution_identity=solution_identity,
            action_schema=self.metadata['action_schema'],
            factory=type(self).__module__ + '.' + type(self).__name__,
            configuration=self.value['resolved_configuration'],
            execution_configuration=execution_configuration, owners=owners,
        )
        if self.binding.recorder_mode == 'canonical':
            from ..trajectory.canonical.contracts import CanonicalRecorder
            recorder = CanonicalRecorder(metadata, self._boundary())
            self.recording_path, self.recorder = path, recorder
            return
        recorder = ExecutionRecorder(metadata, recipe, content_fields=('task_outcome',))
        recorder.boundary(self._boundary(), owners, 'reference', self.info['task_metrics'])
        self.recording_path, self.recorder = path, recorder

    def _record_interval(self, request, canonical, target, applied, stage, diagnostics,
                         terminated, truncated, substeps):
        from ..recorders.reference_provenance import append_selected_transition
        return append_selected_transition(
            self.recorder, recorder_mode=self.binding.recorder_mode,
            record_native_substeps=self.binding.record_native_substeps,
            timebase=self.artifact.timebase, control_step=self.state.control_step,
            substeps=substeps, request=request, canonical=canonical, target=target,
            applied=applied, reward=self.evaluation.reward, terminated=terminated,
            truncated=truncated, stage=stage, diagnostics=diagnostics,
            boundary=self._boundary, owners=self._owners, task_metrics=lambda: self.info['task_metrics'],
        )

    def finish_recording(self, reason):
        if getattr(self, 'mixed_control_profile', False):
            from ..recorders.recorder import finalize_structured_recording

            if self.recorder is None or not getattr(self.recorder, 'active', False):
                raise RuntimeError('no active mixed-control recording')
            if self._mixed_episode_end is None:
                self.stop(str(reason))
            return finalize_structured_recording(
                self.recorder, self.recording_path, self._mixed_episode_end, reason, position=False,
            )
        if getattr(self, 'position_profile', False):
            from ..recorders.recorder import finalize_structured_recording
            if self.recorder is None or not getattr(self.recorder, 'active', False):
                raise RuntimeError('no active recording')
            if self._position_episode_end is None:
                self.stop(str(reason))
            return finalize_structured_recording(
                self.recorder, self.recording_path, self._position_episode_end, reason, position=True,
                leaf=self.leaf_position_profile, camera=self.camera_observation_config is not None,
            )
        if self.recorder is None or getattr(self.recorder, 'frozen', getattr(self.recorder, '_frozen', False)):
            raise RuntimeError('no active recording')
        if self.binding.recorder_mode == 'canonical' and self._execution_fault is not None:
            raise RuntimeError(
                'cannot finalize a faulted selected recording as a complete trajectory; '
                'reset is required'
            )
        from ..recorders.reference_provenance import finalize_selected_recording
        return finalize_selected_recording(
            self.recorder, self.recording_path, recorder_mode=self.binding.recorder_mode,
            reason=reason,
        )

    def get_record_metadata(self):
        """Return the task-owned JSON-safe metadata for the mixed-control Recorder."""
        if self._has_component_assembly():
            return {**self._component_record_metadata(), 'execution_configuration_v1': self.get_execution_receipt()}
        if not getattr(self, 'mixed_control_profile', False):
            if getattr(self, 'position_profile', False):
                return self._position_record_metadata()
            return {'execution_configuration_v1': self.get_execution_receipt()}
        value = self._mixed_record_metadata
        if value is None:
            value = self.binding.mixed_record_metadata(self)
        if not isinstance(value, Mapping):
            raise TypeError('task recording metadata hook must return a mapping')
        result = dict(value)
        if self._selected_execution_context()[0] is not None:
            result['execution_configuration_v1'] = self.get_execution_receipt()
        return result

    def _position_record_metadata(self):
        from ..recorders.position_metadata import position_record_metadata
        result = position_record_metadata(self)
        if getattr(getattr(self, 'resolved_public_config', None), 'gravity_compensation', False):
            result['resolved_config']['gravity_compensation'] = True
            result['env_metadata']['reference_profile']['gravity_compensation'] = {
                'enabled': True, 'schema_version': 'panda-gravity-position-contribution-v1',
                'source_closure_digest': self.value['source'].source_closure_digest,
            }
        if self._selected_execution_context()[0] is not None:
            result['execution_configuration_v1'] = self.get_execution_receipt()
        return result
