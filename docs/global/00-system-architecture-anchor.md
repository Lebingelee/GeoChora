# Geochora System Architecture Anchor

> Status: canonical architecture anchor, v0.1  
> Date: 2026-09-12  
> Scope: defines the stable system-level concepts and lifecycle that other Geochora documents must follow.

## 1. What Geochora is

Geochora is an **agentic embodied experimentation infrastructure**. It does not replace the simulator, controller, planner, learner, or agent. It organizes them into a reproducible workflow that turns a user requirement into a validated task, executable expert data, learned policy, evaluation evidence, and eventually reusable system improvements.

A concise positioning is:

- **Simulator / solver**: decides how the physical world evolves.
- **Renderer**: produces visual observations.
- **Controller / planner / expert route**: generates executable behavior or references.
- **Policy / learner**: learns how to act from observations.
- **Agent**: reasons about the requirement and calls tools.
- **Geochora**: governs the whole task-construction, experiment, evaluation, evidence, and improvement lifecycle.

## 2. Canonical architecture

The current architecture is anchored by `整体架构.png`.

```text
User Requirement (Human / LLM)
        |
        v
Agent Orchestrator
        |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
Part B Memory Layer     Asset Library       Geochora Core
adaptive memory         passive resources   executable shared capability
        |                   |                   |
        +--------- retrieval / composition ----+
                            |
                            v
                    Part A: Task Artifact
                            |
                    validate + judge + freeze
                            |
                            v
                    Experiment Engine
                            |
                            v
                    Experiment Evidence
```

`Geochora Core` consumes solver and renderer providers through explicit provider boundaries:

```text
Geochora Core
   |-- physics/runtime provider --> GeoPhys (canonical now), future MuJoCo/SAPIEN/... adapters
   `-- render provider          --> GeoPhys default renderer now, Flora optional/future primary visual provider
```

### 2.1 Part B — Memory Layer

Part B answers: **“What did we learn from previous tasks that can make the next task easier or more reliable?”**

It is external persistent adaptive state, not Core source code. It may contain:

- Experience evidence references;
- distilled knowledge;
- validated skills;
- workflow / improvement skills (enabled later, after manual validation of Part A / Part B behavior).

Part B is maintained by other project owners. Geochora Core exposes interfaces and evidence contracts for Part B, but must not depend on Part B implementation internals.

### 2.2 Asset Library

The Asset Library answers: **“Which robot and object resources are available?”**

It contains passive resources and metadata such as:

- URDF / MJCF / XML;
- meshes and textures;
- robot assets;
- object / articulated-object assets;
- asset metadata and references.

Controllers, planners, training algorithms, and runtime logic are not Asset Library contents; they are executable capabilities and belong to Core or external algorithm packages.

For simple task-local geometry, an asset may be created inside a Task Artifact. More complex or reusable assets should be resolved through `Geochora/asset`.

### 2.3 Geochora Core

`Geochora/task_env` is the canonical Core implementation. It evolves from the previous `task_env` implementation developed on the GeoPhys `env_task_design` branch.

Core is the stable software capability layer and includes or integrates:

- registry / config / composition;
- environment and task lifecycle;
- runtime ports and provider adapters;
- observation / action contracts;
- controllers and action conversions;
- planning / expert-route capabilities;
- validators;
- recorder / replay;
- learner integration;
- `runner(env, policy)` style rollout execution;
- evaluation and reporting;
- experiment and evidence infrastructure.

Core must be usable **without Agent, Part B, or Asset Library**. A human or Codex must be able to construct and validate a task, collect simulated data, train/evaluate a policy, and generate a final report using only Core APIs plus local/default assets.

### 2.4 Part A — Task Artifact

Part A answers: **“What exactly is this task?”**

It is a task-specific, versioned, non-Git artifact. It contains the concrete task definition needed by Stage 1 and referenced by Stage 2. The artifact includes, at minimum:

- embodiment / robot setup;
- task-local assets or asset references;
- scene/world construction;
- task semantics;
- observation/action requirements;
- controller/action-mode configuration where needed;
- reset and domain-randomization contract;
- evaluation contract;
- validated expert-route configuration/provenance after Stage 1 validation.

Task Artifact is a fast-changing task-level object. Drafts may be cleaned periodically; validated/frozen versions and key evidence are archived.

### 2.5 Experiment Engine

Experiment answers: **“How did this specific task/data/policy configuration actually perform?”**

An Experiment references a frozen Task Artifact version and binds:

- Core version;
- Task Artifact version;
- expert/data-generation configuration;
- learner/policy configuration;
- seeds and budgets;
- provider/runtime capability snapshot;
- outputs and evaluation contract.

One Task Artifact may be referenced by many Experiments.

## 3. Canonical one-task workflow

The current workflow is anchored by `一次工作流.png`.

### Stage 1 — Task Construction & Validation

```text
User Requirement
   |
   v
Agent or Human/Codex
   |
   v
Task Artifact Candidate
   |-- 1. embodiment/control-subject construction
   |-- 2. environment/world construction
   `-- 3. task construction
   |
   v
Automatic Validator
   |  config / asset / runtime / reset / controller / schema
   |  fail -> revise Part A
   v
Expert Route & Feasibility
   |  current manipulation reference:
   |  IK / trajectory optimizer -> controller conversion -> randomized expert rollout
   |  output: success / failure / unknown report
   v
Human/Agent Judge #1
   |  reject -> revise Part A or expert route
   v
Freeze Task Artifact vN
```

Important semantics:

- Automatic Validator checks **definition/runtime validity**.
- Expert Route checks **current executable feasibility**.
- Judge checks **acceptability and alignment with the user requirement**.
- Planner failure is not automatically equivalent to intrinsic task infeasibility.

### Stage 2 — Data Collection / Learning / Evaluation

```text
Frozen Task Artifact vN + validated expert route
   |
   v
Expert Dataset Generation
   |  randomized training reset
   |  validated expert rollout
   |  recorder / replay
   |  lightweight data checks
   v
Oracle-State Policy Verification
   |  state + privileged_state
   |  Diffusion Policy / Flow Matching reference route
   |  closed-loop simulation
   v
Visuomotor Policy Verification
   |  RGB + proprioception
   |  policy learner
   |  closed-loop simulation
   v
Closed-loop Evaluation
   |  frozen evaluation contract
   |  ID / OOD
   |  success / failure
   |  oracle-state <-> RGB gap
   |  robustness / failure cases
   v
Human/Agent Judge #2
   v
Experiment Evidence
```

Stage 2 may tune training parameters and permitted randomization parameters, but it may not silently change the Stage 1 task/evaluation contract.

## 4. Domain-randomization ownership rule

This is a hard architectural rule.

### Stage 1 / Task Artifact owns

- which quantities may be randomized;
- randomization schema;
- hard bounds / allowed envelope;
- nominal/default training range;
- evaluation distribution/range;
- randomization semantics required for feasibility validation.

A randomized reset probe is mandatory for the first release of Stage 1.

### Stage 2 / Experiment may

- tune training randomization parameters **inside the allowed envelope**;
- choose curricula or schedules that stay inside the Stage 1 contract.

Stage 2 may not, without a new Task Artifact version and Judge approval:

- add/remove a randomization dimension;
- change hard bounds;
- change the frozen evaluation distribution;
- change task success/failure semantics.

## 5. Three-timescale improvement model

The current improvement architecture is anchored by `改进方案.png`.

```text
Part A (fast): Task Artifact
  construct / correct current task
        |
        | useful task-level experience
        v
Part B (medium): Adaptive Memory
  retain, distill, validate, improve cross-task knowledge/skills
        |
        | repeated/systemic evidence + Part A systemic evidence
        v
Core (slow): governed package update
  candidate patch -> qualification -> judge -> Core v(t+1)
        |
        `---- stronger shared capability ----> future Part A
```

The key promotion hierarchy is:

```text
task-local solution
   -> repeated usefulness
validated Part B skill
   -> repeated structural need
Core capability
```

Part A is periodically cleaned/archived. Part B is long-lived but continuously distilled/refined. Core changes are low-frequency and governed.

## 6. Current project focus

The near-term product/research focus is rigid and articulated rigid-body manipulation.

Primary development line:

```text
PickCube -> NutAssembly -> agent-generated similar unseen manipulation task
```

Locomotion remains a reference/regression capability. The existing Go2 walk/RSL path should remain functional while manipulation becomes the main feature-development route.

Soft-body simulation, direct phone-video-to-digital-twin, 3DGS real-to-sim-to-real, and large VLA/WAM training are explicitly outside the first Core milestone.

## 7. Evidence basis

This document is anchored to:

- `整体架构.png`
- `一次工作流.png`
- `改进方案.png`
- `task_env_capability_audit_2026-09-07.md`
- the previously completed runtime/provider audits (`01`–`07` audit documents)

The current capability audit establishes that the TaskEnv framework already has registry/config/task semantics, runtime/provider boundaries, recording/replay infrastructure, and learner integration; Go2 CUDA/RSL is the strongest currently qualified route, while Panda PickCube/NutAssembly still require full physics execution qualification.
