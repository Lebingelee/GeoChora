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
_ALGORITHM_JOINTS = tuple(f'joint{index}' for index in range(1, 8))
_ALGORITHM_FINGERS = ('finger_joint1', 'finger_joint2')


def position_state_requirements(
    writer_id: str = POSITION_PROFILE_ID,
    *,
    entity_id: str = 'panda-main',
    joint_ids: tuple[str, ...] | None = None,
    hand_frame_id: str = 'hand',
) -> StateRequirements:
    """The exact force-free state consumed by the position profile."""
    joint_ids = tuple(joint_ids or _JOINT_IDS)
    requirements = [
        StateFieldRequirement(
            'state-field-requirement-v1', 'joint_position', 'joint',
            entity_id, joint_id, 'required', 'evaluation_boundary',
            'joint-definition', 'joint_state_query',
        )
        for joint_id in joint_ids
    ]
    requirements.append(StateFieldRequirement(
        'state-field-requirement-v1', 'frame_pose_world', 'frame',
        entity_id, hand_frame_id, 'required', 'evaluation_boundary',
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
    """One Entity-bound writer reusing the canonical Panda position algorithm."""

    profile_id = POSITION_PROFILE_ID
    writer_id = POSITION_PROFILE_ID
    tcp_profile = PANDA_HAND_ORIGIN_TCP_V1

    def __init__(
        self, *, artifact, source, scene, model, config,
        entity_id='panda-main', joint_ids=None, finger_joint_ids=None,
        hand_frame_id='hand', native_prefix='', actuator_prefix='', tcp_profile=None,
    ):
        self.artifact = artifact
        self.source = source
        # RuntimeSource is frozen but its mapping fields are mutable dictionaries.
        # Keep the construction-time mapping snapshot bound to Controller identity.
        self._source_bindings = _source_binding_snapshot(source)
        self.scene = scene
        self.config = config
        self.model = model
        self.entity_id = entity_id
        self.joint_ids = tuple(joint_ids or _ALGORITHM_JOINTS)
        self.finger_joint_ids = tuple(finger_joint_ids or _ALGORITHM_FINGERS)
        if len(self.joint_ids) != 7 or len(set(self.joint_ids)) != 7:
            raise ValueError('PositionServoV1 requires seven distinct Entity-qualified arm Joints')
        if len(self.finger_joint_ids) != 2 or len(set(self.finger_joint_ids)) != 2:
            raise ValueError('PositionServoV1 requires two distinct Entity-qualified finger Joints')
        self.hand_frame_id = hand_frame_id
        self.native_prefix = native_prefix
        self.actuator_prefix = actuator_prefix
        self.profile_id = POSITION_PROFILE_ID if entity_id == 'panda-main' else f'{entity_id}/position-servo-v1'
        self.writer_id = self.profile_id
        if tcp_profile is None:
            from .kinematics import PandaTcpProfileV1
            tcp_profile = PandaTcpProfileV1(
                'panda-tcp-profile-v1', f'{entity_id}/hand-origin-tcp-v1',
                hand_frame_id, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0),
            )
        self.tcp_profile = tcp_profile
        self._source_joint_ids = self.joint_ids + self.finger_joint_ids
        self._algorithm_joint_by_id = {
            joint_id: f'panda-v1/{algorithm_id}'
            for joint_id, algorithm_id in zip(self.joint_ids, _ALGORITHM_JOINTS, strict=True)
        }
        self._algorithm_joint_by_id.update({
            joint_id: f'panda-v1/{algorithm_id}'
            for joint_id, algorithm_id in zip(self.finger_joint_ids, _ALGORITHM_FINGERS, strict=True)
        })
        self._target_bindings = {
            f'{entity_id}/{joint_id}': f'{actuator_prefix}actuator{index}'
            for index, joint_id in enumerate(self.joint_ids, 1)
        }
        self.open_actuator = f'{actuator_prefix}actuator8'
        self.gripper_semantic_id = f'{entity_id}/gripper'
        self._algorithm = CanonicalPandaController(
            model, artifact_hash=artifact.identity_hash, config=config,
        )
        self.requirements = position_state_requirements(
            self.writer_id, entity_id=self.entity_id,
            joint_ids=self._source_joint_ids, hand_frame_id=self.hand_frame_id,
        )
        identity_payload = {
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
            'gripper_semantic_id': self.gripper_semantic_id,
            'required_state': self.requirements.to_mapping(),
            'force_feedback': 'not-consumed-v1',
        }
        if entity_id != 'panda-main':
            identity_payload.update({
                'schema': 'panda-entity-position-servo-v1',
                'entity_id': self.entity_id,
                'entity_joint_ids': self._source_joint_ids,
                'hand_frame_id': self.hand_frame_id,
                'native_prefix': self.native_prefix,
                'actuator_prefix': self.actuator_prefix,
            })
        self.identity = digest(identity_payload)
        self._constructed_identity = self.identity
        self._constructed_config = config
        self._constructed_algorithm_identity = self._algorithm.identity
        self._plan_identity_hash = None
        self._episode_id = None
        self._reset_sample_id = None
        self._next_control_step = None
        self._activation_boundary_id = None

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
        if any(source.joints.get(name) != native for name, native in _EXPECTED_JOINT_BINDINGS.items()):
            raise ValueError('PositionServoV1 requires exact Panda arm/finger Joint source bindings')
        if source.bodies.get('panda-main/hand') != 'hand':
            raise ValueError('PositionServoV1 hand state must bind to the actual hand body')
        if (any(source.joint_targets.get(name) != actuator
                for name, actuator in _EXPECTED_TARGET_BINDINGS.items())
                or 'actuator8' not in tuple(source.open_actuators)):
            raise ValueError('PositionServoV1 requires exact actuator1–7 and actuator8 source bindings')

        config = config or getattr(source.config, 'action', None) or ActionConfig()
        if not isinstance(config, ActionConfig):
            raise TypeError('PositionServoV1 requires the existing ActionConfig')
        materialized_xml = project_scene_definition_v3_to_mjcf(
            source.scene_source.xml, scene,
        )
        model = PandaKinematics(materialized_xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
        return cls(artifact=artifact, source=source, scene=scene, model=model, config=config)

    @classmethod
    def for_entity(
        cls, artifact, source, *, entity_id, joint_ids, finger_joint_ids,
        hand_frame_id, native_prefix, actuator_prefix, config: ActionConfig | None = None,
    ):
        """Bind the same audited Panda algorithm to one independent Scene Entity."""
        if not isinstance(artifact, TaskArtifactV1):
            raise TypeError('PositionServoV1 requires TaskArtifactV1')
        if (artifact.timebase.physics_dt, artifact.timebase.control_substeps, artifact.timebase.control_dt) != (0.002, 5, 0.01):
            raise ValueError('PositionServoV1 requires 100 Hz outer / five 2 ms native steps')
        if source.task_artifact_hash != artifact.identity_hash:
            raise ValueError('PositionServoV1 source/Artifact identity mismatch')
        scene = source.scene_definition
        if not isinstance(scene, SceneDefinition) or scene.identity_hash != artifact.scene_identity_hash:
            raise ValueError('PositionServoV1 requires the exact TaskArtifact Scene source')
        if source.scene_source.source_id != f'{scene.schema_version}:{scene.identity_hash}':
            raise ValueError('PositionServoV1 source ID is not bound to its Scene')
        expected_joint_bindings = {
            f'{entity_id}/{joint_id}': f'{native_prefix}{joint_id.removeprefix(native_prefix)}'
            for joint_id in (*joint_ids, *finger_joint_ids)
        }
        if any(source.joints.get(key) != value for key, value in expected_joint_bindings.items()):
            raise ValueError(f'PositionServoV1 {entity_id} Joint source bindings mismatch')
        native_hand_frame = f'{native_prefix}{hand_frame_id.removeprefix(native_prefix)}'
        if source.bodies.get(f'{entity_id}/{hand_frame_id}') != native_hand_frame:
            raise ValueError(f'PositionServoV1 {entity_id} hand Frame does not bind to its native body')
        expected_targets = {
            f'{entity_id}/{joint_id}': f'{actuator_prefix}actuator{index}'
            for index, joint_id in enumerate(joint_ids, 1)
        }
        if any(source.joint_targets.get(key) != value for key, value in expected_targets.items()):
            raise ValueError(f'PositionServoV1 {entity_id} target actuator bindings mismatch')
        open_actuator = f'{actuator_prefix}actuator8'
        if open_actuator not in source.open_actuators:
            raise ValueError(f'PositionServoV1 {entity_id} gripper actuator is missing')
        config = config or getattr(source.config, 'action', None) or ActionConfig()
        if not isinstance(config, ActionConfig):
            raise TypeError('PositionServoV1 requires the existing ActionConfig')
        xml = project_scene_definition_v3_to_mjcf(source.scene_source.xml, scene)
        from .kinematics import PandaTcpProfileV1
        tcp_profile = PandaTcpProfileV1(
            'panda-tcp-profile-v1', f'{entity_id}/hand-origin-tcp-v1',
            hand_frame_id.removeprefix(native_prefix),
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0),
        )
        model = PandaKinematics(xml, tcp_profile=tcp_profile, native_prefix=native_prefix)
        return cls(
            artifact=artifact, source=source, scene=scene, model=model, config=config,
            entity_id=entity_id, joint_ids=joint_ids, finger_joint_ids=finger_joint_ids,
            hand_frame_id=hand_frame_id, native_prefix=native_prefix,
            actuator_prefix=actuator_prefix, tcp_profile=tcp_profile,
        )

    def controller_binding(self):
        return ControllerBindingV1(
            'controller-binding-v1', self.writer_id, _action_schema(),
            'panda-position-feedback', 'panda-position-state-v1',
            self.requirements,
            (
                ControlGroupActionProjectionV1(
                    'control-group-action-projection-v1', self.entity_id, 'arm',
                    ('x', 'y', 'z', 'qw', 'qx', 'qy', 'qz'),
                ),
                ControlGroupActionProjectionV1(
                    'control-group-action-projection-v1', self.entity_id, 'gripper',
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
        if len(bindings) != 1:
            raise ValueError('PositionServoV1 requires exactly one plan binding for its writer')
        if bindings[0] != self.controller_binding():
            raise ValueError('PositionServoV1 plan Controller/action/group contract mismatch')
        expected_resources = {
            (self.entity_id, f'{self.actuator_prefix}actuator{index}', self.writer_id)
            for index in range(1, 9)
        }
        actual_resources = {
            row for row in plan.resource_writers
            if row[0] == self.entity_id
        }
        if actual_resources != expected_resources:
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
            for value in view.joints if value.entity_id == self.entity_id
        }
        if set(joints) != set(self._source_joint_ids):
            raise ValueError('PositionServoV1 typed Panda Joint state is incomplete or ambiguous')
        definitions = _scene_joint_map(self.scene)
        expected_position_representation = {
            **{joint_id: ('revolute', 'radian') for joint_id in self.joint_ids},
            **{joint_id: ('prismatic', 'meter') for joint_id in self.finger_joint_ids},
        }
        joint_position = {}
        for joint_id, value in joints.items():
            definition = definitions.get((self.entity_id, joint_id))
            if definition is None:
                raise ValueError(f'PositionServoV1 Scene is missing Joint {joint_id!r}')
            value.validate_against(definition)
            if (definition.kind, definition.position_representation) != expected_position_representation[joint_id]:
                raise ValueError(f'PositionServoV1 Joint {joint_id!r} has unexpected unit/coordinate')
            if len(value.position) != 1 or not math.isfinite(value.position[0]):
                raise ValueError(f'PositionServoV1 Joint {joint_id!r} is not a finite scalar')
            joint_position[self._algorithm_joint_by_id[joint_id]] = float(value.position[0])

        hand_values = [
            value for value in view.frames
            if value.frame.entity_id == self.entity_id and value.frame.frame_id == self.hand_frame_id
        ]
        if len(hand_values) != 1:
            raise ValueError(f'PositionServoV1 requires exactly one typed {self.entity_id}/{self.hand_frame_id} Frame')
        frame = hand_values[0]
        expected_reference = FrameReference(self.entity_id, self.hand_frame_id)
        if frame.frame != expected_reference:
            raise ValueError('PositionServoV1 typed hand Frame identity mismatch')
        # TCP profile v1 is the identity transform hand→TCP; both the typed
        # Controller input and source-bound PandaKinematics tip name this body.
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
        self._activation_boundary_id = boundary.boundary_id
        return boundary.boundary_id

    def _prepare_switch_activation(self, publication, plan):
        """Prepare fresh instance memory for a live, already-complete boundary.

        This deliberately does not call ``reset()``: reset remains an episode
        initialization contract and continues to accept only the step-zero
        publication. The returned tuple is inert until the selected lifecycle
        commits this instance as the active writer.
        """
        if any(value is not None for value in (
            self._plan_identity_hash, self._episode_id, self._reset_sample_id,
            self._next_control_step, self._activation_boundary_id,
        )):
            raise ValueError('PositionServoV1 switch candidate must be a fresh instance')
        if (self.identity != self._constructed_identity
                or self.config != self._constructed_config
                or self._algorithm.identity != self._constructed_algorithm_identity
                or self._algorithm.config != self._constructed_config):
            raise ValueError('PositionServoV1 candidate identity or algorithm parameters changed after construction')
        self._validate_source(self.source)
        plan_identity = self._validate_plan(plan)
        self._adapt_publication(publication)
        boundary = publication.view.boundary
        clock = publication.view.sample_clock
        if (clock.clock_domain != 'evaluation_boundary'
                or clock.sample_index != boundary.control_step
                or boundary.control_step < 0):
            raise ValueError('PositionServoV1 switch requires a complete evaluation boundary')
        return (
            self.identity, plan_identity, boundary.episode_id,
            boundary.reset_sample_id, boundary.control_step, boundary.boundary_id,
        )

    def _activate_switch_memory(self, prepared):
        """Install prevalidated mid-episode cursor state on this fresh instance."""
        identity, plan_identity, episode_id, reset_sample_id, control_step, boundary_id = prepared
        if identity != self.identity or self._next_control_step is not None:
            raise ValueError('PositionServoV1 prepared switch activation no longer matches this instance')
        self._plan_identity_hash, self._episode_id, self._reset_sample_id = (
            plan_identity, episode_id, reset_sample_id,
        )
        self._next_control_step = control_step
        self._activation_boundary_id = boundary_id

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
        # identities; lower the same seven values to this Entity's Joint keys.
        source_order = tuple(f'{self.entity_id}/{joint_id}' for joint_id in self.joint_ids)
        algorithm_order = tuple(f'panda-v1/joint{index}' for index in range(1, 8))
        target = replace(
            base_target,
            arm_joint_order=source_order,
            arm_position={source: base_target.arm_position[algorithm]
                          for source, algorithm in zip(source_order, algorithm_order, strict=True)},
            arm_servo_position={source: base_target.arm_servo_position[algorithm]
                                for source, algorithm in zip(source_order, algorithm_order, strict=True)},
            controller_identity=self.identity,
            gripper=replace(base_target.gripper, semantic_id=self.gripper_semantic_id),
        )
        bound_target = PositionControlTargetV1(
            'position-control-target-v1', self.writer_id, self.identity,
            plan_identity, self.source.source_closure_digest,
            boundary, publication.view.sample_clock, target,
        )
        self._next_control_step += 1
        return canonical, bound_target
