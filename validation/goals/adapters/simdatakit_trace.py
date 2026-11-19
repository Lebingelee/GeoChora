"""Read a SimDataKit demo `trace.json` into a goal-evaluation Trace.

Format (verified on franka-scene-50 1.0.0 demos): a list of samples
{time, phase, positions{prim_short_name: [x,y,z]}, orientations{name: [w,x,y,z]}, arm_qpos, ...}.
Quaternions are WXYZ (brick_09 matches the manifest quat_wxyz). Object keys are short prim names
(brick_17, ball_2); the manifest `scene_prim` last component maps them to public names.
`left_finger`/`right_finger`/`hand` are link origins. Drawer bodies appear as drawer_N with
y = DRAWER_CLOSED_Y - opening (slide axis -y); there are no joint positions and no contacts.
"""
from __future__ import annotations

import json
from pathlib import Path

from validation.goals.state import SceneState, Trace

# drawer body y when closed: observed on never-opened drawers in the traces (0.181); the manifest
# cavity centre is 0.18. Opening = closed_y - y.
DRAWER_CLOSED_Y = 0.181


def read_trace(path, manifest, *, recording_complete=True, drawer_closed_y=DRAWER_CLOSED_Y):
    """-> Trace. recording_complete is an independent fact supplied by the caller."""
    samples = json.loads(Path(path).read_text(encoding='utf-8'))
    prim_to_name = {o['scene_prim'].rsplit('/', 1)[-1]: o['name'] for o in manifest['objects']}
    drawers = {d['name'] for d in manifest['drawers']}
    out = []
    for s in samples:
        pos, quat = {}, {}
        for prim, p in s['positions'].items():
            if prim in prim_to_name:
                pos[prim_to_name[prim]] = p
        for prim, q in s.get('orientations', {}).items():
            if prim in prim_to_name:
                quat[prim_to_name[prim]] = q
        openings = {d: drawer_closed_y - s['positions'][d][1] for d in drawers if d in s['positions']}
        fingers = {f'finger_{side}': s['positions'][f'{side}_finger']
                   for side in ('left', 'right') if f'{side}_finger' in s['positions']}
        out.append(SceneState(positions=pos, orientations_wxyz=quat, drawer_openings=openings,
                              finger_positions=fingers, contacts_available=False, time=float(s['time'])))
    return Trace(out, recording_complete=recording_complete)
