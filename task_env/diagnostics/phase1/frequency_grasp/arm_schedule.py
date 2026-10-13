"""Isolated arm-ramp intervention. No native stepping or clock exceptions.

Copied lifecycle of SessionBase.step_control_interval; only per-step target
formation changes after lift release. Every realized target goes through
normal validation, audit, recorder and AppliedCanonicalControl.
"""
import math
from dataclasses import dataclass
import numpy as np
from ..multirate.common import NativeAudit
from ....controllers.canonical.contracts import digest

@dataclass
class ArmRampMemory:
    last_applied_arm: dict | None = None


def ramped_control_interval(self, held_target, gripper_inner_servo, *, audit=None,
                          diagnostic_readback=None, interval_observer=None):
    """Diagnostic ramped arm stream; gripper cadence/physics unchanged."""
    from dataclasses import replace
    self._require_reset()
    start = self.snapshot()
    active = self._diagnostic_arm_ramp_active()
    memory=self._diagnostic_arm_ramp_memory
    if active and memory.last_applied_arm is None:
        raise ValueError('arm ramp requires a preceding public applied acknowledgement')
    initial=dict(memory.last_applied_arm or held_target.arm_servo_position)
    if audit is not None:
        audit._diagnostic_plan=(initial,dict(held_target.arm_servo_position),active)
        audit.begin_inner_interval(start)
    substep_rows = []
    last_target = None
    last_applied = None
    self._inner_interval_active = True
    try:
        for substep_index in range(self._artifact.timebase.control_substeps):
            state = self.snapshot()
            feedback = self.control_feedback(state)
            gripper_target, diagnostics = gripper_inner_servo.inner_gripper_step(state, feedback)
            target = replace(held_target, gripper=gripper_target)
            if active:
                fraction=(substep_index+1)/self._artifact.timebase.control_substeps
                arm={name:initial[name]+fraction*(value-initial[name]) for name,value in held_target.arm_servo_position.items()}
                target=replace(target,arm_position=arm,arm_servo_position=arm)
            last_applied = self.apply_control(target)
            memory.last_applied_arm=dict(last_applied.arm_servo_position)
            if audit is None:
                self._step_physics_once()
            else:
                audit.execute_inner_substep(target, self._step_physics_once)
            if interval_observer is not None:
                interval_observer(substep_index, state, feedback, target, last_applied, diagnostics)
            row = dict(diagnostics)
            row.update({
                "substep_index": substep_index,
                "control_step": state.control_step,
                "simulation_time_s": state.simulation_time,
                "target_hash": target.identity_hash,
                "arm_target_hash": digest({
                    "arm_position": dict(target.arm_position),
                    "arm_servo_position": dict(target.arm_servo_position),
                }),
                "applied_control": last_applied.to_mapping(),
            })
            if diagnostic_readback is not None:
                try:
                    row["native_contact_diagnostic"] = diagnostic_readback(self)
                except Exception as exc:  # diagnostic availability must not affect control
                    row["native_contact_diagnostic"] = {
                        "available": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
            substep_rows.append(row)
            last_target = target
    finally:
        self._inner_interval_active = False
    self._control_step += 1
    final_state = self.snapshot()
    if audit is not None:
        audit.complete_inner_interval(final_state)
    return final_state, last_target, last_applied, substep_rows


class RampedArmAudit(NativeAudit):
    """Distinct diagnostic admission; clock and realized hashes stay strict."""
    def begin_inner_interval(self,before):
        super().begin_inner_interval(before);self._ramp_verified_count=0
    def execute_inner_substep(self,target,step_once):
        initial,end,active=self._diagnostic_plan
        fraction=(self._ramp_verified_count+1)/self.timebase.control_substeps
        expected={k:initial[k]+fraction*(end[k]-initial[k]) if active else end[k] for k in end}
        for field in [target.arm_position,target.arm_servo_position]:
            if set(field)!=set(expected) or any(abs(field[k]-expected[k])>1e-14 for k in expected):
                raise ValueError('diagnostic_arm_ramp_schedule_mismatch')
        result=super().execute_inner_substep(target,step_once)
        self._ramp_verified_count+=1
        return result
    def complete_inner_interval(self, after):
        if self._inner_start is None:raise ValueError('inner interval audit was not started')
        before,count_before=self._inner_start
        observed=self.count-count_before
        dt=after.simulation_time-before.simulation_time
        error=abs(dt-self.timebase.control_dt)
        expected_boundary_time=after.control_step*self.timebase.control_dt
        boundary_clock_error=abs(after.simulation_time-expected_boundary_time)
        # Bound cumulative binary64 rounding from native physics_dt additions,
        # plus the final expected-boundary multiplication. A one-ULP bound on
        # each interval is too strict after several separately rounded steps.
        nu=max(self.count,1)*2.0**-53
        if nu>=1:raise ValueError('inner interval clock bound unavailable')
        bound=nu/(1.0-nu)*abs(expected_boundary_time)+math.ulp(expected_boundary_time)
        same_arm=len(set(self._inner_arm_hashes))==1
        row={'control_step':after.control_step,'simulation_time_s':after.simulation_time,
            'observed_native_substeps':observed,'requested_native_substeps':self.timebase.control_substeps,
            'target_hashes':list(self._inner_expected_hashes),
            'all_substep_target_hashes_observed':self.hashes==self._inner_expected_hashes,
            'all_substep_hashes_identical':len(set(self._inner_expected_hashes))<=1,
            'arm_target_held':same_arm,'time_increment_s':dt,'time_increment_error_s':error,
            'expected_boundary_time_s':expected_boundary_time,
            'boundary_clock_error_s':boundary_clock_error,
            'cumulative_binary64_time_bound_s':bound}
        self.boundaries.append(row)
        self._inner_start=None
        if observed!=self.timebase.control_substeps:raise ValueError('provider_native_substep_count')
        if after.control_step!=before.control_step+1 or boundary_clock_error>bound:raise ValueError('canonical_timebase_alignment')
        if not row['all_substep_target_hashes_observed'] or self._ramp_verified_count!=observed:raise ValueError('diagnostic_ramp_target_sequence_integrity')
        row['arm_schedule']='linear-native-ramp-after-lift-v2-public-ack-memory'
        row['arm_schedule_verified_substeps']=self._ramp_verified_count
        return row

