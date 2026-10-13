"""Diagnostic compiled-model intervention; canonical assets remain unchanged."""
import hashlib
import numpy as np
import mujoco

def set_freejoint_armature(model,data,address,value):
    """Recompute derived model constants on scratch data, preserve live history."""
    spec=mujoco.mjtState.mjSTATE_INTEGRATION
    state=np.zeros(mujoco.mj_stateSize(model,spec));mujoco.mj_getState(model,data,state,spec)
    old=model.dof_armature[address:address+6].copy()
    initial_M0=model.dof_M0[address:address+6].copy()
    model.dof_armature[address:address+6]=float(value)
    scratch=mujoco.MjData(model);mujoco.mj_setConst(model,scratch)
    after=np.zeros_like(state);mujoco.mj_getState(model,data,after,spec)
    if not np.array_equal(state,after):raise ValueError('model constants changed live integration history')
    return {'old':old.tolist(),'new':model.dof_armature[address:address+6].tolist(),'derived_M0_before':initial_M0.tolist(),'derived_M0_after':model.dof_M0[address:address+6].tolist(),'live_integration_state_exact':True,'live_integration_state_sha256':hashlib.sha256(state.tobytes()).hexdigest(),'constant_recompute':'mj_setConst_on_separate_scratch_MjData'}
