"""Bounded mixed RuntimeSession progress check using a synthetic source fixture.

The historical fixture is used only to construct typed source/sample values;
its retired Env factory is replaced locally. Session materialization, reset,
command admission, advance, progress and close use current runtime owners.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import resource
import traceback

from native_locks import acquire_plan_locks

parser = argparse.ArgumentParser()
parser.add_argument('--provider', choices=('mujoco', 'geophys'), required=True)
parser.add_argument('--plan', required=True)
args = parser.parse_args()
plan = json.loads(Path(args.plan).read_text())
resource.setrlimit(resource.RLIMIT_AS, (plan['rss_address_space_limit_bytes'],) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (120, 125))
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
locks, session, source, owned_receipt = [], None, None, None
result = {'provider': args.provider, 'status': 'FAIL', 'source_kind': 'synthetic_fixture'}
try:
    acquire_plan_locks(plan['locks_in_order'], locks)
    from pytest import MonkeyPatch
    from types import SimpleNamespace
    import task_env.tasks.reference_env as ref
    from task_env.diagnostics.tasks.test_r07c_libero_core_env_s1 import _synthetic_mixed_candidate
    from task_env.artifacts import ExecutionSpec
    from task_env.runtime.sessions import materialize
    from task_env.runtime.sessions.source import source_resource_receipt

    with MonkeyPatch.context() as patch:
        patch.setattr(ref, 'ReferenceTaskBinding', lambda **kw: SimpleNamespace(**kw))
        patch.setattr(ref.SelectedReferenceEnv, 'from_mixed_control_candidate',
                      classmethod(lambda cls, binding, **kw: binding), raising=False)
        binding = _synthetic_mixed_candidate(patch, install_fake_sdk=False)
        value = binding.build_mixed_control_profile('mujoco', 'cpu')
        artifact, source = value['artifact'], value['source']
        sample = binding.reset_sample(artifact, 31)
    from dataclasses import fields, replace
    from task_env.artifacts import RequiredCapabilitySet, ResetSampleV1
    from task_env.assembly.source import TaskSceneSource
    from task_env.runtime.sessions.source import ExecutionSourceReceiptV1
    # The old fixture's two hinges share an axis, making its actual MuJoCo
    # mass matrix singular. Bind a new immutable source with distinct axes.
    old_receipt = source_resource_receipt(source)
    old_xml = source.scene_source.xml
    new_xml = old_xml.replace('name="hinge_cobalt" type="hinge"',
                              'name="hinge_cobalt" type="hinge" axis="0 1 0"')
    if new_xml == old_xml:
        raise ValueError('synthetic hinge correction did not match its source')
    raw = new_xml.encode('utf-8')
    receipt = ExecutionSourceReceiptV1.create(
        source_id=source.scene_source.source_id, canonical_xml=raw, importer_xml=raw,
        closure_files={'canonical-source.xml': raw})
    owned_receipt = receipt
    old_receipt.close()
    if args.provider == 'geophys':
        # The provider explicitly rejects geom-pair contact requests.
        from task_env.environment.types import ReferenceSpec, TaskCompositionSpec
        artifact = replace(artifact, required_capabilities=RequiredCapabilitySet(tuple(
            name for name in artifact.required_capabilities.names if name != 'contact_detection')))
        scene = SimpleNamespace(uid='synthetic-scene-v1', reference_spec=lambda: ReferenceSpec())
        composition = TaskCompositionSpec(artifact.task_id, scene.uid)
    else:
        scene, composition = source.scene, source.composition
    mixed_plan = replace(source.mixed_actuator_plan, task_artifact_hash=artifact.identity_hash,
                         source_closure_digest=receipt.source_closure_digest)
    source = replace(source, task_artifact_hash=artifact.identity_hash,
        scene_source=TaskSceneSource(new_xml, receipt.snapshot_root, source.scene_source.source_id),
        source_closure_digest=receipt.source_closure_digest, execution_source_receipt=receipt,
        mixed_actuator_plan=mixed_plan, scene=scene, composition=composition,
        objects=() if args.provider == 'geophys' else source.objects,
        contact_geom_groups={} if args.provider == 'geophys' else source.contact_geom_groups)
    values = {item.name: getattr(sample, item.name) for item in fields(sample) if item.name != 'sample_id'}
    values.update(task_artifact_hash=artifact.identity_hash, source_closure_digest=receipt.source_closure_digest)
    sample = ResetSampleV1.create(**values)
    value['controller'].plan_identity_hash = mixed_plan.identity_hash
    assert artifact.timebase.control_substeps <= plan['per_run_reserved_physics_substeps']
    execution = ExecutionSpec(args.provider, 'p1_2_scalar_cpu_v0', 'none', 'cpu', 0, 'strict')
    session = materialize(artifact, execution, source=source)
    session.bind_mixed_controller(value['controller'].identity)
    session.reset(sample)
    before = session.runtime_progress_receipt
    state = session.snapshot()
    target = value['controller'].compute_target(
        (.1, -.1, .03), state, task_artifact_hash=artifact.identity_hash,
        source_id=source.scene_source.source_id, source_closure_digest=source.source_closure_digest,
        provider_materialization_id=session.provider_materialization_id, episode_id=session.episode_id,
        reset_sample_id=sample.sample_id, state_revision=session.state_revision)
    ack = session.apply_mixed_actuator_command(target)
    session.step()
    after = session.runtime_progress_receipt
    assert before['control_step'] == 0 and after['control_step'] == 1
    assert after['native_step_count'] - before['native_step_count'] == artifact.timebase.control_substeps
    assert after['simulation_time_episode_s'] > before['simulation_time_episode_s']
    for name in ('provider_materialization_id', 'episode_id', 'reset_sample_id',
                 'source_id', 'source_closure_digest', 'plan_identity_hash'):
        assert before[name] == after[name]
    result.update(status='PASS', before=before, after=after,
                  acknowledgement=ack.to_mapping(), expected_substeps=artifact.timebase.control_substeps)
except BaseException as error:
    result['error'] = {'type': type(error).__name__, 'message': str(error)}
    traceback.print_exc()
finally:
    if session is not None:
        try:
            session.close()
            result['close_completed'] = True
        except BaseException as error:
            result['status'] = 'FAIL'
            result['close_error'] = repr(error)
    if source is not None:
        try:
            source_resource_receipt(source).close()
            result['source_close_completed'] = True
        except BaseException as error:
            result['status'] = 'FAIL'
            result['source_close_error'] = repr(error)
    if owned_receipt is not None:
        try:
            owned_receipt.close()
        except BaseException as error:
            result['status'] = 'FAIL'
            result['owned_receipt_close_error'] = repr(error)
    for handle in reversed(locks):
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()
    result['locks_released'] = True
    Path('result.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'provider': args.provider, 'status': result['status']}))
raise SystemExit(0 if result['status'] == 'PASS' else 1)
