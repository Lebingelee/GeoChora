"""One finite real episode for the versioned built-in PickCube Harness mode."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import traceback

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


def _prepare_output_directory(output: Path):
    output = output.resolve()
    if output.exists():
        unexpected = {path.name for path in output.iterdir()} - {
            'worker.stdout.log', 'worker.stderr.log',
        }
        if unexpected:
            raise FileExistsError(f'worker output directory already contains data: {sorted(unexpected)}')
    else:
        output.mkdir(parents=True, exist_ok=False)
    return output


def _install_action_trace(env, path: Path):
    """Capture the public expert proposal and state around each step attempt."""
    capture = {'attempted': 0, 'completed': 0, 'rows': []}
    original_step = env._step

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
        row = {
            'attempt': capture['attempted'],
            'control_step_before': int(state.control_step),
            'simulation_time_before_s': float(state.simulation_time),
            'proposal_stage': getattr(proposal, 'stage', None),
            'planned_tcp_pose': list(map(float, action[:7])) if len(action) >= 7 else list(map(float, action)),
            'gripper_request': float(action[7]) if len(action) >= 8 else None,
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
    }
    env = None
    action_trace = None
    write_action_trace = None
    recording_started = False
    h5 = output / 'episode.h5'
    try:
        context = core_context(catalog['core_repo'])
        # The built-in profile has its own tracked-clean + exact untracked
        # scope; the legacy strict catalog validator correctly remains strict.
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
                   runtime_source_id=compiled.runtime_source_id,
                   runtime_source_sha256=compiled.runtime_source_sha256,
                   working_tree_scope=compiled.working_tree_scope,
                   repo_dirty=compiled.repo_dirty,
                   core_commit=context['core_commit'])
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
        trajectory_live = getattr(env.recorder, 'value', None)
        transitions_live = getattr(trajectory_live, 'transitions', ()) if trajectory_live is not None else ()
        row['planning_action_count'] = sum(
            bool(getattr(transition, 'planned_action', False)) for transition in transitions_live
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
            'phase': 'execute', 'type': type(error).__name__, 'message': str(error),
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
    if h5.is_file():
        try:
            trajectory = load_canonical(h5)
            shapes = _numeric_check(trajectory)
            transition_count = len(trajectory.transitions)
            observation_count = len(trajectory.boundaries)
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
                # Canonical requested actions alone can be caller supplied;
                # planned_action is the Core proposal provenance gate.
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
            row['planning_action_count'] = sum(transition.planned_action for transition in trajectory.transitions)
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
    return 0 if row['runtime_valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
