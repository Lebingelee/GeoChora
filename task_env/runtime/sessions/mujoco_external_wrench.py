"""One-interval caller wrenches owned by a selected MuJoCo session.

This port never advances physics. The session's existing native loop owns
advancement and asks this port to project at each current configuration.
"""
from __future__ import annotations

import numpy as np

from ...controllers.canonical.physical_commands import (
    ExternalComWrenchSegmentV1, ExternalComWrenchSumSegmentV1, ExternalComWrenchV1,
)


def com_wrench_range(request, substeps):
    if type(request) is ExternalComWrenchV1:
        return 0, substeps
    if type(request) in (ExternalComWrenchSegmentV1, ExternalComWrenchSumSegmentV1):
        if request.end_substep > substeps:
            raise ValueError('caller COM segment exceeds the control interval')
        return request.start_substep, request.end_substep
    raise TypeError('caller wrench must be a supported external COM contract')


class MuJoCoExternalComPort:
    def __init__(self, session, requests, *, task_requests=()):
        session._require_reset()
        if (getattr(session, '_provider', None) != 'mujoco'
                or getattr(session, '_physical_port', None) is not None
                or getattr(session, '_mixed_actuator_plan', None) is not None):
            raise ValueError('caller COM wrench requires an admitted scalar MuJoCo position session')
        if (getattr(session._mj, '__version__', None) != '3.8.1'
                or int(session._model.opt.integrator)
                != int(session._mj.mjtIntegrator.mjINT_IMPLICITFAST)):
            raise ValueError('caller COM wrench requires checked MuJoCo 3.8.1 implicitfast')
        if type(requests) is not tuple or type(task_requests) is not tuple or not (requests or task_requests):
            raise TypeError('COM wrenches must be immutable tuples with at least one contribution')
        if np.any(session._data.qfrc_applied) or np.any(session._data.xfrc_applied):
            raise ValueError('caller COM wrench cannot take an occupied force buffer')
        if getattr(session, '_external_com_port', None) is not None:
            raise ValueError('a caller wrench is already staged for this interval')
        source = session._source
        rows, effects, bodies = [], {}, {}
        substeps = session._artifact.timebase.control_substeps
        if type(substeps) is not int or substeps <= 0:
            raise ValueError('caller wrench requires an integral control timebase')
        for request in (*requests, *task_requests):
            if type(request) not in (ExternalComWrenchV1, ExternalComWrenchSegmentV1, ExternalComWrenchSumSegmentV1):
                raise TypeError('caller wrench must be a supported external COM contract')
            request.validate()
            start, end = com_wrench_range(request, substeps)
            semantic = request.source_body_key
            native = source.bodies.get(semantic)
            if native is None:
                raise ValueError('caller wrench body is not bound by the selected source')
            body_id = int(session._model.body(native).id)
            cursor, movable = body_id, False
            while cursor > 0:
                movable = movable or int(session._model.body_dofnum[cursor]) > 0
                cursor = int(session._model.body_parentid[cursor])
            if body_id <= 0 or float(session._model.body_mass[body_id]) <= 0 or not movable:
                raise ValueError('caller wrench requires a source-bound dynamic body')
            effect_ranges = effects.setdefault(request.physical_effect_id, [])
            if any(start < prior_end and prior_start < end for prior_start, prior_end in effect_ranges):
                raise ValueError('caller wrench effect ranges overlap; claims must be unique')
            effect_ranges.append((start, end))
            body_ranges = bodies.setdefault(body_id, [])
            if any(start < prior_end and prior_start < end
                   and (type(request) is not ExternalComWrenchSumSegmentV1
                        or type(prior) is not ExternalComWrenchSumSegmentV1)
                   for prior_start, prior_end, prior in body_ranges):
                raise ValueError('caller wrench native body ranges overlap; exclusive claims must be unique')
            body_ranges.append((start, end, request))
            rows.append((request, body_id))
        self.session, self.rows = session, tuple(rows)
        self.producers = ('caller',) * len(requests) + ('task',) * len(task_requests)
        # Different source names may bind the same native body.  Publish one
        # stable source resource for every such alias, after native admission.
        self.body_resources = {
            body_id: 'body:' + min(key for key, native in source.bodies.items()
                                   if int(session._model.body(native).id) == body_id)
            for _, body_id in self.rows
        }
        self.boundary = session.state_boundary_identity()
        self.source_id = source.source_id
        self.source_closure_sha256 = source.source_closure_digest
        self.artifact_sha256 = session._artifact.identity_hash
        self.authorized = False
        self.pending_values = None
        self.refresh_count = 0
        self.substeps = substeps

    def verify(self, interval):
        s = self.session
        if (self.authorized or s.state_boundary_identity() != self.boundary
                or interval.boundary != self.boundary
                or (interval.source_id, interval.source_closure_sha256, interval.artifact_sha256)
                != (self.source_id, self.source_closure_sha256, self.artifact_sha256)
                or interval.substeps != s._artifact.timebase.control_substeps):
            raise ValueError('caller wrench is stale or differs from the committed interval')
        if np.any(s._data.qfrc_applied) or np.any(s._data.xfrc_applied):
            raise ValueError('caller wrench force buffer changed before submission')
        for request, body_id in self.rows:
            native = s._source.bodies.get(request.source_body_key)
            if native is None or int(s._model.body(native).id) != body_id:
                raise ValueError('caller wrench source body binding changed before submission')
            aliases = [key for key, name in s._source.bodies.items()
                       if int(s._model.body(name).id) == body_id]
            if not aliases or 'body:' + min(aliases) != self.body_resources[body_id]:
                raise ValueError('caller wrench source body aliases changed before submission')

    def refresh_substep(self):
        s = self.session
        if not self.authorized:
            raise RuntimeError('caller wrench requires the common submission owner')
        if self.pending_values is None:
            if np.any(s._data.qfrc_applied) or np.any(s._data.xfrc_applied):
                raise RuntimeError('caller wrench force buffer changed before projection')
        elif (not np.array_equal(s._data.qfrc_applied, self.pending_values)
              or np.any(s._data.xfrc_applied)):
            raise RuntimeError('caller wrench force buffer changed during interval')
        # xipos is the current inertial-frame origin, i.e. this body's COM in
        # world coordinates. It must be refreshed after every configuration.
        s._mj.mj_kinematics(s._model, s._data)
        s._mj.mj_comPos(s._model, s._data)
        projected = np.zeros(s._model.nv, dtype=float)
        if self.refresh_count >= self.substeps:
            raise RuntimeError('caller wrench was refreshed beyond its control interval')
        for request, body_id in self.rows:
            start, end = com_wrench_range(request, self.substeps)
            if not start <= self.refresh_count < end:
                continue
            s._mj.mj_applyFT(s._model, s._data, np.asarray(request.force_world_N),
                np.asarray(request.torque_com_world_Nm), s._data.xipos[body_id].copy(), body_id, projected)
        if not np.isfinite(projected).all():
            raise ValueError('caller COM wrench produced nonfinite generalized force')
        if self.pending_values is None:
            unchanged = not np.any(s._data.qfrc_applied)
        else:
            unchanged = np.array_equal(s._data.qfrc_applied, self.pending_values)
        if not unchanged or np.any(s._data.xfrc_applied):
            raise RuntimeError('caller wrench force buffer changed during projection')
        s._data.qfrc_applied[:] = projected
        self.pending_values = projected
        self.refresh_count += 1

    def preflight_reset(self):
        data = self.session._data
        if (np.any(data.xfrc_applied)
                or (self.pending_values is None and np.any(data.qfrc_applied))
                or (self.pending_values is not None
                    and not np.array_equal(data.qfrc_applied, self.pending_values))):
            raise RuntimeError('caller wrench reset cannot clear a foreign force buffer')

    def finish(self):
        data = self.session._data
        if self.pending_values is not None:
            owned = np.equal(data.qfrc_applied, self.pending_values)
            data.qfrc_applied[owned] = 0
        self.pending_values = None
        if getattr(self.session, '_external_com_port', None) is self:
            self.session._external_com_port = None
