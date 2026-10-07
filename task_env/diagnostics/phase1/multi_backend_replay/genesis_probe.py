"""Private Genesis public MJCF import/readback for shared primitive recipes."""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from ....utils.rotation import quat_wxyz_to_matrix, matrix_to_quat_wxyz


def array(value):
    if hasattr(value, 'detach'):
        value = value.detach().cpu().numpy()
    return np.asarray(value, dtype=float)


class GenesisProbe:
    def __init__(self, specification, raw):
        import genesis as gs
        self.gs = gs; self.spec = specification
        root = ET.fromstring(specification['recipe']['source_xml'])
        option = root.find('option')
        self.dt = float(option.get('timestep'))
        gravity = tuple(map(float, option.get('gravity').split()))
        gs.init(backend=gs.cpu, precision='64', logging_level='warning')
        self.scene = gs.Scene(sim_options=gs.options.SimOptions(dt=self.dt, gravity=gravity), show_viewer=False)
        source = Path(raw) / 'shared_fixture.xml'; source.write_text(specification['recipe']['source_xml'])
        self.entity = self.scene.add_entity(morph=gs.morphs.MJCF(file=str(source.resolve()), default_armature=None))
        self.scene.build()
        self.frames = {}
        for body in root.iter('body'):
            for site in body.findall('site'):
                local = np.eye(4)
                local[:3,3] = np.fromstring(site.get('pos', '0 0 0'), sep=' ')
                local[:3,:3] = quat_wxyz_to_matrix(np.fromstring(site.get('quat', '1 0 0 0'), sep=' '))
                self.frames[site.get('name')] = (self.entity.get_link(body.get('name')), local)
        for actuator in root.findall('actuator/general'):
            native = self.entity.get_joint(actuator.get('joint')); index = native.dof_idx_local
            gain = np.fromstring(actuator.get('gainprm', '1 0 0'), sep=' ')[0]
            bias = np.fromstring(actuator.get('biasprm', '0 -1 0'), sep=' ')
            if bias[0] != 0 or bias[1] >= 0 or gain <= 0:
                raise ValueError('unsupported affine actuator')
            self.entity.set_dofs_kp([-bias[1]], [index]); self.entity.set_dofs_kv([-bias[2]], [index])
            self.entity.control_dofs_position([specification['recipe']['inputs']['fixed_target'] * gain / -bias[1]], [index])

    def read(self):
        bindings = self.spec['recipe']['semantic_bindings']; bodies = {}; frames = {}; joints = {}
        for semantic, name in bindings.get('bodies', {}).items():
            link = self.entity.get_link(name); index = link.idx_local
            bodies[semantic] = {'position': array(link.get_pos()).tolist(), 'quaternion_wxyz': array(link.get_quat()).tolist(),
                'linear_velocity': array(self.entity.get_links_vel([index]))[0].tolist(),
                'angular_velocity': array(self.entity.get_links_ang([index]))[0].tolist()}
        for semantic, name in bindings.get('frames', {}).items():
            link, local = self.frames[name]; parent = np.eye(4)
            parent[:3,3] = array(link.get_pos()); parent[:3,:3] = quat_wxyz_to_matrix(array(link.get_quat()))
            world = parent @ local
            frames[semantic] = {'position': world[:3,3].tolist(), 'quaternion_wxyz': matrix_to_quat_wxyz(world[:3,:3]).tolist()}
        for semantic, name in bindings.get('joints', {}).items():
            index = self.entity.get_joint(name).dof_idx_local
            joints[semantic] = {'position': float(array(self.entity.get_dofs_position([index]))[0]), 'velocity': float(array(self.entity.get_dofs_velocity([index]))[0])}
        return {'time': float(array(self.scene.get_time())), 'bodies': bodies, 'frames': frames, 'joints': joints}

    def facts(self):
        result = {'native_dt': float(self.scene.dt), 'clock': 'public scene.get_time'}
        if self.spec['probe_id'] == 'asset_frame':
            link = self.entity.get_link('root'); i = link.idx_local
            inertia = array(self.entity.get_links_inertia([i]))[0]
            # Geometry must come from materialized provider objects, never source/oracle.
            if len(link.geoms) == 1:
                geometry = array(link.geoms[0].data).tolist()
                readback = 'native collision geometry data'
            elif len(link.vgeoms) == 1:
                vertices = array(link.vgeoms[0].init_vverts)
                geometry = ((vertices.max(axis=0)-vertices.min(axis=0))/2).tolist()
                readback = 'native materialized visual vertex bounds'
            else:
                raise ValueError('materialized geometry readback unavailable')
            result.update(mass=float(array(self.entity.get_links_mass([i]))[0]), inertia=np.diag(inertia).tolist(), geometry=geometry, geometry_readback=readback)
        return result

    def step(self): self.scene.step()

    def close(self):
        self.scene.destroy(); self.gs.destroy()
