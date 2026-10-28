"""Provider-free readback and tamper audit of closed R03c Generic H5 files."""
from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path
import sys

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_001'
WRITERS = ('panda-arm/arm-position-leaf', 'panda-hand/hand-position-leaf')
HOME = np.asarray((0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853), dtype=np.float64)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rotation_error(left, right):
    left, right = np.asarray(left, dtype=np.float64), np.asarray(right, dtype=np.float64)
    left /= np.linalg.norm(left)
    right /= np.linalg.norm(right)
    return float(2.0 * np.arccos(np.clip(abs(np.dot(left, right)), 0.0, 1.0)))


def _native_dir(output_dir: Path) -> Path:
    candidates = [path for path in output_dir.glob('native_attempt_*')
                  if path.is_dir() and (path / 'executed_contract.json').exists()
                  and any(path.glob('E?.h5'))]
    if candidates:
        return max(candidates, key=lambda path: int(path.name.rsplit('_', 1)[1]))
    return output_dir / 'native'


def run(output_dir: Path):
    output_dir = output_dir.resolve()
    native_dir = _native_dir(output_dir)
    result_path = native_dir / 'native_result.json'
    result = json.loads(result_path.read_text()) if result_path.exists() else None
    contract = json.loads((native_dir / 'executed_contract.json').read_text())
    original_import = builtins.__import__

    def block_provider(name, *args, **kwargs):
        if name.split('.', 1)[0] in {'mujoco', 'taichi'}:
            raise AssertionError(f'offline R03c H5 reader imported {name}')
        return original_import(name, *args, **kwargs)

    builtins.__import__ = block_provider
    from task_env.recorders.h5 import load_leaf_control_records_h5
    from task_env.diagnostics.tasks.r03c_attached_leaf_probe import _tamper_checks

    executed_by_id = {item['episode_id']: item for item in contract['episodes']}
    native_by_id = ({item['episode_id']: item for item in result['episodes']}
                    if result is not None else {})
    episode_rows = []
    for path in sorted(native_dir.glob('E?.h5')):
        episode_id = path.stem
        loaded = load_leaf_control_records_h5(path)
        if (loaded['transition_count'], loaded['observation_count']) != (64, 65):
            raise ValueError(f'{episode_id} closed H5 readback is not exactly T=64/T+1=65')
        if tuple(loaded['leaf_writer_ids']) != WRITERS:
            raise ValueError(f'{episode_id} offline reader observed the wrong Entity writers')
        episode_contract = executed_by_id.get(episode_id)
        if episode_contract is None:
            raise ValueError(f'{episode_id} has no frozen execution-contract row')
        profile = loaded['leaf_profile']
        for key, contract_key in (
            ('task_artifact_identity_hash', 'task_artifact_identity_sha256'),
            ('scene_identity_hash', 'scene_identity_sha256'),
            ('assembly_identity_sha256', 'assembly_identity_sha256'),
            ('attachment_plan_identity_sha256', 'attachment_plan_identity_sha256'),
            ('source_closure_digest', 'source_closure_sha256'),
            ('reset_plan_identity_hash', 'reset_plan_identity_sha256'),
            ('effective_leaf_plan_identity_sha256', 'effective_leaf_plan_identity_sha256'),
        ):
            if profile.get(key) != episode_contract[contract_key]:
                raise ValueError(f'{episode_id} offline H5 profile differs from frozen {key}')
        if (profile.get('episode_id') != episode_id
                or profile.get('arm_active') is not episode_contract['arm_active']
                or profile.get('hand_active') is not episode_contract['hand_active']):
            raise ValueError(f'{episode_id} H5 activity/episode metadata differs from the frozen contract')
        native_episode = native_by_id.get(episode_id)
        actual_sha = _sha(path)
        if native_episode is not None and native_episode['sha256'] != actual_sha:
            raise ValueError(f'{episode_id} H5 changed after the native process closed it')

        with h5py.File(path, 'r') as root:
            arm = np.asarray(root['obs/state/entities/panda-arm/joint_position'][...])
            fingers = np.asarray(root['obs/state/entities/panda-hand/joint_position'][...])
            hand_pose = np.asarray(root['obs/state/entities/panda-hand/hand_pose'][...])
        if (arm.shape != (65, 7) or arm.dtype != np.dtype(np.float32)
                or fingers.shape != (65, 2) or fingers.dtype != np.dtype(np.float32)
                or hand_pose.shape != (65, 7) or hand_pose.dtype != np.dtype(np.float32)
                or not np.isfinite(arm).all() or not np.isfinite(fingers).all()
                or not np.isfinite(hand_pose).all()):
            raise ValueError(f'{episode_id} offline H5 arrays violate the R03c dtype/shape/finite contract')
        arm64, fingers64 = arm.astype(np.float64), fingers.astype(np.float64)
        opening = fingers64.sum(axis=1)
        home_error = float(np.max(np.abs(arm64[-1] - HOME)))
        if home_error > 0.02:
            raise ValueError(f'{episode_id} stored Arm final return-home gate failed')
        arm_peak = float(np.max(np.abs(arm64[:, 0] - HOME[0])))
        hand_rotation = float(max(
            _rotation_error(hand_pose[0, 3:7], row[3:7]) for row in hand_pose
        ))
        if episode_contract['arm_active'] and (arm_peak < 0.08 - 1e-6 or hand_rotation < 0.05 - 1e-6):
            raise ValueError(f'{episode_id} stored active Arm motion/root-rotation gate failed')
        closed_min = float(np.min(opening[16:33]))
        hand_final = float(opening[-1])
        hand_excursion = float(np.max(opening) - np.min(opening))
        finger_mismatch = float(np.max(np.abs(fingers64[:, 0] - fingers64[:, 1])))
        if hand_final < 0.06 - 1e-6:
            raise ValueError(f'{episode_id} stored Hand final opening gate failed')
        if episode_contract['hand_active'] and (
                closed_min > 0.02 + 1e-6 or hand_excursion < 0.04 - 1e-6
                or finger_mismatch > 1e-4 + 1e-7):
            raise ValueError(f'{episode_id} stored Hand motion/equality gate failed')
        tamper = _tamper_checks(path, native_dir)
        if len(tamper) != 12 or not all(row['rejected'] for row in tamper):
            raise ValueError(f'{episode_id} offline H5 tamper matrix did not reject all 12 mutations')
        episode_rows.append({
            'episode_id': episode_id, 'path': str(path), 'sha256': actual_sha,
            'bytes': path.stat().st_size, 'transition_count': loaded['transition_count'],
            'observation_count': loaded['observation_count'], 'leaf_writer_ids': list(loaded['leaf_writer_ids']),
            'attachment_receipt_identity_sha256': loaded['attachment_receipt_identity_sha256'],
            'stored_motion': {
                'arm_peak_abs_joint1_rad': arm_peak,
                'arm_return_home_max_abs_rad': home_error,
                'hand_root_rotation_max_rad': hand_rotation,
                'hand_closed_min_opening_m': closed_min,
                'hand_final_opening_m': hand_final,
                'hand_total_excursion_m': hand_excursion,
                'hand_finger_mismatch_max_m': finger_mismatch,
            },
            'tamper_checks': tamper,
        })
    complete = (result is not None and result.get('status') == 'NATIVE_S2_COMPLETE_AWAITING_HOST_OFFLINE_S3'
                and len(episode_rows) == 4
                and {item['episode_id'] for item in episode_rows} == set(executed_by_id))
    output = {
        'schema_version': 'r03c-host-offline-readback-v1',
        'status': ('BOUNDED_ATTACHED_LEAF_PUBLIC_ENV_S2_S3_PASS_PENDING_SOL_REVIEW'
                   if complete else 'OFFLINE_READBACK_INCOMPLETE_OR_FAILED'),
        'input_head': contract['input_head'], 'native_result_present': result is not None,
        'native_process_status': None if result is None else result.get('status'),
        'provider_imports': 0, 'episodes_read': episode_rows,
        'aggregate': {
            'episode_count': len(episode_rows),
            'transition_count': sum(item['transition_count'] for item in episode_rows),
            'observation_count': sum(item['observation_count'] for item in episode_rows),
            'tamper_rejections': sum(len(item['tamper_checks']) for item in episode_rows),
        },
    }
    if {'mujoco', 'taichi'} & set(sys.modules):
        raise AssertionError('offline R03c reader loaded a native provider')
    destination = output_dir / 'offline_readback.json'
    destination.write_text(json.dumps(output, sort_keys=True, indent=2, allow_nan=False) + '\n')
    print(json.dumps({
        'status': output['status'], 'episodes': len(episode_rows),
        'transitions': output['aggregate']['transition_count'],
        'observations': output['aggregate']['observation_count'],
        'tamper_rejections': output['aggregate']['tamper_rejections'],
        'provider_imports': 0,
    }, sort_keys=True))
    return output


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    run(args.output_dir)


if __name__ == '__main__':
    main()
