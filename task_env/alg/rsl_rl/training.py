"""Current RSL-RL 5.x training assembly and artifact lifecycle.

The learner is task-independent.  Static-template/contact choices are read
from the selected task YAML before the environment is constructed; this layer
never mutates a built runtime or CUDA Graph configuration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import numpy as np

from .action_transform import resolve_learner_profile, resolve_task_action_profile
from .adapter import TaskEnvRslVecAdapter
from .artifacts import (
    install_iteration_metric_capture,
    write_runner_h5_artifact,
)
from .runner import build_runner


@dataclass(frozen=True)
class RslPpoOptions:
    """Validated values for the unified current-RSL training entry point."""

    env_id: str
    num_env: int
    iterations: int
    rollout_steps: int
    seed: int
    sim_device: str
    rl_device: str
    render: bool
    env_config: Path | None
    output_dir: Path
    log_dir: Path | None
    save_interval: int
    checkpoint_out: Path | None
    resume: str | None
    hard_render: bool = False
    hard_render_num: int = 16
    hard_render_bypass_budget: bool = False

    @classmethod
    def from_namespace(cls, args: Any) -> "RslPpoOptions":
        return cls(
            env_id=str(args.env_id),
            num_env=int(args.num_env),
            iterations=int(args.iterations),
            rollout_steps=int(args.rollout_steps),
            seed=int(args.seed),
            sim_device=str(args.sim_device),
            rl_device=str(args.rl_device),
            render=bool(args.render),
            hard_render=bool(getattr(args, "hard_render", False)),
            hard_render_num=int(getattr(args, "hard_render_num", 16)),
            hard_render_bypass_budget=bool(
                getattr(args, "hard_render_bypass_budget", False)
            ),
            env_config=(
                None if getattr(args, "env_config", None) is None else Path(args.env_config)
            ),
            output_dir=Path(args.output_dir),
            log_dir=(
                None if getattr(args, "log_dir", None) is None else Path(args.log_dir)
            ),
            save_interval=int(args.save_interval),
            checkpoint_out=(
                None
                if getattr(args, "checkpoint_out", None) is None
                else Path(args.checkpoint_out)
            ),
            resume=(
                None if getattr(args, "resume", None) is None else str(args.resume)
            ),
        )


@dataclass
class RslTrainingBundle:
    """Raw, learner, and optional headed-render training boundary."""

    raw_env: Any
    learner_env: TaskEnvRslVecAdapter
    training_env: Any
    action_profile: Any
    layout: str
    transfer_mode: str
    execution: str
    render_layout: dict[str, float | int]
    render_settings: Any
    render_controller: Any
    raw_metadata: dict[str, Any]
    resolved_runtime: Mapping[str, Any]
    # Optional for compatibility with lightweight artifact tests and older
    # integrations that construct this boundary directly.  New training
    # bundles always carry the YAML-resolved learner profile.
    learner_profile: Any = None

    def close(self) -> None:
        self.training_env.close()


@dataclass(frozen=True)
class _ResolvedOptions:
    log_dir: Path
    checkpoint_out: Path
    resume_checkpoint: Path | None


_MODEL_PATTERN = re.compile(r"^model_(\d+)\.pt$")


def current5_train_cfg(
    *,
    rollout_steps: int,
    save_interval: int = 50,
    checkpoint_dir: Path | None = None,
    observation_groups: Mapping[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Build the one supported GeoPhys current-5 PPO configuration."""

    return {
        "algorithm": {
            "class_name": "rsl_rl.algorithms:PPO",
            "num_learning_epochs": 5,
            "num_mini_batches": 4,
            "learning_rate": 1.0e-3,
            "clip_param": 0.2,
            "gamma": 0.99,
            "lam": 0.95,
            "entropy_coef": 0.01,
            "value_loss_coef": 1.0,
            "max_grad_norm": 1.0,
            "rnd_cfg": None,
            "symmetry_cfg": None,
        },
        "actor": {
            "class_name": "rsl_rl.models:MLPModel",
            "hidden_dims": [512, 256, 128],
            "activation": "elu",
            "distribution_cfg": {
                "class_name": "rsl_rl.modules:GaussianDistribution",
                "init_std": 1.0,
            },
        },
        "critic": {
            "class_name": "rsl_rl.models:MLPModel",
            "hidden_dims": [512, 256, 128],
            "activation": "elu",
        },
        "obs_groups": {
            "actor": ["policy"],
            "critic": ["policy"],
        }
        if observation_groups is None
        else {
            str(name): [str(group) for group in groups]
            for name, groups in observation_groups.items()
        },
        "num_steps_per_env": int(rollout_steps),
        "save_interval": int(save_interval),
        "multi_gpu": None,
        "empirical_normalization": False,
        "logger": {
            "class_name": "task_env.alg.rsl_rl.artifacts:H5TensorBoardLogWriter",
            **(
                {"checkpoint_dir": str(checkpoint_dir)}
                if checkpoint_dir is not None
                else {}
            ),
        },
        "check_for_nan": True,
    }


def _model_iteration(path: Path) -> int:
    match = _MODEL_PATTERN.match(path.name)
    return int(match.group(1)) if match else -1


def resolve_resume_checkpoint(value: str | None, output_dir: Path) -> Path | None:
    """Resolve a checkpoint file, run directory, or latest-model request."""

    if value is None:
        return None
    requested = str(value)
    if requested == "auto":
        roots = (output_dir, output_dir / "tensorboard")
    else:
        candidate = Path(requested)
        if candidate.is_file():
            return candidate
        roots = (candidate, candidate / "tensorboard") if candidate.is_dir() else ()
    candidates: list[Path] = []
    for root in roots:
        if root.is_dir():
            candidates.extend(
                path for path in root.glob("model_*.pt") if _model_iteration(path) >= 0
            )
    if candidates:
        return max(
            candidates,
            key=lambda path: (_model_iteration(path), path.stat().st_mtime_ns),
        )
    for root in roots:
        final = root / "checkpoint.pt"
        if final.is_file():
            return final
    searched = ", ".join(str(root) for root in roots)
    raise FileNotFoundError(
        "--resume could not find model_*.pt or checkpoint.pt under: "
        f"{searched or requested}"
    )


def _resolve_options(options: RslPpoOptions) -> _ResolvedOptions:
    if not options.env_id.strip():
        raise ValueError("--env-id cannot be empty")
    if options.num_env < 1:
        raise ValueError("--num-env must be positive")
    if options.iterations < 1:
        raise ValueError("--iterations must be positive")
    if options.rollout_steps < 1:
        raise ValueError("--rollout-steps must be positive")
    if options.save_interval < 1:
        raise ValueError("--save-interval must be positive")
    if options.sim_device not in {"cpu", "cuda"}:
        raise ValueError("--sim-device must be cpu or cuda")
    if options.hard_render_num not in {16, 32, 64, 96, 128, 256}:
        raise ValueError(
            "--hard-render-num must be 16, 32, 64, 96, 128 or 256"
        )
    if options.hard_render and options.render:
        raise ValueError("--render and --hard-render are mutually exclusive")
    if options.hard_render_bypass_budget and not options.hard_render:
        raise ValueError("--hard-render-bypass-budget requires --hard-render")
    options.output_dir.mkdir(parents=True, exist_ok=True)
    log_dir = options.log_dir or options.output_dir / "tensorboard"
    checkpoint_out = options.checkpoint_out or options.output_dir / "checkpoint.pt"
    return _ResolvedOptions(
        log_dir=log_dir,
        checkpoint_out=checkpoint_out,
        resume_checkpoint=resolve_resume_checkpoint(options.resume, options.output_dir),
    )


def _resolved_runtime(raw_env: Any) -> Mapping[str, Any]:
    record = raw_env.get_record_metadata()
    resolved_config = record.get("resolved_config", {})
    if not isinstance(resolved_config, Mapping):
        return {}
    runtime = resolved_config.get("runtime", {})
    return dict(runtime) if isinstance(runtime, Mapping) else {}


def _configure_noise_curriculum(raw_env: Any, options: RslPpoOptions) -> None:
    configure = getattr(raw_env, "configure_observation_noise_curriculum", None)
    if not callable(configure):
        return
    configure(
        total_policy_ticks=max(1, int(options.iterations) * int(options.rollout_steps)),
        start_policy_tick=0,
    )


def _configure_domain_randomization_curriculum(
    raw_env: Any, options: RslPpoOptions
) -> None:
    configure = getattr(raw_env, "configure_domain_randomization_curriculum", None)
    if not callable(configure):
        return
    configure(
        total_policy_ticks=max(1, int(options.iterations) * int(options.rollout_steps)),
        start_policy_tick=0,
    )


def _build_bundle(
    options: RslPpoOptions,
    resolved: _ResolvedOptions,
) -> RslTrainingBundle:
    from task_env import make_parallel_env
    from task_env.environment.configuration import load_yaml_mapping
    from task_env.runtime.device_plan import admit_runtime_port
    from task_env.render import (
        TrainingRenderController,
        TrainingRenderKeyMap,
        TrainingRenderVecAdapter,
        resolve_training_render_settings,
    )

    env_config: dict[str, Any] = (
        dict(load_yaml_mapping(options.env_config))
        if options.env_config is not None
        else {}
    )
    configured_runtime = env_config.get("runtime", {})
    if not isinstance(configured_runtime, Mapping):
        raise ValueError("--env-config runtime section must be a mapping")
    env_config["base_seed"] = options.seed

    # Current RSL's device adapter requires a same-process vector runtime.
    # This is a learner integration invariant, not an exposed simulation
    # option.  Transfer selection below is capability-based rather than a
    # task-id exception, so unsupported environments do not silently change
    # their authored runtime configuration.
    raw_env = make_parallel_env(
        options.env_id,
        env_config=env_config,
        num_env=options.num_env,
        backend=options.sim_device,
        execution="local",
    )
    raw_metadata = dict(getattr(raw_env, "metadata", {}) or {})
    runtime_config = _resolved_runtime(raw_env)
    layout = str(
        raw_metadata.get(
            "batch_physics_layout", runtime_config.get("batch_physics_layout", "unknown")
        )
    )
    _configure_noise_curriculum(raw_env, options)
    _configure_domain_randomization_curriculum(raw_env, options)

    resource_summary = getattr(raw_env, "resource_summary", None)
    live_summary: Mapping[str, Any] | None = None
    if callable(resource_summary):
        candidate_summary = resource_summary()
        if isinstance(candidate_summary, Mapping):
            live_summary = dict(candidate_summary)
            raw_metadata["runtime_resource_summary"] = dict(live_summary)
            if isinstance(getattr(raw_env, "metadata", None), dict):
                raw_env.metadata["runtime_resource_summary"] = dict(live_summary)
    admission = admit_runtime_port(
        runtime=raw_env,
        summary=live_summary,
        execution="local",
        requested_transfer_mode="device",
    )
    if not admission.host_available:
        raise RuntimeError(
            "parallel environment does not satisfy the host Runtime Port: "
            + ", ".join(admission.host_reasons)
        )
    transfer_mode = admission.transfer_mode

    render_config = _resolved_runtime(raw_env).get("render", {})
    # ``render`` is a sibling of runtime in the resolved record, not part of
    # it.  Retrieve the complete record once for its task-owned render YAML.
    record = raw_env.get_record_metadata()
    resolved_config = record.get("resolved_config", {})
    if isinstance(resolved_config, Mapping):
        render_config = resolved_config.get("render", {})
    if not isinstance(render_config, Mapping):
        render_config = {}
    render_settings = resolve_training_render_settings(
        render_config,
        num_env=options.num_env,
        hard_render=options.hard_render,
        hard_render_num=options.hard_render_num,
    )
    learner_profile = resolve_learner_profile(
        resolve_task_action_profile(options.env_id, config=env_config)
    )
    action_profile = learner_profile.action
    learner_env = TaskEnvRslVecAdapter(
        raw_env,
        device=options.rl_device,
        transfer_mode=transfer_mode,
        action_profile=action_profile,
        observation_profile=learner_profile.observation,
    )
    training_env = learner_env
    render_controller = None
    render_layout = render_settings.layout()
    if options.render or options.hard_render:
        set_hard_render = getattr(raw_env, "set_parallel_render_hard", None)
        if not callable(set_hard_render):
            raise RuntimeError(
                "parallel environment does not expose set_parallel_render_hard()"
            )
        set_hard_render(options.hard_render)
        if options.hard_render_bypass_budget:
            set_budget_bypass = getattr(
                raw_env,
                "set_parallel_render_budget_bypass",
                None,
            )
            if not callable(set_budget_bypass):
                raise RuntimeError(
                    "parallel environment does not expose "
                    "set_parallel_render_budget_bypass()"
                )
            set_budget_bypass(True)
        raw_env.set_parallel_render_layout(**render_layout)
        render_controller = TrainingRenderController(
            raw_env,
            enabled=True,
            render_every=render_settings.render_every,
            render_num=render_settings.render_num,
            keymap=TrainingRenderKeyMap(),
        )
        training_env = TrainingRenderVecAdapter(learner_env, render_controller)
    return RslTrainingBundle(
        raw_env=raw_env,
        learner_env=learner_env,
        training_env=training_env,
        action_profile=action_profile,
        learner_profile=learner_profile,
        layout=layout,
        transfer_mode=transfer_mode,
        execution="local",
        render_layout=render_layout,
        render_settings=render_settings,
        render_controller=render_controller,
        raw_metadata=raw_metadata,
        resolved_runtime=runtime_config,
    )


def _runtime_resource_summary(bundle: RslTrainingBundle) -> Mapping[str, Any] | None:
    summary = getattr(bundle.raw_env, "resource_summary", None)
    if callable(summary):
        value = summary()
        if isinstance(value, Mapping):
            return dict(value)
    value = bundle.raw_metadata.get("runtime_resource_summary")
    return dict(value) if isinstance(value, Mapping) else None


def train(options: RslPpoOptions) -> Path:
    """Run current-5 PPO for one registered homogeneous TaskEnv."""

    resolved = _resolve_options(options)
    import torch
    import tensordict  # noqa: F401  # import before Taichi initialization

    torch.manual_seed(options.seed)
    np.random.seed(options.seed)
    bundle = _build_bundle(options, resolved)
    resume_iteration = None
    try:
        runner = build_runner(
            bundle.training_env,
            current5_train_cfg(
                rollout_steps=options.rollout_steps,
                save_interval=options.save_interval,
                checkpoint_dir=options.output_dir,
                observation_groups={
                    "actor": list(
                        getattr(bundle.learner_env, "actor_observation_groups", ("policy",))
                    ),
                    "critic": list(
                        getattr(bundle.learner_env, "critic_observation_groups", ("policy",))
                    ),
                },
            ),
            log_dir=str(resolved.log_dir),
            device=options.rl_device,
        )
        install_iteration_metric_capture(runner)
        if resolved.resume_checkpoint is not None:
            runner.load(
                str(resolved.resume_checkpoint),
                map_location=options.rl_device,
            )
            loaded_iteration = int(getattr(runner, "current_learning_iteration", -1))
            if loaded_iteration < 0:
                raise RuntimeError(
                    "resume checkpoint did not expose a valid iteration: "
                    f"{resolved.resume_checkpoint}"
                )
            runner.current_learning_iteration = loaded_iteration + 1
            resume_iteration = loaded_iteration
            bundle.learner_env.configure_observation_noise_curriculum(
                total_policy_ticks=max(
                    1,
                    int(runner.current_learning_iteration + options.iterations)
                    * int(options.rollout_steps),
                ),
                start_policy_tick=int(runner.current_learning_iteration)
                * int(options.rollout_steps),
            )
            bundle.learner_env.configure_domain_randomization_curriculum(
                total_policy_ticks=max(
                    1,
                    int(runner.current_learning_iteration + options.iterations)
                    * int(options.rollout_steps),
                ),
                start_policy_tick=int(runner.current_learning_iteration)
                * int(options.rollout_steps),
            )
        training_start_iteration = int(
            getattr(runner, "current_learning_iteration", 0)
        )
        runner.learn(
            num_learning_iterations=options.iterations,
            init_at_random_ep_len=resolved.resume_checkpoint is None,
        )
        training_render = (
            bundle.render_controller.describe()
            if bundle.render_controller is not None
            else {
                "schema": "task_env.training_render.v1",
                "enabled": False,
                "started": False,
                "render_count": 0,
            }
        )
        runtime_resource_summary = _runtime_resource_summary(bundle)
        learner_profile_manifest = (
            bundle.learner_profile.manifest()
            if bundle.learner_profile is not None
            else {
                "profile_id": bundle.action_profile.manifest().get("profile_id", "default"),
                "action": bundle.action_profile.manifest(),
                "observation": {
                    "actor_groups": ["policy"],
                    "critic_groups": ["policy"],
                    "groups": {},
                },
            }
        )
        manifest = {
            "task": options.env_id,
            "runtime": dict(bundle.resolved_runtime),
            "batch_physics_layout": bundle.layout,
            "sim_device": options.sim_device,
            "rl_device": options.rl_device,
            "transfer_mode": bundle.transfer_mode,
            "execution": bundle.execution,
            "env_config": (
                str(options.env_config)
                if options.env_config is not None
                else "task_default.yaml"
            ),
            "rsl_api": "5.4.2",
            "rsl_action_profile": bundle.action_profile.manifest(),
            "rsl_learner_profile": learner_profile_manifest,
            "env_id": options.env_id,
            "seed": options.seed,
            "resume_checkpoint": (
                str(resolved.resume_checkpoint)
                if resolved.resume_checkpoint is not None
                else None
            ),
            "resume_iteration": resume_iteration,
            "start_iteration": training_start_iteration,
            "training_render": training_render,
            "render_layout": bundle.render_layout,
            "render_settings": bundle.render_settings.describe(),
            "runtime_resource_summary": runtime_resource_summary,
        }
        runner.save(str(resolved.checkpoint_out), infos=manifest)
        h5_output = options.output_dir / (
            "train.h5"
            if resolved.resume_checkpoint is None
            else f"train_resume_from_{training_start_iteration}.h5"
        )
        write_runner_h5_artifact(
            h5_output,
            runner,
            log_dir=resolved.log_dir,
            schema="task-env-rsl-ppo-run-v4",
            manifest={
                **manifest,
                "checkpoint": str(resolved.checkpoint_out),
                "log_dir": str(resolved.log_dir),
                "h5_output": str(h5_output),
                "num_env": options.num_env,
                "iterations": options.iterations,
                "rollout_steps": options.rollout_steps,
            },
        )
        return resolved.checkpoint_out
    finally:
        bundle.close()


__all__ = [
    "RslPpoOptions",
    "RslTrainingBundle",
    "current5_train_cfg",
    "resolve_resume_checkpoint",
    "train",
]
