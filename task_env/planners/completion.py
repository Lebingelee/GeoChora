"""Provider-neutral completion values for frozen public-action stage plans."""
from dataclasses import dataclass
import numpy as np
from ..artifacts.contracts import Contract
from ..controllers.canonical.readiness import CanonicalControlReadiness
from ..utils.rotation import quat_wxyz_to_matrix, rotation_vector_error


@dataclass(frozen=True)
class ExpertExecutionInfo(Contract):
    schema_version: str
    control_step: int
    simulation_time: float
    control_readiness: CanonicalControlReadiness

    def validate(self):
        if self.schema_version != 'expert-execution-info-v1':
            raise ValueError('unsupported expert execution metadata')
        self.control_readiness.require_boundary(self.control_step, self.simulation_time)


@dataclass(frozen=True)
class StageCompletionPolicy(Contract):
    schema_version: str
    kind: str
    hold_ticks: int
    position_deadband_m: float
    rotation_deadband_rad: float
    collection_endpoint_m: float
    gripper_semantic_id: str
    failure_reason: str

    def validate(self):
        if self.schema_version != 'stage-completion-v1' or self.kind not in ('pose_ready', 'gripper_ready', 'task_outcome'):
            raise ValueError('unsupported stage completion policy')
        if self.hold_ticks < 0 or min(self.position_deadband_m, self.rotation_deadband_rad, self.collection_endpoint_m) <= 0:
            raise ValueError('invalid completion limits')

    def evaluate(self, ee_pose, target_pose, task_info, execution_info):
        if self.kind == 'task_outcome':
            return bool(task_info.get('is_success', False)) and float(task_info.get('task_metrics', {}).get('cube_lift', 0.)) >= self.collection_endpoint_m
        if self.kind == 'gripper_ready':
            gripper = execution_info.control_readiness.gripper
            if gripper.semantic_id != self.gripper_semantic_id:
                raise ValueError('unexpected semantic gripper binding')
            return gripper.close_ready
        current, target = np.asarray(ee_pose), np.asarray(target_pose)
        if not np.isfinite(current).all() or not np.isfinite(target).all():
            raise ValueError('nonfinite public pose')
        position = np.linalg.norm(current[:3] - target[:3])
        rotation = np.linalg.norm(rotation_vector_error(quat_wxyz_to_matrix(current[3:7]), quat_wxyz_to_matrix(target[3:7])))
        return bool(position <= self.position_deadband_m and rotation <= self.rotation_deadband_rad)
