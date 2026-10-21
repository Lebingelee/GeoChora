"""TaskEnv lifecycle facade."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from gymnasium.spaces import Box

from .configuration import resolve_env_config, resolve_execution_plan
from ..registry import AGENT_REGISTRY, OBJECT_REGISTRY, SCENE_REGISTRY
from .config import ResolvedEnvConfig
from .gym_compat import GymEnvBase
from .metadata import (
    TaskEnvMetadata,
    build_stage0_metadata,
    gym_metadata_dict,
    validate_task_info,
)
from .protocols import TaskEnvironmentComponent
from .lifecycle import SingleTaskLifecycleAdapter, TaskLifecycleAdapter
from .types import (
    ControlCommand,
    ExecutionFaultV1,
    SnapshotRequest,
    StageUnavailableError,
    TaskCompositionSpec,
    TaskEvaluation,
    attach_execution_fault,
)


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


class BaseTaskEnv(GymEnvBase, TaskEnvironmentComponent):
    """组合组件，并在显式构造时延迟创建物理 runtime。"""

    uid = "base-task-env"
    task_uid = "base-task-v1"
    scene_uid = "tabletop-v1"
    agent_uids: tuple[str, ...] = ()
    object_uids: tuple[str, ...] = ()
    success_definition = "none"
    # A generic TaskEnv step does not yet publish StructuredControlTransitionV1.
    # The v3 transition wrapper checks this declaration before recording.
    supports_structured_control_recording = False

    metadata = {
        "render_modes": [],
        "stage": "stage4_gym_contract",
    }
    render_mode = None
    action_space = None
    observation_space = None

    def __init__(
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
        self._last_task_evaluation = None
        self._camera_sensors = ()
        self._sensor_provider = None
        self._last_camera_metadata = {}
        self._last_snapshot = None
        self._elapsed_steps = 0
        self._episode_finished = False
        self.metadata = gym_metadata_dict(self._env_metadata, stage="stage4_gym_contract")
        reference_profile = _json_value(self.reference_profile())
        if reference_profile:
            self.metadata["reference_profile"] = reference_profile
        self._configure_render_metadata()
        if build_runtime:
            self._build_runtime_with_rollback()

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
            if "panda-v1" in resolved_agents:
                from ..controllers import (
                    AbsoluteJointPositionActionAdapter,
                    AbsolutePoseActionAdapter,
                    DeltaPoseActionController,
                )
                from ..robots.runtime import (
                    RobotControllerHandle,
                    RobotFrameReference,
                    RobotRuntime,
                )

                controller_config = self.config.robot.controller
                if controller_config is None:
                    raise StageUnavailableError(
                        "robot TaskEnv requires an explicit robot.controller config"
                    )
                from .types import ActionModeSpec

                action_spec = ActionModeSpec.from_controller_config(controller_config)
                controller_kind = controller_config.kind
                controller_reference = controller_config.reference
                if controller_config.kind == "absolute_joint":
                    adapter_type = AbsoluteJointPositionActionAdapter
                elif controller_config.kind == "absolute_pose":
                    adapter_type = AbsolutePoseActionAdapter
                elif controller_config.kind == "delta_pose":
                    adapter_type = DeltaPoseActionController
                else:
                    raise StageUnavailableError(
                        f"unsupported robot controller kind {controller_config.kind!r}"
                    )
                panda_agent = next(
                    agent for agent in self.agents if agent.uid == "panda-v1"
                )
                references = compiled_scene.references.agents[
                    "panda-v1"
                ]
                reference_identity = {
                    None: None,
                    "world": "world",
                    "base": f"body:{references.base_body_name}",
                    "ee": f"site:{references.eef_site_name}",
                }[controller_reference]
                action_spec = replace(
                    action_spec,
                    reference_identity=reference_identity,
                )
                self._env_metadata = replace(
                    self._env_metadata,
                    external_action=action_spec,
                )
                gripper = panda_agent.create_gripper_controller(
                    references=references,
                    config=self.config.action,
                    kind=self.config.robot.gripper.kind,
                    force_limit_N=self.config.robot.gripper.force_limit_N,
                    opening_step_m=self.config.robot.gripper.opening_step_m,
                    force_deadband_N=self.config.robot.gripper.force_deadband_N,
                    force_adjust_step_m=self.config.robot.gripper.force_adjust_step_m,
                )
                bind_force_limit = getattr(gripper, "bind_force_limit", None)
                if callable(bind_force_limit):
                    bind_force_limit(self._runtime_assembly.boundary)
                adapter_kwargs = {
                    "references": references,
                    "config": self.config.action,
                    "gripper": gripper,
                }
                if controller_config.kind in {
                    "absolute_pose",
                    "delta_pose",
                }:
                    adapter_kwargs["controller_config"] = controller_config
                    adapter_kwargs["action_spec"] = action_spec
                controller = RobotControllerHandle(
                    adapter=adapter_type(**adapter_kwargs),
                    kind=controller_kind,
                    reference=controller_reference,
                    action_spec=action_spec,
                )
                self._robot = RobotRuntime(
                    uid="panda-v1",
                    references=references,
                    controller=controller,
                    gripper=gripper,
                    world=RobotFrameReference(
                        name="world",
                        frame_type="world",
                        index=None,
                        source_name="world",
                    ),
                    base=RobotFrameReference(
                        name="base",
                        frame_type="body",
                        index=references.base_body_id,
                        source_name=references.base_body_name,
                    ),
                    ee=RobotFrameReference(
                        name="ee",
                        frame_type="site",
                        index=references.eef_site_id,
                        source_name=references.eef_site_name,
                    ),
                )
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
    def composition_spec(self) -> TaskCompositionSpec:
        return self._composition_spec

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
    def execution_fault(self) -> ExecutionFaultV1 | None:
        """Return the latched receipt after an incomplete lifecycle operation."""

        lifecycle = self._task_lifecycle
        return None if lifecycle is None else lifecycle.execution_fault

    @property
    def episode_end(self):
        """Return the most recent immutable Event/Outcome finalizer result."""

        lifecycle = self._task_lifecycle
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

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ):
        if self._closed:
            raise RuntimeError("environment is closed")
        super().reset(seed=seed)
        self._last_camera_metadata = {}
        lifecycle = self._require_task_lifecycle()
        result = lifecycle.reset(
            seed=seed,
            options=options,
            rng=self.np_random,
        )
        snapshot = result.snapshot
        evaluation = result.evaluation
        reset_parameters = result.reset_parameters
        self._last_snapshot = snapshot
        self._elapsed_steps = lifecycle.elapsed_steps
        self._episode_finished = lifecycle.episode_finished
        self._last_task_evaluation = evaluation
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

    def step(self, action):
        if self._closed:
            raise RuntimeError("environment is closed")
        lifecycle = self._require_task_lifecycle()
        self._last_camera_metadata = {}
        result = lifecycle.step(action)
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
            self._episode_finished = lifecycle.episode_finished
            raise

    def _format_step_result(self, lifecycle, result):
        snapshot = result.snapshot
        evaluation = result.evaluation
        command = result.command
        applied = result.applied
        self._last_task_evaluation = evaluation
        self._last_snapshot = snapshot
        self._elapsed_steps = result.elapsed_steps
        self._episode_finished = lifecycle.episode_finished
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

    def stop(self, reason: str = "external_stop"):
        """Stop at the last complete public boundary without compute or step."""

        if self._closed:
            raise RuntimeError("cannot stop a closed environment")
        lifecycle = self._require_task_lifecycle()
        result = lifecycle.stop(reason)
        self._last_episode_end = result
        self._episode_finished = lifecycle.episode_finished
        return result

    def get_record_metadata(self) -> dict[str, Any]:
        """Return the JSON-compatible public projection used by recorders only."""
        metadata = {
            "env_metadata": _json_value(self.metadata),
            "resolved_config": _json_value(asdict(self.config)),
        }
        metadata["universal_action_schema"] = _json_value(
            self.metadata.get("universal_action_schema", {})
        )
        return metadata

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

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
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
        if lifecycle is not None and lifecycle.episode_end is not None:
            self._last_episode_end = lifecycle.episode_end
        if first_error is not None:
            raise first_error
