"""Focused checks for selected candidate context and source-free dependency rejection."""
from dataclasses import replace
import sys

import pytest

from task_env import make_env
from task_env.artifacts import ExecutionSpecV1, RendererSelectionV1
from task_env.environment.configuration import resolve_candidate_execution_selection
from task_env.runtime.sessions.provenance import DeploymentPreflightError, preflight_interpreter_before_source


def test_source_free_preflight_rejects_missing_interpreter_without_fabricating_source():
    env = make_env('pick-cube-p16-reference-v1', config={'provider':'mujoco'})
    try:
        selection = replace(env.resolved_public_config.execution_spec_v2,
                            deployment='isolated_worker', interpreter='/nonexistent/geochora/python')
        with pytest.raises(DeploymentPreflightError) as failure:
            preflight_interpreter_before_source(selection, requested=None, task_uid=env.uid)
        receipt = failure.value.receipt
        assert failure.value.reason == 'environment_probe_failed'
        assert receipt['identity_scope'] == 'selection_only_source_not_evaluated'
        assert receipt['identity_facts']['source_id'] is None
        assert receipt['identity_facts']['artifact_identity'] is None
        assert receipt['assessment'] is None and receipt['status'] == 'rejected'
    finally:
        env.close()


def test_existing_v1_candidate_selection_preserves_declared_execution_identity():
    env = make_env('pick-cube-p16-reference-v1', config={'provider':'mujoco'})
    try:
        renderer = RendererSelectionV1('renderer-selection-v1','none','cpu','none',None)
        execution = ExecutionSpecV1('execution-spec-v1','mujoco','cpu','p1_2_scalar_cpu_v0',
                                    31,'strict',renderer,'cpu',())
        before = execution.identity_hash
        selection = resolve_candidate_execution_selection(provider='mujoco', backend='cpu',
            source=env.value['source'], execution_spec=execution)
        assert execution.identity_hash == before
        assert (selection.physics_provider,selection.physics_backend,selection.physics_device) == ('mujoco','cpu','cpu')
        assert (selection.provider_seed,selection.physics_profile,selection.determinism_mode) == (31,execution.physics_profile,'strict')
        assert selection.interpreter == sys.executable and selection.deployment == 'in_process'
    finally:
        env.close()
