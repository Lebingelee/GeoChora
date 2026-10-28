"""Bounded R03c MuJoCo native runner for the attached two-Entity leaf public Env."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import time
import traceback

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r03b_001/r03c_001_input_snapshot.json'


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def _append_jsonl(path: Path, value):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rss_bytes() -> int:
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('Linux VmRSS is not present in /proc/self/status')


def _native_identity(mujoco, expected_static):
    import mujoco._functions as functions

    package = Path(mujoco.__file__).resolve()
    binding = Path(functions.__file__).resolve()
    header = package.parent / 'include/mujoco/mujoco.h'
    mapped = set()
    with Path('/proc/self/maps').open(encoding='utf-8') as stream:
        for line in stream:
            if 'libmujoco.so.3.8.1' not in line:
                continue
            raw = line.rstrip().split()[-1]
            if raw.startswith('/'):
                mapped.add(str(Path(raw.removesuffix(' (deleted)')).resolve()))
    if len(mapped) != 1:
        raise ValueError(f'expected one mapped MuJoCo CPU library, found {sorted(mapped)}')
    library = Path(next(iter(mapped)))
    identity = {
        'package_version': mujoco.__version__,
        'runtime_version': mujoco.mj_versionString(),
        'api_version': int(mujoco.mj_version()),
        'package_path': str(package), 'package_sha256': _sha(package),
        'binding_path': str(binding), 'binding_sha256': _sha(binding),
        'mapped_native_libraries': [{'path': str(library), 'sha256': _sha(library)}],
        'public_header_path': str(header.resolve()), 'public_header_sha256': _sha(header),
        'renderer_initialized': False,
    }
    expected_hashes = expected_static['files_sha256']
    expected_paths = {
        'package_path': '/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/__init__.py',
        'binding_path': '/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/_functions.cpython-312-x86_64-linux-gnu.so',
        'library_path': '/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/libmujoco.so.3.8.1',
        'header_path': '/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/include/mujoco/mujoco.h',
    }
    pairs = (
        ('package_path', 'package_sha256', '__init__.py'),
        ('binding_path', 'binding_sha256', '_functions.cpython-312-x86_64-linux-gnu.so'),
    )
    for path_key, hash_key, filename in pairs:
        if (identity[path_key], identity[hash_key]) != (
                expected_paths[path_key], expected_hashes[expected_paths[path_key]]):
            raise ValueError(f'loaded MuJoCo {filename} identity differs from the protected input snapshot')
    actual_library = identity['mapped_native_libraries'][0]
    for filename, path_value, hash_value, expected_path in (
        ('libmujoco.so.3.8.1', actual_library['path'], actual_library['sha256'],
         '/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/libmujoco.so.3.8.1'),
        ('mujoco.h', identity['public_header_path'], identity['public_header_sha256'],
         '/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/include/mujoco/mujoco.h'),
    ):
        if (path_value, hash_value) != (expected_path, expected_hashes[expected_path]):
            raise ValueError(f'loaded MuJoCo {filename} identity differs from the protected input snapshot')
    if (identity['package_version'], identity['runtime_version'], identity['api_version']) != (
            '3.8.1', '3.8.1', 3008001):
        raise ValueError('loaded MuJoCo package/runtime/API identity differs from 3.8.1/3008001')
    return identity


def _qmul(left, right):
    w, x, y, z = left
    a, b, c, d = right
    return np.asarray((w*a-x*b-y*c-z*d, w*b+x*a+y*d-z*c,
                       w*c-x*d+y*a+z*b, w*d+x*c-y*b+z*a), dtype=np.float64)


def _qrotate(quaternion, vector):
    q = np.asarray(quaternion, dtype=np.float64)
    v = np.asarray((0.0, *vector), dtype=np.float64)
    return _qmul(_qmul(q, v), (q[0], -q[1], -q[2], -q[3]))[1:]


def _mount_error(publication, attachment_plan):
    frames = {(item.frame.entity_id, item.frame.frame_id): item.pose_world
              for item in publication.view.frames}
    parent = frames[('panda-arm', 'attachment_site')]
    child = frames[('panda-hand', 'hand')]
    rel = attachment_plan.parent_site_from_child_root
    expected_pos = np.asarray(parent.position) + _qrotate(parent.quaternion_wxyz, rel.position)
    actual_pos = np.asarray(child.position)
    expected_rot = _qmul(parent.quaternion_wxyz, rel.quaternion_wxyz)
    actual_rot = np.asarray(child.quaternion_wxyz, dtype=np.float64)
    expected_rot /= np.linalg.norm(expected_rot)
    actual_rot /= np.linalg.norm(actual_rot)
    pos_error = float(np.linalg.norm(actual_pos - expected_pos))
    dot = float(np.clip(abs(np.dot(expected_rot, actual_rot)), 0.0, 1.0))
    rot_error = float(2.0 * np.arccos(dot))
    return pos_error, rot_error


def _rotation_error(left, right):
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    left /= np.linalg.norm(left)
    right /= np.linalg.norm(right)
    return float(2.0 * np.arccos(np.clip(abs(np.dot(left, right)), 0.0, 1.0)))


def _mount_requirements(candidate):
    from task_env.artifacts.state import StateFieldRequirement, StateRequirements

    base_requirements = tuple(
        requirement
        for entry in candidate.plan.leaves
        for requirement in entry.binding.required_state.state_requirements.requirements
    )
    existing = {(item.field_key, item.sample_domain) for item in base_requirements}
    desired = tuple(StateFieldRequirement(
        'state-field-requirement-v1', 'frame_pose_world', 'frame', entity, frame,
        'required', 'evaluation_boundary', 'meter+quaternion_wxyz', 'frame_pose_query',
    ) for entity, frame in (('panda-arm', 'attachment_site'), ('panda-hand', 'hand')))
    additional = tuple(
        item for item in desired
        if (item.field_key, item.sample_domain) not in existing
    )
    return StateRequirements(
        'state-requirements-v1', 'controller', 'r03c-fixed-mount-audit-v1',
        base_requirements + additional,
    )


def _candidate_bindings(candidate):
    joint_bindings = {
        f'{ref.entity_id}/{ref.joint_id}': ref
        for entry in candidate.plan.leaves
        for ref in entry.binding.joint_order
    }
    frame_bindings = {
        name: __import__('task_env.artifacts', fromlist=['FrameReference']).FrameReference(
            *name.split('/', 1)
        )
        for name in (*candidate.source.bodies, *candidate.source.frames)
    }
    return joint_bindings, frame_bindings


def _check_reset(candidate, env, publication, baseline_warnings):
    from task_env.tasks.position_candidate.attached_leaf_candidate import ARM_HOME

    sample = candidate.reset_plan.reset_sample
    for key, expected in sample.joint_position.items():
        if abs(float(env.state.joint_position[key]) - float(expected)) > 1e-12:
            raise ValueError(f'reset Joint differs from the named ResetSample: {key}')
        if abs(float(env.state.joint_velocity[key])) > 1e-12:
            raise ValueError(f'reset Joint velocity is nonzero: {key}')
    diagnostics = env.session.fixed_attachment_diagnostics
    if (env.state.control_step != 0 or abs(float(env.state.simulation_time)) > 1e-12
            or abs(float(diagnostics['native_time_s'])) > 1e-12):
        raise ValueError('reset public/native clock is not at zero')
    if not np.isfinite(np.asarray(diagnostics['ctrl'], dtype=np.float64)).all():
        raise ValueError('reset native ctrl contains a non-finite value')
    mapping = candidate.attachment_plan.native_actuator_names
    receipt = env.session.fixed_attachment_receipt
    expected_ctrl = {}
    for index, value in enumerate(ARM_HOME, 1):
        slot = receipt['native_actuator_mappings'][f'panda-arm/actuator{index}']['ctrl_slot']
        expected_ctrl[slot] = value
    slot = receipt['native_actuator_mappings']['panda-hand/actuator8']['ctrl_slot']
    expected_ctrl[slot] = 242.25
    for slot, expected in expected_ctrl.items():
        if abs(float(diagnostics['ctrl'][slot]) - float(expected)) > 1e-12:
            raise ValueError(f'reset ctrl slot {slot} differs from the frozen Home/Hand242.25 vector')
    pos_error, rot_error = _mount_error(publication, candidate.attachment_plan)
    if pos_error > 1e-8 or rot_error > 2e-7:
        raise ValueError('reset measured fixed mount exceeds the position/orientation oracle')
    warnings = tuple(int(value) for value in diagnostics['warning_counts'])
    if warnings != tuple(baseline_warnings):
        raise ValueError('MuJoCo warning count changed during reset')
    return {
        'reset_sample_id': sample.sample_id,
        'joint_position_max_abs_error_rad_or_m': max(
            abs(float(env.state.joint_position[key]) - float(value))
            for key, value in sample.joint_position.items()
        ),
        'joint_velocity_max_abs': max(abs(float(value)) for value in env.state.joint_velocity.values()),
        'ctrl': [float(value) for value in diagnostics['ctrl']],
        'mount_position_error_m': pos_error, 'mount_rotation_error_rad': rot_error,
        'warning_counts': list(warnings),
    }


def _check_outer(candidate, env, publication, expected_step, baseline_warnings):
    diagnostics = env.session.fixed_attachment_diagnostics
    clock = publication.view.sample_clock
    if (env.state.control_step != expected_step or clock.sample_index != expected_step
            or abs(float(env.state.simulation_time) - expected_step * 0.01) > 1e-12
            or abs(float(clock.simulation_time_s) - expected_step * 0.01) > 1e-12
            or abs(float(diagnostics['native_time_s']) - expected_step * 0.01) > 1e-12
            or diagnostics['native_step_count'] != expected_step * 5
            or diagnostics['forward_call_count'] != expected_step + 1):
        raise ValueError('outer public/native time or exact five-step Runtime counter mismatch')
    warnings = tuple(int(value) for value in diagnostics['warning_counts'])
    if warnings != tuple(baseline_warnings):
        raise ValueError('MuJoCo warning count changed during the episode')
    if not np.isfinite(np.asarray(diagnostics['ctrl'], dtype=np.float64)).all():
        raise ValueError('outer native ctrl contains a non-finite value')
    positions = {}
    for joint in publication.view.joints:
        value = float(joint.position[0])
        if not math.isfinite(value):
            raise ValueError('outer Joint state is non-finite')
        positions[(joint.entity_id, joint.joint_id)] = value
    for entry in candidate.plan.leaves:
        for ref, (low, high) in zip(entry.binding.joint_order,
                                     entry.binding.joint_position_limits, strict=True):
            value = positions[(ref.entity_id, ref.joint_id)]
            if value < low - 1e-6 or value > high + 1e-6:
                raise ValueError(f'outer Joint crossed its source range: {ref.entity_id}/{ref.joint_id}')
    if not np.isfinite(np.asarray([
            number for item in publication.view.frames
            for number in (*item.pose_world.position, *item.pose_world.quaternion_wxyz)
    ], dtype=np.float64)).all():
        raise ValueError('outer typed frame state contains non-finite values')
    pos_error, rot_error = _mount_error(publication, candidate.attachment_plan)
    if pos_error > 1e-8 or rot_error > 2e-7:
        raise ValueError('outer measured fixed mount exceeds the position/orientation oracle')
    return pos_error, rot_error


def _tamper_checks(source_h5: Path, output_dir: Path):
    import h5py
    from task_env.recorders.h5 import _read_text, load_leaf_control_records_h5
    from task_env.trajectory.metadata import dump_metadata, load_metadata

    cases = {
        'target_identity': lambda rows: rows[0]['writer_controls'][0]['controller_target'].__setitem__('identity_hash', '0' * 64),
        'ack_writer': lambda rows: rows[0]['writer_controls'][0]['canonical_action']['application_ack'].__setitem__('writer_id', 'tampered-writer'),
        'prepared_command': lambda rows: rows[0]['writer_controls'][0]['canonical_action']['prepared_command']['slot_values'][0].__setitem__('value', 999.0),
        'source_digest': lambda rows: rows[0]['writer_controls'][0]['canonical_action'].__setitem__('source_closure_sha256', '0' * 64),
        'configuration_identity': lambda rows: rows[0]['writer_controls'][0]['canonical_action'].__setitem__('configuration_identity_sha256', '0' * 64),
        'missing_writer': lambda rows: rows[0]['writer_controls'].pop(),
        'duplicate_slot': lambda rows: rows[0]['writer_controls'][1]['applied_control']['payload'].__setitem__(
            'applied_slots', [rows[0]['writer_controls'][0]['canonical_action']['prepared_command']['slot_values'][0]['ctrl_slot']]
        ),
    }
    results = []
    with tempfile.TemporaryDirectory(prefix='r03c-h5-tamper-', dir=output_dir) as temporary:
        temp = Path(temporary)
        for label, mutation in cases.items():
            destination = temp / f'{label}.h5'
            shutil.copy2(source_h5, destination)
            with h5py.File(destination, 'r+') as root:
                rows = json.loads(_read_text(root, 'meta/structured_controls_v1_json'))
                mutation(rows)
                del root['meta/structured_controls_v1_json']
                root.create_dataset('meta/structured_controls_v1_json',
                                    data=json.dumps(rows, sort_keys=True),
                                    dtype=h5py.string_dtype(encoding='utf-8'))
            try:
                load_leaf_control_records_h5(destination)
            except Exception as error:
                results.append({'case': label, 'rejected': True,
                                'error_type': type(error).__name__, 'error': str(error)})
            else:
                raise AssertionError(f'R03c reader accepted tampered {label}')
        for label, mutate_dataset in (
            ('boundary_observation', lambda root: root['obs/state/boundary_identity_sha256'].__setitem__(
                (1, 0), (int(root['obs/state/boundary_identity_sha256'][1, 0]) + 1) % 256)),
            ('t_plus_one', lambda root: root.attrs.__setitem__('observation_count', 64)),
        ):
            destination = temp / f'{label}.h5'
            shutil.copy2(source_h5, destination)
            with h5py.File(destination, 'r+') as root:
                mutate_dataset(root)
            try:
                load_leaf_control_records_h5(destination)
            except Exception as error:
                results.append({'case': label, 'rejected': True,
                                'error_type': type(error).__name__, 'error': str(error)})
            else:
                raise AssertionError(f'R03c reader accepted tampered {label}')
        metadata_cases = {
            'attachment_plan_hash': lambda profile: profile.__setitem__('attachment_plan_identity_sha256', '0' * 64),
            'entity_binding': lambda profile: profile['writers'][0].__setitem__('entity_id', 'panda-secondary'),
            'native_tcp': lambda profile: profile['attachment_receipt']['native_body_mappings'][
                'panda-hand/hand'
            ].__setitem__('native_name', 'hand'),
        }
        for label, mutation in metadata_cases.items():
            destination = temp / f'{label}.h5'
            shutil.copy2(source_h5, destination)
            with h5py.File(destination, 'r+') as root:
                metadata = load_metadata(_read_text(root, 'meta/env_meta'))
                mutation(metadata['reference_profile'])
                del root['meta/env_meta']
                root.create_dataset('meta/env_meta', data=dump_metadata(metadata),
                                    dtype=h5py.string_dtype(encoding='utf-8'))
            try:
                load_leaf_control_records_h5(destination)
            except Exception as error:
                results.append({'case': label, 'rejected': True,
                                'error_type': type(error).__name__, 'error': str(error)})
            else:
                raise AssertionError(f'R03c reader accepted tampered {label}')
    if len(results) != 12 or not all(item['rejected'] for item in results):
        raise AssertionError('R03c H5 tamper matrix did not reject all 12 copy-only mutations')
    return results


def _retry_counters(prior_native_dir: Path, output_dir: Path):
    """Reconstruct cumulative counters from the sole pre-step retryable failure."""
    failure_path = prior_native_dir / 'native_failure.json'
    progress_path = prior_native_dir / 'native_progress.json'
    ledger_path = prior_native_dir / 'native_process_ledger.jsonl'
    failure = json.loads(failure_path.read_text())
    progress = json.loads(progress_path.read_text())
    ledger_lines = [line for line in ledger_path.read_bytes().splitlines(keepends=True) if line.strip()]
    ledger = [json.loads(line) for line in ledger_lines]
    retry_invocation_path = prior_native_dir.parent / 'native_attempt_002' / 'native_invocation.json'
    retry_invocation = json.loads(retry_invocation_path.read_text())
    traceback_text = failure.get('traceback', '')
    if (len(ledger) != 2 or ledger[0].get('attempt') != 1
            or ledger[1] != retry_invocation or retry_invocation.get('attempt') != 2
            or retry_invocation.get('event') != 'START_RECORDED_BEFORE_NATIVE_PROCESS_LAUNCH'
            or retry_invocation.get('budget_before_start', {}).get('native_starts') != 1
            or retry_invocation.get('budget_after_reserving_start', {}).get('native_starts') != 2
            or failure.get('status') != 'NATIVE_FAILURE'
            or failure.get('exception_type') != 'ValueError'
            or failure.get('message') != 'Attachment receipt omits the canonical Hand actuator/tendon mapping'
            or failure.get('active', {}).get('phase') != 'public_env_reset'
            or 'control.py' not in traceback_text or 'materialize_control' not in traceback_text
            or 'admit_leaf_control_plan' not in traceback_text
            or failure.get('counters', {}).get('mj_step_calls') != 0
            or failure.get('counters', {}).get('mj_forward_calls') != 0
            or failure.get('counters', {}).get('materialization_attempts') != 0
            or failure.get('counters', {}).get('resets') != 1
            or progress.get('counters', {}).get('native_starts') != 1
            or progress.get('counters', {}).get('mj_step_calls') != 0
            or progress.get('counters', {}).get('mj_forward_calls') != 0):
        raise ValueError('prior native process is not the package-authorized retryable pre-step Core admission failure')
    # The wrapper missed this call because ReferenceEnv retained an imported
    # alias before the wrapper was installed. The preserved traceback proves
    # one materialization call entered the public control owner.
    reconstructed = {
        'attempt': 1, 'materialization_attempts': 1, 'resets': 1,
        'mj_forward_calls': 0, 'mj_step_calls': 0,
        'native_failure_sha256': _sha(failure_path),
        'native_progress_sha256': _sha(progress_path),
        # The append-only ledger now includes this retry's pre-launch row.
        # Bind the first-start prefix byte-for-byte to the frozen provenance.
        'native_process_ledger_sha256': hashlib.sha256(ledger_lines[0]).hexdigest(),
        'native_process_ledger_after_retry_sha256': _sha(ledger_path),
        'basis': 'preserved traceback enters ReferenceEnv.materialize_control and RuntimeSession.admit_leaf_control_plan; failed before mj_forward/mj_step',
    }
    return {
        'native_starts': 2, 'materialization_attempts': 1, 'resets': 1,
        'mj_forward_calls': 0, 'mj_step_calls': 0, 'outer_intervals': 0,
        'simulated_seconds': 0.0, 'max_rss_bytes': 0, 'rss_samples': [],
        'reconstructed_prior_attempt': reconstructed,
    }


def run_native(output_dir: Path, snapshot_path: Path = SNAPSHOT,
               native_attempt_dir: str = 'native', prior_native_dir: str | None = None):
    output_dir.mkdir(parents=True, exist_ok=True)
    native_dir = output_dir / native_attempt_dir
    if native_dir.resolve().parent != output_dir.resolve():
        raise ValueError('native attempt directory must be a direct child of the package output directory')
    if prior_native_dir is not None and (native_attempt_dir != 'native_attempt_002'
                                         or prior_native_dir != 'native'):
        raise ValueError('the authorized retry must be native_attempt_002 against preserved attempt native/')
    native_dir.mkdir(exist_ok=True)
    for name in ('native_progress.json', 'native_failure.json', 'native_result.json'):
        if (native_dir / name).exists():
            raise FileExistsError(native_dir / name)
    snapshot = json.loads(snapshot_path.read_text())
    frozen = json.loads((output_dir / 'freeze' / 'execution_freeze.json').read_text())
    for relative, expected in frozen['code_sha256'].items():
        actual = _sha(ROOT / relative)
        if actual != expected:
            raise ValueError(f'R03c source changed after the execution freeze: {relative}')
    contract = json.loads((output_dir / 'freeze' / 'executed_contract.json').read_text())
    if contract['input_head'] != snapshot['core_head']:
        raise ValueError('frozen execution contract is not bound to the protected input HEAD')
    counters = (_retry_counters(output_dir / prior_native_dir, output_dir)
                if prior_native_dir is not None else {
                    'native_starts': 1, 'materialization_attempts': 0, 'resets': 0,
                    'mj_forward_calls': 0, 'mj_step_calls': 0, 'outer_intervals': 0,
                    'simulated_seconds': 0.0, 'max_rss_bytes': 0, 'rss_samples': [],
                })
    if prior_native_dir is not None:
        frozen_retry = contract.get('retry_provenance', {})
        reconstructed = counters['reconstructed_prior_attempt']
        if (contract.get('required_native_totals', {}).get('native_starts') != 2
                or frozen_retry.get('prior_native_failure_sha256') != reconstructed['native_failure_sha256']
                or frozen_retry.get('prior_native_progress_sha256') != reconstructed['native_progress_sha256']
                or frozen_retry.get('prior_native_process_ledger_sha256') != reconstructed['native_process_ledger_sha256']):
            raise ValueError('retry execution contract does not bind the preserved first-process evidence')
    active = {'episode_id': None, 'outer': 0, 'phase': 'native_import'}
    native_started_at = time.monotonic()
    _write_json(native_dir / 'native_progress.json', {
        'status': 'NATIVE_PROCESS_STARTED', 'input_head': snapshot['core_head'],
        'counters': counters, 'active': active,
    })
    envs = []
    try:
        import mujoco
        identity = _native_identity(mujoco, snapshot['mujoco_installation_static'])
        _write_json(native_dir / 'runtime_identity.json', identity)
        original_step, original_forward = mujoco.mj_step, mujoco.mj_forward
        trace_path = native_dir / 'native_step_trace.jsonl'

        def counted_step(model, data, *args, **kwargs):
            nstep = int(kwargs.get('nstep', 1))
            if counters['mj_step_calls'] + nstep > 1280:
                raise RuntimeError('native mj_step budget of 1280 would be exceeded')
            attempted = nstep
            try:
                value = original_step(model, data, *args, **kwargs)
            except BaseException:
                _append_jsonl(trace_path, {
                    'event': 'mj_step_raise', 'attempted_nstep': attempted,
                    'successful_before': counters['mj_step_calls'],
                    'episode_id': active['episode_id'], 'outer': active['outer'],
                })
                raise
            counters['mj_step_calls'] += nstep
            if counters['mj_step_calls'] > 1280:
                raise RuntimeError('native mj_step budget exceeded after provider call')
            _append_jsonl(trace_path, {
                'event': 'mj_step', 'nstep': nstep,
                'successful_cumulative': counters['mj_step_calls'],
                'episode_id': active['episode_id'], 'outer': active['outer'],
            })
            return value

        def counted_forward(*args, **kwargs):
            if counters['mj_forward_calls'] + 1 > 300:
                raise RuntimeError('native mj_forward budget of 300 would be exceeded')
            value = original_forward(*args, **kwargs)
            counters['mj_forward_calls'] += 1
            return value

        mujoco.mj_step = counted_step
        mujoco.mj_forward = counted_forward

        from task_env.tasks.position_candidate.attached_leaf_candidate import (
            ARM_WRITER_ID, HAND_WRITER_ID, action_for_interval,
            build_attached_leaf_candidate,
        )
        from task_env.tasks.reference_env import SelectedReferenceEnv
        from task_env.tasks import reference_env as reference_env_module
        from task_env.runtime.sessions.leaf_control import (
            LeafActionRequestV1, LeafControlIntervalRequestV1, dispatch_leaf_control_interval,
            prepare_leaf_command,
        )
        from task_env.runtime.sessions import control as control_module
        from task_env.artifacts import StateRequirements

        original_materialize_control = control_module.materialize_control

        def counted_materialize_control(*args, **kwargs):
            counters['materialization_attempts'] += 1
            if counters['materialization_attempts'] > 5:
                raise RuntimeError('RuntimeSession materialization attempt budget of 5 exceeded')
            active['phase'] = 'runtime_materialization'
            _write_progress(native_dir, snapshot, counters, active)
            return original_materialize_control(*args, **kwargs)

        control_module.materialize_control = counted_materialize_control
        reference_env_module.materialize_control = counted_materialize_control
        shutil.copy2(output_dir / 'freeze' / 'executed_contract.json',
                     native_dir / 'executed_contract.json')
        inventory = None
        results = []
        gain_comparison = {}
        for episode_spec in contract['episodes']:
            active.update({'episode_id': episode_spec['episode_id'], 'outer': 0, 'phase': 'candidate_build'})
            _write_progress(native_dir, snapshot, counters, active)
            candidate = build_attached_leaf_candidate(
                environment_type=SelectedReferenceEnv,
                arm_gain=episode_spec['arm_gain'], hand_stiffness_N_per_m=50.0,
                provider='mujoco', horizon=64, episode_id=episode_spec['episode_id'],
                arm_active=episode_spec['arm_active'], hand_active=episode_spec['hand_active'],
            )
            env = candidate.env
            envs.append(env)
            inventory = candidate.source_inventory
            frozen_episode = next(
                item for item in contract['episodes']
                if item['episode_id'] == episode_spec['episode_id']
            )
            live_episode = {
                'task_source_identity_sha256': candidate.artifact.task_source_identity_hash,
                'task_artifact_identity_sha256': candidate.artifact.identity_hash,
                'scene_identity_sha256': candidate.scene.identity_hash,
                'assembly_identity_sha256': candidate.assembly.logical_content_sha256,
                'attachment_plan_identity_sha256': candidate.attachment_plan.identity_hash,
                'source_closure_sha256': candidate.source.source_closure_digest,
                'reset_plan_identity_sha256': candidate.reset_plan.identity_hash,
                'reset_sample_id': candidate.reset_plan.reset_sample.sample_id,
                'effective_leaf_plan_identity_sha256': candidate.plan.identity_sha256,
                'leaf_configurations': [
                    {
                        'writer_id': item.binding.writer_id,
                        'entity_id': item.binding.entity_id,
                        'profile_kind': item.binding.profile_kind,
                        'binding_identity_sha256': item.binding.identity_hash,
                        'configuration_identity_sha256': item.effective_configuration_identity_sha256,
                    }
                    for item in candidate.plan.leaves
                ],
            }
            if live_episode != {key: frozen_episode[key] for key in live_episode}:
                raise ValueError('live R03c candidate identities differ from the provider-free execution freeze')
            if inventory != json.loads((output_dir / 'freeze' / 'source_inventory.json').read_text()):
                raise ValueError('live R03c source inventory differs from the provider-free execution freeze')
            if inventory['derived_source_closure_bytes'] > 128 * 1024 * 1024:
                raise ValueError('fixed source closure exceeds 128 MiB')
            if (candidate.scene.identity_hash != '7981f0bb31875b35eb0973b08c1f65ac09210b55b7e9e0ea45761e4f8a4cfe9a'
                    or candidate.assembly.logical_content_sha256 != '232e62b18ea48ab04cc4ec2761a11666c8e1955a599b4f04ff585887d2fe1b4a'
                    or candidate.attachment_plan.identity_hash != 'b4b2099d7b0009aed023c74f15b142194ba47e23823fff639f505736fb92c2a3'):
                raise ValueError('R03c candidate changed a protected fixed Scene/Assembly/Attachment identity')

            active['phase'] = 'public_env_reset'
            _write_progress(native_dir, snapshot, counters, active)
            counters['resets'] += 1
            if counters['resets'] > 5:
                raise RuntimeError('ResetPlan realization budget of 5 exceeded')
            reset_result = env.reset(seed=31)
            reset_info = reset_result[1]
            if (reset_result[1].get('state_boundary_id') != env.typed_state.view.boundary.boundary_id
                    or reset_info['reset_sample_id'] != candidate.reset_plan.reset_sample.sample_id
                    or reset_info['seed'] != 31):
                raise ValueError('public Env reset did not realize the exact seed-31 ResetPlan')
            warnings = tuple(int(value) for value in env.session.fixed_attachment_diagnostics['warning_counts'])
            mount_requirements = _mount_requirements(candidate)
            joint_bindings, frame_bindings = _candidate_bindings(candidate)
            initial_mount_pub = env.session.snapshot_v1(
                scene=candidate.scene, joint_bindings=joint_bindings,
                frame_bindings=frame_bindings, requirements=mount_requirements,
            )
            reset_metrics = _check_reset(candidate, env, initial_mount_pub, warnings)
            initial_hand_root = next(
                item.pose_world.quaternion_wxyz for item in initial_mount_pub.view.frames
                if item.frame.entity_id == 'panda-hand' and item.frame.frame_id == 'hand'
            )
            if counters['mj_step_calls'] > 1280 or counters['mj_forward_calls'] > 300:
                raise RuntimeError('native budget exceeded during materialization/reset')

            receipt = env.session.leaf_materialization_receipt
            if (receipt.fixed_attachment_receipt_identity_sha256
                    != env.session.fixed_attachment_receipt['receipt_identity_sha256']
                    or receipt.materialization_id != env.session.fixed_attachment_receipt['provider_materialization_id']):
                raise ValueError('leaf and fixed Attachment receipts do not share this Env Runtime')
            if env.session.fixed_attachment_receipt['runtime_identity'] != identity:
                raise ValueError('provider adapter runtime identity differs from pre-compile native identity')

            if episode_spec['episode_id'] in {'E3', 'E4'}:
                probe_action = action_for_interval(candidate, 1, arm_active=True, hand_active=True)
                arm_action = probe_action.arm
                hand_action = probe_action.hand
                arm_command = prepare_leaf_command(
                    candidate.plan, ARM_WRITER_ID, arm_action, env.typed_state,
                    receipt, env.session.leaf_configuration_revision, scene=candidate.scene,
                )
                hand_command = prepare_leaf_command(
                    candidate.plan, HAND_WRITER_ID, hand_action, env.typed_state,
                    receipt, env.session.leaf_configuration_revision, scene=candidate.scene,
                )
                gain_comparison[episode_spec['episode_id']] = {
                    'arm_config': next(item.effective_configuration_identity_sha256
                                       for item in candidate.plan.leaves
                                       if item.binding.profile_kind == 'arm_position'),
                    'arm_slot_values': [item.value for item in arm_command.slot_values],
                    'hand_config': next(item.effective_configuration_identity_sha256
                                        for item in candidate.plan.leaves
                                        if item.binding.profile_kind == 'hand_position'),
                    'hand_request_m': hand_command.requested_opening_m,
                    'hand_servo_m': hand_command.servo_opening_m,
                    'hand_ctrl': hand_command.native_ctrl,
                }
                if 'E3' in gain_comparison and 'E4' in gain_comparison:
                    e3, e4 = gain_comparison['E3'], gain_comparison['E4']
                    if (e3['arm_config'] == e4['arm_config']
                            or e3['arm_slot_values'] == e4['arm_slot_values']
                            or e3['hand_config'] != e4['hand_config']
                            or e3['hand_request_m'] != e4['hand_request_m']
                            or e3['hand_servo_m'] != e4['hand_servo_m']
                            or e3['hand_ctrl'] != e4['hand_ctrl']):
                        raise ValueError('E3/E4 affine Arm calibration isolation or Hand command invariance failed')

            h5_path = native_dir / f"{episode_spec['episode_id']}.h5"
            env.start_recording(h5_path)
            maximum_mount_position, maximum_mount_rotation = reset_metrics['mount_position_error_m'], reset_metrics['mount_rotation_error_rad']
            maximum_hand_root_rotation = 0.0
            peak_arm = abs(float(env.state.joint_position['panda-arm/joint1']))
            openings, finger_mismatches = [], []
            for interval_index in range(1, 65):
                active.update({'phase': 'typed_leaf_dispatch', 'outer': interval_index})
                action = action_for_interval(
                    candidate, interval_index, arm_active=episode_spec['arm_active'],
                    hand_active=episode_spec['hand_active'],
                )
                try:
                    _, _, terminated, truncated, info = env.step(action)
                except BaseException:
                    active['phase'] = 'typed_leaf_dispatch_failed'
                    _write_progress(native_dir, snapshot, counters, active)
                    raise
                counters['outer_intervals'] += 1
                counters['simulated_seconds'] = counters['outer_intervals'] * 0.01
                if terminated or truncated != (interval_index == 64):
                    raise ValueError('public Env termination/truncation differs from the fixed 64 outer horizon')
                mount_pub = env.session.snapshot_v1(
                    scene=candidate.scene, joint_bindings=joint_bindings,
                    frame_bindings=frame_bindings, requirements=mount_requirements,
                )
                pos_error, rot_error = _check_outer(
                    candidate, env, mount_pub, interval_index, warnings,
                )
                maximum_mount_position = max(maximum_mount_position, pos_error)
                maximum_mount_rotation = max(maximum_mount_rotation, rot_error)
                hand_root = next(
                    item.pose_world.quaternion_wxyz for item in mount_pub.view.frames
                    if item.frame.entity_id == 'panda-hand' and item.frame.frame_id == 'hand'
                )
                maximum_hand_root_rotation = max(
                    maximum_hand_root_rotation,
                    _rotation_error(initial_hand_root, hand_root),
                )
                measured = {(item.entity_id, item.joint_id): float(item.position[0])
                            for item in env.typed_state.view.joints}
                arm_q = measured[('panda-arm', 'joint1')]
                opening = measured[('panda-hand', 'finger_joint1')] + measured[('panda-hand', 'finger_joint2')]
                mismatch = abs(measured[('panda-hand', 'finger_joint1')]
                               - measured[('panda-hand', 'finger_joint2')])
                peak_arm = max(peak_arm, abs(arm_q))
                openings.append(opening)
                finger_mismatches.append(mismatch)
                rss = _rss_bytes()
                counters['max_rss_bytes'] = max(counters['max_rss_bytes'], rss)
                counters['rss_samples'].append({
                    'episode_id': episode_spec['episode_id'], 'outer': interval_index,
                    'rss_bytes': rss, 'sampled_at_monotonic_s': time.monotonic(),
                })
                if rss > 4 * 1024 * 1024 * 1024:
                    raise MemoryError('sampled RSS exceeds the 4 GiB observation gate')
                _write_progress(native_dir, snapshot, counters, active)
                if terminated or truncated != (interval_index == 64):
                    raise ValueError('episode outcome changed before the frozen horizon')
            final_joint_positions = {
                (item.entity_id, item.joint_id): float(item.position[0])
                for item in env.typed_state.view.joints
            }
            final_arm = np.asarray([
                final_joint_positions[('panda-arm', f'joint{index}')]
                for index in range(1, 8)
            ], dtype=np.float64)
            home = np.asarray((0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853), dtype=np.float64)
            arm_error = float(np.max(np.abs(final_arm - home)))
            hand_opening = float(openings[-1])
            hand_minimum = float(min(openings[16:32]))
            hand_excursion = float(max(openings) - min(openings))
            arm_excursion = peak_arm
            if arm_error > 0.02:
                raise ValueError(f"{episode_spec['episode_id']} Arm return-home error exceeds 0.02 rad")
            if episode_spec['arm_active'] and arm_excursion < 0.08:
                raise ValueError(f"{episode_spec['episode_id']} Arm joint1 measured peak is below 0.08 rad")
            if episode_spec['arm_active'] and maximum_hand_root_rotation < 0.05:
                raise ValueError(f"{episode_spec['episode_id']} Hand root rotation is below 0.05 rad")
            if episode_spec['hand_active'] and (
                    hand_minimum > 0.02 or hand_opening < 0.06 or hand_excursion < 0.04
                    or max(finger_mismatches) > 1e-4):
                raise ValueError(f"{episode_spec['episode_id']} Hand measured opening/equality gates failed")
            active['phase'] = 'close_recording_and_readback'
            _write_progress(native_dir, snapshot, counters, active)
            result = env.finish_recording('horizon')
            if (result['transition_count'], result['observation_count']) != (64, 65):
                raise ValueError('SelectedReferenceEnv closed Generic H5 without exact T/T+1 counts')
            episode_result = {
                'episode_id': episode_spec['episode_id'], 'path': result['path'],
                'sha256': _sha(Path(result['path'])), 'bytes': Path(result['path']).stat().st_size,
                'transition_count': result['transition_count'], 'observation_count': result['observation_count'],
                'env_close_reader': 'PASS',
                'reset': reset_metrics, 'outer_intervals': 64,
                'arm_peak_abs_joint1_rad': peak_arm, 'arm_return_home_max_abs_rad': arm_error,
                'hand_closed_min_opening_m': hand_minimum, 'hand_final_opening_m': hand_opening,
                'hand_total_excursion_m': hand_excursion,
                'hand_finger_mismatch_max_m': max(finger_mismatches),
                'hand_root_rotation_max_rad': maximum_hand_root_rotation,
                'mount_position_error_max_m': maximum_mount_position,
                'mount_rotation_error_max_rad': maximum_mount_rotation,
                'warning_counts': list(env.session.fixed_attachment_diagnostics['warning_counts']),
                'native_steps': env.session.fixed_attachment_diagnostics['native_step_count'],
                'native_forwards': env.session.fixed_attachment_diagnostics['forward_call_count'],
                'outcome': result['outcome'],
            }
            results.append(episode_result)
            _write_json(native_dir / f"{episode_spec['episode_id']}_result.json", episode_result)
            env.close()
            _write_progress(native_dir, snapshot, counters,
                            {'episode_id': episode_spec['episode_id'], 'outer': 64, 'phase': 'episode_closed'})
        if counters['materialization_attempts'] > 5 or counters['resets'] > 5:
            raise RuntimeError('materialization or reset budget exceeded')
        if (counters['outer_intervals'] != 256 or counters['mj_step_calls'] != 1280
                or counters['simulated_seconds'] != 2.56 or counters['mj_forward_calls'] > 300):
            raise ValueError('cumulative native counters differ from the exact four-episode contract')
        if len(results) != 4:
            raise ValueError('one or more of the four same-Env episode H5 files are missing')
        result = {
            'status': 'NATIVE_S2_COMPLETE_AWAITING_HOST_OFFLINE_S3',
            'input_head': snapshot['core_head'], 'runtime_identity': identity,
            'counters': counters, 'episodes': results,
            'gain_isolation': gain_comparison,
            'source_inventory': inventory,
            'resource_limits': {
                'rss_sampled_max_bytes': counters['max_rss_bytes'],
                'rss_sampling': 'sampled at each returned outer boundary; intra-interval peak may be missed',
                'native_log_bytes': native_log_bytes, 'output_bytes': output_bytes,
            },
            'native_wall_seconds': time.monotonic() - native_started_at,
            'executed_contract_sha256': _sha(native_dir / 'executed_contract.json'),
            'execution_freeze_sha256': _sha(output_dir / 'freeze' / 'execution_freeze.json'),
        }
        _write_json(native_dir / 'native_result.json', result)
        output_bytes = sum(path.stat().st_size for path in output_dir.rglob('*') if path.is_file())
        native_log_bytes = sum(path.stat().st_size for path in native_dir.rglob('*') if path.is_file())
        if native_log_bytes > 128 * 1024 * 1024 or output_bytes > 256 * 1024 * 1024:
            raise MemoryError('native/log or total output byte budget exceeded')
        result['resource_limits']['native_log_bytes'] = native_log_bytes
        result['resource_limits']['output_bytes'] = output_bytes
        _write_json(native_dir / 'native_result.json', result)
        _write_progress(native_dir, snapshot, counters,
                        {'episode_id': None, 'outer': None, 'phase': 'complete'})
        return result
    except BaseException as error:
        active['exception_type'] = type(error).__name__
        active['message'] = str(error)
        _write_json(native_dir / 'native_failure.json', {
            'status': 'NATIVE_FAILURE', 'exception_type': type(error).__name__,
            'message': str(error), 'traceback': traceback.format_exc(),
            'active': active, 'counters': counters,
            'native_wall_seconds': time.monotonic() - native_started_at,
        })
        _write_progress(native_dir, snapshot, counters, active)
        raise
    finally:
        for env in envs:
            try:
                if not getattr(env, '_closed', False):
                    env.close()
            except BaseException as close_error:
                _append_jsonl(native_dir / 'cleanup_errors.jsonl', {
                    'exception_type': type(close_error).__name__, 'message': str(close_error),
                })


def _write_progress(native_dir, snapshot, counters, active):
    _write_json(native_dir / 'native_progress.json', {
        'status': 'NATIVE_RUNNING', 'input_head': snapshot['core_head'],
        'counters': counters, 'active': active,
    })


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--native-attempt-dir', default='native')
    parser.add_argument('--prior-native-dir')
    args = parser.parse_args(argv)
    result = run_native(args.output_dir, args.snapshot, args.native_attempt_dir,
                        args.prior_native_dir)
    print(json.dumps({
        'status': result['status'], 'counters': result['counters'],
        'episodes': len(result['episodes']),
        'native_wall_seconds': result['native_wall_seconds'],
    }, sort_keys=True))


if __name__ == '__main__':
    main()
