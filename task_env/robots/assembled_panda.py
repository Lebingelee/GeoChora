"""Declared two-source Panda arm and attached parallel hand."""
from __future__ import annotations

from ..environment import AssetManifest, InitialStateSpec, ReferenceSpec
from ..registry import register_agent
from .base import BaseAgent
from .panda import PANDA_ASSET_ROOT


@register_agent('panda-arm-hand-v1')
class AssembledPandaAgent(BaseAgent):
    """Describe the exact pinned arm/hand recipe, without allocating a runtime."""
    uid = 'panda-arm-hand-v1'

    def asset_manifest(self):
        return AssetManifest(owner_uid=self.uid, asset_kind='agent_mjcf',
            mjcf_sources=(PANDA_ASSET_ROOT / 'panda_nohand.xml', PANDA_ASSET_ROOT / 'hand.xml'),
            asset_roots=(PANDA_ASSET_ROOT,), asset_version='menagerie-b846dd12',
            source_reference='mujoco-menagerie://franka_emika_panda/panda_nohand.xml+hand.xml',
            source_revision='b846dd12bc459d776cccb3dee0b1d02acbf7a9c7')

    def reference_spec(self):
        return ReferenceSpec(body_names=('link0', 'probe_hand_hand', 'probe_hand_left_finger', 'probe_hand_right_finger'),
            joint_names=tuple(f'joint{i}' for i in range(1, 8)) +
                        ('probe_hand_finger_joint1', 'probe_hand_finger_joint2'),
            site_names=('attachment_site',),
            actuator_names=tuple(f'actuator{i}' for i in range(1, 8)) + ('probe_hand_actuator8',))

    def initial_state_spec(self):
        return InitialStateSpec(joint_positions=tuple(zip(
            tuple(f'joint{i}' for i in range(1, 8)) + ('probe_hand_finger_joint1', 'probe_hand_finger_joint2'),
            (0., 0., 0., -1.57079, 0., 1.57079, -.7853, .038, .038), strict=True)),
            notes=('Source names refer to the verified fixed-attachment lowering.',))

    def compile_position_binding(self, declaration, *, artifact, controller, task_closure_sha256):
        """Compile the exact arm and hand as nested position subjects."""
        from .panda_position_binding import compile_panda_position_subjects
        fixed = declaration.attachment_plan
        arm, hand = fixed.parent_entity_id, fixed.child_entity_id
        return compile_panda_position_subjects(source_scene=declaration.scene,
            components=((arm, fixed.parent_root.frame_id, tuple(f'joint{i}' for i in range(1, 8)), None),
                        (hand, fixed.child_root.frame_id, ('finger_joint1', 'finger_joint2'), arm)),
            site_entity=hand, site_name='nutassembly_ee_site',
            groups=((arm, 'arm-position'), (hand, 'hand-position')),
            source_id=declaration.parent_source.source_id,
            robot_closure_sha256=fixed.source_closure_sha256, task_closure_sha256=task_closure_sha256,
            artifact=artifact, controller=controller, attachment=fixed)

    def compose_task_source(self, source, *, artifact, controller, task_entities, existing_robot_entity,
                            task_body_names, task_site_transfers):
        """Bind this exact robot to a task's existing source without parsing native state.

        The caller holds the source execution locks. Legacy task semantic keys
        remain an explicit compatibility projection; the physical owners are
        the two declared robot entities in the composition plan.
        """
        from dataclasses import replace
        from ..assembly.source_composition import (
            CompositionRuntimeInputV1, CompositionSourceV1, SourceCompositionPlanV1,
            PositionSubjectControlBindingV1,
        )
        from ..runtime.sessions.source import RuntimeSource
        if type(source) is not RuntimeSource or source.execution_source_receipt is None:
            raise TypeError('assembled Panda requires a verified task RuntimeSource')
        if type(task_entities) is not tuple or type(task_body_names) is not tuple:
            raise TypeError('task entity and native body declarations must be tuples')
        if set(dict(task_body_names)) != set(task_entities):
            raise ValueError('task body names must cover the declared task entities')
        declaration = self.declare_source()
        from ..runtime.sessions.mujoco_composition import derive_task_compatible_attachment
        if len(task_site_transfers) != 1:
            raise ValueError('assembled Panda requires one declared task end-effector site')
        task_hand, _site, source_hand = task_site_transfers[0]
        declaration = derive_task_compatible_attachment(declaration=declaration,
            task_receipt=source.execution_source_receipt,
            task_hand_name=task_hand, source_hand_name=source_hand)
        fixed = declaration.attachment_plan
        arm, hand = fixed.parent_entity_id, fixed.child_entity_id
        control_plan, subject_identity = self.compile_position_binding(declaration, artifact=artifact, controller=controller,
                                                     task_closure_sha256=source.source_closure_digest)
        position_binding = PositionSubjectControlBindingV1(control_plan, subject_identity, tuple(
            (entity, actuator, fixed.native_actuator_names[f'{entity}/{actuator}'])
            for entity, actuator, _ in control_plan.resource_writers), tuple(
            (f'{existing_robot_entity}/{name}', entity, name,
             fixed.native_joint_names[f'{entity}/{name}'], actuator)
            for entity, names, actuator_names in (
                (arm, tuple(f'joint{i}' for i in range(1, 8)), tuple(f'actuator{i}' for i in range(1, 8))),
                (hand, ('finger_joint1', 'finger_joint2'), ('actuator8', 'actuator8')))
            for name, actuator in zip(names, actuator_names, strict=True)))
        robot_sources = tuple(CompositionSourceV1(
            declaration.source_by_entity[entity].source_id, fixed.source_closure_sha256, (entity,))
            for entity in (arm, hand))
        plan = SourceCompositionPlanV1(
            CompositionSourceV1(source.source_id, source.source_closure_digest,
                                (*task_entities, existing_robot_entity)),
            task_entities, (existing_robot_entity,), self.uid, robot_sources, 'replace',
            declaration.assembly.logical_content_sha256, fixed.identity_hash, task_site_transfers,
            control_plan.identity_hash, subject_identity,
            task_entity_source_roots=task_body_names,
            replaced_robot_source_roots=(fixed.native_body_names[f'{arm}/{fixed.parent_root.frame_id}'],),
            task_free_joints=tuple(source.free_joints.items()),
            position_binding_identity_sha256=position_binding.identity_hash)
        robot_bodies = ((arm, fixed.native_body_names[f'{arm}/{fixed.parent_root.frame_id}']),
                        (hand, fixed.native_body_names[f'{hand}/{fixed.child_root.frame_id}']))
        composition = CompositionRuntimeInputV1(
            plan, declaration, tuple(name for _, name in task_body_names),
            (fixed.native_body_names[f'{arm}/{fixed.parent_root.frame_id}'],),
            (*task_body_names, *robot_bodies), tuple(source.free_joints.values()), control_plan, subject_identity)
        joints = dict(source.joints)
        for index in (1, 2):
            key, expected = f'{existing_robot_entity}/finger_joint{index}', f'finger_joint{index}'
            if joints.get(key) != expected:
                raise ValueError('task finger binding differs from the declared Panda source')
            joints[key] = fixed.native_joint_names[f'{hand}/{expected}']
        frames = dict(source.frames)
        for source_body, site, target_body in task_site_transfers:
            matching = [key for key, native in frames.items() if native == site]
            if len(matching) != 1 or not matching[0].startswith(existing_robot_entity + '/'):
                raise ValueError('task site binding does not uniquely belong to its robot')
            frames[matching[0]] = fixed.namespace_prefix + site
        if source.open_actuators != ('actuator8',):
            raise ValueError('task gripper binding differs from the declared Panda source')
        return replace(source, joints=joints, frames=frames,
            open_actuators=(fixed.native_actuator_names[f'{hand}/actuator8'],),
            composition_runtime_input=composition, position_subject_binding=position_binding)

    def supported_controller_kinds(self):
        # The component-runtime controller route is not admitted by this slice.
        return ()

    def selected_controller_profiles(self):
        return ('r1',)

    def compile_effort_subjects(self, declaration, *, artifact_sha256, source_id,
                                native_ranges, native_drive='disabled'):
        """Compile nested arm/hand declarations against the common physical binding owner.

        The caller must obtain ranges from the verified source and separately
        establish a matching native-build receipt before submitting commands.
        """
        from ..artifacts import (LogicalAssemblyV1, LogicalAssemblyEntityMemberV1,
            LogicalAssemblyNestedMemberV1, LogicalAssemblySubcomponentReferenceV1)
        from ..runtime.sessions.physical_control import (ControlledSubjectV1,
            SubjectJointDeclarationV1, compile_declared_subject_binding)
        from ..assembly.panda_fixed_source import PandaFixedSourceDeclarationV1
        if type(declaration) is not PandaFixedSourceDeclarationV1:
            raise TypeError('assembled Panda requires its pinned source declaration')
        if len(native_ranges) != 8 or native_drive not in {'disabled', 'position'}:
            raise ValueError('assembled Panda requires eight source actuator ranges and declared drive')
        scene, plan, pin = declaration.scene, declaration.attachment_plan, declaration.assembly.scene_pin
        if source_id != declaration.parent_source.source_id:
            raise ValueError('assembled Panda source id differs from its pinned Scene')
        entity = {item.entity_id: item for item in scene.entities}
        arm_names = tuple(f'joint{i}' for i in range(1, 8))
        hand_names = ('finger_joint1', 'finger_joint2')
        def child(label, target_entity, names):
            return LogicalAssemblyV1('logical-assembly-v1', label, 'v1', pin, tuple(
                LogicalAssemblySubcomponentReferenceV1('existing_entity_subcomponent_ref',
                    (name,), 'joint', JointReference(target_entity, name)) for name in names))
        arm_leaf = child('panda-assembled-arm-channels', 'panda-arm', arm_names)
        hand_leaf = child('panda-assembled-hand-channels', 'panda-hand', hand_names)
        branch = LogicalAssemblyV1('logical-assembly-v1', 'panda-assembled-components', 'v1', pin, (
            LogicalAssemblyNestedMemberV1('nested_assembly', ('arm',), arm_leaf.assembly_id,
                                          arm_leaf.revision, arm_leaf.logical_content_sha256),
            LogicalAssemblyNestedMemberV1('nested_assembly', ('hand',), hand_leaf.assembly_id,
                                          hand_leaf.revision, hand_leaf.logical_content_sha256)))
        root = LogicalAssemblyV1('logical-assembly-v1', 'panda-assembled-controlled', 'v1', pin, (
            *(LogicalAssemblyEntityMemberV1('entity_member', (name+'-owner',), name,
                  entity[name].asset_id, entity[name].asset_version) for name in ('panda-arm', 'panda-hand')),
            LogicalAssemblyNestedMemberV1('nested_assembly', ('robot',), branch.assembly_id,
                                          branch.revision, branch.logical_content_sha256)))
        catalog = {(item.assembly_id, item.revision): item for item in (branch, arm_leaf, hand_leaf)}
        arm_paths = tuple(('robot', 'arm', name) for name in arm_names)
        hand_paths = tuple(('robot', 'hand', name) for name in hand_names)
        subjects = (
            ControlledSubjectV1('panda-arm', 'panda-arm', source_id, plan.source_closure_sha256,
                'references_existing', 'fixed', plan.parent_root, None, arm_paths, ('panda-arm-effort',)),
            ControlledSubjectV1('panda-hand', 'panda-hand', source_id, plan.source_closure_sha256,
                'references_existing', 'constrained', plan.child_root, 'panda-arm', hand_paths,
                ('panda-hand-effort',), attachment_plan=plan),
        )
        declarations = tuple(SubjectJointDeclarationV1(path, name, ('panda-arm-effort',),
            plan.native_actuator_names[f'panda-arm/actuator{i}'], f'arm-transmission-{i}', 1.,
            native_ranges[i-1], native_drive)
            for i, (path, name) in enumerate(zip(arm_paths, arm_names, strict=True), 1)) + tuple(
            SubjectJointDeclarationV1(path, name, ('panda-hand-effort',),
                plan.native_actuator_names['panda-hand/actuator8'], 'hand-tendon-split', .5,
                native_ranges[7], native_drive) for path, name in zip(hand_paths, hand_names, strict=True))
        compiled = compile_declared_subject_binding(scene, artifact_sha256, source_id,
            plan.source_closure_sha256, root, catalog, subjects, declarations)
        return compiled, subjects, declarations

    def build_effort_execution(self, declaration, *, artifact, source, native_ranges):
        """Build a source-bound arm/hand physical profile without allocating a solver."""
        from ..artifacts.state import StateFieldRequirement, StateRequirements
        from ..controllers.canonical.model import ControllerModelRequirementV1, AffineJointBiasModelV1
        from ..controllers.canonical.physical_controller import LinearEffortControllerV1, LinearEffortProfileV1
        from ..runtime.sessions.physical_control import PhysicalControlExecutionV1
        if (source.scene_definition.identity_hash != declaration.scene.identity_hash
                or source.source_closure_digest != declaration.attachment_plan.source_closure_sha256):
            raise ValueError('assembled Panda runtime source differs from its declaration')
        compiled, subjects, declarations = self.compile_effort_subjects(declaration,
            artifact_sha256=artifact.identity_hash, source_id=source.source_id,
            native_ranges=native_ranges, native_drive='position')
        controllers = []
        for subject in subjects:
            channels = tuple(c for c in compiled.binding.channels if c.entity_id == subject.entity_id)
            keys = tuple(f'{c.entity_id}/{c.joint_id}' for c in channels)
            writer = subject.controller_writers[0]
            is_arm = subject.entity_id == 'panda-arm'
            actions = tuple(f'arm-effort-{i}' for i in range(1, 8)) if is_arm else ('finger-tendon-effort',)
            matrix = tuple(tuple((1. if index == column else 0.) if is_arm else .5
                                 for column in range(len(actions))) for index in range(len(channels)))
            requirement = ControllerModelRequirementV1('controller-model-requirement-v1',
                'direct-effort-zero-bias-v1', 'geochora', 'v1', 'stdlib', source.source_id,
                source.source_closure_digest, keys,
                tuple('rad' if c.kind == 'revolute' else 'm' for c in channels), 'joint_bias',
                tuple(c.unit for c in channels), 'joint-axis', 'evaluation_boundary',
                artifact.timebase.control_dt, 0., 'pure_no_physics_step', writer, 'none', 'required')
            zeros = (0.,) * len(channels)
            model = AffineJointBiasModelV1('affine-joint-bias-model-v1', requirement, zeros, zeros, zeros)
            profile = LinearEffortProfileV1('linear-effort-profile-v1', writer, actions, keys, matrix, requirement)
            controllers.append(LinearEffortControllerV1(profile, compiled.binding, model))
        joints = {f'{a.entity_id}/{j.joint_id}': j for a in declaration.scene.articulations or () for j in a.joints}
        frames = {name: FrameReference(*name.split('/', 1)) for name in (*source.bodies, *source.frames)}
        requirements = StateRequirements('state-requirements-v1', 'controller', 'panda-assembled-effort', tuple(
            StateFieldRequirement('state-field-requirement-v1', field, 'joint', c.entity_id, c.joint_id,
                'required', 'evaluation_boundary', 'joint-definition', 'joint_state_query')
            for c in compiled.binding.channels for field in ('joint_position', 'joint_velocity')))
        execution = PhysicalControlExecutionV1(compiled, tuple(controllers), declaration.scene,
                                                joints, frames, requirements, 1, subjects)
        execution.validate_source(scene=declaration.scene, artifact_sha256=artifact.identity_hash,
            source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
        return execution

    def declare_source(self):
        """Read and verify pinned source bytes; caller owns source execution lock."""
        from ..assembly.panda_fixed_source import declare_panda_fixed_source
        return declare_panda_fixed_source()


from dataclasses import replace
from ..artifacts import ActuatorReference, FrameReference, JointReference, PoseWorld
from ..controllers.canonical.leaf_actions import ARM_WRITER_ID, HAND_WRITER_ID
from ..controllers.canonical.leaf_profiles import (
    ARM_POSITION_ACTION_SCHEMA, ARM_POSITION_PROFILE_ID, HAND_POSITION_ACTION_SCHEMA,
    HAND_POSITION_PROFILE_ID, PANDA_ARM_JOINT_IDS, PANDA_ARM_JOINT_LIMITS_RAD,
    PANDA_HAND_FINGER_JOINT_IDS, PANDA_HAND_FINGER_LIMITS_M, PANDA_HAND_TENDON_IDENTITY,
    PANDA_HAND_TENDON_COEFFICIENTS, PANDA_HAND_EQUALITY_IDENTITY,
    PANDA_HAND_COMMAND_SCALE_CTRL_PER_OPENING_M, PANDA_HAND_ACTUATOR_GAINPRM,
    PANDA_HAND_ACTUATOR_BIASPRM, LeafJointActuatorBindingV1, LeafProfileBindingV1,
    panda_arm_required_state, panda_hand_required_state,
)
from ..controllers.canonical.leaf_plan import default_leaf_profile_section

def panda_assembly_leaf_bindings(candidate, provider_version, build_sha):
    scene = candidate.scene
    assembly = candidate.assembly
    asset_by_entity = {item.entity_id: item for item in scene.entities}
    assets = {(item.asset_id, item.asset_version): item for item in scene.assets}
    identity_pose = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    records = []
    for is_arm in (True, False):
        entity_id = "panda-arm" if is_arm else "panda-hand"
        path = ("arm",) if is_arm else ("hand",)
        kind = "arm_position" if is_arm else "hand_position"
        group = "arm-position" if is_arm else "hand-position"
        joints = PANDA_ARM_JOINT_IDS if is_arm else PANDA_HAND_FINGER_JOINT_IDS
        limits = PANDA_ARM_JOINT_LIMITS_RAD if is_arm else PANDA_HAND_FINGER_LIMITS_M
        actuators = tuple(f"actuator{i}" for i in range(1, 8)) if is_arm else ("actuator8",)
        tcp = FrameReference(entity_id, "link7" if is_arm else "hand")
        asset_instance = asset_by_entity[entity_id]
        asset = assets[(asset_instance.asset_id, asset_instance.asset_version)]
        binding = LeafProfileBindingV1(
            "leaf-profile-binding-v1", "declared", kind,
            ARM_POSITION_PROFILE_ID if is_arm else HAND_POSITION_PROFILE_ID,
            ARM_POSITION_ACTION_SCHEMA if is_arm else HAND_POSITION_ACTION_SCHEMA,
            scene.identity_hash, assembly.assembly_id, assembly.revision,
            assembly.logical_content_sha256, path, "entity_member", "entity", entity_id,
            entity_id, asset.asset_id, asset.asset_version,
            candidate.runtime_source.source_closure_digest, "canonical-joint-position-v1", "0" * 64,
            ARM_WRITER_ID if is_arm else HAND_WRITER_ID, group,
            "mujoco", provider_version, build_sha, "cpu", 0.002, 5,
            tuple(JointReference(entity_id, item) for item in joints),
            "radian" if is_arm else "meter", tuple(limits),
            tuple(ActuatorReference(entity_id, item) for item in actuators),
            tuple(LeafJointActuatorBindingV1(
                "leaf-joint-actuator-binding-v1", JointReference(entity_id, joint),
                ActuatorReference(entity_id, actuator),
            ) for joint, actuator in zip(joints, actuators, strict=True)) if is_arm else (),
            tcp, "T_parent_from_tcp", identity_pose,
            panda_arm_required_state(entity_id, tcp) if is_arm else panda_hand_required_state(entity_id, tcp),
            None if is_arm else PANDA_HAND_TENDON_IDENTITY,
            () if is_arm else PANDA_HAND_TENDON_COEFFICIENTS,
            None if is_arm else PANDA_HAND_EQUALITY_IDENTITY,
            None if is_arm else PANDA_HAND_COMMAND_SCALE_CTRL_PER_OPENING_M,
            None if is_arm else "opening_m = finger_joint1_q_m + finger_joint2_q_m",
            None if is_arm else "ctrl = 3187.5 * opening_m",
            None if is_arm else (0.0, 255.0),
            () if is_arm else PANDA_HAND_ACTUATOR_GAINPRM,
            () if is_arm else PANDA_HAND_ACTUATOR_BIASPRM,
        )
        records.append(binding)
    defaults = tuple(sorted((default_leaf_profile_section(item) for item in records),
                             key=lambda item: item.member_path))
    bindings = tuple(sorted((replace(item, configuration_identity_sha256=next(
        section.configuration_identity_sha256 for section in defaults
        if section.member_path == item.member_path
    )) for item in records), key=lambda item: item.member_path))
    return bindings, defaults
