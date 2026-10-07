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
    for i in range(data.ncon):
        c = data.contact[i]; force = np.zeros(6); mj.mj_contactForce(model, data, i, force)
        names = [mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, int(model.geom_bodyid[g])) for g in [c.geom1, c.geom2]]
        rows.append({'source_body_names': names, 'separation_m': float(c.dist), 'point_world': c.pos.tolist(),
                     'contact_frame_force_native': force.tolist()})
    return {'public_api': 'MjData.contact + mj_contactForce', 'meaning': 'native completed-substep contacts; diagnostic only', 'contact_count': int(data.ncon), 'contacts': rows}
