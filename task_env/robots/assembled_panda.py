"""Declared two-source Panda arm and attached parallel hand."""
from __future__ import annotations

from ..environment import AssetManifest, InitialStateSpec, ReferenceSpec
from ..artifacts import FrameReference, JointReference
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

    def source_recipe(self):
        """Declare pinned arm/hand sources and the canonical nesting edge."""
        from .source_recipe import RobotSourceRecipeV1, RobotSourceReferenceV1
        manifest = self.asset_manifest()
        return RobotSourceRecipeV1(self.uid, 'replace-task-subtree', (
            RobotSourceReferenceV1('panda-arm-source',
                'mujoco-menagerie://franka_emika_panda/panda_nohand.xml',
                manifest.source_revision, ('panda-arm',)),
            RobotSourceReferenceV1('panda-hand-source',
                'mujoco-menagerie://franka_emika_panda/hand.xml',
                manifest.source_revision, ('panda-hand',))),
            (('panda-arm', 'attachment_site', 'panda-hand', 'hand',
              'fixed-transform-from-task-authored-tcp-v1'),),
            tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2'),
            ('r1',),
            tuple((entity, f'actuator{index}', 'panda-position-controller')
                  for entity, indexes in (('panda-arm', range(1, 8)), ('panda-hand', (8,)))
                  for index in indexes))

    def source_recipe_for_profile(self, profile):
        """Keep the historical recipe identity and bind split writers explicitly."""
        recipe = self.source_recipe()
        if profile == 'r1':
            return recipe
        if profile != 'r1_split':
            raise ValueError('assembled Panda does not declare this Controller profile')
        from dataclasses import replace
        from ..controllers.canonical.split_panda_position import ARM_WRITER, HAND_WRITER
        return replace(recipe, control_profiles=('r1_split',), resource_writers=tuple(
            (entity, f'actuator{index}', writer)
            for entity, indexes, writer in (
                ('panda-arm', range(1, 8), ARM_WRITER), ('panda-hand', (8,), HAND_WRITER))
            for index in indexes))

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

    def supported_controller_kinds(self):
        # The component-runtime controller route is not admitted by this slice.
        return ()

    def selected_controller_profiles(self):
        return ('r1', 'r1_split')

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
        if any(not hasattr(declaration, name) for name in
               ('scene', 'attachment_plan', 'assembly', 'source_by_entity')):
            raise TypeError('assembled Panda requires a typed assembly/component declaration')
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
        from ..controllers.canonical.physical_controller import LinearEffortControllerV1
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
            controllers.append(LinearEffortControllerV1.zero_bias(compiled.binding,
                writer_id=writer, channel_keys=keys, action_names=actions, action_to_effort=matrix,
                cadence_s=artifact.timebase.control_dt, model_id='direct-effort-zero-bias-v1'))
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
