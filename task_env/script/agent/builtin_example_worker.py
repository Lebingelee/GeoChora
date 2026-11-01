"""One finite real episode for the versioned built-in PickCube Harness mode."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

_CORE_ROOT = Path(__file__).resolve().parents[3]
if str(_CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CORE_ROOT))
_CORE_SITE = os.environ.get('GEOCHORA_CORE_SITE')
if _CORE_SITE and Path(_CORE_SITE).is_dir() and _CORE_SITE not in sys.path:
    # Keep Isaac's native packages first; use the frozen Core environment only
    # for Python dependencies that the Isaac distribution does not ship.
    sys.path.append(_CORE_SITE)

from builtin_example_schema import BuiltinPickCubeExampleV1, ExampleWorkingTreeScopeV1
from catalog_query import core_context
from harness_compiler import compile_builtin_pickcube_example


def _write(path: Path, value):
    def jsonable(item):
        if isinstance(item, dict):
            return {str(key): jsonable(child) for key, child in item.items()}
        if isinstance(item, (tuple, list)):
            return [jsonable(child) for child in item]
        if hasattr(item, 'to_mapping') and callable(item.to_mapping):
            return jsonable(item.to_mapping())
        if hasattr(item, 'item') and callable(item.item):
            return jsonable(item.item())
        return item

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(jsonable(value), sort_keys=True, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def _numeric_check(trajectory):
    import numpy as np
    from task_env.trajectory.canonical.h5 import arrays

    for name, value in arrays(trajectory).items():
        if value.dtype.kind in 'fc' and not np.isfinite(value).all():
            raise ValueError(f'canonical H5 numeric field {name} contains nonfinite values')
    return {name: list(value.shape) for name, value in arrays(trajectory).items()}


def _planned_action_count(trajectory):
    """Count Core-planned transitions from the loaded canonical trajectory."""
    transitions = getattr(trajectory, 'transitions', None)
    if transitions is None:
        raise TypeError('canonical trajectory transitions are required')
    return sum(1 for transition in transitions if transition.planned_action is True)


def _read_f06_position_h5(path: Path, output: Path, row: dict) -> dict:
    """Validate the existing generic-v3 Position recorder and planned-action trace."""
    import h5py
    import numpy as np
    from task_env.recorders import load_structured_control_records_h5

    generic = load_structured_control_records_h5(path)
    transition_count = generic['transition_count']
    observation_count = generic['observation_count']
    profile = generic['env_meta'].get('reference_profile', {})
    if not isinstance(profile, dict):
        raise ValueError('F06 v3 H5 has no Position source-profile metadata')
    expected_profile = {
        'provider': 'isaacsim', 'backend': 'cuda', 'device': 'cuda:0',
        'determinism_mode': 'best_effort',
        'task_artifact_identity_hash': row.get('artifact_sha256'),
        'controller_identity': row.get('controller_identity'),
        'solution_identity': row.get('solution_identity'),
        'source_id': row.get('runtime_source_id'),
    }
    for key, expected in expected_profile.items():
        if profile.get(key) != expected:
            raise ValueError(f'F06 v3 H5 source profile differs at {key}')
    if (not profile.get('source_closure_digest')
            or profile.get('delivery_manifest_sha256') != row.get('source_delivery_manifest_sha256')):
        raise ValueError('F06 v3 H5 omits its pinned source closure or delivery manifest identity')
    bootstrap = profile.get('native_public_bootstrap_receipt')
    if not isinstance(bootstrap, dict) or bootstrap.get('schema_version') != 'isaac-public-physics-bootstrap-v1':
        raise ValueError('F06 v3 H5 omits the public Isaac bootstrap counter receipt')
    before, after, bootstrap_steps = (
        bootstrap.get('step_index_before'), bootstrap.get('step_index_after'),
        bootstrap.get('physics_steps'),
    )
    dt = bootstrap.get('physics_dt_s')
    bootstrap_time = bootstrap.get('physics_time_s')
    if (any(type(value) is not int or value < 0 for value in (before, after, bootstrap_steps))
            or after - before != bootstrap_steps or type(dt) not in (int, float)
            or type(bootstrap_time) not in (int, float)
            or not np.isfinite((dt, bootstrap_time)).all()
            or dt != row['physics_dt_s'] or bootstrap_steps > 10
            or not np.isclose(bootstrap_time, bootstrap_steps * dt, rtol=0.0, atol=1e-8)):
        raise ValueError('F06 public Isaac bootstrap counters/time exceed or differ from the run plan')
    shapes = {}
    with h5py.File(path, 'r') as handle:
        def inspect_dataset(name, value):
            if isinstance(value, h5py.Dataset):
                data = value[...]
                if data.dtype.kind in 'fc' and not np.isfinite(data).all():
                    raise ValueError(f'F06 H5 numeric field {name} contains nonfinite values')
                if data.dtype.kind in 'biufc':
                    shapes[name] = list(data.shape)
        handle.visititems(inspect_dataset)
    trace = json.loads((output / 'step_trace.json').read_text())
    trace_rows = trace.get('rows', [])
    if len(trace_rows) != transition_count or trace.get('completed_transitions') != transition_count:
        raise ValueError('F06 action trace does not cover every finalized Position transition')
    expected_control_dt = row['physics_dt_s'] * row['control_substeps']
    if any(not np.isclose(
            float(item.get('simulation_time_after_s')) - float(item.get('simulation_time_before_s')),
            expected_control_dt, rtol=0.0, atol=1e-7,
    ) for item in trace_rows):
        raise ValueError('F06 Position trace interval clocks differ from the frozen physics/control timebase')
    controls = generic['structured_controls']
    planned_rows = [item for item in trace_rows
                    if item.get('planned_action') is True and item.get('readiness_hold') is not True]
    planning_count = len(planned_rows)
    if planning_count <= 0:
        raise ValueError('F06 episode contains no non-hold Core-planned action')
    for index, (control, trace_row) in enumerate(zip(controls, trace_rows, strict=True)):
        if control is None:
            raise ValueError(f'F06 H5 transition {index} has no structured control record')
        request_values = tuple(value for group in control.request.groups for value in group.values)
        observed_values = tuple(trace_row.get('planned_action_values', ()))
        if (len(request_values) != 8 or len(observed_values) != 8
                or not np.allclose(request_values, observed_values, rtol=0.0, atol=1e-7)):
            raise ValueError(f'F06 H5 transition {index} differs from its Core solution proposal trace')
    return {
        'transition_count': transition_count,
        'observation_count': observation_count,
        'planning_action_count': planning_count,
        'profile': profile,
        'bootstrap_steps': bootstrap_steps,
        'completed_interval_physics_steps': transition_count * row['control_substeps'],
        'native_steps_measured_completed': bootstrap_steps + transition_count * row['control_substeps'],
        'numeric_shapes': shapes,
    }


def _prepare_output_directory(output: Path):
    output = output.resolve()
    if output.exists():
        unexpected = {path.name for path in output.iterdir()} - {
            'worker.stdout.log', 'worker.stderr.log', 'run_plan.json', 'run_preflight.json',
        }
        if unexpected:
            raise FileExistsError(f'worker output directory already contains data: {sorted(unexpected)}')
    else:
        output.mkdir(parents=True, exist_ok=False)
    return output


def _terminate_isaac_worker(exit_code: int) -> None:
    """Leave the isolated Kit process after its durable run receipt is written."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            pass
    os._exit(int(exit_code))


def _install_action_trace(env, path: Path):
    """Capture the public expert proposal and state around each step attempt."""
    capture = {'attempted': 0, 'completed': 0, 'rows': []}
    position_route = (
        bool(getattr(env, 'position_profile', False))
        and getattr(env, 'value', {}).get('f06_pickcube_isaac_input') is not None
    )
    original_step = env._step_position_profile if position_route else env._step

    def pose(state, name):
        value = getattr(state, 'pose_world', {}).get(name)
        if value is None:
            return None
        return {'position_m': list(value.position), 'quaternion_wxyz': list(value.quaternion_wxyz)}

    def controller_diagnostics():
        controller = getattr(env, 'controller', None)
        value = getattr(controller, 'last_arm_diagnostics', None)
        return dict(value) if isinstance(value, dict) else None

    def arm_state(state, field):
        values = getattr(state, field, {})
        return {f'panda-v1/joint{i}': float(values[f'panda-v1/joint{i}'])
                for i in range(1, 8) if f'panda-v1/joint{i}' in values}

    def write_trace():
        _write(path, {
            'schema_version': 'harness-builtin-pickcube-action-trace-v1',
            'provider': env.provider, 'seed': getattr(getattr(env, 'sample', None), 'task_seed', None),
            'attempted_actions': capture['attempted'], 'completed_transitions': capture['completed'],
            'rows': capture['rows'],
        })

    def observed_step(action, *, proposal=None, observer_solution=None):
        capture['attempted'] += 1
        state = env.state
        if position_route:
            groups = {(group.entity_id, group.group_id): group for group in action.groups}
            entity_id = env.position_profiles[0].entity_id
            values = tuple(float(value) for value in (
                *groups[(entity_id, 'arm')].values,
                *groups[(entity_id, 'gripper')].values,
            ))
        else:
            values = tuple(float(value) for value in action)
        proposal_diagnostics = dict(getattr(proposal, 'diagnostics', {}))
        row = {
            'attempt': capture['attempted'],
            'control_step_before': int(state.control_step),
            'simulation_time_before_s': float(state.simulation_time),
            'proposal_stage': getattr(proposal, 'stage', None),
            'proposal_diagnostics': proposal_diagnostics,
            'planned_action': proposal is not None,
            'readiness_hold': proposal_diagnostics.get('readiness_hold') is True,
            'planned_action_values': list(values),
            'planned_tcp_pose': list(values[:7]),
            'gripper_request': values[7] if len(values) >= 8 else None,
            'eef_pose_before': pose(state, 'panda-v1/ee'),
            'cube_pose_before': pose(state, 'cube-v1'),
            'arm_joint_position_before_rad': arm_state(state, 'joint_position'),
            'arm_joint_velocity_before_rad_s': arm_state(state, 'joint_velocity'),
            'task_metrics_before': dict(getattr(env, 'info', {}).get('task_metrics', {})),
        }
        try:
            result = original_step(action, proposal=proposal, observer_solution=observer_solution)
        except BaseException as error:
            row.update(error={'type': type(error).__name__, 'message': str(error)})
            fault = getattr(env, 'execution_fault', None)
            row['execution_fault'] = fault.to_mapping() if hasattr(fault, 'to_mapping') else None
            row['control_step_after'] = int(env.state.control_step)
            row['simulation_time_after_s'] = float(env.state.simulation_time)
            row['eef_pose_after'] = pose(env.state, 'panda-v1/ee')
            row['cube_pose_after'] = pose(env.state, 'cube-v1')
            row['arm_joint_position_after_rad'] = arm_state(env.state, 'joint_position')
            row['arm_joint_velocity_after_rad_s'] = arm_state(env.state, 'joint_velocity')
            row['controller_diagnostics'] = controller_diagnostics()
            capture['rows'].append(row)
            write_trace()
            raise
        capture['completed'] += 1
        row['control_step_after'] = int(env.state.control_step)
        row['simulation_time_after_s'] = float(env.state.simulation_time)
        row['eef_pose_after'] = pose(env.state, 'panda-v1/ee')
        row['cube_pose_after'] = pose(env.state, 'cube-v1')
        row['arm_joint_position_after_rad'] = arm_state(env.state, 'joint_position')
        row['arm_joint_velocity_after_rad_s'] = arm_state(env.state, 'joint_velocity')
        row['controller_diagnostics'] = controller_diagnostics()
        row['task_metrics_after'] = dict(getattr(env, 'info', {}).get('task_metrics', {}))
        capture['rows'].append(row)
        if capture['attempted'] % 5 == 0:
            write_trace()
        return result

    if position_route:
        env._step_position_profile = observed_step
    else:
        env._step = observed_step
    return capture, write_trace


def run_one(spec, catalog, scope, *, seed: int, output: Path):
    from examples._common import run_expert
    from task_env.trajectory.canonical.h5 import load as load_canonical

    output = _prepare_output_directory(output)
    started = time.perf_counter()
    row = {
        'schema_version': 'harness-builtin-pickcube-example-run-v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'example_id': spec.example_id, 'example_spec_sha256': spec.identity_sha256,
        'task_uid': spec.task_uid, 'provider': spec.provider, 'backend': spec.backend,
        'device': spec.device, 'profile': spec.controller_profile,
        'seed': seed, 'horizon_control_ticks': spec.horizon_control_ticks,
        'physics_dt_s': spec.physics_dt_s, 'control_substeps': spec.control_substeps,
        'construction_succeeded': False, 'reset_succeeded': False,
        'solution_identity': None, 'controller_identity': None,
        'planning_action_count': 0, 'executed_transition_count': 0,
        'task_success': None, 'task_failure': None, 'expert_complete': None,
        'solution_done': None, 'solution_failed': None, 'terminated': None,
        'truncated': None, 'execution_fault': None,
        'recording': None, 'cold_read': None, 'close_attempted': False,
        'close_succeeded': False, 'errors': [], 'status': 'INVALID',
        'qualification': False,
        'isaac_app_precompile_start_attempted': False,
        'isaac_app_precompile_start_completed': False,
        'isaac_app_owner_close_receipt': None,
    }
    env = None
    app_owner = None
    action_trace = None
    write_action_trace = None
    recording_started = False
    h5 = output / 'episode.h5'
    execution_phase = 'worker_setup'
    try:
        context = core_context(catalog['core_repo'])
        if spec.provider == 'isaacsim':
            # The USD delivery compiler imports OpenUSD while inspecting the
            # frozen source closure. Kit must configure Isaac's pxr extension
            # paths before that import, and runtime materialization must reuse
            # this same process-owned App.
            execution_phase = 'isaac_app_precompile_startup'
            row['isaac_app_precompile_start_attempted'] = True
            from task_env.runtime.sessions.isaac_native_io import _process_app_owner

            app_owner = _process_app_owner()
            app_owner.open()
            row['isaac_app_precompile_start_completed'] = True
        # The built-in profile has its own tracked-clean + exact untracked
        # scope; the legacy strict catalog validator correctly remains strict.
        execution_phase = 'compile'
        compiled = compile_builtin_pickcube_example(
            spec, catalog, working_tree_scope=scope,
        )
        env = compiled.make_env()
        row.update(construction_succeeded=True,
                   artifact_sha256=compiled.artifact_hash,
                   construction_id=compiled.construction_id,
                   recipe_identity=compiled.recipe_identity,
                   source_revision=compiled.source_revision,
                   source_sha256=compiled.source_sha256,
                   source_delivery_manifest_sha256=compiled.source_sha256.get(
                       'f06_delivery_manifest_sha256'
                   ),
                   runtime_source_id=compiled.runtime_source_id,
                   runtime_source_sha256=compiled.runtime_source_sha256,
                   working_tree_scope=compiled.working_tree_scope,
                   repo_dirty=compiled.repo_dirty,
                   core_commit=context['core_commit'])
        execution_phase = 'reset'
        _, reset_info = env.reset(seed=seed)
        row['reset_succeeded'] = True
        row['reset_sample'] = {
            'task_seed': env.sample.task_seed,
            'sampler_id': env.sample.sampler_id,
            'sampler_version': env.sample.sampler_version,
            'cube_v1': {
                'position_m': list(env.sample.poses_world['cube-v1'].position),
                'quaternion_wxyz': list(env.sample.poses_world['cube-v1'].quaternion_wxyz),
            },
        }
        row['solution_identity'] = env.solution.identity
        row['controller_identity'] = env.controller.identity
        row['provider_materialization_id'] = env.session.provider_materialization_id
        action_trace, write_action_trace = _install_action_trace(env, output / 'step_trace.json')
        env.start_recording(h5)
        recording_started = True
        execution_phase = 'solution_execution'
        episode = run_expert(
            env, seed=seed, horizon=spec.horizon_control_ticks,
            already_reset=True, initial_info=reset_info,
        )
        row['episode'] = episode
        row.update(
            task_success=episode['task_success'], task_failure=episode['task_failure'],
            expert_complete=episode['expert_complete'], solution_done=episode['solution_done'],
            solution_failed=episode['solution_failed'], terminated=episode['terminated'],
            truncated=episode['truncated'], executed_transition_count=episode['transitions'],
        )
        reason = episode.get('failure_reason') or (
            'task_success' if episode.get('task_success') else 'task_or_expert_incomplete'
        )
        if episode.get('truncated') and episode.get('transitions') == spec.horizon_control_ticks:
            reason = 'horizon_reached'
        row['recorder_finalize'] = env.finish_recording(reason)
        recording_started = False
    except BaseException as error:
        row['errors'].append({
            'phase': execution_phase, 'type': type(error).__name__, 'message': str(error),
            'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__)),
        })
        fault = getattr(error, 'execution_fault', None)
        if fault is None and env is not None:
            fault = getattr(env, 'execution_fault', None)
        if fault is not None:
            row['execution_fault'] = fault.to_mapping() if hasattr(fault, 'to_mapping') else str(fault)
    finally:
        if write_action_trace is not None:
            try:
                write_action_trace()
            except BaseException as error:
                row['errors'].append({'phase': 'action-trace', 'type': type(error).__name__, 'message': str(error)})
        if action_trace is not None:
            row['solution_action_attempt_count'] = action_trace['attempted']
            row['solution_action_completed_count'] = action_trace['completed']
            row['action_trace'] = 'step_trace.json'
        if env is not None:
            if recording_started:
                try:
                    # Faulted/incomplete canonical intervals must remain
                    # unfinalized; do not turn them into apparently valid H5.
                    row['recording_finalize_skipped'] = 'execution did not return a complete episode'
                except BaseException as error:
                    row['errors'].append({'phase': 'finalize', 'type': type(error).__name__, 'message': str(error)})
            row['close_attempted'] = True
            try:
                env.close()
                row['close_succeeded'] = True
            except BaseException as error:
                row['errors'].append({'phase': 'close', 'type': type(error).__name__, 'message': str(error),
                                      'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__))})
        if app_owner is not None:
            # Env/session close normally closes this shared owner. Calling its
            # idempotent close here also covers compile failures before Env
            # construction and retains cleanup evidence in the worker receipt.
            try:
                app_owner.close()
            except BaseException as error:
                row['errors'].append({
                    'phase': 'isaac_app_close', 'type': type(error).__name__,
                    'message': str(error),
                    'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__)),
                })
            try:
                row['isaac_app_owner_close_receipt'] = app_owner.close_receipt()
            except BaseException as error:
                row['errors'].append({
                    'phase': 'isaac_app_close_receipt', 'type': type(error).__name__,
                    'message': str(error),
                })
    if h5.is_file():
        try:
            if spec.provider == 'isaacsim':
                readback = _read_f06_position_h5(h5, output, row)
                row['planning_action_count'] = readback['planning_action_count']
                row['native_bootstrap_steps'] = readback['bootstrap_steps']
                row['native_completed_interval_steps'] = readback['completed_interval_physics_steps']
                row['native_steps_measured_completed'] = readback['native_steps_measured_completed']
                profile = readback['profile']
                transition_count = readback['transition_count']
                observation_count = readback['observation_count']
                row['recording'] = {
                    'path': h5.name, 'sha256': hashlib.sha256(h5.read_bytes()).hexdigest(),
                    'bytes': h5.stat().st_size, 'schema': 'task-env-h5/v3',
                    'transitions': transition_count, 'observations': observation_count,
                    't_plus_one_valid': observation_count == transition_count + 1,
                    'numeric_shapes': readback['numeric_shapes'],
                    'provider_build': profile.get('provider_build_identity'),
                    'source_provenance': {
                        'source_id': profile.get('source_id'),
                        'source_closure_digest': profile.get('source_closure_digest'),
                    },
                    'controller_identity': profile.get('controller_identity'),
                    'solution_identity': profile.get('solution_identity'),
                }
                row['producer_readback'] = 'same-process-structured-control-v3-reader-pass'
            else:
                trajectory = load_canonical(h5)
                shapes = _numeric_check(trajectory)
                transition_count = len(trajectory.transitions)
                observation_count = len(trajectory.boundaries)
                row['planning_action_count'] = _planned_action_count(trajectory)
                metadata = trajectory.metadata.to_mapping()
                if observation_count != transition_count + 1:
                    raise ValueError('canonical trajectory does not satisfy T+1')
                if metadata.get('task_artifact_hash') != row.get('artifact_sha256'):
                    raise ValueError('H5 TaskArtifact identity differs from compiled built-in task')
                if metadata.get('controller_identity') != row.get('controller_identity'):
                    raise ValueError('H5 controller identity differs from executed controller')
                if metadata.get('expert_identity') != row.get('solution_identity'):
                    raise ValueError('H5 solution identity differs from executed solution')
                if [item.requested_action for item in trajectory.transitions] and row['planning_action_count'] == 0:
                    raise ValueError('no Core solution-planned action was recorded')
                row['recording'] = {
                    'path': h5.name, 'sha256': hashlib.sha256(h5.read_bytes()).hexdigest(),
                    'bytes': h5.stat().st_size, 'schema': 'canonical-v0',
                    'transitions': transition_count, 'observations': observation_count,
                    't_plus_one_valid': observation_count == transition_count + 1,
                    'numeric_shapes': shapes,
                    'provider_build': metadata.get('provider_provenance'),
                    'source_provenance': metadata.get('source_provenance'),
                    'controller_identity': metadata.get('controller_identity'),
                    'solution_identity': metadata.get('expert_identity'),
                }
                row['producer_readback'] = 'same-process-canonical-reader-pass'
        except BaseException as error:
            row['errors'].append({'phase': 'h5-readback', 'type': type(error).__name__, 'message': str(error),
                                  'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__))})
    runtime_valid = (
        row['construction_succeeded'] and row['reset_succeeded']
        and row['executed_transition_count'] > 0 and row['planning_action_count'] > 0
        and row['execution_fault'] is None and not row['errors']
        and row['recording'] is not None and row['close_succeeded']
    )
    row['runtime_valid'] = bool(runtime_valid)
    row['task_outcome'] = (
        'SOLVED' if row.get('task_success') and row.get('expert_complete')
        else 'TASK_OR_EXPERT_FAILURE_REPORTED' if runtime_valid
        else 'UNRESOLVED_RUNTIME_FAILURE'
    )
    row['status'] = 'RUNTIME_VALID' if runtime_valid else 'INVALID'
    row['wall_time_s'] = time.perf_counter() - started
    row['close_result'] = 'PASS' if row['close_succeeded'] else 'FAIL'
    _write(output / 'run.json', row)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--working-tree-scope', type=Path, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    spec = BuiltinPickCubeExampleV1.load(args.spec)
    scope = ExampleWorkingTreeScopeV1.load(args.working_tree_scope)
    catalog = json.loads(args.catalog.read_text())
    row = run_one(spec, catalog, scope, seed=args.seed, output=args.output)
    print(json.dumps({'seed': row['seed'], 'provider': row['provider'],
                      'status': row['status'], 'task_outcome': row['task_outcome'],
                      'errors': row['errors']}, sort_keys=True), flush=True)
    exit_code = 0 if row['runtime_valid'] else 1
    if spec.provider == 'isaacsim':
        _terminate_isaac_worker(exit_code)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
