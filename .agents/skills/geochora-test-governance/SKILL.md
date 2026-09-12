---
name: geochora-test-governance
description: "Design, classify, select, or review Geochora tests and qualification evidence for Core contracts, golden-path tasks, providers, learning, recording, rendering, and capability claims."
---

# Geochora Test Governance

Use this skill when adding or changing tests, qualification gates, smoke
commands, regression coverage, or claims that a task/provider route is
supported. Ordinary execution of an already-governed narrow test does not need
it.

## Evidence layers

Keep the following evidence levels distinct:

- **API/contract**: public lifecycle, reset/step, schemas, provider admission,
  controller conversion, artifact/experiment handling, and report/Judge rules.
- **Golden path**: real task construction, reset, step/rollout, record, replay,
  evaluate, and report; manipulation paths additionally need randomized
  feasibility evidence in Stage 1.
- **Provider/system regression**: runtime, renderer, recorder/replay, learner,
  runner, and provider capability snapshots across the declared envelope.

A constructor test, registry entry, successful import, or visual demo is not
end-to-end qualification.

## Test invariants

1. State the protected capability, production path, oracle, tolerance or
   failure condition, backend/provider, asset, representation, and lifecycle
   envelope for each meaningful test.
2. A numerical check is verification only when its oracle is stable, its input
   is bounded/deterministic, its tolerance is justified, and the target path
   actually ran.
3. Never obtain green status by weakening a valid tolerance, swallowing an
   exception, removing an assertion, or hiding unsupported behavior.
4. Preserve independent defect detectors. Merge setup only when lifecycle
   isolation and attribution remain intact; do not create a subsystem-wide
   mega-test.
5. Keep task/provider qualification claims fail-closed and do not generalize
   one provider × backend result to unrelated combinations.
6. A timeout is incomplete evidence, not a pass. Record untested or
   unmeasured envelopes explicitly.

## Current reference matrix

- **PickCube**: primary manipulation MVP, including expert route, randomized
  feasibility, recording/replay, and learning routes as they become ready.
- **NutAssemblySquare**: precision/contact regression beyond PickCube.
- **Agent-generated similar unseen task**: documentation and public-API
  sufficiency acceptance route.
- **Go2 Walk / RSL**: locomotion/RL regression route that must survive Core
  changes.

Do not copy GeoPhys's test directory taxonomy into Geochora without checking
the current Core test structure and purpose.

## Workflow

1. Record branch, HEAD, dirty paths, runtime/provider provenance, and the
   exact protected risk.
2. Locate the production path and existing stronger or neighboring detector.
3. Define oracle, failure semantics, input/asset/backend envelope, and expected
   cost before selecting or writing the test.
4. Run the smallest defect-sensitive check first, then the required contract,
   golden-path, or provider regression gate.
5. Do not expand a bounded request into unrelated physics, performance, or
   convergence campaigns.
6. Hand off retained/added coverage, exact commands/results, untested
   envelopes, and any claim that remains intentionally unsupported.
