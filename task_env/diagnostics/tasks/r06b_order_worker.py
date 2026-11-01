"""Single-process R06b baseline plus derived MuJoCo CPU execution worker."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback


ROOT = Path(__file__).resolve().parents[3]

FROZEN_LIMITS = {
    'native_processes': 1, 'materialization_attempts_total': 2, 'resets_total': 2,
    'outer_intervals_per_case': 64, 'outer_intervals_total': 128,
    'mj_step_calls_total': 640, 'simulated_seconds_total': 1.28,
    'physics_dt_s': 0.002, 'substeps_per_outer': 5, 'control_dt_s': 0.01,
    'mj_forward_calls_max': 300, 'worker_wall_seconds_max': 300,
    'output_bytes_max': 256 * 1024 * 1024, 'process_group_rss_bytes_max': 4 * 1024**3,
    'mem_available_before_start_min_bytes': 2 * 1024**3,
    'mem_available_stop_below_bytes': 768 * 1024**2, 'mem_available_stop_samples': 3,
    'shared_lock_wait_seconds_max': 1200, 'term_grace_seconds': 10,
    'cpu_threads': 1,
}
FROZEN_ORACLES = {
    'reset_joint_position_abs_error_max_rad_or_m': 1e-12,
    'reset_joint_velocity_abs_max': 1e-12,
    'reset_mount_position_error_max_m': 1e-8,
    'reset_mount_rotation_error_max_rad': 2e-7,
    'outer_joint_range_tolerance': 1e-6,
    'outer_mount_position_error_max_m': 1e-8,
    'outer_mount_rotation_error_max_rad': 2e-7,
    'arm_joint1_peak_abs_rad_min': 0.08,
    'arm_final_home_max_abs_error_rad': 0.02,
    'hand_close_phase_opening_max_m': 0.02,
    'hand_final_opening_min_m': 0.06,
    'hand_opening_excursion_min_m': 0.04,
    'finger_equality_max_abs_error_m': 1e-4,
    'hand_root_rotation_excursion_min_rad': 0.05,
    'native_step_calls_per_case': 320, 'forward_calls_per_case': 65,
    'simulated_seconds_per_case': 0.64,
    'warning_counts': 'must equal reset baseline at every boundary',
    'action_waveform': 'r03c_E3_arm_hand_active_intervals_1_64',
}
FROZEN_PRODUCTION_TAMPER_MATRIX = [
    'target_identity', 'ack_writer', 'prepared_command', 'source_digest',
    'configuration_identity', 'missing_writer', 'duplicate_slot',
    'boundary_observation', 't_plus_one', 'attachment_plan_hash', 'entity_binding', 'native_tcp',
]
FROZEN_RAW_TAMPER_MATRIX = [
    'raw_source_hash', 'raw_target', 'raw_ack', 'raw_native_slot', 'raw_state_order', 'raw_clock',
    'raw_contract_digest', 'raw_worker_result_file', 'raw_worker_result_size',
    'raw_worker_result_receipt', 'raw_worker_materialization', 'raw_worker_native_order',
    'raw_worker_native_slot', 'raw_worker_case_counters', 'raw_worker_aggregate_counters',
    'raw_worker_candidate', 'raw_duplicate_case', 'raw_missing_case', 'raw_swapped_case', 'raw_wrong_run',
]
FROZEN_TAMPER_MATRIX = [*FROZEN_PRODUCTION_TAMPER_MATRIX, *FROZEN_RAW_TAMPER_MATRIX]


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def _append_jsonl(path: Path, value) -> None:
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contract_digest(contract: dict) -> str:
    payload = {key: value for key, value in contract.items() if key != 'contract_sha256'}
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(',', ':'), allow_nan=False,
    ).encode()).hexdigest()


def _tree_sha(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(item for item in path.rglob('*') if item.is_file()):
        digest.update(file.relative_to(path).as_posix().encode())
        digest.update(b'\0')
        digest.update(file.read_bytes())
    return digest.hexdigest()


def _check_frozen_contract(contract: dict, contract_path: Path) -> None:
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    if (head, branch) != (contract['input_head'], contract['branch']):
        raise ValueError('live camera branch/HEAD differs from the frozen R06b native contract')
    dirty = subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True,
    )
    if dirty.strip():
        raise ValueError('camera worktree is not clean at the frozen R06b native boundary')
    if contract.get('limits') != FROZEN_LIMITS or contract.get('oracles') != FROZEN_ORACLES:
        raise ValueError('R06b frozen limits/oracles differ from the audited worker implementation')
    if contract.get('reader_tamper_matrix') != FROZEN_TAMPER_MATRIX:
        raise ValueError('R06b strict/raw reader tamper matrix differs from the audited package')
    if _contract_digest(contract) != contract['contract_sha256']:
        raise ValueError('R06b native contract bytes changed after freeze')
    for relative, expected in contract['submodule_pins'].items():
        actual = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT / relative, text=True,
        ).strip()
        if actual != expected:
            raise ValueError(f'R06b protected submodule pin changed: {relative}')
    for relative, expected in contract['code_sha256'].items():
        if _sha(ROOT / relative) != expected:
            raise ValueError(f'R06b implementation changed after native freeze: {relative}')
    for absolute, expected in contract['protected_sha256'].items():
        if _sha(Path(absolute)) != expected:
            raise ValueError(f'R06b protected input changed after native freeze: {absolute}')
    if (os.environ.get('OMP_NUM_THREADS'), os.environ.get('OPENBLAS_NUM_THREADS'),
            os.environ.get('MKL_NUM_THREADS')) != ('1', '1', '1'):
        raise ValueError('native worker CPU thread limits were not set to one')


def _copy_source_closure(candidate, destination: Path) -> dict[str, object]:
    from task_env.assembly.fixed_attachment import lower_fixed_attachment_sources

    source = candidate.source
    plan = candidate.attachment_plan
    lowered = lower_fixed_attachment_sources(
        parent_source=source.scene_source,
        source_by_entity=source.fixed_attachment_sources,
        scene=candidate.scene, plan=plan, assembly=candidate.assembly,
    )
    files = {
        'parent/scene.xml': lowered.parent_xml.encode('utf-8'),
        'child/scene.xml': lowered.child_xml.encode('utf-8'),
        **{f'parent/{name}': content for name, content in lowered.parent_assets.items()},
        **{f'child/{name}': content for name, content in lowered.child_assets.items()},
        'license/LICENSE': (source.scene_source.base_dir / 'LICENSE').read_bytes(),
    }
    entries = []
    for relative, content in sorted(files.items()):
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        entries.append({'path': relative, 'bytes': len(content),
                        'sha256': hashlib.sha256(content).hexdigest()})
    return {
        'source_closure_sha256': lowered.source_closure_sha256,
        'source_closure_bytes': lowered.closure_bytes,
        'copied_files': entries,
        'copied_tree_sha256': _tree_sha(destination),
    }


def _candidate_identity(candidate) -> dict[str, object]:
    return {
        'task_source_identity_sha256': candidate.artifact.task_source_identity_hash,
        'task_artifact_identity_sha256': candidate.artifact.identity_hash,
        'scene_identity_sha256': candidate.scene.identity_hash,
        'assembly_identity_sha256': candidate.assembly.logical_content_sha256,
        'attachment_plan_identity_sha256': candidate.attachment_plan.identity_hash,
        'leaf_plan_identity_sha256': candidate.plan.identity_sha256,
        'reset_plan_identity_sha256': candidate.reset_plan.identity_hash,
        'reset_sample_id': candidate.reset_plan.reset_sample.sample_id,
        'source_closure_sha256': candidate.source.source_closure_digest,
        'source_inventory': candidate.source_inventory,
    }


def _assert_receipt(candidate, receipt, expected) -> dict[str, object]:
    plan = candidate.attachment_plan
    if (receipt['scene_identity_sha256'] != candidate.scene.identity_hash
            or receipt['assembly_identity_sha256'] != candidate.assembly.logical_content_sha256
            or receipt['attachment_plan_sha256'] != plan.identity_hash
            or receipt['source_closure_sha256'] != candidate.source.source_closure_digest):
        raise ValueError('compiled fixed Attachment receipt identity join differs from the case')
    for name in ('native_body_order', 'native_joint_order', 'native_actuator_order'):
        if receipt[name] != expected[name]:
            raise ValueError(f'compiled native {name} differs from the frozen case order')
    joint_maps = receipt['native_joint_mappings']
    actuator_maps = receipt['native_actuator_mappings']
    if (set(joint_maps) != set(plan.native_joint_names)
            or set(actuator_maps) != set(plan.native_actuator_names)
            or set(receipt['native_body_mappings']) != set(plan.native_body_names)
            or set(receipt['native_site_mappings']) != set(plan.native_site_names)
            or set(receipt['native_tendon_mappings']) != set(plan.native_tendon_names)):
        raise ValueError('compiled native name maps do not cover the full fixed Attachment plan')
    if receipt['dimensions'] != expected['dimensions']:
        raise ValueError('compiled native model dimensions differ from the frozen R06b case')
    body_slots = {name: index for index, name in enumerate(receipt['native_body_order'])}
    body_slots.pop('world', None)
    if {row['native_name']: row['body_id'] for row in receipt['native_body_mappings'].values()} != body_slots:
        raise ValueError('compiled native Body IDs do not invert the frozen body order')
    joint_slots = {name: index for index, name in enumerate(receipt['native_joint_order'])}
    for row in joint_maps.values():
        native_name = row['native_name']
        if (joint_slots.get(native_name) != row['joint_id']
                or row['qpos_address'] != row['joint_id']
                or row['dof_address'] != row['joint_id']):
            raise ValueError(f'compiled native Joint ID/address map is inconsistent for {native_name}')
    actuator_slots_by_name = {
        name: index for index, name in enumerate(receipt['native_actuator_order'])
    }
    for canonical, row in actuator_maps.items():
        native_name = row['native_name']
        if (actuator_slots_by_name.get(native_name) != row['actuator_id']
                or row['ctrl_slot'] != row['actuator_id']):
            raise ValueError(f'compiled native Actuator/ctrl slot map is inconsistent for {native_name}')
        if canonical.startswith('panda-arm/'):
            local = canonical.rsplit('/', 1)[1].replace('actuator', 'joint')
            expected_target = plan.native_joint_names[f'panda-arm/{local}']
            if row['transmission_type'] != 0 or row['target_native_name'] != expected_target:
                raise ValueError(f'compiled Arm Actuator transmission target is wrong for {canonical}')
        elif (row['transmission_type'] != 3
              or row['target_native_name'] != plan.native_tendon_names['panda-hand/split']):
            raise ValueError(f'compiled Hand Actuator transmission target is wrong for {canonical}')
    joint_ids = [row['joint_id'] for row in joint_maps.values()]
    qpos = [row['qpos_address'] for row in joint_maps.values()]
    dofs = [row['dof_address'] for row in joint_maps.values()]
    actuator_ids = [row['actuator_id'] for row in actuator_maps.values()]
    slots = [row['ctrl_slot'] for row in actuator_maps.values()]
    if (sorted(joint_ids) != list(range(9)) or sorted(qpos) != list(range(9))
            or sorted(dofs) != list(range(9)) or sorted(actuator_ids) != list(range(8))
            or sorted(slots) != list(range(8))):
        raise ValueError('compiled native IDs, qpos/dof addresses or ctrl slots are aliased or incomplete')
    for inverse_name, forward_name in (
        ('native_body_inverse', 'native_body_mappings'),
        ('native_site_inverse', 'native_site_mappings'),
        ('native_joint_inverse', 'native_joint_mappings'),
        ('native_actuator_inverse', 'native_actuator_mappings'),
    ):
        inverse = receipt[inverse_name]
        forward = receipt[forward_name]
        if inverse != {row['native_name']: key for key, row in forward.items()}:
            raise ValueError(f'compiled Attachment inverse map {inverse_name} is inconsistent')
    expected_slots = expected['actuator_slots']
    actual_slots = {key: value['ctrl_slot'] for key, value in actuator_maps.items()}
    if actual_slots != expected_slots:
        raise ValueError('compiled named Actuator to native ctrl slot mapping differs from source recipe')
    return {
        'receipt_identity_sha256': receipt['receipt_identity_sha256'],
        'provider_materialization_id': receipt['provider_materialization_id'],
        'native_body_order': receipt['native_body_order'],
        'native_joint_order': receipt['native_joint_order'],
        'native_actuator_order': receipt['native_actuator_order'],
        'native_joint_mappings': joint_maps,
        'native_actuator_mappings': actuator_maps,
        'native_body_mappings': receipt['native_body_mappings'],
        'native_body_inverse': receipt['native_body_inverse'],
        'native_site_mappings': receipt['native_site_mappings'],
        'native_site_inverse': receipt['native_site_inverse'],
        'native_joint_inverse': receipt['native_joint_inverse'],
        'native_actuator_inverse': receipt['native_actuator_inverse'],
        'native_tendon_mappings': receipt['native_tendon_mappings'],
        'compiled_exclusions': receipt['compiled_exclusions'],
        'dimensions': receipt['dimensions'],
        'runtime_identity': receipt['runtime_identity'],
    }


def _run_case(case, output_dir: Path, counters: dict, active: dict,
              identity: dict, native_dir: Path) -> dict[str, object]:
    from task_env.tasks.position_candidate.attached_leaf_candidate import (
        ARM_HOME, action_for_interval, build_attached_leaf_candidate,
    )
    from task_env.tasks.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions import control as control_module
    from task_env.tasks import reference_env as reference_env_module
    from task_env.runtime.sessions.leaf_control import prepare_leaf_command
    from task_env.recorders.h5 import load_leaf_control_records_h5
    from task_env.assembly.fixed_attachment import lower_fixed_attachment_sources
    from r03c_attached_leaf_probe import (
        _candidate_bindings, _check_outer, _check_reset, _mount_requirements,
        _rotation_error, _tamper_checks,
    )

    active.update({'episode_id': case['episode_id'], 'outer': 0, 'phase': 'candidate_build'})
    case_counts = counters['cases'][case['episode_id']]
    _write_json(native_dir / 'native_progress.json', {'status': 'NATIVE_WORKER_RUNNING',
                'counters': counters, 'active': active})
    candidate = build_attached_leaf_candidate(
        environment_type=SelectedReferenceEnv, arm_gain=2.5,
        hand_stiffness_N_per_m=50.0, provider='mujoco', horizon=64,
        episode_id=case['episode_id'], arm_active=True, hand_active=True,
        order_variant=case['order_variant'],
    )
    live_identity = _candidate_identity(candidate)
    if live_identity != case['candidate']:
        raise ValueError(f"{case['episode_id']} candidate identities/source closure differ from native freeze")
    if candidate.env.camera_observation_config is not None:
        raise ValueError('R06b native case unexpectedly enabled camera observations')
    source_copy = _copy_source_closure(candidate, output_dir / 'cases' / case['episode_id'] / 'source_closure')
    if source_copy['source_closure_sha256'] != case['candidate']['source_closure_sha256']:
        raise ValueError('copied source closure differs from frozen candidate closure')

    original_control_materialize = control_module.materialize_control
    original_reference_materialize = reference_env_module.materialize_control

    def make_counted_materialize(original):
        def counted_materialize(*args, **kwargs):
            counters['materialization_attempts'] += 1
            case_counts['materialization_attempts'] += 1
            if counters['materialization_attempts'] > 2:
                raise RuntimeError('R06b per-worker materialization budget of two attempts exceeded')
            active['phase'] = 'runtime_materialization'
            _write_json(native_dir / 'native_progress.json', {'status': 'NATIVE_WORKER_RUNNING',
                        'counters': counters, 'active': active})
            result = original(*args, **kwargs)
            counters['materializations_completed'] += 1
            case_counts['materializations_completed'] += 1
            return result
        return counted_materialize

    control_module.materialize_control = make_counted_materialize(original_control_materialize)
    reference_env_module.materialize_control = make_counted_materialize(original_reference_materialize)
    env = candidate.env
    session = None
    primary_error = None
    cleanup_error = None
    result = None
    try:
        active['phase'] = 'public_env_reset'
        counters['resets'] += 1
        case_counts['reset_attempts'] += 1
        if counters['resets'] > 2:
            raise RuntimeError('R06b reset budget of two attempts exceeded')
        _, reset_info = env.reset(seed=31)
        counters['resets_completed'] += 1
        case_counts['resets_completed'] += 1
        session = env.session
        if (reset_info.get('state_boundary_id') != env.typed_state.view.boundary.boundary_id
                or reset_info.get('reset_sample_id') != candidate.reset_plan.reset_sample.sample_id
                or reset_info.get('seed') != 31):
            raise ValueError('public reset did not realize the exact seed-31 ResetPlan')
        if session.fixed_attachment_receipt['runtime_identity'] != identity:
            raise ValueError('adapter Runtime identity differs from the inspected MuJoCo 3.8.1 worker')
        receipt = session.fixed_attachment_receipt
        attachment_receipt = _assert_receipt(candidate, receipt, case['native_expected'])
        if session.leaf_materialization_receipt.fixed_attachment_receipt_identity_sha256 != receipt['receipt_identity_sha256']:
            raise ValueError('leaf and fixed Attachment materialization receipts do not share one Env')
        if session.leaf_materialization_receipt.materialization_id != receipt['provider_materialization_id']:
            raise ValueError('leaf and fixed Attachment receipts have different materialization IDs')
        if session.leaf_materialization_receipt.scene_identity_sha256 != candidate.scene.identity_hash:
            raise ValueError('leaf materialization receipt differs from the frozen Scene')

        warnings = tuple(int(value) for value in session.fixed_attachment_diagnostics['warning_counts'])
        mount_requirements = _mount_requirements(candidate)
        joint_bindings, frame_bindings = _candidate_bindings(candidate)
        initial = session.snapshot_v1(
            scene=candidate.scene, joint_bindings=joint_bindings,
            frame_bindings=frame_bindings, requirements=mount_requirements,
        )
        reset_metrics = _check_reset(candidate, env, initial, warnings)
        initial_hand_root = next(
            item.pose_world.quaternion_wxyz for item in initial.view.frames
            if item.frame.entity_id == 'panda-hand' and item.frame.frame_id == 'hand'
        )

        # Verify named per-joint targets resolve to this compiled model's actual
        # slots before the public dispatcher applies any writer.
        probe = action_for_interval(candidate, 1, arm_active=True, hand_active=True)
        arm_binding = next(item.binding for item in candidate.plan.leaves
                           if item.binding.profile_kind == 'arm_position')
        prepared = prepare_leaf_command(
            candidate.plan, arm_binding.writer_id, probe.arm, env.typed_state,
            session.leaf_materialization_receipt, session.leaf_configuration_revision,
            scene=candidate.scene,
        )
        actuator_maps = receipt['native_actuator_mappings']
        if len(prepared.slot_values) != 7:
            raise ValueError('Arm prepared command does not contain all seven canonical Joint targets')
        for value in prepared.slot_values:
            canonical = f'{value.actuator.entity_id}/{value.actuator.actuator_id}'
            if (value.ctrl_slot != actuator_maps[canonical]['ctrl_slot']
                    or value.actuator.actuator_id != canonical.rsplit('/', 1)[1]):
                raise ValueError(f'Arm target {canonical} does not bind its semantic native ctrl slot')

        h5_path = output_dir / 'cases' / case['episode_id'] / f"{case['episode_id']}.h5"
        h5_path.parent.mkdir(parents=True, exist_ok=True)
        if h5_path.exists():
            raise FileExistsError(h5_path)
        env.start_recording(h5_path)
        maximum_mount_position = reset_metrics['mount_position_error_m']
        maximum_mount_rotation = reset_metrics['mount_rotation_error_rad']
        maximum_hand_root_rotation = 0.0
        peak_arm = abs(float(env.state.joint_position['panda-arm/joint1']))
        openings, finger_mismatches = [], []
        for interval in range(1, 65):
            active.update({'phase': 'public_typed_dispatch', 'outer': interval})
            action = action_for_interval(candidate, interval, arm_active=True, hand_active=True)
            _, _, terminated, truncated, _ = env.step(action)
            counters['outer_intervals'] += 1
            case_counts['outer_intervals'] += 1
            counters['simulated_seconds'] = counters['outer_intervals'] * 0.01
            if (counters['outer_intervals'] > 128 or counters['mj_step_calls'] > 640
                    or terminated or truncated != (interval == 64)):
                raise ValueError('R06b outer transition/termination/substep budget mismatch')
            publication = session.snapshot_v1(
                scene=candidate.scene, joint_bindings=joint_bindings,
                frame_bindings=frame_bindings, requirements=mount_requirements,
            )
            position_error, rotation_error = _check_outer(
                candidate, env, publication, interval, warnings,
            )
            maximum_mount_position = max(maximum_mount_position, position_error)
            maximum_mount_rotation = max(maximum_mount_rotation, rotation_error)
            hand_root = next(
                item.pose_world.quaternion_wxyz for item in publication.view.frames
                if item.frame.entity_id == 'panda-hand' and item.frame.frame_id == 'hand'
            )
            maximum_hand_root_rotation = max(
                maximum_hand_root_rotation, _rotation_error(initial_hand_root, hand_root),
            )
            measured = {(item.entity_id, item.joint_id): float(item.position[0])
                        for item in env.typed_state.view.joints}
            expected_public_order = tuple(sorted(measured))
            actual_public_order = tuple((item.entity_id, item.joint_id)
                                        for item in env.typed_state.view.joints)
            if actual_public_order != expected_public_order:
                raise ValueError('typed public Joint state order depends on the native model order')
            peak_arm = max(peak_arm, abs(measured[('panda-arm', 'joint1')]))
            openings.append(measured[('panda-hand', 'finger_joint1')]
                            + measured[('panda-hand', 'finger_joint2')])
            finger_mismatches.append(abs(measured[('panda-hand', 'finger_joint1')]
                                         - measured[('panda-hand', 'finger_joint2')]))
            counters['simulated_seconds'] = counters['outer_intervals'] * 0.01
            _write_json(native_dir / 'native_progress.json', {
                'status': 'NATIVE_WORKER_RUNNING', 'counters': counters, 'active': active,
            })

        final_positions = {(item.entity_id, item.joint_id): float(item.position[0])
                           for item in env.typed_state.view.joints}
        final_arm = [final_positions[('panda-arm', f'joint{i}')] for i in range(1, 8)]
        arm_error = max(abs(value - home) for value, home in zip(final_arm, ARM_HOME, strict=True))
        hand_minimum = min(openings[16:32])
        hand_final = openings[-1]
        hand_excursion = max(openings) - min(openings)
        if (arm_error > 0.02 or peak_arm < 0.08 or maximum_hand_root_rotation < 0.05
                or hand_minimum > 0.02 or hand_final < 0.06 or hand_excursion < 0.04
                or max(finger_mismatches) > 1e-4):
            raise ValueError('bounded Arm/Hand physical-motion or fixed-mount gates failed')
        final_diagnostics = session.fixed_attachment_diagnostics
        if (final_diagnostics['native_step_count'] != 320
                or final_diagnostics['forward_call_count'] != 65
                or not abs(float(final_diagnostics['native_time_s']) - 0.64) <= 1e-12):
            raise ValueError('one Env did not close at exactly 64 outer / 320 native steps / 0.64 s')

        active['phase'] = 'recording_finalization'
        record_result = env.finish_recording('horizon')
        if (record_result['transition_count'], record_result['observation_count']) != (64, 65):
            raise ValueError('public H5 finalization did not preserve exact 64/65 T/T+1 counts')
        _write_json(native_dir / f"{case['episode_id']}_recording_finalized.json", record_result)
        session_ref = session
        env.close()
        close_evidence = session_ref.fixed_attachment_close_evidence
        if (close_evidence is None or close_evidence['session_closed'] is not True
                or close_evidence['model_released'] is not True
                or close_evidence['data_released'] is not True
                or close_evidence['native_step_count'] != 320
                or close_evidence['forward_call_count'] != 65):
            raise ValueError('normal Env close did not release the same materialization cleanly')
        loaded = load_leaf_control_records_h5(h5_path)
        if (loaded['transition_count'], loaded['observation_count']) != (64, 65):
            raise ValueError('strict production leaf H5 reader did not return exact T/T+1 counts')
        tamper_output = output_dir / 'reader_tamper' / case['episode_id']
        tamper_output.mkdir(parents=True, exist_ok=True)
        tamper_results = _tamper_checks(h5_path, tamper_output)
        actual_tamper_names = [item.get('case') for item in tamper_results]
        if (actual_tamper_names != FROZEN_PRODUCTION_TAMPER_MATRIX
                or any(not item['rejected'] for item in tamper_results)):
            raise ValueError('strict H5 reader did not reject the exact frozen production tamper matrix')
        result = {
            'episode_id': case['episode_id'], 'order_variant': case['order_variant'],
            'candidate': live_identity, 'native_receipt': attachment_receipt,
            'source_closure_copy': source_copy,
            'h5': {'path': str(h5_path), 'sha256': _sha(h5_path), 'bytes': h5_path.stat().st_size,
                   'transition_count': loaded['transition_count'],
                   'observation_count': loaded['observation_count'],
                   'production_reader': 'PASS'},
            'reader_tamper_cases': tamper_results,
            'reset': reset_metrics,
            'physical_gates': {
                'arm_joint1_peak_abs_rad': peak_arm,
                'arm_return_home_max_abs_rad': arm_error,
                'hand_close_min_opening_m': hand_minimum,
                'hand_final_opening_m': hand_final,
                'hand_total_excursion_m': hand_excursion,
                'finger_equality_max_m': max(finger_mismatches),
                'hand_root_rotation_max_rad': maximum_hand_root_rotation,
                'mount_position_error_max_m': maximum_mount_position,
                'mount_rotation_error_max_rad': maximum_mount_rotation,
            },
            'warning_counts': list(warnings),
            'native_counts': {
                'episode_id': case['episode_id'],
                **case_counts,
                'outer_intervals_total': case_counts['outer_intervals'],
                'mj_step_calls_case': final_diagnostics['native_step_count'],
                'mj_forward_calls_case': final_diagnostics['forward_call_count'],
                'simulated_seconds_case': final_diagnostics['native_time_s'],
            },
            'close_evidence': close_evidence,
            'episode_outcome': record_result['outcome'],
        }
        _write_json(native_dir / f"{case['episode_id']}_result.json", result)
    except BaseException as error:
        primary_error = error
    finally:
        control_module.materialize_control = original_control_materialize
        reference_env_module.materialize_control = original_reference_materialize
        if session is None:
            session = getattr(env, 'session', None)
        if env is not None and not getattr(env, '_closed', False):
            try:
                env.close()
            except BaseException as error:
                cleanup_error = error
        if primary_error is not None:
            failure = {
                'episode_id': case['episode_id'],
                'primary_error': {'type': type(primary_error).__name__, 'message': str(primary_error),
                                  'traceback': ''.join(traceback.format_exception(primary_error))},
                'cleanup_error': (None if cleanup_error is None else
                                  {'type': type(cleanup_error).__name__, 'message': str(cleanup_error),
                                   'traceback': ''.join(traceback.format_exception(cleanup_error))}),
                'close_evidence': (None if session is None else session.fixed_attachment_close_evidence),
                'counters': counters,
                'case_counters': case_counts,
            }
            _write_json(native_dir / f"{case['episode_id']}_failure.json", failure)
            raise primary_error
        if cleanup_error is not None:
            raise cleanup_error
    return result


def run_worker(contract_path: Path) -> dict[str, object]:
    contract_path = contract_path.resolve()
    contract = json.loads(contract_path.read_text())
    output_dir = Path(contract['output_dir']).resolve()
    native_dir = output_dir / 'native'
    if native_dir.exists():
        raise FileExistsError(native_dir)
    native_dir.mkdir(parents=True)
    _check_frozen_contract(contract, contract_path)
    starts = json.loads((output_dir / 'native_start_ledger.json').read_text())
    if starts.get('native_start_count') != 1 or starts.get('native_worker') != 'r06b_order_worker.py':
        raise ValueError('R06b native worker does not have the unique authorized native-start reservation')
    if len(contract['cases']) != 2 or [case['episode_id'] for case in contract['cases']] != ['E1', 'E2']:
        raise ValueError('R06b same-worker native contract must contain baseline E1 and derived E2 exactly once')
    counters = {
        'native_starts': 1, 'materialization_attempts': 0, 'materializations_completed': 0,
        'resets': 0, 'resets_completed': 0, 'outer_intervals': 0,
        'mj_step_calls': 0, 'mj_forward_calls': 0,
        'attempted_mj_step_calls': 0, 'attempted_mj_forward_calls': 0,
        'simulated_seconds': 0.0,
        'cases': {case['episode_id']: {
            'materialization_attempts': 0, 'materializations_completed': 0,
            'reset_attempts': 0, 'resets_completed': 0,
            'outer_intervals': 0, 'attempted_mj_step_calls': 0,
            'mj_step_calls': 0, 'attempted_mj_forward_calls': 0,
            'mj_forward_calls': 0,
        } for case in contract['cases']},
    }
    active = {'episode_id': None, 'outer': 0, 'phase': 'native_import'}
    _write_json(native_dir / 'native_progress.json', {
        'status': 'NATIVE_PROCESS_STARTED', 'input_head': contract['input_head'],
        'contract_sha256': contract['contract_sha256'], 'counters': counters, 'active': active,
    })
    started = time.monotonic()
    mujoco_module = None
    original_step = original_forward = None
    try:
        import mujoco as mujoco_module
        from r03c_attached_leaf_probe import _native_identity

        identity = _native_identity(mujoco_module, contract['mujoco_static'])
        if (identity['package_version'], identity['runtime_version'], identity['api_version']) != (
            '3.8.1', '3.8.1', 3008001,
        ):
            raise ValueError('R06b native worker is not MuJoCo package/runtime 3.8.1 API 3008001')
        _write_json(native_dir / 'runtime_identity.json', identity)
        original_step, original_forward = mujoco_module.mj_step, mujoco_module.mj_forward
        trace = native_dir / 'native_step_trace.jsonl'

        def counted_step(model, data, *args, **kwargs):
            attempted = int(kwargs.get('nstep', args[0] if args else 1))
            counters['attempted_mj_step_calls'] += attempted
            case_counts = counters['cases'][active['episode_id']]
            case_counts['attempted_mj_step_calls'] += attempted
            if counters['mj_step_calls'] + attempted > 640:
                raise RuntimeError('R06b native mj_step budget of 640 would be exceeded')
            try:
                result = original_step(model, data, *args, **kwargs)
            except BaseException:
                _append_jsonl(trace, {'event': 'mj_step_raise', 'attempted_nstep': attempted,
                                      'successful_before': counters['mj_step_calls'], **active})
                raise
            counters['mj_step_calls'] += attempted
            case_counts['mj_step_calls'] += attempted
            _append_jsonl(trace, {'event': 'mj_step', 'nstep': attempted,
                                  'successful_cumulative': counters['mj_step_calls'], **active})
            if counters['mj_step_calls'] > 640:
                raise RuntimeError('R06b native mj_step budget exceeded after provider call')
            return result

        def counted_forward(*args, **kwargs):
            case_counts = counters['cases'][active['episode_id']]
            counters['attempted_mj_forward_calls'] += 1
            case_counts['attempted_mj_forward_calls'] += 1
            if counters['mj_forward_calls'] + 1 > 300:
                raise RuntimeError('R06b mj_forward diagnostic budget of 300 would be exceeded')
            result = original_forward(*args, **kwargs)
            counters['mj_forward_calls'] += 1
            case_counts['mj_forward_calls'] += 1
            return result

        mujoco_module.mj_step, mujoco_module.mj_forward = counted_step, counted_forward
        results = []
        for case in contract['cases']:
            active.update({'episode_id': case['episode_id'], 'outer': 0, 'phase': 'case_start'})
            results.append(_run_case(case, output_dir, counters, active, identity, native_dir))
        if (counters['materialization_attempts'], counters['materializations_completed'],
                counters['resets'], counters['resets_completed'], counters['outer_intervals'],
                counters['mj_step_calls'], counters['attempted_mj_step_calls']) != (
                    2, 2, 2, 2, 128, 640, 640):
            raise ValueError('R06b final cumulative native counters differ from its exact bounded contract')
        if counters['mj_forward_calls'] != 130:
            raise ValueError('R06b final cumulative mj_forward count differs from 130')
        for episode_id, case_counts in counters['cases'].items():
            if (case_counts['materialization_attempts'], case_counts['materializations_completed'],
                    case_counts['reset_attempts'], case_counts['resets_completed'],
                    case_counts['outer_intervals'], case_counts['attempted_mj_step_calls'],
                    case_counts['mj_step_calls'], case_counts['mj_forward_calls']) != (
                        1, 1, 1, 1, 64, 320, 320, 65):
                raise ValueError(f'R06b {episode_id} case counters differ from the exact bounded contract')
        if abs(counters['simulated_seconds'] - 1.28) > 1e-12:
            raise ValueError('R06b total simulated time differs from 1.28 seconds')
        if not results[0]['native_receipt']['native_actuator_order'] == [
            *(f'actuator{i}' for i in range(1, 8)), 'probe_hand_actuator8',
        ] or not results[1]['native_receipt']['native_actuator_order'] == [
            *(f'actuator{i}' for i in range(7, 0, -1)), 'probe_hand_actuator8',
        ]:
            raise ValueError('baseline and derived native actuator order lists were not both observed')
        if (results[0]['native_receipt']['native_actuator_mappings']['panda-arm/actuator1']['ctrl_slot']
                == results[1]['native_receipt']['native_actuator_mappings']['panda-arm/actuator1']['ctrl_slot']):
            raise ValueError('derived compilation did not move the named Arm actuator1 native ctrl slot')
        result = {
            'status': 'R06B_NATIVE_WORKER_PASS_PENDING_READBACK',
            'input_head': contract['input_head'], 'contract_sha256': contract['contract_sha256'],
            'runtime_identity': identity, 'counters': counters, 'cases': results,
            'native_wall_seconds': time.monotonic() - started,
            'max_native_wall_seconds': 300,
            'output_bytes': sum(path.stat().st_size for path in output_dir.rglob('*') if path.is_file()),
            'max_output_bytes': 256 * 1024 * 1024,
        }
        if result['output_bytes'] > result['max_output_bytes']:
            raise MemoryError('R06b output byte budget of 256 MiB exceeded')
        if result['native_wall_seconds'] > 300:
            raise TimeoutError('R06b native worker exceeded the 300 second wall limit')
        _write_json(native_dir / 'native_result.pending.json', result)
        result['output_bytes'] = sum(path.stat().st_size for path in output_dir.rglob('*') if path.is_file())
        _write_json(native_dir / 'native_result.pending.json', result)
        (native_dir / 'native_result.pending.json').replace(native_dir / 'native_result.json')
        _write_json(native_dir / 'native_progress.json', {
            'status': 'NATIVE_WORKER_COMPLETE', 'counters': counters,
            'active': {'episode_id': None, 'outer': None, 'phase': 'complete'},
        })
        return result
    except BaseException as error:
        failure = {
            'status': 'NATIVE_WORKER_FAILED', 'input_head': contract.get('input_head'),
            'contract_sha256': contract.get('contract_sha256'), 'counters': counters,
            'active': active, 'error_type': type(error).__name__, 'error': str(error),
            'traceback': ''.join(traceback.format_exception(error)),
            'native_wall_seconds': time.monotonic() - started,
        }
        _write_json(native_dir / 'native_failure.json', failure)
        _write_json(native_dir / 'native_progress.json', {
            'status': 'NATIVE_WORKER_FAILED', 'counters': counters, 'active': active,
        })
        raise
    finally:
        if mujoco_module is not None and original_step is not None and original_forward is not None:
            mujoco_module.mj_step = original_step
            mujoco_module.mj_forward = original_forward


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_worker(args.contract)
    print(json.dumps({'status': result['status'], 'counters': result['counters']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
