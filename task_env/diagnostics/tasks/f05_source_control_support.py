"""Build the retained F05 native input and lower its public USD model for tests."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
BASE = REPO / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001'
PROVIDER = REPO / 'GeoPhys'
for _path in (REPO, PROVIDER / 'src'):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def build_native_input(family='menagerie-panda'):
    """Build the retained F05 native candidate directly, without a synthetic S1 input."""
    if family != 'menagerie-panda':
        raise ValueError('F05 native candidate is restricted to the frozen Menagerie USD cell')
    from task_env.assembly.usd_delivery import resolve_provider_representation
    from task_env.diagnostics.tasks.f04_candidate_s1_support import build_candidate
    from task_env.runtime.sessions.leaf_control import GeoPhysHostModelProducerIdentityV1
    from task_env.tasks.position_candidate.builder import F05NativePositionCandidateInputV1

    accepted = build_candidate(family)
    old_source = accepted.runtime_source
    target_build_identity = 'geophys-67da1165149486d3ae3e779c13ce31af49e17d50'
    execution = replace(
        accepted.execution,
        physics_provider='geophys', physics_backend='cpu',
        physics_profile='geophys-usd-position-f05-native-v1',
        physics_device='cpu', determinism_mode='best_effort',
    )
    provisional_representation = resolve_provider_representation(
        old_source.scene_source.loaded_delivery,
        provider='geophys', provider_build_identity=target_build_identity,
        options={
            'f05_attempt': '003', 'lowering': 'public-host-model-native-v1',
            'producer_capture': 'pending',
        },
    )
    provisional_source = replace(
        old_source,
        scene_source=replace(old_source.scene_source, representation=provisional_representation),
    )
    lower_public_model(provisional_source)
    module_sources = {}
    source_root = (PROVIDER / 'src').resolve()
    for module_name, module in tuple(sys.modules.items()):
        raw_origin = getattr(module, '__file__', None)
        if not raw_origin:
            continue
        path = Path(raw_origin).resolve()
        try:
            path.relative_to(source_root)
        except ValueError:
            continue
        if path.is_file():
            module_sources[module_name] = (
                module_name, str(path), hashlib.sha256(path.read_bytes()).hexdigest(),
            )
    rows = tuple(sorted(module_sources.values(), key=lambda row: row[0]))
    producer_identity = GeoPhysHostModelProducerIdentityV1(
        'geophys-host-model-producer-identity-v1', target_build_identity,
        str(PROVIDER.resolve()),
        subprocess.check_output(
            ['git', '-C', str(PROVIDER), 'remote', 'get-url', 'origin'], text=True,
        ).strip(),
        subprocess.check_output(
            ['git', '-C', str(PROVIDER), 'rev-parse', 'HEAD'], text=True,
        ).strip(),
        not bool(subprocess.check_output(
            ['git', '-C', str(PROVIDER), 'status', '--porcelain=v1', '--untracked-files=all'],
            text=True,
        ).strip()),
        rows,
    )
    producer_identity.validate_current_tree()
    representation = resolve_provider_representation(
        old_source.scene_source.loaded_delivery,
        provider='geophys', provider_build_identity=target_build_identity,
        options={
            'f05_attempt': '003', 'lowering': 'public-host-model-native-v1',
            'host_model_producer_identity_sha256': producer_identity.identity_sha256,
            'actual_execution_build_identity': producer_identity.actual_provider_build_identity,
        },
    )
    source = replace(
        old_source,
        scene_source=replace(old_source.scene_source, representation=representation),
    )
    candidate = F05NativePositionCandidateInputV1(
        'f05-native-position-candidate-input-v1', accepted.task_source,
        accepted.artifact, source, execution, accepted.reset_plan,
        accepted.kinematics_source_xml, accepted.kinematics_source_sha256,
        producer_identity,
    )
    candidate.validate()
    return candidate


def lower_public_model(source):
    from task_env.runtime.sessions.geophys_source import GeoPhysSourceComposer
    from scene import import_scene_source

    composer = GeoPhysSourceComposer(source)
    try:
        public_source, bridge_id = composer.build_scene_source(None, ())
        imported = import_scene_source(public_source, cache=False)
        model = composer.build_scene_model(imported, None)
        return imported, model, bridge_id, composer.usd_mapping_report
    finally:
        composer.close()
