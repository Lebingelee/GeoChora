"""Run native SB3 PPO against the remote Pendulum TaskEnv batch.

The learner process constructs only the SB3 policy and the shared remote
vector adapter.  Taichi and the homogeneous runtime are created in the
simulator child owned by ``make_parallel_env(..., execution='remote')``.

``--updates`` is the number of PPO rollout/update cycles.  With
``--save-log`` the script incrementally writes an H5 return curve with
episode returns indexed by learner timesteps.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import sys
from typing import Any

import numpy as np

if __package__ in (None, ""):
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[3]))
    from task_env.script._bootstrap import (
        BACKEND_CHOICES,
        get_logger,
        stage14_output,
        with_backend_fallback,
        write_json,
    )
else:
    from .._bootstrap import (
        BACKEND_CHOICES,
        get_logger,
        stage14_output,
        with_backend_fallback,
        write_json,
    )


def _train_once(
    *,
    requested_backend: str,
    num_env: int,
    updates: int,
    rollout_steps: int,
    seed: int,
    output_root: Path,
    return_log_path: Path | None,
    log_every_updates: int,
    save_every_updates: int,
    batch_physics_layout: str = "merged_scene",
    static_template_profile: str = "auto",
    integrator: str = "implicitfast",
) -> tuple[str, dict[str, Any]]:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    import h5py
    from task_env.utils import SB3FlattenVecWrapper
    from task_env import make_parallel_env

    logger = get_logger("task-env-stage14-rl-pendulum")

    class _ReturnCurveCallback(BaseCallback):
        """Track per-slot episode returns without touching the simulator."""

        def __init__(self) -> None:
            super().__init__(verbose=0)
            self.rollout_index = 0
            self._episode_returns = np.zeros(num_env, dtype=np.float64)
            self._episode_lengths = np.zeros(num_env, dtype=np.int64)
            self.episode_timesteps: list[int] = []
            self.episode_returns: list[float] = []
            self.episode_lengths: list[int] = []
            self.episode_env_indices: list[int] = []
            self.rollout_timesteps: list[int] = []
            self.rollout_mean_returns: list[float] = []
            self.rollout_episode_counts: list[int] = []
            self.rollout_completed_episode_counts: list[int] = []
            self._saved_episode_count = 0

        def _rolling_mean(self, window: int = 100) -> np.ndarray:
            values = np.asarray(self.episode_returns, dtype=np.float64)
            if values.size == 0:
                return np.empty(0, dtype=np.float32)
            output = np.empty(values.size, dtype=np.float64)
            for index in range(values.size):
                output[index] = values[max(0, index + 1 - window) : index + 1].mean()
            return output.astype(np.float32)

        @staticmethod
        def _create_dataset(group: h5py.Group, name: str, values: np.ndarray) -> None:
            """Write a plotting-friendly snapshot dataset with safe empty-array handling."""
            if values.ndim > 0 and values.shape[0] > 0:
                group.create_dataset(
                    name,
                    data=values,
                    compression="gzip",
                    compression_opts=4,
                    shuffle=True,
                )
            else:
                group.create_dataset(name, data=values)

        def _save_curve(self) -> None:
            if return_log_path is None:
                return
            return_log_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = return_log_path.with_name(return_log_path.name + ".tmp")
            with h5py.File(temporary, "w") as root:
                root.attrs["format"] = "task-env.ppo-return-curve.v1"
                root.attrs["num_env"] = num_env
                root.attrs["rollout_steps"] = rollout_steps
                root.attrs["rollouts_completed"] = self.rollout_index
                root.attrs["learner_timesteps"] = int(self.num_timesteps)

                episodes = root.create_group("episodes")
                self._create_dataset(
                    episodes,
                    "timesteps",
                    np.asarray(self.episode_timesteps, dtype=np.int64),
                )
                self._create_dataset(
                    episodes,
                    "returns",
                    np.asarray(self.episode_returns, dtype=np.float32),
                )
                self._create_dataset(
                    episodes,
                    "lengths",
                    np.asarray(self.episode_lengths, dtype=np.int64),
                )
                self._create_dataset(
                    episodes,
                    "env_indices",
                    np.asarray(self.episode_env_indices, dtype=np.int64),
                )
                self._create_dataset(episodes, "rolling_mean_return", self._rolling_mean())

                rollouts = root.create_group("rollouts")
                self._create_dataset(
                    rollouts,
                    "indices",
                    np.arange(1, self.rollout_index + 1, dtype=np.int64),
                )
                self._create_dataset(
                    rollouts,
                    "timesteps",
                    np.asarray(self.rollout_timesteps, dtype=np.int64),
                )
                self._create_dataset(
                    rollouts,
                    "mean_return",
                    np.asarray(self.rollout_mean_returns, dtype=np.float32),
                )
                self._create_dataset(
                    rollouts,
                    "mean_return_valid",
                    np.asarray(self.rollout_episode_counts, dtype=np.int64) > 0,
                )
                self._create_dataset(
                    rollouts,
                    "episode_counts",
                    np.asarray(self.rollout_episode_counts, dtype=np.int64),
                )
                self._create_dataset(
                    rollouts,
                    "completed_episode_counts",
                    np.asarray(self.rollout_completed_episode_counts, dtype=np.int64),
                )

                active = root.create_group("active")
                self._create_dataset(active, "episode_returns", self._episode_returns.astype(np.float32))
                self._create_dataset(active, "episode_lengths", self._episode_lengths.copy())
            temporary.replace(return_log_path)

        def _on_step(self) -> bool:
            rewards = np.asarray(self.locals["rewards"], dtype=np.float64).reshape(-1)
            dones = np.asarray(self.locals["dones"], dtype=np.bool_).reshape(-1)
            if rewards.shape != (num_env,) or dones.shape != (num_env,):
                raise ValueError(
                    "SB3 callback expected vector rewards/dones with shape "
                    f"({num_env},), got {rewards.shape}/{dones.shape}"
                )
            self._episode_returns += rewards
            self._episode_lengths += 1
            for slot, done in enumerate(dones):
                if not done:
                    continue
                self.episode_timesteps.append(int(self.num_timesteps))
                self.episode_returns.append(float(self._episode_returns[slot]))
                self.episode_lengths.append(int(self._episode_lengths[slot]))
                self.episode_env_indices.append(slot)
                self._episode_returns[slot] = 0.0
                self._episode_lengths[slot] = 0
            return True

        def _on_rollout_end(self) -> None:
            self.rollout_index += 1
            completed = len(self.episode_returns)
            recent = self.episode_returns[self._saved_episode_count : completed]
            mean_return = float(np.mean(recent)) if recent else float("nan")
            self.rollout_timesteps.append(int(self.num_timesteps))
            self.rollout_mean_returns.append(mean_return)
            self.rollout_episode_counts.append(len(recent))
            self.rollout_completed_episode_counts.append(completed)
            self._saved_episode_count = completed
            if self.rollout_index % save_every_updates == 0:
                self._save_curve()
            if self.rollout_index == 1 or self.rollout_index % log_every_updates == 0:
                logger.info(
                    "SB3 Pendulum PPO rollout completed",
                    event="rl.ppo.rollout_completed",
                    rollout=self.rollout_index,
                    num_env=num_env,
                    rollout_steps=rollout_steps,
                    timesteps=int(self.num_timesteps),
                    completed_episodes=completed,
                    mean_return=None if not recent else round(mean_return, 6),
                    return_log=None if return_log_path is None else str(return_log_path),
                )

        def _on_training_end(self) -> None:
            self._save_curve()

    def create(backend: str):
        if "taichi" in sys.modules:
            raise RuntimeError("learner-side PPO script imported Taichi before remote env creation")
        raw_env = make_parallel_env(
            uid="pendulum-v1",
            env_config={
                "base_seed": seed,
                "runtime": {
                    "batch_physics_layout": batch_physics_layout,
                    "integrator": integrator,
                    "static_template": {
                        "profile": static_template_profile,
                    },
                },
            },
            num_env=num_env,
            backend=backend,
            execution="remote",
        )
        try:
            record_metadata = raw_env.get_record_metadata()
            reported_layout = record_metadata.get("env_metadata", {}).get(
                "batch_physics_layout"
            )
            if reported_layout != batch_physics_layout:
                raise RuntimeError(
                    "remote vector metadata reported the wrong batch physics layout: "
                    f"expected {batch_physics_layout!r}, got {reported_layout!r}"
                )
            if "runtime_resource_summary" not in record_metadata.get(
                "resolved_config", {}
            ):
                raise RuntimeError(
                    "remote vector record metadata lacks runtime_resource_summary"
                )
            env = SB3FlattenVecWrapper(raw_env)
            observation = env.reset()
            if observation.shape != (num_env, 3):
                raise ValueError(f"remote Pendulum reset shape must be {(num_env, 3)}, got {observation.shape}")
            model = PPO(
                "MlpPolicy",
                env,
                n_steps=rollout_steps,
                batch_size=rollout_steps * num_env,
                n_epochs=1,
                device="cuda" if backend == "cuda" else "cpu",
                verbose=0,
                seed=seed,
            )
            callback = _ReturnCurveCallback()
            model.learn(
                total_timesteps=updates * rollout_steps * num_env,
                callback=callback,
            )
            checkpoint = output_root / f"pendulum_ppo_b{num_env}_{backend}"
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            model.save(str(checkpoint))
            summary = {
                "task_uid": "pendulum-v1",
                "backend": backend,
                "num_env": num_env,
                "updates": updates,
                "rollout_steps": rollout_steps,
                "seed": seed,
                "timesteps": int(model.num_timesteps),
                "updates_completed": callback.rollout_index,
                "episodes_recorded": len(callback.episode_returns),
                "return_log": None if return_log_path is None else str(return_log_path),
                "checkpoint": str(checkpoint.with_suffix(".zip")),
                "execution": "remote",
                "batch_physics_layout": batch_physics_layout,
                "static_template_profile": static_template_profile,
                "integrator": integrator,
                "learner_imported_taichi": False,
            }
            return env, summary
        except BaseException:
            raw_env.close()
            raise

    backend, pair = with_backend_fallback(
        requested_backend,
        create,
        logger=logger,
        operation=f"rl:pendulum-ppo:B{num_env}",
    )
    env, summary = pair
    try:
        summary["backend"] = backend
        return backend, summary
    finally:
        env.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-env", dest="num_env", type=int, default=4)
    parser.add_argument("--backend", choices=BACKEND_CHOICES, default="auto")
    parser.add_argument(
        "--batch-physics-layout",
        choices=("merged_scene", "static_template"),
        default="merged_scene",
        help="select the batch physics layout; static_template is the Stage 15 route",
    )
    parser.add_argument(
        "--static-template-profile",
        choices=("auto", "rigid_batch_v1"),
        default="auto",
        help="explicit static profile; rigid_batch_v1 uses src/solvers/rigid/batch",
    )
    parser.add_argument(
        "--integrator",
        choices=("implicitfast", "euler"),
        default="implicitfast",
        help="physics integrator; rigid_batch_v1 requires euler",
    )
    parser.add_argument(
        "--updates",
        type=int,
        default=3,
        help="number of PPO rollout/update cycles",
    )
    parser.add_argument(
        "--rollout-steps",
        dest="rollout_steps",
        type=int,
        default=5,
    )
    parser.add_argument("--seed", type=int, default=73)
    parser.add_argument(
        "--random",
        action="store_true",
        help="draw an OS-random base seed for this training run",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--save-log",
        dest="save_log",
        nargs="?",
        const=Path("return_curve.h5"),
        default=None,
        type=Path,
        help="save an H5 return curve; optionally provide a relative/absolute .h5 path",
    )
    parser.add_argument(
        "--log-every-updates",
        dest="log_every_updates",
        type=int,
        default=100,
        help="emit progress logger output every N rollout/update cycles",
    )
    parser.add_argument(
        "--save-every-updates",
        dest="save_every_updates",
        type=int,
        default=10,
        help="flush the H5 return curve every N rollout/update cycles",
    )
    parser.add_argument(
        "--verify-batches",
        action="store_true",
        help="run the same short native PPO loop for B=1, 2, and 4",
    )
    args = parser.parse_args()
    if (
        args.num_env < 1
        or args.updates < 1
        or args.rollout_steps < 1
        or args.log_every_updates < 1
        or args.save_every_updates < 1
    ):
        parser.error(
            "num-env, updates, rollout-steps, log-every-updates, and "
            "save-every-updates must be positive"
        )
    output_root = args.output_dir or stage14_output("rl", "pendulum_ppo")
    batches = (1, 2, 4) if args.verify_batches else (args.num_env,)
    logger = get_logger("task-env-stage14-rl-pendulum")
    run_seed = secrets.randbelow(2**31) if args.random else args.seed
    seed_mode = "os-random" if args.random else "fixed"
    logger.info(
        "TaskEnv PPO seed selected",
        event="rl.ppo.seed_selected",
        seed=run_seed,
        seed_mode=seed_mode,
    )
    results = []
    for num_env in batches:
        return_log_path = None
        if args.save_log is not None:
            return_log_path = args.save_log
            if not return_log_path.is_absolute():
                return_log_path = output_root / return_log_path
            if return_log_path.suffix.lower() != ".h5":
                return_log_path = return_log_path.with_suffix(".h5")
            if len(batches) > 1:
                return_log_path = return_log_path.with_name(
                    f"{return_log_path.stem}_b{num_env}{return_log_path.suffix}"
                )
        backend, summary = _train_once(
            requested_backend=args.backend,
            num_env=num_env,
            updates=args.updates,
            rollout_steps=args.rollout_steps,
            seed=run_seed + num_env,
            output_root=output_root,
            return_log_path=return_log_path,
            log_every_updates=args.log_every_updates,
            save_every_updates=args.save_every_updates,
            batch_physics_layout=args.batch_physics_layout,
            static_template_profile=args.static_template_profile,
            integrator=args.integrator,
        )
        logger.check_or_raise(
            summary["timesteps"] == args.updates * args.rollout_steps * num_env,
            "native SB3 PPO must complete the requested short updates",
            backend=backend,
            num_env=num_env,
            timesteps=summary["timesteps"],
        )
        logger.check_or_raise(
            summary["updates_completed"] == args.updates,
            "native SB3 PPO must emit one completion event per requested rollout/update",
            backend=backend,
            num_env=num_env,
            updates_completed=summary["updates_completed"],
        )
        summary["seed_mode"] = seed_mode
        results.append(summary)
    summary_path = output_root / "summary.json"
    write_json(summary_path, {"batches": results, "verify_batches": args.verify_batches})
    logger.success(
        "remote native SB3 Pendulum PPO completed",
        batches=tuple(batches),
        batch_physics_layout=args.batch_physics_layout,
        output=str(summary_path),
    )


if __name__ == "__main__":
    main()
