"""Defect-sensitive pure checks for the bounded coupled effort servo."""
from dataclasses import replace
import numpy as np
import pytest

from task_env.artifacts import FrameReference
from task_env.artifacts.state import CanonicalStateViewV2, TypedJointStateValue
from task_env.controllers.canonical.mass_matrix_effort import MassMatrixEffortControllerV1
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case


def _fixture():
    plan, context, _, _ = _case()
    base = plan.binding.channels[0]
    names = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1','finger_joint2')
    channels = tuple(replace(base, component_path=('robot',name), entity_id='panda-v1', joint_id=name,
        axis_frame=FrameReference('panda-v1','base'), kind='revolute' if i<7 else 'prismatic',
        unit='N*m' if i<7 else 'N', native_actuator=f'a{i}', transmission_id=f't{i}',
        native_drive='disabled') for i,name in enumerate(names))
    binding=replace(plan.binding,channels=channels)
    joints=tuple(TypedJointStateValue('typed-joint-state-v1','panda-v1',name,
        'revolute' if i<7 else 'prismatic','radian' if i<7 else 'meter',
        (0. if i<7 else (.019 if i==7 else .021),),
        'radian_per_second' if i<7 else 'meter_per_second',(0.,)) for i,name in enumerate(names))
    state=CanonicalStateViewV2('canonical-state-v2','SI_right_handed_z_up_wxyz',context.boundary,context.clock,joints,(),())
    matrix=np.eye(8);matrix[0,1]=matrix[1,0]=.1
    return binding,context,state,matrix


def test_mass_servo_maps_acceleration_to_coupled_effort_and_equal_pair():
    binding,context,state,matrix=_fixture()
    servo=MassMatrixEffortControllerV1(binding,matrix=matrix,nominal_position=[0.]*7+[.02],
        max_abs_deviation=[.15]*7+[.019],model_sha256='c'*64,cadence_s=.01)
    batch=servo.compute([.1,0,0,0,0,0,0,.04],state,context)
    assert [x.value for x in batch.joint_efforts] == pytest.approx([2.,.2,0,0,0,0,0,0,0])
    assert all(x.controller_law=='explicit_full_pd' for x in batch.joint_efforts)
    with pytest.raises(ValueError,match='stale or foreign'):
        servo.compute([0.]*8,state,replace(context,boundary=replace(context.boundary,state_revision=1)))
    moved=replace(state,joints=tuple(replace(x,position=(.3,)) if x.joint_id=='joint1' else x for x in state.joints))
    with pytest.raises(ValueError,match='neighborhood'):
        servo.compute([0.]*8,moved,context)
    with pytest.raises(ValueError, match='nonfinite effort'):
        servo.compute([1e308,0,0,0,0,0,0,.04],state,context)


def test_mass_servo_rejects_unstable_model_and_active_drive():
    binding,_,_,matrix=_fixture()
    matrix[0,0]=-1.
    with pytest.raises(ValueError,match='positive definite'):
        MassMatrixEffortControllerV1(binding,matrix=matrix,nominal_position=[0.]*8,
            max_abs_deviation=[.1]*8,model_sha256='c'*64,cadence_s=.01)
    active=replace(binding,channels=(replace(binding.channels[0],native_drive='position'),*binding.channels[1:]))
    with pytest.raises(ValueError,match='isolated'):
        MassMatrixEffortControllerV1(active,matrix=np.eye(8),nominal_position=[0.]*8,
            max_abs_deviation=[.1]*8,model_sha256='c'*64,cadence_s=.01)
