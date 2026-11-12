"""F06 source-bound direct-effort port over public Isaac articulation I/O."""
from __future__ import annotations
import math

from ...artifacts.contracts import CapabilityAssessmentRowV1, CapabilityAssessmentV1
from ...controllers.canonical.physical_commands import (
    PhysicalBufferPolicyV1, PhysicalControlReceiptV1, PhysicalJointBuildReceiptV1,
)
from .physical_control import PhysicalControlExecutionV1, ResolvedPhysicalBatchV1, prepare_physical_command_batch, _rotate


def build_isaac_panda_effort_execution(robot, scene, artifact, source, *, native_drive):
    """Bind the admitted USD Panda transmissions to the Robot's effort Controller."""
    from ...robots.panda import PandaEffortSourceLayout
    from .source import (UsdRuntimeSourceV1, position_joint_bindings_from_artifact,
                         position_frame_bindings_from_artifact)

    if type(source) is not UsdRuntimeSourceV1:
        raise TypeError('Isaac effort requires a USD RuntimeSource')
    source.validate()
    if (source.source_closure_digest != 'dc2a87a74963e0ec10f3cf98b3e33cc87226350dde78aeddbc88244a0fbdafc6'
            or source.task_artifact.identity_hash != artifact.identity_hash
            or source.scene_definition.identity_hash != scene.identity_hash):
        raise ValueError('Isaac effort requires the admitted source and Artifact')
    expected_artifacts = {'position': 'pickcube-f06-physical-effort-fixture-v1',
                          'disabled': 'pickcube-f06-physical-effort-no-drive-v1'}
    if expected_artifacts.get(native_drive) != artifact.artifact_id:
        raise ValueError('Isaac effort drive differs from its admitted Artifact')
    names = robot.physical_joint_names()
    layout = PandaEffortSourceLayout(
        tuple(name if i < 7 else 'finger_joint1' for i, name in enumerate(names)),
        tuple(f'f06-arm-{i+1}' if i < 7 else 'f06-mimic-pair' for i in range(9)),
        'f06-panda-direct-effort-assembly', 'f06-panda-direct-effort-components',
        'f06-direct-effort-zero-bias-v1', 'finger-pair-effort')
    return robot.build_direct_effort_execution(
        scene, artifact, source, entity_id=robot.uid, native_drive=native_drive,
        native_ranges=((-250., 250.),) * 7 + ((-5., 5.),), layout=layout,
        joint_bindings=position_joint_bindings_from_artifact(scene, artifact, source),
        frame_bindings=position_frame_bindings_from_artifact(artifact, source))


def preflight_physical_isaac(execution, artifact, source):
    if type(execution) is not PhysicalControlExecutionV1:
        raise TypeError('physical session requires an exact execution profile')
    execution.validate_source(scene=source.scene_definition, artifact_sha256=artifact.identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
    if execution.requires_source_dynamics:
        from ...environment.types import StageUnavailableError
        raise StageUnavailableError('Isaac physical adapter has no source dynamics model')
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


class IsaacSimpleEffortPhysicalPort:
    """Source-bound scalar effort port shared by the G05 task subjects."""

    def __init__(self, session, execution):
        preflight_physical_isaac(execution, session._artifact, session._source)
        if session._execution_spec_v1.physics_profile != 'isaac-gpu-physx-g05-5c-effort-v1':
            raise ValueError('simple effort port only admits the exact G05 Isaac profile')
        binding = execution.compiled.binding
        if not binding.channels:
            raise ValueError('G05 effort port requires at least one declared joint channel')
        if any(channel.native_drive not in {'disabled', 'passive'} for channel in binding.channels):
            raise ValueError('G05 effort port requires native drives to be disabled or passive')
        names = tuple(session._native_io_metadata.native_dof_names)
        if set(names) != set(session._source.joint_targets.values()):
            raise ValueError('G05 native DOFs differ from the exact source joint map')
        by_key = {channel.target_key: channel for channel in binding.channels}
        if len(by_key) != len(binding.channels):
            raise ValueError('G05 physical channels are not unique')
        # The canonical binding carries the source actuator declaration while
        # the USD source carries only the native joint/DOF map.  Re-read the
        # immutable source XML here so the actuator name is checked against the
        # source declaration and its actual joint, rather than against a set
        # containing the value being checked.
        import xml.etree.ElementTree as ET
        try:
            source_root = ET.fromstring(session._source.scene_source.xml)
        except (AttributeError, ET.ParseError) as error:
            raise ValueError('G05 source XML is unavailable for actuator admission') from error
        source_actuators = {}
        for motor in source_root.findall('./actuator/motor'):
            joint_name = motor.get('joint')
            actuator_name = motor.get('name')
            if not joint_name or not actuator_name or joint_name in source_actuators:
                raise ValueError('G05 source actuator declarations are missing or ambiguous')
            source_actuators[joint_name] = actuator_name
        for channel in binding.channels:
            semantic = f'{channel.entity_id}/{channel.joint_id}'
            native_joint = session._source.joints.get(semantic)
            expected_actuator = source_actuators.get(channel.joint_id)
            if native_joint is None or native_joint != session._source.joint_targets.get(semantic):
                raise ValueError(f'G05 physical channel is absent from the USD source: {semantic}')
            if expected_actuator is None or channel.native_actuator != expected_actuator:
                raise ValueError(
                    f'G05 native actuator differs from the source declaration for {semantic}: '
                    f'actual={channel.native_actuator!r}, expected={expected_actuator!r}'
                )
        io = session._native_io
        if any(not callable(getattr(io, method, None)) for method in
               ('write_physical_effort', 'clear_physical_effort')):
            raise ValueError('G05 public effort I/O owner is unavailable')
        self.session, self.execution, self.binding = session, execution, binding
        self._channel_by_key = by_key
        self.pending = None
        self.consumed = set()

    def _binding(self, binding):
        self.session._require_open()
        if binding != self.binding:
            raise ValueError('physical port binding differs from materialized G05 profile')

    def assessment(self, binding):
        self._binding(binding)
        rows = tuple(CapabilityAssessmentRowV1(
            'capability-assessment-row-v1', name,
            f'binding:{binding.identity_hash}', 'required', 'supported', 'implemented', 'available',
            'none', 'native_build', 'G05 source-bound scalar PhysX effort route', None, None,
        ) for name in ('sum', 'joint_effort', 'transmission', 'native_drive_state', 'hold_reapply'))
        return CapabilityAssessmentV1('capability-assessment-v1', binding.identity_hash, 'native_build', rows)

    def joints(self, binding):
        self._binding(binding)
        return PhysicalJointBuildReceiptV1(
            'physical-joint-build-receipt-v1', binding.identity_hash,
            binding.source_closure_sha256, self.session.provider_materialization_id,
            binding.channels, 'native_build',
        )

    def policy(self, binding):
        self._binding(binding)
        return PhysicalBufferPolicyV1(
            'physical-buffer-policy-v1', binding.identity_hash,
            self.session.provider_materialization_id, 'replace',
            'each_native_step', 'clear_before_new_episode',
        )

    def write(self, resolved):
        s = self.session
        s._require_reset()
        if type(resolved) is not ResolvedPhysicalBatchV1 or resolved.binding_sha256 != self.binding.identity_hash:
            raise ValueError('physical batch differs from materialized G05 binding')
        context = resolved.input_batch.context
        if (context.boundary != s.state_boundary_identity() or context.generation != self.execution.generation
                or context.identity_hash in self.consumed or self.pending is not None or context.row != 0
                or not math.isclose(context.duration_s, s._artifact.timebase.control_dt, rel_tol=0, abs_tol=1e-12)
                or not math.isclose(context.cadence_s, s._artifact.timebase.control_dt, rel_tol=0, abs_tol=1e-12)):
            raise ValueError('physical batch is stale, duplicated or differs from the G05 interval')
        view = s.snapshot_v2(scene=self.execution.scene, joint_bindings=self.execution.joint_bindings,
            frame_bindings=self.execution.frame_bindings, requirements=self.execution.requirements).view
        if view.boundary != context.boundary or view.sample_clock != context.clock:
            raise ValueError('physical batch clock differs from the current G05 state')
        has_hold = any(item.contribution.persistence == 'hold_reapply'
                       for item in resolved.input_batch.joint_efforts)
        admitted = prepare_physical_command_batch(
            self.execution.compiled, resolved.input_batch,
            expected_context=context, assessment=self.assessment(self.binding), state=view,
            joint_build_receipt=self.joints(self.binding),
            buffer_policy=self.policy(self.binding) if has_hold else None,
        )
        if admitted != resolved or resolved.body_wrenches or resolved.extensions:
            raise ValueError('physical batch differs from the admitted G05 effort-only route')
        resolved_keys = {
            (item.entity_id, item.joint_id, item.dof_id)
            for item in resolved.joints
        }
        if resolved_keys != set(self._channel_by_key):
            raise ValueError('G05 direct effort requires the complete declared wheel/hinge channel set')
        native = {name: 0.0 for name in s._native_io_metadata.native_dof_names}
        for item in resolved.joints:
            target_key = (item.entity_id, item.joint_id, item.dof_id)
            channel = self._channel_by_key[target_key]
            semantic = f'{channel.entity_id}/{channel.joint_id}'
            native_name = s._source.joints[semantic]
            native[native_name] = float(channel.sign) * float(item.value) / float(channel.transmission_coefficient)
        s._native_io.write_physical_effort(native)
        self.pending = context.identity_hash
        self.consumed.add(context.identity_hash)
        return PhysicalControlReceiptV1(
            'physical-control-receipt-v1', context,
            resolved.input_batch.identity_hash, 'native_write_ack',
            resolved.accepted_receipt.contribution_ids,
            'isaac-g05-articulation-effort', 'generalized-force',
        )

    def finish_interval(self):
        try:
            self.session._native_io.clear_physical_effort()
        finally:
            self.pending = None


__all__ = ['IsaacF06PhysicalPort', 'IsaacSimpleEffortPhysicalPort', 'preflight_physical_isaac']
