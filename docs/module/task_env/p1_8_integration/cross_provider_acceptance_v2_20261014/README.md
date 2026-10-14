# P1.8 Cross-Provider Acceptance Candidate V2

This versioned candidate is for the 2026-10-14 NutAssembly cross-provider
Evidence campaign. Its machine-readable contract is in
[`acceptance_contract.json`](acceptance_contract.json). The exact file SHA-256
is recorded in the campaign Evidence package and is part of every campaign
source/replay association.

The campaign records GeoPhys's native completed-substep body contact
aggregates. Pair-level finger attribution is unavailable in the pinned
GeoPhys runtime, so this evidence is not treated as equivalent to MuJoCo's
pair-level contact records. The FULL runner uses the opt-in
`stability-history-refs-v2` recorder representation; this changes only the
storage representation of `stability.history`, with the recorder report's
original-reader and reconstruction limitations retained.

V2 accepts the opt-in `alternative_force_8n` authorization route while keeping
the physical gripper target and cap at 10 N. It preserves the continuous
100 ms native-time guard dwell, 1.5 s deadline, post-authorization hold,
existing capture limits, task semantics, stage readiness, action budgets, and
timeouts. The 2 mm Nut/EE drift value is a separate research target; exceeding
it is reported exactly and does not by itself fail a physically valid FULL
Expert episode.

The candidate does not approve or replace historical V1/primary-only results.
MuJoCo NoSlip2 and GeoPhys Row-PGS remain distinct provider-native physical
profiles. A complete Evidence package may recommend a decision to a Human
Judge, but this document does not grant formal P1.8 qualification.
