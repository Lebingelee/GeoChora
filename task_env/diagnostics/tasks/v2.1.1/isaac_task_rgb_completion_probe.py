"""Bounded Isaac task-RGB boundary and synchronous-completion probe."""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

import numpy as np

# Preload only Core dependencies; remove the Core site before Kit loads USD.
try:
    import gymnasium  # noqa: F401
    import h5py  # noqa: F401
except ModuleNotFoundError:
    core_site = os.environ['GEOCHORA_CORE_SITE']
    sys.path.insert(0, core_site)
    try:
        import gymnasium  # noqa: F401
        import h5py  # noqa: F401
    finally:
        sys.path.remove(core_site)

from task_env import make_env
from task_env.environment.config import CameraSpec
from task_env.utils.rotation import look_at_quat_wxyz


def camera_spec():
    position = np.asarray((.10, 0., -.025))
    return CameraSpec('wrist', frame='body', parent='panda-v1/ee',
        position=tuple(position), quaternion_wxyz=look_at_quat_wxyz(position, np.asarray((0., 0., .035))),
        width=256, height=192, fov_y=1.15, near=.005, far=2., depth=False)


def frame_summary(image, info):
    frame = np.asarray(image)
    if frame.shape != (192, 256, 3) or frame.dtype != np.float32 or not np.isfinite(frame).all():
        raise ValueError('task RGB frame violates its shape, dtype or finite-value contract')
    receipt = info['task_rgb_v1']
    completion = receipt['completion_evidence']
    if not completion or not completion['dispatcher_completions'][-1]['completed']:
        raise ValueError('task RGB has no completed synchronous capture witness')
    return {'sha256': hashlib.sha256(frame.tobytes()).hexdigest(),
            'capture_identity': receipt['capture_identity'],
            'renderer_generation': receipt['renderer_generation'],
            'completion_evidence': completion}


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'FAIL', 'explicit_substeps': 0,
              'implicit_startup_reset_steps': 'unknown', 'source': 'task RGB public Env'}
    env = session = None
    recording = False
    try:
        env = make_env('pick-cube-p16-reference-v1', task_rgb_camera=camera_spec(),
            task_renderer='isaacsim', config={
                'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                    'physics_device': 'cuda:0', 'deployment': 'in_process', 'interpreter': sys.executable},
                'controller': {'profile_id': 'r3_continuous_v1'}, 'episode': {'horizon': 8}})
        obs, info = env.reset(seed=31)
        session = env.session
        result['reset_1'] = frame_summary(obs['task_rgb'], info)
        env.start_recording(output / 'episode.h5')
        recording = True
        pose = np.asarray(obs['state']['ee_pose'], dtype=np.float32).copy()
        pose[0] += .002
        action = np.asarray([*pose, 1.0], dtype=np.float32)
        obs, reward, terminated, truncated, info = env.step(action)
        result['step'] = frame_summary(obs['task_rgb'], info)
        advances = session.native_interval_evidence['advances']
        if len(advances) != 5:
            raise ValueError('step did not report five explicit native substeps')
        result['explicit_substeps'] = len(advances)
        result['task_success'] = bool(info.get('is_success', False))
        result['solution_completion'] = 'not_run'
        result['recording'] = env.finish_recording('external_stop')
        recording = False
        # Capture twice against the same published boundary through the existing
        # task-camera owner; diagnostic reads no provider-private solver state.
        view = env._task_rgb_typed_state.view
        geometry = env._task_rgb_config[0]
        before = session.snapshot()
        boundary = session.state_boundary_identity()
        repeated = []
        for _ in range(2):
            capture = session.capture_task_camera(geometry, view)
            completion = session.task_camera_completion(view)
            after = session.snapshot()
            if (session.state_boundary_identity() != boundary or
                    (after.control_step, after.simulation_time) != (before.control_step, before.simulation_time)):
                raise ValueError('same-boundary render advanced the physics clock')
            if not completion['dispatcher_completions'][-1]['completed']:
                raise ValueError('repeated render did not complete')
            repeated.append({'sha256': hashlib.sha256(np.asarray(capture.rgb).tobytes()).hexdigest(),
                             'completion': completion})
        result['repeated_render'] = {'control_step': before.control_step,
                                     'simulation_time_s': before.simulation_time,
                                     'captures': repeated, 'physics_delta_steps': 0}
        previous_session = session
        obs2, info2 = env.reset(seed=31)
        result['reset_1_close'] = previous_session.worker_close_receipt()
        session = env.session
        result['reset_2'] = frame_summary(obs2['task_rgb'], info2)
        first = result['reset_1']['capture_identity']['state_boundary']
        second = result['reset_2']['capture_identity']['state_boundary']
        if first['episode_id'] == second['episode_id'] or result['reset_1']['renderer_generation'] == result['reset_2']['renderer_generation']:
            raise ValueError('second reset reused a prior episode or renderer generation')
        result['status'] = 'PASS'
    except BaseException as error:
        result.update(error=repr(error), traceback=traceback.format_exc())
    finally:
        if env is not None:
            try:
                if recording:
                    result['fault_recording'] = env.finish_recording('execution_fault')
                env.close()
                result['close'] = session.worker_close_receipt() if session is not None else None
            except BaseException as error:
                result.update(status='FAIL', close_error=repr(error))
        (output / 'result.json').write_text(json.dumps(result, indent=2, default=str) + '\n')
        print(json.dumps({'status': result['status'], 'explicit_substeps': result['explicit_substeps']}), flush=True)
    code = 0 if result['status'] == 'PASS' else 1
    if (result.get('close') or {}).get('app_owner', {}).get('close_completed'):
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
