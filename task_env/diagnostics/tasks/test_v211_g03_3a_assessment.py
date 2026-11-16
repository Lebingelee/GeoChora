"""Request-bound offline assessment of actual selected declarations."""
from dataclasses import replace
import sys

import pytest

from task_env import make_env
from task_env.artifacts import CapabilityClaim, RequiredCapabilitySet, RendererSelectionV1
from task_env.runtime.sessions.api import assess_selected_request, provider_manifest
from task_env.runtime.sessions.provenance import probe_interpreter_environment, assess_declared_dependencies


@pytest.fixture(scope='module')
def selected():
    from task_env.diagnostics.tasks.original_panda_test_source import install_legacy_original_source
    with pytest.MonkeyPatch.context() as patch:
        install_legacy_original_source(patch)
        env = make_env('pick-cube-p16-reference-v1', config={'provider': 'mujoco'})
        try:
            facts = probe_interpreter_environment(sys.executable)
            dependency = assess_declared_dependencies('mujoco', facts)
            assert dependency['status'] == 'available'
            yield env, dependency['status']
            env.value['source'].execution_source_receipt.validate_snapshot()
        finally:
            env.close()


def _assess(env, dependency, *, artifact=None, source=None, value=None, selection=None, manifest=None):
    return assess_selected_request(
        selection=selection or env.resolved_public_config.execution_spec_v2,
        artifact=artifact or env.artifact, source=source or env.value['source'],
        value=value or env.value, binding=env.binding, dependency_status=dependency,
        request_identity=env.get_execution_receipt()['request_identity'], caller_manifest=manifest,
    )


def test_real_task_closure_is_bound_and_does_not_infer_provider_evidence(selected):
    env, dependency = selected
    assessment = _assess(env, dependency)
    assert assessment.decision == 'pending_native_build'
    closure = next(row for row in assessment.rows if row.capability_id == 'source_closure')
    assert closure.requirement_status == 'satisfied'
    assert env.value['source'].execution_source_receipt is not None
    assert assessment.request_identity == env.get_execution_receipt()['request_identity']
    assert all(row.evidence == 'none' for row in assessment.rows)
    assert any(row.provider_api == 'supported' for row in assessment.rows)
    assert {'source_closure', 'controller_binding', 'scalar_layout', 'state_only_renderer'} <= {
        row.capability_id for row in assessment.rows}
    assert assessment.to_mapping()['rows']


def test_user_manifest_cannot_expand_adapter_or_override_required_source(selected):
    env, dependency = selected
    manifest = provider_manifest('mujoco')
    expanded = replace(manifest, capabilities=(*manifest.capabilities,
                        CapabilityClaim('joint_torque_actuation', 'tested', 'synthetic-only')))
    artifact = replace(env.artifact, required_capabilities=RequiredCapabilitySet(
        (*env.artifact.required_capabilities.names, 'joint_torque_actuation')))
    # Keep the actual source binding unchanged: a changed Artifact is foreign
    # to it, and the assessor must reject that mismatch independently of the
    # caller's expanded manifest.
    source = env.value['source']
    value = {**env.value, 'artifact': artifact, 'source': source}
    assessment = _assess(env, dependency, artifact=artifact, source=source, value=value, manifest=expanded)
    torque = next(row for row in assessment.rows if row.capability_id == 'joint_torque_actuation')
    assert torque.provider_api == 'unknown' and torque.core_adapter == 'not_implemented'
    assert assessment.decision == 'rejected'
    controller = next(row for row in assessment.rows if row.capability_id == 'controller_binding')
    assert controller.requirement_status == 'unsatisfied'


def test_manifest_restriction_and_missing_source_names_are_independent(selected):
    env, dependency = selected
    manifest = provider_manifest('mujoco')
    restricted = replace(manifest, capabilities=tuple(
        item for item in manifest.capabilities if item.name != 'frame_pose_query'))
    assessment = _assess(env, dependency, manifest=restricted)
    row = next(r for r in assessment.rows if r.capability_id == 'frame_pose_query')
    assert row.core_adapter == 'implemented' and row.caller_restriction == 'denied'
    assert assessment.decision == 'rejected'
    # RuntimeSource now rejects this malformed mapping at construction.  A
    # copied and deliberately corrupted object exercises the assessor's own
    # defensive check without weakening the constructor contract.
    from copy import copy
    source = copy(env.value['source'])
    object.__setattr__(source, 'joints', {})
    value = {**env.value, 'source': source}
    assessment = _assess(env, dependency, source=source, value=value)
    assert next(r for r in assessment.rows if r.capability_id == 'source_closure').requirement_status == 'unsatisfied'
    assert assessment.decision == 'rejected'


def test_batch_renderer_and_unknown_required_do_not_gain_admission(selected):
    from task_env.artifacts import CapabilityAssessmentV1
    env, dependency = selected
    original = env.resolved_public_config.execution_spec_v2
    selection = replace(original, batch_layout='native_batch', render_default=RendererSelectionV1(
        'renderer-selection-v1', 'mujoco', 'cpu', 'offscreen', 'cpu'))
    assessment = _assess(env, dependency, selection=selection)
    assert assessment.decision == 'rejected'
    assert {r.capability_id for r in assessment.rows if r.requirement_status == 'unsatisfied'} >= {
        'scalar_layout', 'state_only_renderer'}
    sample = next(r for r in _assess(env, dependency).rows if r.requirement_status == 'unknown')
    no_oracle = replace(sample, build_oracle=None)
    unknown = CapabilityAssessmentV1('capability-assessment-v1', 'a' * 64, 'static_preflight', (no_oracle,))
    assert unknown.decision == 'rejected'
    optional = CapabilityAssessmentV1('capability-assessment-v1', 'a' * 64, 'static_preflight',
                                      (replace(no_oracle, requiredness='optional'),))
    assert optional.decision == 'static_admitted'
    after_build = CapabilityAssessmentV1('capability-assessment-v1', 'a' * 64, 'native_build',
                                         (replace(sample, phase='native_build'),))
    assert after_build.decision == 'rejected'
