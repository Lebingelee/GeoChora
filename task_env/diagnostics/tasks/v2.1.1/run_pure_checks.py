"""Run curated pure/fake or explicit offline-H5 nodes under fresh guards.

No arbitrary pytest arguments are accepted: resource-bearing checks have their
own opt-in commands and budgets. This is a thin launcher for existing pytest.
"""
from pathlib import Path
import os
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NODES = (
    'task_env/diagnostics/tasks/v2.1.1/test_position_publication.py',
    'task_env/diagnostics/tasks/v2.1.1/test_public_scalar_example.py',
    'task_env/diagnostics/tasks/v2.1.1/test_pickcube_close_readiness.py',
    'task_env/diagnostics/tasks/v2.1.1/test_solution_compatibility.py::test_pickcube_position_and_physical_readiness_share_measured_boundary',
    'task_env/diagnostics/tasks/v2.1.1/test_solution_compatibility.py::test_solution_observation_commits_once_and_preserves_report_policy',
    'task_env/diagnostics/tasks/v2.1.1/test_solution_compatibility.py::test_solution_observation_failure_does_not_publish_completion',
    'task_env/diagnostics/tasks/v2.1.1/test_frame_mounted_task_camera.py',
    'task_env/diagnostics/tasks/v2.1.1/test_document_history_refs.py',
    'task_env/diagnostics/tasks/v2.1.1/test_pickcube_clock.py',
    'task_env/diagnostics/tasks/v2.1.1/test_reporter_ownership.py',
    'task_env/diagnostics/phase1/integration/test_solution_lifecycle.py::test_on_task_success_completes_immediately',
    'task_env/diagnostics/phase1/integration/test_solution_lifecycle.py::test_task_failure_after_success_is_not_overridden',
    'task_env/diagnostics/phase1/integration/test_solution_lifecycle.py::test_snapshot_restore_continues_deterministically',
    'task_env/diagnostics/phase1/integration/test_solution_lifecycle.py::test_snapshot_restore_fails_closed_for_missing_or_incompatible_state',
    'bench_deploy/libero/diagnostics/test_controller_policy.py',
    'bench_deploy/libero/diagnostics/test_replay_contract.py',
    'task_env/diagnostics/tasks/v2.1.1/test_learner_boundaries.py',
    'task_env/diagnostics/tasks/v2.1.1/test_batch_boundaries.py',
    'task_env/diagnostics/tasks/v2.1.1/test_completion_projections.py',
    'task_env/diagnostics/tasks/v2.1.1/test_script_backend_selection.py',
    'task_env/diagnostics/tasks/v2.1.1/test_public_isaac_example.py',
    'task_env/diagnostics/tasks/v2.1.1/test_formal_configuration.py::test_config_resolution_does_not_open_assets_or_import_native_sdks',
    'task_env/diagnostics/tasks/v2.1.1/test_control_lifecycle.py',
    'task_env/diagnostics/tasks/v2.1.1/test_episode_import.py',
    'task_env/diagnostics/tasks/v2.1.1/test_reset_reconstruction.py',
    'task_env/diagnostics/tasks/v2.1.1/test_isaac_effort_admission.py::test_isaac_position_input_dispatch_requires_exact_formal_type_and_schema',
    'task_env/diagnostics/tasks/v2.1.1/test_physical_control_contract.py',
    'task_env/diagnostics/tasks/v2.1.1/test_effort_servo.py',
    'task_env/diagnostics/tasks/v2.1.1/test_task_rgb_source_routing.py',
    'task_env/diagnostics/tasks/v2.1.1/test_controlled_subject_declarations.py',
    'task_env/diagnostics/tasks/v2.1.1/test_free_joint_state.py',
    'task_env/diagnostics/tasks/v2.1.1/test_mjcf_light_com.py',
    'task_env/diagnostics/tasks/v2.1.1/test_observation_owners.py',
    'task_env/diagnostics/tasks/v2.1.1/test_position_outputs.py',
    'task_env/diagnostics/tasks/v2.1.1/test_geophys_public_bootstrap.py',
    'task_env/diagnostics/tasks/v2.1.1/test_task_ownership.py::test_native_interval_common_contract_checks_identity_and_measured_time',
    'task_env/diagnostics/tasks/v2.1.1/test_task_ownership.py::test_shared_guard_dwell_gap_restore_and_priority_without_task_import',
    'task_env/diagnostics/tasks/v2.1.1/test_task_ownership.py::test_nut_guard_keeps_actuator_and_two_millisecond_policy_at_task_boundary',
    'task_env/diagnostics/tasks/v2.1.1/test_task_ownership.py::test_nut_solution_factory_releases_its_temporary_source',
    'task_env/diagnostics/tasks/v2.1.1/test_worker_resources.py',
    'task_env/diagnostics/tasks/v2.1.1/test_renderer_capabilities.py',
    'task_env/diagnostics/tasks/v2.1.1/test_task_rgb.py',
    'task_env/diagnostics/tasks/v2.1.1/test_recording_preflight.py',
    'task_env/diagnostics/tasks/v2.1.1/test_recording_observation_metadata.py::test_v3_preserves_declared_units_frame_and_clock_without_changing_v2',
    'task_env/diagnostics/tasks/v2.1.1/test_recording_observation_metadata.py::test_physical_metadata_preserves_declared_pose_semantic',
    'task_env/diagnostics/tasks/v2.1.1/test_solution_compatibility.py::test_solution_proposal_is_projected_once_and_remains_caller_owned',
    'task_env/diagnostics/tasks/v2.1.1/test_solution_compatibility.py::test_proposal_subclass_policy_is_explicit_and_independent_of_error_phase',
    'task_env/diagnostics/tasks/v2.1.1/test_solution_compatibility.py::test_bad_solution_proposal_faults_after_act_and_preserves_abort_error',
    'task_env/diagnostics/tasks/v2.1.1/test_solution_compatibility.py::test_nut_solution_accepts_public_schema_but_still_rejects_nonfinite_info',
)
OFFLINE_H5 = (
    'task_env/diagnostics/tasks/v2.1.1/test_legacy_leaf_codec.py',
)
OFFLINE_PHYSICAL = (
    'task_env/diagnostics/tasks/v2.1.1/test_physical_recording_readback.py',
    'task_env/diagnostics/tasks/v2.1.1/test_recording_observation_metadata.py::test_formal_pendulum_record_keeps_published_observation_metadata',
)
_CHILD = r'''
import builtins
import io
import os
import subprocess
import sys
import sitecustomize
if not sitecustomize.READY:
    raise RuntimeError('pure-check guard did not start')
subprocess.run([sys.executable, '-B', '-c',
                "import sitecustomize\nif not sitecustomize.READY: raise RuntimeError('guard missing')"],
               check=True)
try:
    __import__('mujoco')
except RuntimeError as exc:
    if 'blocked native import' not in str(exc):
        raise
else:
    raise AssertionError('native import guard failed')
for root in sitecustomize._ROOTS:
    for opener, args in ((builtins.open, ('rb',)), (io.open, ('rb',)),
                         (os.open, (os.O_RDONLY,))):
        try:
            opener(root / 'pure-guard-canary', *args)
        except RuntimeError as exc:
            if 'blocked asset access' not in str(exc):
                raise
        else:
            raise AssertionError('asset access guard failed')
import pytest
raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider', *%r]))
'''


def main():
    if len(sys.argv) == 1:
        nodes = NODES
    elif sys.argv[1:] == ['--offline-h5']:
        nodes = OFFLINE_H5
    elif sys.argv[1:] == ['--offline-physical']:
        directory = os.environ.get('TASK_ENV_PHYSICAL_RECORDINGS')
        metadata = os.environ.get('TASK_ENV_METADATA_RECORD')
        if not directory or not metadata:
            raise SystemExit('offline physical checks require TASK_ENV_PHYSICAL_RECORDINGS and TASK_ENV_METADATA_RECORD')
        directory, metadata = Path(directory).expanduser().resolve(), Path(metadata).expanduser().resolve()
        required = [directory / name / 'episode.h5'
                    for name in ('pendulum-rgb', 'two-wheel', 'panda-rgb')]
        required.append(metadata)
        if not all(path.is_file() for path in required):
            raise SystemExit('offline physical checks require all four explicit H5 files')
        nodes = OFFLINE_PHYSICAL
    else:
        raise SystemExit('Only --offline-h5 or --offline-physical is accepted; use explicit opt-in commands for source/native checks.')
    env = os.environ.copy()
    env.pop('PYTHONOPTIMIZE', None)
    if nodes is OFFLINE_PHYSICAL:
        env['TASK_ENV_PHYSICAL_RECORDINGS'] = str(directory)
        env['TASK_ENV_METADATA_RECORD'] = str(metadata)
    usd_root = env.get('GEOCHORA_USD_ASSET_ROOT') or str(Path.home() / '.cache/geochora/usd')
    env['GEOCHORA_PURE_GUARD_ROOTS'] = os.pathsep.join((str(ROOT / 'asset'), usd_root))
    env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = os.pathsep.join((str(HERE / 'pure_guard'), str(ROOT)))
    return subprocess.run([sys.executable, '-B', '-c', _CHILD % (list(nodes),)],
                          cwd=ROOT, env=env, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
