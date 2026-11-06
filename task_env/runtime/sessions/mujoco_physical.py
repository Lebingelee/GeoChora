"""Source-bound MuJoCo physical command port for a selected session.

This module imports no SDK.  It receives the existing MuJoCo session only
once its normal materialization has completed and checks the compiled model
before issuing any build receipt.  It owns no simulation or second runtime.
"""
from __future__ import annotations

import math

import numpy as np

from ...artifacts.contracts import CapabilityAssessmentRowV1, CapabilityAssessmentV1
from ...controllers.canonical.physical_commands import (
    PhysicalBodyBuildReceiptV1, PhysicalBufferPolicyV1, PhysicalControlReceiptV1,
    PhysicalJointBuildReceiptV1,
)
from .physical_control import (PhysicalControlExecutionV1, ResolvedPhysicalBatchV1,
                               prepare_physical_command_batch, resolve_body_wrench_at_poses)


def _same(a, b):
    return bool(np.allclose(a, b, rtol=0, atol=1e-12))


def preflight_physical_mujoco(execution, artifact, source):
    """Reject foreign declarations or missing dependency before materialization."""
    from importlib import metadata
    from ...environment.types import StageUnavailableError
    if type(execution) is not PhysicalControlExecutionV1:
        raise TypeError('physical session requires an exact execution profile')
    execution.validate_source(scene=source.scene_definition, artifact_sha256=artifact.identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
    try:
        version = metadata.version('mujoco')
    except metadata.PackageNotFoundError as error:
        raise StageUnavailableError('physical MuJoCo dependency is unavailable') from error
    if version != '3.8.1':
        raise StageUnavailableError('physical MuJoCo route requires the checked 3.8.1 dependency')


class MuJoCoPhysicalPort:
    """One materialization's checked named mapping and single batch authority."""

    def __init__(self, session, execution):
        if type(execution) is not PhysicalControlExecutionV1:
            raise TypeError('physical session requires an exact execution profile')
        binding = execution.compiled.binding
        execution.validate_source(scene=session._source.scene_definition,
            artifact_sha256=session._artifact.identity_hash,
            source_id=session._source.source_id,
            source_closure_sha256=session._source.source_closure_digest,
            source=session._source)
        model, mj, source = session._model, session._mj, session._source
        if session._provider != 'mujoco' or session._mixed_actuator_plan is not None:
            raise ValueError('physical port requires a scalar MuJoCo session')
        definitions = {(a.entity_id, j.joint_id): j for a in execution.scene.articulations or () for j in a.joints}
        groups, dofs, actuator_ids, equality_ids = {}, {}, set(), []
        for channel in binding.channels:
            semantic = f'{channel.entity_id}/{channel.joint_id}'
            native = source.joints.get(semantic)
            if native is None:
                raise ValueError('physical channel has no named source joint')
            joint_id = int(model.joint(native).id)
            kind = mj.mjtJoint.mjJNT_HINGE if channel.kind == 'revolute' else mj.mjtJoint.mjJNT_SLIDE
            if int(model.jnt_type[joint_id]) != int(kind) or channel.dof_id != 'dof0':
                raise ValueError('compiled physical joint kind/DOF differs')
            definition = definitions[(channel.entity_id, channel.joint_id)]
            if not _same(model.jnt_axis[joint_id], definition.axis):
                raise ValueError('compiled joint axis differs from declared source')
            dof = int(model.jnt_dofadr[joint_id])
            if dof in dofs.values():
                raise ValueError('physical channels alias one native DOF')
            dofs[channel.target_key] = dof
            groups.setdefault((channel.entity_id, channel.transmission_id), []).append((channel, joint_id))
        for group in groups.values():
            actuator = int(model.actuator(group[0][0].native_actuator).id)
            if actuator in actuator_ids:
                raise ValueError('physical transmissions alias one native actuator')
            actuator_ids.add(actuator)
            first = group[0][0]
            if (not bool(model.actuator_forcelimited[actuator])
                    or not _same(model.actuator_forcerange[actuator], first.native_range)
                    or not _same(model.actuator_gear[actuator], (1, 0, 0, 0, 0, 0))
                    or int(model.actuator_biastype[actuator]) != int(mj.mjtBias.mjBIAS_AFFINE)
                    or int(model.actuator_gaintype[actuator]) != int(mj.mjtGain.mjGAIN_FIXED)
                    or int(model.actuator_dyntype[actuator]) != int(mj.mjtDyn.mjDYN_NONE)
                    or float(model.actuator_gainprm[actuator, 0]) <= 0
                    or float(model.actuator_biasprm[actuator, 1]) >= 0
                    or float(model.actuator_biasprm[actuator, 2]) > 0
                    or any(channel.native_drive != 'position' for channel, _ in group)):
                raise ValueError('compiled actuator range, gear or position drive differs')
            trn = int(model.actuator_trntype[actuator])
            target = int(model.actuator_trnid[actuator][0])
            if trn == int(mj.mjtTrn.mjTRN_JOINT):
                if len(group) != 1 or target != group[0][1] or first.transmission_coefficient != 1:
                    raise ValueError('compiled joint transmission differs')
            elif trn == int(mj.mjtTrn.mjTRN_TENDON):
                start, count = int(model.tendon_adr[target]), int(model.tendon_num[target])
                actual = [(int(model.wrap_objid[i]), float(model.wrap_prm[i]))
                          for i in range(start, start + count)
                          if int(model.wrap_type[i]) == int(mj.mjtWrap.mjWRAP_JOINT)]
                expected = [(joint, channel.transmission_coefficient) for channel, joint in group]
                if len(actual) != count or sorted(actual) != sorted(expected):
                    raise ValueError('compiled tendon transmission differs')
                if len(group) != 2:
                    raise ValueError('physical port requires the declared paired tendon')
                joint_pair = {joint for _, joint in group}
                matches = [i for i in range(model.neq)
                    if int(model.eq_type[i]) == int(mj.mjtEq.mjEQ_JOINT)
                    and {int(model.eq_obj1id[i]), int(model.eq_obj2id[i])} == joint_pair
                    and bool(model.eq_active0[i])
                    and _same(model.eq_data[i, :5], (0, 1, 0, 0, 0))]
                if len(matches) != 1:
                    raise ValueError('compiled paired-joint equality differs')
                equality_ids.append(matches[0])
            else:
                raise ValueError('unsupported compiled physical transmission')
        bodies = {}
        body_frames = {}
        for body in binding.bodies:
            if source.bodies.get(f'{body.entity_id}/{body.body_id}') != body.native_body:
                raise ValueError('physical body differs from source mapping')
            body_id = int(model.body(body.native_body).id)
            if body_id <= 0:
                raise ValueError('physical wrench target must be a non-world body')
            bodies[(body.entity_id, body.body_id)] = body_id
            body_frames[(body.entity_id, body.body_id)] = body.body_frame
        if binding.bodies and int(model.opt.integrator) != int(mj.mjtIntegrator.mjINT_IMPLICITFAST):
            raise ValueError('physical body wrench requires the verified MuJoCo implicitfast integrator')
        frame_handles = {}
        for semantic, reference in execution.frame_bindings.items():
            if semantic in source.bodies:
                frame_handles[reference] = ('body', session._bodies[semantic])
            elif semantic in source.frames:
                frame_handles[reference] = ('site', session._frames[semantic])
            else:
                raise ValueError('physical frame lacks a compiled native mapping')
        self.session, self.execution, self.binding = session, execution, binding
        self.dofs, self.bodies = dofs, bodies
        self.body_frames, self.frame_handles = body_frames, frame_handles
        self.equality_ids = tuple(equality_ids)
        self.pending = None
        self.pending_values = None
        self.pending_joints = None
        self.pending_wrenches = ()
        self.kinematics_refreshes = 0
        self.consumed = set()

    def _binding(self, binding):
        self.session._require_open()
        if binding != self.binding:
            raise ValueError('physical port binding differs from materialized profile')

    def assessment(self, binding):
        self._binding(binding)
        names = ('sum', 'hold_reapply')
        if binding.channels:
            names += ('joint_effort', 'transmission', 'native_drive_state')
        if binding.bodies:
            names += ('body_force', 'body_torque', 'body_frame', 'body_offset_point')
        rows = tuple(CapabilityAssessmentRowV1('capability-assessment-row-v1', name,
            f'binding:{binding.identity_hash}', 'required', 'supported', 'implemented',
            'available', 'none', 'native_build', 'compiled MuJoCo named mapping checked',
            None, None) for name in names)
        return CapabilityAssessmentV1('capability-assessment-v1', binding.identity_hash, 'native_build', rows)

    def joints(self, binding):
        self._binding(binding)
        return PhysicalJointBuildReceiptV1('physical-joint-build-receipt-v1', binding.identity_hash,
            binding.source_closure_sha256, self.session.provider_materialization_id, binding.channels, 'native_build')

    def body(self, binding):
        self._binding(binding)
        return PhysicalBodyBuildReceiptV1('physical-body-build-receipt-v1', binding.identity_hash,
            binding.source_closure_sha256, self.session.provider_materialization_id, binding.bodies, 'native_build')

    def policy(self, binding):
        self._binding(binding)
        return PhysicalBufferPolicyV1('physical-buffer-policy-v1', binding.identity_hash,
            self.session.provider_materialization_id, 'replace', 'each_native_step', 'clear_before_new_episode')

    def write(self, resolved):
        s = self.session
        s._require_reset()
        if type(resolved) is not ResolvedPhysicalBatchV1 or resolved.binding_sha256 != self.binding.identity_hash:
            raise ValueError('physical batch differs from materialized binding')
        context = resolved.input_batch.context
        if (resolved.accepted_receipt.context != context
                or resolved.accepted_receipt.batch_sha256 != resolved.input_batch.identity_hash
                or resolved.accepted_receipt.stage != 'accepted'
                or len(resolved.mapping_provenance) != int(bool(resolved.joints)) + int(bool(resolved.body_wrenches))
                or any(provenance != 'native_build' for provenance in resolved.mapping_provenance)):
            raise ValueError('physical batch lacks exact native build admission')
        if (context.boundary != s.state_boundary_identity() or context.generation != self.execution.generation
                or context.identity_hash in self.consumed or self.pending is not None):
            raise ValueError('physical batch is stale, duplicated or already pending')
        if (context.row != 0 or not math.isclose(context.duration_s, s._artifact.timebase.control_dt, abs_tol=1e-12)
                or not math.isclose(context.cadence_s, s._artifact.timebase.control_dt, abs_tol=1e-12)):
            raise ValueError('physical batch row or interval differs from session')
        view = s.snapshot_v2(scene=self.execution.scene,
            joint_bindings=self.execution.joint_bindings, frame_bindings=self.execution.frame_bindings,
            requirements=self.execution.requirements).view
        if view.boundary != context.boundary or view.sample_clock != context.clock:
            raise ValueError('physical batch clock differs from current state publication')
        admitted = prepare_physical_command_batch(self.execution.compiled, resolved.input_batch,
            expected_context=context, assessment=self.assessment(self.binding), state=view,
            joint_build_receipt=self.joints(self.binding) if resolved.input_batch.joint_efforts else None,
            body_build_receipt=self.body(self.binding) if resolved.input_batch.body_wrenches else None,
            buffer_policy=self.policy(self.binding) if any(
                item.contribution.persistence == 'hold_reapply' for item in
                (*resolved.input_batch.joint_efforts, *resolved.input_batch.body_wrenches)) else None)
        if admitted != resolved:
            raise ValueError('physical batch differs from independent session admission')
        if resolved.extensions or np.any(s._data.qfrc_applied) or np.any(s._data.xfrc_applied):
            raise ValueError('physical buffer is occupied or extension unsupported')
        if any(not bool(s._data.eq_active[index]) for index in self.equality_ids):
            raise ValueError('physical tendon equality is not active')
        values = np.zeros(s._model.nv, dtype=float)
        for item in resolved.joints:
            key = (item.entity_id, item.joint_id, item.dof_id)
            values[self.dofs[key]] += item.value * next(c.sign for c in self.binding.channels if c.target_key == key)
        raw_wrenches = resolved.input_batch.body_wrenches
        for item in raw_wrenches:
            key = (item.entity_id, item.body_id)
            needed = (item.expressed_in, item.point_frame, item.moment_reference_frame, self.body_frames[key])
            if any(frame not in self.frame_handles for frame in needed):
                raise ValueError('physical wrench frame has no native mapping')
        projected = self._project_current(values, raw_wrenches)
        if not np.isfinite(projected).all():
            raise ValueError('physical projection produced nonfinite generalized force')
        if np.any(s._data.qfrc_applied) or np.any(s._data.xfrc_applied):
            raise RuntimeError('physical force buffer changed before owned write')
        s._data.qfrc_applied[:] = projected
        self.pending = context.identity_hash
        self.pending_values = projected
        self.pending_joints = values
        self.pending_wrenches = raw_wrenches
        self.consumed.add(context.identity_hash)
        return PhysicalControlReceiptV1('physical-control-receipt-v1', context,
            resolved.input_batch.identity_hash, 'native_write_ack', resolved.accepted_receipt.contribution_ids,
            'mujoco-qfrc-applied', 'generalized-force')

    def _project_current(self, joints, wrenches):
        """Use fresh public kinematics and each declared frame at this substep."""
        values = np.array(joints, dtype=float, copy=True)
        if not wrenches:
            return values
        s = self.session
        if int(s._model.opt.integrator) != int(s._mj.mjtIntegrator.mjINT_IMPLICITFAST):
            raise ValueError('physical body wrench requires the verified MuJoCo implicitfast integrator')
        s._mj.mj_kinematics(s._model, s._data)
        s._mj.mj_comPos(s._model, s._data)
        self.kinematics_refreshes += 1
        from .common import pose
        poses = {}
        for item in wrenches:
            key = (item.entity_id, item.body_id)
            for frame in (item.expressed_in, item.point_frame, item.moment_reference_frame, self.body_frames[key]):
                if frame in poses:
                    continue
                kind, index = self.frame_handles[frame]
                if kind == 'body':
                    poses[frame] = pose(s._data.xpos[index], s._data.xquat[index])
                else:
                    quaternion = np.zeros(4)
                    s._mj.mju_mat2Quat(quaternion, s._data.site_xmat[index])
                    poses[frame] = pose(s._data.site_xpos[index], quaternion)
            origin, force, torque = resolve_body_wrench_at_poses(item, self.body_frames[key], poses)
            s._mj.mj_applyFT(s._model, s._data, np.asarray(force), np.asarray(torque),
                             np.asarray(origin), self.bodies[key], values)
        if not np.isfinite(values).all():
            raise ValueError('physical projection produced nonfinite generalized force')
        return values

    def refresh_substep(self):
        """Replace this port's contribution without accumulating or stealing a buffer."""
        s = self.session
        if self.pending is None or self.pending_values is None:
            raise RuntimeError('physical interval requires exactly one fresh batch')
        if not np.array_equal(s._data.qfrc_applied, self.pending_values) or np.any(s._data.xfrc_applied):
            raise RuntimeError('physical force buffer changed during owned interval')
        projected = self._project_current(self.pending_joints, self.pending_wrenches)
        if not np.array_equal(s._data.qfrc_applied, self.pending_values) or np.any(s._data.xfrc_applied):
            raise RuntimeError('physical force buffer changed during projection')
        s._data.qfrc_applied[:] = projected
        self.pending_values = projected

    def finish_interval(self):
        data = self.session._data
        if self.pending_values is not None:
            # Clear only slots that still contain the exact value owned by this
            # port. A concurrent foreign overwrite is left untouched and is a fault.
            owned = np.equal(data.qfrc_applied, self.pending_values)
            data.qfrc_applied[owned] = 0
        self.pending = None
        self.pending_values = None
        self.pending_joints = None
        self.pending_wrenches = ()
