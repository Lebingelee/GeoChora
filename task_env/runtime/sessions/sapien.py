"""Private CPU SAPIEN lowering of compiled shared MJCF authoring facts.

MuJoCo compiles source defaults/geometry only, never simulation truth. PhysX
public articulation/actor APIs own dynamics. Source arm PD uses public implicit drives with unchanged gains; fixed tendon
force uses measured native state/public qf at each physics substep;
the canonical controller is unchanged. Native handles stay private.
"""
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from .common import _SessionValues, pose
from .representation import calibrate_timestep


class _SapienSession(_SessionValues):
    def __init__(self, artifact, source):
        self._initialize_values(artifact,source,'sapien')
        import sapien
        import mujoco
        self._sp,self._mj=sapien,mujoco
        root=ET.fromstring(source.scene_source.xml)
        for e in root.iter('freejoint'):e.tag='joint';e.set('type','free')
        for e in root.findall('keyframe'):root.remove(e)
        self._model=m=mujoco.MjModel.from_xml_string(ET.tostring(root,encoding='unicode'))
        self._temp=tempfile.TemporaryDirectory(prefix='geochora-sapien-')
        sapien.physx.set_scene_config(gravity=m.opt.gravity)
        self._scene=sapien.Scene([sapien.physx.PhysxCpuSystem()])
        self._native_timestep=calibrate_timestep(self._scene,artifact.timebase.physics_dt)
        if not self._native_timestep['pass']:raise ValueError('SAPIEN native timestep representation mismatch')
        self._entities={};self._articulations=[];self._joint_bindings={};self._native_steps=0
        roots=[i for i in range(1,m.nbody) if m.body_parentid[i]==0]
        for body in roots:
            children=[i for i in range(body+1,m.nbody) if self._ancestor(i,body)]
            j=int(m.body_jntadr[body]);nj=int(m.body_jntnum[body])
            if children:
                if nj:raise ValueError('only fixed-root articulated source supported')
                ab=self._scene.create_articulation_builder();builders={}
                for b in [body]+children:
                    parent=builders.get(int(m.body_parentid[b]));builder=ab.create_link_builder(parent)
                    builder.set_name(m.body(b).name);builders[b]=builder
                    n=int(m.body_jntnum[b]);ji=int(m.body_jntadr[b])
                    if n>1:raise ValueError('one scalar joint per body required')
                    if parent is not None:
                        if n:
                            kind=int(m.jnt_type[ji])
                            if kind not in (mujoco.mjtJoint.mjJNT_HINGE,mujoco.mjtJoint.mjJNT_SLIDE):raise ValueError('unsupported articulation joint')
                            child=self._axis_pose(m.jnt_pos[ji],m.jnt_axis[ji]);local=self._body_pose(b)
                            builder.set_joint_name(m.joint(ji).name)
                            builder.set_joint_properties('revolute' if kind==mujoco.mjtJoint.mjJNT_HINGE else 'prismatic',
                                [m.jnt_range[ji]] if m.jnt_limited[ji] else [[-np.inf,np.inf]],local*child,child)
                        else:builder.set_joint_properties('fixed',[],self._body_pose(b),sapien.Pose())
                    self._shapes(builder,b);self._inertia(builder,b)
                ab.set_initial_pose(self._body_pose(body));a=ab.build(fix_root_link=True);self._articulations.append(a)
                joints=list(a.get_active_joints());indices={x.name:i for i,x in enumerate(joints)}
                for b in [body]+children:
                    link=a.find_link_by_name(m.body(b).name)
                    if len(link.get_collision_shapes())!=builders[b]._geochora_expected_shapes:raise ValueError('native collision cooking lost source geometry')
                    self._entities[m.body(b).name]=link.entity
                for ji in range(m.njnt):
                    name=m.joint(ji).name
                    if name in indices:
                        joint=joints[indices[name]];joint.set_armature([float(m.dof_armature[m.jnt_dofadr[ji]])])
                        self._joint_bindings[name]=(a,indices[name],joint,ji)
            else:
                builder=self._scene.create_actor_builder();builder.set_name(m.body(body).name);builder.set_initial_pose(self._body_pose(body))
                self._shapes(builder,body)
                if nj:
                    if nj!=1 or m.jnt_type[j]!=mujoco.mjtJoint.mjJNT_FREE:raise ValueError('unsupported root body joint')
                    self._inertia(builder,body);entity=builder.build()
                    component=entity.find_component_by_type(sapien.physx.PhysxRigidDynamicComponent)
                    component.set_linear_damping(0);component.set_angular_damping(0)
                else:entity=builder.build_static()
                component=entity.find_component_by_type(sapien.physx.PhysxRigidBaseComponent)
                if len(component.get_collision_shapes())!=builder._geochora_expected_shapes:raise ValueError('native collision cooking lost source geometry')
                self._entities[m.body(body).name]=entity
        # Sibling affine joint equality uses SAPIEN's public mimic-tendon recipe.
        # 1e5 is the installed loader's native mimic default, not a controller gain.
        for i in range(m.neq):
            if m.eq_type[i]!=mujoco.mjtEq.mjEQ_JOINT or not np.array_equal(m.eq_data[i,:5],[0,1,0,0,0]):raise ValueError('unsupported source equality')
            aa,_,ja,_=self._joint_bindings[m.joint(int(m.eq_obj1id[i])).name]
            bb,_,jb,_=self._joint_bindings[m.joint(int(m.eq_obj2id[i])).name]
            if aa is not bb or ja.parent_link!=jb.parent_link:raise ValueError('only sibling identity joint equality supported')
            aa.create_fixed_tendon([ja.parent_link,ja.child_link,jb.child_link],[0,-1,1],[0,-1,1],stiffness=1e5)
        self._joints={k:self._joint_bindings[n] for k,n in source.joints.items()}
        self._free={k:self._entities[m.body(int(m.jnt_bodyid[m.joint(n).id])).name] for k,n in source.free_joints.items()}
        self._bodies={k:self._entities[n] for k,n in source.bodies.items()}
        self._frames={k:(self._entities[m.body(int(m.site_bodyid[m.site(n).id])).name],sapien.Pose(m.site_pos[m.site(n).id],m.site_quat[m.site(n).id])) for k,n in source.frames.items()}
        self._target_actuators={k:int(m.actuator(n).id) for k,n in source.joint_targets.items()}
        self._open_actuators=tuple(int(m.actuator(n).id) for n in source.open_actuators)
        if len(self._open_actuators)!=1:raise ValueError('one named fixed tendon actuator required')
        i=self._open_actuators[0];tid=int(m.actuator_trnid[i,0])
        if m.actuator_trntype[i]!=mujoco.mjtTrn.mjTRN_TENDON:raise ValueError('fixed tendon source required')
        self._members=[]
        for w in range(int(m.tendon_adr[tid]),int(m.tendon_adr[tid]+m.tendon_num[tid])):
            if m.wrap_type[w]!=mujoco.mjtWrap.mjWRAP_JOINT:raise ValueError('joint fixed tendon required')
            native=m.joint(int(m.wrap_objid[w])).name;c=float(m.wrap_prm[w])
            if c<=0:raise ValueError('positive opening direction required')
            self._members.append((native,c))
        for i in (*self._target_actuators.values(),*self._open_actuators):
            if m.actuator_biasprm[i,0]!=0 or m.actuator_biasprm[i,1]>=0:raise ValueError('affine position actuator required')
        self._arm_native_names=set()
        for i in self._target_actuators.values():
            if m.actuator_trntype[i]!=mujoco.mjtTrn.mjTRN_JOINT:raise ValueError('named joint actuator required')
            native=m.joint(int(m.actuator_trnid[i,0])).name
            _,_,joint,ji=self._joint_bindings[native]
            low,high=m.actuator_forcerange[i]
            if not m.actuator_forcelimited[i] or low!=-high:raise ValueError('symmetric source actuator force bounds required')
            joint.set_drive_properties(-float(m.actuator_biasprm[i,1]),-float(m.actuator_biasprm[i,2])+float(m.dof_damping[m.jnt_dofadr[ji]]),float(high),'force')
            self._arm_native_names.add(native)
        self._ctrl={};self._force_limits={};self._completed_opening_force=0.
        self._initial_poses={n:e.pose for n,e in self._entities.items()}
        self._materialization_facts={'source_joint_order':[m.joint(i).name for i in range(m.njnt)],
            'native_joint_limits':{n:j.get_limits().tolist() for n,(_,_,j,_) in self._joint_bindings.items()},
            'source_mass_inertia':{m.body(b).name:{'mass':float(m.body_mass[b]),'inertia':m.body_inertia[b].tolist()} for b in range(1,m.nbody)},
            'equality_mapping':'public sibling mimic fixed tendon; native loader stiffness default 1e5',
            'actuator_mapping':'source affine force law, measured native state, force-clipped public set_qf per substep'}

    def _ancestor(self,b,root):
        while b:
            b=int(self._model.body_parentid[b])
            if b==root:return True
        return False

    def _body_pose(self,b):return self._sp.Pose(self._model.body_pos[b],self._model.body_quat[b])

    def _axis_pose(self,p,axis):
        from ...utils.rotation import matrix_to_quat_wxyz
        x=np.array(axis,dtype=float);x/=np.linalg.norm(x)
        helper=np.array([0.,0.,1.]) if abs(x[2])<.9 else np.array([0.,1.,0.])
        y=np.cross(helper,x);y/=np.linalg.norm(y)
        return self._sp.Pose(p,matrix_to_quat_wxyz(np.column_stack((x,y,np.cross(x,y)))))

    def _inertia(self,builder,b):
        m=self._model;builder.set_mass_and_inertia(float(m.body_mass[b]),self._sp.Pose(m.body_ipos[b],m.body_iquat[b]),m.body_inertia[b])

    def _shapes(self,builder,b):
        m=self._model;expected=0
        for g in range(int(m.body_geomadr[b]),int(m.body_geomadr[b]+m.body_geomnum[b])):
            if m.geom_contype[g]==0 and m.geom_conaffinity[g]==0:continue
            expected+=1;local=self._sp.Pose(m.geom_pos[g],m.geom_quat[g]);f=float(m.geom_friction[g,0])
            material=self._scene.create_physical_material(f,f,0.)
            if m.geom_type[g]==self._mj.mjtGeom.mjGEOM_BOX:builder.add_box_collision(local,m.geom_size[g],material=material)
            elif m.geom_type[g]==self._mj.mjtGeom.mjGEOM_MESH:
                mesh=int(m.geom_dataid[g]);path=Path(self._temp.name)/f'mesh{mesh}.obj'
                if not path.exists():
                    vertices=m.mesh_vert[m.mesh_vertadr[mesh]:m.mesh_vertadr[mesh]+m.mesh_vertnum[mesh]]
                    faces=m.mesh_face[m.mesh_faceadr[mesh]:m.mesh_faceadr[mesh]+m.mesh_facenum[mesh]]
                    path.write_text(''.join('v '+' '.join(map(str,v))+'\n' for v in vertices)+''.join('f '+' '.join(str(int(x)+1) for x in v)+'\n' for v in faces))
                builder.add_convex_collision_from_file(str(path),pose=local,material=material)
            else:raise ValueError('unsupported collision geometry')
        # No render or visual construction.
        builder.collision_groups=[1,1,0,0]
        builder._geochora_expected_shapes=expected

    def reset(self,sample):
        self._validate_sample(sample)
        for a in self._articulations:
            a.set_qpos(np.zeros(a.dof));a.set_qvel(np.zeros(a.dof));a.set_qf(np.zeros(a.dof))
        for semantic,value in sample.joint_position.items():
            a,i,_,_=self._joints[semantic];q=a.get_qpos();q[i]=value;a.set_qpos(q)
        for semantic,p in sample.poses_world.items():
            entity=self._free[semantic];entity.pose=self._sp.Pose(p.position,p.quaternion_wxyz)
            c=entity.find_component_by_type(self._sp.physx.PhysxRigidDynamicComponent)
            c.set_linear_velocity([0,0,0]);c.set_angular_velocity([0,0,0])
        self._ctrl={i:sample.joint_position[k] for k,i in self._target_actuators.items()}
        self._ctrl.update({i:float(self._model.actuator_ctrlrange[i,1]) for i in self._open_actuators})
        self._set_arm_drives()
        self._force_limits={};self._completed_opening_force=0.;self._native_steps=0
        return self._realized(sample)

    def snapshot(self):
        self._require_reset()
        if self._native_steps!=self._control_step*self._artifact.timebase.control_substeps:raise ValueError('native/canonical boundary count mismatch')
        q={k:float(a.get_qpos()[i]) for k,(a,i,_,_) in self._joints.items()}
        v={k:float(a.get_qvel()[i]) for k,(a,i,_,_) in self._joints.items()}
        poses={k:pose(e.pose.p,e.pose.q) for k,e in self._bodies.items()}
        for k,(e,local) in self._frames.items():
            world=e.pose*local;poses[k]=pose(world.p,world.q)
        return self._state(q,v,poses,self._control_step*self._artifact.timebase.control_dt)

    def control_feedback(self,state):
        from ...controllers.canonical.feedback import CanonicalControlFeedback,CanonicalGripperFeedback
        if state.to_mapping()!=self.snapshot().to_mapping():raise ValueError('feedback requires current measured boundary')
        opening=sum(state.joint_position[k] for k,(a,i,_,_) in self._joints.items() if any(self._joint_bindings[n][0] is a and self._joint_bindings[n][1]==i for n,_ in self._members))
        return CanonicalControlFeedback('canonical-control-feedback-v0',state.control_step,state.simulation_time,
            CanonicalGripperFeedback(self._control_binding.gripper_semantic_id,max(0.,opening),max(0.,-self._completed_opening_force)))

    def apply_control(self,target):
        from .control import validate_target
        from ...controllers.canonical.contracts import AppliedCanonicalControl
        validate_target(self,target);m=self._model;realized={};clipped=False
        for name,i in self._target_actuators.items():
            desired=target.arm_servo_position[name];value=float(np.clip(desired,*m.actuator_ctrlrange[i])) if m.actuator_ctrllimited[i] else desired
            self._ctrl[i]=value;realized[name]=value;clipped|=value!=desired
        self._set_arm_drives()
        opening=float(np.clip(target.gripper.servo_opening_m,0,self._control_binding.opening_range_m))
        for i in self._open_actuators:
            low,high=m.actuator_ctrlrange[i];self._ctrl[i]=float(low+opening/self._control_binding.opening_range_m*(high-low))
            self._force_limits[i]=(-target.gripper.force_limit_N,target.gripper.force_limit_N)
        return AppliedCanonicalControl('applied-canonical-control-v0',target.identity_hash,'sapien',realized,opening,target.gripper.force_limit_N,bool(clipped),
            'source_PD_native_arm_drive_fixed_tendon_public_force_ZOH')

    def _set_arm_drives(self):
        m=self._model
        for i in self._target_actuators.values():
            native=m.joint(int(m.actuator_trnid[i,0])).name
            joint=self._joint_bindings[native][2]
            joint.set_drive_target(float(self._ctrl[i]*m.actuator_gainprm[i,0]/-m.actuator_biasprm[i,1]))
            joint.set_drive_velocity_target(0.)

    def _apply_native_forces(self):
        m=self._model;forces={a:np.zeros(a.dof) for a in self._articulations}
        for n,(a,i,_,ji) in self._joint_bindings.items():
            if n not in self._arm_native_names:forces[a][i]-=float(m.dof_damping[m.jnt_dofadr[ji]])*float(a.get_qvel()[i])
        opening_force=0.
        for actuator in self._open_actuators:
            ctrl=self._ctrl[actuator];members=self._members
            position=sum(float(a.get_qpos()[i])*c for n,c in members for a,i,_,_ in [self._joint_bindings[n]])
            velocity=sum(float(a.get_qvel()[i])*c for n,c in members for a,i,_,_ in [self._joint_bindings[n]])
            force=float(m.actuator_gainprm[actuator,0]*ctrl+m.actuator_biasprm[actuator,1]*position+m.actuator_biasprm[actuator,2]*velocity)
            if actuator in self._force_limits:force=float(np.clip(force,*self._force_limits[actuator]))
            elif m.actuator_forcelimited[actuator]:force=float(np.clip(force,*m.actuator_forcerange[actuator]))
            if actuator in self._open_actuators:opening_force=force
            for n,c in members:
                a,i,_,_=self._joint_bindings[n];forces[a][i]+=c*force
        for a,f in forces.items():a.set_qf(f)
        # Measure the actually accepted public generalized force (float32),
        # removing separately authored joint damping from the opening members.
        measured=[]
        for n,c in self._members:
            a,i,_,ji=self._joint_bindings[n]
            damping=float(m.dof_damping[m.jnt_dofadr[ji]])*float(a.get_qvel()[i])
            measured.append((float(a.get_qf()[i])+damping)/c)
        self._completed_opening_force=float(np.mean(measured))

    def step(self):
        self._require_reset()
        if self._scene.get_timestep()!=self._native_timestep['expected_native_dt']:raise ValueError('native timestep changed')
        for _ in range(self._artifact.timebase.control_substeps):
            self._apply_native_forces();self._scene.step();self._native_steps+=1
        self._control_step+=1;return self.snapshot()

    def close(self):
        if not self._closed:
            for entity in self._entities.values():self._scene.remove_entity(entity)
            self._entities.clear();self._articulations.clear();self._scene=None;self._temp.cleanup();self._closed=True
