"""Source-bound, force-free Panda position profile for the C02b candidate."""
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from types import SimpleNamespace

from ...artifacts import (
    FrameReference,
    SceneDefinition,
    StateFieldRequirement,
    StateRequirements,
    TaskArtifactV1,
)
from ...environment import ActionConfig
from ...environment.types import ActionModeSpec
from ...runtime.sessions.control import (
    ControlGroupActionProjectionV1,
    ControllerBindingV1,
    _schema_hash,
)
from ...runtime.sessions.source import project_scene_definition_v3_to_mjcf
from .contracts import PositionControlTargetV1, RequestedAction, digest
from .controller import CanonicalPandaController
from .kinematics import (
    ARM,
    FINGERS,
    PANDA_HAND_ORIGIN_TCP_V1,
    PandaKinematics,
)


POSITION_PROFILE_ID = 'panda-main/position-servo-v1'
POSITION_GRIPPER_SEMANTIC = 'panda-main/gripper'
_JOINT_IDS = tuple(f'joint{index}' for index in range(1, 8)) + (
    'finger_joint1', 'finger_joint2',
)
_EXPECTED_JOINT_BINDINGS = {
    f'panda-main/{joint_id}': joint_id for joint_id in _JOINT_IDS
}
_EXPECTED_TARGET_BINDINGS = {
    f'panda-main/joint{index}': f'actuator{index}' for index in range(1, 8)
}


def position_state_requirements(writer_id: str = POSITION_PROFILE_ID) -> StateRequirements:
    """The exact force-free state consumed by the position profile."""

    requirements = [
        StateFieldRequirement(
            'state-field-requirement-v1', 'joint_position', 'joint',
            'panda-main', joint_id, 'required', 'evaluation_boundary',
            'joint-definition', 'joint_state_query',
        )
        for joint_id in _JOINT_IDS
    ]
    requirements.append(StateFieldRequirement(
        'state-field-requirement-v1', 'frame_pose_world', 'frame',
        'panda-main', 'hand', 'required', 'evaluation_boundary',
        'meter+quaternion_wxyz', 'frame_pose_query',
    ))
    return StateRequirements('state-requirements-v1', 'controller', writer_id, tuple(requirements))


def _action_schema():
    return ActionModeSpec.from_controller_config(SimpleNamespace(
        kind='absolute_pose', reference='world',
        rotation_representation='quaternion_wxyz',
    ))


def _scene_joint_map(scene: SceneDefinition):
    return {
        (joint.parent_frame.entity_id, joint.joint_id): joint
        for articulation in scene.articulations or ()
        for joint in articulation.joints
    }


def _source_binding_snapshot(source):
    return {
        'joints': dict(sorted(source.joints.items())),
        'bodies': dict(sorted(source.bodies.items())),
        'frames': dict(sorted(source.frames.items())),
        'joint_targets': dict(sorted(source.joint_targets.items())),
        'open_actuators': tuple(source.open_actuators),
    }


class PandaPositionServoProfileV1:
    """Independent one-writer profile reusing the canonical position algorithm."""

    profile_id = POSITION_PROFILE_ID
    writer_id = POSITION_PROFILE_ID
    tcp_profile = PANDA_HAND_ORIGIN_TCP_V1

    def __init__(self, *, artifact, source, scene, model, config):
        self.artifact = artifact
        self.source = source
        # RuntimeSource is frozen but its mapping fields are mutable dictionaries.
        # Keep the construction-time mapping snapshot bound to Controller identity.
        self._source_bindings = _source_binding_snapshot(source)
        self.scene = scene
        self.config = config
        self.model = model
        self._algorithm = CanonicalPandaController(
            model, artifact_hash=artifact.identity_hash, config=config,
        )
        self.requirements = position_state_requirements(self.writer_id)
        self.identity = digest({
            'schema': 'panda-main-position-servo-v1',
            'profile_id': self.profile_id,
            'writer_id': self.writer_id,
            'task_artifact_identity_hash': artifact.identity_hash,
            'scene_identity_hash': scene.identity_hash,
            'source_closure_digest': source.source_closure_digest,
            'materialized_xml_sha256': model.source_sha256,
            'runtime_source_bindings': self._source_bindings,
            'tcp_profile': self.tcp_profile.to_mapping(),
            'action_config': asdict(config),
            'action_schema_identity': _schema_hash(asdict(_action_schema())),
            'timebase': {
                'physics_dt': artifact.timebase.physics_dt,
                'control_substeps': artifact.timebase.control_substeps,
                'control_dt': artifact.timebase.control_dt,
            },
            'algorithm_identity': self._algorithm.identity,
            'gripper_semantic_id': POSITION_GRIPPER_SEMANTIC,
            'required_state': self.requirements.to_mapping(),
            'force_feedback': 'not-consumed-v1',
        })
        self._plan_identity_hash = None
        self._episode_id = None
        self._reset_sample_id = None
        self._next_control_step = None

    def _validate_source(self, source):
        expected_source_id = f'{self.scene.schema_version}:{self.scene.identity_hash}'
        if (source.task_artifact_hash != self.artifact.identity_hash
                or source.source_closure_digest != self.source.source_closure_digest
                or source.scene_definition is None
                or source.scene_definition.identity_hash != self.scene.identity_hash
                or source.scene_source.source_id != expected_source_id
                or _source_binding_snapshot(source) != self._source_bindings):
            raise ValueError('PositionServoV1 RuntimeSource identity or bindings changed after construction')

    @classmethod
    def from_source(cls, artifact, source, *, config: ActionConfig | None = None):
        if not isinstance(artifact, TaskArtifactV1):
            raise TypeError('PositionServoV1 requires TaskArtifactV1')
        if artifact.timebase.physics_dt != 0.002 or artifact.timebase.control_substeps != 5 or artifact.timebase.control_dt != 0.01:
            raise ValueError('PositionServoV1 requires 100 Hz outer / five 2 ms native steps')
        if source.task_artifact_hash != artifact.identity_hash:
            raise ValueError('PositionServoV1 source/Artifact identity mismatch')
        scene = source.scene_definition
        if not isinstance(scene, SceneDefinition) or scene.identity_hash != artifact.scene_identity_hash:
            raise ValueError('PositionServoV1 requires the exact TaskArtifact Scene source')
        if source.scene_source.source_id != f'{scene.schema_version}:{scene.identity_hash}':
            raise ValueError('PositionServoV1 source ID is not bound to its Scene')
        if not isinstance(source.source_closure_digest, str) or len(source.source_closure_digest) != 64:
            raise ValueError('PositionServoV1 requires a source closure digest')
        if dict(source.joints) != _EXPECTED_JOINT_BINDINGS:
            raise ValueError('PositionServoV1 requires exact Panda arm/finger Joint source bindings')
        if source.bodies.get('panda-main/hand') != 'hand':
            raise ValueError('PositionServoV1 hand state must bind to the actual hand body')
        if dict(source.joint_targets) != _EXPECTED_TARGET_BINDINGS or tuple(source.open_actuators) != ('actuator8',):
            raise ValueError('PositionServoV1 requires exact actuator1–7 and actuator8 source bindings')

        config = config or getattr(source.config, 'action', None) or ActionConfig()
        if not isinstance(config, ActionConfig):
            raise TypeError('PositionServoV1 requires the existing ActionConfig')
        materialized_xml = project_scene_definition_v3_to_mjcf(
            source.scene_source.xml, scene,
        )
        model = PandaKinematics(materialized_xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
        return cls(artifact=artifact, source=source, scene=scene, model=model, config=config)

    def controller_binding(self):
        return ControllerBindingV1(
            'controller-binding-v1', self.writer_id, _action_schema(),
            'panda-position-feedback', 'panda-position-state-v1',
            self.requirements,
            (
                ControlGroupActionProjectionV1(
                    'control-group-action-projection-v1', 'panda-main', 'arm',
                    ('x', 'y', 'z', 'qw', 'qx', 'qy', 'qz'),
                ),
                ControlGroupActionProjectionV1(
                    'control-group-action-projection-v1', 'panda-main', 'gripper',
                    ('gripper',),
                ),
            ),
        )

    def _validate_plan(self, plan):
        from ...runtime.sessions.control import ControlBindingPlanV1

        if not isinstance(plan, ControlBindingPlanV1) or not plan._compiled:
            raise ValueError('PositionServoV1 requires a compiled ControlBindingPlanV1')
        if plan.scene_identity_hash != self.scene.identity_hash:
            raise ValueError('PositionServoV1 plan/Scene identity mismatch')
        bindings = tuple(item for item in plan.controller_bindings if item.writer_id == self.writer_id)
        if len(bindings) != 1 or len(plan.controller_bindings) != 1:
            raise ValueError('PositionServoV1 requires one complete writer')
        if bindings[0].feedback_requirements.to_mapping() != self.requirements.to_mapping():
            raise ValueError('PositionServoV1 plan Required State mismatch')
        expected_resources = {
            ('panda-main', f'actuator{index}', self.writer_id) for index in range(1, 9)
        }
        if set(plan.resource_writers) != expected_resources:
            raise ValueError('PositionServoV1 plan actuator mapping mismatch')
        return plan.identity_hash

    def _adapt_publication(self, publication):
        from ...artifacts.state import CanonicalStatePublicationV1

        if not isinstance(publication, CanonicalStatePublicationV1):
            raise TypeError('PositionServoV1 consumes CanonicalStatePublicationV1')
        publication.validate()
        view = publication.view
        view.validate_against_scene(self.scene)
        view.validate_requirements(self.requirements)
        if view.boundary.scene_identity_hash != self.scene.identity_hash:
            raise ValueError('PositionServoV1 state boundary/Scene identity mismatch')
        if view.sample_clock.clock_domain != 'evaluation_boundary' or (
            view.sample_clock.sample_index != view.boundary.control_step
        ):
            raise ValueError('PositionServoV1 requires an evaluation-boundary state sample')

        joints = {
            value.joint_id: value
            for value in view.joints if value.entity_id == 'panda-main'
        }
        if set(joints) != set(_JOINT_IDS):
            raise ValueError('PositionServoV1 typed Panda Joint state is incomplete or ambiguous')
        definitions = _scene_joint_map(self.scene)
        expected_position_representation = {
            **{f'joint{index}': ('revolute', 'radian') for index in range(1, 8)},
            'finger_joint1': ('prismatic', 'meter'),
            'finger_joint2': ('prismatic', 'meter'),
        }
        joint_position = {}
        for joint_id, value in joints.items():
            definition = definitions.get(('panda-main', joint_id))
            if definition is None:
                raise ValueError(f'PositionServoV1 Scene is missing Joint {joint_id!r}')
            value.validate_against(definition)
            if (definition.kind, definition.position_representation) != expected_position_representation[joint_id]:
                raise ValueError(f'PositionServoV1 Joint {joint_id!r} has unexpected unit/coordinate')
            if len(value.position) != 1 or not math.isfinite(value.position[0]):
                raise ValueError(f'PositionServoV1 Joint {joint_id!r} is not a finite scalar')
            joint_position[f'panda-v1/{joint_id}'] = float(value.position[0])

        hand_values = [
            value for value in view.frames
            if value.frame.entity_id == 'panda-main' and value.frame.frame_id == 'hand'
        ]
        if len(hand_values) != 1:
            raise ValueError('PositionServoV1 requires exactly one typed panda-main/hand Frame')
        frame = hand_values[0]
        expected_reference = FrameReference('panda-main', 'hand')
        if frame.frame != expected_reference:
            raise ValueError('PositionServoV1 typed hand Frame identity mismatch')
        # TCP profile v1 is the identity transform hand→TCP; both the typed
        # Controller input and PandaKinematics tip therefore name this same body.
        state = SimpleNamespace(
            joint_position=joint_position,
            pose_world={'panda-v1/ee': frame.pose_world},
        )
        return state

    def reset(self, publication, plan):
        self._validate_source(self.source)
        plan_identity = self._validate_plan(plan)
        self._adapt_publication(publication)
        boundary = publication.view.boundary
        clock = publication.view.sample_clock
        if boundary.control_step != 0 or clock.sample_index != 0 or clock.simulation_time_s != 0.0:
            raise ValueError('PositionServoV1 reset requires the initial evaluation boundary')
        self._plan_identity_hash = plan_identity
        self._episode_id = boundary.episode_id
        self._reset_sample_id = boundary.reset_sample_id
        self._next_control_step = 0
        return boundary.boundary_id

    def compute(self, publication, requested: RequestedAction, plan):
        self._validate_source(self.source)
        plan_identity = self._validate_plan(plan)
        if self._next_control_step is None or self._plan_identity_hash != plan_identity:
            raise RuntimeError('PositionServoV1 reset is required for this binding plan')
        if not isinstance(requested, RequestedAction):
            raise TypeError('PositionServoV1 compute requires RequestedAction')
        requested.validate()
        state = self._adapt_publication(publication)
        boundary = publication.view.boundary
        if (boundary.episode_id != self._episode_id
                or boundary.reset_sample_id != self._reset_sample_id
                or boundary.control_step != self._next_control_step):
            raise ValueError('PositionServoV1 target source boundary is stale or out of order')

        canonical, base_target = self._algorithm.compute(state, requested)
        # The shared legacy position algorithm consumes panda-v1 semantic
        # names. The v1 Artifact and RuntimeSource use entity-qualified
        # panda-main identities; lower the same seven values back to those
        # source Joint keys before the existing RuntimeSession applies them.
        source_order = tuple(f'panda-main/joint{index}' for index in range(1, 8))
        algorithm_order = tuple(f'panda-v1/joint{index}' for index in range(1, 8))
        target = replace(
            base_target,
            arm_joint_order=source_order,
            arm_position={source: base_target.arm_position[algorithm]
                          for source, algorithm in zip(source_order, algorithm_order, strict=True)},
            arm_servo_position={source: base_target.arm_servo_position[algorithm]
                                for source, algorithm in zip(source_order, algorithm_order, strict=True)},
            controller_identity=self.identity,
            gripper=replace(base_target.gripper, semantic_id=POSITION_GRIPPER_SEMANTIC),
        )
        bound_target = PositionControlTargetV1(
            'position-control-target-v1', self.writer_id, self.identity,
            plan_identity, self.source.source_closure_digest,
            boundary, publication.view.sample_clock, target,
        )
        self._next_control_step += 1
        return canonical, bound_target
