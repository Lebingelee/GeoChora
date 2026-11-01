# DG04 window002 N1 source-consumer stop

**Review state:** `F05_DIAGNOSTIC04_PARTIAL_PENDING_SOL_REVIEW`
**Input:** `develop-full@bd069b4325a68ea89007f8d6118b49193d6fb27d`
**Implementation commit:** `6e7858cc` (`fix DG03 homogeneous mimic compliance mapping`)

## Work completed

The source compliance mapping now follows the pinned MuJoCo reference equation and states its homogeneous, single-constraint assumptions. Its independent numeric oracle checks fixed source-derived points. Core validation uses declared tolerances for public float-backed readbacks while retaining strict source arithmetic checks. The paired N1 detector now requires both public mimic property separation and physical post-step residual and relative-velocity separation, with positive and property-only negative cases.

The affected offline Core/detector suite passed **27/27** at `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic04/window_002/offline_core_s1_attempt010_response_delta_error.log` (SHA-256 `00107103c97973885daa92d1911010c8ff64dbfc87ea733d242d239ca368e3ad`). It used no Isaac App or native physics steps.

## Live N1 result

Attempt005 used one Isaac 6.2 App/model for the paired `source_dynamic` and `fixed_endpoint_ablation` modes, 40 rollout steps per mode and 18 counted bootstrap steps. The supervisor confirmed exactly **100 attempted steps** and charged **89.122619861999s**. The frequency readback delta was **1.2861003875732422 Hz**, above its 0.1 Hz gate. The physical response deltas were **2.60770320892334e-08 m** for equality residual and **4.240870475769043e-05 m/s** for relative velocity; both missed their frozen gates of `>5e-6 m` and `>1e-4 m/s`. Thresholds were unchanged.

This proves that the exercised public USD `Set/Get` update route changed its readback but did not demonstrate the required physical consumer response. It does not prove that the documented PhysX C++ capability is absent. The worker wrote its failure receipt and exited `-11` during native teardown; the supervisor confirmed all process groups gone and the shared lock released.

Raw receipts and hashes are in `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic04/window_002/source_consumer_api_boundary.md` and the adjacent `run_ledger.json`. The failure receipt SHA-256 is `407025ea233d4169cdfba75e184b3200838ebec1bc379ec0962d55e8d59bb92c`; the supervisor receipt SHA-256 is `d9026e029761452c8921ceea59131404e61c6dda52ab7905054f5e00b5e74efc`.

## Public API boundary and next decision

The installed Isaac Sim 6.2 public Python source/stub tree inspected for this run exposes no mimic-joint setter/getter binding. The examined `_physx.pyi` is SHA-256 `d5a6c56a0bf929917d1876fadb4127d4232b58d8b65e7aaefc856a4f6b0ca1f0`; this is bounded evidence about the installed Python surface. The [PhysX Articulations guide](https://nvidia-omniverse.github.io/PhysX/physx/5.8.0/docs/Articulations.html) and [PxArticulationMimicJoint API](https://nvidia-omniverse.github.io/PhysX/physx/5.6.0/_api_build/classPxArticulationMimicJoint.html) document natural-frequency and damping-ratio setters. The [Omni Physics articulation guide](https://docs.omniverse.nvidia.com/kit/docs/omni_physics/latest/dev_guide/rigid_bodies_articulations/articulations.html) covers the USD schema route; it does not establish the runtime Python bridge exercised in this run.

Keep production admission fail-closed. Sol review is needed to authorize a supported public Isaac-to-PhysX setter bridge or another explicitly supported route, followed by a live run that passes the frozen physical-response gates. No provider-private solver pointers or replacement solver were used.

## Budget and scope

Window002 N1 used **257/1,400 steps** and **453.017245377s/500s**, leaving **1,143 steps / 46.982754623s**. The full formal N2 reserve remains unused at **6,400 steps / 2,400s**. No formal N2, new F05 three-route matrix, F06 or F07 work was started. This stop is due to the failed source-consumer gate and the insufficient remaining wall for another complete App lifecycle, not an exhausted total budget.
