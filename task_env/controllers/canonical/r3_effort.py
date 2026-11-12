"""Compose the existing R3 Cartesian reference with the shared effort servo."""
from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
import math

from .contracts import digest, reference_pose_action
from .effort_servo import JointReferenceEffortControllerV1


PANDA_EFFORT_PROFILE_KINDS = MappingProxyType({
    'panda-direct-effort-v1': 'direct',
    'panda-joint-effort-reference-v1': 'joint',
    'panda-r3-effort-reference-v1': 'r3-pose',
    'panda-joint-mass-effort-v1': 'joint-mass',
    'panda-r3-mass-effort-v1': 'r3-mass-pose',
})
PANDA_SWITCHABLE_EFFORT_KINDS = ('joint', 'r3-pose')


def build_panda_direct_effort_controller(binding, writer, *, entity_id, joint_names,
                                         cadence_s, model_id, finger_action_id):
    """Bind the Panda's arm and paired finger action to declared effort channels."""
    from .physical_controller import LinearEffortControllerV1

    keys = tuple(f'{entity_id}/{name}' for name in joint_names)
    action_names = tuple(f'arm-effort-{i}' for i in range(1, 8)) + (finger_action_id,)
    matrix = tuple(tuple((1. if i == j else 0.) if i < 7 else (0.5 if j == 7 else 0.)
                         for j in range(8)) for i in range(len(joint_names)))
    return LinearEffortControllerV1.zero_bias(binding, writer_id=writer,
        channel_keys=keys, action_names=action_names, action_to_effort=matrix,
        cadence_s=cadence_s, model_id=model_id, selection_profile_id='panda-direct-effort-v1')


def resolve_panda_effort_options(profile_id, native_drive, parameters):
    """Resolve Controller-owned drive and reset options without provider policy."""
    kind = PANDA_EFFORT_PROFILE_KINDS[profile_id]
    if native_drive not in (None, 'position', 'disabled'):
        raise ValueError('unsupported Robot native drive selection')
    drive = native_drive or ('position' if kind == 'direct' else 'disabled')
    if kind != 'direct' and drive != 'disabled':
        raise ValueError('reference effort requires the isolated native drive fixture')
    switch = parameters.get('reset_selection', False)
    policy = parameters.get('action_space_policy', 'dynamic')
    if type(switch) is not bool or policy not in {'dynamic', 'fixed_semantic'}:
        raise ValueError('invalid physical reset selection or action-space policy')
    if not switch and policy != 'dynamic':
        raise ValueError('physical action-space policy requires reset selection')
    return kind, drive, switch, policy


def panda_reset_action_schema(kind):
    """Describe the selected reference input after a reset-scoped change."""
    if kind == 'r3-pose':
        from .contracts import REFERENCE_POSE_ACTION_SCHEMA
        return dict(REFERENCE_POSE_ACTION_SCHEMA)
    if kind == 'joint':
        return {'schema_id': 'physical-joint-reference-v1',
                'controller_kind': 'absolute_joint', 'dimension': 8}
    raise ValueError('unsupported physical controller reset selection')


class ConstrainedPairEffortControllerV1:
    """Project two finger efforts onto the declared equal-motion constraint."""
    def __init__(self, servo):
        if type(servo) is not JointReferenceEffortControllerV1:
            raise TypeError('paired effort requires the shared joint-reference servo')
        self.servo, self.binding, self.writer_id = servo, servo.binding, servo.writer_id
        self._channels, self.profile = servo._channels, servo.profile
        self.profile_id = servo.profile_id
        self.identity = digest({'schema': 'constrained-pair-effort-controller-v1',
                                'servo': servo.identity, 'projection': 'equal-pair-mean'})

    @property
    def action_shape(self):
        return self.servo.action_shape

    def compute(self, action, state, context):
        from dataclasses import replace
        batch = self.servo.compute(action, state, context)
        fingers = [x for x in batch.joint_efforts if x.joint_id in {'finger_joint1', 'finger_joint2'}]
        if len(fingers) != 2 or fingers[0].entity_id != fingers[1].entity_id:
            raise ValueError('paired effort projection requires the exact two finger contributions')
        common = .5 * (fingers[0].value + fingers[1].value)
        return replace(batch, joint_efforts=tuple(replace(x, value=common) if x in fingers else x
                                                  for x in batch.joint_efforts))


class R3ReferenceEffortControllerV1:
    """Resolve a world pose through R3, then emit one typed joint-effort batch.

    The injected R3 reference and effort servo are provider-neutral. The
    native adapter must independently prove that full-PD contributions do not
    duplicate active position drives.
    """
    def __init__(self, reference, servo, *, entity_id, end_frame_id, opening_range_m,
                 selection_profile_id=None):
        from .mass_matrix_effort import MassMatrixEffortControllerV1
        from .dynamic_mass_effort import DynamicMassEffortControllerV1
        if type(servo) not in (JointReferenceEffortControllerV1, ConstrainedPairEffortControllerV1,
                               MassMatrixEffortControllerV1, DynamicMassEffortControllerV1):
            raise TypeError('R3 effort composition requires a shared joint-reference effort servo')
        if (not callable(getattr(reference, 'reset', None))
                or not callable(getattr(reference, 'compute_reference', None))
                or not isinstance(getattr(reference, 'identity', None), str)):
            raise TypeError('R3 effort composition requires the existing R3 reference owner')
        if not entity_id or not end_frame_id or not math.isfinite(opening_range_m) or opening_range_m <= 0:
            raise ValueError('R3 effort composition requires a named frame and positive opening range')
        if servo.action_shape != (8,):
            raise ValueError('R3 effort servo needs seven joint references and one paired opening')
        self.reference, self.servo = reference, servo
        self.binding, self.writer_id = servo.binding, servo.writer_id
        self._channels = servo._channels
        self.profile_id = selection_profile_id
        self.model_requirement = getattr(getattr(servo, 'profile', None), 'model_requirement', None)
        self.entity_id, self.end_frame_id = entity_id, end_frame_id
        self.opening_range_m = float(opening_range_m)
        identity = {'schema': 'r3-reference-effort-controller-v1',
            'r3_identity': reference.identity, 'servo_identity': servo.identity,
            'entity_id': entity_id, 'end_frame_id': end_frame_id,
            'opening_range_m': self.opening_range_m}
        if selection_profile_id is not None:
            from ...artifacts.contracts import _name
            _name(selection_profile_id)
            if getattr(servo, 'profile_id', None) != selection_profile_id:
                raise ValueError('R3 reference and servo Controller selections differ')
            identity['selection_profile_id'] = selection_profile_id
        self.identity = digest(identity)
        self._episode_id = None
        self._next_step = None

    @property
    def action_shape(self):
        return (8,)

    @property
    def bind_model(self):
        """Expose only the wrapped servo's actual source-model capability."""
        bind = getattr(self.servo, 'bind_model', None)
        if not callable(bind):
            raise AttributeError('this R3 effort servo does not accept a dynamic model')
        return bind

    def reset_from_realized_state(self, state):
        """Initialize R3 memory at the actual newly published reset boundary."""
        if state.boundary.control_step != 0:
            raise ValueError('R3 effort reset requires the initial realized boundary')
        joints = {j.joint_id: j for j in state.joints if j.entity_id == self.entity_id}
        names = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2')
        frames = [f for f in state.frames if f.frame.entity_id == self.entity_id
                  and f.frame.frame_id == self.end_frame_id]
        if set(joints) != set(names) or len(frames) != 1:
            raise ValueError('R3 effort reset requires nine Panda joints and its end frame')
        q = {f'panda-v1/{name}': float(joints[name].position[0]) for name in names}
        qd = {f'panda-v1/{name}': float(joints[name].velocity[0]) for name in names}
        if not all(math.isfinite(x) for x in (*q.values(), *qd.values())):
            raise ValueError('R3 effort reset state contains nonfinite joint values')
        adapted = SimpleNamespace(control_step=0, joint_position=q, joint_velocity=qd,
                                  pose_world={'panda-v1/ee': frames[0].pose_world})
        self.reference.reset(adapted)
        self._episode_id, self._next_step = state.boundary.episode_id, 0

    def compute(self, action, state, context):
        if state.boundary != context.boundary or state.sample_clock != context.clock:
            raise ValueError('R3 effort state is stale or foreign')
        requested = reference_pose_action(action)
        joints = {j.joint_id: j for j in state.joints if j.entity_id == self.entity_id}
        names = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2')
        frames = [f for f in state.frames if f.frame.entity_id == self.entity_id
                  and f.frame.frame_id == self.end_frame_id]
        if set(joints) != set(names) or len(frames) != 1:
            raise ValueError('R3 effort requires exactly nine Panda joints and its end frame')
        q = {f'panda-v1/{name}': float(joints[name].position[0]) for name in names}
        qd = {f'panda-v1/{name}': float(joints[name].velocity[0]) for name in names}
        if not all(math.isfinite(x) for x in (*q.values(), *qd.values())):
            raise ValueError('R3 effort state contains nonfinite joint values')
        adapted = SimpleNamespace(control_step=context.boundary.control_step, joint_position=q,
                                  joint_velocity=qd, pose_world={'panda-v1/ee': frames[0].pose_world})
        if self._episode_id != context.boundary.episode_id:
            if context.boundary.control_step != 0:
                raise ValueError('R3 effort requires the initial boundary for a new episode')
            self.reference.reset(adapted)
            self._episode_id, self._next_step = context.boundary.episode_id, 0
        if self._next_step != context.boundary.control_step:
            raise ValueError('R3 effort reference boundary is duplicated or out of order')
        target = self.reference.compute_reference(adapted, requested)
        opening = .5 * (float(target.canonical_action.interpreted_values[-1]) + 1.) * self.opening_range_m
        refs = tuple(float(target.arm_position[f'panda-v1/joint{i}']) for i in range(1, 8)) + (opening,)
        # R3 has advanced its memory; a later admission failure faults the Env
        # rather than permitting the same boundary to be replayed.
        self._next_step += 1
        return self.servo.compute(refs, state, context)


def build_panda_effort_profile(direct_execution, *, kind, cadence_s, end_frame_id,
                               source_xml=None, tcp_profile=None, config=None, artifact_hash=None, r3_profile=None,
                               joint_velocity_limit_rad_s=None, mass_model=None,
                               dynamic_parameters=None):
    """Compose a Panda effort profile from source-admitted controller inputs."""
    from dataclasses import replace
    profile_ids = {value: key for key, value in PANDA_EFFORT_PROFILE_KINDS.items()}
    if kind not in profile_ids:
        raise ValueError('unknown Panda effort profile')
    if dynamic_parameters is not None:
        from .dynamic_mass_effort import validate_reset_effort_parameters
        if mass_model is not None or kind not in PANDA_SWITCHABLE_EFFORT_KINDS:
            raise ValueError('dynamic effort profile requires a joint or pose reference')
        validate_reset_effort_parameters(dynamic_parameters)

    def selected(execution):
        return replace(execution, selection_profile_id=profile_ids[kind])

    if kind == 'direct':
        return selected(direct_execution)
    reference = None
    if kind in {'r3-pose', 'r3-mass-pose'}:
        from .production_r3 import ProductionCanonicalPandaControllerR3
        from .kinematics import PandaKinematics
        model = PandaKinematics(source_xml, tcp_profile=tcp_profile)
        reference = ProductionCanonicalPandaControllerR3.create_arm_reference(
            model, artifact_hash=artifact_hash, config=config, control_dt=cadence_s,
            profile=r3_profile, joint_velocity_limit_rad_s=joint_velocity_limit_rad_s)
    if dynamic_parameters is not None:
        return selected(build_dynamic_reference_effort_execution(
            direct_execution, reference_kind=kind, cadence_s=cadence_s,
            r3_reference=reference, end_frame_id=end_frame_id,
            selection_profile_id=profile_ids[kind], **dynamic_parameters))
    if kind in {'joint-mass', 'r3-mass-pose'}:
        if mass_model is None:
            return selected(build_dynamic_reference_effort_execution(
                direct_execution, reference_kind='r3-pose' if kind == 'r3-mass-pose' else 'joint',
                cadence_s=cadence_s, r3_reference=reference, end_frame_id=end_frame_id,
                kp=20., kd=2., mass_only=True, selection_profile_id=profile_ids[kind]))
        from .mass_matrix_effort import build_mass_effort_execution
        return selected(build_mass_effort_execution(
            direct_execution, **mass_model, use_pose_reference=kind == 'r3-mass-pose',
            r3_reference=reference, end_frame_id=end_frame_id, selection_profile_id=profile_ids[kind]))
    if mass_model is not None:
        raise ValueError('mass model supplied to non-mass effort profile')
    return selected(build_reference_effort_execution(
        direct_execution, reference_kind=kind, r3_reference=reference, end_frame_id=end_frame_id,
        selection_profile_id=profile_ids[kind]))


def _reference_effort_contract(direct_execution, reference_kind, r3_reference, end_frame_id):
    """Validate the shared binding and declare the state required by a reference."""
    from ...artifacts.state import StateFieldRequirement, StateRequirements
    from .production_r3 import _ProductionR3ArmReference
    from ...runtime.sessions.physical_control import PhysicalControlExecutionV1
    if type(direct_execution) is not PhysicalControlExecutionV1:
        raise TypeError('reference effort profile requires a typed direct execution')
    binding = direct_execution.compiled.binding
    if binding.bodies or len(binding.channels) != 9 or any(c.native_drive != 'disabled' for c in binding.channels):
        raise ValueError('reference effort profile requires nine isolated native drive channels')
    if reference_kind not in {'joint', 'r3-pose'}:
        raise ValueError('unknown reference effort input kind')
    if reference_kind == 'r3-pose' and not isinstance(r3_reference, _ProductionR3ArmReference):
        raise TypeError('pose effort profile requires the existing production R3 reference')
    channels = binding.channels
    entity = channels[0].entity_id
    expected = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2')
    if tuple(c.joint_id for c in channels) != expected or any(c.entity_id != entity for c in channels):
        raise ValueError('reference effort profile requires ordered Panda channels')
    owner = channels[0].owner_ids[0]
    if any(c.owner_ids != (owner,) for c in channels):
        raise ValueError('reference effort profile requires one common writer')
    requirements = direct_execution.requirements
    if reference_kind == 'r3-pose':
        frame_requirement = StateFieldRequirement('state-field-requirement-v1', 'frame_pose_world',
            'frame', entity, end_frame_id, 'required', 'evaluation_boundary',
            'meter+quaternion_wxyz', 'frame_pose_query')
        requirements = StateRequirements('state-requirements-v1', 'controller', owner,
                                          (*requirements.requirements, frame_requirement))
    return binding, channels, entity, owner, requirements


def build_reference_effort_execution(direct_execution, *, reference_kind, r3_reference=None,
                                     end_frame_id='ee', opening_range_m=.08,
                                     kp=(20., 20., 20., 20., 10., 10., 10., 50., 50.),
                                     kd=(2., 2., 2., 2., 1., 1., 1., 4., 4.),
                                     selection_profile_id=None):
    """Build one named joint-reference or R3 pose-reference effort writer.

    The exact native drive isolation remains a session admission requirement;
    constructing this provider-free profile does not prove it occurred.
    """
    from dataclasses import replace
    from .model import AffineJointBiasModelV1, ControllerModelRequirementV1
    from .effort_servo import JointReferenceEffortProfileV1
    binding, channels, entity, owner, requirements = _reference_effort_contract(
        direct_execution, reference_kind, r3_reference, end_frame_id)
    if len(kp) != 9 or len(kd) != 9:
        raise ValueError('reference effort gains must cover nine channels')
    keys = tuple(f'{entity}/{channel.joint_id}' for channel in channels)
    units = ('N*m',)*7 + ('N',)*2
    source = binding.source_id
    cadence = direct_execution.controllers[0].model.requirement.cadence_s
    requirement = ControllerModelRequirementV1('controller-model-requirement-v1',
        'panda-reference-effort-affine-pd-v1', 'geochora', 'v1', 'stdlib', source,
        binding.source_closure_sha256, keys, ('rad',)*7 + ('m',)*2, 'joint_bias', units,
        'joint-axis', 'evaluation_boundary', cadence, 0., 'pure_no_physics_step', owner, 'none', 'required')
    matrix = tuple(tuple((1. if i == j else 0.) if i < 7 else (.5 if j == 7 else 0.)
                         for j in range(8)) for i in range(9))
    profile = JointReferenceEffortProfileV1('joint-reference-effort-profile-v1', owner,
        tuple(f'joint-reference-{i}' for i in range(1, 8)) + ('paired-opening',), keys,
        matrix, tuple(kp), tuple(kd), requirement)
    model = AffineJointBiasModelV1('affine-joint-bias-model-v1', requirement,
        (0.,)*9, tuple(-x for x in kp), tuple(-x for x in kd))
    servo = ConstrainedPairEffortControllerV1(JointReferenceEffortControllerV1(
        profile, binding, model, selection_profile_id=selection_profile_id))
    if reference_kind == 'r3-pose':
        controller = R3ReferenceEffortControllerV1(r3_reference, servo, entity_id=entity,
            end_frame_id=end_frame_id, opening_range_m=opening_range_m,
            selection_profile_id=selection_profile_id)
    else:
        controller = servo
    return replace(direct_execution, controllers=(controller,), requirements=requirements)


def build_dynamic_reference_effort_execution(direct_execution, *, reference_kind, cadence_s,
                                             r3_reference=None, end_frame_id='ee',
                                             kp=120., kd=22., finger_kp=1200., finger_kd=35.,
                                             mass_only=False, selection_profile_id=None):
    """Build a source-dynamics joint or R3 reference from the existing binding."""
    from dataclasses import replace
    from .dynamic_mass_effort import DynamicMassEffortControllerV1
    binding, _, entity, _, requirements = _reference_effort_contract(
        direct_execution, reference_kind, r3_reference, end_frame_id)
    servo = DynamicMassEffortControllerV1(binding, cadence_s=cadence_s,
        kp=kp, kd=kd, finger_kp=finger_kp, finger_kd=finger_kd, mass_only=mass_only,
        selection_profile_id=selection_profile_id)
    if reference_kind == 'r3-pose':
        controller = R3ReferenceEffortControllerV1(r3_reference, servo,
            entity_id=entity, end_frame_id=end_frame_id, opening_range_m=.08,
            selection_profile_id=selection_profile_id)
    else:
        controller = servo
    return replace(direct_execution, controllers=(controller,), requirements=requirements)
