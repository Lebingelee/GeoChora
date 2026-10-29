"""Provider-free gates for the one R06b deterministic order derivative."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from task_env.artifacts import ArticulationDefinition, ExecutionSpec, SceneDefinition
from task_env.assembly.fixed_attachment import (
    R06B_ORDER_RECIPE_ID, R06B_ORDER_SOURCE_SHA256,
    _validate_source_declarations, fixed_attachment_source_recipe,
)
from task_env.runtime.sessions.api import _validate_fixed_attachment_materialization_source
from task_env.runtime.sessions.mujoco import _MuJoCoSession
from task_env.tasks.position_candidate.fixed_attachment_candidate import (
    ARM_SHA256, HAND_SHA256, build_fixed_attachment_candidate,
)
from task_env.tasks.position_candidate.attached_leaf_candidate import build_attached_leaf_candidate
from task_env.tasks.reference_env import SelectedReferenceEnv


def _execution():
    return ExecutionSpec('mujoco', 'p1_2_scalar_cpu_v0', 'none', 'cpu', 31, 'strict')


def _model_for(candidate):
    variant = candidate.attachment_plan.parent_asset_version == 'menagerie-b846dd12-r06b-order-v1'
    body_order = [
        'world', 'link0', 'link1', 'link2', 'link3', 'link4', 'link5', 'link6',
        'link7', 'attachment', 'probe_hand_hand',
        *(('probe_hand_right_finger', 'probe_hand_left_finger') if variant else
          ('probe_hand_left_finger', 'probe_hand_right_finger')),
    ]
    joint_order = [*(f'joint{i}' for i in range(1, 8)),
                   *(('probe_hand_finger_joint2', 'probe_hand_finger_joint1') if variant else
                     ('probe_hand_finger_joint1', 'probe_hand_finger_joint2'))]
    actuator_order = [*(f'actuator{i}' for i in (range(7, 0, -1) if variant else range(1, 8))),
                      'probe_hand_actuator8']
    tendon_order = ['probe_hand_split']
    site_order = ['attachment_site']
    geom_order = [f'geom{index}' for index in range(81)]
    ids = {
        'body': {name: index for index, name in enumerate(body_order)},
        'joint': {name: index for index, name in enumerate(joint_order)},
        'actuator': {name: index for index, name in enumerate(actuator_order)},
        'tendon': {name: index for index, name in enumerate(tendon_order)},
        'site': {name: index for index, name in enumerate(site_order)},
        'geom': {name: index for index, name in enumerate(geom_order)},
    }
    names = {'body': body_order, 'joint': joint_order, 'actuator': actuator_order,
             'tendon': tendon_order, 'site': site_order, 'geom': geom_order}
    parents = {'world': 'world', 'link0': 'world',
               **{f'link{i}': f'link{i-1}' for i in range(1, 8)},
               'attachment': 'link7', 'probe_hand_hand': 'attachment',
               'probe_hand_left_finger': 'probe_hand_hand',
               'probe_hand_right_finger': 'probe_hand_hand'}
    parent_ids = [0 if name == 'world' else ids['body'][parents[name]] for name in body_order]
    child_body = {f'joint{i}': f'link{i}' for i in range(1, 8)}
    child_body.update({'probe_hand_finger_joint1': 'probe_hand_left_finger',
                       'probe_hand_finger_joint2': 'probe_hand_right_finger'})
    joint_limits = {
        'joint1': (-2.8973, 2.8973), 'joint2': (-1.7628, 1.7628),
        'joint3': (-2.8973, 2.8973), 'joint4': (-3.0718, -0.0698),
        'joint5': (-2.8973, 2.8973), 'joint6': (-0.0175, 3.7525),
        'joint7': (-2.8973, 2.8973),
        'probe_hand_finger_joint1': (0.0, 0.04), 'probe_hand_finger_joint2': (0.0, 0.04),
    }
    actuator_limits = {
        'actuator1': (-2.8973, 2.8973), 'actuator2': (-1.7628, 1.7628),
        'actuator3': (-2.8973, 2.8973), 'actuator4': (-3.0718, -0.0698),
        'actuator5': (-2.8973, 2.8973), 'actuator6': (-0.0175, 3.7525),
        'actuator7': (-2.8973, 2.8973), 'probe_hand_actuator8': (0.0, 255.0),
    }
    joint_type = [2 if name.startswith('probe_hand_') else 3 for name in joint_order]
    actuator_trnid = [[ids['joint'][name.replace('actuator', 'joint')], -1]
                      if name != 'probe_hand_actuator8' else [0, -1] for name in actuator_order]
    exclusions = [('link0', 'link1'), ('probe_hand_hand', 'probe_hand_left_finger'),
                  ('probe_hand_hand', 'probe_hand_right_finger')]
    model = SimpleNamespace(
        nq=9, nv=9, nu=8, njnt=9, nbody=13, nsite=1, nmesh=67, ngeom=81,
        neq=1, ntendon=1, nexclude=3,
        body_parentid=np.asarray(parent_ids),
        jnt_type=np.asarray(joint_type), jnt_limited=np.ones(9, dtype=bool),
        jnt_range=np.asarray([joint_limits[name] for name in joint_order]),
        jnt_bodyid=np.asarray([ids['body'][child_body[name]] for name in joint_order]),
        jnt_axis=np.tile((0.0, 0.0, 1.0), (9, 1)),
        jnt_qposadr=np.arange(9), jnt_dofadr=np.arange(9),
        site_bodyid=np.asarray([ids['body']['attachment']]),
        geom_bodyid=np.asarray([ids['body'][body_order[1 + index % 12]] for index in range(81)]),
        actuator_ctrllimited=np.ones(8, dtype=bool),
        actuator_ctrlrange=np.asarray([actuator_limits[name] for name in actuator_order]),
        actuator_forcelimited=np.zeros(8, dtype=bool), actuator_forcerange=np.zeros((8, 2)),
        actuator_trnid=np.asarray(actuator_trnid),
        actuator_trntype=np.asarray([3 if name == 'probe_hand_actuator8' else 0
                                     for name in actuator_order]),
        tendon_adr=np.asarray([0]), tendon_num=np.asarray([2]),
        wrap_type=np.asarray([1, 1]),
        wrap_objid=np.asarray([ids['joint']['probe_hand_finger_joint1'],
                               ids['joint']['probe_hand_finger_joint2']]),
        wrap_prm=np.asarray([0.5, 0.5]),
        eq_type=np.asarray([2]),
        eq_obj1id=np.asarray([ids['joint']['probe_hand_finger_joint1']]),
        eq_obj2id=np.asarray([ids['joint']['probe_hand_finger_joint2']]),
        exclude_signature=np.asarray([(ids['body'][left] << 16) | ids['body'][right]
                                      for left, right in exclusions]),
        geom_contype=np.ones(81, dtype=int), geom_conaffinity=np.ones(81, dtype=int),
    )
    mj = SimpleNamespace(
        mjtJoint=SimpleNamespace(mjJNT_FREE=0, mjJNT_HINGE=3, mjJNT_SLIDE=2),
        mjtObj=SimpleNamespace(mjOBJ_BODY='body', mjOBJ_JOINT='joint',
                               mjOBJ_ACTUATOR='actuator', mjOBJ_SITE='site',
        mjOBJ_TENDON='tendon', mjOBJ_GEOM='geom'),
        mjtTrn=SimpleNamespace(mjTRN_JOINT=0, mjTRN_TENDON=3),
        mjtWrap=SimpleNamespace(mjWRAP_JOINT=1),
        mjtEq=SimpleNamespace(mjEQ_JOINT=2),
        mj_name2id=lambda _model, kind, name: ids[kind].get(name, -1),
        mj_id2name=lambda _model, kind, index: names[kind][index],
    )
    return model, mj


def test_exact_default_and_one_derived_recipe_are_distinct_and_provider_free():
    baseline = build_fixed_attachment_candidate()
    derived = build_fixed_attachment_candidate(order_variant=True)
    assert baseline.scene.scene_id == 'phase-ii-r03b-fixed-attachment'
    assert baseline.scene.identity_hash == '7981f0bb31875b35eb0973b08c1f65ac09210b55b7e9e0ea45761e4f8a4cfe9a'
    assert baseline.assembly.identity_hash == '232e62b18ea48ab04cc4ec2761a11666c8e1955a599b4f04ff585887d2fe1b4a'
    assert baseline.artifact.identity_hash == '08f6e60c22d00d4db6aff20d2978a571b3332e9c1a8deec3e1fd2c1283379133'
    assert baseline.source_inventory['arm']['sha256'] == ARM_SHA256
    assert baseline.source_inventory['hand']['sha256'] == HAND_SHA256
    assert derived.scene.scene_id != baseline.scene.scene_id
    assert derived.scene.identity_hash != baseline.scene.identity_hash
    assert derived.assembly.identity_hash != baseline.assembly.identity_hash
    assert derived.artifact.identity_hash != baseline.artifact.identity_hash
    assert derived.attachment_plan.identity_hash != baseline.attachment_plan.identity_hash
    assert derived.reset_plan.identity_hash != baseline.reset_plan.identity_hash
    assert fixed_attachment_source_recipe(
        derived.runtime_source.fixed_attachment_sources['panda-arm'].xml,
        derived.runtime_source.fixed_attachment_sources['panda-hand'].xml,
    ) == R06B_ORDER_RECIPE_ID
    assert derived.source_inventory['arm']['sha256'] == R06B_ORDER_SOURCE_SHA256['panda-arm']
    assert derived.source_inventory['hand']['sha256'] == R06B_ORDER_SOURCE_SHA256['panda-hand']
    hand = next(item for item in derived.scene.articulations if item.entity_id == 'panda-hand')
    assert tuple(joint.joint_id for joint in hand.joints) == ('finger_joint1', 'finger_joint2')
    assert tuple(node.get('name') for node in ET.fromstring(
        derived.runtime_source.fixed_attachment_sources['panda-hand'].xml
    ).find("./worldbody/body[@name='hand']").findall('body')) == ('right_finger', 'left_finger')
    arm_group = next(group for group in derived.scene.control_groups if group.entity_id == 'panda-arm')
    assert tuple(ref.actuator_id for ref in arm_group.actuator_refs) == tuple(
        f'actuator{index}' for index in range(1, 8)
    )
    assert not any(name == 'mujoco' or name.startswith('mujoco.') for name in sys.modules)


def test_exact_baseline_and_derived_sources_pass_core_preflight():
    for variant in (False, True):
        candidate = build_fixed_attachment_candidate(order_variant=variant)
        _validate_fixed_attachment_materialization_source(
            candidate.artifact, _execution(), candidate.runtime_source,
        )


def test_articulation_v1_reverse_joint_input_preserves_canonical_mapping_and_scene_identity():
    baseline = build_fixed_attachment_candidate()
    hand = next(item for item in baseline.scene.articulations if item.entity_id == 'panda-hand')
    old_identity = baseline.scene.identity_hash
    assert old_identity == '7981f0bb31875b35eb0973b08c1f65ac09210b55b7e9e0ea45761e4f8a4cfe9a'
    reversed_constructor = ArticulationDefinition.from_mapping({
        **hand.to_mapping(), 'joints': list(reversed(hand.to_mapping()['joints'])),
    })
    assert tuple(joint.joint_id for joint in reversed_constructor.joints) == (
        'finger_joint1', 'finger_joint2',
    )
    assert reversed_constructor.to_mapping() == hand.to_mapping()
    scene_mapping = baseline.scene.to_mapping()
    mapped_hand = next(item for item in scene_mapping['articulations']
                       if item['entity_id'] == 'panda-hand')
    mapped_hand['joints'] = list(reversed(mapped_hand['joints']))
    decoded = SceneDefinition.from_mapping(scene_mapping)
    assert decoded.identity_hash == old_identity
    assert decoded.to_mapping() == baseline.scene.to_mapping()
    assert tuple(joint.joint_id for joint in next(
        item for item in decoded.articulations if item.entity_id == 'panda-hand'
    ).joints) == ('finger_joint1', 'finger_joint2')


def test_scene_joint_reverse_is_canonical_equivalent_but_source_recipe_order_stays_strict():
    candidate = build_fixed_attachment_candidate()
    root = ET.fromstring(candidate.runtime_source.fixed_attachment_sources['panda-hand'].xml)
    articulation = next(item for item in candidate.scene.articulations if item.entity_id == 'panda-hand')
    mismatched = replace(candidate.scene, articulations=tuple(
        replace(item, joints=tuple(reversed(item.joints))) if item.entity_id == 'panda-hand' else item
        for item in candidate.scene.articulations
    ))
    assert mismatched.identity_hash == candidate.scene.identity_hash
    _validate_source_declarations(
        root, 'panda-hand', mismatched, HAND_SHA256,
        expected_traversal=('finger_joint1', 'finger_joint2'),
    )
    with pytest.raises(ValueError, match='source traversal'):
        _validate_source_declarations(
            root, 'panda-hand', mismatched, HAND_SHA256,
            expected_traversal=('finger_joint2', 'finger_joint1'),
        )
    derived = build_fixed_attachment_candidate(order_variant=True)
    changed_sources = dict(derived.runtime_source.fixed_attachment_sources)
    changed_sources['panda-hand'] = replace(
        changed_sources['panda-hand'], xml=ET.tostring(root, encoding='unicode'),
    )
    with pytest.raises(ValueError):
        _validate_fixed_attachment_materialization_source(
            derived.artifact, _execution(), replace(
                derived.runtime_source, fixed_attachment_sources=changed_sources,
            ),
        )


@pytest.mark.parametrize('tamper', [
    'axis', 'target', 'gain', 'limit', 'root', 'provenance', 'source_id', 'closure',
])
def test_core_preflight_rejects_nonrecipe_bytes_and_mismatched_bindings(tamper):
    candidate = build_fixed_attachment_candidate(order_variant=True)
    source = candidate.runtime_source
    sources = dict(source.fixed_attachment_sources)
    with pytest.raises((ValueError, TypeError)):
        if tamper == 'axis':
            root = ET.fromstring(sources['panda-hand'].xml)
            root.find(".//joint[@name='finger_joint1']").set('axis', '1 0 0')
            sources['panda-hand'] = replace(
                sources['panda-hand'], xml=ET.tostring(root, encoding='unicode'),
            )
            changed = replace(source, fixed_attachment_sources=sources)
        elif tamper == 'target':
            root = ET.fromstring(sources['panda-arm'].xml)
            root.find("./actuator/*[@name='actuator7']").set('joint', 'joint6')
            sources['panda-arm'] = replace(
                sources['panda-arm'], xml=ET.tostring(root, encoding='unicode'),
            )
            changed = replace(source, fixed_attachment_sources=sources)
        elif tamper in {'gain', 'limit', 'root'}:
            root = ET.fromstring(sources['panda-hand'].xml if tamper != 'gain'
                                 else sources['panda-arm'].xml)
            if tamper == 'gain':
                root.find("./actuator/*[@name='actuator7']").set('gainprm', '2.1 0 0 0 0 0 0 0 0 0')
                entity = 'panda-arm'
            elif tamper == 'limit':
                root.find(".//default[@class='finger']/joint").set('range', '0 0.039')
                entity = 'panda-hand'
            else:
                root.find("./worldbody/body[@name='hand']").set('name', 'hand_altered')
                entity = 'panda-hand'
            sources[entity] = replace(
                sources[entity], xml=ET.tostring(root, encoding='unicode'),
            )
            changed = replace(source, fixed_attachment_sources=sources)
        elif tamper == 'provenance':
            assets = tuple(replace(asset, source_reference='derived:wrong-recipe')
                           if asset.asset_id == 'panda-hand' else asset
                           for asset in source.scene_definition.assets)
            changed_scene = replace(source.scene_definition, assets=assets)
            changed = replace(source, scene_definition=changed_scene, scene=changed_scene)
        elif tamper == 'source_id':
            sources['panda-hand'] = replace(sources['panda-hand'], source_id='fixed-attachment-source-v1:wrong')
            changed = replace(source, fixed_attachment_sources=sources)
        else:
            changed = replace(source, source_closure_digest='0' * 64)
        _validate_fixed_attachment_materialization_source(candidate.artifact, _execution(), changed)


@pytest.mark.parametrize('variant', [False, True])
def test_actual_adapter_order_gate_accepts_only_each_declared_order(variant):
    candidate = build_fixed_attachment_candidate(order_variant=variant)
    model, mj = _model_for(candidate)
    session = object.__new__(_MuJoCoSession)
    session._source, session._model, session._mj = candidate.runtime_source, model, mj
    session._validate_fixed_attachment_scene_model()
    if variant:
        assert [mj.mj_id2name(model, 'actuator', i) for i in range(model.nu)] == [
            *(f'actuator{i}' for i in range(7, 0, -1)), 'probe_hand_actuator8',
        ]
        assert mj.mj_name2id(model, 'actuator', 'actuator1') != 0
    else:
        assert mj.mj_name2id(model, 'actuator', 'actuator1') == 0


@pytest.mark.parametrize('variant', [False, True])
def test_actual_attachment_and_leaf_receipts_resolve_named_native_slots(variant):
    import json

    from task_env.diagnostics.tasks.r06b_order_worker import _assert_receipt

    candidate = build_attached_leaf_candidate(
        environment_type=SelectedReferenceEnv, order_variant=variant,
        episode_id='E2' if variant else 'E1',
    )
    model, mj = _model_for(candidate)
    _validate_fixed_attachment_materialization_source(candidate.artifact, _execution(), candidate.source)
    session = object.__new__(_MuJoCoSession)
    session._initialize_values(candidate.artifact, candidate.source, 'mujoco')
    session._model, session._mj = model, mj
    session._fixed_attachment_runtime_identity = {'package_version': '3.8.1', 'synthetic_model_io': True}
    session._fixed_attachment_provider_build = candidate.provider_build_identity
    session._fixed_attachment_lowering = {'method': 'synthetic model IO; production receipt builder'}
    session._leaf_plan = None
    session._leaf_materialization_receipt = None
    session._leaf_configuration_revision = None
    session._leaf_fault = None
    session._leaf_consumed_boundaries = set()
    session._fixed_attachment_receipt = session._make_fixed_attachment_receipt()
    session._validate_fixed_attachment_scene_model()
    receipt = session.fixed_attachment_receipt
    session.admit_leaf_control_plan(candidate.plan)
    leaf = session.leaf_materialization_receipt
    assert receipt['native_joint_order'][-2:] == (
        ['probe_hand_finger_joint2', 'probe_hand_finger_joint1'] if variant else
        ['probe_hand_finger_joint1', 'probe_hand_finger_joint2']
    )
    slots = {name: row['ctrl_slot'] for name, row in receipt['native_actuator_mappings'].items()}
    assert slots['panda-arm/actuator1'] == (6 if variant else 0)
    assert slots['panda-arm/actuator7'] == (0 if variant else 6)
    assert slots['panda-hand/actuator8'] == 7
    by_joint = {row.canonical_joint.joint_id: row for row in leaf.joints}
    assert by_joint['joint1'].native_joint_id == mj.mj_name2id(model, 'joint', 'joint1')
    assert by_joint['finger_joint1'].qpos_address == mj.mj_name2id(
        model, 'joint', 'probe_hand_finger_joint1',
    )
    expected = {
        'native_body_order': receipt['native_body_order'],
        'native_joint_order': receipt['native_joint_order'],
        'native_actuator_order': receipt['native_actuator_order'],
        'dimensions': {
            'nq': 9, 'nv': 9, 'nu': 8, 'njnt': 9, 'nbody': 13,
            'nsite': 1, 'nmesh': 67, 'ngeom': 81, 'neq': 1,
            'ntendon': 1, 'nexclude': 3,
        },
        'actuator_slots': slots,
    }
    _assert_receipt(candidate, receipt, expected)
    malformed = json.loads(json.dumps(receipt))
    malformed['native_joint_mappings']['panda-arm/joint1']['qpos_address'] += 1
    with pytest.raises(ValueError, match='Joint ID/address map'):
        _assert_receipt(candidate, malformed, expected)


def test_adapter_rejects_a_list_order_mismatch_even_when_names_are_covered():
    candidate = build_fixed_attachment_candidate(order_variant=True)
    model, mj = _model_for(candidate)
    model_names = list(range(model.nu))
    # Rebind the first two compiled names while leaving every named resource present.
    original = ['actuator7', 'actuator6', 'actuator5', 'actuator4', 'actuator3', 'actuator2', 'actuator1',
                'probe_hand_actuator8']
    wrong = original.copy()
    wrong[0], wrong[1] = wrong[1], wrong[0]
    name2id = mj.mj_name2id
    id2name = mj.mj_id2name
    mj.mj_id2name = lambda _m, kind, index: wrong[index] if kind == 'actuator' else id2name(_m, kind, index)
    mj.mj_name2id = lambda _m, kind, name: wrong.index(name) if kind == 'actuator' else name2id(_m, kind, name)
    session = object.__new__(_MuJoCoSession)
    session._source, session._model, session._mj = candidate.runtime_source, model, mj
    with pytest.raises(ValueError, match='Actuator order'):
        session._validate_fixed_attachment_scene_model()


def test_derived_case_public_env_h5_reader_and_close_use_actual_reordered_slots(
        monkeypatch, tmp_path):
    # Reuse the established R03c synthetic-session fixture. It replaces only
    # native model/data IO; public factory, admission, Env reset/dispatch,
    # Recorder, final receipt, H5 loader and close remain production owners.
    from test_phase_ii_01_r03c_attached_leaf import (
        _candidate, _session_with_synthetic_native_io,
    )
    from task_env.recorders.h5 import load_leaf_control_records_h5
    from task_env.runtime.sessions import api
    from task_env.tasks.position_candidate.attached_leaf_candidate import action_for_interval

    candidate = _candidate(monkeypatch, order_variant=True, episode_id='E2')
    session = _session_with_synthetic_native_io(candidate)
    monkeypatch.setattr(api, '_materialize_admitted', lambda *_: session)
    h5_path = tmp_path / 'r06b-derived-E2.h5'
    try:
        _, reset_info = candidate.env.reset(seed=31)
        assert reset_info['reset_sample_id'] == candidate.reset_plan.reset_sample.sample_id
        receipt = session.fixed_attachment_receipt
        assert receipt['native_body_order'][-2:] == [
            'probe_hand_right_finger', 'probe_hand_left_finger',
        ]
        assert receipt['native_joint_order'][-2:] == [
            'probe_hand_finger_joint2', 'probe_hand_finger_joint1',
        ]
        assert receipt['native_actuator_order'][:7] == [
            f'actuator{index}' for index in range(7, 0, -1)
        ]
        assert receipt['native_actuator_mappings']['panda-arm/actuator1']['ctrl_slot'] == 6
        assert receipt['native_actuator_mappings']['panda-arm/actuator7']['ctrl_slot'] == 0
        candidate.env.start_recording(h5_path)
        for interval in range(1, 65):
            _, _, terminated, truncated, _ = candidate.env.step(
                action_for_interval(candidate, interval, arm_active=True, hand_active=True),
            )
            assert terminated is False
            assert truncated is (interval == 64)
        final_receipt = candidate.env.finish_recording('horizon')
        assert final_receipt['transition_count'] == 64
        assert final_receipt['observation_count'] == 65
        loaded = load_leaf_control_records_h5(h5_path)
        assert loaded['transition_count'] == 64
        assert loaded['observation_count'] == 65
        assert loaded['env_meta']['reference_profile']['attachment_receipt']['native_actuator_mappings'][
            'panda-arm/actuator1'
        ]['ctrl_slot'] == 6
    finally:
        candidate.env.close()
    close_evidence = session.fixed_attachment_close_evidence
    assert session._closed is True
    assert close_evidence['session_closed'] is True
    assert close_evidence['native_step_count'] == 320
    assert close_evidence['model_released'] is True
    assert close_evidence['data_released'] is True


def test_independent_raw_reader_accepts_two_cases_and_rejects_frozen_tamper_matrix(
        monkeypatch, tmp_path):
    import hashlib
    import json
    import os
    from pathlib import Path
    import shutil
    import subprocess
    import sys

    import h5py

    from test_phase_ii_01_r03c_attached_leaf import (
        _candidate, _session_with_synthetic_native_io, _write_attached_recording,
    )
    from task_env.runtime.sessions import api
    from task_env.tasks.position_candidate.attached_leaf_candidate import action_for_interval

    output_dir = tmp_path / 'raw-reader-output'
    output_dir.mkdir()
    baseline_fixture = tmp_path / 'baseline-fixture'
    baseline_fixture.mkdir()
    baseline, _baseline_env = _write_attached_recording(monkeypatch, baseline_fixture, episode_id='E1')
    baseline_file = Path(_baseline_env.recording_path)
    baseline_case_dir = output_dir / 'cases' / 'E1'
    baseline_case_dir.mkdir(parents=True)
    shutil.copy2(baseline_file, baseline_case_dir / 'E1.h5')

    derived = _candidate(monkeypatch, order_variant=True, episode_id='E2')
    session = _session_with_synthetic_native_io(derived)
    monkeypatch.setattr(api, '_materialize_admitted', lambda *_: session)
    derived_case_dir = output_dir / 'cases' / 'E2'
    derived_case_dir.mkdir(parents=True)
    derived_file = derived_case_dir / 'E2.h5'
    try:
        derived.env.reset(seed=31)
        derived.env.start_recording(derived_file)
        for interval in range(1, 65):
            derived.env.step(action_for_interval(
                derived, interval, arm_active=True, hand_active=True,
            ))
        derived.env.finish_recording('horizon')
    finally:
        derived.env.close()

    def case_for(candidate, episode_id, h5_path, receipt):
        return {
            'episode_id': episode_id,
            'order_variant': episode_id == 'E2',
            'candidate': {
                'task_source_identity_sha256': candidate.artifact.task_source_identity_hash,
                'task_artifact_identity_sha256': candidate.artifact.identity_hash,
                'scene_identity_sha256': candidate.scene.identity_hash,
                'assembly_identity_sha256': candidate.assembly.logical_content_sha256,
                'attachment_plan_identity_sha256': candidate.attachment_plan.identity_hash,
                'leaf_plan_identity_sha256': candidate.plan.identity_sha256,
                'reset_plan_identity_sha256': candidate.reset_plan.identity_hash,
                'reset_sample_id': candidate.reset_plan.reset_sample.sample_id,
                'source_closure_sha256': candidate.source.source_closure_digest,
            },
            'native_expected': {
                'native_body_order': receipt['native_body_order'],
                'native_joint_order': receipt['native_joint_order'],
                'native_actuator_order': receipt['native_actuator_order'],
                'actuator_slots': {
                    key: row['ctrl_slot']
                    for key, row in receipt['native_actuator_mappings'].items()
                },
            },
        }

    baseline_receipt = baseline.attachment_plan
    # The baseline synthetic recorder fixture uses the production profile
    # receipt generated from the exact default source order.
    from test_phase_ii_01_r03c_attached_leaf import _fixed_receipt
    baseline_receipt = _fixed_receipt(baseline)
    contract = {
        'schema': 'r06b-order-readback-contract-test-v1',
        'input_head': 'synthetic-test-head',
        'output_dir': str(output_dir),
        'cases': [
            case_for(baseline, 'E1', baseline_case_dir / 'E1.h5', baseline_receipt),
            case_for(derived, 'E2', derived_file, session.fixed_attachment_receipt),
        ],
    }
    contract['contract_sha256'] = hashlib.sha256(json.dumps(
        contract, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        allow_nan=False,
    ).encode()).hexdigest()
    contract_path = output_dir / 'contract.json'
    native_dir = output_dir / 'native'
    native_dir.mkdir()
    native_result_path = native_dir / 'native_result.json'
    native_result = {'status': 'R06B_NATIVE_WORKER_PASS_PENDING_READBACK'}

    def worker_case(case, root):
        episode_id = case['episode_id']
        path = root / 'cases' / episode_id / f'{episode_id}.h5'
        source_receipt = baseline_receipt if episode_id == 'E1' else session.fixed_attachment_receipt
        counts = {
            'materialization_attempts': 1, 'materializations_completed': 1,
            'reset_attempts': 1, 'resets_completed': 1, 'outer_intervals': 64,
            'attempted_mj_step_calls': 320, 'mj_step_calls': 320,
            'attempted_mj_forward_calls': 65, 'mj_forward_calls': 65,
        }
        return {
            'episode_id': episode_id,
            'order_variant': case['order_variant'],
            'candidate': case['candidate'],
            'h5': {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                   'bytes': path.stat().st_size, 'transition_count': 64,
                   'observation_count': 65, 'production_reader': 'PASS'},
            'native_receipt': {
                'receipt_identity_sha256': source_receipt['receipt_identity_sha256'],
                'provider_materialization_id': source_receipt['provider_materialization_id'],
                'native_body_order': source_receipt['native_body_order'],
                'native_joint_order': source_receipt['native_joint_order'],
                'native_actuator_order': source_receipt['native_actuator_order'],
                'native_actuator_mappings': source_receipt['native_actuator_mappings'],
            },
            'native_counts': {
                **counts, 'episode_id': episode_id, 'mj_step_calls_case': 320,
                'mj_forward_calls_case': 65, 'simulated_seconds_case': 0.64,
            },
        }

    def publish(root, current_contract):
        current_contract['output_dir'] = str(root)
        current_contract['contract_sha256'] = hashlib.sha256(json.dumps(
            {key: value for key, value in current_contract.items() if key != 'contract_sha256'},
            sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
        ).encode()).hexdigest()
        contract_file = root / 'contract.json'
        contract_file.write_text(json.dumps(current_contract, sort_keys=True, indent=2) + '\n')
        (root / 'native').mkdir(exist_ok=True)
        (root / 'native' / 'native_result.json').write_text(json.dumps({
            'status': native_result['status'],
            'input_head': current_contract['input_head'],
            'contract_sha256': current_contract['contract_sha256'],
            'counters': {
                'materialization_attempts': 2, 'materializations_completed': 2,
                'resets': 2, 'resets_completed': 2, 'outer_intervals': 128,
                'attempted_mj_step_calls': 640, 'mj_step_calls': 640,
                'attempted_mj_forward_calls': 130, 'mj_forward_calls': 130,
                'cases': {episode: worker_case(case, root)['native_counts']
                          for episode, case in ((c['episode_id'], c) for c in current_contract['cases'])},
            },
            'cases': [worker_case(case, root) for case in current_contract['cases']],
        }, sort_keys=True) + '\n')
        return contract_file, root / 'native' / 'native_result.json'

    contract_path, native_result_path = publish(output_dir, contract)
    script = Path(__file__).with_name('r06b_order_readback.py').resolve()
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'

    def raw_reader(root, current_contract):
        current_contract_path, current_result_path = publish(root, current_contract)
        return subprocess.run(
            [sys.executable, str(script), '--contract', str(current_contract_path),
             '--native-result', str(current_result_path)],
            cwd=root, env=env, text=True, capture_output=True, timeout=30, check=False,
        )

    valid = raw_reader(output_dir, contract)
    assert valid.returncode == 0, valid.stdout + valid.stderr
    raw_receipt = json.loads((output_dir / 'raw_readback.json').read_text())
    assert raw_receipt['status'] == 'INDEPENDENT_RAW_H5_READBACK_PASS'
    assert [item['episode_id'] for item in raw_receipt['cases']] == ['E1', 'E2']
    assert raw_receipt['forbidden_imports_seen'] == []

    def edit_controls(path, mutation):
        with h5py.File(path, 'r+') as root:
            raw = root['meta/structured_controls_v1_json'][()]
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8')
            rows = json.loads(str(raw))
            mutation(rows)
            del root['meta/structured_controls_v1_json']
            root.create_dataset('meta/structured_controls_v1_json',
                                data=json.dumps(rows, sort_keys=True),
                                dtype=h5py.string_dtype(encoding='utf-8'))

    from task_env.diagnostics.tasks.r06b_order_worker import FROZEN_RAW_TAMPER_MATRIX
    tamper_labels = set(FROZEN_RAW_TAMPER_MATRIX)
    results = {}
    for label in sorted(tamper_labels):
        tampered_root = tmp_path / f'raw-tamper-{label}'
        shutil.copytree(output_dir, tampered_root)
        contract_file = tampered_root / 'contract.json'
        result_path = tampered_root / 'native/native_result.json'
        tampered_contract = json.loads(contract_file.read_text())
        result_data = json.loads(result_path.read_text())
        case_h5 = tampered_root / 'cases/E2/E2.h5'
        if label == 'raw_source_hash':
            tampered_contract['cases'][1]['candidate']['source_closure_sha256'] = '0' * 64
            result_data['cases'][1]['candidate'] = tampered_contract['cases'][1]['candidate']
            digest = hashlib.sha256(json.dumps(
                {key: value for key, value in tampered_contract.items() if key != 'contract_sha256'},
                sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
            ).encode()).hexdigest()
            tampered_contract['contract_sha256'] = digest
            result_data['contract_sha256'] = digest
        elif label == 'raw_target':
            edit_controls(case_h5, lambda rows: rows[0]['writer_controls'][0][
                'controller_target'].__setitem__('identity_hash', '0' * 64))
        elif label == 'raw_ack':
            edit_controls(case_h5, lambda rows: rows[0]['writer_controls'][0][
                'canonical_action']['application_ack'].__setitem__('writer_id', 'tampered-writer'))
        elif label == 'raw_native_slot':
            edit_controls(case_h5, lambda rows: rows[0]['writer_controls'][0][
                'canonical_action']['prepared_command']['slot_values'][0].__setitem__('ctrl_slot', 5))
        elif label == 'raw_clock':
            edit_controls(case_h5, lambda rows: rows[0]['writer_controls'][0][
                'canonical_action']['source_boundary'].__setitem__('control_step', 7))
        elif label == 'raw_state_order':
            _swap_state_columns(case_h5)
        elif label == 't_plus_one':
            _tamper_observation_count(case_h5)
        elif label == 'raw_worker_result_file':
            result_data['cases'][1]['h5']['sha256'] = '0' * 64
        elif label == 'raw_worker_result_size':
            result_data['cases'][1]['h5']['bytes'] -= 1
        elif label == 'raw_worker_result_receipt':
            result_data['cases'][1]['native_receipt']['receipt_identity_sha256'] = '0' * 64
        elif label == 'raw_worker_materialization':
            result_data['cases'][1]['native_receipt']['provider_materialization_id'] = 'wrong-run'
        elif label == 'raw_worker_native_order':
            result_data['cases'][1]['native_receipt']['native_actuator_order'].reverse()
        elif label == 'raw_worker_native_slot':
            result_data['cases'][1]['native_receipt']['native_actuator_mappings'][
                'panda-arm/actuator1']['ctrl_slot'] = 0
        elif label == 'raw_worker_case_counters':
            result_data['cases'][1]['native_counts']['mj_step_calls'] = 319
        elif label == 'raw_worker_aggregate_counters':
            result_data['counters']['cases']['E2']['mj_forward_calls'] = 64
        elif label == 'raw_worker_candidate':
            result_data['cases'][1]['candidate']['scene_identity_sha256'] = '0' * 64
        elif label == 'raw_duplicate_case':
            result_data['cases'][1] = dict(result_data['cases'][0])
        elif label == 'raw_missing_case':
            result_data['cases'].pop()
        elif label == 'raw_swapped_case':
            result_data['cases'].reverse()
        elif label == 'raw_wrong_run':
            shutil.copy2(tampered_root / 'cases/E1/E1.h5', case_h5)
        elif label == 'raw_contract_digest':
            tampered_contract['cases'][1]['candidate']['source_closure_sha256'] = '0' * 64
        if label in {'raw_target', 'raw_ack', 'raw_native_slot', 'raw_clock',
                     'raw_state_order', 't_plus_one', 'raw_wrong_run'}:
            result_data['cases'][1]['h5']['sha256'] = hashlib.sha256(case_h5.read_bytes()).hexdigest()
            result_data['cases'][1]['h5']['bytes'] = case_h5.stat().st_size
        if label in {'raw_target', 'raw_ack', 'raw_native_slot', 'raw_clock',
                     'raw_state_order', 't_plus_one', 'raw_wrong_run', 'raw_source_hash', 'raw_contract_digest'}:
            contract_file.write_text(json.dumps(tampered_contract, sort_keys=True, indent=2) + '\n')
        result_path.write_text(json.dumps(result_data, sort_keys=True) + '\n')
        result = subprocess.run(
            [sys.executable, str(script), '--contract', str(tampered_root / 'contract.json'),
             '--native-result', str(tampered_root / 'native/native_result.json')],
            cwd=tampered_root, env=env, text=True, capture_output=True, timeout=30, check=False,
        )
        results[label] = result.returncode
        assert result.returncode != 0, f'{label} tamper passed raw readback'
    assert set(results) == tamper_labels
    assert all(value != 0 for value in results.values())


def _swap_state_columns(path):
    import h5py
    import numpy as np
    with h5py.File(path, 'r+') as root:
        values = root['obs/state/joint_position']
        array = values[...]
        array[:, [0, 1]] = array[:, [1, 0]]
        values[...] = array


def _tamper_observation_count(path):
    import h5py
    with h5py.File(path, 'r+') as root:
        root.attrs['observation_count'] = 64


def test_frozen_native_preflight_binds_clean_head_code_and_submodule_pins(
        monkeypatch, tmp_path):
    import json
    import subprocess

    from task_env.diagnostics.tasks import r06b_order_worker as worker

    root = worker.ROOT
    protected = tmp_path / 'protected-input.txt'
    protected.write_text('frozen-input-v1\n')
    code_path = 'task_env/diagnostics/tasks/r06b_order_worker.py'
    contract = {
        'input_head': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=root, text=True,
        ).strip(),
        'branch': subprocess.check_output(
            ['git', 'branch', '--show-current'], cwd=root, text=True,
        ).strip(),
        'code_sha256': {code_path: worker._sha(root / code_path)},
        'protected_sha256': {str(protected): worker._sha(protected)},
        'limits': worker.FROZEN_LIMITS,
        'oracles': worker.FROZEN_ORACLES,
        'reader_tamper_matrix': worker.FROZEN_TAMPER_MATRIX,
        'submodule_pins': {
            relative: subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=root / relative, text=True,
            ).strip()
            for relative in ('GeoPhys', 'asset/external/mujoco_menagerie')
        },
    }
    monkeypatch.setenv('OMP_NUM_THREADS', '1')
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    monkeypatch.setenv('MKL_NUM_THREADS', '1')
    contract['contract_sha256'] = worker._contract_digest(contract)
    contract_path = tmp_path / 'native_contract.json'
    contract_path.write_text(json.dumps(contract))
    worker._check_frozen_contract(contract, contract_path)

    tampered = dict(contract)
    tampered['submodule_pins'] = dict(contract['submodule_pins'])
    tampered['submodule_pins']['GeoPhys'] = '0' * 40
    tampered['contract_sha256'] = worker._contract_digest(tampered)
    with pytest.raises(ValueError, match='submodule pin changed: GeoPhys'):
        worker._check_frozen_contract(tampered, contract_path)
