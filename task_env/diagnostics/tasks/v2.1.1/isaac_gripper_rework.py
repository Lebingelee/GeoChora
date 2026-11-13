"""Explicit native gripper experiments through the formal Env owner.

No experiment switches or provider-private state are added to Core. Run only
inside an externally supervised Isaac execution window with a frozen plan.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback


def _bootstrap_core_dependencies():
    # Import the optional Gym dependency without shadowing Isaac's OpenUSD.
    try:
        import gymnasium  # noqa: F401
        import h5py  # noqa: F401
    except ModuleNotFoundError:
        import os
        site = os.environ['GEOCHORA_CORE_SITE']
        sys.path.insert(0, site)
        try:
            import gymnasium  # noqa: F401
            import h5py  # noqa: F401
        finally:
            sys.path.remove(site)


def inspect_cube_asset(manifest: Path):
    """Read declared collision geometry using public OpenUSD; no stage edits."""
    from pxr import Usd, UsdGeom, UsdPhysics
    delivery = json.loads(manifest.read_text())
    entry = manifest.parent / delivery['entry_file']
    stage = Usd.Stage.Open(str(entry))
    units = float(UsdGeom.GetStageMetersPerUnit(stage))
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render', 'proxy'])
    rows = []
    for prim in stage.Traverse():
        if ('cube' in str(prim.GetPath()).lower() and prim.IsA(UsdGeom.Boundable)
                and prim.HasAPI(UsdPhysics.CollisionAPI)):
            bounds = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            rows.append({'path': str(prim.GetPath()), 'geometry_type': prim.GetTypeName(),
                         'world_aligned_size_m': [float(v) * units for v in bounds.GetSize()]})
    if len(rows) != 1:
        raise ValueError('expected one cube collision shape in the selected delivery')
    return {'manifest': str(manifest), 'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'entry_sha256': hashlib.sha256(entry.read_bytes()).hexdigest(),
            'meters_per_unit': units, 'collisions': rows,
            'scope': 'authored collision geometry; not contact width or inferred finger opening'}


def _observation_row(env, observation, *, phase, requested):
    import numpy as np
    joints = np.asarray(observation['state']['joint_position'], dtype=float)
    evidence = env.session.native_interval_evidence
    return {'phase': phase, 'control_step': int(env.state.control_step),
            'simulation_time_s': float(env.state.simulation_time),
            'requested_action': list(map(float, requested)),
            'ee_pose': np.asarray(observation['state']['ee_pose']).tolist(),
            'cube_pose': np.asarray(observation['privileged_state']['cube_v1_body_pose']).tolist(),
            'joint_position': joints.tolist(), 'opening_m': float(joints[-2:].sum()),
            'native_interval': evidence}


class IsaacContactObserver:
    """Public SDK event subscription, no native views or stepping ownership.

    Only contact reporting is authored on the transient stage. Body poses,
    collision/drive/material properties and source files are never changed.
    Each callback copies values before the SDK-owned buffers can expire.
    """

    def __init__(self, env):
        import omni.usd
        from omni.physx import get_physx_simulation_interface
        from pxr import PhysxSchema, UsdPhysics

        self.env, self.events = env, []
        self.paths = {}
        stage = omni.usd.get_context().get_stage()
        for name in ('left_finger', 'right_finger', 'cube_v1'):
            matches = [p for p in stage.Traverse()
                       if p.GetName() == name and p.HasAPI(UsdPhysics.RigidBodyAPI)]
            if len(matches) != 1:
                raise ValueError('contact observer needs exactly one declared body: ' + name)
            self.paths[name] = str(matches[0].GetPath())
            PhysxSchema.PhysxContactReportAPI.Apply(matches[0]).CreateThresholdAttr().Set(0.)
        self.subscription = get_physx_simulation_interface().subscribe_contact_report_events(self._on_contact)

    def _on_contact(self, headers, data):
        from pxr import PhysicsSchemaTools
        for h in headers:
            actors = [str(PhysicsSchemaTools.intToSdfPath(v)) for v in (h.actor0, h.actor1)]
            if not set(actors).intersection(self.paths.values()):
                continue
            contacts = []
            for i in range(h.contact_data_offset, h.contact_data_offset + h.num_contact_data):
                point = data[i]
                contacts.append({'position_world_m': list(point.position),
                                 'normal_world': list(point.normal),
                                 'impulse_Ns': list(point.impulse),
                                 'separation_m': float(point.separation)})
            self.events.append({'type': str(h.type), 'actors': actors,
                                'colliders': [str(PhysicsSchemaTools.intToSdfPath(v))
                                              for v in (h.collider0, h.collider1)],
                                'contacts': contacts})

    def read(self):
        before = self.env.session.state_boundary_identity()
        events, self.events = self.events, []
        if self.env.session.state_boundary_identity() != before:
            raise RuntimeError('contact report read changed the physical boundary')
        return {'boundary': before.to_mapping(), 'bodies': self.paths, 'events': events,
                'source': 'public PhysX contact report events from the five owned substeps; impulses in N s'}

    def close(self):
        self.subscription = None


def wrist_camera():
    """One diagnostic view declaration; the normal renderer owns capture."""
    import numpy as np
    from task_env.environment.config import CameraSpec
    from task_env.utils.rotation import look_at_quat_wxyz

    position = np.asarray((.10, 0., -.025))
    return CameraSpec('wrist', frame='body', parent='panda-v1/ee',
                      position=tuple(position),
                      quaternion_wxyz=look_at_quat_wxyz(position, np.asarray((0., 0., .035))),
                      width=256, height=192, fov_y=1.15, near=.005, far=2., depth=False)


def run_contact_lift(output: Path, manifest: Path, asset_inspection: Path):
    """Controlled lift after closure, explicitly separate from formal Solution.

    This tests whether a held object can rise before changing the Solution's
    readiness policy. A diagnostic success is not a formal Solution success.
    """
    import numpy as np
    from task_env import make_env

    output.mkdir(parents=True, exist_ok=False)
    asset = json.loads(asset_inspection.read_text())
    if asset['manifest_sha256'] != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise ValueError('offline asset inspection belongs to another delivery')
    result = {'case': 'contact-lift', 'status': 'RUNNING', 'explicit_substeps': 0,
              'asset': asset, 'implicit_startup_reset_steps': 'unknown',
              'intervention': 'caller commands lift after close, bypassing Solution readiness only; original Task predicate unchanged',
              'camera': 'formal frame-mounted task RGB, one frame at reset and each returned step'}
    env = session = observer = None
    recording = False
    rows = []
    code = 1
    try:
        env = make_env('pick-cube-p16-reference-v1', task_rgb_camera=wrist_camera(),
                       task_renderer='isaacsim', config={
            'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                          'physics_device': 'cuda:0', 'deployment': 'in_process',
                          'interpreter': sys.executable},
            'controller': {'profile_id': 'r3_continuous_v1'},
            'episode': {'horizon': 600},
        })
        observation, info = env.reset(seed=31)
        session = env.session
        observer = IsaacContactObserver(env)
        pose = np.asarray(observation['state']['ee_pose'], dtype=np.float32).copy()
        cube = np.asarray(observation['privileged_state']['cube_v1_body_pose'])[0, :3].copy()
        result['initial_cube_z_m'] = float(cube[2])
        result['initial_camera_receipt'] = info['task_rgb_v1']
        np.save(output / 'reset_rgb.npy', observation['task_rgb'])
        env.start_recording(output / 'episode.h5')
        recording = True
        phases = [('approach', 80, float(cube[2] + .115), 1.),
                  ('descend', 80, float(cube[2] + .045), 1.),
                  ('close', 120, float(cube[2] + .045), -1.),
                  ('lift', 120, float(cube[2] + .195), -1.),
                  ('hold', 30, float(cube[2] + .195), -1.)]
        for phase, count, height, gripper in phases:
            pose[:3] = (*cube[:2], height)
            for tick in range(count):
                action = np.asarray([*pose, gripper], dtype=np.float32)
                observation, reward, terminated, truncated, info = env.step(action)
                row = _observation_row(env, observation, phase=phase, requested=action)
                row['contacts'] = observer.read()
                row['camera'] = info['task_rgb_v1']
                row['task_metrics'] = dict(info.get('task_metrics', {}))
                if tick in (0, count - 1):
                    np.save(output / f'{phase}-{tick:03d}-rgb.npy', observation['task_rgb'])
                if len(row['native_interval']['advances']) != 5:
                    raise ValueError('native interval did not have exactly five explicit substeps')
                result['explicit_substeps'] += 5
                rows.append(row)
                with (output / 'rows.jsonl').open('a') as stream:
                    stream.write(json.dumps(row, default=str) + '\n')
                if len(rows) % 10 == 0:
                    (output / 'progress.json').write_text(json.dumps({
                        'phase': phase, 'step': len(rows), 'opening_m': row['opening_m'],
                        'cube_z': row['cube_pose'][0][2]}) + '\n')
                if terminated or truncated:
                    raise RuntimeError('contact-lift experiment terminated before its planned end')
        result['recording'] = env.finish_recording('external_stop')
        recording = False
        result.update(status='PASS', final_task_metrics=rows[-1]['task_metrics'],
                      final_opening_m=rows[-1]['opening_m'],
                      cube_rise_from_initial_m=rows[-1]['cube_pose'][0][2] - float(cube[2]))
        code = 0
    except BaseException as error:
        result.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    finally:
        (output / 'rows.json').write_text(json.dumps(rows, indent=2, default=str) + '\n')
        (output / 'before-close.json').write_text(json.dumps(result, indent=2, default=str) + '\n')
        if observer is not None:
            observer.close()
        if env is not None:
            try:
                if recording:
                    result['recording'] = env.finish_recording('execution_fault')
                env.close()
                result['close'] = session.worker_close_receipt() if session is not None else None
            except BaseException as error:
                result.update(status='FAIL', close_error=repr(error))
                code = 1
        (output / 'result.json').write_text(json.dumps(result, indent=2, default=str) + '\n')
        print(json.dumps(result, default=str), flush=True)
    if (result.get('close') or {}).get('app_owner', {}).get('close_completed'):
        import os
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    return code


def run_empty_close(output: Path, manifest: Path, asset_inspection: Path):
    import numpy as np
    from task_env import make_env
    output.mkdir(parents=True, exist_ok=False)
    # OpenUSD inspection runs separately. Importing pip pxr before Kit starts
    # loads an incompatible USD ABI into the native simulation process.
    asset = json.loads(asset_inspection.read_text())
    if asset['manifest_sha256'] != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise ValueError('offline asset inspection belongs to another delivery')
    result = {'case': 'empty-close', 'status': 'RUNNING', 'explicit_substeps': 0,
              'implicit_startup_reset_steps': 'unknown', 'asset': asset}
    env = session = None
    recording = False
    rows = []
    exit_code = 1
    try:
        env = make_env('pick-cube-p16-reference-v1', config={
            'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                          'physics_device': 'cuda:0', 'deployment': 'in_process',
                          'interpreter': sys.executable},
            'controller': {'profile_id': 'r3_continuous_v1'},
            'episode': {'horizon': 400},
        })
        observation, info = env.reset(seed=31)
        session = env.session
        hold_pose = np.asarray(observation['state']['ee_pose'], dtype=np.float32).copy()
        cube = np.asarray(observation['privileged_state']['cube_v1_body_pose'])[0, :3]
        result['initial_ee_cube_distance_m'] = float(np.linalg.norm(hold_pose[:3] - cube))
        result['construction'] = {'episode_id': session.episode_id,
                                  'materialization_id': session.provider_materialization_id}
        env.start_recording(output / 'episode.h5')
        recording = True
        for phase, count, gripper in [('close', 200, -1.), ('reopen', 60, 1.)]:
            for _ in range(count):
                action = np.asarray([*hold_pose, gripper], dtype=np.float32)
                observation, reward, terminated, truncated, info = env.step(action)
                row = _observation_row(env, observation, phase=phase, requested=action)
                advances = row['native_interval']['advances']
                if len(advances) != 5:
                    raise ValueError('native interval did not have exactly five explicit substeps')
                result['explicit_substeps'] += len(advances)
                rows.append(row)
                if terminated or truncated:
                    raise RuntimeError('empty-close experiment terminated before its planned end')
        result['recording'] = env.finish_recording('external_stop')
        recording = False
        closing = [row['opening_m'] for row in rows if row['phase'] == 'close']
        result.update(status='PASS', minimum_empty_opening_m=min(closing),
                      final_empty_opening_m=closing[-1], final_reopened_m=rows[-1]['opening_m'],
                      empty_within_0_1_mm_of_zero=abs(closing[-1]) <= .0001,
                      warning='joint opening is not the geometric distance between collision pads')
        exit_code = 0
    except BaseException as error:
        result.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    finally:
        (output / 'rows.json').write_text(json.dumps(rows, indent=2) + '\n')
        (output / 'before-close.json').write_text(json.dumps(result, indent=2, default=str) + '\n')
        if env is not None:
            try:
                if recording:
                    result['recording'] = env.finish_recording('execution_fault')
                env.close()
                result['close'] = session.worker_close_receipt() if session is not None else None
            except BaseException as error:
                result.update(status='FAIL', close_error=repr(error))
                exit_code = 1
        (output / 'result.json').write_text(json.dumps(result, indent=2, default=str) + '\n')
        print(json.dumps(result, default=str), flush=True)
    # The Env has closed its native owner; avoid the SDK interpreter teardown
    # hanging after a completed App close. Never use this before its receipt.
    if (result.get('close') or {}).get('app_owner', {}).get('close_completed'):
        import os
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)
    return exit_code


class SolutionProgress:
    """Observe the existing caller-owned Solution once, then save public facts."""

    def __init__(self, solution, output):
        self.solution, self.output = solution, output

    def __getattr__(self, name):
        return getattr(self.solution, name)

    def observe(self, observation, reward, terminated, truncated, info):
        self.solution.observe(observation, reward, terminated, truncated, info)
        readback = info['pickcube_position_execution_info_v2']
        if readback['control_step'] % 10 == 0 or self.solution.done or self.solution.failed:
            value = {'execution': readback, 'stage': self.solution.stage,
                     'task_metrics': dict(info.get('task_metrics', {})),
                     'solution_done': bool(self.solution.done), 'solution_failed': bool(self.solution.failed)}
            (self.output / 'progress.json').write_text(json.dumps(value, default=str) + '\n')


def run_solution(output: Path, manifest: Path, asset_inspection: Path):
    """Unmodified caller-owned Solution loop, same seed/horizon as the failure.

    The RGB intervention record is separate; this state-only run isolates the
    Task readiness repair without a diagnostic lift or contact instrumentation.
    """
    from task_env import make_env
    from task_env.tasks.pick_cube import build_readiness_solution
    from examples._common import run_caller_solution

    output.mkdir(parents=True, exist_ok=False)
    asset = json.loads(asset_inspection.read_text())
    if asset['manifest_sha256'] != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise ValueError('offline asset inspection belongs to another delivery')
    env = session = None
    recording = False
    result = {'case': 'solution', 'status': 'RUNNING', 'asset': asset,
              'seed': 31, 'horizon': 1000, 'intervention': 'none; formal Solution act -> env.step -> observe',
              'implicit_startup_reset_steps': 'unknown'}
    code = 1
    try:
        env = make_env('pick-cube-p16-reference-v1', config={
            'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                          'physics_device': 'cuda:0', 'deployment': 'in_process',
                          'interpreter': sys.executable},
            'controller': {'profile_id': 'r3_continuous_v1'}, 'episode': {'horizon': 1000}})
        solution = build_readiness_solution(backend='cuda', controller_profile='r3_continuous_v1')
        observation, info = env.reset(seed=31)
        session = env.session
        solution.reset(observation, info, env.metadata)
        result['initial_execution_info'] = info['pickcube_position_execution_info_v2']
        env.start_recording(output / 'episode.h5')
        recording = True
        episode = run_caller_solution(env, SolutionProgress(solution, output), observation, info, horizon=1000)
        result.update(episode=episode, solution_done=bool(solution.done), solution_failed=bool(solution.failed),
                      completion_events=solution.completion_events, solution_identity=solution.identity)
        result['recording'] = env.finish_recording('solution_completed' if solution.done else 'solution_incomplete')
        recording = False
        result['h5_sha256'] = hashlib.sha256((output / 'episode.h5').read_bytes()).hexdigest()
        result['status'] = episode['status']
        code = 0 if solution.done and not solution.failed and episode['task_success'] else 1
    except BaseException as error:
        result.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
    finally:
        (output / 'before-close.json').write_text(json.dumps(result, indent=2, default=str) + '\n')
        if env is not None:
            try:
                if recording:
                    result['recording'] = env.finish_recording('execution_fault')
                env.close()
                result['close'] = session.worker_close_receipt() if session is not None else None
            except BaseException as error:
                result.update(status='FAIL', close_error=repr(error))
                code = 1
        (output / 'result.json').write_text(json.dumps(result, indent=2, default=str) + '\n')
        print(json.dumps(result, default=str), flush=True)
    if (result.get('close') or {}).get('app_owner', {}).get('close_completed'):
        import os
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('asset', 'empty-close', 'contact-lift', 'solution'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--asset-inspection', type=Path)
    args = parser.parse_args()
    if args.case == 'asset':
        args.output.write_text(json.dumps(inspect_cube_asset(args.manifest), indent=2) + '\n')
        return 0
    _bootstrap_core_dependencies()
    if args.asset_inspection is None:
        parser.error('native case requires --asset-inspection from the separate asset process')
    import faulthandler
    faulthandler.enable()
    runner = {'empty-close': run_empty_close, 'contact-lift': run_contact_lift, 'solution': run_solution}[args.case]
    return runner(args.output, args.manifest, args.asset_inspection)


if __name__ == '__main__':
    raise SystemExit(main())
