# Controller and execution owner APIs

These are advanced owner-module interfaces. Root task_env exports and canonical contracts remain unchanged; existing names are preferred to new production controller families.

| Responsibility | Reused/extracted API | State owner | Boundary |
|---|---|---|---|
| Generate motion | CartesianPosePlanner.plan_to_pose / MotionReferences.move | planner configuration | cubic/SLERP references only |
| Generate hold | hold_pose / MotionReferences.hold | planner configuration | holds reference, does not prove stability |
| EE tracking | ProductionCanonicalPandaControllerR3.compute | R3 | persistent q_ref, reference twist history; canonical inputs |
| EE target hold | StableArmTargetHold.lock / locked=False to resume | execution adapter | freezes arm target and preserves R3 q_ref; never native stepping |
| Actual EE stability | PoseStabilityWindow.is_stable | explicit feedback window | canonical achieved pose + simulation time; exact sampled algorithm |
| Gripper open/close | existing RequestedAction opening scalar + R3 compute | R3 gripper memory | target and force cap from source config |
| Gripper grasp hold | repeat closed request, EqualRateGripperServo.inner_gripper_step | R3 law + cadence owner | continues closed-loop force regulation; no frozen force law |
| Gripper readiness | controller.readiness(state,feedback).gripper.close_ready | canonical readiness | controller-only; no 25N fallback |
| wait_until / hold_for | BoundaryWait | coordinator | simulation-time decision only; caller advances normal public boundary |
| Execute interval | session.step / additive step_control_interval | provider runtime | arm ZOH, explicit gripper cadence, one outer control-step increment |
| Task policy | NutAssemblyStableGraspCandidate | task-local coordinator | offset, compensation, deadlines, capture baseline and transitions |

No new torque controller, provider-private control inputs or global behavior change. The EE hold adapter currently depends on the R3-owned _joint_reference to preserve exact historical behavior; this dependency is explicit and bounded to canonical controller state, not native runtime state. A future public suspend-reference-update seam should be qualified before replacing it.

Gripper hold means continued regulation. Native target retention between cadence updates is interval realization, not a production freeze-actuator mode. Existing frozen-target diagnostic scripts stay archived only.

Execution helpers do not run physics themselves or sleep. Candidate actions, readiness holds and post-authorization hold are normal public boundary actions and appear in JSON traces/native audit. Current R5 tracking worker does not yet produce a fully resumable canonical trajectory for this coordinator; next replay plan identifies the missing metadata/serialization and substep stream. Do not claim replay qualification from these diagnostics.

The candidate is not migrated into the legacy task registry or PickCube. Run through the explicit integration diagnostic entry.
