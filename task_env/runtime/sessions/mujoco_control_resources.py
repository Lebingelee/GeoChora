"""Resolve source-bound Position actuators to conservative native DOF claims."""


def position_native_dofs(session, profile, plan):
    """Return the native DOFs driven by one admitted Position writer.

    Only scalar direct-joint and fixed joint-tendon transmissions are admitted.
    Active joint equalities conservatively couple both native coordinates. Other
    active equality kinds cannot yet be mapped safely and are rejected.
    """
    model, mj, source = session._model, session._mj, session._source
    expected = {native for entity, native, writer in plan.resource_writers
                if entity == profile.entity_id and writer == profile.writer_id}
    target_bindings = profile._target_bindings
    declared = set(target_bindings.values()) | {profile.open_actuator}
    if (not expected or expected != declared or len(declared) != len(target_bindings) + 1
            or any(source.joint_targets.get(key) != value for key, value in target_bindings.items())
            or profile.open_actuator not in source.open_actuators):
        raise ValueError('Position resources differ from the bound native source')
    scalar = {int(mj.mjtJoint.mjJNT_HINGE), int(mj.mjtJoint.mjJNT_SLIDE)}
    selected_joints = set()
    for native in sorted(declared):
        actuator = int(model.actuator(native).id)
        if not 0 <= actuator < int(model.nu):
            raise ValueError('Position actuator is outside the native model')
        kind = int(model.actuator_trntype[actuator])
        target = int(model.actuator_trnid[actuator][0])
        if kind == int(mj.mjtTrn.mjTRN_JOINT):
            joints = (target,)
        elif kind == int(mj.mjtTrn.mjTRN_TENDON):
            if not 0 <= target < int(model.ntendon):
                raise ValueError('Position tendon is outside the native model')
            start, count = int(model.tendon_adr[target]), int(model.tendon_num[target])
            if count <= 0 or start < 0 or start + count > len(model.wrap_type):
                raise ValueError('Position tendon has no complete native mapping')
            if any(int(model.wrap_type[i]) != int(mj.mjtWrap.mjWRAP_JOINT)
                   for i in range(start, start + count)):
                raise ValueError('Position tendon requires a joint-only transmission')
            joints = tuple(int(model.wrap_objid[i]) for i in range(start, start + count))
        else:
            raise ValueError('Position actuator transmission is not a supported native mapping')
        for joint in joints:
            if not 0 <= joint < int(model.njnt) or int(model.jnt_type[joint]) not in scalar:
                raise ValueError('Position actuator requires native scalar joints')
            selected_joints.add(joint)
        source_keys = [key for key, name in target_bindings.items() if name == native]
        if source_keys:
            joint = int(model.joint(source.joints[source_keys[0]]).id)
            if joints != (joint,):
                raise ValueError('Position actuator aliases a different native joint')
    pairs = []
    active = getattr(session._data, 'eq_active', None)
    if int(model.neq) and (active is None or len(active) != int(model.neq)):
        raise ValueError('Position ownership requires live native equality state')
    for eq in range(int(model.neq)):
        if not bool(active[eq]):
            continue
        if int(model.eq_type[eq]) != int(mj.mjtEq.mjEQ_JOINT):
            raise ValueError('Position ownership cannot resolve a non-joint native equality')
        first, second = int(model.eq_obj1id[eq]), int(model.eq_obj2id[eq])
        for joint in (first, second):
            if joint != -1 and (not 0 <= joint < int(model.njnt) or int(model.jnt_type[joint]) not in scalar):
                raise ValueError('Position equality requires native scalar joints')
        if first >= 0 and second >= 0:
            pairs.append((first, second))
    changed = True
    while changed:
        changed = False
        for first, second in pairs:
            if first in selected_joints or second in selected_joints:
                previous = len(selected_joints)
                selected_joints.update((first, second))
                changed |= len(selected_joints) != previous
    result = frozenset(int(model.jnt_dofadr[joint]) for joint in selected_joints)
    if not result or any(dof < 0 or dof >= int(model.nv) for dof in result):
        raise ValueError('Position native DOF footprint is invalid')
    return result
