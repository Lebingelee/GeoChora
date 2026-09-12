"""Duck-typed RSL-RL 5.x VecEnv adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from ..contracts import LearnerTensorContract
from ._private_extras import (
    DEVICE_RESET_SELECTION_CONTRACT_KEY,
    DEVICE_RESET_SELECTION_CONTRACT_VALUE,
    DEVICE_RESET_SELECTION_EXTRAS_KEY,
)
from .action_transform import (
    RslActionTransformSpec,
    RslLearnerProfile,
    RslObservationProfile,
    resolve_action_profile,
)
from ...runtime.device_plan import admit_runtime_port


class TaskEnvRslVecAdapter:
    """Expose a homogeneous TaskEnv to the current RSL-RL runner."""

    def __init__(
        self,
        env: Any,
        *,
        contract: LearnerTensorContract | None = None,
        device: str = "cpu",
        transfer_mode: str = "host_numpy",
        action_profile: str | RslActionTransformSpec | Mapping[str, Any] | None = None,
        observation_profile: RslObservationProfile | Mapping[str, Any] | None = None,
    ) -> None:
        self.env = env
        self.num_envs = int(env.num_envs)
        self.single_observation_space = (
            env.single_observation_space
            if hasattr(env, "single_observation_space")
            else env.observation_space
        )
        self.single_action_space = (
            env.single_action_space
            if hasattr(env, "single_action_space")
            else env.action_space
        )
        self.contract = contract or LearnerTensorContract.from_spaces(
            self.single_observation_space,
            self.single_action_space,
        )
        self.device = str(device)
        self.transfer_mode = str(transfer_mode)
        if isinstance(action_profile, RslLearnerProfile):
            learner_profile = action_profile
            self.action_transform = learner_profile.action
            resolved_observation_profile = learner_profile.observation
        else:
            self.action_transform = resolve_action_profile(action_profile)
            resolved_observation_profile = RslObservationProfile.from_mapping(
                observation_profile
            )
        self.observation_profile = resolved_observation_profile
        self.actor_observation_groups = tuple(self.observation_profile.actor_groups)
        self.critic_observation_groups = tuple(self.observation_profile.critic_groups)
        privileged_groups = self.observation_profile.privileged_groups
        if len(privileged_groups) > 1:
            raise ValueError(
                "RSL learner profiles currently support one privileged critic group"
            )
        self.privileged_observation_group = privileged_groups[0] if privileged_groups else None
        if self.privileged_observation_group is not None:
            if not bool(getattr(env, "has_privileged_observation", False)):
                raise RuntimeError(
                    "the selected RSL learner profile requires a privileged critic "
                    f"group {self.privileged_observation_group!r}, but the environment "
                    "does not declare that capability"
                )
            if not callable(getattr(env, "get_privileged_observation", None)) or not callable(
                getattr(env, "get_privileged_observation_device", None)
            ):
                raise RuntimeError(
                    "privileged critic profile requires host and device observation builders"
                )
        if self.transfer_mode not in {"host_numpy", "device"}:
            raise ValueError("RSL transfer_mode must be host_numpy or device")
        if self.transfer_mode == "device":
            metadata = getattr(env, "metadata", {})
            cached_summary = (
                metadata.get("runtime_resource_summary")
                if isinstance(metadata, Mapping)
                else None
            )
            if not isinstance(cached_summary, Mapping):
                summary_getter = getattr(env, "resource_summary", None)
                cached_summary = (
                    summary_getter() if callable(summary_getter) else None
                )
            admission = admit_runtime_port(
                runtime=env,
                summary=cached_summary if isinstance(cached_summary, Mapping) else None,
                execution=(
                    metadata.get("execution", "local")
                    if isinstance(metadata, Mapping)
                    else "local"
                ),
                requested_transfer_mode="device",
            )
            if not admission.device_available:
                raise RuntimeError(
                    "device transfer requested but runtime_resource_summary "
                    "does not confirm a complete local device transition: "
                    + ", ".join(admission.device_reasons)
                )
        self.num_actions = self.contract.action_dim
        self.max_episode_length = int(
            getattr(env, "horizon", 0)
            or getattr(env, "metadata", {}).get("horizon", 0)
            or getattr(getattr(env, "_task_spec", None), "horizon", 0)
        )
        if self.max_episode_length < 1:
            raise ValueError("wrapped TaskEnv must expose a positive horizon")
        self.cfg: dict[str, Any] = {
            "learner_contract": self.contract.manifest(),
            "transfer_mode": self.transfer_mode,
            "sim_device": getattr(env, "backend", "unknown"),
            "rl_device": self.device,
            "rsl_api_version": "current_5",
            "action_profile": self.action_transform.manifest(),
            "observation_profile": self.observation_profile.manifest(),
        }
        self._episode_length_np = np.zeros(self.num_envs, dtype=np.int64)
        self._observation_np: np.ndarray | None = None
        self._observation_tensor: Any = None
        # Device transitions normally carry named metric tensors rather than
        # per-world Python info payloads.  Keep the empty vector container
        # stable and materialize a fresh list only on terminal/reset ticks.
        self._device_empty_infos = [{} for _ in range(self.num_envs)]
        self._action_low: Any = None
        self._action_high: Any = None
        if hasattr(self.single_action_space, "low") and hasattr(self.single_action_space, "high"):
            torch = self._torch()
            self._action_low = torch.as_tensor(
                self.single_action_space.low,
                dtype=torch.float32,
                device=self.device,
            )
            self._action_high = torch.as_tensor(
                self.single_action_space.high,
                dtype=torch.float32,
                device=self.device,
            )
        self._reset()

        # Tensor is imported lazily so importing task_env.alg is dependency safe.
        torch = self._torch()
        self.episode_length_buf = torch.zeros(
            self.num_envs, dtype=torch.long, device=self.device
        )

    @staticmethod
    def _torch():
        try:
            import torch
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("RSL-RL integration requires PyTorch") from exc
        return torch

    def _to_tensor_dict(
        self,
        observation: np.ndarray,
        privileged_observation: np.ndarray | None = None,
    ) -> Any:
        torch = self._torch()
        tensor = torch.as_tensor(observation, dtype=torch.float32, device=self.device)
        try:
            from tensordict import TensorDict
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("RSL-RL integration requires tensordict") from exc
        values: dict[str, Any] = {self.contract.observation_group: tensor}
        if privileged_observation is not None:
            if self.privileged_observation_group is None:
                raise ValueError("received privileged observation without a profile group")
            privileged = torch.as_tensor(
                privileged_observation, dtype=torch.float32, device=self.device
            )
            values[self.privileged_observation_group] = privileged
        return TensorDict(
            values,
            batch_size=[self.num_envs],
            device=tensor.device,
        )

    def _host_privileged_observation(self) -> np.ndarray | None:
        if self.privileged_observation_group is None:
            return None
        value = np.asarray(self.env.get_privileged_observation(), dtype=np.float32)
        if value.ndim != 2 or value.shape[0] != self.num_envs or not np.isfinite(value).all():
            raise ValueError(
                "host privileged observation must be finite with shape (num_envs, features)"
            )
        return value

    def _device_privileged_observation(self, torch: Any) -> Any:
        if self.privileged_observation_group is None:
            return None
        value = self.env.get_privileged_observation_device()
        if not hasattr(value, "shape") or tuple(value.shape[:1]) != (self.num_envs,):
            raise ValueError("device privileged observation has an invalid batch shape")
        return value.to(device=self.device, dtype=torch.float32)

    def _with_device_privileged_observation(self, observation: Any, torch: Any) -> Any:
        if self.privileged_observation_group is None:
            return observation
        values = {str(key): observation[key] for key in observation.keys()}
        values[self.privileged_observation_group] = self._device_privileged_observation(torch)
        return type(observation)(
            values,
            batch_size=[self.num_envs],
            device=observation.device,
        )

    def _reset(self, seed: Any = None) -> None:
        result = self.env.reset(seed=seed) if seed is not None else self.env.reset()
        if hasattr(result, "observation"):
            observation = result.observation
        elif isinstance(result, tuple):
            observation = result[0]
        else:
            observation = result
        self._observation_np = self.contract.flatten_observation(observation, self.num_envs)
        self._observation_tensor = self._to_tensor_dict(
            self._observation_np,
            self._host_privileged_observation(),
        )
        self._episode_length_np.fill(0)

    def get_observations(self) -> Any:
        if self._observation_tensor is None:
            raise RuntimeError("RSL adapter has no current observation; reset required")
        return self._observation_tensor

    def _format_step(self, rewards, dones, extras: dict[str, Any]):
        """Return the current RSL-RL transition tuple."""

        torch = self._torch()
        return (
            self._observation_tensor,
            torch.as_tensor(rewards, dtype=torch.float32, device=self.device),
            torch.as_tensor(dones, dtype=torch.bool, device=self.device),
            extras,
        )

    def _masked_reset(self, mask: np.ndarray) -> Any:
        """Reset done slots through either raw or SB3-wrapped vector boundary."""

        import inspect

        reset = getattr(self.env, "reset", None)
        try:
            accepts_mask = "mask" in inspect.signature(reset).parameters
        except (TypeError, ValueError):
            accepts_mask = False
        if accepts_mask:
            return reset(mask=mask)
        # ``make_parallel_env(..., execution='local')`` returns the SB3
        # adapter, whose public reset intentionally follows VecEnv and has no
        # mask argument.  The additive device bridge may unwrap exactly one
        # local layer for an explicit masked reset; remote environments do not
        # expose this device path.
        inner = getattr(self.env, "env", None)
        if inner is None or not callable(getattr(inner, "reset", None)):
            raise TypeError("wrapped vector environment has no masked reset capability")
        result = inner.reset(mask=mask)
        if hasattr(self.env, "_last_observation"):
            observation = result.observation if hasattr(result, "observation") else result[0]
            self.env._last_observation = observation
        if hasattr(self.env, "reset_infos"):
            infos = result.infos if hasattr(result, "infos") else result[1]
            self.env.reset_infos = infos
        return result

    def _clip_policy_action(self, action: Any) -> Any:
        """Apply declared flat Box bounds at the learner boundary.

        RSL policies sample an unconstrained Gaussian.  Gym action spaces are
        the authoritative contract, so clipping happens once per policy tick
        before the raw vector environment; physics substeps never see an
        unbounded action.  Structured spaces remain task-owned and are not
        guessed here.
        """

        if self._action_low is None or self._action_high is None:
            return self.action_transform.apply_torch(action)
        try:
            low = self._action_low
            high = self._action_high
            value = action
            if low.dtype != value.dtype:
                low = low.to(dtype=value.dtype)
                high = high.to(dtype=value.dtype)
            return self.action_transform.apply_torch(
                value,
                fallback_low=low,
                fallback_high=high,
            )
        except (AttributeError, TypeError, RuntimeError):
            return action

    def step(self, actions: Any) -> tuple[Any, Any, Any, dict[str, Any]]:
        torch = self._torch()
        if self.transfer_mode == "device":
            return self._step_device(actions, torch)
        action_tensor = actions
        if not hasattr(action_tensor, "detach"):
            action_tensor = torch.as_tensor(action_tensor, dtype=torch.float32, device=self.device)
        action_tensor = self._clip_policy_action(action_tensor)
        action_np = self.contract.validate_flat_action(
            action_tensor.detach().to("cpu").numpy(), self.num_envs
        )
        raw_action = self.contract.unflatten_action(action_np, self.num_envs)
        if callable(getattr(self.env, "step_async", None)):
            self.env.step_async(raw_action)
            result = self.env.step_wait()
        else:
            result = self.env.step(raw_action)
        if hasattr(result, "observation"):
            observation = result.observation
            rewards = np.asarray(result.reward, dtype=np.float32)
            terminated = np.asarray(result.terminated, dtype=np.bool_)
            truncated = np.asarray(result.truncated, dtype=np.bool_)
            infos = list(result.infos)
        elif len(result) == 5:
            observation, rewards, terminated, truncated, raw_infos = result
            rewards = np.asarray(rewards, dtype=np.float32)
            terminated = np.asarray(terminated, dtype=np.bool_)
            truncated = np.asarray(truncated, dtype=np.bool_)
            infos = list(raw_infos)
        elif len(result) == 4:
            observation, rewards, dones, raw_infos = result
            rewards = np.asarray(rewards, dtype=np.float32)
            dones = np.asarray(dones, dtype=np.bool_)
            infos = list(raw_infos)
            truncated = np.asarray(
                [bool(info.get("TimeLimit.truncated", False)) for info in infos],
                dtype=np.bool_,
            )
            terminated = np.logical_and(dones, np.logical_not(truncated))
            # VecEnv implementations already autoreset and return the reset
            # observation.  Do not call reset a second time here.
            self._episode_length_np += 1
            self._episode_length_np[dones] = 0
            terminal_observation = self.contract.flatten_observation(
                observation, self.num_envs
            )
            self._observation_np = terminal_observation
            self._observation_tensor = self._to_tensor_dict(
                terminal_observation,
                self._host_privileged_observation(),
            )
            self.episode_length_buf = self._torch().as_tensor(
                self._episode_length_np,
                dtype=self._torch().long,
                device=self.device,
            )
            return self._format_step(
                rewards,
                dones,
                {
                    "time_outs": self._torch().as_tensor(
                        np.logical_and(truncated, np.logical_not(terminated)),
                        dtype=self._torch().bool,
                        device=self.device,
                    ),
                    "log": {},
                    "infos": infos,
                    "terminated": self._torch().as_tensor(terminated, dtype=self._torch().bool, device=self.device),
                    "truncated": self._torch().as_tensor(truncated, dtype=self._torch().bool, device=self.device),
                },
            )
        else:
            raise TypeError("wrapped vector environment returned an unsupported step result")
        dones = np.logical_or(terminated, truncated)
        self._episode_length_np += 1
        terminal_observation = self.contract.flatten_observation(observation, self.num_envs)

        if np.any(dones):
            reset_result = self._masked_reset(dones)
            if hasattr(reset_result, "observation"):
                reset_observation = reset_result.observation
                reset_infos = reset_result.infos
            else:
                reset_observation, reset_infos = reset_result
            reset_flat = self.contract.flatten_observation(reset_observation, self.num_envs)
            for slot, done in enumerate(dones):
                if done:
                    infos[slot]["terminal_observation"] = terminal_observation[slot].copy()
                    infos[slot]["reset_info"] = reset_infos[slot]
                    terminal_observation[slot] = reset_flat[slot]
            self._episode_length_np[dones] = 0

        self._observation_np = terminal_observation
        self._observation_tensor = self._to_tensor_dict(
            terminal_observation,
            self._host_privileged_observation(),
        )
        self.episode_length_buf = torch.as_tensor(
            self._episode_length_np, dtype=torch.long, device=self.device
        )
        extras: dict[str, Any] = {
            "time_outs": torch.as_tensor(
                np.logical_and(truncated, np.logical_not(terminated)),
                dtype=torch.bool,
                device=self.device,
            ),
            "log": {},
            "infos": infos,
            "terminated": torch.as_tensor(terminated, dtype=torch.bool, device=self.device),
            "truncated": torch.as_tensor(truncated, dtype=torch.bool, device=self.device),
        }
        noise_level = getattr(self.env, "observation_noise_level", None)
        if noise_level is not None and not callable(noise_level):
            extras["observation_noise_level"] = torch.full(
                (self.num_envs,),
                float(noise_level),
                dtype=torch.float32,
                device=self.device,
            )
        return self._format_step(rewards, dones, extras)

    def _step_device(self, actions: Any, torch: Any) -> tuple[Any, Any, Any, dict[str, Any]]:
        """Consume the explicit lifecycle device transition without readback.

        A device-capable lifecycle owns masked reset/autoreset semantics.  The
        bridge therefore only packages named tensors and never calls
        ``to('cpu')`` on the policy action or observation.
        """

        actions = self._clip_policy_action(actions)
        result = self.env.step_device(actions)
        if not hasattr(result, "observation"):
            raise TypeError(
                "device step must return a named transition with observation, "
                "reward, terminated and truncated attributes"
            )
        observation = result.observation
        if not hasattr(observation, "batch_size"):
            try:
                from tensordict import TensorDict
            except ModuleNotFoundError as exc:  # pragma: no cover
                raise RuntimeError("current RSL device transition requires tensordict") from exc
            if not hasattr(observation, "shape") or tuple(observation.shape[:1]) != (self.num_envs,):
                raise ValueError("device observation must expose a leading batch dimension")
            observation = TensorDict(
                {self.contract.observation_group: observation},
                batch_size=[self.num_envs],
                device=observation.device,
            )
        rewards = result.reward
        terminated = result.terminated
        truncated = result.truncated
        self._observation_np = None
        terminated_t = terminated if hasattr(terminated, "device") else torch.as_tensor(
            terminated, dtype=torch.bool, device=self.device
        )
        truncated_t = truncated if hasattr(truncated, "device") else torch.as_tensor(
            truncated, dtype=torch.bool, device=self.device
        )
        rewards_t = rewards if hasattr(rewards, "device") else torch.as_tensor(
            rewards, dtype=torch.float32, device=self.device
        )
        dones_t = torch.logical_or(terminated_t, truncated_t)
        # Keep the per-slot length counter on the learner device.  New device
        # environments materialize one reset selection at this boundary;
        # older environments retain the scalar terminal-probe fallback.
        self.episode_length_buf.add_(1)
        prepare_selection = getattr(
            self.env,
            "prepare_device_reset_selection",
            None,
        )
        if callable(prepare_selection):
            reset_selection = prepare_selection(dones_t)
            has_done = reset_selection.selected_count > 0
        else:
            reset_selection = None
            has_done = bool(torch.any(dones_t).item())
        dones_np = None

        # A device tick is deliberately kept readback-free.  Episode-boundary
        # reset is the one explicit low-frequency host exchange permitted by
        # the public reset-sampler contract: it samples per-world state,
        # writes only the done mask, and returns a reset observation for the
        # same slots.  This mirrors SB3/Gym VecEnv autoreset semantics while
        # keeping physics and reward evaluation device-native between resets.
        raw_infos = getattr(result, "infos", None)
        transition_metrics: Mapping[str, Any] = {}
        transition_reward_terms: Mapping[str, Any] = {}
        if isinstance(raw_infos, Mapping):
            transition_metrics = raw_infos.get("metrics", {}) or {}
            transition_reward_terms = raw_infos.get("reward_terms", {}) or {}
            infos = self._device_empty_infos
        else:
            infos = list(raw_infos or [{} for _ in range(self.num_envs)])
        if len(infos) != self.num_envs:
            raise ValueError("device transition infos must contain one mapping per slot")
        if has_done:
            terminal_observation = observation
            device_resetter = getattr(self.env, "reset_device_from_mask", None)
            if callable(device_resetter):
                # The native reset result currently carries no Python info
                # payload.  Reuse the stable empty container instead of
                # allocating B dictionaries on every terminal tick.
                infos = self._device_empty_infos
                if reset_selection is None:
                    reset_result = device_resetter(dones_t)
                else:
                    reset_result = device_resetter(
                        dones_t,
                        selection=reset_selection,
                    )
                reset_observation = reset_result.observation
                reset_infos = reset_result.infos
                native_device_reset = True
            else:
                infos = [{} for _ in range(self.num_envs)]
                dones_np = np.asarray(dones_t.detach().to("cpu"), dtype=np.bool_)
                reset_result = self._masked_reset(dones_np)
                if hasattr(reset_result, "observation"):
                    reset_observation = reset_result.observation
                    reset_infos = list(reset_result.infos)
                else:
                    reset_observation, reset_infos = reset_result
                    reset_infos = list(reset_infos)
                reset_flat = self.contract.flatten_observation(
                    reset_observation, self.num_envs
                )
                reset_observation = self._to_tensor_dict(reset_flat)
                native_device_reset = False
            if native_device_reset:
                if hasattr(reset_observation, "batch_size"):
                    observation = reset_observation
                else:
                    observation = type(terminal_observation)(
                        {self.contract.observation_group: reset_observation},
                        batch_size=[self.num_envs],
                        device=reset_observation.device,
                    )
                # Terminal observations are intentionally omitted on this
                # path: materializing them would reintroduce a full device to
                # host copy at every episode boundary.  The learner consumes
                # the named transition tensors above, not SB3 diagnostic
                # payloads.
                if reset_infos is not None:
                    dones_np = (
                        reset_selection.host_mask
                        if reset_selection is not None
                        else np.asarray(dones_t.detach().to("cpu"), dtype=np.bool_)
                    )
                    reset_infos = list(reset_infos)
                    for slot, done in enumerate(dones_np):
                        if done:
                            infos[slot]["reset_info"] = reset_infos[slot]
            else:
                terminal_value = terminal_observation[
                    self.contract.observation_group
                ]
                reset_value = reset_observation[self.contract.observation_group]
                done_view = dones_t.reshape(
                    self.num_envs,
                    *([1] * (terminal_value.ndim - 1)),
                )
                observation = type(terminal_observation)(
                    {
                        self.contract.observation_group: torch.where(
                            done_view,
                            reset_value,
                            terminal_value,
                        )
                    },
                    batch_size=[self.num_envs],
                    device=terminal_value.device,
                )
                for slot, done in enumerate(dones_np):
                    if done:
                        infos[slot]["terminal_observation"] = terminal_observation[self.contract.observation_group][slot].detach().to("cpu").numpy()
                        infos[slot]["reset_info"] = reset_infos[slot]
            self.episode_length_buf.masked_fill_(dones_t, 0)
        add_privileged_observation = getattr(
            self,
            "_with_device_privileged_observation",
            None,
        )
        if callable(add_privileged_observation):
            self._observation_tensor = add_privileged_observation(
                observation, torch
            )
        else:
            # Keep the unbound device-step contract usable with minimal test
            # doubles that intentionally model only the flat-observation path.
            self._observation_tensor = observation
        extras = {
            "time_outs": torch.logical_and(truncated_t, torch.logical_not(terminated_t)),
            "terminated": terminated_t,
            "truncated": truncated_t,
            "log": {},
            "infos": infos,
            "metrics": transition_metrics,
            "reward_terms": transition_reward_terms,
        }
        if reset_selection is not None:
            # Private same-tick evidence for the only supported optimized
            # route: this adapter -> installed RSL-RL 5.x PPO -> our logger.
            # The installed PPO method is read-only on dones (covered by an
            # inference-mode regression).  Any other intermediary must drop
            # both private keys so the logger uses its generic fallback.
            extras[DEVICE_RESET_SELECTION_EXTRAS_KEY] = reset_selection
            extras[DEVICE_RESET_SELECTION_CONTRACT_KEY] = (
                DEVICE_RESET_SELECTION_CONTRACT_VALUE
            )
        noise_level = getattr(self.env, "observation_noise_level", None)
        if noise_level is not None and not callable(noise_level):
            extras["observation_noise_level"] = torch.full(
                (self.num_envs,),
                float(noise_level),
                dtype=torch.float32,
                device=self.device,
            )
        return self._format_step(rewards_t, dones_t, extras)

    def configure_observation_noise_curriculum(
        self, *, total_policy_ticks: int, start_policy_tick: int = 0
    ) -> None:
        """Forward one-time curriculum setup through the public vector edge."""

        configure = getattr(self.env, "configure_observation_noise_curriculum", None)
        if callable(configure):
            configure(
                total_policy_ticks=total_policy_ticks,
                start_policy_tick=start_policy_tick,
            )
            return
        env_method = getattr(self.env, "env_method", None)
        if callable(env_method):
            env_method(
                "configure_observation_noise_curriculum",
                total_policy_ticks=total_policy_ticks,
                start_policy_tick=start_policy_tick,
            )

    def configure_domain_randomization_curriculum(
        self, *, total_policy_ticks: int, start_policy_tick: int = 0
    ) -> None:
        """Forward reset-randomization curriculum setup through the vector edge."""

        configure = getattr(self.env, "configure_domain_randomization_curriculum", None)
        if callable(configure):
            configure(
                total_policy_ticks=total_policy_ticks,
                start_policy_tick=start_policy_tick,
            )
            return
        env_method = getattr(self.env, "env_method", None)
        if callable(env_method):
            env_method(
                "configure_domain_randomization_curriculum",
                total_policy_ticks=total_policy_ticks,
                start_policy_tick=start_policy_tick,
            )

    def close(self) -> None:
        self.env.close()


__all__ = ["TaskEnvRslVecAdapter"]
