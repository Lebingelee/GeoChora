"""Versioned P1.6 construction; provider materialization stays caller-owned."""
from dataclasses import asdict, replace
import hashlib
from pathlib import Path

from ...artifacts.execution import ResetSample
from ...controllers.canonical import ProductionCanonicalPandaController
from .candidate import build_candidate
from .runtime_source import build_runtime_source
from .readiness_solution import PickCubeReadinessConfig, PickCubeReadinessSolution
from .reset import sample_reset as historical_sample_reset

CONSTRUCTION_ID = 'pickcube-p16-reference-construction-v1'
ARTIFACT_ID = 'pick-cube-v1/p1_6_experimental_100hz'
ARTIFACT_VERSION = 'ver_p1_6_experimental_100hz'
ARTIFACT_SHA256 = 'fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4'


def build_artifact():
    historical = build_candidate()
    artifact = replace(historical, artifact_id=ARTIFACT_ID,
        artifact_version=ARTIFACT_VERSION,
        timebase=replace(historical.timebase, physics_dt=.002,
                         control_substeps=5, control_dt=.010))
    if artifact.identity_hash != ARTIFACT_SHA256:
        raise ValueError('P1.6 selected Artifact identity mismatch')
    return artifact


def sample_reset(artifact, task_seed):
    """Preserve PCG64-v0 draws, rebinding only the selected Artifact identity."""
    if artifact != build_artifact():
        raise ValueError('selected P1.6 experimental_100hz Artifact required')
    sample = historical_sample_reset(build_candidate(), task_seed)
    payload = sample.to_mapping()
    payload.pop('sample_id')
    payload['task_artifact_hash'] = artifact.identity_hash
    return ResetSample.create(**payload)


def build_reference(*, backend='cpu'):
    """Construct without importing/starting a simulator; no qualification grant."""
    if backend not in {'cpu', 'cuda'}:
        raise ValueError('PickCube reference backend must be cpu or cuda')
    historical = build_candidate()
    artifact = build_artifact()
    source0 = build_runtime_source(historical)
    source = replace(source0, task_artifact_hash=artifact.identity_hash,
        config=replace(source0.config, runtime=replace(source0.config.runtime,
            physics_dt=.002, control_substeps=5, backend=backend, prewarm=False)))
    readiness = PickCubeReadinessConfig.from_source(artifact, source)
    controller = ProductionCanonicalPandaController.from_source(artifact, source)
    solution = PickCubeReadinessSolution(config=readiness)
    source_ids = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                  for name in ('reference.py', 'candidate.py', 'runtime_source.py', 'reset.py',
                               'canonical_semantics.py', 'readiness_solution.py', 'solution.py',
                               'task.py', 'assets.py', 'default.yaml')}
    canonical_dir = Path(__file__).resolve().parents[2] / 'controllers' / 'canonical'
    for name in ('production.py', 'controller.py', 'readiness.py', 'kinematics.py'):
        source_ids['controllers/canonical/' + name] = hashlib.sha256((canonical_dir / name).read_bytes()).hexdigest()
    return {'construction_id': CONSTRUCTION_ID, 'historical_artifact': historical,
        'artifact': artifact, 'source': source, 'readiness': readiness,
        'controller': controller, 'solution': solution,
        'resolved_configuration': {
            'construction_id': CONSTRUCTION_ID, 'artifact': artifact.to_mapping(),
            'artifact_sha256': artifact.identity_hash, 'runtime_config': asdict(source.config),
            'readiness': asdict(readiness),
            'resolved_controller_action': asdict(controller.config),
            'resolved_controller_gripper': asdict(controller.gripper_config),
            'controller_identity': controller.identity,
            'solution_identity': solution.identity,
            'source_xml_sha256': hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
            'source_sha256': source_ids,
            'qualification': 'NOT_REQUALIFIED',
            'runtime_source_bindings': {name: dict(getattr(source, name)) for name in
                ('joints', 'bodies', 'frames', 'free_joints', 'joint_targets')},
            'runtime_open_actuators': list(source.open_actuators)}}


__all__ = ['build_reference', 'build_artifact', 'sample_reset']
