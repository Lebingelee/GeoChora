"""Opt-in semantic control admission; legacy no-control materialize unchanged."""
from dataclasses import dataclass
from typing import Protocol
from .api import RuntimeSession
from ...controllers.canonical.contracts import CanonicalControlTarget, AppliedCanonicalControl
from ...artifacts import RequiredCapabilitySet,admit_capabilities
from .api import materialize,provider_manifest

class ControlledRuntimeSession(RuntimeSession, Protocol):
    def apply_control(self, target: CanonicalControlTarget) -> AppliedCanonicalControl: ...


CONTROL_REQUIRED=RequiredCapabilitySet(('articulated_robot','joint_position_actuation','joint_state_query','body_pose_query','frame_pose_query'))


@dataclass(frozen=True)
class ControlBinding:
    gripper_semantic_id: str
    opening_range_m: float

    def __post_init__(self):
        from ...artifacts.contracts import _name
        _name(self.gripper_semantic_id)
        if self.opening_range_m!=.08:raise ValueError('only audited 0.08m tendon gripper mapping implemented')


def materialize_control(artifact,execution,*,source,binding,manifest=None):
    if manifest is not None:admit_capabilities(CONTROL_REQUIRED,manifest,execution)
    admit_capabilities(CONTROL_REQUIRED,provider_manifest(execution.physics_provider),execution)
    if len(source.joint_targets)!=7 or len(source.open_actuators)!=1:raise ValueError('unsupported control source bindings')
    session=materialize(artifact,execution,source=source,manifest=manifest)
    session._control_binding=binding
    return session


def validate_target(session,target):
    if not isinstance(target, CanonicalControlTarget):raise TypeError("CanonicalControlTarget required")
    session._require_reset()
    if not hasattr(session,'_control_binding'):raise ValueError('control session admission required')
    if (target.task_artifact_hash!=session._artifact.identity_hash or set(target.arm_joint_order)!=set(session._target_actuators)
        or target.gripper.semantic_id!=session._control_binding.gripper_semantic_id):raise ValueError('canonical control binding mismatch')
