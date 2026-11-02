#!/usr/bin/env python3
"""One bounded normal-profile R05b S2 run and production-reader verification."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
import traceback

from task_env.diagnostics.tasks.c05c_geophys_gripper_cadence import validate_h5
from task_env.runtime.sessions.provenance import (
    provider_build_identity,
    provider_module_origins,
)
from task_env.tasks.nut_assembly.task import (
    NutAssemblyReferenceEnv,
    R05B_NATIVE_FEEDBACK_PROFILE,
    build_native_feedback_solution,
)
from task_env.trajectory.canonical.execution import load


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def run(backend: str, output_dir: Path, *, gripper_hz: int = 500, full_episode: bool = False):
    if full_episode:
        from task_env.diagnostics.tasks.c05c_geophys_gripper_cadence import run_group
        return run_group(backend, gripper_hz, output_dir, profile='normal')
    output_dir.mkdir(parents=True, exist_ok=False)
    result_path = output_dir / 'result.json'
    h5_path = output_dir / 'r05b-two-interval.h5'
    result = {
        'schema': 'r05b-native-feedback-s2-run-v1',
        'profile': R05B_NATIVE_FEEDBACK_PROFILE,
        'backend': backend,
        'law_hz': 500,
        'outer_hz': 100,
        'physics_dt_s': 0.002,
        'native_steps_per_outer': 5,
        'target_outer_intervals': 2,
        'target_native_steps': 10,
        'status': 'not_started',
        'h5_path': str(h5_path),
    }
    env = None
    start = time.monotonic()
    try:
        result['phase'] = 'construct_and_reset'
        env = NutAssemblyReferenceEnv.for_native_feedback_profile(
            backend=backend, gripper_control_hz=500, horizon=6000,
        )
        solution = build_native_feedback_solution(backend=backend, gripper_control_hz=500)
        _, reset_info = env.reset_for_solution(solution, seed=19)
        boundary = reset_info['expert_execution_boundary_v1']
        source = env.value['source']
        receipt = source.execution_source_receipt
        provider = provider_build_identity('geophys')
        module_origins = provider_module_origins('geophys')
        provider_source_root = (Path(__file__).resolve().parents[3] / 'GeoPhys' / 'src').resolve()
        if set(module_origins) != {'control', 'geophys', 'scene', 'simulation', 'solvers'} or any(
            provider_source_root not in Path(origin).parents for origin in module_origins.values()
        ):
            raise RuntimeError('worker resolved a GeoPhys peer module outside the integration provider source root')
        if (provider['repository_revision'] !=
                '67da1165149486d3ae3e779c13ce31af49e17d50'
                or provider['dirty_build_sha256'] is not None):
            raise RuntimeError('worker resolved an unexpected or dirty GeoPhys build')
        if env.execution.backend != backend or source.config.runtime.backend != backend:
            raise RuntimeError('requested backend differs from the selected execution profile')
        result.update({
            'provider_build_identity': provider,
            'provider_module_origins': module_origins,
            'artifact_identity': env.artifact.identity_hash,
            'source_id': source.scene_source.source_id,
            'source_xml_sha256': receipt.canonical_xml_sha256,
            'execution_source_receipt': receipt.to_mapping(),
            'source_closure_digest': receipt.source_closure_digest,
            'controller_identity': env.controller.identity,
            'solution_identity': solution.identity,
            'episode_id': boundary['episode_id'],
            'reset_sample_id': boundary['reset_sample_id'],
            'provider_materialization_id': boundary['provider_materialization_id'],
            'reset_boundary_identity': boundary['identity_hash'],
            'reset_clock': {
                'control_step': int(env.state.control_step),
                'simulation_time_s': float(env.state.simulation_time),
            },
            'profile_identity': env._native_feedback_profile,
            'diagnostic_profile': env._diagnostic_profile,
        })

        result['phase'] = 'two_outer_intervals_and_recording'
        env.start_recording(h5_path)
        per_interval_wall = []
        for interval in range(2):
            before = time.monotonic()
            _, _, terminated, truncated, _ = env.step_with_solution(solution)
            per_interval_wall.append(time.monotonic() - before)
            if terminated or truncated:
                raise RuntimeError(f'task lifecycle ended before bounded interval {interval + 1}')
        if (env.state.control_step != 2
                or abs(float(env.state.simulation_time) - 0.02) > 1e-10):
            raise RuntimeError('two-interval S2 clock is not exactly 2/0.02s')
        finish = env.finish_recording('r05b-two-interval-s2-complete')
        if not h5_path.is_file() or h5_path.stat().st_size > 64 * 1024 * 1024:
            raise RuntimeError('same-run H5 is missing or exceeds the 64 MiB output limit')

        result['phase'] = 'production_reader'
        value = load(h5_path)
        expected = {
            'backend': backend,
            'gripper_control_hz': 500,
            'artifact_identity': result['artifact_identity'],
            'source_id': result['source_id'],
            'source_xml_sha256': result['source_xml_sha256'],
            'controller_identity': result['controller_identity'],
            'solution_identity': result['solution_identity'],
            'episode_id': result['episode_id'],
            'reset_sample_id': result['reset_sample_id'],
            'provider_materialization_id': result['provider_materialization_id'],
            'request_boundary_id': result['reset_boundary_identity'],
        }
        readback = validate_h5(value, expected)
        if readback['transition_count'] != 2 or readback['native_sample_count'] != 10:
            raise RuntimeError('production reader did not validate two transitions and ten native samples')
        provenance = value['metadata']['source_provenance']
        recorded = json.loads(provenance['runtime_execution_source_receipt_json'])
        if recorded != receipt.to_mapping():
            raise RuntimeError('same-run H5 source receipt differs from the materialized source')
        result.update({
            'status': 'passed',
            'phase': 'complete',
            'completed_outer_intervals': 2,
            'completed_native_steps': 10,
            'end_clock': {
                'control_step': int(env.state.control_step),
                'simulation_time_s': float(env.state.simulation_time),
            },
            'reader': readback,
            'recorder_finish': finish,
            'h5_size_bytes': h5_path.stat().st_size,
            'h5_sha256': _sha(h5_path.read_bytes()),
            'interval_wall_s': per_interval_wall,
            'wall_seconds': time.monotonic() - start,
            'native_steps_per_outer': 5,
            'task_completion_claim': False,
        })
    except BaseException as error:
        result.update({
            'status': 'failed_or_blocked',
            'error': f'{type(error).__name__}: {error}',
            'traceback': traceback.format_exc(),
            'wall_seconds': time.monotonic() - start,
        })
    finally:
        if env is not None:
            try:
                env.close()
                result['close_success'] = True
            except BaseException as error:
                result['close_success'] = False
                result['close_error'] = f'{type(error).__name__}: {error}'
                result['status'] = 'failed_or_blocked'
        result['wall_seconds'] = time.monotonic() - start
        result_path.write_text(
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n',
            encoding='utf-8',
        )
    print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', choices=('cpu', 'cuda'), required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--gripper-hz', type=int, choices=(100, 500), default=500)
    parser.add_argument('--full-episode', action='store_true')
    args = parser.parse_args()
    result = run(args.backend, args.output_dir, gripper_hz=args.gripper_hz,
                 full_episode=args.full_episode)
    if result['status'] != 'passed' or result.get('close_success') is not True:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
