"""Explicit two-Entity Position candidate for the bounded C02b S2 probe.

This diagnostic reuses the frozen A05 Panda asset closure but creates a new
Scene/Artifact/source closure. The two Panda articulations remain independent
roots in one native world; no Assembly or attachment is implied.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from types import SimpleNamespace

from task_env.artifacts import SceneDefinition, Timebase
from task_env.controllers.canonical.contracts import digest
from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
from task_env.diagnostics.tasks.test_phase_ii_d01a_scene_materialization import (
    _a05_scene,
    _artifact_and_sample,
    _source_input,
)
from task_env.diagnostics.tasks.test_phase_ii_d01b_vnext_materialization import _task_source
from task_env.environment import (
    TaskRoleDeclarationV1,
    compile_task_artifact_v1,
    sample_episode_reset_plan,
)
from task_env.runtime.sessions.control import compile_control_binding_plan
from task_env.tasks.reference_env import ReferenceTaskBinding, SelectedReferenceEnv


DUAL_ENTITY_TASK_ID = 'phase-ii-c02b-dual-position'
DUAL_ENTITY_VERSION = 'candidate-v1'
DUAL_ENTITY_SCENE_ID = 'phase-ii-c02b-dual-entity-position-v1'
DUAL_ENTITY_SEED = 31
MAIN_ENTITY = 'panda-main'
SECONDARY_ENTITY = 'panda-secondary'
SECONDARY_PREFIX = 'secondary_'


def _dual_scene(base):
    """Clone the authored Panda topology under globally distinct names."""
    mapping = deepcopy(base.to_mapping())
    mapping['scene_id'] = DUAL_ENTITY_SCENE_ID

    entity = next(row for row in mapping['entities'] if row['entity_id'] == MAIN_ENTITY)
    mapping['entities'].append({**deepcopy(entity), 'entity_id': SECONDARY_ENTITY})

    for row in tuple(mapping['frames']):
        if row['entity_id'] != MAIN_ENTITY:
            continue
        clone = deepcopy(row)
        clone['entity_id'] = SECONDARY_ENTITY
        clone['frame_id'] = SECONDARY_PREFIX + clone['frame_id']
        if clone.get('parent'):
            clone['parent']['entity_id'] = SECONDARY_ENTITY
            clone['parent']['frame_id'] = SECONDARY_PREFIX + clone['parent']['frame_id']
        mapping['frames'].append(clone)

    for row in tuple(mapping['articulations']):
        if row['entity_id'] != MAIN_ENTITY:
            continue
        clone = deepcopy(row)
        clone['entity_id'] = SECONDARY_ENTITY
        clone['root_frame_id'] = SECONDARY_PREFIX + clone['root_frame_id']
        clone['link_frame_ids'] = [SECONDARY_PREFIX + value for value in clone['link_frame_ids']]
        for joint in clone['joints']:
            joint['joint_id'] = SECONDARY_PREFIX + joint['joint_id']
            for endpoint in ('parent_frame', 'child_frame'):
                joint[endpoint]['entity_id'] = SECONDARY_ENTITY
                joint[endpoint]['frame_id'] = SECONDARY_PREFIX + joint[endpoint]['frame_id']
        mapping['articulations'].append(clone)

    robot = next(row for row in mapping['robots'] if row['entity_id'] == MAIN_ENTITY)
    root = deepcopy(robot['articulation_roots'][0])
    root['entity_id'] = SECONDARY_ENTITY
    root['frame_id'] = SECONDARY_PREFIX + root['frame_id']
    mapping['robots'].append({
        'schema_version': robot['schema_version'],
        'entity_id': SECONDARY_ENTITY,
        'articulation_roots': [root],
    })

    for row in tuple(mapping['actuator_resources']):
        if row['entity_id'] == MAIN_ENTITY:
            clone = deepcopy(row)
            clone['entity_id'] = SECONDARY_ENTITY
            clone['actuator_id'] = SECONDARY_PREFIX + clone['actuator_id']
            mapping['actuator_resources'].append(clone)
    for row in tuple(mapping['control_groups']):
        if row['entity_id'] == MAIN_ENTITY:
            clone = deepcopy(row)
            clone['entity_id'] = SECONDARY_ENTITY
            for resource in clone['actuator_refs']:
                resource['entity_id'] = SECONDARY_ENTITY
                resource['actuator_id'] = SECONDARY_PREFIX + resource['actuator_id']
            mapping['control_groups'].append(clone)

    scene = SceneDefinition.from_mapping(mapping)
    return scene


def _duplicate_panda_xml(xml):
    """Add one prefixed Panda root and its controls to the diagnostic source."""
    root = ET.fromstring(xml)
    worldbody = root.find('worldbody')
    native_root = worldbody.find("body[@name='link0']") if worldbody is not None else None
    if native_root is None:
        raise ValueError('candidate source does not contain the A05 Panda link0 root')
    clone = deepcopy(native_root)
    clone.set('name', SECONDARY_PREFIX + 'link0')
    clone.set('pos', '-1.6 0 0')

    native_names = {
        item.get('name') for item in root.iter()
        if item.get('name') and item is not native_root
    }
    native_names.update(item.get('name') for item in native_root.iter() if item.get('name'))
    refs = {'joint', 'joint1', 'joint2', 'body1', 'body2', 'geom1', 'geom2',
            'site1', 'site2', 'tendon'}

    def prefix_clone(element):
        for node in element.iter():
            name = node.get('name')
            if name in native_names:
                node.set('name', SECONDARY_PREFIX + name)
            for key in refs:
                value = node.get(key)
                if value in native_names:
                    node.set(key, SECONDARY_PREFIX + value)

    prefix_clone(clone)
    worldbody.append(clone)

    for section_name in ('tendon', 'equality', 'contact', 'actuator'):
        source_section = root.find(section_name)
        if source_section is None:
            continue
        children = tuple(source_section)
        for child in children:
            copied = deepcopy(child)
            prefix_clone(copied)
            source_section.append(copied)
    return ET.tostring(root, encoding='unicode')


def _candidate_task_source(scene):
    declared = _task_source(scene)
    roles = (
        TaskRoleDeclarationV1('manipulator_main', 'robot', 'ids', (MAIN_ENTITY,), 'exactly_one'),
        TaskRoleDeclarationV1('manipulator_secondary', 'robot', 'ids', (SECONDARY_ENTITY,), 'exactly_one'),
        TaskRoleDeclarationV1('target_peg', 'rigid_body', 'ids', ('square-peg-instance',), 'exactly_one'),
    )
    return replace(
        declared,
        task_id=DUAL_ENTITY_TASK_ID,
        version=DUAL_ENTITY_VERSION,
        roles=roles,
    )


def build_dual_entity_position_candidate(
    workspace: Path | str, *, provider: str, horizon: int = 6000,
):
    """Build a real two-Entity candidate through the existing selected lifecycle."""
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    scene = _dual_scene(_a05_scene())
    legacy, _ = _artifact_and_sample(scene)
    legacy = replace(
        legacy,
        artifact_id='phase-ii-c02b-dual-position-v1',
        task_id=DUAL_ENTITY_TASK_ID,
        artifact_version=DUAL_ENTITY_VERSION,
        timebase=Timebase(0.002, 5, 0.01),
    )
    task_source = _candidate_task_source(scene)
    artifact = compile_task_artifact_v1(task_source, scene, legacy)
    reset_plan = sample_episode_reset_plan(
        task_source, scene, artifact, task_seed=DUAL_ENTITY_SEED,
    )

    source, imported, closure_digest, panda_digest, panda_file_count = _source_input(
        importlib.import_module('scene'), root / 'source-closure', scene, legacy,
        source_mutator=_duplicate_panda_xml,
    )
    if imported is None or len(closure_digest) != 64 or len(panda_digest) != 64:
        raise ValueError('dual Position candidate source import/closure evidence is incomplete')
    source_config = replace(
        source.config,
        runtime=replace(source.config.runtime, control_substeps=5),
    )
    source = replace(
        source,
        task_artifact_hash=artifact.identity_hash,
        joint_targets={
            **{f'{MAIN_ENTITY}/joint{i}': f'actuator{i}' for i in range(1, 8)},
            **{f'{SECONDARY_ENTITY}/{SECONDARY_PREFIX}joint{i}': f'{SECONDARY_PREFIX}actuator{i}'
               for i in range(1, 8)},
        },
        open_actuators=('actuator8', f'{SECONDARY_PREFIX}actuator8'),
        config=source_config,
        source_closure_digest=closure_digest,
    )

    def make_profiles():
        main = PandaPositionServoProfileV1.from_source(artifact, source)
        secondary = PandaPositionServoProfileV1.for_entity(
            artifact, source,
            entity_id=SECONDARY_ENTITY,
            joint_ids=tuple(f'{SECONDARY_PREFIX}joint{i}' for i in range(1, 8)),
            finger_joint_ids=(f'{SECONDARY_PREFIX}finger_joint1', f'{SECONDARY_PREFIX}finger_joint2'),
            hand_frame_id=f'{SECONDARY_PREFIX}hand',
            native_prefix=SECONDARY_PREFIX,
            actuator_prefix=SECONDARY_PREFIX,
        )
        return main, secondary

    profiles = make_profiles()
    plan = compile_control_binding_plan(scene, tuple(profile.controller_binding() for profile in profiles))

    def build(_provider):
        bound_profiles = make_profiles()
        bound_plan = compile_control_binding_plan(
            scene, tuple(profile.controller_binding() for profile in bound_profiles),
        )
        return {
            'artifact': artifact,
            'solution': None,
            'controller': bound_profiles,
            'source': source,
            'reset_plan': reset_plan,
            'controller_binding_plan': bound_plan,
            'construction_id': digest({
                'artifact': artifact.identity_hash,
                'scene': scene.identity_hash,
                'source_closure': source.source_closure_digest,
                'profiles': tuple(profile.identity for profile in bound_profiles),
                'plan': bound_plan.identity_hash,
            }),
            'resolved_configuration': {
                'provider': _provider, 'backend': 'cpu',
                'profile_ids': tuple(profile.profile_id for profile in bound_profiles),
            },
            'source_revision': 'C02b-minimal-dual-entity-position-v1',
            'source_sha256': {'source_closure': source.source_closure_digest},
        }

    def fixed_seed(seed):
        if type(seed) is not int or seed != reset_plan.reset_sample.task_seed:
            raise ValueError(
                'dual Position candidate uses a fixed ResetPlan; reset seed must equal '
                f'{reset_plan.reset_sample.task_seed}'
            )
        return seed

    binding = ReferenceTaskBinding(
        build=build,
        reset_sample=lambda _artifact, _seed: reset_plan.reset_sample,
        evaluate=lambda _state, _semantics: SimpleNamespace(
            reward=0.0, success=False, failure=False, metrics={},
        ),
        object_poses=(('square-peg-instance/peg1', 'target'),),
        external_actions=True,
        interval_mode='grouped',
        recorder_mode='execution',
        reset_seed=fixed_seed,
    )
    env = SelectedReferenceEnv.from_position_candidate(
        binding, provider=provider, backend='cpu', horizon=horizon,
    )
    return SimpleNamespace(
        env=env, scene=scene, task_source=task_source, artifact=artifact,
        reset_plan=reset_plan, source=source, controller_binding_plan=plan,
        panda_closure_digest=panda_digest, panda_file_count=panda_file_count,
        provider=provider, imported_scene=imported,
        source_closure_digest=closure_digest,
        profiles=profiles,
    )


__all__ = [
    'DUAL_ENTITY_SEED', 'DUAL_ENTITY_SCENE_ID', 'DUAL_ENTITY_TASK_ID',
    'DUAL_ENTITY_VERSION', 'MAIN_ENTITY', 'SECONDARY_ENTITY',
    'build_dual_entity_position_candidate',
]
