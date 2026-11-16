# GeoChora system architecture

## Versioned baseline

v1.1.0 is the published Core consolidation baseline. v2.0.0 is a frozen source tag at commit `3759f917b80adb0b7df361c0928d6aff2e4cf1ec`; publication and acceptance are not inferred from the tag. v2.1.0 is the source baseline for the next plan; its local tag resolves to `fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`. Its [capability matrix](../module/task_env/v2.1.0/capabilities/capability-matrix.json) preserves the original candidate context, bounded evidence and limitations. Remote publication was not rechecked in this documentation change. None of these records grants a new formal Qualification.

## Dependency direction

```text
person / script / CI / external Agent
                │
                ▼
        GeoChora public API
                │
                ▼
      provider public/runtime API
          ├── physics/runtime
          └── renderer
```

`task_env/` is the one Core owner for task construction, configuration, runtime admission, reset/step lifecycle, controllers, observation contracts, recording, and evaluation. GeoPhys owns its solvers, native state, kernels, and renderer implementation. Core and task code must not read provider-private solver or renderer state to compensate for a missing public contract.

## Current runtime boundary

Selected PickCube and NutAssembly references use one `SelectedReferenceEnv` lifecycle owner and public `RuntimeSession` routes. Task-specific reset, evaluation, source composition, and solution policy remain in their task owners. The v2.1 candidate adds configuration precedence and explicit renderer selection facts; selected-task rendering remains state-only unless a separately documented route admits a renderer. A general Physics × Renderer matrix is not established.

The v2.1 integration records a bounded intersection across the merged F/R implementation and GeoPhys P=`67da1165149486d3ae3e779c13ce31af49e17d50`. The current scope and evidence boundaries are described in the [v2.1.0 TaskEnv docs](../module/task_env/v2.1.0/README.md). The full phase history remains under that version’s `history/` and `maintenance/`; historical plans alone do not establish current capability.

## v2.1.1 current boundary

G01–G05 have bounded acceptance in their exact reviewed intersections: shared controlled subjects and scene intervals, provider execution/reset, native and cross-render RGB. The maintainer has entered [post-5c code and project optimization](../module/task_env/v2.1.1/planning/post-5c-optimization-execution.md) before G06. Read the [current state](../module/task_env/v2.1.1/maintenance/current-state.md) for evidence, source restrictions and remaining formal-entry migration. G06 batch and G07 final integration remain unfinished; protocol approval and bounded route acceptance do not imply arbitrary composition. Task semantics remain task-owned and shared native resources retain a single owner.

## Evidence and task state

Task Artifact, Experiment, observed Evidence, and Judge decisions remain separate. Raw task predicates, lifecycle-valid success, Expert completion, replay validity, and formal Qualification are distinct facts. A runtime-valid route may still have task success=false. See [ownership](ownership.md) and the [roadmap](../roadmap/README.md).
