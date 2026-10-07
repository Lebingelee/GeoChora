"""Private CPU Genesis MJCF session using public entity APIs.

MuJoCo's public source compiler resolves authored defaults/actuator facts only;
no MuJoCo simulation/state is used. Fixed tendon PD is lowered mechanically to
its member joints, with imported joint equality retained by Genesis. Native
indices and temporary MJCF/mesh resources remain private.
"""
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from .common import _SessionValues, pose


def array(value):
    return value.detach().cpu().numpy() if hasattr(value, 'detach') else np.asarray(value)


class _GenesisSession(_SessionValues):
    def __init__(self, artifact, source):
        self._initialize_values(artifact, source, 'genesis')
        import genesis as gs
        import mujoco
        from ...utils.rotation import quat_wxyz_to_matrix
        self._gs = gs; self._temporary = tempfile.TemporaryDirectory(prefix='geochora-genesis-')
        root = ET.fromstring(source.scene_source.xml)
        for element in root.iter('freejoint'):
            element.tag='joint'; element.set('type','free')
        for element in root.findall('keyframe'): root.remove(element)
        xml = ET.tostring(root, encoding='unicode')
        authored = mujoco.MjModel.from_xml_string(xml)
        self._target_actuators={semantic:int(authored.actuator(native).id) for semantic,native in source.joint_targets.items()}
        self._open_actuators=tuple(int(authored.actuator(name).id) for name in source.open_actuators)
        if len(self._open_actuators)!=1:raise ValueError('one fixed tendon control binding required')
        i=self._open_actuators[0]
        if authored.actuator_trntype[i]!=mujoco.mjtTrn.mjTRN_TENDON:raise ValueError('fixed tendon source required')
        tendon=authored.actuator_trnid[i,0];start=authored.tendon_adr[tendon];count=authored.tendon_num[tendon]
        native_to_semantic={v:k for k,v in source.joints.items()};self._fingers=[]
        for index in range(start,start+count):
            if authored.wrap_type[index]!=mujoco.mjtWrap.mjWRAP_JOINT:raise ValueError('only named fixed tendon members supported')
            name=authored.joint(int(authored.wrap_objid[index])).name
            coefficient=float(authored.wrap_prm[index])
            if name not in native_to_semantic or coefficient<=0:raise ValueError('positive named tendon member required')
            self._fingers.append((native_to_semantic[name],coefficient))
        if len(self._fingers)!=2 or self._fingers[0][1]!=self._fingers[1][1]:raise ValueError('symmetric two-member fixed tendon only')
        self._authored=authored;self._frames={}
        gs.init(backend=gs.cpu, precision='64',logging_level='warning')
        self._scene=gs.Scene(sim_options=gs.options.SimOptions(dt=artifact.timebase.physics_dt,gravity=tuple(authored.opt.gravity)),
            rigid_options=gs.options.RigidOptions(enable_torsional_friction=bool(np.any(authored.geom_condim>=4)),
                enable_rolling_friction=bool(np.any(authored.geom_condim>=6)),enable_neutral_collision=True),show_viewer=False)
        path=Path(self._temporary.name)/'source.xml';path.write_text(xml)
        self._entity=self._scene.add_entity(morph=gs.morphs.MJCF(file=str(path),default_armature=None))
        self._scene.build()
        self._joints={semantic:self._entity.get_joint(name) for semantic,name in source.joints.items()}
        self._free={semantic:self._entity.get_joint(name) for semantic,name in source.free_joints.items()}
        self._bodies={semantic:self._entity.get_link(name) for semantic,name in source.bodies.items()}
        for semantic,native in source.frames.items():
            site=authored.site(native).id;body=authored.body(int(authored.site_bodyid[site])).name
            self._frames[semantic]=(self._entity.get_link(body),authored.site_pos[site].copy(),quat_wxyz_to_matrix(authored.site_quat[site]))
        for semantic,index in self._target_actuators.items():
            if authored.actuator_trntype[index]!=mujoco.mjtTrn.mjTRN_JOINT:raise ValueError('named joint servo required')
            self._drive(self._joints[semantic].dofs_idx_local[0],index,1.)
        for semantic,coefficient in self._fingers:self._drive(self._joints[semantic].dofs_idx_local[0],i,coefficient)
        self._native_initial=self._entity.get_qpos().clone()

    def _drive(self, index, actuator, coefficient):
        m=self._authored
        if m.actuator_biasprm[actuator,0]!=0 or m.actuator_biasprm[actuator,1]>=0:raise ValueError('affine position servo required')
        self._entity.set_dofs_kp([-float(m.actuator_biasprm[actuator,1])*coefficient**2],[index])
        self._entity.set_dofs_kv([-float(m.actuator_biasprm[actuator,2])*coefficient**2],[index])
        low,high=m.actuator_forcerange[actuator]*coefficient
        self._entity.set_dofs_force_range([float(low)],[float(high)],[index])

    def reset(self,sample):
        self._validate_sample(sample);self._scene.reset()
        q=self._native_initial.clone()
        for semantic,value in sample.joint_position.items():q[self._joints[semantic].qs_idx_local]=value
        for semantic,requested in sample.poses_world.items():
            indices=self._free[semantic].qs_idx_local
            q[indices]=self._gs.tensor((*requested.position,*requested.quaternion_wxyz))
        self._entity.set_qpos(q,zero_velocity=True)
        for semantic in self._target_actuators:
            self._entity.control_dofs_position([sample.joint_position[semantic]],[self._joints[semantic].dofs_idx_local[0]])
        for semantic,_ in self._fingers:self._entity.control_dofs_position([sample.joint_position[semantic]],[self._joints[semantic].dofs_idx_local[0]])
        return self._realized(sample)

    def snapshot(self):
        self._require_reset();from ...utils.rotation import quat_wxyz_to_matrix,matrix_to_quat_wxyz
        positions={k:float(array(self._entity.get_dofs_position([v.dofs_idx_local[0]]))[0]) for k,v in self._joints.items()}
        velocities={k:float(array(self._entity.get_dofs_velocity([v.dofs_idx_local[0]]))[0]) for k,v in self._joints.items()}
        poses={k:pose(array(v.get_pos()),array(v.get_quat())) for k,v in self._bodies.items()}
        for name,(link,offset,rotation) in self._frames.items():
            r=quat_wxyz_to_matrix(array(link.get_quat()))
            poses[name]=pose(array(link.get_pos())+r@offset,matrix_to_quat_wxyz(r@rotation))
        return self._state(positions,velocities,poses,float(array(self._scene.get_time())))

    def control_feedback(self,state):
        from ...controllers.canonical.feedback import CanonicalControlFeedback,CanonicalGripperFeedback
        if state.to_mapping()!=self.snapshot().to_mapping():raise ValueError('feedback requires current measured state')
        indices=[self._joints[name].dofs_idx_local[0] for name,_ in self._fingers]
        forces=array(self._entity.get_dofs_control_force(indices))
        opening=max(0.,sum(state.joint_position[name] for name,_ in self._fingers))
        return CanonicalControlFeedback('canonical-control-feedback-v0',state.control_step,state.simulation_time,
            CanonicalGripperFeedback(self._control_binding.gripper_semantic_id,opening,max(0.,-float(forces.sum()))))

    def apply_control(self,target):
        from .control import validate_target
        from ...controllers.canonical.contracts import AppliedCanonicalControl
        validate_target(self,target);realized={};clipped=False
        for name,index in self._target_actuators.items():
            desired=target.arm_servo_position[name];low,high=self._authored.actuator_ctrlrange[index]
            value=float(np.clip(desired,low,high)) if self._authored.actuator_ctrllimited[index] else desired
            clipped=clipped or value!=desired;realized[name]=value
            self._entity.control_dofs_position([value],[self._joints[name].dofs_idx_local[0]])
        opening=target.gripper.servo_opening_m
        for name,coefficient in self._fingers:
            dof=self._joints[name].dofs_idx_local[0]
            self._entity.set_dofs_force_range([-target.gripper.force_limit_N*coefficient],[target.gripper.force_limit_N*coefficient],[dof])
            self._entity.control_dofs_position([opening/len(self._fingers)],[dof])
        return AppliedCanonicalControl('applied-canonical-control-v0',target.identity_hash,'genesis',realized,opening,target.gripper.force_limit_N,clipped,
            'source_derived_symmetric_fixed_tendon_PD_joint_mapping_native_equality_ZOH')

    def step(self):
        self._require_reset()
        for _ in range(self._artifact.timebase.control_substeps):self._scene.step()
        self._control_step+=1;return self.snapshot()

    def close(self):
        if not self._closed:
            self._scene.destroy();self._gs.destroy();self._temporary.cleanup();self._closed=True
