"""Optional HDF5 artifact writers for RSL-RL runs.

The learner bridge remains dependency-lazy; ``h5py`` and TensorBoard are
loaded only when a user explicitly requests a persisted run artifact.
"""

from __future__ import annotations

import json
import functools
from pathlib import Path
import shutil
from typing import Any, Mapping

import numpy as np

from rsl_rl.utils.log_writer import LogWriter

from ...runtime.contracts import validate_device_reset_selection
from ._private_extras import (
    DEVICE_RESET_SELECTION_CONTRACT_KEY,
    DEVICE_RESET_SELECTION_CONTRACT_VALUE,
    DEVICE_RESET_SELECTION_EXTRAS_KEY,
)


class H5TensorBoardLogWriter(LogWriter):
    """RSL-RL log writer that keeps an in-memory scalar ledger.

    RSL-RL's built-in logger writes episode metrics only after at least one
    episode terminates.  Keeping the scalar calls here lets the task runner
    export an iteration-complete ledger to H5 without parsing TensorBoard
    event files (which may legitimately omit early episode metrics).
    """

    def __init__(
        self,
        log_dir: str,
        flush_secs: int = 10,
        checkpoint_dir: str | Path | None = None,
        **_: Any,
    ) -> None:
        from torch.utils.tensorboard import SummaryWriter

        self._writer = SummaryWriter(log_dir=log_dir, flush_secs=int(flush_secs))
        self.log_dir = str(log_dir)
        self.checkpoint_dir = None if checkpoint_dir is None else Path(checkpoint_dir)
        self.scalar_records: list[tuple[str, int, float]] = []

    def add_scalar(
        self,
        tag: str,
        scalar_value: Any,
        global_step: int | None = None,
        walltime: float | None = None,
        new_style: bool = False,
    ) -> None:
        value = scalar_value
        if hasattr(value, "detach"):
            value = value.detach().to("cpu").item()
        value = float(value)
        step = int(global_step or 0)
        self.scalar_records.append((str(tag), step, value))
        self._writer.add_scalar(
            str(tag),
            value,
            global_step=step,
            walltime=walltime,
            new_style=new_style,
        )

    def has_scalar(self, tag: str, step: int) -> bool:
        return any(name == str(tag) and iteration == int(step) for name, iteration, _ in self.scalar_records)

    def store_config(self, env_cfg: Any, train_cfg: dict[str, Any]) -> None:
        # The resolved config is stored in train.h5's manifest by the caller.
        return None

    def save_model(self, model_path: str, it: int) -> None:
        # RSL-RL calls this immediately after torch.save().  Keep TensorBoard
        # events under ``log_dir`` but move periodic model_N.pt artifacts to
        # the experiment root when the runner supplies ``checkpoint_dir``.
        # This leaves one canonical periodic checkpoint instead of retaining
        # identical copies under both log_dir and the experiment root.
        if self.checkpoint_dir is None:
            return None
        source = Path(model_path)
        target = self.checkpoint_dir / source.name
        if source.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
        return None

    def save_file(self, path: str) -> None:
        return None

    def stop(self) -> None:
        self._writer.flush()
        self._writer.close()


def install_iteration_metric_capture(runner: Any) -> Any:
    """Capture RSL-RL console-equivalent metrics for every PPO iteration.

    The installed RSL-RL logger intentionally suppresses mean reward and mean
    episode length until a completed episode exists.  This wrapper preserves
    that console behavior while adding explicit H5 scalars (NaN when the
    rolling statistic is unavailable) and rollout-level diagnostics on every
    iteration.  It only wraps the learner logger; no runtime or task API is
    changed.
    """

    logger = getattr(runner, "logger", None)
    if logger is None:
        raise TypeError("runner does not expose an RSL-RL logger")
    original_log = logger.log
    try:
        import torch
    except ModuleNotFoundError as exc:  # pragma: no cover - optional learner dependency
        raise RuntimeError("iteration metric capture requires torch") from exc

    device = getattr(logger, "device", "cpu")
    num_envs = int(getattr(logger, "num_envs"))
    current_reward = torch.zeros(num_envs, dtype=torch.float64, device=device)
    current_length = torch.zeros(num_envs, dtype=torch.float64, device=device)
    state: dict[str, Any] = {
        "rollout_reward_sum": 0.0,
        "rollout_reward_sum_device": torch.zeros((), dtype=torch.float64, device=device),
        "rollout_reward_count": 0,
        "rollout_reward_term_sums_device": {},
        "rollout_reward_term_counts": {},
        "completed_rewards": [],
        "completed_lengths": [],
        "pending_episode_columns": [],
        "rows": [],
    }

    def append_selected_host(
        selected_host: np.ndarray,
        *,
        include_base: bool,
        include_rnd: bool,
    ) -> None:
        """Append one chronological terminal batch to custom/RSL buffers."""

        state["completed_rewards"].extend(selected_host[:, 0].tolist())
        state["completed_lengths"].extend(selected_host[:, 1].tolist())
        if include_base:
            logger.rewbuffer.extend(selected_host[:, 2].tolist())
            logger.lenbuffer.extend(selected_host[:, 3].tolist())
            if include_rnd:
                logger.erewbuffer.extend(selected_host[:, 4].tolist())
                logger.irewbuffer.extend(selected_host[:, 5].tolist())

    def flush_pending_episode_columns() -> None:
        """Materialize direct-path terminal rows once per PPO iteration."""

        pending = state["pending_episode_columns"]
        while pending:
            include_base = bool(pending[0][1])
            include_rnd = bool(pending[0][2])
            split = 1
            while split < len(pending) and pending[split][1:] == pending[0][1:]:
                split += 1
            selected_host = (
                torch.cat([item[0] for item in pending[:split]], dim=0)
                .detach()
                .to("cpu")
                .numpy()
            )
            append_selected_host(
                selected_host,
                include_base=include_base,
                include_rnd=include_rnd,
            )
            del pending[:split]

    original_process = logger.process_env_step

    @functools.wraps(original_process)
    def process_env_step(rewards: Any, dones: Any, extras: dict, intrinsic_rewards: Any = None) -> None:
        reward_vector = rewards.detach().to(device=device, dtype=torch.float64).reshape(-1)
        done_vector = dones.detach().to(device=device).reshape(-1).bool()
        if reward_vector.numel() != num_envs or done_vector.numel() != num_envs:
            raise ValueError("RSL-RL metric capture received an unexpected environment batch shape")

        has_selection = DEVICE_RESET_SELECTION_EXTRAS_KEY in extras
        has_direct_contract = DEVICE_RESET_SELECTION_CONTRACT_KEY in extras
        if has_selection != has_direct_contract:
            raise ValueError(
                "reset selection direct PPO/logger contract evidence is incomplete"
            )
        selection = extras.get(DEVICE_RESET_SELECTION_EXTRAS_KEY)
        if has_selection:
            if (
                extras[DEVICE_RESET_SELECTION_CONTRACT_KEY]
                != DEVICE_RESET_SELECTION_CONTRACT_VALUE
            ):
                raise ValueError(
                    "reset selection direct PPO/logger contract is unsupported"
                )
            # Validate before mutating either the TaskEnv metric state or the
            # installed RSL logger.  Identity and pointer checks bind the host
            # slots to this exact dones batch.  This no-readback validation is
            # valid only for the direct, read-only installed-PPO route named
            # by the companion private contract key above.
            validate_device_reset_selection(
                selection,
                mask=dones,
                num_envs=num_envs,
                device=str(getattr(dones, "device", device)),
                require_data_pointer=True,
            )
            selected_count = int(selection.selected_count)
            done_ids = (
                torch.tensor(
                    selection.selected_slots,
                    dtype=torch.long,
                    device=done_vector.device,
                )
                if selected_count
                else None
            )
        else:
            # Generic/non-TaskEnv runners and unsupported intermediaries do
            # not publish either private key and retain this correct fallback.
            done_ids = torch.nonzero(done_vector, as_tuple=False).reshape(-1)
            selected_count = int(done_ids.numel())

        current_reward.add_(reward_vector)
        current_length.add_(1.0)
        # Keep the reduction on-device during collection.  Materialize the
        # scalar once per PPO iteration in ``log`` instead of synchronizing
        # the CUDA stream on every environment step.
        state["rollout_reward_sum_device"].add_(reward_vector.sum())
        state["rollout_reward_count"] += int(reward_vector.numel())

        # Reward terms are already published by the TaskEnv device contract.
        # Accumulate them on the learner device and transfer one compact
        # vector at iteration logging time; never read a term back per tick.
        transition_terms = (
            extras.get("reward_terms", {})
            if isinstance(extras, Mapping)
            else {}
        )
        if transition_terms:
            term_sums = state["rollout_reward_term_sums_device"]
            term_counts = state["rollout_reward_term_counts"]
            for raw_name, raw_value in transition_terms.items():
                name = str(raw_name)
                if hasattr(raw_value, "detach"):
                    term_vector = raw_value.detach().to(
                        device=device, dtype=torch.float64
                    ).reshape(-1)
                else:
                    term_vector = torch.as_tensor(
                        raw_value, device=device, dtype=torch.float64
                    ).reshape(-1)
                if term_vector.numel() == 1:
                    term_vector = term_vector.expand(num_envs)
                if term_vector.numel() != num_envs:
                    raise ValueError(
                        "RSL-RL reward term has an unexpected environment batch shape: "
                        f"{name}={tuple(term_vector.shape)}, expected ({num_envs},)"
                    )
                if name not in term_sums:
                    # RSL-RL 在 torch.inference_mode() 中收集 transition，
                    # 但累加器会在该上下文结束后的 log() 阶段重置。
                    # 工厂显式关闭 inference mode，确保迭代边界仍可修改。
                    with torch.inference_mode(False):
                        term_sums[name] = torch.zeros(
                            (), dtype=torch.float64, device=device
                        )
                if name not in term_counts:
                    term_counts[name] = 0
                term_sums[name].add_(term_vector.sum())
                term_counts[name] += int(term_vector.numel())

        writer = getattr(logger, "writer", None)
        if writer is not None:
            if "episode" in extras:
                logger.ep_extras.append(extras["episode"])
            elif "log" in extras:
                logger.ep_extras.append(extras["log"])

            if intrinsic_rewards is not None:
                logger.cur_ereward_sum += rewards
                logger.cur_ireward_sum += intrinsic_rewards
                logger.cur_reward_sum += rewards + intrinsic_rewards
            else:
                logger.cur_reward_sum += rewards
            logger.cur_episode_length += 1

        if selected_count:
            # Select every custom/base/RND terminal value on-device, promote
            # them into one rectangular tensor, then perform exactly one
            # selected device-to-host transfer for this tick.
            selected_columns = [
                current_reward.index_select(0, done_ids),
                current_length.index_select(0, done_ids),
            ]
            if writer is not None:
                selected_columns.extend(
                    (
                        logger.cur_reward_sum.index_select(0, done_ids),
                        logger.cur_episode_length.index_select(0, done_ids),
                    )
                )
                if intrinsic_rewards is not None:
                    selected_columns.extend(
                        (
                            logger.cur_ereward_sum.index_select(0, done_ids),
                            logger.cur_ireward_sum.index_select(0, done_ids),
                        )
                    )
            selected_device = torch.stack(selected_columns, dim=1).detach()
            if has_selection:
                # The direct TaskEnv->installed-PPO contract preserves these
                # selected tensors until iteration logging.  Queue them on the
                # learner device so terminal bookkeeping performs one compact
                # D2H transfer per rollout instead of one synchronization per
                # terminal tick.
                state["pending_episode_columns"].append(
                    (selected_device, writer is not None, intrinsic_rewards is not None)
                )
            else:
                # Generic fallback already synchronizes this tick.  Drain any
                # older deferred direct batches first so completion chronology
                # (and bounded RSL deque truncation) remains exact if callers
                # switch contracts within one rollout.
                flush_pending_episode_columns()
                append_selected_host(
                    selected_device.to("cpu").numpy(),
                    include_base=writer is not None,
                    include_rnd=intrinsic_rewards is not None,
                )
            current_reward[done_ids] = 0.0
            current_length[done_ids] = 0.0
            if writer is not None:
                logger.cur_reward_sum[done_ids] = 0
                logger.cur_episode_length[done_ids] = 0
                if intrinsic_rewards is not None:
                    logger.cur_ereward_sum[done_ids] = 0
                    logger.cur_ireward_sum[done_ids] = 0

    @functools.wraps(original_log)
    def log(*args: Any, **kwargs: Any) -> None:
        flush_pending_episode_columns()
        original_log(*args, **kwargs)
        iteration = kwargs.get("it")
        if iteration is None and args:
            iteration = args[0]
        if iteration is None:
            raise ValueError("RSL-RL logger.log did not provide an iteration")
        iteration = int(iteration)
        writer = getattr(logger, "writer", None)
        rolling_reward = (
            float(np.mean(list(logger.rewbuffer))) if len(logger.rewbuffer) else float("nan")
        )
        rolling_length = (
            float(np.mean(list(logger.lenbuffer))) if len(logger.lenbuffer) else float("nan")
        )
        completed_count = float(len(state["completed_rewards"]))
        term_sums = state["rollout_reward_term_sums_device"]
        term_counts = state["rollout_reward_term_counts"]
        term_names = sorted(
            name for name in term_sums if int(term_counts.get(name, 0)) > 0
        )
        aggregate_values_device = torch.stack(
            [state["rollout_reward_sum_device"], *[term_sums[name] for name in term_names]]
        )
        aggregate_values = (
            aggregate_values_device.detach().to("cpu").numpy()
        )
        rollout_reward_sum = float(aggregate_values[0])
        rollout_mean_reward = (
            rollout_reward_sum / state["rollout_reward_count"]
            if state["rollout_reward_count"]
            else float("nan")
        )
        rollout_mean_episode_length = (
            float(np.mean(state["completed_lengths"]))
            if state["completed_lengths"]
            else float("nan")
        )
        partial_mean_reward = float(current_reward.mean().detach().to("cpu").item())
        partial_mean_length = float(current_length.mean().detach().to("cpu").item())
        collect_time = float(kwargs.get("collect_time", 0.0))
        learn_time = float(kwargs.get("learn_time", 0.0))
        iteration_time = collect_time + learn_time
        start_iteration = int(kwargs.get("start_it", iteration))
        total_iteration = int(kwargs.get("total_it", iteration + 1))
        completed_iterations = max(1, iteration + 1 - start_iteration)
        remaining_iterations = max(0, total_iteration - start_iteration - completed_iterations)
        total_time = float(getattr(logger, "tot_time", iteration_time))
        eta_seconds = total_time / completed_iterations * remaining_iterations
        total_steps = int(getattr(logger, "tot_timesteps", 0))
        metrics = {
            "Train/mean_reward": rolling_reward,
            "Train/mean_episode_length": rolling_length,
            "Train/completed_episode_count": completed_count,
            "Train/rollout_mean_reward": rollout_mean_reward,
            "Train/rollout_mean_episode_length": rollout_mean_episode_length,
            "Train/partial_mean_reward": partial_mean_reward,
            "Train/partial_mean_episode_length": partial_mean_length,
            "Train/total_steps": float(total_steps),
            "Perf/iteration_time": iteration_time,
            "Perf/time_elapsed": total_time,
            "Perf/eta_seconds": eta_seconds,
        }
        # Keep reward diagnostics in their own TensorBoard class.  ``total``
        # is the same transition mean as ``Train/rollout_mean_reward``; the
        # named curves expose the algebra that produced it.
        reward_metrics = {}
        if term_names:
            reward_metrics["Reward/total"] = rollout_mean_reward
            for index, name in enumerate(term_names, start=1):
                count = int(term_counts[name])
                reward_metrics[f"Reward/{name}"] = (
                    float(aggregate_values[index]) / count if count else float("nan")
                )
        metrics.update(reward_metrics)
        if writer is not None and hasattr(writer, "add_scalar"):
            for tag, value in metrics.items():
                if not hasattr(writer, "has_scalar") or not writer.has_scalar(tag, iteration):
                    writer.add_scalar(tag, value, iteration)
        row = {"iteration": iteration, **metrics}
        state["rows"].append(row)
        state["rollout_reward_sum"] = 0.0
        state["rollout_reward_sum_device"].zero_()
        state["rollout_reward_count"] = 0
        for value in term_sums.values():
            value.zero_()
        term_counts.clear()
        state["completed_rewards"].clear()
        state["completed_lengths"].clear()

    logger.process_env_step = process_env_step
    logger.log = log
    state["flush_pending_episode_columns"] = flush_pending_episode_columns
    state["current_reward"] = current_reward
    state["current_length"] = current_length
    return state


def scalar_records_to_arrays(records: Any) -> dict[str, np.ndarray]:
    """Convert captured ``(tag, iteration, value)`` records to H5 arrays."""

    latest: dict[tuple[str, int], float] = {}
    for tag, step, value in records:
        latest[(str(tag), int(step))] = float(value)
    grouped: dict[str, list[tuple[int, float]]] = {}
    for (tag, step), value in latest.items():
        grouped.setdefault(tag, []).append((step, value))
    return {
        tag: np.asarray(sorted(values), dtype=np.float64)
        for tag, values in grouped.items()
    }


def iteration_table_from_scalars(scalars: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Build a rectangular per-iteration table with NaN for unavailable values."""

    # RSL-RL also emits ``Train/*/time`` using wall-clock seconds as the
    # global step.  Those remain available in ``scalars`` but are not PPO
    # iteration rows, otherwise one wall-clock sample creates a spurious
    # all-NaN iteration in the rectangular ledger.
    iteration_scalars = {
        str(tag): values for tag, values in scalars.items() if not str(tag).endswith("/time")
    }
    tags = sorted(iteration_scalars)
    steps = sorted({int(row[0]) for values in iteration_scalars.values() for row in np.asarray(values)})
    matrix = np.full((len(steps), len(tags)), np.nan, dtype=np.float64)
    step_index = {step: index for index, step in enumerate(steps)}
    tag_index = {tag: index for index, tag in enumerate(tags)}
    for tag, values in iteration_scalars.items():
        for step, value in np.asarray(values):
            matrix[step_index[int(step)], tag_index[str(tag)]] = float(value)
    return {
        "ppo_iteration": np.asarray(steps, dtype=np.int64),
        "ppo_metric_names": np.asarray(tags, dtype="S"),
        "ppo_values": matrix,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def _write_json_dataset(group: Any, name: str, value: Any) -> None:
    text = json.dumps(value, sort_keys=True, default=_json_default)
    group.create_dataset(name, data=np.bytes_(text.encode("utf-8")))


def _write_mapping(group: Any, mapping: Mapping[str, Any]) -> None:
    for key, value in mapping.items():
        name = str(key).replace("/", "__")
        if isinstance(value, Mapping):
            child = group.create_group(name)
            _write_mapping(child, value)
        elif isinstance(value, (str, bytes)):
            group.create_dataset(name, data=np.bytes_(str(value).encode("utf-8")))
        else:
            try:
                array = np.asarray(value)
                # Preserve fixed-width byte-string arrays (for example the
                # per-iteration metric-name vector) as real HDF5 vectors;
                # only object/unicode arrays need JSON fallback.
                if array.dtype.kind in "OU":
                    _write_json_dataset(group, name, value)
                else:
                    group.create_dataset(name, data=array)
            except (TypeError, ValueError):
                _write_json_dataset(group, name, value)


def write_h5_artifact(
    path: str | Path,
    *,
    schema: str,
    manifest: Mapping[str, Any],
    scalars: Mapping[str, np.ndarray] | None = None,
    arrays: Mapping[str, Any] | None = None,
    report: Mapping[str, Any] | None = None,
) -> Path:
    """Write a self-contained run/report artifact with named HDF5 groups."""

    try:
        import h5py
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("HDF5 artifacts require h5py; install it in geophys") from exc

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(target, "w") as handle:
        handle.attrs["schema"] = str(schema)
        handle.attrs["format_version"] = "task-env-h5-artifact-v1"
        manifest_group = handle.create_group("manifest")
        _write_mapping(manifest_group, manifest)
        if scalars:
            scalar_group = handle.create_group("scalars")
            for name, values in scalars.items():
                scalar_group.create_dataset(
                    str(name).replace("/", "__"),
                    data=np.asarray(values),
                )
        if arrays:
            array_group = handle.create_group("arrays")
            _write_mapping(array_group, arrays)
        if report is not None:
            _write_json_dataset(handle, "report_json", report)
    return target


def write_runner_h5_artifact(
    path: str | Path,
    runner: Any,
    *,
    log_dir: str | Path,
    schema: str,
    manifest: Mapping[str, Any],
) -> Path:
    """Export a current RSL-RL runner's scalar ledger and iteration table."""

    writer = getattr(getattr(runner, "logger", None), "writer", None)
    records = getattr(writer, "scalar_records", None)
    if records is None:
        scalars = read_tensorboard_scalars(log_dir)
    else:
        scalars = scalar_records_to_arrays(records)
    iteration_table = iteration_table_from_scalars(scalars)
    artifact_manifest = {
        **dict(manifest),
        "scalar_tags": sorted(scalars),
        "iteration_metric_table": {
            "iterations": int(len(iteration_table["ppo_iteration"])),
            "columns": int(iteration_table["ppo_values"].shape[1]),
            "missing_values": (
                "NaN means RSL-RL's rolling episode statistic was unavailable "
                "at that iteration"
            ),
        },
    }
    return write_h5_artifact(
        path,
        schema=schema,
        manifest=artifact_manifest,
        scalars=scalars,
        arrays=iteration_table,
    )


def read_tensorboard_scalars(log_dir: str | Path) -> dict[str, np.ndarray]:
    """Read TensorBoard scalar history as ``(step, value)`` arrays."""

    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("TensorBoard scalar export requires tensorboard") from exc
    accumulator = EventAccumulator(str(log_dir))
    accumulator.Reload()
    result: dict[str, np.ndarray] = {}
    for tag in accumulator.Tags().get("scalars", ()):
        result[str(tag)] = np.asarray(
            [[event.step, event.value] for event in accumulator.Scalars(tag)],
            dtype=np.float64,
        )
    return result


__all__ = [
    "H5TensorBoardLogWriter",
    "install_iteration_metric_capture",
    "iteration_table_from_scalars",
    "read_tensorboard_scalars",
    "scalar_records_to_arrays",
    "write_h5_artifact",
    "write_runner_h5_artifact",
]
