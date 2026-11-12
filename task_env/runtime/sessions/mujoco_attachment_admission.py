"""MuJoCo admission of the explicitly bounded Panda fixed source.

The historic R03/R06 exact identities are checked before native import.
"""

def _validate_fixed_attachment_materialization_source(artifact, execution, source) -> None:
    """Preflight the one fixed Panda Arm+Hand plan before native import/compile."""
    from ...artifacts import FixedAttachmentPlanV1, LogicalAssemblyV1
    from ...assembly.panda_source_profiles import (
        R06B_ORDER_ASSET_VERSION, R06B_ORDER_RECIPE_ID, R06B_ORDER_SOURCE_SHA256,
        R06B_ORDER_SOURCE_REFERENCES, fixed_attachment_source_recipe,
    )
    from ...assembly import panda_source_profiles
    from ...assembly.fixed_attachment import lower_fixed_attachment_sources

    plan = source.fixed_attachment_plan
    if type(plan) is not FixedAttachmentPlanV1 or type(source.fixed_attachment_assembly) is not LogicalAssemblyV1:
        raise TypeError('fixed Attachment materialization requires the typed R03b plan and Assembly')
    if execution.physics_provider != 'mujoco' or execution.backend != 'cpu' or execution.render_provider != 'none':
        raise ValueError('fixed Attachment materialization is bounded to MuJoCo CPU without rendering')
    if (artifact.timebase.physics_dt, artifact.timebase.control_substeps, artifact.timebase.control_dt) != (
        0.002, 5, 0.01,
    ):
        raise ValueError('fixed Attachment materialization requires the R03b 2 ms / 100 Hz timebase')
    if source.free_joints:
        raise ValueError('fixed Attachment must not admit a free root joint')
    scene = source.scene_definition
    if scene is None:
        raise ValueError('fixed Attachment materialization requires a pinned canonical Scene-v3')
    artifact.validate_scene(scene)
    panda_source_profiles.validate_panda_fixed_attachment_scene(plan, source.fixed_attachment_assembly, scene)
    sources = source.fixed_attachment_sources
    if set(sources) != {'panda-arm', 'panda-hand'}:
        raise ValueError('fixed Attachment source pair differs from the exact two-Entity recipe')
    recipe = fixed_attachment_source_recipe(
        sources['panda-arm'].xml, sources['panda-hand'].xml,
    )
    expected_asset_version = (R06B_ORDER_ASSET_VERSION if recipe == R06B_ORDER_RECIPE_ID
                              else 'menagerie-b846dd12')
    expected_source_hashes = (
        (R06B_ORDER_SOURCE_SHA256['panda-arm'], R06B_ORDER_SOURCE_SHA256['panda-hand'])
        if recipe == R06B_ORDER_RECIPE_ID else (
            'e7090a5e2384b18a223ef532d98bf914f7f9a6b74dc8bc9f74c8291201074071',
            'd2a6539d0fd7c55c75c14f11c78f04505ee33f31d93e6112e3ad7120e5ee786a',
        )
    )
    expected_scene_id = ('phase-ii-r06b-order-v1-fixed-attachment'
                         if recipe == R06B_ORDER_RECIPE_ID else 'phase-ii-r03b-fixed-attachment')
    expected_assembly_revision = (R06B_ORDER_RECIPE_ID if recipe == R06B_ORDER_RECIPE_ID
                                  else 'r03b-001')
    expected_task_ids = ({'phase-ii-r06b-order-v1-fixed-arm-hand',
                          'phase-ii-r06b-order-v1-attached-leaf-position'}
                         if recipe == R06B_ORDER_RECIPE_ID else
                         {'phase-ii-r03b-fixed-arm-hand', 'phase-ii-r03c-attached-leaf-position'})
    if (
        plan.parent_entity_id, plan.child_entity_id,
        plan.parent_asset_id, plan.parent_asset_version,
        plan.child_asset_id, plan.child_asset_version,
        plan.parent_source_sha256, plan.child_source_sha256,
        plan.license_source_sha256, plan.parent_mount_site_name,
        plan.child_mount_body_name, plan.namespace_prefix,
        plan.parent_mount.frame_id, plan.child_mount.frame_id,
        plan.parent_root.frame_id, plan.child_root.frame_id,
        plan.reset_hand_opening_m, plan.assembly_revision,
        scene.scene_id,
    ) != (
        'panda-arm', 'panda-hand', 'panda-arm-nohand', expected_asset_version,
        'panda-hand', expected_asset_version,
        *expected_source_hashes,
        'a6cba85bc92e0cff7a450b1d873c0eaa2e9fc96bf472df0247a26bec77bf3ff9',
        'attachment_site', 'probe_hand_hand', 'probe_hand_',
        'attachment_site', 'hand', 'link0', 'hand', 0.076,
        expected_assembly_revision, expected_scene_id,
    ):
        raise ValueError('fixed Attachment source pair differs from the accepted R03a source recipe')
    if artifact.task_id not in expected_task_ids:
        raise ValueError('fixed Attachment TaskArtifact identity differs from its exact source recipe')
    if (
        plan.parent_site_from_child_root.position,
        plan.parent_site_from_child_root.quaternion_wxyz,
        plan.attach_frame_from_child_worldbody.position,
        plan.attach_frame_from_child_worldbody.quaternion_wxyz,
    ) != (
        (0.0, 0.0, 0.0), (0.9238795391929064, 0.0, 0.0, 0.38268341623423263),
        (0.0, 0.0, 0.0), (0.38268341623423263, 0.0, 0.0, -0.9238795391929064),
    ):
        raise ValueError('fixed Attachment mount direction or child-frame compensation differs from the source oracle')
    if plan.collision_policy != 'source_preserved' or plan.extra_cross_entity_overrides:
        raise ValueError('fixed Attachment collision admission must preserve source filters and exclusions')
    assets = {(asset.asset_id, asset.asset_version): asset for asset in scene.assets}
    source_references = (
        (R06B_ORDER_SOURCE_REFERENCES['panda-arm'], R06B_ORDER_SOURCE_REFERENCES['panda-hand'])
        if recipe == R06B_ORDER_RECIPE_ID else (
            'menagerie:franka_emika_panda/panda_nohand.xml',
            'menagerie:franka_emika_panda/hand.xml',
        )
    )
    for (asset_id, asset_version, source_reference) in zip(
        (plan.parent_asset_id, plan.child_asset_id),
        (plan.parent_asset_version, plan.child_asset_version), source_references, strict=True,
    ):
        asset = assets[(asset_id, asset_version)]
        if (asset.source_reference, asset.source_revision, asset.license_id) != (
            source_reference, 'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7', 'Apache-2.0',
        ):
            raise ValueError('fixed Attachment Asset provenance differs from the pinned source recipe')
    if source.task_artifact_hash != artifact.identity_hash:
        raise ValueError('fixed Attachment RuntimeSource does not bind the exact TaskArtifact')
    if source.scene_source.source_id != f'scene-definition-v3:{scene.identity_hash}':
        raise ValueError('fixed Attachment RuntimeSource ID differs from the pinned Scene')
    if set(source.joints) != set(artifact.initialization.joint_position):
        raise ValueError('fixed Attachment Joint bindings do not cover the exact reset declaration')
    if any(source.joints.get(key) != value for key, value in plan.native_joint_names.items()):
        raise ValueError('fixed Attachment Joint binding differs from its Entity/native map')
    if source.bodies != plan.native_body_names or source.frames != plan.native_site_names:
        raise ValueError('fixed Attachment body/Site bindings differ from their explicit maps')
    expected_arm_targets = {
        f'{plan.parent_entity_id}/joint{index}': plan.native_actuator_names[
            f'{plan.parent_entity_id}/actuator{index}'
        ] for index in range(1, 8)
    }
    if dict(source.joint_targets) != expected_arm_targets:
        raise ValueError('fixed Attachment Arm target mapping differs from its seven named actuator owners')
    expected_hand_open = (plan.native_actuator_names[f'{plan.child_entity_id}/actuator8'],)
    if source.open_actuators != expected_hand_open:
        raise ValueError('fixed Attachment open-actuator mapping differs from source Hand actuator8')
    # The source and path closure are re-read here, still before importing MuJoCo.
    lowered = lower_fixed_attachment_sources(
        parent_source=source.scene_source,
        source_by_entity=source.fixed_attachment_sources,
        scene=scene,
        plan=plan,
        assembly=source.fixed_attachment_assembly,
        source_profile=panda_source_profiles,
    )
    if lowered.source_closure_sha256 != source.source_closure_digest:
        raise ValueError('fixed Attachment RuntimeSource closure differs from its measured source closure')
