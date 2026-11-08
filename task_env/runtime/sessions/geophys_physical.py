"""Source-bound generalized-effort port over GeoPhys' public host setter."""
from __future__ import annotations
import math
import numpy as np

from ...artifacts.contracts import CapabilityAssessmentRowV1, CapabilityAssessmentV1
from ...controllers.canonical.physical_commands import (
    PhysicalControlReceiptV1, PhysicalJointBuildReceiptV1,
)
from .physical_control import PhysicalControlExecutionV1, ResolvedPhysicalBatchV1, prepare_physical_command_batch


def preflight_physical_geophys(execution, artifact, source):
    """Reject unsupported physical declarations before native materialization."""
    if type(execution) is not PhysicalControlExecutionV1:
        raise TypeError('physical session requires an exact execution profile')
    execution.validate_source(scene=source.scene_definition, artifact_sha256=artifact.identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
    if execution.compiled.binding.bodies:
        raise ValueError('GeoPhys physical port does not admit body wrench')


class GeoPhysPhysicalPort:
    """One scalar materialization's exclusively owned generalized-effort interval."""
    def __init__(self, session, execution):
        if type(execution) is not PhysicalControlExecutionV1:
            raise TypeError('physical session requires an exact execution profile')
        binding = execution.compiled.binding
        execution.validate_source(scene=session._source.scene_definition,
            artifact_sha256=session._artifact.identity_hash, source_id=session._source.source_id,
            source_closure_sha256=session._source.source_closure_digest, source=session._source)
        if binding.bodies:
            raise ValueError('GeoPhys physical port does not admit body wrench')
        if session._mixed_actuator_plan is not None:
            raise ValueError('GeoPhys physical port requires an unshared scalar session')
        model = session._build_layout_facts['effective_physical_model']
        if model.get('schema_version') != 'rigid-model-snapshot-v1':
            raise ValueError('GeoPhys physical port requires the effective model snapshot')
        joints = {j['name']: j for j in model['joints']}
        actuators = {a['name']: a for a in model['actuators']}
        definitions = {(a.entity_id, j.joint_id): j for a in execution.scene.articulations or () for j in a.joints}
        drive_mode = ('disabled' if getattr(session._artifact, 'artifact_id', None)
                      == 'pickcube-mjcf-physical-effort-no-drive-v1' else 'position')
        source = session._source
        direct_motor = (bool(getattr(source, 'torque_actuators', {})) and not getattr(source, 'position_actuators', {})
                        and all(c.native_drive == 'disabled' for c in binding.channels))
        if direct_motor:
            if ({f'{c.entity_id}/{c.joint_id}': c.native_actuator for c in binding.channels}
                    != dict(source.torque_actuators) or source.joint_targets or source.open_actuators):
                raise ValueError('physical motor bindings must exactly cover the source actuators')
            drive_mode = 'disabled'
            bodies = {row['name']: row for row in model['bodies']}
            for subject in execution.subjects:
                if subject.root_mode == 'fixed':
                    row = bodies.get(subject.root_frame.frame_id)
                    if row is None or int(row['parent_id']) >= 0 or int(row['joint_count']) != 0:
                        raise ValueError('physical motor subject root is not a fixed world child')
        groups, dofs = {}, {}
        for channel in binding.channels:
            name = session._source.joints.get(f'{channel.entity_id}/{channel.joint_id}')
            row = joints.get(name)
            definition = definitions.get((channel.entity_id, channel.joint_id))
            if (row is None or definition is None or int(row['type']) != (2 if channel.kind == 'revolute' else 3)
                    or channel.dof_id != 'dof0' or not np.allclose(row['axis_child'], definition.axis, rtol=0, atol=1e-6)):
                raise ValueError('GeoPhys compiled joint kind, axis, or source differs')
            address = int(row['dof_address'])
            if address < 0 or address in dofs.values():
                raise ValueError('GeoPhys physical channels alias an invalid native DOF')
            dofs[channel.target_key] = address
            groups.setdefault((channel.entity_id, channel.transmission_id), []).append((channel, int(row['id'])))
        used = set()
        for group in groups.values():
            first = group[0][0]
            actuator = actuators.get(first.native_actuator)
            if actuator is None or int(actuator['id']) in used:
                raise ValueError('GeoPhys compiled actuator missing or duplicated')
            if direct_motor:
                if (int(actuator['enabled']) != 1 or int(actuator['force_limited']) != 0
                        or int(actuator['control_limited']) != 1
                        or not np.allclose(actuator['control_range'], first.native_range, rtol=1e-6, atol=1e-6)
                        or not math.isclose(float(actuator['gear0']), 1., abs_tol=1e-6)
                        or int(actuator['bias_type']) != 0 or int(actuator['gain_type']) != 0
                        or int(actuator['dynamics_type']) != 0
                        or not math.isclose(float(actuator['gain_parameters'][0]), 1., abs_tol=1e-6)):
                    raise ValueError('GeoPhys compiled direct motor range, gear or gain differs')
            elif (int(actuator['enabled']) != 1
                    or int(actuator['force_limited']) != 1 or not np.allclose(actuator['force_range'], first.native_range, rtol=1e-6, atol=1e-6)
                    or not math.isclose(float(actuator['gear0']), 1., abs_tol=1e-6)
                    or int(actuator['bias_type']) != 1 or int(actuator['gain_type']) != 0
                    or int(actuator['dynamics_type']) != 0 or float(actuator['gain_parameters'][0]) <= 0
                    or float(actuator['bias_parameters'][1]) >= 0 or float(actuator['bias_parameters'][2]) > 0
                    or any(c.native_drive != drive_mode for c, _ in group)):
                raise ValueError('GeoPhys compiled actuator/position drive differs')
            used.add(int(actuator['id']))
            trn, target = int(actuator['transmission_type']), int(actuator['transmission_id'])
            if trn == 0:
                if len(group) != 1 or target != group[0][1] or first.transmission_coefficient != 1:
                    raise ValueError('GeoPhys joint transmission differs')
            elif trn == 1:
                tendon = next((t for t in model['tendons'] if int(t['id']) == target), None)
                if tendon is None:
                    raise ValueError('GeoPhys tendon transmission is absent')
                start, count = int(tendon['wrap_address']), int(tendon['wrap_count'])
                actual = sorted((int(w['joint_id']), float(w['coefficient'])) for w in model['tendon_wraps'][start:start+count])
                expected = sorted((joint, channel.transmission_coefficient) for channel, joint in group)
                matches = [eq for eq in model['equalities'] if bool(eq['active'])
                    and {int(eq['joint_id_a']), int(eq['joint_id_b'])} == {joint for _, joint in group}
                    and np.allclose(eq['polycoef'], (0, 1, 0, 0, 0), rtol=0, atol=1e-6)]
                if len(group) != 2 or actual != expected or len(matches) != 1:
                    raise ValueError('GeoPhys paired tendon/equality differs')
            else:
                raise ValueError('GeoPhys unsupported transmission')
        if direct_motor and used != {int(a['id']) for a in model['actuators']}:
            raise ValueError('physical motor source contains undeclared actuators')
        if drive_mode == 'disabled':
            session._build_layout_facts['physical_drive_override'] = (
                session._boundary.isolate_actuator_outputs_for_physical_fixture(tuple(sorted(used))))
        self.session, self.execution, self.binding, self.dofs = session, execution, binding, dofs
        self.pending = None
        self.consumed = set()

    def _binding(self, binding):
        self.session._require_open()
        if binding != self.binding:
            raise ValueError('physical port binding differs from materialized profile')

    def assessment(self, binding):
        self._binding(binding)
        rows = tuple(CapabilityAssessmentRowV1('capability-assessment-row-v1', name,
            f'binding:{binding.identity_hash}', 'required', 'supported', 'implemented', 'available',
            'none', 'native_build', 'GeoPhys effective named model and public effort setter', None, None)
            for name in ('sum', 'joint_effort', 'transmission', 'native_drive_state'))
        return CapabilityAssessmentV1('capability-assessment-v1', binding.identity_hash, 'native_build', rows)

    def joints(self, binding):
        self._binding(binding)
        return PhysicalJointBuildReceiptV1('physical-joint-build-receipt-v1', binding.identity_hash,
            binding.source_closure_sha256, self.session.provider_materialization_id, binding.channels, 'native_build')

    def policy(self, binding):
        self._binding(binding)
        raise ValueError('GeoPhys held-load reapplication is not yet admitted')

    def write(self, resolved):
        s = self.session
        s._require_reset()
        if type(resolved) is not ResolvedPhysicalBatchV1 or resolved.binding_sha256 != self.binding.identity_hash:
            raise ValueError('physical batch differs from materialized binding')
        context = resolved.input_batch.context
        if (context.boundary != s.state_boundary_identity() or context.generation != self.execution.generation
                or context.identity_hash in self.consumed or self.pending is not None or context.row != 0
                or not math.isclose(context.duration_s, s._artifact.timebase.control_dt, rel_tol=0, abs_tol=1e-12)
                or not math.isclose(context.cadence_s, s._artifact.timebase.control_dt, rel_tol=0, abs_tol=1e-12)):
            raise ValueError('physical batch is stale, duplicated or differs from session interval')
        view = s.snapshot_v2(scene=self.execution.scene, joint_bindings=self.execution.joint_bindings,
            frame_bindings=self.execution.frame_bindings, requirements=self.execution.requirements).view
        if view.boundary != context.boundary or view.sample_clock != context.clock:
            raise ValueError('physical batch clock differs from current state publication')
        admitted = prepare_physical_command_batch(self.execution.compiled, resolved.input_batch,
            expected_context=context, assessment=self.assessment(self.binding), state=view,
            joint_build_receipt=self.joints(self.binding), buffer_policy=self.policy(self.binding) if any(
                item.contribution.persistence == 'hold_reapply' for item in resolved.input_batch.joint_efforts) else None)
        if admitted != resolved or resolved.body_wrenches or resolved.extensions:
            raise ValueError('physical batch differs from admitted GeoPhys effort-only route')
        n_dof = len(s._initial.qvel)
        values = np.zeros(n_dof, dtype=np.float64)
        signs = {c.target_key: c.sign for c in self.binding.channels}
        for item in resolved.joints:
            key = (item.entity_id, item.joint_id, item.dof_id)
            values[self.dofs[key]] += item.value * signs[key]
        s._boundary.write_generalized_effort(values)
        self.pending = context.identity_hash
        self.consumed.add(context.identity_hash)
        return PhysicalControlReceiptV1('physical-control-receipt-v1', context,
            resolved.input_batch.identity_hash, 'native_write_ack', resolved.accepted_receipt.contribution_ids,
            'geophys-qfrc-applied', 'generalized-force')

    def finish_interval(self):
        try:
            self.session._boundary.clear_generalized_effort()
        finally:
            self.pending = None
