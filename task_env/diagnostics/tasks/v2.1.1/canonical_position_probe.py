"""Bounded Runtime check of a canonical task source with a Position owner."""
import argparse
import fcntl
import json
from pathlib import Path
import resource
import sys
import time
import traceback

parser = argparse.ArgumentParser()
parser.add_argument('--provider', choices=('mujoco', 'geophys'), required=True)
parser.add_argument('--plan', required=True)
args = parser.parse_args()
plan = json.loads(Path(args.plan).read_text())
resource.setrlimit(resource.RLIMIT_AS, (plan['rss_address_space_limit_bytes'],) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (120, 125))
result = {'provider': args.provider, 'status': 'RUNNING', 'native_substeps': 0 if args.provider == 'mujoco' else None}
locks, task_binding, session = [], None, None
started = time.monotonic()
try:
    for path in plan['locks_in_order']:
        handle = open(path, 'r+')
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(handle)
    import numpy as np
    if args.provider == 'mujoco':
        import mujoco
        original_step = mujoco.mj_step
        def counted_step(*values, **kwargs):
            count = int(kwargs.get('nstep', values[2] if len(values) > 2 else 1))
            if result['native_substeps'] + count > plan['per_run_reserved_physics_substeps']:
                raise RuntimeError('reserved physics substep limit exhausted')
            result['native_substeps'] += count
            return original_step(*values, **kwargs)
        mujoco.mj_step = counted_step
    from task_env.artifacts import ExecutionSpec
    from task_env.controllers.canonical.contracts import reference_pose_action
    from task_env.controllers.canonical.execution import build_reference_position_controller
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.robots.panda import panda_reference_control_binding
    from task_env.runtime.sessions.api import PROFILE
    from task_env.runtime.sessions.control import materialize_control, position_subject_interval
    from task_env.runtime.sessions.source_composition_adapters import declared_robot_source_composer
    from task_env.tasks.pick_cube import specialization as task
    execution = {'physics_provider': args.provider, 'physics_backend': 'cpu',
                 'deployment': 'in_process', 'interpreter': sys.executable}
    physical_config = resolve_task_env_config(task.PickCubeReferenceEnv, {
        'execution': execution, 'controller': {'profile_id': 'panda-joint-effort-reference-v1'},
        'episode': {'horizon': 8}})
    position_config = resolve_task_env_config(task.PickCubeReferenceEnv, {
        'execution': execution, 'controller': {'profile_id': 'r3_continuous_v1'},
        'episode': {'horizon': 8}})
    task_binding = task.PickCubeReferenceEnv.selected_binding(physical_config)
    value = task_binding.build_for_request(args.provider, 'cpu', 31, 8)
    artifact, source = value['artifact'], value['source']
    dynamic_profile, _ = task._r3_dynamic_profile()
    controller = build_reference_position_controller(artifact, source, profile_id='r3_continuous_v1',
        dynamic_profile=dynamic_profile,
        joint_velocity_limit_rad_s=task.PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s'])
    compose = declared_robot_source_composer(position_config, robot_uid=position_config.robot_uid,
        existing_robot_entity=task.PickCubeReferenceEnv.default_robot_source_uid,
        task_body_names=task.PickCubeReferenceEnv.robot_source_roots,
        task_site_transfers=task.PickCubeReferenceEnv.robot_source_site_transfers)
    source = compose(source, artifact=artifact, controller=controller)
    result['artifact'] = artifact.identity_hash
    result['scene'] = source.scene_definition.identity_hash
    result['source_closure'] = source.source_closure_digest
    result['position_plan'] = source.position_subject_binding.plan.identity_hash
    session = materialize_control(artifact, ExecutionSpec(args.provider, PROFILE, 'none', 'cpu', 0, 'strict'),
        source=source, binding=panda_reference_control_binding(), selected_controller=controller)
    result['materialized'] = True
    session.reset_plan(value['reset_plan'])
    state = session.snapshot()
    feedback = session.control_feedback(state)
    controller.reset(state, feedback)
    before = session.state_boundary_identity().to_mapping()
    request = reference_pose_action(np.asarray([.4, 0., .4, 1., 0., 0., 0., 1.]))
    _, target = controller.compute(state, feedback, request)
    with position_subject_interval(session, target, state, controller=controller):
        next_state, _, _, _ = session.step_control_interval(target, controller, arm_schedule=controller)
    after = session.state_boundary_identity().to_mapping()
    assert after['control_step'] == before['control_step'] + 1
    assert abs(next_state.simulation_time - state.simulation_time - artifact.timebase.control_dt) < 1e-9
    result.update(status='PASS', before=before, after=after)
except BaseException as error:
    result.update(status='FAIL', error={'type': type(error).__name__, 'message': str(error)})
    traceback.print_exc()
finally:
    for resource_ in (session, task_binding):
        if resource_ is not None:
            try:
                close = getattr(resource_, 'close_task_resources', None) or getattr(resource_, 'close', None)
                if close: close()
            except BaseException as error:
                result.update(status='FAIL', cleanup_error=repr(error))
    result['wall_s'] = time.monotonic() - started
    for handle in reversed(locks):
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()
    Path('result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
raise SystemExit(0 if result['status'] == 'PASS' else 1)
