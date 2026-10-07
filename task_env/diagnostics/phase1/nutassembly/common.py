"""Shared task context, strict lock and provider-free public observation view."""
import hashlib
import json
from pathlib import Path
import numpy as np
import yaml
from ....tasks.nut_assembly.canonical_artifact import build_candidate
from ....tasks.nut_assembly.canonical_source import build_runtime_source
from ....tasks.nut_assembly.canonical_semantics import evaluate
from ....tasks.nut_assembly.solution import NutAssemblySolution, NutAssemblySolutionConfig
from ....controllers.canonical import ProductionCanonicalPandaController
from ....controllers.canonical.contracts import digest
from ..multirate.common import NativeAudit, write

METADATA = {'action_schema': {'controller_kind': 'absolute_pose', 'reference': 'world',
    'rotation_representation': 'quaternion_wxyz', 'dimension': 8}}
EVENTS = {'grasp': 'grasped_nut', 'lift': 'lifted_nut', 'hover': 'hovered_over_peg',
          'insert': 'inserted_on_peg', 'release': 'released_nut', 'success': 'task_success'}


def label(profile):
    return profile.lower().replace('na-', '')


def context(profile):
    artifact = build_candidate(profile)
    return artifact, build_runtime_source(artifact), NutAssemblySolutionConfig()


def observation(state, artifact):
    evaluation = evaluate(state, artifact.semantics)
    ee = state.pose_world['panda-v1/ee']
    obs = {'state': {'ee_pose': np.array((*ee.position, *ee.quaternion_wxyz), dtype=np.float32)},
           'privileged_state': {}}
    for semantic, key in [('square-nut-v1', 'square_nut_v1'), ('square-peg-v1', 'square_peg_v1')]:
        pose = state.pose_world[semantic]
        obs['privileged_state'][key + '_body_pose'] = np.array([(*pose.position, *pose.quaternion_wxyz)], dtype=np.float32)
    info = {'is_success': bool(evaluation.success), 'task_failure': bool(evaluation.failure),
            'task_metrics': dict(evaluation.metrics)}
    return obs, info, evaluation


def verify(root):
    root = Path(root)
    lock = json.loads((root / 'nutassembly_spec_lock.json').read_text())
    if hashlib.sha256((root / 'nutassembly_spec.yaml').read_bytes()).hexdigest() != lock['sha256']:
        raise ValueError('NutAssembly spec lock changed')
    spec = yaml.safe_load((root / 'nutassembly_spec.yaml').read_text())
    for path, sha in {**spec['frozen_sources'], **spec['implementation_sources']}.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
            raise ValueError('locked source changed: ' + path)
    return spec


def events_update(events, state, metrics):
    for event, metric in EVENTS.items():
        if metrics[metric] and events[event] is None:
            events[event] = {'control_step': state.control_step, 'simulation_time_s': state.simulation_time}


def empty_events():
    return {event: None for event in EVENTS}
