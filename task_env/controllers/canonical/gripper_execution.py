"""Equal outer/gripper-rate cadence for the verified R5 candidate.

Closed grasp hold still regulates force once per outer boundary; the native
actuator target is held only between those updates. Fixed-500Hz R3 inner mode
remains available separately and is not covered by 10N development evidence.
"""
class EqualRateGripperServo:
    """Update gripper once per outer boundary at a physical outer-rate dt."""
    def __init__(self, controller, rate_hz, outer_dt_s):
        self.controller=controller; self.rate_hz=int(rate_hz); self.outer_dt_s=float(outer_dt_s)
        self._update=controller.inner_gripper_step
        self._last_control_step=None; self._last_target=None; self._last_diagnostics=None
        self.update_count=0; self.held_count=0
    def __getattr__(self,name): return getattr(self.controller,name)
    def inner_gripper_step(self,state,feedback):
        due=state.control_step != self._last_control_step
        if due:
            old_dt=self.controller.inner_physics_dt_s
            try:
                self.controller.inner_physics_dt_s=self.outer_dt_s
                target,diagnostics=self._update(state,feedback)
            finally:
                self.controller.inner_physics_dt_s=old_dt
            self._last_control_step=state.control_step; self._last_target=target
            self._last_diagnostics=dict(diagnostics); self.update_count+=1
            diagnostics=dict(diagnostics)
            diagnostics.update(inner_update_performed=True,
                               inner_update_period_s=self.outer_dt_s,
                               configured_inner_rate_hz=self.rate_hz)
            return target,diagnostics
        if self._last_target is None or self._last_diagnostics is None:
            raise RuntimeError('inner target was not initialized at the first physics substep')
        self.held_count+=1; previous=self._last_diagnostics
        return self._last_target,{
            'measured_opening_m':float(feedback.gripper.opening_m),
            'commanded_opening_m':float(previous['commanded_opening_m']),
            'desired_opening_m':float(previous['desired_opening_m']),
            'closing_force_N':float(feedback.gripper.closing_force_N),
            'force_mode_active':bool(self.controller._force_mode),
            'force_mode_initialized':bool(self.controller._force_initialized),
            'controller_close_ready':bool(previous['controller_close_ready']),
            'command_saturated_at_zero':bool(previous['command_saturated_at_zero']),
            'inner_update_performed':False,
            'inner_update_period_s':self.outer_dt_s,
            'configured_inner_rate_hz':self.rate_hz,
        }
