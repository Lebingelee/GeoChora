"""Internal binding between selected task semantics and the environment."""

from dataclasses import dataclass
from typing import Callable
from ..controllers.canonical.contracts import reference_pose_action, reference_pose_action_space


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
    native_sample_factory: Callable | None = None
    native_interval_receipt_factory: Callable | None = None
    control_request_required: bool = False
    external_solution_actions: bool = False
    expert_uses_public_observation: bool = False
    build_external: Callable | None = None
    validate_external_solution: Callable | None = None
    runtime_episode_identity: bool = False
    build_gripper_cadence_diagnostic: Callable | None = None
    build_seeded: Callable | None = None
    build_native_feedback_profile: Callable | None = None
    build_mixed_control_profile: Callable | None = None
    reset_sample_with_options: Callable | None = None
    prepare_mixed_control: Callable | None = None
    prepare_mixed_control_substep: Callable | None = None
    observe_mixed_control: Callable | None = None
    mixed_record_metadata: Callable | None = None
    pre_reset_session_validator: Callable | None = None
    post_reset_session_validator: Callable | None = None
    close_task_resources: Callable | None = None
    action_schema: dict | None = None
    action_space_factory: Callable = reference_pose_action_space
    prepare_action: Callable = reference_pose_action
    position_execution_info: Callable | None = None
    position_execution_info_key: str | None = None
    reset_runtime_input: Callable | None = None
    position_gripper_binding: Callable | None = None

    def __post_init__(self):
        if not callable(self.action_space_factory) or not callable(self.prepare_action):
            raise TypeError('selected action space and action preparation must be callable')
        if self.action_schema is not None and not isinstance(self.action_schema, dict):
            raise TypeError('selected task action schema must be a dictionary')
        if self.interval_mode not in {"grouped", "native"}:
            raise ValueError("unknown selected control-interval requirement")
        if self.recorder_mode not in {"canonical", "execution"}:
            raise ValueError("unknown selected recording requirement")
        if ((self.position_execution_info is None) != (self.position_execution_info_key is None)
                or (self.position_execution_info is not None
                    and (not callable(self.position_execution_info)
                         or not isinstance(self.position_execution_info_key, str)
                         or not self.position_execution_info_key))):
            raise ValueError('position execution info requires a callable and nonempty result key')
        if (self.build_external is None) != (self.validate_external_solution is None):
            raise ValueError('external Solution construction and validation must be supplied together')
        if (self.native_sample_factory is None) != (self.native_interval_receipt_factory is None):
            raise ValueError('native sample and interval receipt factories must be supplied together')
        if self.reset_runtime_input is not None and not callable(self.reset_runtime_input):
            raise ValueError('reset runtime input selector must be callable when supplied')
        if self.position_gripper_binding is not None and not callable(self.position_gripper_binding):
            raise ValueError('position gripper selector must be callable when supplied')
        if self.close_task_resources is not None and not callable(self.close_task_resources):
            raise ValueError('task resource cleanup hook must be callable when supplied')
        if self.control_request_required and self.native_sample_factory is None:
            raise ValueError('native controller requests require the selected native sample contract')
        if self.external_solution_actions and not self.control_request_required:
            raise ValueError('caller-driven Solution actions require the native control request contract')
        mixed_hooks = (
            self.build_mixed_control_profile, self.reset_sample_with_options,
            self.prepare_mixed_control, self.observe_mixed_control,
            self.mixed_record_metadata, self.pre_reset_session_validator,
        )
        if any(value is not None for value in mixed_hooks) and any(
            not callable(value) for value in mixed_hooks
        ):
            raise ValueError('mixed-control binding requires its complete task-owned hook set')
        if (self.prepare_mixed_control_substep is not None
                and not callable(self.prepare_mixed_control_substep)):
            raise ValueError('mixed-control substep preparation hook must be callable when supplied')
        if (self.post_reset_session_validator is not None
                and not callable(self.post_reset_session_validator)):
            raise ValueError('post-reset session validator must be callable when supplied')
