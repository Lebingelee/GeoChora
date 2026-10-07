"""Versioned, provider-free NutAssembly solution with physical-time planning.

Historical solution remains unchanged. Readiness uses canonical observations
and optional public control readiness only; native contacts are not inputs.
"""
from dataclasses import dataclass, asdict
import hashlib
import math
from pathlib import Path
import numpy as np
from ...planners import AbsolutePosePlanner, AbsolutePosePlannerConfig, ExpertAction
from ...controllers.canonical.contracts import digest
from ...utils.rotation import normalize_quat_wxyz, rotate_vector_wxyz, quat_multiply_wxyz, quat_angle_wxyz
from .assets import PEG_HALF_HEIGHT, NUT_HALF_HEIGHT, NUT_CONTACT_MARGIN, TABLE_TOP_Z
from .solution import _square_yaw_correction


@dataclass(frozen=True)
class CanonicalNutAssemblyConfig:
    # Historical achieved close pose: handle offset (-.020,0,+.0499).
    # +2mm request clearance accommodates achieved-state controller equilibrium.
    grasp_offset: tuple = (0., 0., .052)
    grasp_quaternion_wxyz: tuple = (-.0001953937, .9996899962, .0248992145, -.000055298)
    grasp_opening_m: float = .022
    opening_range_m: float = .08
    approach_height_m: float = .12
    translation_speed_m_s: float = .12
    translation_acceleration_m_s2: float = .9
    rotation_speed_rad_s: float = 3.
    rotation_acceleration_rad_s2: float = 27.
    settle_duration_s: float = 8./30.
    close_transition_s: float = 10./30.
    close_settle_s: float = 15./30.
    release_transition_s: float = 10./30.
    release_settle_s: float = 20./30.
    pose_position_ready_m: float = .007
    pose_rotation_ready_rad: float = .06
    readiness_stable_s: float = .10
    gripper_stable_speed_m_s: float = .003
    max_pose_hold_s: float = 3.
    max_close_hold_s: float = 8.
    max_release_hold_s: float = 3.
    verify_lift_m: float = .10
    max_stage_plan_s: float = 6.
    action_budget_s: float = 60.

    def __post_init__(self):
        if len(self.grasp_offset)!=3 or len(self.grasp_quaternion_wxyz)!=4:
            raise ValueError('physical grasp pose required')
        if not all(math.isfinite(float(x)) for x in (*self.grasp_offset,*self.grasp_quaternion_wxyz)):
            raise ValueError('finite grasp geometry required')
        for k,v in asdict(self).items():
            if k not in {'grasp_offset','grasp_quaternion_wxyz'} and (not math.isfinite(v) or v<=0):
                raise ValueError('positive physical-time config required: '+k)
        normalize_quat_wxyz(self.grasp_quaternion_wxyz)


class NutAssemblyCanonicalSolutionV1:
    version='nut-assembly-canonical-solution-v1'
    STAGES=('approach_nut','descend_to_handle','close_gripper','verify_lift',
        'raise_for_transport','move_above_square_peg','align_nut_yaw','descend_to_peg_top',
        'lower_nut_to_table','open_gripper','release_retreat')

    def __init__(self, *, config=None, control_dt):
        self.config=config or CanonicalNutAssemblyConfig();self.control_dt=float(control_dt)
        if not math.isfinite(self.control_dt) or self.control_dt<=0:raise ValueError('positive control_dt required')
        c=self.config;dt=self.control_dt
        self._planner=AbsolutePosePlanner(AbsolutePosePlannerConfig(
            max_translation_per_step=c.translation_speed_m_s*dt,
            max_translation_acceleration_per_step=c.translation_acceleration_m_s2*dt*dt,
            max_rotation_per_step=c.rotation_speed_rad_s*dt,
            max_rotation_acceleration_per_step=c.rotation_acceleration_rad_s2*dt*dt,
            settle_steps=self._ticks(c.settle_duration_s),max_steps=self._ticks(c.max_stage_plan_s)))
        self.source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.identity=digest({'version':self.version,'config':asdict(c),'source_sha256':self.source_sha256,
            'planning':'physical-time-derived-ticks','readiness':'canonical-pose-gripper-and-outcome'})
        self._done=False;self._failed=False;self._failure_reason=None

    def _ticks(self, seconds):return max(1,int(math.ceil(seconds/self.control_dt-1e-10)))
    @property
    def stage(self):return self.STAGES[self._stage_index]
    @property
    def done(self):return self._done
    @property
    def failed(self):return self._failed
    @property
    def failure_reason(self):return self._failure_reason

    @staticmethod
    def _ee(obs):return np.asarray(obs['state']['ee_pose'],dtype=float).reshape(7)
    @staticmethod
    def _body(obs,name):return np.asarray(obs['privileged_state'][name+'_body_pose'][0],dtype=float).reshape(7)

    def reset(self, observation, info, metadata):
        schema=metadata.get('action_schema',{})
        if (schema.get('controller_kind'),schema.get('reference'),schema.get('rotation_representation'))!=('absolute_pose','world','quaternion_wxyz'):
            raise ValueError('absolute_pose/world/wxyz required')
        self._stage_index=0;self._emitted=0;self._done=bool(info.get('is_success',False));self._failed=False;self._failure_reason=None
        self._last_opening=float(info['task_metrics']['gripper_opening']);self._plan(observation)

    def _plan(self, obs):
        c=self.config;ee=self._ee(obs);nut=self._body(obs,'square_nut_v1');peg=self._body(obs,'square_peg_v1')
        handle=nut[:3]+rotate_vector_wxyz(nut[3:],np.array([.054,0,0]));pose=ee.copy();pose[3:]=normalize_quat_wxyz(c.grasp_quaternion_wxyz)
        stage=self.stage;gripper=2*c.grasp_opening_m/c.opening_range_m-1.
        if stage=='approach_nut':pose[:3]=handle+np.array([c.grasp_offset[0],c.grasp_offset[1],c.approach_height_m]);gripper=1.
        elif stage=='descend_to_handle':pose[:3]=handle+np.array(c.grasp_offset);gripper=1.
        elif stage=='close_gripper':pose=self._grasp_pose.copy()
        elif stage=='verify_lift':pose[:3]=ee[:3]+np.array([0.,0.,c.verify_lift_m])
        else:
            # Achieved canonical relative pose, not assumed provider dynamics.
            nut_to_ee=nut[:3]-ee[:3];hover_nut=peg[:3]+[0.,0.,PEG_HALF_HEIGHT+.08]
            if stage=='raise_for_transport':pose[2]=(hover_nut-nut_to_ee)[2]
            elif stage=='move_above_square_peg':pose[:3]=hover_nut-nut_to_ee
            elif stage=='align_nut_yaw':
                yaw=_square_yaw_correction(nut[3:]);q=np.array([np.cos(yaw/2),0.,0.,np.sin(yaw/2)]);pose[3:]=quat_multiply_wxyz(q,ee[3:])
            elif stage=='descend_to_peg_top':pose[:3]=peg[:3]+[0.,0.,PEG_HALF_HEIGHT+NUT_HALF_HEIGHT+NUT_CONTACT_MARGIN]-nut_to_ee
            elif stage=='lower_nut_to_table':pose[:3]=np.array([peg[0],peg[1],TABLE_TOP_Z+NUT_HALF_HEIGHT+NUT_CONTACT_MARGIN])-nut_to_ee
            elif stage=='open_gripper':pose=ee.copy();gripper=1.
            elif stage=='release_retreat':pose[:3]=ee[:3]+[0.,0.,.10];gripper=1.
        if stage=='descend_to_handle':self._grasp_pose=pose.copy()
        self._goal=pose.copy();self._index=0;self._hold_ticks=0;self._stable_ticks=0
        if stage=='close_gripper':self._actions=self._planner.plan_gripper_transition(pose=pose,start_gripper=1.,goal_gripper=gripper,steps=self._ticks(c.close_transition_s),settle_steps=self._ticks(c.close_settle_s))
        elif stage=='open_gripper':self._actions=self._planner.plan_gripper_transition(pose=pose,start_gripper=2*c.grasp_opening_m/c.opening_range_m-1.,goal_gripper=1.,steps=self._ticks(c.release_transition_s),settle_steps=self._ticks(c.release_settle_s))
        else:self._actions=self._planner.plan_to_pose(current_pose=ee,goal_pose=pose,gripper=gripper)

    def act(self):
        if self.done or self.failed:raise RuntimeError('cannot act after completion')
        hold=self._index>=len(self._actions);action=self._actions[-1] if hold else self._actions[self._index]
        diagnostics={'version':self.version,'stage_index':self._stage_index,'stage_step':self._index,
            'readiness_hold':hold,'hold_seconds':self._hold_ticks*self.control_dt,'control_dt':self.control_dt}
        if hold:self._hold_ticks+=1
        else:self._index+=1
        self._emitted+=1
        return ExpertAction(action=action.copy(),stage=self.stage,diagnostics=diagnostics)

    def observe(self,obs,reward,terminated,truncated,info,*,readiness=None):
        del reward
        if info.get('is_success',False):self._done=True;return
        if terminated or truncated:self._fail('environment_terminated');return
        if self._emitted>self._ticks(self.config.action_budget_s):self._fail('canonical_solution_action_budget');return
        metrics=info['task_metrics'];opening=float(metrics['gripper_opening']);opening_speed=abs(opening-self._last_opening)/self.control_dt;self._last_opening=opening
        if self._index<len(self._actions):return
        ee=self._ee(obs);c=self.config;stage=self.stage
        pose_ready=np.linalg.norm(ee[:3]-self._goal[:3])<=c.pose_position_ready_m and quat_angle_wxyz(ee[3:],self._goal[3:])<=c.pose_rotation_ready_rad
        limit=c.max_pose_hold_s;ready=pose_ready
        if stage=='close_gripper':
            force_ready=bool(readiness and readiness.gripper.close_ready)
            ready=bool(metrics['grasped_nut']) and (force_ready or opening_speed<=c.gripper_stable_speed_m_s)
            limit=c.max_close_hold_s
        elif stage=='verify_lift':ready=pose_ready and bool(metrics['lifted_nut'])
        elif stage=='move_above_square_peg':ready=pose_ready and bool(metrics['hovered_over_peg'])
        elif stage=='lower_nut_to_table':ready=pose_ready and bool(metrics['inserted_on_peg'])
        elif stage=='open_gripper':
            ready=opening>=.065;limit=c.max_release_hold_s
        self._stable_ticks=self._stable_ticks+1 if ready else 0
        if self._stable_ticks>=self._ticks(c.readiness_stable_s):
            if stage=='release_retreat':self._fail('release_retreat_without_canonical_success');return
            self._stage_index+=1;self._plan(obs)
        elif self._hold_ticks>=self._ticks(limit):self._fail(stage+'_readiness_timeout')

    def _fail(self,reason):self._failed=True;self._failure_reason=reason
