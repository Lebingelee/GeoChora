"""Source-bound point-reference profile; no native build or physics."""


def test_fixed_frame_point_wrench_is_distinct_from_legacy_profile(tmp_path):
    from types import SimpleNamespace
    import math
    import pytest
    from task_env.artifacts import PoseWorld
    from task_env.registry import make_env
    from task_env.runtime.sessions.physical_control import resolve_body_wrench_at_poses

    envs = []
    try:
        for index, profile in enumerate(('panda-direct-effort-wrench-v1',
                                         'panda-fixed-frame-point-wrench-v1')):
            env = make_env('panda-position-servo-candidate-v1', config={
                'provider': 'mujoco', 'backend': 'cpu', 'horizon': 8,
                'physical_profile': profile, 'source_workspace': str(tmp_path / str(index)),
            })
            envs.append(env)
        old, new = (env.binding.physical_control_profile(env) for env in envs)
        old_wrench, new_wrench = (execution.controllers[-1].profile for execution in (old, new))
        assert old_wrench.expression_frame.frame_id == 'hand'
        assert old_wrench.moment_reference == (0., 0., 0.)
        assert new_wrench.expression_frame.entity_id == 'square-peg-instance'
        assert new_wrench.expression_frame.frame_id == 'peg1'
        assert new_wrench.point_frame.frame_id == new_wrench.moment_reference_frame.frame_id == 'hand'
        assert new_wrench.point == new_wrench.moment_reference == (0.01, 0., 0.)
        assert old.controllers[-1].identity != new.controllers[-1].identity
        assert any(field.entity_id == 'square-peg-instance' and field.subject_id == 'peg1'
                   for field in new.requirements.requirements)
        # An offset rotating with the hand must change its moment while the
        # force remains fixed in the explicitly separate expression frame.
        half = math.sqrt(0.5)
        poses = {
            new_wrench.expression_frame: PoseWorld((0., 0., 0.), (1., 0., 0., 0.)),
            new_wrench.point_frame: PoseWorld((0., 0., 0.), (half, 0., 0., half)),
        }
        command = SimpleNamespace(expressed_in=new_wrench.expression_frame,
            point_frame=new_wrench.point_frame, moment_reference_frame=new_wrench.moment_reference_frame,
            point=new_wrench.point, moment_reference=new_wrench.moment_reference,
            force_N=(0., 0., 1.), torque_Nm=(0., 0., 0.))
        _, force, moment = resolve_body_wrench_at_poses(command, new_wrench.point_frame, poses)
        assert force == pytest.approx((0., 0., 1.))
        assert moment == pytest.approx((0.01, 0., 0.), abs=1e-12)
        poses[new_wrench.point_frame] = PoseWorld((0., 0., 0.), (half, 0., half, 0.))
        _, force, moment = resolve_body_wrench_at_poses(command, new_wrench.point_frame, poses)
        assert force == pytest.approx((0., 0., 1.))
        assert moment == pytest.approx((0., 0., 0.), abs=1e-12)
    finally:
        for env in envs:
            env.close()


def test_free_body_fixture_has_distinct_versioned_source_and_point_reference(tmp_path):
    from dataclasses import replace
    import pytest
    from task_env.artifacts import ExecutionSpec
    from task_env.registry import make_env
    from task_env.runtime.sessions.api import _validate_v1_materialization_source
    env = make_env('panda-position-servo-candidate-v1', config={
        'provider': 'mujoco', 'backend': 'cpu', 'horizon': 8,
        'physical_profile': 'panda-free-body-point-wrench-v1',
        'source_workspace': str(tmp_path / 'fixture'),
    })
    try:
        execution = env.binding.physical_control_profile(env)
        source = env.value['source']
        wrench = execution.controllers[-1].profile
        assert env.artifact.task_id == 'panda-free-body-point-wrench'
        assert source.free_joints['probe/probe_body'] == 'probe_free'
        assert (wrench.entity_id, wrench.body_id) == ('probe', 'probe_body')
        assert wrench.point_frame == wrench.moment_reference_frame == wrench.expression_frame
        assert wrench.point == wrench.moment_reference == (-0.57, -0.045, 0.478)
        assert source.source_closure_digest != 'aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47'
        spec = ExecutionSpec('mujoco', 'p1_2_scalar_cpu_v0', 'none', 'cpu', 0, 'strict')
        _validate_v1_materialization_source(env.artifact, spec, source)
        with pytest.raises(ValueError, match='exactly match'):
            _validate_v1_materialization_source(env.artifact, spec, replace(source, free_joints={}))
        with pytest.raises(ValueError, match='canonical floating Joint'):
            _validate_v1_materialization_source(env.artifact, spec,
                replace(source, free_joints={'probe/probe_body': 'wrong_joint'}))
    finally:
        env.close()
