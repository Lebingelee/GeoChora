# Geochora Core Qualification and Governance

> Status: canonical Core validation policy, v0.1  
> Date: 2026-09-12

## 1. Purpose

Every Geochora Core update must preserve existing qualified capability while adding new capability deliberately.

Qualification is evidence-based. A registered task, importable provider, or existing class does not by itself count as an end-to-end supported capability.

## 2. Qualification layers

### Layer A — API / contract tests

Verify public behavior and invariants:

- environment/task API;
- Runtime Port/provider boundary;
- reset/step semantics;
- observation/action schemas;
- controller/action conversions;
- artifact/experiment schema handling;
- report/Judge contract;
- fail-closed capability admission.

### Layer B — Golden-path task qualification

Run real executable task workflows, not construction-only tests.

A golden path includes as applicable:

```text
construct
-> reset
-> step/rollout
-> record
-> replay
-> evaluate
-> report
```

Stage-1 manipulation golden paths additionally include randomized feasibility.

### Layer C — Provider/system regression

Verify the default end-to-end integration envelope:

- runtime smoke;
- default render smoke;
- recorder/replay smoke;
- learning smoke;
- runner closed-loop smoke;
- provider capability snapshot/report.

## 3. Reference qualification matrix

### 3.1 PickCube — primary manipulation MVP

Purpose:

- first complete manipulation Stage 1 + Stage 2 route;
- controller/action conversion;
- expert trajectory generation;
- randomized feasibility;
- recording/replay;
- oracle-state IL;
- RGB visuomotor route when render/camera path is ready.

### 3.2 NutAssemblySquare — precision/manipulation regression

Purpose:

- more demanding alignment/contact/task semantics;
- tests whether the Core generalizes beyond PickCube;
- validates artifact/evaluation contracts for a harder task.

### 3.3 Agent-generated similar unseen manipulation task

Purpose:

- acceptance test that public Core APIs and documentation are sufficient for Agent construction;
- should be generated from a text requirement and be comparable in scope to PickCube/NutAssembly without being a copied task.

### 3.4 Go2 Walk — locomotion/RL regression

Purpose:

- preserve the currently strongest qualified training/runtime path;
- ensure Core refactors do not break device/RSL capability;
- serve as a reference when later adapting locomotion to another robot.

The Go2 route is a regression/reference capability, not the architecture driver for manipulation.

## 4. Current-state caution

The 2026-09-07 capability audit establishes:

- Go2 CUDA/static/RSL is the strongest current production/qualification route;
- Pendulum/TwoWheel have host batch evidence;
- PickCube/NutAssembly task semantics exist but their full physics execution path is not yet qualified;
- recorder/replay infrastructure exists, but task-by-task collection/save/load/replay oracles remain to be completed;
- one task/backend qualification must not be generalized to unrelated task/backend combinations.

Roadmap claims must respect these evidence boundaries.

## 5. Core update gate

A Core change follows:

```text
Evidence-backed proposal
        |
        v
Candidate patch
        |
        v
API/contract tests
        |
        v
reference task/system regression
        |
        v
Judge / maintainer review
   |             |
reject         promote
   |             |
rollback       Core v(t+1)
```

Core is intentionally slower-moving than Part A and Part B.

## 6. Provider integration governance

For GeoPhys/Flora/future provider changes:

### Core team defines

- required public behavior;
- capability/admission expectations;
- conformance tests;
- error/fail-closed semantics;
- provider version/capability metadata expected in reports.

### Provider team defines

- numerical/storage/kernel implementation;
- backend-specific caches/graphs;
- renderer implementation details;
- performance engineering.

Core must not pass provider qualification by adding private-internal workarounds.

## 7. Default smoke suite

The first stable Geochora Core should always provide a default smoke command or governed test group that covers:

- import/bootstrap;
- default physics runtime construction;
- reset + one/multiple steps;
- default renderer frame/readback where applicable;
- trajectory record + replay;
- `runner(env, policy)` rollout;
- baseline learning smoke;
- report/evidence generation;
- artifact/experiment provenance.

The smoke suite is not proof of policy convergence; convergence/performance evaluation is a separate evidence level.

## 8. Judge and reporting governance

Evaluation and acceptance are distinct:

```text
Evaluator -> evaluation_report.json + report.md
Judge     -> judge_decision.yaml
```

Initially, Human Judge is authoritative for Stage 1 and Stage 2 acceptance.

Future Agent Judge may use the same contract, but must emit explicit `approve/reject`, reasons, and requested changes.

## 9. Core promotion sources

Core updates may be proposed from:

- Part A systemic/repeated issues;
- Part B validated skills or repeated bottlenecks;
- provider/API integration requirements;
- qualification failures revealing a Core defect.

Single task-local inconvenience should normally remain in Part A. Reusable behavior should first be validated as Part B skill or otherwise supported by repeated evidence before being promoted to Core.
