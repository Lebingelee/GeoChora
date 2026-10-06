"""Four immutable semantic control layers, independent of native storage."""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib,json
from ...artifacts.contracts import Contract,PoseWorld,_name


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class RequestedAction(Contract):
    mode: str
    reference: str | None
    rotation_representation: str
    values: tuple[float,...]

    def validate(self):
        allowed={'absolute_joint':{None},'absolute_pose':{'world','base'},'delta_pose':{'world','base','ee'}}
        if self.mode not in allowed or self.reference not in allowed[self.mode]:raise ValueError('invalid action mode/reference')
        if self.rotation_representation not in ({'none'} if self.mode=='absolute_joint' else {'quaternion_wxyz','rotvec'}):raise ValueError('invalid rotation')
        size=8 if self.mode=='absolute_joint' or self.rotation_representation=='quaternion_wxyz' else 7
        if len(self.values)!=size:raise ValueError('invalid action shape')


@dataclass(frozen=True)
class CanonicalAction(Contract):
    schema_version: str
    requested: RequestedAction
    interpreted_values: tuple[float,...]
    clipped: bool
    resolved_world_pose: PoseWorld | None

    def validate(self):
        if self.schema_version!='canonical-action-v0' or len(self.interpreted_values)!=len(self.requested.values):raise ValueError('invalid canonical action')
        if not -1<=self.interpreted_values[-1]<=1:raise ValueError('invalid gripper scalar')
        if (self.requested.mode=='absolute_joint') != (self.resolved_world_pose is None):raise ValueError('pose interpretation mismatch')


@dataclass(frozen=True)
class GripperControlTarget(Contract):
    semantic_id: str
    opening_m: float
    force_limit_N: float
    servo_opening_m: float

    def validate(self):
        _name(self.semantic_id)
        if not 0<=self.opening_m<=.08 or not 0<=self.servo_opening_m<=.08 or self.force_limit_N<=0:raise ValueError('invalid physical gripper target')


@dataclass(frozen=True)
class CanonicalControlTarget(Contract):
    schema_version: str
    task_artifact_hash: str
    controller_identity: str
    arm_joint_order: tuple[str,...]
    arm_position: Mapping[str,float]
    arm_servo_position: Mapping[str,float]
    gripper: GripperControlTarget

    def validate(self):
        if self.schema_version!='canonical-control-v0' or len(self.task_artifact_hash)!=64:raise ValueError('invalid control schema/link')
        if len(self.arm_joint_order)!=7 or len(set(self.arm_joint_order))!=7 or set(self.arm_joint_order)!=set(self.arm_position) or set(self.arm_position)!=set(self.arm_servo_position):raise ValueError('seven semantic arm joints required')
        for name in self.arm_joint_order:_name(name)

    @property
    def identity_hash(self):return digest(self.to_mapping())


@dataclass(frozen=True)
class AppliedCanonicalControl(Contract):
    schema_version: str
    target_hash: str
    provider_name: str
    arm_servo_position: Mapping[str,float]
    gripper_servo_opening_m: float
    gripper_force_limit_N: float
    clipped: bool
    mapping: str

    def validate(self):
        if self.schema_version!='applied-canonical-control-v0' or len(self.target_hash)!=64:raise ValueError('invalid applied schema')
        for name in self.arm_servo_position:_name(name)
        if self.gripper_force_limit_N<=0 or not 0<=self.gripper_servo_opening_m<=.08:raise ValueError('invalid applied gripper')
