# V210 F/R integration baseline

**Goal:** `V210_INTEGRATION_GOAL_20261102_001`
**Core implementation:** `b769046e0572a0b59f5af19c31a1d8ed2ecd7275`
**Unified GeoPhys P:** `67da1165149486d3ae3e779c13ce31af49e17d50`
**Phase branch:** `codex/v2.1-integration`

The frozen F and R Core histories are normally merged at `1518559998ec79ac405abbd83e67f9488e0eebef`, followed by the bounded R04B test repair and integration fixes. Core pins the clean provider P, which normally merges R `7d3d3d082ce871de1ddc5333505eaeebecf28246` and F `a9e4c4850bd225f5929e74831ac282b18ff517ce`. The original source checkouts and provider candidates remain unchanged.

The bounded GeoPhys matrix GP01–GP08 passed. It covers current-P site/MSH/force/host I/O, USD lowering and a real public USD Core run, free-joint damping, CPU/CUDA force freshness, F06/Panda/A123 runtime routes, historical R04 render evidence reuse, and actual producer origin checks. Five module families in final R05b/A123 receipts resolve below the integration `GeoPhys/src`; current native claims are bound to P. The matrix limits are explicit: no general capability claim, task success, cross-engine trajectory equivalence or Qualification.

Cumulative native use: 1,737.476710554 worker seconds, 28,002 steps, 29 reset attempts/26 completed; no worker or shared-lock holder remains. The maintainer cancelled the previous cleanup-60% threshold on 2026-11-02; prior reports remain unchanged.

Detailed report, actual semantic map, GP matrix, cumulative ledger, evidence index and next API handoff are in [the ignored run package](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/v210_integration_001/report.md). Ready for Sol independent review. No push, tag, release or develop/main integration was performed.
