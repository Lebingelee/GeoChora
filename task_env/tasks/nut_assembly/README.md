# NutAssemblySquare solution ownership

`solution.py` remains the historical compatibility solution. Its implementation,
task geometry, canonical task semantics, initialization, production controller,
and provider adapters are unchanged by P1.8-E-R2.

`canonical_solution.py` contains the **experimental, unqualified**
`NutAssemblyCanonicalSolutionV1`. It emits public `absolute_pose/world/wxyz`
actions from canonical observations and readiness. One configuration expresses
planning and holds in physical time; `control_dt` derives tick counts. It has no
provider selection, native contact input, or simulator import. It is not
registered as a replacement for the historical solution.

The paired recovery detector lives in
`task_env.diagnostics.phase1.nutassembly_recovery`. Its `campaign` entry point
archives each solution/configuration before isolated provider execution. The
`grasp_lift` scope stops after verification lift and cannot establish full task
success. `analysis` consumes recorded traces without simulation. Required
governed source bytes and run artifacts belong under
`workspace/qualification/phase1/p1_8_nutassembly_solution_recovery/`.

The instantaneous `gripper_stable_speed_m_s` configuration value is retained in
archived configurations; current readiness uses a physical-time opening window
and measured canonical load instead. The production controller's force
readiness remains unchanged. Verification lift additionally checks the
nut/EE relative pose rather than treating `grasped_nut` or `lifted_nut` alone as
proof of stable capture.

Historical 30 Hz legacy success does not qualify this canonical candidate.
Qualification requires six successful source trajectories, a solution lock,
six exact D0 reconstructions, and 24 valid D1/D2 replay cells. Until those gates
and Human review succeed, P1.8-E remains PARTIAL / NOT APPROVED.
