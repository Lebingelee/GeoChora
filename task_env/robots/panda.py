"""Franka Panda 的纯描述组件。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from ..utils._paths import MUJOCO_MENAGERIE_ROOT
from ..environment import AssetManifest, InitialStateSpec, ReferenceSpec
from ..artifacts import (
    ActuatorReference,
    ActuatorResourceDefinition,
    ArticulationDefinition,
    ControlGroup,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    PoseWorld,
    RobotInstance,
    SceneDefinition,
)
from ..assembly.assets import _asset_definition_from_manifest
from ..registry import register_agent
from .base import BaseAgent
from .gripper import ExperimentalPandaGripperController, PandaGripperController
from ..utils.rotation import matrix_to_quat_wxyz


PANDA_ASSET_ROOT = MUJOCO_MENAGERIE_ROOT / "franka_emika_panda"


def panda_reference_control_binding():
    """Return the legacy scalar Panda gripper binding owned by this robot."""
    from ..runtime.sessions.control import ControlBinding

    return ControlBinding('panda-v1/gripper', 0.08)


def build_panda_direct_effort_execution(scene, artifact, source, *, entity_id,
                                        native_drive, native_ranges):
    """Bind Panda's declared channels to a direct-effort Controller execution.

    The source adapter supplies verified native ranges; this function does not
    parse or materialize a provider-specific source.
    """
    from ..artifacts import JointReference
    from ..artifacts.logical_assembly import (
        LogicalAssemblyV1, LogicalAssemblyScenePinV1, LogicalAssemblyEntityMemberV1,
        LogicalAssemblyNestedMemberV1, LogicalAssemblySubcomponentReferenceV1,
    )
    from ..artifacts.state import StateFieldRequirement, StateRequirements
    from ..controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
    from ..controllers.canonical.physical_controller import LinearEffortProfileV1, LinearEffortControllerV1
    from ..runtime.sessions.physical_control import PhysicalControlExecutionV1, compile_declared_subject_binding

    if native_drive not in {'position', 'disabled'}:
        raise ValueError('Panda effort profile requires a declared native drive mode')
    names = PandaAgent.physical_joint_names()
    definitions = {j.joint_id: j for a in scene.articulations or ()
                   if a.entity_id == entity_id for j in a.joints}
    if any(name not in definitions or source.joints.get(f'{entity_id}/{name}') != name for name in names):
        raise ValueError('Panda effort profile requires the exact nine named source joints')
    subject, declarations = PandaAgent.physical_subject_declaration(
        entity_id=entity_id, source_id=source.source_id,
        source_closure_sha256=source.source_closure_digest, native_ranges=native_ranges,
        native_drive=native_drive)
    instance = next(x for x in scene.entities if x.entity_id == subject.entity_id)
    pin = LogicalAssemblyScenePinV1('logical-assembly-scene-pin-v1', scene.scene_id,
                                     scene.schema_version, scene.identity_hash)
    refs = tuple(LogicalAssemblySubcomponentReferenceV1('existing_entity_subcomponent_ref',
        item.component_path[1:], 'joint', JointReference(subject.entity_id, item.joint_id))
        for item in declarations)
    child = LogicalAssemblyV1('logical-assembly-v1', 'panda-direct-effort-components', 'v1', pin, refs)
    logical = LogicalAssemblyV1('logical-assembly-v1', 'panda-direct-effort-assembly', 'v1', pin, (
        LogicalAssemblyEntityMemberV1('entity_member', ('owner',), entity_id, instance.asset_id, instance.asset_version),
        LogicalAssemblyNestedMemberV1('nested_assembly', ('robot',), child.assembly_id,
                                      child.revision, child.logical_content_sha256)))
    compiled = compile_declared_subject_binding(scene, artifact.identity_hash, source.source_id,
        source.source_closure_digest, logical, {(child.assembly_id, child.revision): child},
        (subject,), declarations, ())
    writer = subject.controller_writers[0]
    keys = tuple(f'{entity_id}/{name}' for name in names)
    kinds = tuple(definitions[name].kind for name in names)
    requirement = ControllerModelRequirementV1('controller-model-requirement-v1',
        'direct-effort-zero-bias-v1', 'geochora', 'v1', 'stdlib', source.source_id,
        source.source_closure_digest, keys,
        tuple('rad' if kind == 'revolute' else 'm' for kind in kinds), 'joint_bias',
        tuple('N*m' if kind == 'revolute' else 'N' for kind in kinds),
        'joint-axis', 'evaluation_boundary', artifact.timebase.control_dt,
        0., 'pure_no_physics_step', writer, 'none', 'required')
    zero = (0.,) * len(names)
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1', requirement, zero, zero, zero)
    action_names = tuple(f'arm-effort-{i}' for i in range(1, 8)) + ('finger-tendon-effort',)
    matrix = tuple(tuple((1. if i == j else 0.) if i < 7 else (0.5 if j == 7 else 0.)
                         for j in range(8)) for i in range(len(names)))
    profile = LinearEffortProfileV1('linear-effort-profile-v1', writer, action_names, keys, matrix, requirement)
    controller = LinearEffortControllerV1(profile, compiled.binding, model)
    fields = tuple(StateFieldRequirement('state-field-requirement-v1', field, 'joint', entity_id, name,
        'required', 'evaluation_boundary', 'joint-definition', 'joint_state_query')
        for name in names for field in ('joint_position', 'joint_velocity'))
    requirements = StateRequirements('state-requirements-v1', 'controller', 'panda-direct-effort', fields)
    definitions_by_native = {j.joint_id: j for a in scene.articulations or ()
                             for j in a.joints if j.kind != 'fixed'}
    joint_bindings = {semantic: definitions_by_native[native]
                      for semantic, native in (*source.joints.items(), *source.free_joints.items())}
    frame_bindings = {name: (artifact.legacy_frame_bindings[name]
                             if name in artifact.legacy_frame_bindings
                             else FrameReference(*name.split('/', 1)))
                      for name in (*source.bodies, *source.frames)}
    execution = PhysicalControlExecutionV1(compiled, (controller,), scene, joint_bindings,
                                            frame_bindings, requirements, 1, (subject,))
    execution.validate_source(scene=scene, artifact_sha256=artifact.identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
    return execution


@register_agent("panda-v1")
class PandaAgent(BaseAgent):
    uid = "panda-v1"
    component_controller_kinds = ("absolute_joint", "absolute_pose", "delta_pose")

    def compile_reference_position_source(self, source, *, artifact, controller, entity_id, recipe):
        """Bind the Panda already present in a checked task source."""
        from .panda_position_binding import compile_reference_position_source
        return compile_reference_position_source(
            self, source, artifact=artifact, controller=controller, entity_id=entity_id, recipe=recipe)

    @staticmethod
    def physical_joint_names():
        return tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2')

    @staticmethod
    def physical_subject_declaration(*, entity_id, source_id, source_closure_sha256,
                                     native_ranges, native_drive, split=False):
        """Describe Panda channels before any physical binding is constructed."""
        from ..runtime.sessions.physical_control import ControlledSubjectV1, SubjectJointDeclarationV1
        names = PandaAgent.physical_joint_names()
        if len(native_ranges) != 8:
            raise ValueError('Panda source requires eight checked actuator ranges')
        writers = ('panda-arm-effort', 'panda-hand-effort') if split else ('panda-direct-effort',)
        paths = tuple(('robot', name) for name in names)
        subject = ControlledSubjectV1(entity_id, entity_id, source_id, source_closure_sha256,
            'references_existing', 'fixed', FrameReference(entity_id, 'link0'), None, paths, writers)
        declarations = tuple(SubjectJointDeclarationV1(
            path, name, ((writers[0] if i < 7 else writers[-1]),),
            f'actuator{i+1}' if i < 7 else 'actuator8',
            f'arm-transmission-{i+1}' if i < 7 else 'split-transmission',
            1.0 if i < 7 else 0.5, native_ranges[i if i < 7 else 7], native_drive)
            for i, (name, path) in enumerate(zip(names, paths, strict=True)))
        return subject, declarations

    @staticmethod
    def controlled_subject(*, entity_id, source_id, source_closure_sha256, channels, writers):
        """Declare this Panda's existing Scene entity for the shared physical owner."""
        from ..runtime.sessions.physical_control import ControlledSubjectV1
        names = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2')
        if tuple(channel.joint_id for channel in channels) != names:
            raise ValueError('Panda subject requires its declared ordered arm and finger joints')
        if any(channel.entity_id != entity_id for channel in channels):
            raise ValueError('Panda subject channels must target its own entity')
        return ControlledSubjectV1(entity_id, entity_id, source_id, source_closure_sha256,
            'references_existing', 'fixed', FrameReference(entity_id, 'link0'), None,
            tuple(channel.component_path for channel in channels), tuple(writers))

    def project_references(self, *, names, spec, qpos_adr, dof_adr, ctrl_range):
        """Project the established Panda layout without making the resolver identify robots."""
        from ..assembly.references import AgentReferences
        arm_names = tuple(f'joint{i}' for i in range(1, 8))
        fingers = ('finger_joint1', 'finger_joint2')
        arm_ids = [names.joints[name] for name in arm_names]
        finger_ids = [names.joints[name] for name in fingers]
        return AgentReferences(uid=self.uid, arm_joint_ids=arm_ids,
            arm_qpos_ids=qpos_adr[arm_ids], arm_dof_ids=dof_adr[arm_ids],
            arm_actuator_ids=[names.actuators[f'actuator{i}'] for i in range(1, 8)],
            gripper_joint_ids=finger_ids, gripper_qpos_ids=qpos_adr[finger_ids],
            gripper_actuator_ids=[names.actuators['actuator8']],
            eef_site_id=names.sites['nutassembly_ee_site'], hand_body_id=names.bodies['hand'],
            ctrl_range=ctrl_range, arm_joint_names=arm_names, base_body_id=names.bodies['link0'],
            base_body_name='link0', eef_site_name='nutassembly_ee_site',
            joint_names=tuple(spec.joint_names), actuator_names=tuple(spec.actuator_names),
            body_ids=[names.bodies[name] for name in spec.body_names],
            site_ids=[names.sites[name] for name in spec.site_names])

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="agent_mjcf",
            mjcf_sources=(PANDA_ASSET_ROOT / "panda.xml",),
            asset_roots=(PANDA_ASSET_ROOT,),
            asset_version="mujoco-menagerie-panda",
            source_reference="mujoco-menagerie://franka_emika_panda/panda.xml",
            source_revision="b846dd12bc459d776cccb3dee0b1d02acbf7a9c7",
        )

    def source_recipe(self):
        """Declare this Panda's pinned asset and canonical controlled joints."""
        from .source_recipe import RobotSourceRecipeV1, RobotSourceReferenceV1
        manifest = self.asset_manifest()
        return RobotSourceRecipeV1(self.uid, 'reference-task-source', (
            RobotSourceReferenceV1('panda-menagerie-source', manifest.source_reference,
                                   manifest.source_revision, (self.uid,)),), (),
            self.physical_joint_names(), self.selected_controller_profiles(),
            tuple((self.uid, f'actuator{index}', 'panda-position-controller')
                  for index in range(1, 9)))

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=("link0", "hand", "left_finger", "right_finger"),
            joint_names=(
                "joint1",
                "joint2",
                "joint3",
                "joint4",
                "joint5",
                "joint6",
                "joint7",
                "finger_joint1",
                "finger_joint2",
            ),
            site_names=("nutassembly_ee_site",),
            actuator_names=(
                "actuator1",
                "actuator2",
                "actuator3",
                "actuator4",
                "actuator5",
                "actuator6",
                "actuator7",
                "actuator8",
            ),
        )

    def initial_state_spec(self) -> InitialStateSpec:
        return InitialStateSpec(
            joint_positions=(
                ("joint1", -0.17),
                ("joint2", 0.0),
                ("joint3", 0.0),
                ("joint4", -1.57079),
                ("joint5", 0.0),
                ("joint6", 1.57079),
                ("joint7", -0.7853),
                ("finger_joint1", 0.04),
                ("finger_joint2", 0.04),
            ),
            notes=("Stage 1 must resolve these names to qpos addresses.",),
        )

    def selected_controller_profiles(self):
        return ('r1', 'r3_continuous_v1', 'r3_continuous_v1_pose_path_x20')

    def supported_controller_kinds(self) -> tuple[str, ...]:
        return self.component_controller_kinds

    def bind_runtime(self, *, references, config, boundary):
        """Bind this robot's controller and named frames to a compiled runtime."""
        from ..controllers import (
            AbsoluteJointPositionActionAdapter, AbsolutePoseActionAdapter,
            DeltaPoseActionController,
        )
        from ..environment.types import ActionModeSpec, StageUnavailableError
        from .runtime import RobotControllerHandle, RobotFrameReference, RobotRuntime

        controller_config = config.robot.controller
        if controller_config is None:
            raise StageUnavailableError('robot TaskEnv requires an explicit robot.controller config')
        adapters = {
            'absolute_joint': AbsoluteJointPositionActionAdapter,
            'absolute_pose': AbsolutePoseActionAdapter,
            'delta_pose': DeltaPoseActionController,
        }
        adapter_type = adapters.get(controller_config.kind)
        if adapter_type is None:
            raise StageUnavailableError(f'unsupported robot controller kind {controller_config.kind!r}')
        reference_identity = {
            None: None, 'world': 'world',
            'base': f'body:{references.base_body_name}',
            'ee': f'site:{references.eef_site_name}',
        }[controller_config.reference]
        action_spec = replace(
            ActionModeSpec.from_controller_config(controller_config),
            reference_identity=reference_identity,
        )
        gripper = self.create_gripper_controller(
            references=references, config=config.action, kind=config.robot.gripper.kind,
            force_limit_N=config.robot.gripper.force_limit_N,
            opening_step_m=config.robot.gripper.opening_step_m,
            force_deadband_N=config.robot.gripper.force_deadband_N,
            force_adjust_step_m=config.robot.gripper.force_adjust_step_m,
        )
        bind_force_limit = getattr(gripper, 'bind_force_limit', None)
        if callable(bind_force_limit):
            bind_force_limit(boundary)
        adapter_kwargs = {'references': references, 'config': config.action, 'gripper': gripper}
        if controller_config.kind in {'absolute_pose', 'delta_pose'}:
            adapter_kwargs.update(controller_config=controller_config, action_spec=action_spec)
        controller = RobotControllerHandle(
            adapter=adapter_type(**adapter_kwargs), kind=controller_config.kind,
            reference=controller_config.reference, action_spec=action_spec,
        )
        runtime = RobotRuntime(
            uid=self.uid, references=references, controller=controller, gripper=gripper,
            world=RobotFrameReference('world', 'world', None, 'world'),
            base=RobotFrameReference('base', 'body', references.base_body_id, references.base_body_name),
            ee=RobotFrameReference('ee', 'site', references.eef_site_id, references.eef_site_name),
        )
        return runtime, action_spec

    def create_gripper_controller(
        self,
        *,
        references,
        config,
        kind: str = "experimental_rate_limited",
        force_limit_N: float = 30.0,
        opening_step_m: float = 0.002,
        force_deadband_N: float = 1.0,
        force_adjust_step_m: float = 1.0e-4,
    ) -> PandaGripperController:
        """Create the selected Panda gripper controller after references resolve."""

        if kind == "experimental_rate_limited":
            return ExperimentalPandaGripperController(
                references=references,
                config=config,
                force_limit_N=force_limit_N,
                max_opening_step_m=opening_step_m,
                force_deadband_N=force_deadband_N,
                force_adjust_step_m=force_adjust_step_m,
            )
        if kind != "legacy":
            raise ValueError(f"unsupported Panda gripper controller kind {kind!r}")
        return PandaGripperController(
            references=references,
            config=config,
            force_limit_N=force_limit_N,
        )


__all__ = ["PANDA_ASSET_ROOT", "PandaAgent", "panda_reference_control_binding"]


def _panda_scene_from_import(
    imported,
    manifest: AssetManifest,
    *,
    entity_id: str,
    scene_id: str,
    source_content_sha256: str | None = None,
) -> SceneDefinition:
    """Map a public imported Panda source to the canonical typed Scene owner."""

    entity_id = str(entity_id)
    scene_id = str(scene_id)
    if not entity_id or not scene_id:
        raise ValueError("Panda Scene identity requires nonempty entity and scene IDs")
    asset = _asset_definition_from_manifest(manifest)
    if source_content_sha256 is not None:
        asset = replace(asset, source_content_sha256=source_content_sha256)

    bodies = {body.body_id: body for body in imported.ir.bodies}
    bodies_by_frame = {body.frame_id: body for body in imported.ir.bodies}
    frames_by_id = {frame.node_id: frame for frame in imported.ir.frames}
    frames = tuple(
        FrameDefinition(
            "frame-definition-v1", entity_id, body.name, "runtime", None, None,
        )
        for body in imported.ir.bodies
    )
    coordinate_layout = {
        "hinge": ("revolute", "radian", "radian_per_second", 1, 1),
        "slide": ("prismatic", "meter", "meter_per_second", 1, 1),
        "fixed": ("fixed", "none", "none", 0, 0),
    }
    joints = []
    source_joint_names = set()
    joint_child_frames = set()
    for imported_joint in imported.ir.joints:
        source_name = imported_joint.dynamics.get("source_name")
        if not source_name:
            raise ValueError(f"Panda joint lacks source name: {imported_joint.joint_id}")
        if imported_joint.body_a is None or imported_joint.body_a not in bodies:
            raise ValueError(f"Panda joint has no canonical parent body: {source_name}")
        if imported_joint.body_b not in bodies:
            raise ValueError(f"Panda joint has no canonical child body: {source_name}")
        parent = bodies[imported_joint.body_a]
        child = bodies[imported_joint.body_b]
        try:
            kind, position, velocity, position_size, velocity_size = coordinate_layout[
                imported_joint.type
            ]
        except KeyError as exc:
            raise ValueError(
                f"unsupported imported Panda joint type: {imported_joint.type!r}"
            ) from exc
        joints.append(
            JointDefinition(
                "joint-definition-v1",
                str(source_name),
                FrameReference(entity_id, parent.name),
                FrameReference(entity_id, child.name),
                _pose_from_transform(imported_joint.frame_a),
                _pose_from_transform(imported_joint.frame_b),
                kind,
                tuple(float(value) for value in imported_joint.axis)
                if kind in {"revolute", "prismatic"} else None,
                position,
                velocity,
                position_size,
                velocity_size,
            )
        )
        source_joint_names.add(str(source_name))
        joint_child_frames.add(child.frame_id)

    root_body = next((body for body in imported.ir.bodies if body.name == "link0"), None)
    if root_body is None:
        raise ValueError("imported Panda source is missing root body 'link0'")
    for body in imported.ir.bodies:
        if body is root_body or body.frame_id in joint_child_frames:
            continue
        source_frame = frames_by_id.get(body.frame_id)
        parent_body = None if source_frame is None else bodies_by_frame.get(source_frame.parent_id)
        if parent_body is None:
            raise ValueError(f"unmapped fixed Panda frame: {body.name}")
        joints.append(
            JointDefinition(
                "joint-definition-v1",
                f"{body.name}_fixed_mount",
                FrameReference(entity_id, parent_body.name),
                FrameReference(entity_id, body.name),
                _pose_from_transform(source_frame.local_transform),
                PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
                "fixed",
                None,
                "none",
                "none",
                0,
                0,
            )
        )

    articulation = ArticulationDefinition(
        "articulation-definition-v1",
        entity_id,
        "link0",
        tuple(body.name for body in imported.ir.bodies),
        tuple(joints),
    )
    actuator_names = tuple(sorted(
        str(actuator.parameters.get("source_name"))
        for actuator in imported.ir.actuators
        if actuator.parameters.get("source_name")
    ))
    expected_actuators = {f"actuator{index}" for index in range(1, 9)}
    if set(actuator_names) != expected_actuators:
        raise ValueError("imported Panda source must expose its eight named actuators")
    resources = tuple(
        ActuatorResourceDefinition("actuator-resource-v1", entity_id, name)
        for name in actuator_names
    )
    scene = SceneDefinition(
        "scene-definition-v3",
        scene_id,
        (asset,),
        (EntityInstance("entity-instance-v1", entity_id, asset.asset_id, asset.asset_version),),
        frames,
        (articulation,),
        (RobotInstance(
            "robot-instance-v1", entity_id, (FrameReference(entity_id, "link0"),),
        ),),
        resources,
        (
            ControlGroup(
                "control-group-v1", entity_id, "arm",
                tuple(ActuatorReference(entity_id, f"actuator{index}") for index in range(1, 8)),
            ),
            ControlGroup(
                "control-group-v1", entity_id, "gripper",
                (ActuatorReference(entity_id, "actuator8"),),
            ),
        ),
    )
    scene.validate()
    scene_joint_ids = {joint.joint_id for joint in articulation.joints}
    if not source_joint_names <= scene_joint_ids:
        raise ValueError("Panda Scene dropped an imported source joint")
    for name in actuator_names:
        reference = ActuatorReference(entity_id, name)
        if scene.resolve_actuator(reference) != ActuatorResourceDefinition(
            "actuator-resource-v1", entity_id, name,
        ):
            raise ValueError(f"Panda Scene did not retain imported actuator {name!r}")
    return scene


def _pose_from_transform(values) -> PoseWorld:
    matrix = np.asarray(values, dtype=np.float64).reshape(4, 4)
    quaternion = matrix_to_quat_wxyz(matrix[:3, :3])
    return PoseWorld(
        tuple(float(value) for value in matrix[:3, 3]),
        tuple(float(value) for value in quaternion),
    )
