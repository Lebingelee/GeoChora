"""S1 fail-closed contracts for the bounded dual-Entity Position route."""

from dataclasses import replace

import pytest

from task_env.controllers.canonical.contracts import StructuredActionRequestV1
from task_env.artifacts import ExecutionSpec
from task_env.diagnostics.tasks.c02b_dual_entity_candidate import (
    MAIN_ENTITY,
    SECONDARY_ENTITY,
    build_dual_entity_position_candidate,
)
from task_env.runtime.sessions.control import (
    apply_position_control_target,
    compile_control_binding_plan,
    prepare_structured_action,
)
from task_env.runtime.sessions.api import materialize


def _candidate(tmp_path):
    pytest.importorskip('scene', reason='GeoPhys public Scene importer is required')
    return build_dual_entity_position_candidate(
        tmp_path / 'dual-candidate', provider='mujoco', horizon=4,
    )


def _request(env):
    groups = []
    for profile in env.position_profiles:
        schema = profile.controller_binding().action_schema
        pose = next(
            item.pose_world for item in env.typed_state.view.frames
            if item.frame.entity_id == profile.entity_id
            and item.frame.frame_id == profile.hand_frame_id
        )
        groups.extend((
            {
                'schema_version': 'control-group-action-v1',
                'entity_id': profile.entity_id,
                'group_id': 'arm',
                'action_schema_id': schema.schema_id,
                'values': (*pose.position, *pose.quaternion_wxyz),
            },
            {
                'schema_version': 'control-group-action-v1',
                'entity_id': profile.entity_id,
                'group_id': 'gripper',
                'action_schema_id': schema.schema_id,
                'values': (1.0,),
            },
        ))
    return StructuredActionRequestV1.from_mapping({
        'schema_version': 'structured-action-request-v1',
        'scene_identity_hash': env.position_plan.scene_identity_hash,
        'binding_identity_hash': env.position_plan.identity_hash,
        'groups': list(groups),
    })


def test_dual_plan_names_resources_and_rejects_overlap_or_missing_group(tmp_path):
    candidate = _candidate(tmp_path)
    env = candidate.env
    try:
        env.reset()
        profiles = env.position_profiles
        assert tuple(profile.entity_id for profile in profiles) == (MAIN_ENTITY, SECONDARY_ENTITY)
        assert tuple(profile.writer_id for profile in profiles) == (
            'panda-main/position-servo-v1', 'panda-secondary/position-servo-v1',
        )
        assert len(env.position_plan.resource_writers) == 16
        assert len({(entity, actuator) for entity, actuator, _writer in env.position_plan.resource_writers}) == 16
        assert all(
            (entity == profile.entity_id and actuator.startswith('secondary_'))
            if profile.entity_id == SECONDARY_ENTITY
            else entity == profile.entity_id and not actuator.startswith('secondary_')
            for profile in profiles
            for entity, actuator, writer in env.position_plan.resource_writers
            if writer == profile.writer_id
        )
        with pytest.raises(ValueError, match='exactly one RobotInstance'):
            materialize(
                candidate.artifact,
                ExecutionSpec('mujoco', 'p1_2_scalar_cpu_v0', 'none', 'cpu', 0, 'strict'),
                source=candidate.source,
            )

        main_binding, secondary_binding = tuple(
            profile.controller_binding() for profile in profiles
        )
        overlapping = replace(secondary_binding, groups=main_binding.groups)
        with pytest.raises(ValueError, match='overlapping Controller writers|overlapping actuator writers'):
            compile_control_binding_plan(candidate.scene, (main_binding, overlapping))
        missing = replace(secondary_binding, groups=secondary_binding.groups[:1])
        with pytest.raises(ValueError, match='partition the complete action schema'):
            compile_control_binding_plan(candidate.scene, (main_binding, missing))

        altered_arm = replace(
            main_binding.groups[0],
            action_components=('y', 'x', 'z', 'qw', 'qx', 'qy', 'qz'),
        )
        altered_main = replace(
            main_binding, groups=(altered_arm, *main_binding.groups[1:]),
        )
        altered_plan = compile_control_binding_plan(
            candidate.scene, (altered_main, secondary_binding),
        )
        with pytest.raises(ValueError, match='Controller/action/group contract'):
            profiles[0]._validate_plan(altered_plan)
    finally:
        env.close()


def test_bad_entity_missing_group_and_wrong_plan_reject_before_compute_apply_or_step(
    monkeypatch, tmp_path,
):
    from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1

    candidate = _candidate(tmp_path)
    env = candidate.env
    try:
        env.reset()
        request = _request(env)
        counts = {'compute': 0, 'apply': 0, 'step': 0}
        original_compute = PandaPositionServoProfileV1.compute
        session_type = type(env.session)
        original_apply = session_type.apply_control
        original_step = session_type.step

        def compute(profile, *args, **kwargs):
            counts['compute'] += 1
            return original_compute(profile, *args, **kwargs)

        def apply(session, target):
            if session is env.session:
                counts['apply'] += 1
            return original_apply(session, target)

        def step(session):
            if session is env.session:
                counts['step'] += 1
            return original_step(session)

        monkeypatch.setattr(PandaPositionServoProfileV1, 'compute', compute)
        monkeypatch.setattr(session_type, 'apply_control', apply)
        monkeypatch.setattr(session_type, 'step', step)
        env.start_recording(tmp_path / 's1-no-pseudo-transition.h5')

        missing_group = replace(request, groups=request.groups[:-1])
        wrong_entity = replace(
            request,
            groups=(replace(request.groups[0], entity_id='panda-unknown'), *request.groups[1:]),
        )
        wrong_plan = replace(request, binding_identity_hash='0' * 64)
        for invalid in (missing_group, wrong_entity, wrong_plan):
            with pytest.raises(ValueError):
                env.step(invalid)
            assert counts == {'compute': 0, 'apply': 0, 'step': 0}
            assert (env.recorder.transition_count, env.recorder.observation_count) == (0, 1)
        env.stop('s1-preflight')
        env.finish_recording('s1-preflight')

        # Compute one writer directly to prove each Controller owns its memory.
        env.reset()
        profiles = env.position_profiles
        prepared = dict(prepare_structured_action(env.position_plan, _request(env)))
        _canonical, target = profiles[0].compute(
            env.typed_state, prepared[profiles[0].writer_id], env.position_plan,
        )
        assert profiles[0]._next_control_step == 1
        assert profiles[1]._next_control_step == 0

        # A self-consistent target from another provider materialization is
        # rejected against this publication before RuntimeSession.apply_control.
        wrong_boundary = replace(
            target,
            source_boundary=replace(
                target.source_boundary,
                provider_materialization_id='wrong-materialization',
            ),
        )
        applied_before = counts['apply']
        with pytest.raises(ValueError, match='source boundary'):
            apply_position_control_target(
                env.session, wrong_boundary,
                controller_profile=profiles[0], plan=env.position_plan,
                publication=env.typed_state, scene=env.position_scene,
                joint_bindings=env.position_joint_bindings,
                frame_bindings=env.position_frame_bindings,
            )
        assert counts['apply'] == applied_before
        assert counts['step'] == 0

        # Reset creates new Profiles and a new Episode boundary; a target from
        # the former episode cannot cross that lifecycle boundary.
        old_episode_id = target.source_boundary.episode_id
        env.reset()
        assert env.typed_state.view.boundary.episode_id != old_episode_id
        assert all(profile._next_control_step == 0 for profile in env.position_profiles)
        with pytest.raises(ValueError, match='source boundary'):
            apply_position_control_target(
                env.session, target,
                controller_profile=env.position_profiles[0], plan=env.position_plan,
                publication=env.typed_state, scene=env.position_scene,
                joint_bindings=env.position_joint_bindings,
                frame_bindings=env.position_frame_bindings,
            )
        assert counts['apply'] == applied_before
        assert counts['step'] == 0
    finally:
        env.close()
