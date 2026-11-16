"""Environment-free recorder core; wrapper owns all env interaction."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .contracts import RecorderConfig
from .trajectory import FrozenTrajectory, copy_tree, tree_nbytes
from task_env.trajectory.canonical.episode import (
    BoundaryEventV1,
    EpisodeOutcomeV1,
    StructuredControlTransitionV1,
    validate_episode_records,
)


def _recording_copy(value: Any, *, in_rgb_branch: bool = False) -> Any:
    """复制观测，并将 RGB 叶子压缩为适合数据集存储的 ``uint8``。"""

    if isinstance(value, Mapping):
        return {
            str(key): _recording_copy(item, in_rgb_branch=in_rgb_branch or str(key) == "rgb")
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_recording_copy(item, in_rgb_branch=in_rgb_branch) for item in value]
    if isinstance(value, np.ndarray):
        if in_rgb_branch:
            return _quantize_rgb(value)
        return np.asarray(value).copy()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _quantize_rgb(value: np.ndarray) -> np.ndarray:
    """将 RGB 图像量化为数据集统一使用的 ``CHW uint8`` 副本。"""

    image = np.asarray(value)
    if image.ndim != 3 or (image.shape[0] != 3 and image.shape[-1] != 3):
        raise ValueError("recorded RGB leaf must be a CHW or HWC image with three channels")
    if not np.issubdtype(image.dtype, np.number):
        raise ValueError("recorded RGB leaf must use a numeric dtype")
    if image.dtype == np.uint8:
        result = image.copy()
        return result if result.shape[0] == 3 else np.transpose(result, (2, 0, 1)).copy()
    values = np.asarray(image, dtype=np.float32)
    if not np.isfinite(values).all():
        raise ValueError("recorded RGB leaf must contain finite values")
    if np.all((values >= 0.0) & (values <= 1.0)):
        values = values * 255.0
    elif not np.all((values >= 0.0) & (values <= 255.0)):
        raise ValueError("recorded RGB leaf values must be in [0, 1] or [0, 255]")
    result = np.rint(values).astype(np.uint8)
    return result if result.shape[0] == 3 else np.transpose(result, (2, 0, 1)).copy()


class TransitionRecorder:
    def __init__(self, config: RecorderConfig | None = None) -> None:
        self.config = config or RecorderConfig()
        self._active = False
        self._frozen: FrozenTrajectory | None = None
        self._bytes = 0
        self._observations: list[Any] = []
        self._actions: list[np.ndarray] = []
        self._universal_actions: list[np.ndarray] = []
        self._rewards: list[float] = []
        self._successes: list[bool] = []
        self._terminated: list[bool] = []
        self._truncated: list[bool] = []
        self._infos: list[dict[str, Any]] = []
        self._reset_info: dict[str, Any] = {}
        self._record_metadata: dict[str, Any] = {}
        self._structured_controls: list[StructuredControlTransitionV1 | None] = []
        self._boundary_events: list[BoundaryEventV1] = []
        self._outcome: EpisodeOutcomeV1 | None = None
        self._save_index = 0

    @property
    def active(self) -> bool:
        return self._active

    @property
    def frozen(self) -> FrozenTrajectory | None:
        return self._frozen

    @property
    def transition_count(self) -> int:
        return len(self._actions)

    @property
    def observation_count(self) -> int:
        return len(self._observations)

    def begin_episode(self, initial_obs: Any, reset_info: dict[str, Any], record_metadata: dict[str, Any]) -> None:
        if self._active:
            raise RuntimeError("recording is already active")
        # Prepare the entire first boundary before replacing a frozen episode.
        # A copy or capacity failure must leave the recorder retryable.
        reset_copy = copy_tree(reset_info)
        metadata_copy = copy_tree(record_metadata)
        observation_copy = _recording_copy(initial_obs)
        observation_bytes = tree_nbytes(observation_copy)
        if observation_bytes > self.config.max_buffer_bytes:
            raise MemoryError("recording buffer exceeds max_buffer_bytes")
        self._active = True
        self._frozen = None
        self._bytes = observation_bytes
        self._observations = [observation_copy]
        self._actions = []
        self._universal_actions = []
        self._rewards, self._successes, self._terminated, self._truncated, self._infos = [], [], [], [], []
        self._reset_info, self._record_metadata = reset_copy, metadata_copy
        self._structured_controls = []
        self._boundary_events = []
        self._outcome = None

    def append_transition(
        self,
        action: Any,
        universal_action: Any,
        next_obs: Any,
        reward: float,
        success: bool,
        terminated: bool,
        truncated: bool,
        info: dict[str, Any],
        *,
        structured_control: StructuredControlTransitionV1 | None = None,
    ) -> None:
        if not self._active:
            raise RuntimeError("begin_episode() must be called before append_transition()")
        if structured_control is not None and not isinstance(structured_control, StructuredControlTransitionV1):
            raise TypeError("structured_control must be StructuredControlTransitionV1 or None")
        if self._structured_controls and (self._structured_controls[0] is None) != (structured_control is None):
            raise ValueError("structured control evidence must be present for every transition or none")
        if len(self._actions) >= self.config.max_transitions:
            raise OverflowError("recording exceeds max_transitions")
        action_value = np.asarray(action, dtype=np.float32).copy()
        universal_value = np.asarray(universal_action, dtype=np.float32).copy()
        if universal_value.ndim != 1 or not np.isfinite(universal_value).all():
            raise ValueError("universal_action must be a finite 1D vector")
        schema = self._record_metadata.get("universal_action_schema", {})
        if not schema:
            env_metadata = self._record_metadata.get("env_metadata", {})
            schema = env_metadata.get("universal_action_schema", {})
        if isinstance(schema, dict) and schema.get("dimension") is not None:
            expected_dimension = int(schema["dimension"])
            if universal_value.shape != (expected_dimension,):
                raise ValueError(
                    "universal_action shape does not match its schema: "
                    f"got {universal_value.shape}, expected {(expected_dimension,)}"
                )
        # Prepare every potentially failing copy and capacity check before
        # mutating any aligned transition list. A rejected append must leave
        # the trajectory at its prior T / T+1 boundary.
        observation_value = _recording_copy(next_obs)
        info_value = copy_tree(info)
        reward_value = float(reward)
        success_value = bool(success)
        terminated_value = bool(terminated)
        truncated_value = bool(truncated)
        required_bytes = action_value.nbytes + universal_value.nbytes + tree_nbytes(observation_value)
        if self._bytes + required_bytes > self.config.max_buffer_bytes:
            raise MemoryError("recording buffer exceeds max_buffer_bytes")
        self._bytes += required_bytes
        self._actions.append(action_value)
        self._structured_controls.append(structured_control)
        self._universal_actions.append(universal_value)
        self._rewards.append(reward_value)
        self._successes.append(success_value)
        self._terminated.append(terminated_value)
        self._truncated.append(truncated_value)
        self._infos.append(info_value)
        self._observations.append(observation_value)

    def next_boundary_event_sequence(self, boundary_index: int) -> int:
        """Return the next event sequence at the current complete T/T+1 boundary."""
        if not self._active:
            raise RuntimeError("boundary events require an active recording")
        if type(boundary_index) is not int or boundary_index != len(self._actions):
            raise ValueError("boundary event must target the current control boundary")
        if len(self._observations) != len(self._actions) + 1:
            raise ValueError("boundary events require a complete T/T+1 recorder boundary")
        return sum(item.boundary_index == boundary_index for item in self._boundary_events)

    def validate_boundary_event(self, event: BoundaryEventV1) -> None:
        """Validate an event without changing the active recording."""
        if not self._active:
            raise RuntimeError("boundary events require an active recording")
        if not isinstance(event, BoundaryEventV1):
            raise TypeError("event must be BoundaryEventV1")
        event.validate()
        if event.boundary_index != len(self._actions):
            raise ValueError("boundary event must target the current control boundary")
        same_boundary = [item for item in self._boundary_events if item.boundary_index == event.boundary_index]
        if event.event_sequence != len(same_boundary):
            raise ValueError("boundary event sequence must be contiguous")
        if self._boundary_events and event.episode_id != self._boundary_events[0].episode_id:
            raise ValueError("boundary event episode identity mismatch")

    def add_boundary_event(self, event: BoundaryEventV1) -> None:
        """Append an event at the recorder's current real control boundary."""
        self.validate_boundary_event(event)
        self._boundary_events.append(event)

    def end_episode(
        self,
        reason: str,
        *,
        outcome: EpisodeOutcomeV1 | None = None,
        end_event: BoundaryEventV1 | None = None,
    ) -> FrozenTrajectory:
        if not self._active:
            raise RuntimeError("no active recording to end")
        if self.config.schema_version == "v3" and not isinstance(outcome, EpisodeOutcomeV1):
            raise ValueError("task-env-h5 v3 requires an explicit EpisodeOutcomeV1")
        candidate_events = list(self._boundary_events)
        if end_event is not None:
            if not isinstance(end_event, BoundaryEventV1):
                raise TypeError("end_event must be BoundaryEventV1 or None")
            if outcome is None:
                raise ValueError("end_event requires its EpisodeOutcomeV1")
            if end_event.event_type != "episode_ended":
                raise ValueError("final BoundaryEvent must use event_type='episode_ended'")
            if end_event.boundary_index != len(self._actions):
                raise ValueError("final BoundaryEvent must target the current control boundary")
            same_boundary = [item for item in candidate_events if item.boundary_index == end_event.boundary_index]
            if end_event.event_sequence != len(same_boundary):
                raise ValueError("final BoundaryEvent sequence must be contiguous")
            if candidate_events and end_event.episode_id != candidate_events[0].episode_id:
                raise ValueError("final BoundaryEvent episode identity mismatch")
            candidate_events.append(end_event)
        if outcome is not None:
            if not isinstance(outcome, EpisodeOutcomeV1):
                raise TypeError("outcome must be EpisodeOutcomeV1 or None")
            if outcome.end_reason != str(reason):
                raise ValueError("EpisodeOutcome end_reason must match recorder stop reason")
            validate_episode_records(candidate_events, outcome, len(self._actions))
        elif candidate_events != self._boundary_events:
            raise ValueError("BoundaryEvent finalizer requires EpisodeOutcomeV1")
        trajectory = FrozenTrajectory(
            tuple(self._observations),
            tuple(self._actions),
            tuple(self._universal_actions),
            tuple(self._rewards),
            tuple(self._successes),
            tuple(self._terminated),
            tuple(self._truncated),
            tuple(self._infos),
            self._reset_info,
            self._record_metadata,
            str(reason),
            tuple(self._structured_controls),
            tuple(candidate_events),
            outcome,
        )
        trajectory.validate()
        self._boundary_events = candidate_events
        self._outcome = outcome
        self._active = False
        self._frozen = trajectory
        return trajectory

    def save_h5(self, path: Path | str | None = None, name: str | None = None) -> Path:
        if self._frozen is None:
            raise RuntimeError("save_h5() requires a frozen trajectory")
        from .h5 import save_trajectory_h5
        output = save_trajectory_h5(self._frozen, self.config, path=path, name=name, index=self._save_index)
        self._save_index += 1
        return output


def mixed_control_transition(request, writer_control, target, applied_payload, stepwise_receipt):
    """Build and validate the structured recording projection for one interval."""
    writer_row = {
        **dict(writer_control),
        'controller_target': {
            'schema_version': target.schema_version,
            'payload': target.to_mapping(),
            'identity_hash': target.identity_hash,
        },
        'applied_control': {
            'schema_version': applied_payload['schema_version'],
            'payload': dict(applied_payload),
            'target_hash': applied_payload['target_hash'],
        },
    }
    if stepwise_receipt is not None:
        canonical_action = dict(writer_row['canonical_action'])
        canonical_action['physics_rate_control_v1'] = stepwise_receipt
        writer_row['canonical_action'] = canonical_action
    transition = StructuredControlTransitionV1(
        'structured-control-transition-v1', request, (writer_row,),
    )
    transition.validate()
    return transition


def begin_structured_recording(path, *, horizon, observation, reset_info, metadata_factory,
                               max_buffer_bytes=None):
    """Create a v3 recording and publish it only after begin_episode succeeds."""
    path = Path(path)
    if path.suffix != '.h5':
        path = path.with_name(path.name + '.h5')
    if path.exists():
        raise FileExistsError(path)
    # Fail before arming the episode if this interpreter cannot write H5.  A
    # missing dependency discovered after end_episode would leave a frozen
    # recording that cannot be finalized through the public Env again.
    import h5py  # noqa: F401
    config = {'schema_version': 'v3', 'max_transitions': max(horizon, 1)}
    if max_buffer_bytes is not None:
        config['max_buffer_bytes'] = max_buffer_bytes
    recorder = TransitionRecorder(RecorderConfig(**config))
    recorder.begin_episode(observation, dict(reset_info), metadata_factory())
    return path, recorder


def begin_selected_recording(env, path, *, adapter_path):
    """Choose the existing writer and prepare its metadata for one reset boundary."""
    if env.value.get('physical_execution') is not None or getattr(env, '_physical_reset_selection', None) is not None:
        from .physical_metadata import physical_action_group, physical_boundary_info, physical_record_metadata
        execution = env._physical_execution()
        if getattr(env, '_physical_reset_selection', None) is None:
            if (len(execution.controllers) != 1
                    or not all(key in env.binding.action_schema
                               for key in ('schema_id', 'mode', 'components'))):
                raise ValueError('physical recording requires one declared controller and action group')
            physical_action_group(execution)
        return begin_structured_recording(
            path, horizon=env.horizon, observation=env.obs,
            reset_info=physical_boundary_info(env, env.info),
            metadata_factory=lambda: physical_record_metadata(env))
    if getattr(env, 'position_profile', False):
        from .position_metadata import position_record_metadata
        return begin_structured_recording(
            path, horizon=env.horizon, observation=env.obs, reset_info=env._position_reset_info,
            metadata_factory=lambda: position_record_metadata(env, include_binding_provenance=True))

    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    from .reference_provenance import selected_recording_metadata, selected_source_provenance
    execution_configuration = env._recorded_execution_configuration()
    solution_identity = env._active_solution_identity()
    env._recording_adapter_source_sha256, provenance = selected_source_provenance(
        adapter_path=adapter_path, binding=env.binding, value=env.value, artifact=env.artifact,
        controller_identity=env._selected_controller.identity, solution_identity=solution_identity,
        execution_configuration=execution_configuration,
        execution_receipt=(env.get_execution_receipt()
                           if getattr(env, 'resolved_public_config', None) is not None else None))
    owners = env._owners()
    metadata, recipe = selected_recording_metadata(
        artifact=env.artifact, sample=env.sample, realized=env.realized,
        execution=env.execution, provider=env.provider, source_provenance=provenance,
        controller_identity=env._selected_controller.identity, solution_identity=solution_identity,
        action_schema=env.metadata['action_schema'],
        factory=type(env).__module__ + '.' + type(env).__name__,
        configuration=env.value['resolved_configuration'],
        execution_configuration=execution_configuration, owners=owners)
    if env.binding.recorder_mode == 'canonical':
        from ..trajectory.canonical.contracts import CanonicalRecorder
        return path, CanonicalRecorder(metadata, env._boundary())
    from ..trajectory.canonical.execution import ExecutionRecorder
    recorder = ExecutionRecorder(metadata, recipe, content_fields=('task_outcome',))
    recorder.boundary(env._boundary(), owners, 'reference', env.info['task_metrics'])
    return path, recorder


def finalize_structured_recording(recorder, path, episode_end, reason, *, position, camera=False):
    """Finalize and verify the existing v3 stream against its episode boundary."""
    from .h5 import load_camera_observations_h5, load_structured_control_records_h5

    outcome = episode_end.outcome
    allowed_reasons = {
        outcome.end_reason,
        str(episode_end.boundary_event.payload.get('requested_reason', '')),
    }
    if position and outcome.end_reason == 'horizon_reached':
        allowed_reasons.add('horizon')
    if str(reason) not in allowed_reasons:
        raise ValueError(
            'recording finalization reason disagrees with EpisodeOutcome' if position else
            'mixed-control recording finalization reason disagrees with EpisodeOutcome'
        )
    if recorder.transition_count != outcome.final_boundary:
        raise RuntimeError(
            'recording T does not match the last complete Position boundary; '
            'an incomplete interval cannot be finalized' if position else
            'mixed-control H5 T does not match the final complete control boundary'
        )
    trajectory = recorder.end_episode(
        outcome.end_reason, outcome=outcome, end_event=episode_end.boundary_event,
    )
    output = recorder.save_h5(path.parent, path.name)
    loaded = load_structured_control_records_h5(output)
    if (loaded['transition_count'] != trajectory.transition_count
            or loaded['observation_count'] != len(trajectory.observations)
            or loaded['outcome'] != outcome):
        raise ValueError('PositionServoV1 Generic H5 v3 readback mismatch' if position else
                         'mixed-control Generic H5 v3 structured-control readback mismatch')
    camera_result = None
    if camera:
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


__all__ = ["TransitionRecorder"]
