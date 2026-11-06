"""Compose the existing R3 Cartesian reference with the shared effort servo."""
from __future__ import annotations

from types import SimpleNamespace
import math

from .contracts import digest, reference_pose_action
from .effort_servo import JointReferenceEffortControllerV1


class ConstrainedPairEffortControllerV1:
    """Project two finger efforts onto the declared equal-motion constraint."""
    def __init__(self, servo):
        if type(servo) is not JointReferenceEffortControllerV1:
            raise TypeError('paired effort requires the shared joint-reference servo')
        self.servo, self.binding, self.writer_id = servo, servo.binding, servo.writer_id
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
    def __init__(self, reference, servo, *, entity_id, end_frame_id, opening_range_m):
        from .mass_matrix_effort import MassMatrixEffortControllerV1
        if type(servo) not in (JointReferenceEffortControllerV1, ConstrainedPairEffortControllerV1,
                               MassMatrixEffortControllerV1):
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
        self.entity_id, self.end_frame_id = entity_id, end_frame_id
        self.opening_range_m = float(opening_range_m)
        self.identity = digest({'schema': 'r3-reference-effort-controller-v1',
            'r3_identity': reference.identity, 'servo_identity': servo.identity,
            'entity_id': entity_id, 'end_frame_id': end_frame_id,
            'opening_range_m': self.opening_range_m})
        self._episode_id = None
        self._next_step = None

    @property
    def action_shape(self):
        return (8,)

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


def build_reference_effort_execution(direct_execution, *, reference_kind, r3_reference=None,
                                     end_frame_id='ee', opening_range_m=.08,
                                     kp=(20., 20., 20., 20., 10., 10., 10., 50., 50.),
                                     kd=(2., 2., 2., 2., 1., 1., 1., 4., 4.)):
    """Build one named joint-reference or R3 pose-reference effort writer.

    The exact native drive isolation remains a session admission requirement;
    constructing this provider-free profile does not prove it occurred.
    """
    from dataclasses import replace
    from ...artifacts.state import StateFieldRequirement, StateRequirements
    from .model import AffineJointBiasModelV1, ControllerModelRequirementV1
    from .effort_servo import JointReferenceEffortProfileV1
    from ..canonical.production_r3 import _ProductionR3ArmReference
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
    if len(kp) != 9 or len(kd) != 9:
        raise ValueError('reference effort gains must cover nine channels')
    keys = tuple(f'{entity}/{name}' for name in expected)
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
    servo = ConstrainedPairEffortControllerV1(JointReferenceEffortControllerV1(profile, binding, model))
    requirements = direct_execution.requirements
    if reference_kind == 'r3-pose':
        frame_requirement = StateFieldRequirement('state-field-requirement-v1', 'frame_pose_world',
            'frame', entity, end_frame_id, 'required', 'evaluation_boundary',
            'meter+quaternion_wxyz', 'frame_pose_query')
        requirements = StateRequirements('state-requirements-v1', 'controller', owner,
                                          (*requirements.requirements, frame_requirement))
        controller = R3ReferenceEffortControllerV1(r3_reference, servo, entity_id=entity,
            end_frame_id=end_frame_id, opening_range_m=opening_range_m)
    else:
        controller = servo
    return replace(direct_execution, controllers=(controller,), requirements=requirements)
