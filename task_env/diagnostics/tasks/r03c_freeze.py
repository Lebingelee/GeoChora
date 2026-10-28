"""Provider-free freeze of the exact R03c native execution contract."""
from __future__ import annotations

import builtins
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_001'
SNAPSHOT = ROOT / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r03b_001/r03c_001_input_snapshot.json'
PROMPT = ROOT / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r03b_001/luna_r03c_001_prompt.md'
SOURCES = (
    'task_env/controllers/canonical/leaf_plan.py',
    'task_env/controllers/canonical/leaf_profiles.py',
    'task_env/recorders/h5.py',
    'task_env/runtime/sessions/api.py',
    'task_env/runtime/sessions/common.py',
    'task_env/runtime/sessions/control.py',
    'task_env/runtime/sessions/leaf_control.py',
    'task_env/runtime/sessions/mujoco.py',
    'task_env/runtime/sessions/source.py',
    'task_env/tasks/position_candidate/attached_leaf_candidate.py',
    'task_env/tasks/position_candidate/fixed_attachment_candidate.py',
    'task_env/tasks/reference_env.py',
    'task_env/diagnostics/tasks/r03c_attached_leaf_probe.py',
    'task_env/diagnostics/tasks/r03c_freeze.py',
    'task_env/diagnostics/tasks/r03c_offline_readback.py',
    'task_env/diagnostics/tasks/test_phase_ii_01_r03c_attached_leaf.py',
)
EPISODES = (
    ('E1', True, False, 2.5),
    ('E2', False, True, 2.5),
    ('E3', True, True, 2.5),
    ('E4', True, True, 3.0),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        allow_nan=False,
    ).encode()).hexdigest()


def _preserved_retry_provenance(output_dir):
    prior_native_dir = output_dir / 'native'
    prior_failure_path = prior_native_dir / 'native_failure.json'
    prior_progress_path = prior_native_dir / 'native_progress.json'
    prior_ledger_path = prior_native_dir / 'native_process_ledger.jsonl'
    prior_failure = json.loads(prior_failure_path.read_text())
    prior_progress = json.loads(prior_progress_path.read_text())
    prior_ledger = [json.loads(line) for line in prior_ledger_path.read_text().splitlines() if line.strip()]
    if (len(prior_ledger) != 1 or prior_ledger[0].get('attempt') != 1
            or prior_failure.get('status') != 'NATIVE_FAILURE'
            or prior_failure.get('exception_type') != 'ValueError'
            or prior_failure.get('message') != 'Attachment receipt omits the canonical Hand actuator/tendon mapping'
            or prior_failure.get('active', {}).get('phase') != 'public_env_reset'
            or prior_failure.get('counters', {}).get('mj_step_calls') != 0
            or prior_failure.get('counters', {}).get('mj_forward_calls') != 0
            or prior_failure.get('counters', {}).get('resets') != 1
            or prior_progress.get('counters', {}).get('native_starts') != 1):
        raise ValueError('preserved first native attempt does not match the authorized pre-step retry conditions')
    return {
        'retry_attempt': 2, 'prior_native_starts': 1,
        'prior_materialization_attempts_reconstructed': 1, 'prior_resets': 1,
        'prior_mj_forward_calls': 0, 'prior_mj_step_calls': 0,
        'prior_native_failure_sha256': sha(prior_failure_path),
        'prior_native_progress_sha256': sha(prior_progress_path),
        'prior_native_process_ledger_sha256': sha(prior_ledger_path),
        'reconstruction_basis': 'preserved traceback enters ReferenceEnv.materialize_control and RuntimeSession.admit_leaf_control_plan; failed before mj_forward/mj_step',
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=OUTPUT)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--prompt', type=Path, default=PROMPT)
    parser.add_argument('--fresh-window', action='store_true')
    args = parser.parse_args(argv)
    output_dir = args.output_dir
    freeze_dir = output_dir / 'freeze'
    if freeze_dir.exists():
        raise FileExistsError(freeze_dir)
    snapshot = json.loads(args.snapshot.read_text())
    if snapshot['core_head'] != subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip():
        raise ValueError('input HEAD changed before the R03c execution freeze')
    if args.fresh_window:
        if (snapshot.get('native_window', {}).get('max_starts') != 1
                or snapshot.get('native_window', {}).get('consumed') is not False):
            raise ValueError('fresh R03c window requires an explicit unconsumed one-start snapshot')
        if (output_dir / 'native').exists():
            raise FileExistsError('fresh R03c window already contains a native directory')
        retry_provenance = {}
    else:
        retry_provenance = _preserved_retry_provenance(output_dir)
    original_import = builtins.__import__

    def block_provider(name, *args, **kwargs):
        level = args[3] if len(args) > 3 else kwargs.get('level', 0)
        if level == 0 and name.split('.', 1)[0] in {'mujoco', 'taichi'}:
            raise AssertionError(f'provider-free freeze imported {name}')
        return original_import(name, *args, **kwargs)

    builtins.__import__ = block_provider
    from task_env.tasks.position_candidate.attached_leaf_candidate import build_attached_leaf_candidate
    from task_env.tasks.reference_env import SelectedReferenceEnv
    from task_env.diagnostics.tasks.r03c_attached_leaf_probe import (
        _candidate_bindings, _mount_requirements,
    )

    rows = []
    inventory = None
    for episode_id, arm_active, hand_active, arm_gain in EPISODES:
        candidate = build_attached_leaf_candidate(
            environment_type=SelectedReferenceEnv, arm_gain=arm_gain,
            hand_stiffness_N_per_m=50.0, provider='mujoco', horizon=64,
            episode_id=episode_id, arm_active=arm_active, hand_active=hand_active,
        )
        try:
            inventory = candidate.source_inventory
            mount_requirements = _mount_requirements(candidate)
            joint_bindings, frame_bindings = _candidate_bindings(candidate)
            requested_frames = {
                (item.entity_id, item.subject_id)
                for item in mount_requirements.requirements
                if item.field_name == 'frame_pose_world'
            }
            if (('panda-arm', 'attachment_site') not in requested_frames
                    or ('panda-hand', 'hand') not in requested_frames
                    or 'panda-arm/attachment_site' not in frame_bindings
                    or 'panda-hand/hand' not in frame_bindings
                    or len(joint_bindings) != 9):
                raise ValueError('static named Runtime snapshot contract misses an Entity/Joint/mount binding')
            rows.append({
                'episode_id': episode_id, 'arm_active': arm_active,
                'hand_active': hand_active, 'arm_gain': arm_gain,
                'task_source_identity_sha256': candidate.artifact.task_source_identity_hash,
                'task_artifact_identity_sha256': candidate.artifact.identity_hash,
                'scene_identity_sha256': candidate.scene.identity_hash,
                'assembly_identity_sha256': candidate.assembly.logical_content_sha256,
                'attachment_plan_identity_sha256': candidate.attachment_plan.identity_hash,
                'source_closure_sha256': candidate.source.source_closure_digest,
                'reset_plan_identity_sha256': candidate.reset_plan.identity_hash,
                'reset_sample_id': candidate.reset_plan.reset_sample.sample_id,
                'effective_leaf_plan_identity_sha256': candidate.plan.identity_sha256,
                'mount_snapshot_frame_requirements': sorted([list(item) for item in requested_frames]),
                'typed_joint_binding_count': len(joint_bindings),
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
            })
        finally:
            candidate.env.close()
    if {'mujoco', 'taichi'} & set(sys.modules):
        raise AssertionError('provider-free freeze loaded a native provider')
    if inventory is None:
        raise AssertionError('candidate source inventory is missing')
    if (inventory['derived_source_closure_bytes'] != 34_318_679
            or inventory['derived_source_closure_sha256'] !=
            'b97f7c4f9b585ef175e986b9fb59f3054de74184666373443d6d166a45609b63'):
        raise ValueError('R03c fixed source closure differs from the protected R03b source')
    if rows[0]['scene_identity_sha256'] != '7981f0bb31875b35eb0973b08c1f65ac09210b55b7e9e0ea45761e4f8a4cfe9a':
        raise ValueError('R03c Scene identity differs from the protected R03b Scene')
    if rows[0]['assembly_identity_sha256'] != '232e62b18ea48ab04cc4ec2761a11666c8e1955a599b4f04ff585887d2fe1b4a':
        raise ValueError('R03c Assembly identity differs from the protected R03b Assembly')
    if rows[0]['attachment_plan_identity_sha256'] != 'b4b2099d7b0009aed023c74f15b142194ba47e23823fff639f505736fb92c2a3':
        raise ValueError('R03c Attachment plan differs from the protected R03b plan')

    contract = {
        'schema_version': 'r03c-attached-leaf-execution-contract-v1',
        'input_head': snapshot['core_head'], 'backend': 'cpu',
        'fresh_native_window': args.fresh_window,
        'retry_provenance': retry_provenance,
        'provider': {'package_version': '3.8.1', 'runtime_version': '3.8.1', 'api_version': 3008001},
        'seed': 31, 'horizon': 64, 'outer_dt_s': 0.01, 'physics_dt_s': 0.002,
        'substeps': 5, 'episodes': rows,
        'required_native_totals': {
            'native_starts': 1 if args.fresh_window else 2,
            'materialization_attempts': 4 if args.fresh_window else 5,
            'resets': 4 if args.fresh_window else 5,
            'mj_forward_max': 300,
            'outer_intervals': 256, 'mj_step_calls': 1280, 'simulated_seconds': 2.56,
        },
        'frozen_oracles': {
            'arm_home_rad': [0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853],
            'arm_joint1_peak_abs_rad_min': 0.08, 'arm_home_error_max_rad': 0.02,
            'arm_active_hand_root_rotation_min_rad': 0.05,
            'hand_closed_min_opening_max_m': 0.02, 'hand_final_opening_min_m': 0.06,
            'hand_excursion_min_m': 0.04, 'hand_finger_mismatch_max_m': 0.0001,
            'fixed_mount_position_max_m': 1e-8, 'fixed_mount_rotation_max_rad': 2e-7,
            'joint_range_tolerance': 1e-6, 'clock_tolerance_s': 1e-12,
            'reset_position_velocity_ctrl_clock_tolerance': 1e-12,
            'warning_count_delta': 0,
        },
    }
    code_hashes = {relative: sha(ROOT / relative) for relative in SOURCES}
    # Do not leave a partial freeze directory when candidate/static validation
    # fails. Raw evidence from earlier windows is never reused as this output.
    freeze_dir.mkdir(parents=True, exist_ok=False)
    contract_path = freeze_dir / 'executed_contract.json'
    contract_path.write_text(json.dumps(contract, sort_keys=True, indent=2, allow_nan=False) + '\n')
    (freeze_dir / 'source_inventory.json').write_text(
        json.dumps(inventory, sort_keys=True, indent=2, allow_nan=False) + '\n'
    )
    (freeze_dir / 'execution_freeze.json').write_text(json.dumps({
        'schema_version': 'r03c-execution-freeze-v1',
        'input_head': snapshot['core_head'], 'branch': snapshot['branch'],
        'prompt_sha256': sha(args.prompt), 'snapshot_sha256': sha(args.snapshot),
        'code_sha256': code_hashes,
        'executed_contract_sha256': sha(contract_path),
        'executed_contract_identity_sha256': canonical_sha(contract),
        'source_inventory_sha256': sha(freeze_dir / 'source_inventory.json'),
        'retry_provenance_identity_sha256': canonical_sha(retry_provenance),
        'native_imports': 0, 'native_starts': 0, 'provider_compile_calls': 0,
        'candidate_count': len(rows),
    }, sort_keys=True, indent=2, allow_nan=False) + '\n')
    print(json.dumps({
        'status': 'PROVIDER_FREE_EXECUTION_FREEZE_READY',
        'candidate_count': len(rows), 'source_closure_bytes': inventory['derived_source_closure_bytes'],
        'source_closure_sha256': inventory['derived_source_closure_sha256'],
        'scene_identity_sha256': rows[0]['scene_identity_sha256'],
        'attachment_plan_identity_sha256': rows[0]['attachment_plan_identity_sha256'],
        'native_imports': 0,
    }, sort_keys=True))


if __name__ == '__main__':
    main()
