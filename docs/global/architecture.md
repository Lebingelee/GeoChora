# GeoChora system architecture

## Versioned baseline

v1.1.0 is the published Core baseline. v2.0.0 is a frozen source tag at commit `3759f917b80adb0b7df361c0928d6aff2e4cf1ec`; publication and acceptance are not inferred from the tag. v2.1.0 is a local draft candidate whose bounded integration evidence and limitations are recorded in its [capability matrix](../module/task_env/v2.1.0/capabilities/capability-matrix.json). None of these records grants a new formal Qualification.

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

## Evidence and task state

Task Artifact, Experiment, observed Evidence, and Judge decisions remain separate. Raw task predicates, lifecycle-valid success, Expert completion, replay validity, and formal Qualification are distinct facts. A runtime-valid route may still have task success=false. See [ownership](ownership.md) and the [roadmap](../roadmap/README.md).
