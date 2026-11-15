"""MuJoCo source-geometry readback of the saved public control boundaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np


def read(source, directory):
    model = mujoco.MjModel.from_xml_path(str(Path(source).resolve(strict=True)))
    data = mujoco.MjData(model)
    cube = model.geom('PickCube_collision').id
    table = model.geom('grasp_table_geom').id
    joint_names = [f'joint{i}' for i in range(1, 8)] + ['finger_joint1', 'finger_joint2']
    candidates = [i for i in range(model.ngeom)
                  if i != cube and int(model.geom_bodyid[i]) != int(model.geom_bodyid[cube])
                  and (int(model.geom_contype[i]) or int(model.geom_conaffinity[i]))]
    finger_bodies = {model.body('left_finger').id, model.body('right_finger').id}
    fingers = [i for i in candidates if int(model.geom_bodyid[i]) in finger_bodies]
    report = {'reader': 'MuJoCo mj_geomDistance on frozen source, not GeoPhys contacts',
              'mujoco_version': mujoco.__version__, 'geometry_scope': 'control boundaries only',
              'table_limit_m': .002, 'cases': {}}
    for name in ('zero', 'hold', 'descent'):
        with np.load(Path(directory) / f'{name}-trajectory.npz') as f:
            joints, poses = f['joint_position'].copy(), f['cube_pose'].copy()
        distances = np.empty((len(joints), joints.shape[1], len(candidates)))
        for tick in range(len(joints)):
            for row in range(joints.shape[1]):
                for joint, value in zip(joint_names, joints[tick, row], strict=True):
                    data.joint(joint).qpos[:] = value
                data.joint('PickCube_joint').qpos[:] = poses[tick, row]
                mujoco.mj_forward(model, data)
                for col, geom in enumerate(candidates):
                    distances[tick, row, col] = mujoco.mj_geomDistance(model, data, cube, geom, .2, None)
        table_distances = distances[:, :, candidates.index(table)]
        close = []
        for col, geom in enumerate(candidates):
            minimum = float(distances[:, :, col].min())
            if minimum <= .003:
                close.append({'geom_id': int(geom), 'geom_name': model.geom(geom).name,
                              'body_name': model.body(int(model.geom_bodyid[geom])).name,
                              'minimum_distance_m': minimum})
        np.savez_compressed(Path(directory) / f'{name}-independent-geometry.npz',
                            distances=distances, geom_ids=np.asarray(candidates),
                            table_distance=table_distances)
        worst = float(table_distances.min())
        report['cases'][name] = {
            'boundaries': len(joints), 'rows': int(joints.shape[1]),
            'table_min_m_by_row': table_distances.min(axis=0).tolist(),
            'table_boundary_gate': 'PASS' if worst >= -.002 else 'FAIL',
            'finger_min_m_by_row': distances[:, :, [candidates.index(i) for i in fingers]].min(axis=(0, 2)).tolist(),
            'cube_related_geoms_within_3mm': close,
        }
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--directory', required=True)
    args = parser.parse_args()
    print(json.dumps(read(args.source, args.directory), indent=2))
