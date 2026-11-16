"""The F06 recorder projects the selected source and reset declarations."""
from dataclasses import dataclass
from types import SimpleNamespace as NS

from task_env.recorders.position_metadata import position_record_metadata


@dataclass
class Schema:
    components: tuple = ('x',)


def test_f06_recording_contains_selected_provenance():
    sample = NS(sample_id='sample', task_seed=32)
    plan = NS(identity_hash='plan', reset_sample=sample,
              to_mapping=lambda: {'reset': 32},
              to_provider_sample=lambda: NS(to_mapping=lambda: {'sample': 32}))
    execution = NS(identity_hash='execution', to_mapping=lambda: {'seed': 32})
    admission = NS(reset_plan=plan, execution=execution, delivery_manifest_sha256='delivery')
    profile = NS(profile_id='profile', writer_id='writer', identity='controller', entity_id='panda-v1',
                 tcp_profile=NS(to_mapping=lambda: {}),
                 controller_binding=lambda: NS(action_schema=Schema()))
    value = {'session_admission_input': admission, 'reset_plan': plan,
             'source': NS(source_closure_digest='closure', source_id='source'),
             'source_revision': 'commit', 'source_sha256': {'owner.py': 'digest'},
             'resolved_configuration': {'task_recipe': {'recipe': {'id': 'candidate'}}}}
    env = NS(position_profiles=(profile,), dual_entity_position=False, value=value,
             artifact=NS(task_id='task', artifact_version='v1', identity_hash='artifact',
                         timebase=NS(physics_dt=.002, control_substeps=5, control_dt=.01)),
             binding=NS(object_poses=()), position_scene=NS(scene_id='scene', identity_hash='scene-hash'),
             position_plan=NS(identity_hash='binding'),
             session=NS(build_layout_facts={'native_runtime_metadata': {'provider_build_identity': 'isaac'},
                                            'native_public_bootstrap_receipt': {}},
                        provider_materialization_id='materialized', reset_plan_evidence={}),
             realized=NS(measured_state=NS(to_mapping=lambda: {})),
             get_execution_receipt=lambda: {'request_identity': 'request'},
             _active_solution_identity=lambda: 'solution', _selected_execution_context=lambda: (None,),
             provider='isaacsim', backend='cuda', horizon=10)
    recorded = position_record_metadata(env)['env_metadata']['reference_profile']
    assert recorded['recording_provenance_schema'] == 'pickcube-isaac-replay-provenance-v1'
    assert recorded['task_seed'] == 32
    assert recorded['reset_plan_v1'] == {'reset': 32}
    assert recorded['execution_spec_v1'] == {'seed': 32}
    assert recorded['source_revision'] == 'commit'
    assert recorded['source_sha256'] == {'owner.py': 'digest'}
    assert recorded['task_recipe'] == {'recipe': {'id': 'candidate'}}
