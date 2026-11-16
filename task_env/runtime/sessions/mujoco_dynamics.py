"""Public-state MuJoCo dynamics model for the selected source; never steps physics."""
from __future__ import annotations
import numpy as np


class MuJoCoSourceDynamicsV1:
    """Evaluate source mass and bias in independent scratch data from named state."""
    def __init__(self, session):
        session._require_reset()
        self._mj, self._model = session._mj, session._model
        self._data = self._mj.MjData(self._model)
        self._base_qpos = np.asarray(session._data.qpos,dtype=np.float64).copy()
        self.source_closure_sha256 = session._source.source_closure_digest
        self._materialization = session.provider_materialization_id
        self._episode = session.state_boundary_identity().episode_id
        names=tuple(f'joint{i}' for i in range(1,8))+('finger_joint1','finger_joint2')
        ids=[int(self._mj.mj_name2id(self._model,self._mj.mjtObj.mjOBJ_JOINT,name)) for name in names]
        if any(i<0 for i in ids):raise ValueError('source dynamics requires all nine named joints')
        self._qpos=[int(self._model.jnt_qposadr[i]) for i in ids]
        self._dofs=[int(self._model.jnt_dofadr[i]) for i in ids]
        if len(set(self._dofs))!=9:raise ValueError('source dynamics joint DOFs alias')
        self._projection=np.zeros((9,8));self._projection[:7,:7]=np.eye(7);self._projection[7:,7]=1.

    def evaluate(self, q, qd, boundary):
        if (boundary.provider_materialization_id!=self._materialization or boundary.episode_id!=self._episode):
            raise ValueError('source dynamics received a foreign episode boundary')
        q=np.asarray(q,dtype=np.float64);qd=np.asarray(qd,dtype=np.float64)
        if q.shape!=(9,) or qd.shape!=(9,) or not np.isfinite(q).all() or not np.isfinite(qd).all():
            raise ValueError('source dynamics requires nine finite joint states')
        self._data.qpos[:]=self._base_qpos;self._data.qvel[:]=0.
        self._data.qpos[self._qpos]=q;self._data.qvel[self._dofs]=qd
        self._mj.mj_forward(self._model,self._data)
        full=np.zeros((self._model.nv,self._model.nv),dtype=np.float64)
        self._mj.mj_fullM(self._model,full,self._data.qM)
        matrix=full[np.ix_(self._dofs,self._dofs)]
        bias=np.asarray(self._data.qfrc_bias[self._dofs],dtype=np.float64)
        S=self._projection
        return {'mass_matrix':S.T@matrix@S,'bias':S.T@bias,'boundary':boundary,'physics_steps':0}


class MuJoCoArmOperationalSpaceV1:
    """Evaluate named arm dynamics and one TCP in scratch state, without stepping."""
    def __init__(self, session):
        session._require_reset()
        port = session._physical_port
        channels = port.binding.channels
        if len(channels) != 7 or any(c.kind != 'revolute' for c in channels):
            raise ValueError('operational-space model requires seven declared revolute channels')
        self._mj, self._model = session._mj, session._model
        self._data = self._mj.MjData(self._model)
        self.source_id = session._source.source_id
        self.source_closure_sha256 = session._source.source_closure_digest
        self._materialization = session.provider_materialization_id
        self._episode = session.episode_id
        self._qpos, self._dofs = [], []
        for channel in channels:
            name = session._source.joints[f'{channel.entity_id}/{channel.joint_id}']
            joint = int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_JOINT, name))
            if joint < 0:
                raise ValueError('source dynamics joint is missing')
            self._qpos.append(int(self._model.jnt_qposadr[joint]))
            self._dofs.append(int(self._model.jnt_dofadr[joint]))
        if len(set(self._dofs)) != len(channels):
            raise ValueError('source dynamics joint DOFs alias')
        tcp_key = f'{channels[0].entity_id}/ee'
        site_name = session._source.frames.get(tcp_key)
        if site_name is None:
            raise ValueError('operational-space source has no declared TCP')
        self.tcp_frame = port.execution.frame_bindings[tcp_key]
        if self.tcp_frame.entity_id != channels[0].entity_id or self.tcp_frame.frame_id != site_name:
            raise ValueError('operational-space TCP differs from its declared source frame')
        self._site = int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_SITE, site_name))
        if self._site < 0:
            raise ValueError('operational-space TCP is missing')
        self.forward_calls = 0

    def evaluate(self, q, qd, boundary):
        if (boundary.provider_materialization_id != self._materialization or boundary.episode_id != self._episode):
            raise ValueError('operational-space model received a foreign episode')
        q, qd = np.asarray(q, dtype=np.float64), np.asarray(qd, dtype=np.float64)
        if q.shape != (7,) or qd.shape != (7,) or not np.isfinite(q).all() or not np.isfinite(qd).all():
            raise ValueError('operational-space model needs seven finite positions and velocities')
        self._data.qpos[:] = self._model.qpos0
        self._data.qvel[:] = 0.
        self._data.qpos[self._qpos] = q
        self._data.qvel[self._dofs] = qd
        self._mj.mj_forward(self._model, self._data)
        self.forward_calls += 1
        full = np.zeros((self._model.nv, self._model.nv), dtype=np.float64)
        self._mj.mj_fullM(self._model, full, self._data.qM)
        jp = np.zeros((3, self._model.nv)); jr = np.zeros((3, self._model.nv))
        self._mj.mj_jacSite(self._model, self._data, jp, jr, self._site)
        return {'mass': full[np.ix_(self._dofs, self._dofs)],
                'bias': self._data.qfrc_bias[self._dofs].copy(),
                'jacobian': np.vstack((jp[:, self._dofs], jr[:, self._dofs])),
                'position': self._data.site_xpos[self._site].copy(),
                'rotation': self._data.site_xmat[self._site].reshape(3, 3).copy(),
                'boundary': boundary, 'physics_steps': 0}
