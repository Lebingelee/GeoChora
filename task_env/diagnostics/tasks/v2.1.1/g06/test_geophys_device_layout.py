"""Independent CUDA physics oracle for the source-layout GeoPhys adapter."""
import numpy as np
import pytest
import torch


@pytest.mark.parametrize('coupled,integrator,renamed', (
    (False, 'Euler', False), (True, 'Euler', False),
    (False, 'implicitfast', False), (True, 'implicitfast', False),
    (True, 'Euler', True),
))
def test_source_layout_two_joints_free_body_sites_and_masked_reset(monkeypatch, coupled, integrator, renamed):
    import json
    import subprocess
    from pathlib import Path
    from task_env.artifacts import (ActuatorReference, ActuatorResourceDefinition, ArticulationDefinition,
        AssetDefinition, ControlGroup, EntityInstance, FrameDefinition, FrameReference, JointDefinition,
        PoseWorld, RobotInstance, SceneDefinition)
    from task_env.controllers.canonical.physical_commands import PhysicalControlBindingV1, PhysicalJointChannelV1
    from task_env.runtime.providers.geophys.device_batch import GeoPhysNativeBatch
    from task_env.runtime.transport import cuda_ipc

    if not torch.cuda.is_available():
        pytest.skip('CUDA required')
    xml = '''<mujoco model="independent_layout"><option timestep="0.002" gravity="0 0 0" integrator="Euler"/>
    <worldbody><body name="root"><body name="link_a"><joint name="joint_a" type="slide" axis="1 0 0" damping="0.3"/>
    <geom type="sphere" size="0.1" mass="1" contype="0" conaffinity="0"/>
    <site name="tip" pos="0.1 0.2 0.3" quat="0.7071067811865476 0 0 0.7071067811865476"/>
    </body><body name="link_b"><joint name="joint_b" type="slide" axis="0 1 0" damping="0.4"/>
    <geom type="sphere" size="0.1" mass="1" contype="0" conaffinity="0"/></body></body>
    <body name="cube"><joint name="cube_free" type="free" damping="0.8"/><geom type="box" size="0.1 0.1 0.1" mass="1" contype="0" conaffinity="0"/></body>
    </worldbody><actuator><motor name="motor_a" joint="joint_a" ctrllimited="true" ctrlrange="-2 2"/>
    <position name="motor_b" joint="joint_b" kp="20" kv="1" ctrllimited="true" ctrlrange="-2 2"/>
    </actuator></mujoco>'''
    xml = xml.replace('integrator="Euler"', f'integrator="{integrator}"')
    if coupled:
        start = xml.index('<actuator>')
        xml = (xml[:start] + '''<tendon><fixed name="split"><joint joint="joint_a" coef="0.5"/>
            <joint joint="joint_b" coef="0.5"/></fixed></tendon>
            <actuator><position name="motor_split" tendon="split" kp="20" kv="1"
            ctrllimited="true" ctrlrange="-2 2"/></actuator></mujoco>''')
    origin = PoseWorld((0., 0., 0.), (1., 0., 0., 0.))
    asset = AssetDefinition('asset-definition-v1', 'layout', 'v1', 'inline://layout')
    entities = tuple(EntityInstance('entity-instance-v1', name, 'layout', 'v1') for name in ('rig', 'object'))
    frames = tuple(FrameDefinition('frame-definition-v1', entity, name, 'runtime', None, None)
        for entity, names in (('rig', ('root', 'link_a', 'link_b', 'tip')),
                              ('object', ('world', 'cube'))) for name in names)
    ref = lambda entity, name: FrameReference(entity, name)
    joints = tuple(JointDefinition('joint-definition-v1', name, ref('rig', 'root'), ref('rig', child),
        origin, origin, 'prismatic', axis, 'meter', 'meter_per_second', 1, 1)
        for name, child, axis in (('joint_a', 'link_a', (1., 0., 0.)), ('joint_b', 'link_b', (0., 1., 0.))))
    free = JointDefinition('joint-definition-v1', 'cube_free', ref('object', 'world'), ref('object', 'cube'),
        origin, origin, 'floating', None, 'xyz_meter_quaternion_wxyz',
        'linear_xyz_meter_per_second_angular_xyz_radian_per_second', 7, 6)
    articulations = (ArticulationDefinition('articulation-definition-v1', 'rig', 'root',
        ('root', 'link_a', 'link_b'), joints), ArticulationDefinition('articulation-definition-v1',
        'object', 'world', ('world', 'cube'), (free,)))
    actuator_names = ('motor_split',) if coupled else ('motor_a', 'motor_b')
    resources = tuple(ActuatorResourceDefinition('actuator-resource-v1', 'rig', name) for name in actuator_names)
    robot = RobotInstance('robot-instance-v1', 'rig', (ref('rig', 'root'),))
    groups = (ControlGroup('control-group-v1', 'rig', 'drive',
        tuple(ActuatorReference('rig', name) for name in actuator_names)),)
    scene = SceneDefinition('scene-definition-v3', 'layout', (asset,), entities, frames, articulations,
                            (robot,), resources, groups)
    by_name = {item.joint_id: item for item in joints}
    coefficient = .5 if coupled else 1.
    channels = tuple(PhysicalJointChannelV1('physical-joint-channel-v1', ('test',), ('writer',), 'rig', name,
        'dof0', 'prismatic', axis, ref('rig', child), (1 if coupled else sign), 'N',
        (-2. * coefficient, 2. * coefficient), ('motor_split' if coupled else motor),
        ('transmission_split' if coupled else 'transmission_' + name), coefficient, (-2., 2.), 'disabled')
        for name, child, axis, sign, motor in (('joint_b', 'link_b', (0., 1., 0.), -1, 'motor_b'),
                                                ('joint_a', 'link_a', (1., 0., 0.), 1, 'motor_a')))
    binding = PhysicalControlBindingV1('physical-control-binding-v1', '0'*64, '1'*64, 'layout', '2'*64,
                                       '3'*64, channels)
    request = {'source_assets': {}, 'source_xml': xml, 'source_id': 'layout',
        'scene_definition': scene.to_mapping(), 'binding': binding.to_mapping(),
        'source_bodies': {'rig/root': 'root', 'rig/a': 'link_a', 'rig/b': 'link_b', 'object/cube': 'cube'},
        'source_frames': {'rig/tip': 'tip'}, 'source_joints': {'rig/joint_a': 'joint_a', 'rig/joint_b': 'joint_b'},
        'source_free_joints': {'object/cube_free': 'cube_free'},
        'joint_definitions': [by_name[channel.joint_id].to_mapping() for channel in channels],
        'fixed_roots': ['root'], 'num_envs': 3, 'physics_dt': .002, 'control_substeps': 1,
        'gravity': (0, 0, 0), 'broadphase': 'n2', 'contact_mode': 'discrete'}

    # Exercise the same semantic structure after both source renaming and
    # native object/DOF reordering, instead of relying on a fixed Panda layout.
    names = {'joint_a': 'axis_alpha', 'joint_b': 'axis_beta', 'cube_free': 'payload_free',
             'link_a': 'segment_alpha', 'link_b': 'segment_beta', 'cube': 'payload',
             'tip': 'tool_anchor', 'motor_a': 'drive_alpha', 'motor_b': 'drive_beta',
             'motor_split': 'drive_pair', 'split': 'coupler'} if renamed else {}

    def rename(value):
        if isinstance(value, str):
            for old, new in sorted(names.items(), key=lambda item: len(item[0]), reverse=True):
                value = value.replace(old, new)
            return value
        if isinstance(value, dict):
            return {rename(key): rename(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rename(item) for item in value]
        if isinstance(value, tuple):
            return tuple(rename(item) for item in value)
        return value

    if renamed:
        import xml.etree.ElementTree as ET
        root_xml = ET.fromstring(request['source_xml'])
        worldbody = root_xml.find('worldbody')
        worldbody[:] = list(reversed(worldbody[:]))
        rig_body = next(body for body in worldbody if body.get('name') == 'root')
        rig_body[:] = list(reversed(rig_body[:]))
        request['source_xml'] = ET.tostring(root_xml, encoding='unicode')
        request = rename(request)
        xml = request['source_xml']

    class Publisher:
        def __init__(self, fields):
            self.values = {name: torch.zeros(shape, device='cuda', dtype=(torch.bool if dtype == 'bool' else torch.float32))
                           for name, (shape, dtype) in fields.items()}
        def description(self): return {}
        def publish(self, values): self.values.update({name: value.clone() for name, value in values.items()})
        def read_inputs(self, names): return {name: self.values[name] for name in names}
        def close(self): self.values.clear()
    monkeypatch.setattr(cuda_ipc, 'CudaIpcDuplexPublisher', Publisher)
    adapter = GeoPhysNativeBatch(request)
    try:
        np.testing.assert_allclose(adapter._site_pos_tensor.cpu().numpy(), [[.1, .2, .3]], atol=1e-7)
        description = adapter.description()
        assert description['physical_layout_facts']['contact_mode_requested'] == 'discrete'
        assert description['physical_layout_facts']['contact_mode_resolved'] == 'discrete'
        assert (description['nq'], description['nv']) == (9, 8)
        joint_positions = description['joint_qpos_indices']
        cube_qpos = description['free_joint_qpos_indices'][rename('object/cube_free')]
        dof_b, dof_a = description['physical_layout_facts']['source_dofs']
        cube_dofs = [index for index in range(8) if index not in (dof_a, dof_b)]
        assert cube_dofs == list(range(cube_dofs[0], cube_dofs[0] + 6))
        assert len({joint_positions[rename('rig/joint_a')], joint_positions[rename('rig/joint_b')], *range(cube_qpos, cube_qpos + 7)}) == 9
        if renamed:
            # The free body is authored first and the two source children in
            # reverse order; require this to change the compiled slot layout.
            assert cube_qpos == 0 and cube_dofs == list(range(6))
            assert joint_positions[rename('rig/joint_b')] < joint_positions[rename('rig/joint_a')]
            assert dof_b < dof_a
        publisher = adapter._publisher
        q = publisher.values['qpos'].clone()
        q[:, joint_positions[rename('rig/joint_a')]] = torch.tensor([.1, .2, -.1], device='cuda')
        q[:, joint_positions[rename('rig/joint_b')]] = torch.tensor([-.2, .3, .1], device='cuda')
        q[:, cube_qpos:cube_qpos+3] = torch.tensor([[.5, 0., 0.], [1., .1, 0.], [1.5, 0., .2]], device='cuda')
        q[:, cube_qpos+3:cube_qpos+7] = torch.tensor([1., 0., 0., 0.], device='cuda')
        v = torch.zeros((3, 8), device='cuda')
        v[:, cube_dofs[0]] = torch.tensor([.3, -.2, .5], device='cuda')
        v[:, cube_dofs[3]:cube_dofs[3]+3] = torch.tensor([.7, -.4, .3], device='cuda')
        v[:, dof_a] = torch.tensor([.2, -.1, .3], device='cuda')
        v[:, dof_b] = torch.tensor([-.3, .2, -.1], device='cuda')
        publisher.values.update(reset_qpos=q, reset_qvel=v, reset_mask=torch.ones(3, device='cuda', dtype=torch.bool))
        adapter.reset()
        np.testing.assert_allclose(publisher.values['body_orientation'][:, 1].cpu().numpy(),
                                   np.tile([1., 0., 0., 0.], (3, 1)), atol=1e-7)
        np.testing.assert_allclose(publisher.values['frame_position'][0, 0].cpu().numpy(),
                                   [.2, .2, .3], atol=1e-6)
        initial = {key: publisher.values[key].clone() for key in ('qpos', 'qvel', 'frame_position', 'frame_orientation')}
        actions = torch.tensor(([[.3, .3], [-.5, -.5], [.8, .8]] if coupled else
                                [[.3, .7], [-.5, .2], [1., -.1]]), device='cuda')
        publisher.values['effort'] = actions
        adapter.step()
        actual = {key: publisher.values[key].cpu().numpy() for key in ('qpos', 'qvel', 'frame_position', 'frame_orientation')}
        # MuJoCo 3.8.1 and the task's pinned 4.0.1 differ in implicitfast
        # free-body damping. Use the actual pinned version in a CPU oracle,
        # never the GeoPhys interpreter's unrelated MuJoCo installation.
        oracle_script = '''
import json, sys
import mujoco
payload=json.load(sys.stdin)
assert mujoco.__version__ == '4.0.1'
model=mujoco.MjModel.from_xml_string(payload['xml'])
model.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_ACTUATION)
q={key:int(model.jnt_qposadr[mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_JOINT,name)]) for key,name in payload['names'].items()}
v={key:int(model.jnt_dofadr[mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_JOINT,name)]) for key,name in payload['names'].items()}
out=[]
for row in payload['rows']:
 data=mujoco.MjData(model)
 data.qpos[q['joint_a']],data.qpos[q['joint_b']]=row['joint_q']
 data.qpos[q['cube_free']:q['cube_free']+7]=row['free_q']
 data.qvel[v['joint_a']],data.qvel[v['joint_b']]=row['joint_v']
 data.qvel[v['cube_free']:v['cube_free']+6]=row['free_v']
 data.qfrc_applied[v['joint_a']],data.qfrc_applied[v['joint_b']]=row['effort']
 mujoco.mj_step(model,data); mujoco.mj_forward(model,data)
 out.append({'joint_q':[float(data.qpos[q['joint_a']]),float(data.qpos[q['joint_b']])],
  'joint_v':[float(data.qvel[v['joint_a']]),float(data.qvel[v['joint_b']])],
  'free_q':data.qpos[q['cube_free']:q['cube_free']+7].tolist(),
  'free_v':data.qvel[v['cube_free']:v['cube_free']+6].tolist(),
  'site':data.site_xpos[0].tolist()})
print(json.dumps(out))
'''
        rows = []
        for world in range(3):
            rows.append({'joint_q': [q[world, joint_positions[rename('rig/joint_a')]].item(),
                                     q[world, joint_positions[rename('rig/joint_b')]].item()],
                         'joint_v': [v[world, dof_a].item(), v[world, dof_b].item()],
                         'free_q': q[world, cube_qpos:cube_qpos+7].cpu().tolist(),
                         'free_v': v[world, cube_dofs].cpu().tolist(),
                         'effort': [actions[world, 1].item(),
                                    (1 if coupled else -1) * actions[world, 0].item()]})
        oracle_python = (Path(__file__).resolve().parents[5] /
                         'workspace/environments/g06-mujoco-warp-4.0.1/bin/python')
        oracle = subprocess.run([str(oracle_python), '-c', oracle_script],
                                input=json.dumps({'xml': xml, 'rows': rows,
                                                  'names': {key: rename(key) for key in ('joint_a', 'joint_b', 'cube_free')}}), text=True,
                                capture_output=True, check=True)
        expected = json.loads(oracle.stdout)
        for world in range(3):
            for index, (name, dof) in enumerate((('joint_a', dof_a), ('joint_b', dof_b))):
                np.testing.assert_allclose(actual['qpos'][world, joint_positions[rename('rig/' + name)]], expected[world]['joint_q'][index], atol=3e-6, rtol=0)
                np.testing.assert_allclose(actual['qvel'][world, dof], expected[world]['joint_v'][index], atol=3e-6, rtol=0)
            np.testing.assert_allclose(actual['qpos'][world, cube_qpos:cube_qpos+7], expected[world]['free_q'], atol=3e-6, rtol=0)
            np.testing.assert_allclose(actual['qvel'][world, cube_dofs], expected[world]['free_v'], atol=3e-6, rtol=0)
            np.testing.assert_allclose(actual['frame_position'][world, 0], expected[world]['site'], atol=3e-6, rtol=0)
        np.testing.assert_allclose(actual['frame_orientation'][:, 0], np.tile([2**-.5, 0, 0, 2**-.5], (3, 1)), atol=3e-6)
        before = publisher.values['qpos'].clone()
        publisher.values.update(reset_qpos=q, reset_qvel=v,
                                reset_mask=torch.tensor([True, False, True], device='cuda'))
        adapter.reset()
        after = publisher.values['qpos']
        torch.testing.assert_close(after[1], before[1], rtol=0, atol=0)
        torch.testing.assert_close(after[[0, 2]], q[[0, 2]], rtol=0, atol=0)
        assert adapter._runtime.solver.read_direct_step_clock()[0] == 1
    finally:
        adapter.close()
