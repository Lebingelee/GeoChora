"""G05 USD effort admission remains source-bound on the shared preflight path."""

from types import SimpleNamespace

import pytest

from task_env.runtime.sessions.api import G05_ISAAC_EFFORT_PROFILE, _validate_g05_isaac_effort_source


def test_g05_effort_rejects_foreign_delivery_and_timebase():
    renderer = SimpleNamespace(provider='none', backend='cpu', profile='none', device=None)
    execution = SimpleNamespace(physics_provider='isaacsim', physics_backend='cuda',
        physics_device='cuda:0', physics_profile=G05_ISAAC_EFFORT_PROFILE,
        determinism_mode='best_effort', render_default=renderer, camera_overrides=(), validate=lambda: None)
    artifact = SimpleNamespace(identity_hash='artifact', scene_identity_hash='scene',
        timebase=SimpleNamespace(physics_dt=.002, control_substeps=25, control_dt=.05))
    representation = SimpleNamespace(provider='isaacsim', provider_build_identity='isaacsim-6.2.0.0',
        representation_format='usd', runtime_admitted=False)
    delivery = SimpleNamespace(locally_validated=True, source_verified=False,
        delivery=SimpleNamespace(representation_id='isaacsim-6.2.0.0-g05-mjcf-v1'))
    source = SimpleNamespace(validate=lambda: None, task_artifact=artifact,
        scene_definition=SimpleNamespace(identity_hash='scene'),
        scene_source=SimpleNamespace(representation=representation, loaded_delivery=delivery),
        joints={'joint': 'joint'}, joint_targets={'joint': 'joint'})
    _validate_g05_isaac_effort_source(artifact, execution, source)
    delivery.delivery.representation_id = 'foreign'
    with pytest.raises(ValueError, match='reviewed MJCF conversion'):
        _validate_g05_isaac_effort_source(artifact, execution, source)
    delivery.delivery.representation_id = 'isaacsim-6.2.0.0-g05-mjcf-v1'
    artifact.timebase.control_substeps = 24
    with pytest.raises(ValueError, match='25 substep'):
        _validate_g05_isaac_effort_source(artifact, execution, source)
