"""The physical PickCube Solution sees its actual source EE site."""
from types import SimpleNamespace
import numpy as np
from task_env.artifacts import PoseWorld
from task_env.tasks.pick_cube.physical_candidate import _physical_pickcube_observation


def test_physical_observation_uses_source_ee_and_original_task_evaluator(monkeypatch):
    import task_env.observations.selected_reference as selected
    hand = np.array([0.,0.,.6,1.,0.,0.,0.],dtype=np.float32)
    monkeypatch.setattr(selected,'build_selected_observation',lambda env,state: (
        {'state':{'ee_pose':hand.copy(),'hand_pose':hand.copy()}},
        {'task_metrics':{'old':1},'is_success':False},SimpleNamespace(success=False)))
    expected=SimpleNamespace(success=True,failure=False,metrics={'cube_lift':.11},reward=1.)
    state=SimpleNamespace(pose_world={'panda-v1/ee':PoseWorld((0.,0.,.54),(1.,0.,0.,0.))})
    env=SimpleNamespace(binding=SimpleNamespace(evaluate=lambda value,semantics: expected if value is state else None),
                        artifact=SimpleNamespace(semantics=object()))
    obs,info,evaluation=_physical_pickcube_observation(env,state)
    assert obs['state']['ee_pose'][2]==np.float32(.54)
    assert obs['state']['hand_pose'][2]==np.float32(.6)
    assert info['is_success'] is True and info['task_metrics']['cube_lift']==.11 and evaluation is expected
