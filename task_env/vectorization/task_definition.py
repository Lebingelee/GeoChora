"""Framework-owned scalar/batch task lifecycle adapter.

Task authors do not subclass this module.  The adapter receives the same
``TaskDefinitionBase`` used by ``BaseTaskEnv`` and supplies the batch runtime,
reset sampler, action binding and observation space assembled by the
framework.  All episode bookkeeping remains here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import inspect
from typing import Any

import gymnasium as gym
import numpy as np

from ..environment.task_definition import TaskDefinitionBase, as_task_state_view
from ..environment.lifecycle import TaskLifecycleAdapter as CommonTaskLifecycleAdapter
from ..environment.types import EpisodePhysicsState, StageUnavailableError
from ..runtime.contracts import (
    BatchRuntimeProtocol,
    DeviceBatchResetResult,
    DeviceBatchState,
    DeviceBatchTransition,
    DeviceResetSelection,
    build_world_randomization_batch,
    validate_device_reset_selection,
)
from ..runtime.device_plan import admit_runtime_port, build_device_field_plan
from ..utils.tree import tree_index
from .contracts import (
    BatchResetSample,
    BatchTaskEvaluation,
    BatchTaskResetResult,
    BatchTaskStepResult,
)


def _seeded_rng(
    rng: np.random.Generator,
    seed: int | None,
) -> np.random.Generator:
    return rng if seed is None else np.random.default_rng(int(seed))


def _accepts_keyword(callable_value: Any, name: str) -> bool:
    """Return whether a compatibility hook accepts one optional keyword."""

    try:
        parameters = inspect.signature(callable_value).parameters
    except (TypeError, ValueError):
        return False
    parameter = parameters.get(name)
    if parameter is not None and parameter.kind in {
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }:
        return True
    return any(
        value.kind == inspect.Parameter.VAR_KEYWORD
        for value in parameters.values()
    )


def _validate_device_state_fields(
    state: Any,
    *,
    names: tuple[str, ...],
    num_envs: int,
    device: str | None,
    phase: str,
) -> DeviceBatchState:
    """校验冻结 device field plan 所承诺的命名状态字段。"""

    if not isinstance(state, DeviceBatchState):
        raise TypeError(
            f"{phase} must return DeviceBatchState; got {type(state).__name__}"
        )
    missing = tuple(name for name in names if name not in state.arrays)
    if missing:
        raise StageUnavailableError(
            f"{phase} omitted fields declared by DeviceFieldPlan: {missing}"
        )
    if int(state.num_envs) != int(num_envs):
        raise ValueError(
            f"{phase} returned num_envs={state.num_envs}, expected {num_envs}"
        )
    if device is not None and str(state.device) != str(device):
        raise ValueError(
            f"{phase} returned device={state.device!r}, expected {device!r}"
        )
    return state


def _sample_batch_reset(
    *,
    reset_sampler: object,
    compiled_scene: object,
    initial_state: EpisodePhysicsState,
    num_envs: int,
    rng: np.random.Generator,
    seeds: Sequence[int | None] | None,
) -> BatchResetSample:
    """Adapt the single public reset sampler to a batch value object.

    A sampler may expose an optimized ``sample_batch`` implementation, but the
    framework first accepts the canonical scalar ``sample_episode_state``
    contract and stacks its low-frequency reset values.  No physics or
    ``RuntimeSnapshot`` is created in this adapter.
    """

    sample_batch = getattr(reset_sampler, "sample_batch", None)
    if callable(sample_batch):
        candidate = sample_batch(
            num_envs=num_envs,
            rng=rng,
            seeds=seeds,
        )
        if not isinstance(candidate, BatchResetSample):
            raise TypeError("reset sampler sample_batch() must return BatchResetSample")
        # The generic scene runtime consumes compiled state names.  Legacy
        # task-owned semantic state is retained only for compatibility and
        # falls through to the canonical scalar sampler below.
        if "qpos" in candidate.state and "qvel" in candidate.state:
            return candidate

    sample_episode_state = getattr(reset_sampler, "sample_episode_state", None)
    if not callable(sample_episode_state):
        raise StageUnavailableError(
            f"reset sampler {type(reset_sampler).__name__} provides neither "
            "sample_episode_state() nor a compiled-state sample_batch()"
        )

    size = int(num_envs)
    seed_values = [None] * size if seeds is None else list(seeds)
    if len(seed_values) != size:
        raise ValueError("explicit vector seeds must have length B")
    states: list[EpisodePhysicsState] = []
    parameters: list[Mapping[str, Any]] = []
    actual_seeds: list[int | None] = []
    for slot, seed in enumerate(seed_values):
        slot_seed = None if seed is None else int(seed)
        slot_state, slot_parameters = sample_episode_state(
            compiled_scene=compiled_scene,
            initial_state=initial_state,
            rng=_seeded_rng(rng, slot_seed),
            seed=slot_seed,
        )
        if not isinstance(slot_state, EpisodePhysicsState):
            raise TypeError("episode reset sampler must return EpisodePhysicsState")
        if not isinstance(slot_parameters, Mapping):
            raise TypeError("episode reset sampler parameters must be a mapping")
        states.append(slot_state)
        parameters.append(dict(slot_parameters))
        actual_seeds.append(slot_seed)

    def _stack(name: str) -> np.ndarray:
        return np.stack(
            [np.asarray(getattr(state, name), dtype=np.float32) for state in states],
            axis=0,
        )

    return BatchResetSample(
        state={
            "qpos": _stack("qpos"),
            "qvel": _stack("qvel"),
            "qacc": _stack("qacc"),
            "ctrl": _stack("ctrl"),
            "act": _stack("act"),
        },
        seeds=actual_seeds,
        parameters=parameters,
    )


class BatchTaskLifecycleAdapter(CommonTaskLifecycleAdapter):
    """Batch runtime lifecycle over the common task semantic adapter.

    This class owns batch runtime bookkeeping and action-tree conversion.  The
    inherited adapter owns task dispatch, evaluation validation, observation
    projection, and horizon/termination semantics shared with ``BaseTaskEnv``.
    """

    def __init__(
        self,
        *,
        uid: str,
        num_envs: int,
        backend: str,
        base_seed: int,
        runtime: BatchRuntimeProtocol,
        reset_sampler: object,
        compiled_scene: object,
        initial_state: EpisodePhysicsState,
        task_definition: TaskDefinitionBase,
        action_adapter: object | None,
        single_action_space: gym.spaces.Space,
        single_observation_space: gym.spaces.Space,
        metadata: Mapping[str, Any],
        horizon: int,
        ignore_done: bool,
    ) -> None:
        if int(num_envs) < 1:
            raise ValueError("num_envs must be positive")
        self.uid = str(uid)
        self.num_envs = int(num_envs)
        self.backend = str(backend)
        self.base_seed = int(base_seed)
        self.runtime = runtime
        self.reset_sampler = reset_sampler
        self.compiled_scene = compiled_scene
        # P2-S18 attaches a renderer-facing provider only when the concrete
        # batch runtime advertises the selected-world snapshot capability.
        self.parallel_render_provider = None
        self.initial_state = initial_state
        self.task_definition = task_definition
        self.action_adapter = action_adapter
        self.single_action_space = single_action_space
        self.single_observation_space = single_observation_space
        self.metadata = dict(metadata)
        self.horizon = int(horizon)
        self.ignore_done = bool(ignore_done)
        self.resolved_config = {
            "task_uid": self.uid,
            "num_envs": self.num_envs,
            "backend": self.backend,
            "base_seed": self.base_seed,
        }
        curriculum_spec = getattr(
            self.task_definition, "observation_noise_curriculum_spec", None
        )
        self._observation_noise_curriculum = (
            dict(curriculum_spec()) if callable(curriculum_spec) else None
        )
        self._observation_noise_total_ticks: int | None = None
        self._observation_noise_tick = 0
        self._observation_noise_level = 1.0
        self._domain_randomization_progress_setter = getattr(
            self.reset_sampler,
            "set_domain_randomization_progress",
            None,
        )
        self._domain_randomization_total_ticks: int | None = None
        self._domain_randomization_tick = 0
        self._domain_randomization_progress = 0.0
        if self._observation_noise_curriculum is not None:
            self.metadata["observation_noise_curriculum"] = dict(
                self._observation_noise_curriculum
            )
            self.resolved_config["observation_noise_curriculum"] = dict(
                self._observation_noise_curriculum
            )
        self._rng = np.random.default_rng(self.base_seed)
        self._elapsed_steps = np.zeros(self.num_envs, dtype=np.int32)
        # Device-capable tasks keep their policy-tick horizon counter on the
        # learner/physics device.  The NumPy counter above remains the
        # canonical Gym/SB3 bookkeeping path; it must not be copied back on
        # every device transition.
        self._device_elapsed_steps = None
        self._last_state = None
        self._last_device_state = None
        runtime_admission = admit_runtime_port(
            runtime=self.runtime,
            summary=(
                self.metadata.get("runtime_resource_summary")
                if isinstance(self.metadata.get("runtime_resource_summary"), Mapping)
                else None
            ),
            execution=str(self.metadata.get("execution", "local")),
            requested_transfer_mode=str(
                self.metadata.get("transfer_mode", "device")
            ),
        )
        if not runtime_admission.host_available:
            raise StageUnavailableError(
                "batch runtime does not satisfy the host Runtime Port: "
                + ", ".join(runtime_admission.host_reasons)
            )
        # 在构造期解析一次可选 device hook。计划用于公开 provenance；缓存的
        # callable 让正常 device tick 不再重复反射和构造 capability 列表。
        self.device_field_plan = build_device_field_plan(
            runtime=self.runtime,
            action_adapter=self.action_adapter,
            task_definition=self.task_definition,
            metadata=self.metadata,
            num_envs=self.num_envs,
            backend=self.backend,
        )
        self.metadata["device_field_plan"] = self.device_field_plan.as_dict()
        self.resolved_config["device_field_plan"] = self.device_field_plan.as_dict()
        self._device_runtime_read = getattr(self.runtime, "read_device_state", None)
        self._device_runtime_step = getattr(self.runtime, "step_device", None)
        self._device_runtime_reset = getattr(self.runtime, "reset_device", None)
        self._device_runtime_reset_validator = getattr(
            self.runtime,
            "validate_device_reset_selection",
            None,
        )
        self._device_action_converter = getattr(self.action_adapter, "convert_device_batch", None)
        self._device_observation_builder = getattr(self.task_definition, "build_device_observation", None)
        self._privileged_observation_builder = getattr(
            self.task_definition, "build_privileged_observation", None
        )
        self._device_privileged_observation_builder = getattr(
            self.task_definition, "build_device_privileged_observation", None
        )
        self._device_evaluator = getattr(self.task_definition, "evaluate_device", None)
        self._device_task_reset = getattr(self.task_definition, "reset_device", None)
        self._runtime_world_randomization = getattr(
            self.runtime, "apply_world_randomization", None
        )
        self._device_state_fields = self.device_field_plan.state_readback_fields
        # 仅由 Stage 17 诊断挂载；正常 lifecycle 不创建计时对象。
        self._profile_collector = None
        super().__init__(
            task_definition=task_definition,
            horizon=self.horizon,
            ignore_done=self.ignore_done,
        )

    def set_profile_collector(self, collector) -> None:
        """挂载或卸载 Stage 17 的 runtime/task/bridge 分段计时器。"""

        self._profile_collector = collector
        setter = getattr(self.runtime, "set_profile_collector", None)
        if callable(setter):
            setter(collector)

    def _require_world_randomization(self):
        """为非空 randomization payload 执行一次正式 port admission。"""

        admission = admit_runtime_port(
            runtime=self.runtime,
            summary=(
                self.metadata.get("runtime_resource_summary")
                if isinstance(self.metadata.get("runtime_resource_summary"), Mapping)
                else None
            ),
            execution=str(self.metadata.get("execution", "local")),
            requested_transfer_mode=str(
                self.metadata.get("transfer_mode", "host_numpy")
            ),
            randomization_required=True,
        )
        if not admission.randomization_available:
            raise StageUnavailableError(
                "reset sampler produced a randomization payload but the Runtime "
                "Port cannot apply it: "
                + ", ".join(admission.randomization_reasons)
            )
        return self._runtime_world_randomization

    @property
    def observation_noise_level(self) -> float:
        return float(self._observation_noise_level)

    def configure_observation_noise_curriculum(
        self, *, total_policy_ticks: int, start_policy_tick: int = 0
    ) -> None:
        """Configure a task-declared noise schedule in policy-tick units."""

        spec = self._observation_noise_curriculum
        if not spec or not bool(spec.get("enabled", False)):
            return
        total = int(total_policy_ticks)
        if total < 1:
            raise ValueError("total_policy_ticks must be positive")
        start = max(0, min(int(start_policy_tick), total))
        self._observation_noise_total_ticks = total
        self._observation_noise_tick = start
        self._set_observation_noise_level(self._curriculum_level(start))

    def _curriculum_level(self, tick: int) -> float:
        spec = self._observation_noise_curriculum or {}
        total = self._observation_noise_total_ticks or 1
        fraction = float(spec.get("peak_fraction", 0.4))
        peak_tick = max(1.0, fraction * total)
        progress = float(np.clip(float(tick) / peak_tick, 0.0, 1.0))
        initial = float(spec.get("initial_level", 0.0))
        final = float(spec.get("final_level", 1.0))
        return float(initial + (final - initial) * progress)

    def _set_observation_noise_level(self, level: float) -> None:
        value = float(np.clip(level, 0.0, 1.0))
        setter = getattr(self.task_definition, "set_observation_noise_level", None)
        if callable(setter):
            setter(value)
        self._observation_noise_level = value

    def _advance_observation_noise_curriculum(self) -> None:
        if self._observation_noise_total_ticks is None:
            return
        self._observation_noise_tick += 1
        self._set_observation_noise_level(
            self._curriculum_level(self._observation_noise_tick)
        )

    @property
    def domain_randomization_progress(self) -> float:
        return float(self._domain_randomization_progress)

    def configure_domain_randomization_curriculum(
        self, *, total_policy_ticks: int, start_policy_tick: int = 0
    ) -> None:
        """Configure reset-randomization progress in policy-tick units."""

        if not callable(self._domain_randomization_progress_setter):
            return
        total = int(total_policy_ticks)
        if total < 1:
            raise ValueError("total_policy_ticks must be positive")
        start = max(0, min(int(start_policy_tick), total))
        self._domain_randomization_total_ticks = total
        self._domain_randomization_tick = start
        self._set_domain_randomization_progress(start)

    def _set_domain_randomization_progress(self, tick: int) -> None:
        total = self._domain_randomization_total_ticks
        if total is None:
            return
        progress = float(np.clip(float(tick) / float(total), 0.0, 1.0))
        setter = self._domain_randomization_progress_setter
        if callable(setter):
            setter(progress)
        self._domain_randomization_progress = progress

    def _advance_domain_randomization_curriculum(self) -> None:
        if self._domain_randomization_total_ticks is None:
            return
        self._domain_randomization_tick += 1
        self._set_domain_randomization_progress(self._domain_randomization_tick)

    def reset(
        self,
        *,
        seed: int | Sequence[int | None] | None = None,
        options: dict[str, Any] | None = None,
        mask: np.ndarray | None = None,
    ) -> BatchTaskResetResult:
        del options
        reset_mask = self._normalize_reset_mask(mask)
        seeds = self._normalize_seeds(seed)
        sample = _sample_batch_reset(
            reset_sampler=self.reset_sampler,
            compiled_scene=self.compiled_scene,
            initial_state=self.initial_state,
            num_envs=self.num_envs,
            rng=self._rng,
            seeds=seeds,
        )
        if len(sample.seeds) != self.num_envs or len(sample.parameters) != self.num_envs:
            raise ValueError("batch reset sample must contain one entry per slot")
        on_reset_sample = getattr(self.task_definition, "on_reset_sample", None)
        if callable(on_reset_sample):
            on_reset_sample(
                parameters=sample.parameters,
                seeds=sample.seeds,
                reset_mask=reset_mask,
            )
        world_randomization = build_world_randomization_batch(
            sample.parameters,
            reset_mask=reset_mask,
        )
        if world_randomization is not None:
            apply_randomization = self._require_world_randomization()
            apply_randomization(
                payload=world_randomization,
                mask=reset_mask,
            )
        result = self.runtime.reset(state=sample.state, mask=reset_mask)
        reset_batch = getattr(
            getattr(self, "action_adapter", None), "reset_batch", None
        )
        if callable(reset_batch):
            reset_batch(as_task_state_view(result.state), reset_mask)
        self._elapsed_steps[reset_mask] = 0
        state = as_task_state_view(result.state)
        reset_evaluation = self.reset_task(
            state=state,
            reset_mask=reset_mask,
        )
        if not isinstance(reset_evaluation, BatchTaskEvaluation):
            raise TypeError("batch reset semantics must return TaskBatchEvaluation")
        self._last_state = state
        self._last_device_state = None
        if self._device_elapsed_steps is not None:
            import torch

            mask_tensor = torch.as_tensor(
                reset_mask,
                dtype=torch.bool,
                device=self._device_elapsed_steps.device,
            )
            self._device_elapsed_steps.masked_fill_(mask_tensor, 0)
        observation = self._build_observation(state)
        infos = self._build_reset_infos(sample, reset_mask)
        return BatchTaskResetResult(observation=observation, infos=infos)

    def step(self, actions: Any) -> BatchTaskStepResult:
        if self._last_state is None:
            raise RuntimeError("batch reset() must be called before step()")
        external_action = self._prepare_external_action(actions)
        control = self._convert_action(external_action, self._last_state)
        result = self.runtime.step(control)
        self._elapsed_steps += 1
        state = as_task_state_view(result.state)
        evaluation = self.evaluate_task(
            state=state,
            action=external_action,
            elapsed_steps=self._elapsed_steps.copy(),
            previous_state=self._last_state,
        )
        if not isinstance(evaluation, BatchTaskEvaluation):
            raise TypeError("batch step semantics must return TaskBatchEvaluation")
        self._last_state = state
        self._advance_observation_noise_curriculum()
        self._advance_domain_randomization_curriculum()
        observation = self._build_observation(state)
        terminated, truncated = self.resolve_batch_done(
            evaluation,
            self._elapsed_steps,
        )
        infos = self._build_step_infos(external_action, evaluation)
        return BatchTaskStepResult(
            observation=observation,
            reward=np.asarray(evaluation.reward, dtype=np.float32),
            terminated=terminated.astype(np.bool_, copy=False),
            truncated=truncated.astype(np.bool_, copy=False),
            infos=infos,
        )

    def step_device(self, actions: Any) -> DeviceBatchTransition:
        """Run one public tick through an explicitly implemented device path.

        This method is intentionally capability-gated.  It never converts a
        tensor to NumPy as a hidden fallback: a task must provide a device
        action converter and device observation/evaluation semantics, while
        the runtime must expose ``step_device``.  Tasks without these hooks
        continue to use the existing Gym/SB3 NumPy route.
        """

        if self._last_state is None:
            raise RuntimeError("batch reset() must be called before step_device()")
        if not self.device_field_plan.available:
            raise StageUnavailableError(
                "device transition is unavailable; missing explicit capability: "
                + ", ".join(self.device_field_plan.reasons)
            )
        profile = self._profile_collector
        if profile is not None:
            profile.begin("bridge_input")
        try:
            device_before = self._device_runtime_read(self._device_state_fields)
            device_before = _validate_device_state_fields(
                device_before,
                names=self._device_state_fields,
                num_envs=self.num_envs,
                device=self.device_field_plan.device,
                phase="runtime.read_device_state()",
            )
            control = self._device_action_converter(actions, device_before)
        finally:
            if profile is not None:
                profile.end("bridge_input")
        if profile is not None:
            profile.begin("runtime_transition")
        try:
            device_state = self._device_runtime_step(control)
        finally:
            if profile is not None:
                profile.end("runtime_transition")
        device_state = _validate_device_state_fields(
            device_state,
            names=self._device_state_fields,
            num_envs=self.num_envs,
            device=self.device_field_plan.device,
            phase="runtime.step_device()",
        )
        import torch

        state_device = str(device_state.device)
        if (
            self._device_elapsed_steps is None
            or tuple(self._device_elapsed_steps.shape) != (self.num_envs,)
            or str(self._device_elapsed_steps.device) != state_device
        ):
            self._device_elapsed_steps = torch.zeros(
                (self.num_envs,), dtype=torch.int32, device=state_device
            )
        self._device_elapsed_steps.add_(1)
        if profile is not None:
            profile.begin("task_evaluation")
        try:
            evaluation = self._device_evaluator(
                state=device_state,
                action=actions,
                elapsed_steps=self._device_elapsed_steps,
                previous_state=self._last_device_state or device_before,
            )
        finally:
            if profile is not None:
                profile.end("task_evaluation")
        required = ("reward", "terminated", "truncated")
        if not isinstance(evaluation, Mapping) or any(name not in evaluation for name in required):
            raise TypeError(
                "task.evaluate_device() must return a mapping with reward, terminated and truncated"
            )
        if profile is not None:
            profile.begin("task_observation")
        try:
            self._advance_observation_noise_curriculum()
            self._advance_domain_randomization_curriculum()
            observation = self._device_observation_builder(device_state)
        finally:
            if profile is not None:
                profile.end("task_observation")
        reward = evaluation["reward"]
        terminated = evaluation["terminated"]
        truncated = evaluation["truncated"]
        # Horizon semantics belong to the common lifecycle, not to a private
        # task evaluator.  Device tasks may report an earlier semantic
        # truncation, but the resolved public horizon must always be applied
        # at the same boundary as the NumPy path.
        if profile is not None:
            profile.begin("bridge_output")
        try:
            horizon = torch.as_tensor(
                self._device_elapsed_steps >= self.horizon,
                dtype=torch.bool,
                device=state_device,
            )
            truncated = torch.logical_or(
                truncated if hasattr(truncated, "device") else torch.as_tensor(truncated, device=state_device),
                horizon,
            )
            self._last_device_state = device_state
            transition_infos = evaluation.get("infos")
            if transition_infos is None:
                # Metrics and reward terms are named learner evidence, not part
                # of the observation/state contract.  Keep them on-device and
                # let an optional evaluator consume them without forcing a
                # NumPy conversion in the lifecycle.
                transition_infos = {
                    "metrics": evaluation.get("metrics", {}),
                    "reward_terms": evaluation.get("reward_terms", {}),
                }
            return DeviceBatchTransition(
                observation=observation,
                reward=reward,
                terminated=terminated,
                truncated=truncated,
                infos=transition_infos,
                device=device_state.device,
            )
        finally:
            if profile is not None:
                profile.end("bridge_output")

    def read_device_state(self, names: tuple[str, ...]):
        if not callable(self._device_runtime_read):
            raise StageUnavailableError("runtime has no public read_device_state capability")
        requested = tuple(str(name) for name in names)
        return self._device_runtime_read(requested)

    @property
    def has_privileged_observation(self) -> bool:
        """Whether this task exposes a learner-only critic observation."""

        return callable(self._privileged_observation_builder) and callable(
            self._device_privileged_observation_builder
        )

    def privileged_observation_manifest(self) -> Mapping[str, Any] | None:
        """Return the task-owned critic observation description, if declared."""

        provider = getattr(self.task_definition, "privileged_observation_manifest", None)
        if not callable(provider):
            return None
        value = provider()
        if not isinstance(value, Mapping):
            raise TypeError("privileged_observation_manifest() must return a mapping")
        return dict(value)

    def get_privileged_observation(self) -> np.ndarray:
        """Build the critic-only observation from the current host state."""

        if not callable(self._privileged_observation_builder):
            raise StageUnavailableError(
                "task does not expose a host privileged observation capability"
            )
        if self._last_state is None:
            raise RuntimeError("batch reset() must be called before reading privileged observation")
        value = np.asarray(
            self._privileged_observation_builder(as_task_state_view(self._last_state)),
            dtype=np.float32,
        )
        expected = (self.num_envs, value.shape[-1]) if value.ndim == 2 else None
        if expected is None or value.shape != expected:
            raise ValueError(
                "privileged observation must have shape (num_envs, features), "
                f"got {value.shape}"
            )
        if not np.isfinite(value).all():
            raise ValueError("privileged observation must be finite")
        return value

    def get_privileged_observation_device(self):
        """Build the critic-only observation from the current device state."""

        if not callable(self._device_privileged_observation_builder):
            raise StageUnavailableError(
                "task does not expose a device privileged observation capability"
            )
        if self._last_device_state is None:
            raise RuntimeError(
                "device transition must run before reading device privileged observation"
            )
        value = self._device_privileged_observation_builder(self._last_device_state)
        if not hasattr(value, "shape") or tuple(value.shape[:1]) != (self.num_envs,):
            raise ValueError(
                "device privileged observation must have leading shape (num_envs,), "
                f"got {getattr(value, 'shape', None)}"
            )
        if not hasattr(value, "device"):
            raise TypeError("device privileged observation must be a device tensor")
        return value

    def prepare_device_reset_selection(self, mask: Any) -> DeviceResetSelection:
        """Normalize and read back one autoreset mask exactly once."""

        import torch

        device_plan = getattr(self, "device_field_plan", None)
        device = getattr(device_plan, "device", None)
        if device is None and self._last_device_state is not None:
            device = self._last_device_state.device
        if device is None:
            raise StageUnavailableError(
                "device autoreset requires a resolved runtime device"
            )
        device_mask = mask if isinstance(mask, torch.Tensor) else torch.as_tensor(mask)
        device_mask = device_mask.to(device=device, dtype=torch.bool)
        if tuple(device_mask.shape) != (self.num_envs,):
            raise ValueError(f"device reset mask must have shape ({self.num_envs},)")
        host_mask = device_mask.detach().to("cpu").numpy()
        selected_slots = np.flatnonzero(host_mask).astype(np.int64, copy=False)
        return DeviceResetSelection(
            device_mask=device_mask,
            host_mask=host_mask,
            selected_slots=selected_slots,
            selected_count=int(selected_slots.size),
            num_envs=self.num_envs,
            device=str(device_mask.device),
        )

    def reset_device(
        self,
        state: Mapping[str, Any],
        mask: Any,
        *,
        selection: DeviceResetSelection | None = None,
    ):
        if not callable(self._device_runtime_reset):
            raise StageUnavailableError("runtime has no public reset_device capability")
        if selection is not None and _accepts_keyword(
            self._device_runtime_reset,
            "selection",
        ):
            result = self._device_runtime_reset(state, mask, selection=selection)
        else:
            result = self._device_runtime_reset(state, mask)
        plan = getattr(self, "device_field_plan", None)
        if plan is not None and bool(getattr(plan, "available", False)):
            result = _validate_device_state_fields(
                result,
                names=tuple(plan.state_readback_fields),
                num_envs=self.num_envs,
                device=plan.device,
                phase="runtime.reset_device()",
            )
        elif not isinstance(result, DeviceBatchState):
            raise TypeError(
                "runtime.reset_device() must return DeviceBatchState; "
                f"got {type(result).__name__}"
            )
        reset_device_batch = getattr(
            getattr(self, "action_adapter", None), "reset_device_batch", None
        )
        if callable(reset_device_batch):
            reset_device_batch(result, mask)
        if callable(self._device_task_reset):
            task_kwargs = {"state": result, "reset_mask": mask}
            if selection is not None and _accepts_keyword(
                self._device_task_reset,
                "selection",
            ):
                task_kwargs["selection"] = selection
            self._device_task_reset(**task_kwargs)
        if self._device_elapsed_steps is not None:
            import torch

            mask_tensor = mask if hasattr(mask, "device") else torch.as_tensor(
                mask,
                dtype=torch.bool,
                device=self._device_elapsed_steps.device,
            )
            mask_tensor = mask_tensor.to(
                device=self._device_elapsed_steps.device,
                dtype=torch.bool,
            )
            self._device_elapsed_steps.masked_fill_(mask_tensor, 0)
        self._last_device_state = result
        return result

    def reset_device_from_mask(
        self,
        mask: Any,
        *,
        selection: DeviceResetSelection | None = None,
    ) -> DeviceBatchResetResult:
        """Sample and apply an autoreset without reading the live state back.

        Reset sampling is intentionally still a host-side boundary operation:
        the public sampler returns NumPy values and task metadata.  The live
        physics state never crosses that boundary.  Sampled values are copied
        once to the runtime device, then ``reset_device`` performs a masked
        in-place reset and the observation is built directly from device state.
        """

        if not callable(self._device_runtime_reset):
            raise StageUnavailableError("runtime has no public reset_device capability")
        if not callable(self._device_observation_builder):
            raise StageUnavailableError("task has no device observation capability")
        import torch

        if selection is None:
            selection = self.prepare_device_reset_selection(mask)
            reset_mask = selection.device_mask
        elif not isinstance(selection, DeviceResetSelection):
            raise TypeError("selection must be a DeviceResetSelection")
        else:
            reset_mask = mask
            expected_device = (
                getattr(getattr(self, "device_field_plan", None), "device", None)
                or (
                    self._last_device_state.device
                    if self._last_device_state is not None
                    else None
                )
            )
            if expected_device is None:
                expected_device = selection.device
            runtime_validator = getattr(
                self,
                "_device_runtime_reset_validator",
                None,
            ) or getattr(
                self.runtime,
                "validate_device_reset_selection",
                None,
            )
            if callable(runtime_validator):
                runtime_validator(reset_mask, selection)
            else:
                validate_device_reset_selection(
                    selection,
                    mask=reset_mask,
                    num_envs=self.num_envs,
                    device=str(expected_device),
                    require_data_pointer=True,
                )
        reset_mask_np = selection.host_mask
        selected_slots = selection.selected_slots
        device = selection.device
        sample = _sample_batch_reset(
            reset_sampler=self.reset_sampler,
            compiled_scene=self.compiled_scene,
            initial_state=self.initial_state,
            num_envs=int(selected_slots.size),
            rng=self._rng,
            seeds=None,
        )
        if len(sample.seeds) != selected_slots.size or len(sample.parameters) != selected_slots.size:
            raise ValueError("device reset sample must contain one entry per selected slot")
        on_reset_sample = getattr(self.task_definition, "on_reset_sample", None)
        if callable(on_reset_sample):
            on_reset_sample(
                parameters=sample.parameters,
                seeds=sample.seeds,
                reset_mask=reset_mask_np,
            )
        world_randomization = build_world_randomization_batch(
            sample.parameters,
            reset_mask=reset_mask_np,
        )
        if world_randomization is not None:
            apply_randomization = self._require_world_randomization()
            apply_randomization(
                payload=world_randomization,
                mask=reset_mask_np,
            )
        reference_arrays = (
            self._last_device_state.arrays
            if self._last_device_state is not None
            else {}
        )
        device_state_payload = {
            name: torch.as_tensor(
                value,
                dtype=getattr(reference_arrays.get(name), "dtype", torch.float32),
                device=device,
            )
            for name, value in sample.state.items()
        }
        result = self.reset_device(
            device_state_payload,
            reset_mask,
            selection=selection,
        )
        self._elapsed_steps[reset_mask_np] = 0
        observation = self._device_observation_builder(result)
        return DeviceBatchResetResult(
            state=result,
            observation=observation,
            device=result.device,
            infos=None,
        )

    def resource_summary(self) -> dict[str, Any]:
        summary = dict(self.runtime.resource_summary())
        summary["device_field_plan"] = self.device_field_plan.as_dict()
        return summary

    def close(self) -> None:
        provider = self.parallel_render_provider
        if provider is not None:
            close_provider = getattr(provider, "close", None)
            if callable(close_provider):
                close_provider()
        self.runtime.close()

    def _normalize_reset_mask(self, mask: np.ndarray | None) -> np.ndarray:
        if mask is None:
            return np.ones(self.num_envs, dtype=np.bool_)
        value = np.asarray(mask, dtype=np.bool_)
        if value.shape != (self.num_envs,):
            raise ValueError("reset mask must have shape (B,)")
        return value

    def _normalize_seeds(
        self,
        seed: int | Sequence[int | None] | None,
    ) -> list[int | None] | None:
        if seed is None:
            return None
        if isinstance(seed, (int, np.integer)):
            return [int(seed) + slot for slot in range(self.num_envs)]
        values = [None if value is None else int(value) for value in seed]
        if len(values) != self.num_envs:
            raise ValueError("explicit vector seeds must have length B")
        return values

    def _prepare_external_action(self, actions: Any) -> Any:
        if isinstance(actions, Mapping):
            return {
                str(name): np.asarray(value, dtype=np.float32)
                for name, value in actions.items()
            }
        return np.asarray(actions, dtype=np.float32)

    def _convert_action(self, action: Any, state: Any) -> np.ndarray:
        if self.action_adapter is None:
            control = action
        else:
            convert_batch = getattr(self.action_adapter, "convert_batch", None)
            if not callable(convert_batch):
                raise StageUnavailableError(
                    f"action adapter {type(self.action_adapter).__name__} has no "
                    "batch-native conversion"
                )
            control = convert_batch(action, state)
        value = np.asarray(control, dtype=np.float32)
        if not np.isfinite(value).all():
            raise ValueError("batch action conversion produced non-finite control")
        return value

    def _build_observation(self, state: Any) -> Any:
        return self.build_observation(state)

    def _build_reset_infos(
        self,
        sample: BatchResetSample,
        reset_mask: np.ndarray,
    ) -> list[dict[str, Any]]:
        return [
            {
                "seed": sample.seeds[slot] if reset_mask[slot] else None,
                "reset_parameters": (
                    dict(sample.parameters[slot]) if reset_mask[slot] else {}
                ),
                "task_uid": self.uid,
                "vector_slot": slot,
                "reset_applied": bool(reset_mask[slot]),
                "batch_schema_version": self.metadata.get(
                    "batch_schema_version", ""
                ),
                "observation_noise_level": self.observation_noise_level,
            }
            for slot in range(self.num_envs)
        ]

    def _build_step_infos(
        self,
        action: Any,
        evaluation: BatchTaskEvaluation,
    ) -> list[dict[str, Any]]:
        infos: list[dict[str, Any]] = []
        for slot in range(self.num_envs):
            slot_action = tree_index(action, slot)
            infos.append(
                {
                    "is_success": bool(evaluation.success[slot]),
                    "task_reward": float(evaluation.reward[slot]),
                    "task_failure": bool(evaluation.failure[slot]),
                    "task_metrics": {
                        name: self._slot_metric(name, values, slot)
                        for name, values in evaluation.metrics.items()
                    },
                    "reward_terms": {
                        name: float(np.asarray(values)[slot])
                        for name, values in evaluation.reward_terms.items()
                    },
                    "task_uid": self.uid,
                    "vector_slot": slot,
                    "batch_schema_version": self.metadata.get(
                        "batch_schema_version", ""
                    ),
                    "observation_noise_level": self.observation_noise_level,
                    "external_action": slot_action,
                    "universal_action": slot_action,
                }
            )
        return infos

    @staticmethod
    def _slot_metric(name: str, values: Any, slot: int) -> Any:
        value = np.asarray(values)
        item = value[slot]
        if value.dtype == np.bool_:
            return bool(item)
        if name in {"upright_steps", "elapsed_steps"}:
            return int(item)
        return float(item)

    def _validate_evaluation(self, evaluation: BatchTaskEvaluation) -> None:
        self.validate_batch_evaluation(evaluation, self.num_envs)


# Compatibility name for Stage 13 callers.  New framework code should use the
# architecture name, which makes the scalar/batch lifecycle boundary explicit.
TaskLifecycleAdapter = BatchTaskLifecycleAdapter
BatchTaskDefinitionBase = BatchTaskLifecycleAdapter


__all__ = [
    "BatchTaskDefinitionBase",
    "BatchTaskLifecycleAdapter",
    "TaskLifecycleAdapter",
]
