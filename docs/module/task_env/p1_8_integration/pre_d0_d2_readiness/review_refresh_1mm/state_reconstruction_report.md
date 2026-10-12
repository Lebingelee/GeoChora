# 当前审计适用说明

状态 owner 清单与 prototype 源码未改变，以下历史设计和局限复用。当前 +1mm recipe 的 synthetic 重新执行，12204 positive / 9 negative PASS，first divergence none；尚无 live real-checkpoint 验证。

# Stateful reconstruction audit

Disposition: opt-in prototype tested; production recorder integration remains NO-GO. Frozen controller and coordinator bytes unchanged.

| Owner | Fields | Initialize/update | Serialize/restore |
|---|---|---|---|
| arm_gripper | _joint_reference, _previous_reference, _previous_reference_step, _expected_step, _q_ref_reset_events, _lead_clamp_events, _joint_velocity_clip_events, _reference_reset_event_pending, last_arm_diagnostics, _desired, _commanded, _force_mode, _force_initialized | reset/compute/inner_gripper_step | replay_preparation.snapshot, arm_gripper-memory-prototype-v1 / restore |
| arm_hold | locked, fixed, last_target | lock/compute/unlock | replay_preparation.snapshot, arm_hold-memory-prototype-v1 / restore |
| stability | start, history | is_stable observed boundary | replay_preparation.snapshot, stability-memory-prototype-v1 / restore |
| cadence | _last_control_step, _last_target, _last_diagnostics, update_count, held_count | first physics substep per outer boundary; subsequent held target | replay_preparation.snapshot, cadence-memory-prototype-v1 / restore |
| coordinator | events, _pose_wait_start, _postclose_hold_ticks, _lift_released, _done, _failed, _failure_reason, _stage_index, _emitted, _last_opening, _opening_history, _goal, _index, _hold_ticks, _stable_ticks, _actions, _grasp_pose, _captured_position, _captured_rotation, _close_gate | reset/act/observe/_plan | replay_preparation.snapshot, coordinator-memory-prototype-v1 / restore |

Reference twist derives from previous requested position/rotation and dt, no additional hidden twist integrator. Gripper target/cap/gains are frozen construction recipe; readiness is a pure feedback+memory projection. Stability _pose_history aliases the restored window history; cadence _update is rebound by fresh construction and never serialized. Planner configuration is immutable recipe; actions are preserved with dtype/shape (float32 included). Optional capture/deadline fields retain exact presence/absence.

Snapshots include source/controller/solution/artifact/provider identity, control-step/time alignment, owner versions and integrity hash. No native IDs/contacts/solver state or pickle. Restore validates all fields before mutation. Reset-prefix equivalence and snapshot-next-target checked with deterministic canonical mock feedback at500/100/50, including moving translation/yaw, arm lock/unlock, force-mode acquisition, mid-readiness-window recovery, postclose hold and capture baseline. Final first divergence: none. Initial failed fixtures preserved in synthetic_attempt1/2 (numpy scalar contract type; mock contact injected after command reached zero at50Hz), corrected without production changes.

A single CanonicalStateView cannot reconstruct these owners. Prefix reconstruction needs all actions and pre/post feedback, plus coordinator observe/hold provenance in correct order. Boundary resume needs the complete checkpoint and externally aligned canonical/provider state. The tests do not restore native simulator state or exercise a live full-task checkpoint. Real recorder wiring and broader lifecycle coverage are outstanding; no D0/D2 qualification inference.

