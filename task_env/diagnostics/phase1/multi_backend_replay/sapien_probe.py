"""Private SAPIEN CPU lowering of shared P1.3 primitive source recipes.

This is conformance infrastructure, not an implemented PickCube runtime.
Unsupported source features fail before native scene construction.
"""
import xml.etree.ElementTree as ET
import numpy as np
from ....utils.rotation import quat_wxyz_to_matrix, matrix_to_quat_wxyz


def values(element, key, default):
    return np.fromstring(element.get(key, default), sep=' ')


class SapienProbe:
    def __init__(self, spec):
        import sapien
        self.sp = sapien
        self.spec = spec
        root = ET.fromstring(spec['recipe']['source_xml'])
        if root.find('equality') is not None or root.find('tendon') is not None:
            raise ValueError('sapien_source_lowering: equality/tendon not implemented')
        option = root.find('option')
        self.dt = float(option.get('timestep'))
        gravity = values(option, 'gravity', '0 0 -9.81')
        sapien.physx.set_scene_config(gravity=gravity)
        self.scene = sapien.Scene([sapien.physx.PhysxCpuSystem()])
        self.scene.set_timestep(self.dt)
        self.bodies = {}; self.components = {}; self.joints = {}; self.frames = {}
        self.steps = 0
        self.articulations = []
        for body in root.find('worldbody').findall('body'):
            if body.findall('body'):
                raise ValueError('nested source requires articulated source lowering')
            joints = body.findall('joint') + body.findall('freejoint')
            if len(joints) > 1:
                raise ValueError('multiple joints per body unsupported')
            joint = joints[0] if joints else None
            kind = 'free' if joint is not None and (joint.tag == 'freejoint' or joint.get('type') == 'free') else ('fixed' if joint is None else joint.get('type', 'hinge'))
            if kind in ('hinge', 'slide'):
                ab = self.scene.create_articulation_builder()
                anchor = ab.create_link_builder(); anchor.set_name('world_anchor')
                builder = ab.create_link_builder(anchor)
                builder.set_name(body.get('name')); builder.set_joint_name(joint.get('name'))
                axis = values(joint, 'axis', '0 0 1'); axis /= np.linalg.norm(axis)
                helper = np.array([0., 0., 1.]) if abs(axis[2]) < .9 else np.array([0., 1., 0.])
                y = np.cross(helper, axis); y /= np.linalg.norm(y)
                rotation = np.column_stack((axis, y, np.cross(axis, y)))
                joint_frame = sapien.Pose(values(joint, 'pos', '0 0 0'), matrix_to_quat_wxyz(rotation))
                builder.set_joint_properties('revolute' if kind == 'hinge' else 'prismatic',
                    [values(joint, 'range', '-0.5 0.5')], self._pose(body) * joint_frame, joint_frame,
                    damping=float(joint.get('damping', '0')))
                self._shapes(builder, body); self._inertia(builder, body)
                articulation = ab.build(fix_root_link=True)
                articulation.set_qpos(np.zeros(articulation.dof)); articulation.set_qvel(np.zeros(articulation.dof))
                native = articulation.find_joint_by_name(joint.get('name'))
                native.set_armature([float(joint.get('armature', '0'))])
                self.joints[joint.get('name')] = (articulation, native)
                self.articulations.append(articulation)
                entity = native.child_link.entity
            else:
                builder = self.scene.create_actor_builder(); builder.set_name(body.get('name'))
                builder.set_initial_pose(self._pose(body)); self._shapes(builder, body)
                if kind == 'free':
                    self._inertia(builder, body); entity = builder.build()
                else:
                    entity = builder.build_static()
            component = entity.find_component_by_type(sapien.physx.PhysxRigidBodyComponent)
            if component is None:
                component = entity.find_component_by_type(sapien.physx.PhysxRigidStaticComponent)
            self.bodies[body.get('name')] = entity
            self.components[body.get('name')] = component
            if kind == 'free':
                component.set_linear_damping(0); component.set_angular_damping(0)
                component.set_linear_velocity(np.zeros(3)); component.set_angular_velocity(np.zeros(3))
            for site in body.findall('site'):
                self.frames[site.get('name')] = (entity, self._pose(site))
        for actuator in root.findall('actuator/general'):
            if actuator.get('joint') not in self.joints:
                raise ValueError('unsupported actuator transmission')
            _, native = self.joints[actuator.get('joint')]
            gain = values(actuator, 'gainprm', '1 0 0')[0]
            bias = values(actuator, 'biasprm', '0 -1 0')
            if bias[0] != 0 or bias[1] >= 0 or gain <= 0:
                raise ValueError('unsupported affine actuator')
            native.set_drive_properties(-float(bias[1]), -float(bias[2]))
            native.set_drive_target(float(spec['recipe']['inputs']['fixed_target']) * gain / -bias[1])

    def _pose(self, element):
        return self.sp.Pose(values(element, 'pos', '0 0 0'), values(element, 'quat', '1 0 0 0'))

    def _shapes(self, builder, body):
        for geom in body.findall('geom'):
            kind = geom.get('type', 'sphere'); size = values(geom, 'size', '0.1')
            material = self.scene.create_physical_material(*([float(values(geom, 'friction', '1 0 0')[0])] * 2), 0.)
            if kind == 'box':
                builder.add_box_collision(self._pose(geom), size, material=material)
            elif kind == 'sphere':
                builder.add_sphere_collision(self._pose(geom), float(size[0]), material=material)
            else:
                raise ValueError('unsupported primitive geometry: ' + kind)
        if all(g.get('contype', '1') == '0' and g.get('conaffinity', '1') == '0' for g in body.findall('geom')):
            builder.collision_groups = [0, 0, 0, 0]

    def _inertia(self, builder, body):
        inertial = body.find('inertial')
        if inertial is None:
            raise ValueError('explicit inertial required')
        builder.set_mass_and_inertia(float(inertial.get('mass')), self._pose(inertial), values(inertial, 'diaginertia', '0 0 0'))

    def read(self):
        bindings = self.spec['recipe']['semantic_bindings']
        bodies = {}
        for semantic, name in bindings.get('bodies', {}).items():
            entity = self.bodies[name]; component = self.components[name]
            bodies[semantic] = {'position': entity.pose.p.astype(float).tolist(),
                'quaternion_wxyz': entity.pose.q.astype(float).tolist(),
                'linear_velocity': np.asarray(getattr(component, 'linear_velocity', np.zeros(3)), dtype=float).tolist(),
                'angular_velocity': np.asarray(getattr(component, 'angular_velocity', np.zeros(3)), dtype=float).tolist()}
        frames = {}
        for semantic, name in bindings.get('frames', {}).items():
            entity, local = self.frames[name]; world = entity.pose * local
            frames[semantic] = {'position': world.p.astype(float).tolist(), 'quaternion_wxyz': world.q.astype(float).tolist()}
        joints = {}
        for semantic, name in bindings.get('joints', {}).items():
            articulation, native = self.joints[name]
            joints[semantic] = {'position': float(articulation.get_qpos()[0]), 'velocity': float(articulation.get_qvel()[0])}
        return {'time': self.steps * self.scene.get_timestep(), 'bodies': bodies, 'frames': frames, 'joints': joints}

    def facts(self):
        result = {'native_dt': self.scene.get_timestep(), 'clock': 'completed native calls times native timestep; PhysX has no public accumulated time'}
        if self.spec['probe_id'] == 'asset_frame':
            component = self.components['root']; shape = component.get_collision_shapes()[0]
            result.update(mass=float(component.mass), inertia=np.asarray(component.inertia, dtype=float).tolist(), geometry=np.asarray(shape.half_size, dtype=float).tolist())
        return result

    def step(self):
        self.scene.step(); self.steps += 1

    def close(self):
        for entity in list(self.bodies.values()):
            self.scene.remove_entity(entity)
        self.bodies.clear(); self.components.clear(); self.frames.clear(); self.joints.clear(); self.articulations.clear()
        self.scene = None
