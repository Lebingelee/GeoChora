"""Private native diagnostic adapters. No production canonical contract changes."""
from pathlib import Path
import numpy as np

from ....assembly.source import TaskSceneSource
from ....runtime.sessions.geophys_source import native_scene_source


def vector(value):
    return np.asarray(value,dtype=float).tolist()


class MuJoCoProbe:
    def __init__(self, specification):
        import mujoco
        self.mj=mujoco
        self.spec=specification
        self.model=mujoco.MjModel.from_xml_string(specification['recipe']['source_xml'])
        self.data=mujoco.MjData(self.model)
        mujoco.mj_resetData(self.model,self.data)
        self.data.qvel[:]=0
        if specification['probe_id']=='joint_tracking':
            self.data.ctrl[self.model.actuator('servo').id]=specification['recipe']['inputs']['fixed_target']
        mujoco.mj_forward(self.model,self.data)
        self.renderer=None

    def read(self):
        bindings=self.spec['recipe']['semantic_bindings']
        bodies={}
        for name,native in bindings.get('bodies',{}).items():
            index=self.model.body(native).id
            vel=np.zeros(6)
            self.mj.mj_objectVelocity(self.model,self.data,self.mj.mjtObj.mjOBJ_BODY,index,vel,0)
            bodies[name]={'position':vector(self.data.xpos[index]),'quaternion_wxyz':vector(self.data.xquat[index]),
                          'linear_velocity':vector(vel[3:]),'angular_velocity':vector(vel[:3])}
        frames={}
        for name,native in bindings.get('frames',{}).items():
            index=self.model.site(native).id
            quaternion=np.zeros(4)
            self.mj.mju_mat2Quat(quaternion,self.data.site_xmat[index])
            frames[name]={'position':vector(self.data.site_xpos[index]),'quaternion_wxyz':vector(quaternion)}
        joints={}
        for name,native in bindings.get('joints',{}).items():
            index=self.model.joint(native).id
            joints[name]={'position':float(self.data.qpos[self.model.jnt_qposadr[index]]),
                          'velocity':float(self.data.qvel[self.model.jnt_dofadr[index]])}
        return {'time':float(self.data.time),'bodies':bodies,'frames':frames,'joints':joints}

    def facts(self):
        result={'native_dt':float(self.model.opt.timestep),'gravity':vector(self.model.opt.gravity),
                'solver_iterations':int(self.model.opt.iterations),'solver_tolerance':float(self.model.opt.tolerance)}
        if self.spec['probe_id']=='asset_frame':
            index=self.model.body('root').id
            result.update(mass=float(self.model.body_mass[index]),inertia=vector(self.model.body_inertia[index]),geometry=vector(self.model.geom('shape').size))
        return result

    def step(self):
        self.mj.mj_step(self.model,self.data)
        self.mj.mj_forward(self.model,self.data)

    def camera(self, raw):
        camera=self.spec['recipe']['facts']['camera']
        self.renderer=self.mj.Renderer(self.model,height=camera['height'],width=camera['width'])
        self.renderer.update_scene(self.data,camera='fixed')
        self.renderer.enable_depth_rendering()
        depth=self.renderer.render()
        np.save(raw/'depth.npy',depth)
        # Native GL camera/frustum drives projection; independent from authored
        # oracle focal-length computation. Native IDs never leave this adapter.
        views=self.renderer.scene.camera
        position=(np.array(views[0].pos)+np.array(views[1].pos))/2
        forward=np.array(views[0].forward,dtype=float); forward/=np.linalg.norm(forward)
        up=np.array(views[0].up,dtype=float);up/=np.linalg.norm(up)
        right=np.cross(forward,up)
        near=float(views[0].frustum_near)
        top=float(views[0].frustum_top);bottom=float(views[0].frustum_bottom)
        width=(top-bottom)*camera['width']/camera['height']
        center=float(views[0].frustum_center)
        pixels=[]
        for point in self.spec['recipe']['inputs']['landmarks']:
            rel=np.array(point)-position
            z=float(rel@forward)
            x=float(rel@right)*near/z;y=float(rel@up)*near/z
            pixels.append([camera['width']*(.5+(x-center)/width),camera['height']*(top-y)/(top-bottom)])
        return {'pixels':pixels,'center_depth_m':float(np.mean(depth[31:33,31:33])),
                'native_depth_convention':'camera-axis metric depth from mujoco.Renderer',
                'native_camera':{'position':vector(position),'forward':vector(forward),'up':vector(up),'near':near,'top':top,'bottom':bottom},
                'render_backend':'MuJoCo native OpenGL/EGL'}

    def close(self):
        if self.renderer is not None:self.renderer.close()
        self.model=None;self.data=None


class GeoPhysProbe:
    def __init__(self,specification):
        from geophys.test_runtime import init_test_backend
        from geophys.demo_runtime import assemble_mjcf_articulated_runtime
        from scene import import_scene_source
        from solvers.rigid import RigidGroundConfig
        init_test_backend('cpu')
        self.spec=specification
        source=TaskSceneSource(specification['recipe']['source_xml'],Path.cwd(),specification['probe_id'])
        imported=import_scene_source(native_scene_source(source))
        self.runtime=assemble_mjcf_articulated_runtime(imported,scene_kwargs={'use_imported_meshes':False},
            solver_kwargs={'dt':.002,'ground':RigidGroundConfig(height=-10.,visible=False,contact_margin=0.),
                           'enable_ground_contact':False,'enable_domain_boundary_contact':False,'prewarm_kernels':False},
            create_simulator=True,create_render_source=specification['probe_id']=='camera_depth')
        self.physics=self.runtime.solver
        links=imported.articulation.links
        self.body_names={link.name:i for i,link in enumerate(links)}
        self.site_names={site.name:i for i,site in enumerate(site for link in links for site in link.sites)}
        self.joint_names={joint.name:i for i,joint in enumerate(joint for link in links for joint in link.joints)}
        self.actuator_names={act.name:i for i,act in enumerate(imported.articulation.actuators)}
        self.data=self.runtime.scene_model.joint_data
        if self.physics.n_dof:
            self.physics.write_qvel(np.zeros_like(self.physics.read_qvel()))
        if specification['probe_id']=='joint_tracking':
            ctrl=self.physics.read_ctrl();ctrl[self.actuator_names['servo']]=specification['recipe']['inputs']['fixed_target']
            self.physics.write_ctrl(ctrl)
        if self.physics.n_qpos:
            self.physics.synchronize_kinematic_state(update_site_jacobians=False)
        self.steps=0;self.visualizer=None
        self.import_notes=[{'semantic':entry.semantic,'status':entry.status.value,'action':entry.action}
                           for entry in imported.capability_report.entries if entry.status.value in ('retained','rejected')]

    def read(self):
        bindings=self.spec['recipe']['semantic_bindings']
        positions=self.physics.read_positions();quats=self.physics.read_orientations()
        velocities=self.physics.read_linear_velocities();angular=self.physics.read_angular_velocities()
        bodies={name:{'position':vector(positions[self.body_names[native]]),'quaternion_wxyz':vector(quats[self.body_names[native]]),
                      'linear_velocity':vector(velocities[self.body_names[native]]),'angular_velocity':vector(angular[self.body_names[native]])}
                for name,native in bindings.get('bodies',{}).items()}
        frames={}
        if bindings.get('frames'):
            pos=self.physics.read_site_world_pos();quat=self.physics.read_site_world_quat()
            frames={name:{'position':vector(pos[self.site_names[native]]),'quaternion_wxyz':vector(quat[self.site_names[native]])} for name,native in bindings['frames'].items()}
        qpos=self.physics.read_qpos() if self.physics.n_qpos else np.zeros(0)
        qvel=self.physics.read_qvel() if self.physics.n_dof else np.zeros(0)
        joints={name:{'position':float(qpos[self.data['jnt_qposadr'][self.joint_names[native]]]),
                      'velocity':float(qvel[self.data['jnt_dofadr'][self.joint_names[native]]])}
                for name,native in bindings.get('joints',{}).items()}
        return {'time':self.steps*float(self.physics.dt),'bodies':bodies,'frames':frames,'joints':joints}

    def facts(self):
        result={'native_dt':float(self.physics.dt),'import_notes':self.import_notes}
        if self.spec['probe_id']=='asset_frame':
            body=self.runtime.scene_model.objects[self.body_names['root']]
            geom=self.data['geom_names'].index('shape')
            result.update(mass=float(body.body_config.mass),inertia=vector(np.diag(body.body_inertia) if np.asarray(body.body_inertia).ndim==2 else body.body_inertia),geometry=vector(self.data['geom_size'][geom]))
        return result

    def step(self):
        self.runtime.simulator.step(1);self.steps+=1

    def camera(self,raw):
        camera=self.spec['recipe']['facts']['camera']
        self.visualizer=self.runtime.render_source.build_visualizer(backend='raytracer',width=64,height=64,
            render_preset='interactive',enable_shadow=False,enable_taa=False,enable_ao=False,enable_fog=False)
        self.visualizer.write_camera_pose({'pos':camera['position'],'look_at':camera['look_at'],'up':camera['up']})
        # Explicit diagnostic-only access to renderer's native RayCamera object;
        # call its public methods. No production camera contract or repair.
        native_camera=self.visualizer._camera
        native_camera.set_fov(camera['vertical_fov_degrees'])
        self.visualizer.read_frame(width=64,height=64,synchronized=True)
        depth=self.visualizer.read_depth();np.save(raw/'depth.npy',depth)
        pixels=native_project(native_camera,self.spec['recipe']['inputs']['landmarks'])
        return {'pixels':pixels,'center_depth_m':float(np.mean(depth[31:33,31:33])),
                'native_depth_convention':'metric ray distance from GeoPhys native raytracer framebuffer',
                'render_backend':'GeoPhys native Taichi raytracer CPU'}

    def close(self):
        if self.visualizer is not None:
            close=getattr(self.visualizer,'close',None)
            if callable(close):close()
            # Taichi/native render resource ownership ends at worker exit.
        self.physics=None;self.runtime=None


def native_project(camera,points):
    import taichi as ti
    @ti.kernel
    def project(landmarks:ti.types.ndarray(dtype=ti.f32,ndim=2),pixels:ti.types.ndarray(dtype=ti.f32,ndim=2)):
        for i in range(landmarks.shape[0]):
            point=ti.Vector([landmarks[i,0],landmarks[i,1],landmarks[i,2]])
            x,y,z=camera.project(point,64,64)
            pixels[i,0]=x;pixels[i,1]=64-y
    output=np.zeros((len(points),2),dtype=np.float32)
    project(np.array(points,dtype=np.float32),output)
    return output.astype(float).tolist()
