"""Shared value checks/projection only; no solver abstraction."""
from collections.abc import Mapping
import math
import xml.etree.ElementTree as ET
from uuid import uuid4

import numpy as np

from ...artifacts import (
    CanonicalStatePublicationV2,
    CanonicalStatePublicationV1,
    CanonicalStateView,
    CanonicalStateViewV2,
    CanonicalStateViewV1,
    FrameReference,
    JointDefinition,
    PoseWorld,
    SceneDefinition,
    TaskArtifactV1,
    StateBoundaryIdentity,
    StateRequirements,
    StateSampleClock,
    StateViewLifetime,
    TypedJointStateValue,
    UnavailableStateValue,
    project_canonical_state_v0,
)
from ...artifacts.execution import EpisodeResetPlanV1, RealizedInitialState
from ...controllers.canonical.contracts import digest


def pose(position, quaternion):
    q = tuple(float(v) for v in quaternion)
    norm = math.sqrt(sum(v*v for v in q))
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError('invalid provider quaternion')
    return PoseWorld(tuple(float(v) for v in position), tuple(v/norm for v in q))


def _world_linear_velocity_in_body_frame(quaternion_wxyz, linear_world):
    """Convert a world-frame vector into the free body's local frame."""
    w, x, y, z = (float(value) for value in quaternion_wxyz)
    rotation = np.asarray((
        (1.0 - 2.0 * (y*y + z*z), 2.0 * (x*y - z*w), 2.0 * (x*z + y*w)),
        (2.0 * (x*y + z*w), 1.0 - 2.0 * (x*x + z*z), 2.0 * (y*z - x*w)),
        (2.0 * (x*z - y*w), 2.0 * (y*z + x*w), 1.0 - 2.0 * (x*x + y*y)),
    ), dtype=np.float64)
    return rotation.T @ np.asarray(linear_world, dtype=np.float64)


def validate_reset_realization(
    sample,
    realized,
    *,
    joint_atol: float = 1.0e-6,
    pose_position_atol: float = 1.0e-6,
    pose_orientation_atol: float = 1.0e-6,
) -> dict[str, object]:
    """Check requested reset values against provider readback before rollout."""

    tolerances = (joint_atol, pose_position_atol, pose_orientation_atol)
    if any(not math.isfinite(value) or value < 0.0 for value in tolerances):
        raise ValueError('realization tolerances must be finite and nonnegative')
    if realized.reset_sample_id != sample.sample_id:
        raise ValueError('realized state does not belong to the requested ResetSample')
    state = realized.measured_state
    missing_joints = sorted(set(sample.joint_position) - set(state.joint_position))
    missing_poses = sorted(set(sample.poses_world) - set(state.pose_world))
    if missing_joints or missing_poses:
        raise ValueError(
            f'reset realization is missing requested state: joints={missing_joints}, poses={missing_poses}'
        )
    joint_errors = {
        name: abs(float(state.joint_position[name]) - float(expected))
        for name, expected in sample.joint_position.items()
    }
    pose_position_errors = {}
    pose_orientation_errors = {}
    for name, expected in sample.poses_world.items():
        actual = state.pose_world[name]
        pose_position_errors[name] = max(
            abs(float(actual.position[index]) - float(expected.position[index]))
            for index in range(3)
        )
        direct = math.sqrt(sum(
            (float(actual.quaternion_wxyz[index]) - float(expected.quaternion_wxyz[index])) ** 2
            for index in range(4)
        ))
        antipodal = math.sqrt(sum(
            (float(actual.quaternion_wxyz[index]) + float(expected.quaternion_wxyz[index])) ** 2
            for index in range(4)
        ))
        pose_orientation_errors[name] = min(direct, antipodal)
    if any(error > joint_atol for error in joint_errors.values()):
        raise ValueError(f'reset joint realization exceeds tolerance: {joint_errors}')
    if any(error > pose_position_atol for error in pose_position_errors.values()):
        raise ValueError(f'reset pose position realization exceeds tolerance: {pose_position_errors}')
    if any(error > pose_orientation_atol for error in pose_orientation_errors.values()):
        raise ValueError(f'reset pose orientation realization exceeds tolerance: {pose_orientation_errors}')
    return {
        'reset_sample_id': sample.sample_id,
        'provider_name': realized.provider_name,
        'joint_max_abs_error': max(joint_errors.values(), default=0.0),
        'pose_position_max_abs_error': max(pose_position_errors.values(), default=0.0),
        'pose_orientation_max_error': max(pose_orientation_errors.values(), default=0.0),
        'tolerances': {
            'joint_atol': joint_atol,
            'pose_position_atol': pose_position_atol,
            'pose_orientation_atol': pose_orientation_atol,
        },
    }


def validate_reset_plan_realization(
    plan: EpisodeResetPlanV1,
    realized: RealizedInitialState,
    *,
    joint_atol: float = 1.0e-6,
    pose_position_atol: float = 1.0e-6,
    pose_orientation_atol: float = 1.0e-6,
) -> dict[str, object]:
    """Validate plan identity and measured realization before a rollout starts.

    The provider still consumes the existing ``ResetSample`` v0. This wrapper
    adds Core Role/Scene provenance to the established requested-vs-measured
    gate without changing that provider-facing contract.
    """

    if not isinstance(plan, EpisodeResetPlanV1):
        raise TypeError('reset plan realization requires EpisodeResetPlanV1')
    plan.validate_realization_identity(realized)
    result = validate_reset_realization(
        plan.to_provider_sample(), realized,
        joint_atol=joint_atol,
        pose_position_atol=pose_position_atol,
        pose_orientation_atol=pose_orientation_atol,
    )
    return {
        **result,
        'episode_reset_plan_identity_hash': plan.identity_hash,
        'role_binding_identity_hash': plan.role_binding.identity_hash,
        'task_source_identity_hash': plan.role_binding.task_source_identity_hash,
        'scene_identity_hash': plan.role_binding.scene_identity_hash,
        'role_bindings': dict(plan.role_binding.bindings),
        'sampling_domain': plan.sampling_domain,
        'sampler_id': plan.reset_sample.sampler_id,
        'sampler_version': plan.reset_sample.sampler_version,
    }


class _SessionValues:
    def _initialize_values(self, artifact, source, provider):
        self._artifact, self._source, self._provider = artifact, source, provider
        self._closed, self._reset_done, self._control_step = False, False, 0
        self._state_revision = 0
        self._episode_id = None
        self._reset_sample_id = None
        self._reset_plan_gate_required = False
        self._reset_plan_gate_open = False
        self._reset_plan_evidence = None
        self._scene_instance_id = f'scene-instance-{uuid4().hex}'
        self._provider_materialization_id = f'{provider}-materialization-{uuid4().hex}'
        self._inner_interval_active = False
        root = ET.fromstring(source.scene_source.xml)
        option = root.find('option')
        if option is None or float(option.get('timestep', 'nan')) != artifact.timebase.physics_dt:
            raise ValueError('source/native physics timestep mismatch')

    def _require_open(self):
        if self._closed:
            raise RuntimeError('session is closed')

    def _require_reset(self):
        self._require_open()
        if not self._reset_done:
            raise RuntimeError('reset required before snapshot/step')
        if self._reset_plan_gate_required and not self._reset_plan_gate_open:
            raise RuntimeError('ResetPlan realization gate must pass before snapshot/step')

    def _begin_reset(self):
        """Start the legacy provider reset path and clear any earlier plan gate."""
        self._reset_done = False
        self._reset_plan_gate_required = False
        self._reset_plan_gate_open = False
        self._reset_plan_evidence = None
        if hasattr(self, '_position_applied_boundary_ids'):
            self._position_applied_boundary_ids.clear()

    def reset_plan(self, plan: EpisodeResetPlanV1) -> RealizedInitialState:
        """Reset from a Core plan and open rollout only after Scene/readback checks."""
        self._require_open()
        if not isinstance(plan, EpisodeResetPlanV1):
            raise TypeError('reset_plan requires EpisodeResetPlanV1')
        plan.validate()
        source_id = self._source.scene_source.source_id
        schema, separator, scene_hash = source_id.rpartition(':')
        if not separator or schema not in {'scene-definition-v2', 'scene-definition-v3'}:
            raise ValueError('RuntimeSource ID does not bind a canonical Scene identity')
        if scene_hash != plan.role_binding.scene_identity_hash:
            raise ValueError('EpisodeResetPlan Scene identity differs from materialized RuntimeSource')
        if isinstance(self._artifact, TaskArtifactV1):
            if plan.role_binding.task_source_identity_hash != self._artifact.task_source_identity_hash:
                raise ValueError('EpisodeResetPlan Task Source differs from TaskArtifact v1 snapshot')
            if plan.role_binding.scene_identity_hash != self._artifact.scene_identity_hash:
                raise ValueError('EpisodeResetPlan Scene differs from TaskArtifact v1 reference')
        if self._source.scene_definition is not None and (
            self._source.scene_definition.identity_hash != plan.role_binding.scene_identity_hash
        ):
            raise ValueError('EpisodeResetPlan Scene identity differs from materialized SceneDefinition')

        self._reset_plan_gate_required = False
        self._reset_plan_gate_open = False
        self._reset_plan_evidence = None
        realized = self.reset(plan.to_provider_sample())
        # Provider reset has completed, but snapshots/steps remain blocked until
        # the existing measured-state tolerance gate accepts the realization.
        self._reset_plan_gate_required = True
        try:
            evidence = validate_reset_plan_realization(plan, realized)
        except Exception:
            self._reset_plan_gate_open = False
            raise
        self._reset_plan_evidence = evidence
        self._reset_plan_gate_open = True
        return realized

    @property
    def reset_plan_evidence(self):
        """Return a detached B02 realization receipt for the latest reset plan."""
        return None if self._reset_plan_evidence is None else dict(self._reset_plan_evidence)

    def _validate_sample(self, sample):
        self._require_open()
        if sample.task_artifact_hash != self._artifact.identity_hash:
            raise ValueError('reset sample/Artifact mismatch')
        if set(sample.joint_position) != set(self._source.joints) or set(sample.poses_world) != set(self._source.free_joints):
            raise ValueError('reset semantic bindings mismatch')
        if sample.settle_steps != 0:
            raise ValueError('nonzero settle steps unsupported in P1.2')

    def _state(self, joints, velocities, poses, time):
        return CanonicalStateView('canonical-state-v0', 'SI_right_handed_z_up_wxyz',
                                  self._control_step, float(time), joints, velocities, poses)

    def _realized(self, sample):
        self._reset_done, self._control_step = True, 0
        self._state_revision = 0
        self._reset_sample_id = sample.sample_id
        self._episode_id = f'episode-{uuid4().hex}'
        return RealizedInitialState('realized-initial-state-v0', sample.sample_id,
                                    self._provider, self.snapshot(), 0)

    def _snapshot_with_native_free_joints(self):
        raise ValueError(
            f'{self._provider} does not expose a typed free-joint readback through this RuntimeSession'
        )

    def snapshot_v1(
        self,
        *,
        scene: SceneDefinition,
        joint_bindings: Mapping[str, JointDefinition],
        frame_bindings: Mapping[str, FrameReference],
        requirements: StateRequirements,
    ) -> CanonicalStatePublicationV1:
        """Publish an owned typed projection from one provider readback.

        Binding keys must exactly cover the session's scalar/free-joint and
        body/frame state names. ``scene_source.source_id`` binds the exact
        Scene identity; callers cannot attach a Scene hash after the fact.
        """
        self._require_reset()
        if not isinstance(scene, SceneDefinition):
            raise TypeError('typed state projection requires a SceneDefinition')
        scene.validate()
        if not isinstance(requirements, StateRequirements):
            raise TypeError('typed state projection requires StateRequirements')
        if self._source.scene_definition is not None and (
            self._source.scene_definition.identity_hash != scene.identity_hash
        ):
            raise ValueError('typed state Scene differs from the materialized canonical Scene')
        expected_source_id = f'{scene.schema_version}:{scene.identity_hash}'
        if self._source.scene_source.source_id != expected_source_id:
            raise ValueError('RuntimeSource ID must bind the exact typed state Scene identity')
        if any(item.sample_domain != 'evaluation_boundary' for item in requirements.requirements):
            raise ValueError('native interval requirements need NativeIntervalEvidence, not snapshot_v1')

        state_v0, free_joint_native = self._snapshot_with_native_free_joints()
        scalar_names = set(state_v0.joint_position)
        free_names = set(self._source.free_joints)
        if set(joint_bindings) != scalar_names | free_names:
            raise ValueError('typed Joint bindings must cover each source scalar/free joint exactly')
        if set(frame_bindings) != set(state_v0.pose_world):
            raise ValueError('typed Frame bindings must cover each source body/frame exactly')
        for name, definition in joint_bindings.items():
            if not isinstance(definition, JointDefinition):
                raise TypeError(f'typed Joint binding {name!r} must be a JointDefinition')
            if name in scalar_names and definition.kind not in {'revolute', 'continuous', 'prismatic'}:
                raise ValueError(f'scalar source Joint {name!r} has a non-scalar Scene definition')
            if name in free_names and definition.kind != 'floating':
                raise ValueError(f'free source Joint {name!r} requires a floating Scene definition')

        boundary = StateBoundaryIdentity(
            'state-boundary-identity-v1',
            self._episode_id,
            self._reset_sample_id,
            scene.identity_hash,
            self._scene_instance_id,
            self._provider_materialization_id,
            self._control_step,
            self._state_revision,
        )
        sample_clock = StateSampleClock(
            'state-sample-clock-v1', 'evaluation_boundary', self._control_step,
            state_v0.simulation_time,
        )
        scalar_bindings = {name: joint_bindings[name] for name in scalar_names}
        scalar_projection = project_canonical_state_v0(
            state_v0,
            scene=scene,
            boundary=boundary,
            sample_clock=sample_clock,
            joint_bindings=scalar_bindings,
            frame_bindings=frame_bindings,
        )
        joint_values = list(scalar_projection.joints)
        for name in sorted(free_names):
            definition = joint_bindings[name]
            raw_position, raw_velocity = free_joint_native[name]
            if len(raw_position) != 7 or len(raw_velocity) != 6:
                raise ValueError(f'free source Joint {name!r} must have qpos/qvel widths 7/6')
            frame = definition.child_frame
            if (frame.entity_id, frame.frame_id) not in {
                (reference.entity_id, reference.frame_id) for reference in frame_bindings.values()
            }:
                raise ValueError(f'free source Joint {name!r} requires its child Frame in the typed projection')
            q = pose(raw_position[:3], raw_position[3:]).quaternion_wxyz
            linear_local = _world_linear_velocity_in_body_frame(q, raw_velocity[:3])
            # Both MuJoCo-compatible components are expressed in the free body's
            # frame: linear velocity is rotated from world; angular qvel is local.
            value = TypedJointStateValue(
                'typed-joint-state-v1',
                definition.parent_frame.entity_id,
                definition.joint_id,
                definition.kind,
                definition.position_representation,
                (*tuple(float(v) for v in raw_position[:3]), *q),
                definition.velocity_representation,
                (*tuple(float(v) for v in linear_local),
                 *tuple(float(v) for v in raw_velocity[3:])),
                frame,
                frame,
            )
            value.validate_against(definition)
            joint_values.append(value)

        available = {
            (('joint_position', 'joint', item.entity_id, item.joint_id), 'evaluation_boundary')
            for item in joint_values
        } | {
            (('joint_velocity', 'joint', item.entity_id, item.joint_id), 'evaluation_boundary')
            for item in joint_values
        } | {
            (('frame_pose_world', 'frame', item.frame.entity_id, item.frame.frame_id), 'evaluation_boundary')
            for item in scalar_projection.frames
        }
        unavailable = []
        for requirement in requirements.requirements:
            key = (requirement.field_key, requirement.sample_domain)
            if key in available:
                continue
            unavailable.append(UnavailableStateValue(
                'unavailable-state-value-v1',
                requirement.field_name,
                requirement.subject_kind,
                requirement.entity_id,
                requirement.subject_id,
                requirement.sample_domain,
                f'{self._provider} RuntimeSession.snapshot_v1 does not publish {requirement.field_name}',
            ))

        view = CanonicalStateViewV1(
            'canonical-state-v1',
            'SI_right_handed_z_up_wxyz',
            boundary,
            sample_clock,
            tuple(joint_values),
            scalar_projection.frames,
            tuple(unavailable),
        )
        view.validate_against_scene(scene)
        view.validate_requirements(requirements)
        lifetime = StateViewLifetime(
            'state-view-lifetime-v1', self._provider_materialization_id,
            boundary, self._state_revision, 'owned_snapshot', 'retained',
        )
        return CanonicalStatePublicationV1(
            'canonical-state-publication-v1', view, lifetime,
        )

    def snapshot_v2(
        self,
        *,
        scene: SceneDefinition,
        joint_bindings: Mapping[str, JointDefinition],
        frame_bindings: Mapping[str, FrameReference],
        requirements: StateRequirements,
    ) -> CanonicalStatePublicationV2:
        """Publish the additive typed force state alongside the existing view.

        Joint/Frame projection and identity remain owned by snapshot_v1. Only
        the provider adapter may supply actuator-force values; an unsupported
        provider returns explicit unavailability, which required requirements
        reject below.
        """
        self._require_reset()
        if not isinstance(requirements, StateRequirements):
            raise TypeError('typed state v2 requires StateRequirements')
        if any(item.sample_domain != 'evaluation_boundary' for item in requirements.requirements):
            raise ValueError('snapshot_v2 accepts evaluation-boundary requirements only')
        force_requirements = tuple(
            item for item in requirements.requirements if item.field_name == 'actuator_force'
        )
        base_requirements = StateRequirements(
            requirements.schema_version,
            requirements.consumer_kind,
            requirements.consumer_id,
            tuple(item for item in requirements.requirements if item.field_name != 'actuator_force'),
        )
        base = self.snapshot_v1(
            scene=scene,
            joint_bindings=joint_bindings,
            frame_bindings=frame_bindings,
            requirements=base_requirements,
        )
        forces = ()
        force_unavailable = ()
        if force_requirements:
            reader = getattr(self, '_snapshot_typed_actuator_force_values', None)
            if callable(reader):
                forces, force_unavailable = reader(
                    base.view.boundary, base.view.sample_clock, force_requirements,
                )
            else:
                force_unavailable = tuple(UnavailableStateValue(
                    'unavailable-state-value-v1', item.field_name, item.subject_kind,
                    item.entity_id, item.subject_id, item.sample_domain,
                    f'{self._provider} RuntimeSession has no admitted typed actuator-force route',
                ) for item in force_requirements)
        view = CanonicalStateViewV2(
            'canonical-state-v2',
            base.view.convention,
            base.view.boundary,
            base.view.sample_clock,
            base.view.joints,
            base.view.frames,
            tuple(forces),
            tuple(base.view.unavailable) + tuple(force_unavailable),
        )
        view.validate_against_scene(scene)
        view.validate_requirements(requirements)
        lifetime = StateViewLifetime(
            'state-view-lifetime-v1', self._provider_materialization_id,
            view.boundary, self._state_revision, 'owned_snapshot', 'retained',
        )
        return CanonicalStatePublicationV2(
            'canonical-state-publication-v2', view, lifetime,
        )

    def step_control_interval(self, held_target, gripper_inner_servo, *, audit=None,
                              diagnostic_readback=None, interval_observer=None, arm_schedule=None):
        """Opt-in arm-ZOH interval with a shared physics-rate gripper update.

        Existing ``step()`` remains unchanged. Providers implement only
        ``_step_physics_once``; this shared method owns the canonical feedback,
        inner-servo, held-arm, and outer-boundary contract.
        """
        from dataclasses import replace
        self._require_reset()
        start = self.snapshot()
        if arm_schedule is not None:
            arm_schedule.begin(held_target)
        if audit is not None:
            audit.begin_inner_interval(start)
        substep_rows = []
        last_target = None
        last_applied = None
        self._inner_interval_active = True
        try:
            for substep_index in range(self._artifact.timebase.control_substeps):
                state = self.snapshot()
                feedback = self.control_feedback(state)
                gripper_target, diagnostics = gripper_inner_servo.inner_gripper_step(state, feedback)
                target = replace(held_target, gripper=gripper_target)
                if arm_schedule is not None:
                    target = arm_schedule.target(target, substep_index, self._artifact.timebase.control_substeps)
                last_applied = self.apply_control(target)
                if arm_schedule is not None:
                    arm_schedule.applied(last_applied)
                if audit is None:
                    self._step_physics_once()
                else:
                    audit.execute_inner_substep(target, self._step_physics_once)
                if interval_observer is not None:
                    interval_observer(substep_index, state, feedback, target, last_applied, diagnostics)
                row = dict(diagnostics)
                row.update({
                    "substep_index": substep_index,
                    "control_step": state.control_step,
                    "simulation_time_s": state.simulation_time,
                    "target_hash": target.identity_hash,
                    "arm_target_hash": digest({
                        "arm_position": dict(target.arm_position),
                        "arm_servo_position": dict(target.arm_servo_position),
                    }),
                    "applied_control": last_applied.to_mapping(),
                })
                if diagnostic_readback is not None:
                    try:
                        row["native_contact_diagnostic"] = diagnostic_readback(self)
                    except Exception as exc:  # diagnostic availability must not affect control
                        row["native_contact_diagnostic"] = {
                            "available": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                substep_rows.append(row)
                last_target = target
        finally:
            self._inner_interval_active = False
        self._control_step += 1
        self._state_revision += 1
        final_state = self.snapshot()
        if audit is not None:
            audit.complete_inner_interval(final_state)
        return final_state, last_target, last_applied, substep_rows
