"""Independent R1 arm and hand writers for one assembled Panda interval."""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
import numpy as np

from .contracts import CanonicalControlTarget, GripperControlTarget, digest
from .feedback import CanonicalControlFeedback
from .kinematics import ARM, FINGERS, PandaKinematics
from .controller import CanonicalPandaController

ARM_WRITER = 'panda-arm-position-writer'
HAND_WRITER = 'panda-hand-position-writer'


@dataclass(frozen=True)
class SplitPositionBundleV1:
    """Actual independently computed component outputs underlying one native target."""
    arm_identity: str
    hand_identity: str
    arm_position: tuple[float, ...]
    arm_servo_position: tuple[float, ...]
    gripper: GripperControlTarget
    target_hash: str

    @property
    def arm_hash(self):
        return digest({'schema': 'panda-arm-position-output-v1', 'controller': self.arm_identity,
                       'joint_order': ARM, 'position': self.arm_position, 'servo_position': self.arm_servo_position})

    @property
    def hand_hash(self):
        return digest({'schema': 'panda-hand-position-output-v1', 'controller': self.hand_identity,
                       'target': self.gripper.to_mapping()})

    def validate_target(self, target, plan):
        expected = {ARM_WRITER: self.arm_identity, HAND_WRITER: self.hand_identity}
        actual = {item.writer_id: item.controller_identity for item in plan.controller_bindings}
        if actual != expected or target.controller_identity != split_identity(self.arm_identity, self.hand_identity):
            raise ValueError('split Position owners differ from the source-bound plan')
        if (target.identity_hash != self.target_hash or tuple(target.arm_joint_order) != tuple(ARM)
                or tuple(target.arm_position[name] for name in ARM) != self.arm_position
                or tuple(target.arm_servo_position[name] for name in ARM) != self.arm_servo_position
                or target.gripper != self.gripper):
            raise ValueError('split Position outputs differ from the native target')


def split_identity(arm_identity, hand_identity):
    return digest({'schema': 'panda-split-position-controller-v1',
                   'arm_controller': arm_identity, 'hand_controller': hand_identity})


class PandaArmPositionControllerV1:
    writer_id = ARM_WRITER

    def __init__(self, model, artifact_hash, config):
        self.controller = CanonicalPandaController(model, artifact_hash=artifact_hash, config=config)
        self.identity = digest({'schema': 'panda-arm-position-controller-v1',
                                'writer': self.writer_id, 'arm': self.controller.identity})
        self._expected_step = None

    def reset(self, state):
        self._expected_step = state.control_step

    def compute(self, state, request):
        if self._expected_step is None or state.control_step != self._expected_step:
            raise RuntimeError('arm Controller requires reset and one compute per boundary')
        canonical, desired, servo = self.controller._compute_arm(state, request)
        self._expected_step += 1
        return canonical, tuple(map(float, desired)), tuple(map(float, servo))


class PandaHandPositionControllerV1:
    writer_id = HAND_WRITER

    def __init__(self, config, gripper_config, artifact_hash):
        from ...environment import GripperConfig
        if not isinstance(gripper_config, GripperConfig):
            raise TypeError('resolved RobotConfig.gripper required')
        self.config, self.gripper_config = config, gripper_config
        self.gripper_semantic_id = 'panda-v1/gripper'
        if (gripper_config.kind != 'experimental_rate_limited'
                or gripper_config.force_deadband_N >= gripper_config.force_limit_N):
            raise ValueError('split hand Controller requires the admitted R1 gripper law')
        self.identity = digest({'schema': 'panda-hand-position-controller-v1',
            'writer': self.writer_id, 'artifact': artifact_hash, 'gripper': asdict(gripper_config),
            'opening_range_m': config.gripper_opening_range_m,
            'position_stiffness_N_per_m': config.gripper_position_stiffness_N_per_m,
            'feedback': 'nonnegative_closing_magnitude_completed_interval'})
        self._expected_step = None

    def _feedback(self, state, feedback):
        if not isinstance(feedback, CanonicalControlFeedback):
            raise TypeError('CanonicalControlFeedback required')
        feedback.require_state(state, self.gripper_semantic_id, FINGERS)

    def reset(self, state, feedback):
        self._feedback(state, feedback)
        self._commanded = float(np.clip(feedback.gripper.opening_m, 0, self.config.gripper_opening_range_m))
        self._desired = self._commanded
        self._force_mode = self._force_initialized = False
        self._expected_step = state.control_step

    def compute(self, state, feedback, gripper_scalar):
        self._feedback(state, feedback)
        if self._expected_step is None or state.control_step != self._expected_step:
            raise RuntimeError('hand Controller requires reset and one compute per boundary')
        from .r1_gripper import advance_r1_gripper
        target = advance_r1_gripper(self, feedback, gripper_scalar)
        self._expected_step += 1
        return target

    def readiness(self, state, feedback):
        from .readiness import CanonicalControlReadiness, GripperReadiness
        self._feedback(state, feedback)
        if self._expected_step is None or state.control_step != self._expected_step:
            raise ValueError('readiness requires current observed hand Controller boundary')
        force = feedback.gripper.closing_force_N
        error = self.gripper_config.force_limit_N - force
        ready = self._force_mode and self._force_initialized and error <= self.gripper_config.force_deadband_N
        return CanonicalControlReadiness('canonical-control-readiness-v1', state.control_step,
            state.simulation_time, GripperReadiness(self.gripper_semantic_id, bool(ready), force,
                self.gripper_config.force_limit_N, error))


class SplitPandaPositionControllerV1:
    """Coordinate two independent owners while retaining the existing native target."""
    control_submission_capabilities = frozenset({'canonical-position-target-v1'})

    def position_binding_requirements(self):
        """Declare each owner's group, action and cross-entity feedback needs."""
        return (
            (self.arm, (0,), (0, 1, 2, 3, 4, 5, 6), 'absolute_pose', True),
            (self.hand, (1,), (7,), 'absolute_joint', False),
        )

    def __init__(self, artifact, source):
        if source.task_artifact_hash != artifact.identity_hash:
            raise ValueError('source/Artifact mismatch')
        self.config = source.config.action
        self.gripper_config = source.config.robot.gripper
        self.gripper_semantic_id = 'panda-v1/gripper'
        self.arm = PandaArmPositionControllerV1(PandaKinematics(source.scene_source.xml), artifact.identity_hash, self.config)
        self.hand = PandaHandPositionControllerV1(self.config, self.gripper_config, artifact.identity_hash)
        self.identity = split_identity(self.arm.identity, self.hand.identity)
        self.artifact_hash = artifact.identity_hash
        self.last_split_bundle = None

    def position_output_bundle(self, target, plan):
        """Publish both live Controller outputs through the common writer contract."""
        from .position_outputs import PositionOutputBundleV1, PositionWriterOutputV1

        bundle = self.last_split_bundle
        if (type(bundle) is not SplitPositionBundleV1
                or type(self.arm) is not PandaArmPositionControllerV1
                or type(self.hand) is not PandaHandPositionControllerV1
                or self.arm.identity != bundle.arm_identity
                or self.hand.identity != bundle.hand_identity):
            raise ValueError('split Position outputs do not belong to the live Controller owners')
        bundle.validate_target(target, plan)
        return PositionOutputBundleV1(target.identity_hash, target.controller_identity, (
            PositionWriterOutputV1(ARM_WRITER, bundle.arm_identity, bundle.arm_hash,
                                   'arm-position-target', ('rad',)),
            PositionWriterOutputV1(HAND_WRITER, bundle.hand_identity, bundle.hand_hash,
                                   'hand-position-target', ('m',)),
        ))

    def reset(self, state, feedback):
        self.hand.reset(state, feedback)
        self.arm.reset(state)
        self.last_split_bundle = None

    @property
    def source_artifact_hash(self):
        return self.arm.controller.artifact_hash

    @property
    def source_xml_sha256(self):
        return self.arm.controller.model.source_sha256

    def readiness(self, state, feedback):
        return self.hand.readiness(state, feedback)

    def compute(self, state, feedback, requested):
        requested.validate()
        # Reject stale feedback or either stale owner before the first owner
        # can mutate its boundary cursor or target memory.
        self.hand._feedback(state, feedback)
        if (self.arm._expected_step is None or self.hand._expected_step is None
                or self.arm._expected_step != state.control_step
                or self.hand._expected_step != state.control_step):
            raise RuntimeError('split Position owners require one current reset boundary')
        # The legacy arm solver accepts an eight-component request even
        # though its arm calculation uses only the first seven. Give it a
        # fixed placeholder and send the real gripper input only to hand.
        arm_request = replace(requested, values=(*requested.values[:-1], 0.0))
        arm_action, desired, servo = self.arm.compute(state, arm_request)
        hand_scalar = float(np.clip(requested.values[-1], -1., 1.))
        canonical = replace(arm_action, requested=requested,
            interpreted_values=(*arm_action.interpreted_values[:-1], hand_scalar),
            clipped=bool(arm_action.clipped or hand_scalar != requested.values[-1]))
        hand = self.hand.compute(state, feedback, hand_scalar)
        target = CanonicalControlTarget('canonical-control-v0', self.artifact_hash, self.identity,
            ARM, dict(zip(ARM, desired, strict=True)), dict(zip(ARM, servo, strict=True)), hand)
        self.last_split_bundle = SplitPositionBundleV1(self.arm.identity, self.hand.identity,
                                                       desired, servo, hand, target.identity_hash)
        return canonical, target
