"""F06 source-bound direct-effort port over public Isaac articulation I/O."""
from __future__ import annotations
import math

from ...artifacts.contracts import CapabilityAssessmentRowV1, CapabilityAssessmentV1
from ...controllers.canonical.physical_commands import PhysicalControlReceiptV1, PhysicalJointBuildReceiptV1
from .physical_control import PhysicalControlExecutionV1, ResolvedPhysicalBatchV1, prepare_physical_command_batch, _rotate


def preflight_physical_isaac(execution, artifact, source):
    if type(execution) is not PhysicalControlExecutionV1:
        raise TypeError('physical session requires an exact execution profile')
    execution.validate_source(scene=source.scene_definition, artifact_sha256=artifact.identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
    if execution.compiled.binding.bodies:
        raise ValueError('F06 Isaac direct-effort port does not admit body wrench')


class IsaacF06PhysicalPort:
    """Own one interval and revalidate the source-bound public mimic witness."""
    def __init__(self, session, execution):
        preflight_physical_isaac(execution, session._artifact, session._source)
        if session._execution_spec_v1.physics_profile != 'isaac-gpu-physx-pickcube-f06-v1':
            raise ValueError('physical port only admits the exact F06 Isaac profile')
        binding = execution.compiled.binding
        names = tuple(session._native_io_metadata.native_dof_names)
        expected = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2')
        if len(names) != 9 or set(names) != set(expected):
            raise ValueError('F06 native DOF names differ from the nine declared joints')
        facts = session._build_layout_facts or {}
        bootstrap = facts.get('native_public_bootstrap_receipt', {})
        witness = bootstrap.get('native_mimic_drive_witness', {})
        if (witness.get('schema_version') != 'isaac-f06-pickcube-native-mimic-drive-witness-v1'
                or witness.get('native_dof_order') != list(names)
                or witness.get('passive_mimic_dof') != 'finger_joint2'
                or witness.get('mimic_reference_joint') != 'finger_joint1'
                or witness.get('mimic_follower_joint') != 'finger_joint2'
                or witness.get('leader_max_effort_N') != 5.0):
            raise ValueError('F06 native public drive and mimic witness differs')
        axis_witness = facts.get('native_joint_axis_witness', {})
        axes = axis_witness.get('rows', {})
        if (axis_witness.get('schema_version') != 'f06-public-source-native-axis-witness-v1'
                or set(axes) != set(expected)
                or any(axes[name].get('kind') != ('revolute' if name.startswith('joint') else 'prismatic')
                       or not 0.0 <= float(axes[name].get('error_rad', float('nan'))) <= 1e-5
                       for name in expected)):
            raise ValueError('F06 USD axes differ from the public native Jacobian')
        drive_mode = ('disabled' if session._artifact.artifact_id == 'pickcube-f06-physical-effort-no-drive-v1'
                      else 'position')
        if session._artifact.artifact_id not in {'pickcube-f06-physical-effort-fixture-v1',
                                                 'pickcube-f06-physical-effort-no-drive-v1'}:
            raise ValueError('F06 physical port requires a versioned effort fixture')
        channels = {c.joint_id: c for c in binding.channels}
        if len(channels) != 9 or set(channels) != set(expected):
            raise ValueError('F06 physical channels do not cover nine unique joints')
        pose_rows = facts.get('native_kinematic_model_witness', {}).get('link_world_poses', ())
        poses = {row['name']: row for row in pose_rows}
        for i, name in enumerate(expected):
            channel = channels[name]
            parent = poses.get(channel.axis_frame.frame_id)
            if parent is None:
                raise ValueError('F06 channel axis parent lacks a public link pose')
            scene_axis = _rotate(tuple(parent['orientation_world_wxyz']), channel.axis)
            native_axis = axes[name]['native_axis_world']
            if sum((a-b)**2 for a, b in zip(scene_axis, native_axis, strict=True)) > 1e-10:
                raise ValueError('F06 Scene channel axis differs from the public native axis')
            arm = i < 7
            if (channel.entity_id != 'panda-v1' or channel.dof_id != 'dof0'
                    or session._source.joints.get(f'panda-v1/{name}') != name
                    or channel.kind != ('revolute' if arm else 'prismatic')
                    or channel.native_actuator != (name if arm else 'finger_joint1')
                    or channel.transmission_coefficient != (1. if arm else .5)
                    or channel.native_range != ((-250., 250.) if arm else (-5., 5.))
                    or channel.native_drive != drive_mode):
                raise ValueError('F06 physical channel differs from public native model')
        io = session._native_io
        if any(not callable(getattr(io, method, None)) for method in
               ('write_physical_effort', 'clear_physical_effort')):
            raise ValueError('F06 public effort I/O owner is unavailable')
        if drive_mode == 'disabled':
            disable = getattr(io, 'disable_f06_physical_drives', None)
            if not callable(disable):
                raise ValueError('F06 public native drive isolation is unavailable')
            session._build_layout_facts['physical_drive_override'] = disable()
        self.session, self.execution, self.binding = session, execution, binding
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
            'none', 'native_build', 'F06 public articulation and native mimic/drive witness', None, None)
            for name in ('sum', 'joint_effort', 'transmission', 'native_drive_state'))
        return CapabilityAssessmentV1('capability-assessment-v1', binding.identity_hash, 'native_build', rows)

    def joints(self, binding):
        self._binding(binding)
        return PhysicalJointBuildReceiptV1('physical-joint-build-receipt-v1', binding.identity_hash,
            binding.source_closure_sha256, self.session.provider_materialization_id, binding.channels, 'native_build')

    def policy(self, binding):
        self._binding(binding)
        raise ValueError('F06 held-load reapplication is not yet admitted')

    def write(self, resolved):
        s = self.session
        s._require_reset()
        if type(resolved) is not ResolvedPhysicalBatchV1 or resolved.binding_sha256 != self.binding.identity_hash:
            raise ValueError('physical batch differs from materialized F06 binding')
        context = resolved.input_batch.context
        if (context.boundary != s.state_boundary_identity() or context.generation != self.execution.generation
                or context.identity_hash in self.consumed or self.pending is not None or context.row != 0
                or not math.isclose(context.duration_s, s._artifact.timebase.control_dt, rel_tol=0, abs_tol=1e-12)
                or not math.isclose(context.cadence_s, s._artifact.timebase.control_dt, rel_tol=0, abs_tol=1e-12)):
            raise ValueError('physical batch is stale, duplicated or differs from the F06 interval')
        view = s.snapshot_v2(scene=self.execution.scene, joint_bindings=self.execution.joint_bindings,
            frame_bindings=self.execution.frame_bindings, requirements=self.execution.requirements).view
        if view.boundary != context.boundary or view.sample_clock != context.clock:
            raise ValueError('physical batch clock differs from the current F06 state')
        admitted = prepare_physical_command_batch(self.execution.compiled, resolved.input_batch,
            expected_context=context, assessment=self.assessment(self.binding), state=view,
            joint_build_receipt=self.joints(self.binding), buffer_policy=self.policy(self.binding) if any(
                item.contribution.persistence == 'hold_reapply' for item in resolved.input_batch.joint_efforts) else None)
        if admitted != resolved or resolved.body_wrenches or resolved.extensions:
            raise ValueError('physical batch differs from the admitted F06 effort-only route')
        values = {item.joint_id: float(item.value) for item in resolved.joints}
        if set(values) != {c.joint_id for c in self.binding.channels}:
            raise ValueError('F06 direct effort requires the complete named channel set')
        if not math.isclose(values['finger_joint1'], values['finger_joint2'], rel_tol=0, abs_tol=1e-12):
            raise ValueError('F06 mimic pair requires equal finger contributions')
        native = {f'joint{i}': values[f'joint{i}'] for i in range(1, 8)}
        native['finger_joint1'] = values['finger_joint1'] + values['finger_joint2']
        s._native_io.write_physical_effort(native)
        self.pending = context.identity_hash
        self.consumed.add(context.identity_hash)
        return PhysicalControlReceiptV1('physical-control-receipt-v1', context,
            resolved.input_batch.identity_hash, 'native_write_ack', resolved.accepted_receipt.contribution_ids,
            'isaac-f06-articulation-effort', 'generalized-force')

    def finish_interval(self):
        try:
            self.session._native_io.clear_physical_effort()
        finally:
            self.pending = None
