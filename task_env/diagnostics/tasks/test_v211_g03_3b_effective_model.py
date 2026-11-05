"""Checks for the GeoPhys effective model projection and boundary."""
from types import SimpleNamespace

import pytest

from task_env.environment import StageUnavailableError
from task_env.runtime.boundary import GeoPhysRuntimeBoundary
from task_env.runtime.sessions.geophys import _geophys_effective_model_facts


def test_effective_model_named_projection_is_detached_and_keeps_provider_ids():
    source = {'schema_version': 'rigid-model-snapshot-v1',
              'bodies': [{'id': 0, 'mass_kg': 2.0}],
              'joints': [{'id': 1, 'axis_child': [0.0, 0.0, 1.0]}],
              'actuators': [{'id': 3, 'transmission_id': 1}]}
    names = SimpleNamespace(bodies={'body': 0}, joints={'joint': 1}, actuators={'motor': 3})
    result = _geophys_effective_model_facts(source, names)
    assert result['bodies'][0] == {'id': 0, 'mass_kg': 2.0, 'name': 'body'}
    assert result['joints'][0]['name'] == 'joint'
    assert result['actuators'][0]['transmission_id'] == 1
    result['joints'][0]['axis_child'][0] = 2
    assert source['joints'][0]['axis_child'][0] == 0
    with pytest.raises(ValueError, match='unsupported'):
        _geophys_effective_model_facts({'schema_version': 'wrong'}, names)


def test_boundary_calls_only_public_reader_and_fails_when_unavailable():
    boundary = object.__new__(GeoPhysRuntimeBoundary)
    boundary._physics = SimpleNamespace(read_model_snapshot=lambda: {'materialization_id': 'x'})
    assert boundary.read_model_snapshot() == {'materialization_id': 'x'}
    boundary._physics = SimpleNamespace()
    with pytest.raises(StageUnavailableError, match='unavailable'):
        boundary.read_model_snapshot()
