"""Diagnostic-private native readback. Never consumed by task/expert/controller."""
from types import SimpleNamespace
import numpy as np
from ....environment import SnapshotRequest, RuntimeSnapshot
from ....tasks.nut_assembly.task import NutAssemblyTaskDefinition
from ....controllers.canonical.kinematics import ARM, FINGERS


def legacy_metrics(session, provider):
    """Evaluate the unchanged historical task on the same provider boundary."""
    if provider == 'geophys':
        snap = session._boundary.read_snapshot(SnapshotRequest(ctrl=True, site_pose=True))
    else:
        data = session._data
        snap = RuntimeSnapshot(qpos=data.qpos.copy(), qvel=data.qvel.copy(), ctrl=data.ctrl.copy(),
                               site_xpos=data.site_xpos.copy())
    refs = SimpleNamespace(agents={'panda-v1': SimpleNamespace(
        eef_site_id=session._frames['panda-v1/ee'],
        gripper_qpos_ids=np.array([session._joint_addresses[n][0] for n in FINGERS]),
        gripper_actuator_ids=np.array([session._open_actuators[0]]))},
        objects={'square-nut-v1': SimpleNamespace(qpos_ids=np.array([session._free_addresses['square-nut-v1']]))})
    return dict(NutAssemblyTaskDefinition(refs).reset(snap).metrics)


def contact_readback(session, provider):
    if provider == 'geophys':
        packet = session._boundary._physics.read_body_contact_state()
        rows = []
        for semantic, index in session._bodies.items():
            rows.append({'semantic_body': semantic, 'active': int(packet['active'][index]),
                'count': int(packet['count'][index]), 'normal_impulse_native': float(packet['normal_impulse'][index]),
                'tangent_impulse_native': float(packet['tangent_impulse'][index]),
                'point_world': packet['point'][index].tolist()})
        return {'public_api': 'read_body_contact_state', 'meaning': 'native completed-substep body aggregate; diagnostic only', 'bodies': rows}
    model, data, mj = session._model, session._data, session._mj
    rows = []
    nut_body_id = int(session._model.body("SquareNut").id)
    nut_com = np.asarray(data.xipos[nut_body_id], dtype=float)
    nut_resultant = np.zeros(3, dtype=float)
    nut_moment = np.zeros(3, dtype=float)
    nut_contact_count = 0
    nut_normal_magnitude_sum = 0.0
    for i in range(data.ncon):
        c = data.contact[i]; force = np.zeros(6); mj.mj_contactForce(model, data, i, force)
        geom_ids = [int(c.geom1), int(c.geom2)]
        body_ids = [int(model.geom_bodyid[g]) for g in geom_ids]
        body_names = [mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, b) for b in body_ids]
        geom_names = [mj.mj_id2name(model, mj.mjtObj.mjOBJ_GEOM, g) for g in geom_ids]
        frame_axes_world = np.asarray(c.frame, dtype=float).reshape(3, 3)
        # mjContact.frame stores the contact-frame axes as rows. mj_contactForce
        # returns contact-frame force followed by torque, so transpose maps it
        # into world coordinates. The normal points from geom1 toward geom2.
        force_world_on_geom2 = frame_axes_world.T @ np.asarray(force[:3], dtype=float)
        torque_world_on_geom2 = frame_axes_world.T @ np.asarray(force[3:], dtype=float)
        nut_side = 1 if body_ids[1] == nut_body_id else 0 if body_ids[0] == nut_body_id else None
        force_world_on_nut = None
        if nut_side is not None:
            nut_sign = 1.0 if nut_side == 1 else -1.0
            force_world_on_nut = nut_sign * force_world_on_geom2
            nut_resultant += force_world_on_nut
            nut_moment += np.cross(np.asarray(c.pos, dtype=float) - nut_com, force_world_on_nut)
            nut_moment += nut_sign * torque_world_on_geom2
            nut_contact_count += 1
            nut_normal_magnitude_sum += abs(float(force[0]))
        rows.append({
            'contact_index': int(i),
            'source_geom_ids': geom_ids,
            'source_geom_names': geom_names,
            'source_body_ids': body_ids,
            'source_body_names': body_names,
            'separation_m': float(c.dist),
            'point_world': np.asarray(c.pos, dtype=float).tolist(),
            'contact_frame_axes_world_as_rows': frame_axes_world.tolist(),
            'normal_world_geom1_to_geom2': frame_axes_world[0].tolist(),
            'contact_frame_force_native': force.tolist(),
            'normal_force_native': float(force[0]),
            'tangential_force_native': np.asarray(force[1:3], dtype=float).tolist(),
            'tangential_force_magnitude_native': float(np.linalg.norm(force[1:3])),
            'contact_torque_native': np.asarray(force[3:], dtype=float).tolist(),
            'force_world_on_geom2_N': force_world_on_geom2.tolist(),
            'torque_world_on_geom2_Nm': torque_world_on_geom2.tolist(),
            'force_world_on_nut_N': None if force_world_on_nut is None else force_world_on_nut.tolist(),
        })
    return {
        'public_api': 'MjData.contact + mj_contactForce',
        'meaning': 'native completed-substep contacts; diagnostic only',
        'contact_count': int(data.ncon),
        'contacts': rows,
        'nut_com_world_m': nut_com.tolist(),
        'nut_contact_count': nut_contact_count,
        'nut_contact_normal_magnitude_sum_N': float(nut_normal_magnitude_sum),
        'nut_contact_resultant_force_world_N': nut_resultant.tolist(),
        'nut_contact_resultant_force_magnitude_N': float(np.linalg.norm(nut_resultant)),
        'nut_contact_resultant_moment_world_Nm': nut_moment.tolist(),
        'nut_contact_resultant_moment_magnitude_Nm': float(np.linalg.norm(nut_moment)),
    }
