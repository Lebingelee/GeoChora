"""Bound Position preparation for the shared Position/physical interval owner."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PreparedMixedPositionV1:
    session: object
    profile: object
    plan: object
    publication: object
    sequence: object
    lowers: tuple
    position_dofs: frozenset
    action_sha256: str
    env: object = None
    task_source_sha256: str | None = None
    task_construction_sha256: str | None = None

    def validate_physical(self, physical, resolved):
        from .physical_control import ResolvedPhysicalBatchV1
        if (physical is not getattr(self.session, '_physical_port', None)
                or getattr(physical, 'session', None) is not self.session
                or getattr(self.session, '_physical_controller_versions', None)
                   != physical.execution.controller_versions()
                or type(resolved) is not ResolvedPhysicalBatchV1
                or getattr(self.session, '_prepared_position_sequence', None) is not self.sequence):
            raise ValueError('mixed Position/physical commands require their live admitted owners')
        if resolved.input_batch.extensions:
            raise ValueError('mixed Position/physical interval does not admit extensions')
        if self.position_dofs.intersection(physical.dofs.values()):
            raise ValueError('mixed Position and physical bindings overlap native DOFs')
        model = self.session._model
        for item in resolved.input_batch.body_wrenches:
            body = physical.bodies.get((item.entity_id, item.body_id))
            if body is None:
                raise ValueError('mixed physical wrench body lacks its native binding')
            while body > 0:
                count, start = int(model.body_dofnum[body]), int(model.body_dofadr[body])
                if count and (start < 0 or self.position_dofs.intersection(range(start, start + count))):
                    raise ValueError('mixed physical wrench aliases Position native DOFs')
                body = int(model.body_parentid[body])

    def validate_external(self, external):
        if getattr(external, 'session', None) is not self.session:
            raise ValueError('mixed COM load differs from the live session')
        if 'task' in external.producers:
            value = getattr(self.env, 'value', None)
            task = value.get('task_source') if isinstance(value, dict) else None
            if (getattr(task, 'identity_hash', None) != self.task_source_sha256
                    or getattr(self.env.artifact, 'task_source_identity_hash', None) != self.task_source_sha256
                    or value.get('construction_id') != self.task_construction_sha256):
                raise ValueError('mixed Task force differs from its selected Task source or construction')
        model = self.session._model
        for _request, body in external.rows:
            while body > 0:
                count, start = int(model.body_dofnum[body]), int(model.body_dofadr[body])
                if count and (start < 0 or self.position_dofs.intersection(range(start, start + count))):
                    raise ValueError('mixed COM body aliases Position native DOFs')
                body = int(model.body_parentid[body])

    def stage(self):
        return self.session.stage_position_sequence(self.sequence, self.lowers)

    def commit(self, scene_receipt):
        if self.session.state_boundary_identity() != self.publication.view.boundary:
            raise ValueError('mixed Position boundary changed before Controller commit')
        self.profile.commit_absolute_joint_preview(self.publication, self.plan, self.sequence, scene_receipt)


def prepare_mixed_position(env, action):
    """Precompute one S0 Position schedule; no native write or cursor mutation."""
    from .mujoco import _MuJoCoSession
    from .control import _validate_position_source_boundary, _position_control_part, validate_target
    from .control_submission import PositionControlSequenceV1
    from .mujoco_control_resources import position_native_dofs
    from ...controllers.canonical.position_profile import PandaPositionServoProfileV1
    from ...controllers.canonical.position_sequence import PositionPhysicalActionV1
    from ...runtime.sessions.physical_control import PhysicalControlExecutionV1
    session = env.session
    profiles = tuple(getattr(env, 'position_profiles', ()))
    physical = env.binding.physical_control_profile(env)
    if (type(action) is not PositionPhysicalActionV1 or type(session) is not _MuJoCoSession
            or len(profiles) != 1 or type(profiles[0]) is not PandaPositionServoProfileV1
            or type(physical) is not PhysicalControlExecutionV1
            or getattr(env.binding, 'position_physical_mixed', False) is not True
            or getattr(session, '_physical_port', None) is None
            or getattr(session._physical_port, 'execution', None) is not physical
            or getattr(session, '_mixed_actuator_plan', None) is not None
            or env.recorder is not None or getattr(env, '_task_rgb_config', None) is not None
            or getattr(env, '_physical_reset_selection', None) is not None
            or hasattr(session, '_gravity_model')):
        raise ValueError('mixed Position/physical action requires the admitted scalar MuJoCo owners')
    action.validate(substeps=env.artifact.timebase.control_substeps,
                    controller_identities=tuple(c.identity for c in physical.controllers))
    profile, plan, publication = profiles[0], env.position_plan, env.typed_state
    _validate_position_source_boundary(session, profile, plan, publication,
        scene=env.position_scene, joint_bindings=env.position_joint_bindings,
        frame_bindings=env.position_frame_bindings)
    if getattr(session, '_prepared_position_sequence', None) is not None:
        raise RuntimeError('a Position sequence is already prepared')
    dofs = position_native_dofs(session, profile, plan)
    if dofs.intersection(session._physical_port.dofs.values()):
        raise ValueError('mixed Position and physical bindings overlap native DOFs')
    previews = profile.preview_absolute_joint_targets(publication,
        tuple(item.request for item in action.position.slices), plan)
    rows = []
    for item, (_canonical, target) in zip(action.position.slices, previews, strict=True):
        boundary, resources, lower = _position_control_part(session, target,
            controller_profile=profile, plan=plan, publication=publication,
            scene=env.position_scene, joint_bindings=env.position_joint_bindings,
            frame_bindings=env.position_frame_bindings)
        session._position_target_in_flight = target.target.identity_hash
        session._position_target_source_boundary_in_flight = target.source_boundary
        try:
            validate_target(session, target.target)
        finally:
            session._position_target_in_flight = None
            session._position_target_source_boundary_in_flight = None
        rows.append((item.start_substep, item.end_substep, target, boundary, resources, lower))
    if any(row[3] != rows[0][3] or row[4] != rows[0][4] for row in rows):
        raise ValueError('mixed Position slices differ in boundary or resources')
    sequence = PositionControlSequenceV1(action.position, tuple(row[:3] for row in rows))
    sequence.validate()
    external = getattr(session, '_external_com_port', None)
    task_source_sha256 = task_construction_sha256 = None
    if external is not None and 'task' in external.producers:
        task = env.value.get('task_source')
        task_source_sha256 = getattr(task, 'identity_hash', None)
        task_construction_sha256 = env.value.get('construction_id')
        for value in (task_source_sha256, task_construction_sha256):
            if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('mixed Task force requires exact Task source and construction identities')
        if env.artifact.task_source_identity_hash != task_source_sha256:
            raise ValueError('mixed Task force source differs from the selected Artifact')
    session._prepared_position_sequence = sequence
    return PreparedMixedPositionV1(session, profile, plan, publication, sequence,
        tuple(row[5] for row in rows), dofs, action.identity_hash, env,
        task_source_sha256, task_construction_sha256)
