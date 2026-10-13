"""Read-only MuJoCo contact observer, separate from task/controller semantics.

AppliedStepObserver samples mj_step's forces before the session's subsequent
mj_forward, paired with preintegration qpos/qvel. Calling capture without pre
retains explicitly labeled post-forward evaluation semantics. Native forces
are SI forces, not impulses; force*dt is a rectangular force integral.
Contact frame rows map world vectors into (normal,tangent1,tangent2).
"""
from pathlib import Path
import gzip
import hashlib
import json
import numpy as np
import mujoco


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def wrench_at(force, intrinsic_torque, contact_position, reference_position):
    return intrinsic_torque + np.cross(contact_position-reference_position, force)


class NativeObserver:
    def __init__(self, output):
        self.output=Path(output)
        self.stream=gzip.open(self.output/'native.jsonl.gz','wt',compresslevel=1)
        self.count=0;self.errors=[];self.max_projection_error=0.;self.model_saved=False;self.model_hash=None

    def _model(self,m):
        fields=['body_mass','body_inertia','body_ipos','body_iquat','body_parentid',
                'geom_type','geom_size','geom_pos','geom_quat','geom_friction','geom_solref',
                'geom_solimp','geom_condim','geom_bodyid','geom_contype','geom_conaffinity',
                'geom_margin','geom_gap','actuator_trntype','actuator_trnid',
                'actuator_gainprm','actuator_biasprm','actuator_forcerange','actuator_ctrlrange',
                'dof_damping','dof_armature','jnt_qposadr','jnt_dofadr','jnt_range',
                'eq_type','eq_data','tendon_adr','tendon_num','wrap_type','wrap_objid','wrap_prm']
        result={k:np.asarray(getattr(m,k)).tolist() for k in fields}
        result.update(body_names=[m.body(i).name for i in range(m.nbody)],
                      geom_names=[m.geom(i).name for i in range(m.ngeom)],
                      joint_names=[m.joint(i).name for i in range(m.njnt)],
                      actuator_names=[m.actuator(i).name for i in range(m.nu)],
                      options={k:float(getattr(m.opt,k)) for k in ['timestep','impratio','solver','integrator','cone','iterations','tolerance','noslip_iterations','noslip_tolerance']},
                      gravity=m.opt.gravity.tolist(),mujoco_version=mujoco.__version__)
        self.model_hash=canonical_digest(result)
        (self.output/'compiled_model.json').write_text(json.dumps(result,indent=2)+'\n')
        self.model_saved=True

    def capture(self,session,stage,pre=None):
        m,d=session._model,session._data
        velocity=d.qvel if pre is None else pre["qvel"]
        if not self.model_saved:self._model(m)
        nut=session._bodies['square-nut-v1'];ee=session._frames['panda-v1/ee']
        p=d.site_xpos[ee].copy();r=d.site_xmat[ee].reshape(3,3).copy()
        np_=d.xpos[nut].copy();nr=d.xmat[nut].reshape(3,3).copy();com=d.xipos[nut].copy()
        ee_v=np.zeros(6);mujoco.mj_objectVelocity(m,d,mujoco.mjtObj.mjOBJ_SITE,ee,ee_v,0)
        nut_com_v=np.zeros(6);mujoco.mj_objectVelocity(m,d,mujoco.mjtObj.mjOBJ_BODY,nut,nut_com_v,0)
        # Body velocity reference is independently available from the COM Jacobian.
        jp=np.zeros((3,m.nv));jr=np.zeros((3,m.nv));mujoco.mj_jac(m,d,jp,jr,com,nut)
        com_velocity=jp@velocity;omega=jr@velocity
        contacts=[];net_force=np.zeros(3);net_origin=np.zeros(3);net_com=np.zeros(3)
        q_projected=np.zeros(m.nv);normal={'left':0.,'right':0.,'table':0.}
        for ci in range(d.ncon):
            c=d.contact[ci];b1=int(m.geom_bodyid[c.geom1]);b2=int(m.geom_bodyid[c.geom2])
            bn=[m.body(b1).name,m.body(b2).name]
            has_nut=nut in [b1,b2]
            finger_table=any(b in ['left_finger','right_finger'] for b in bn) and any('table' in b for b in bn)
            if not has_nut and not finger_table:continue
            w=np.zeros(6);mujoco.mj_contactForce(m,d,ci,w)
            frame=c.frame.reshape(3,3).copy();fw=frame.T@w[:3];tw=frame.T@w[3:]
            j1=np.zeros((3,m.nv));j2=np.zeros((3,m.nv));rot1=np.zeros((3,m.nv));rot2=np.zeros((3,m.nv))
            mujoco.mj_jac(m,d,j1,rot1,c.pos,b1);mujoco.mj_jac(m,d,j2,rot2,c.pos,b2)
            rel_velocity=frame@((j2-j1)@velocity)
            sign=1 if b2==nut else -1
            force=sign*fw if has_nut else np.zeros(3);intrinsic=sign*tw if has_nut else np.zeros(3)
            origin_torque=wrench_at(force,intrinsic,c.pos,np_)
            com_torque=wrench_at(force,intrinsic,c.pos,com)
            if has_nut:
                net_force+=force;net_origin+=origin_torque;net_com+=com_torque
                mujoco.mj_applyFT(m,d,force,intrinsic,c.pos,nut,q_projected)
                for side,body in [('left','left_finger'),('right','right_finger')]:
                    if body in bn:normal[side]+=w[0]
                if any('table' in b for b in bn):normal['table']+=w[0]
            friction=np.asarray(c.friction);dim=int(c.dim)
            values=w[1:dim];coeffs=friction[:dim-1]
            scaled=np.divide(values,coeffs,out=np.zeros_like(values),where=coeffs>0)
            norm=float(np.sum(np.abs(scaled))) if int(m.opt.cone)==0 else float(np.linalg.norm(scaled))
            utilization=norm/float(w[0]) if w[0]>1e-8 else None
            budgets=None;axis_use=None
            if int(m.opt.cone)==0 and c.efc_address>=0 and dim>1:
                edges=np.asarray(d.efc_force[int(c.efc_address):int(c.efc_address)+2*(dim-1)]).reshape(-1,2)
                budgets=edges.sum(axis=1)
                axis_use=np.divide(np.abs(edges[:,0]-edges[:,1]),budgets,out=np.zeros_like(budgets),where=budgets>1e-10)
                budgets=budgets.tolist();axis_use=axis_use.tolist()
            contacts.append({'id':ci,'geom_ids':[int(c.geom1),int(c.geom2)],
                'geom_names':[m.geom(c.geom1).name,m.geom(c.geom2).name],
                'bodies':bn,'has_nut':has_nut,'finger_table':finger_table,
                'position_world_m':c.pos.tolist(),'frame_world_to_contact':frame.tolist(),
                'distance_m':float(c.dist),'dim':dim,'friction':friction.tolist(),
                'solref':c.solref.tolist(),'solimp':c.solimp.tolist(),
                'solreffriction':np.asarray(getattr(c,'solreffriction',[])).tolist(),
                'efc_address':int(c.efc_address),'wrench_contact_N_Nm':w.tolist(),
                'force_integral_rectangle_Ns':(w[:3]*m.opt.timestep).tolist(),
                'relative_velocity_contact_m_s':rel_velocity.tolist(),'relative_angular_velocity_contact_rad_s':(frame@((rot2-rot1)@velocity)).tolist(),
                'cone_utilization':utilization,'pyramidal_pair_normal_budget_N':budgets,'pyramidal_pair_axis_utilization':axis_use,
                'force_on_nut_world_N':force.tolist(),
                'torque_on_nut_body_origin_world_Nm':origin_torque.tolist(),
                'torque_on_nut_COM_world_Nm':com_torque.tolist()})
        j=int(m.body_jntadr[nut]);adr=int(m.jnt_dofadr[j])
        mass_matrix=np.zeros((m.nv,m.nv));mujoco.mj_fullM(m,mass_matrix,d.qM)
        projection_error=float(np.max(np.abs(q_projected[adr:adr+6]-d.qfrc_constraint[adr:adr+6])))
        self.max_projection_error=max(self.max_projection_error,projection_error)
        if projection_error>1e-7:
            self.errors.append({'time':float(d.time),'solver_niter':d.solver_niter.tolist(),'solver_last_improvement':[float(d.solver[i*(len(d.solver)//len(d.solver_niter))+int(n)-1].improvement) if n else None for i,n in enumerate(d.solver_niter)],'contact_projection_error':projection_error,'solver_options':{k:float(getattr(m.opt,k)) for k in ['impratio','cone','noslip_iterations','noslip_tolerance']}})
        if any(c['wrench_contact_N_Nm'][0]<-1e-10 for c in contacts):
            self.errors.append({'time':float(d.time),'negative_normal_force':True})
        rp=r.T@(np_-p);rr=r.T@nr
        row={'sampling_semantics':'post_forward_evaluation' if pre is None else 'integrated_step_force_preintegration_state', 'time_end_s':float(d.time), 'post_qpos':d.qpos.tolist(), 'post_qvel':d.qvel.tolist(), 'time_s':float(d.time) if pre is None else pre['time_s'],'phase':stage,'control_step':session._control_step,
             'ee_p':p.tolist(),'ee_R':r.reshape(-1).tolist(),'ee_twist_world_rot_lin':ee_v.tolist(),
             'nut_p':np_.tolist(),'nut_R':nr.reshape(-1).tolist(),'nut_COM_p':com.tolist(),
             'nut_COM_velocity_world_m_s':com_velocity.tolist(),'nut_omega_world_rad_s':omega.tolist(),
             'rel_p':rp.tolist(),'rel_R':rr.reshape(-1).tolist(),
             'qpos':d.qpos.tolist() if pre is None else pre['qpos'].tolist(),'qvel':velocity.tolist(),'qacc':d.qacc.tolist(),
             'ctrl':d.ctrl.tolist(),'actuator_force_completed':session._completed_actuator_force.tolist(),
             'actuator_force_current':d.actuator_force.tolist(),
             'actuator_force_applied':d.actuator_force.tolist() if pre is not None else None,
             'nut_contact_force_world_N':net_force.tolist(),
             'nut_contact_torque_body_origin_world_Nm':net_origin.tolist(),
             'nut_contact_torque_COM_world_Nm':net_com.tolist(),
             'normal_load_N':normal,'contacts':contacts,
             'nut_constraint_generalized_force_native':d.qfrc_constraint[adr:adr+6].tolist(),
             'nut_passive_generalized_force_native':d.qfrc_passive[adr:adr+6].tolist(),
             'nut_free_dof_armature':m.dof_armature[adr:adr+6].tolist(),
             'nut_free_dof_damping':m.dof_damping[adr:adr+6].tolist(),
             'nut_generalized_inertia_native_block':mass_matrix[adr:adr+6,adr:adr+6].tolist(),
             'solver_niter':d.solver_niter.tolist(),'solver_last_improvement':[float(d.solver[i*(len(d.solver)//len(d.solver_niter))+int(n)-1].improvement) if n else None for i,n in enumerate(d.solver_niter)],'contact_projection_error':projection_error,'solver_options':{k:float(getattr(m.opt,k)) for k in ['impratio','cone','noslip_iterations','noslip_tolerance']}}
        self.stream.write(json.dumps(row,separators=(',',':'))+'\n');self.count+=1
        return {'schema':'native-contact-summary-v1','sample_time_s':float(d.time),
                'normal_load_N':normal,'contact_projection_error':projection_error,
                'native_sidecar':'native.jsonl.gz'}

    def close(self):self.stream.close()


class AppliedStepObserver:
    """Delegate unchanged mj_step; read its forces before subsequent mj_forward."""
    def __init__(self, module, session, observer, phase):
        self.module=module;self.session=session;self.observer=observer;self.phase=phase
        self.latest={'available':False,'reason':'no integrated step yet'}
    def __getattr__(self,name):return getattr(self.module,name)
    def mj_step(self,m,d):
        pre={'time_s':float(d.time),'qpos':d.qpos.copy(),'qvel':d.qvel.copy()}
        self.module.mj_step(m,d)
        try:self.latest=self.observer.capture(self.session,self.phase(),pre)
        except Exception as exc:
            self.observer.errors.append({'time_s':pre['time_s'],'required_contact_capture_error':repr(exc)})
            self.latest={'available':False,'error':repr(exc)}
