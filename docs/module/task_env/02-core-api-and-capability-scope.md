# Geochora Core API and Capability Scope

> Status: canonical Core scope, v0.1  
> Date: 2026-09-12

## 1. Core mission

`Geochora/task_env` must provide the minimum complete embodied-experiment capability even when the following are absent:

- Agent orchestration;
- Part B Memory/Skills;
- external Asset Library.

A human developer or Codex must be able to complete both stages manually through documented Core APIs.

## 2. Minimum standalone capability

### Stage 1 — Task Construction & Physical/Feasibility Validation

Core must support:

```text
local/default asset or explicit asset path
   -> robot/scene construction
   -> task semantics
   -> observation/action contract
   -> controller/action mode
   -> reset/randomization contract
   -> Automatic Validator
   -> expert route
   -> randomized feasibility probe
   -> report
   -> Judge decision
   -> frozen Task Artifact
```

For the first manipulation reference route, expert generation may use the existing IK + trajectory optimizer + controller/action conversion pipeline.

The expert abstraction must not be frozen around manipulator-specific IK semantics; future locomotion expert routes may use different solvers/controllers/policies.

### Stage 2 — Data / Learning / Simulation Evaluation

Core must support:

```text
Frozen Task Artifact
   -> expert dataset generation
   -> recorder/replay/data checks
   -> baseline learner integration
   -> runner(env, policy)
   -> closed-loop simulation evaluation
   -> evaluation report
   -> Judge decision
   -> Experiment Evidence
```

## 3. Public API capability groups

Exact Python class/function names may evolve. The capability groups below are normative.

### 3.1 Construction APIs

- create/load robot embodiment;
- create/import task-local assets;
- compose scene/environment;
- define task semantics;
- define reset/randomization contract;
- select runtime/provider profile;
- define observations and actions.

### 3.2 Task semantics APIs

- success/failure;
- reward/metrics;
- termination/truncation;
- reset parameters;
- task-level evaluation contract;
- state/privileged-state/camera observation requirements.

### 3.3 Controller/action APIs

Manipulation already has action/control conversions such as:

- `absolute_pose` in world/base frames;
- `delta_pose` in EE/world frames;
- `absolute_joint`;
- trajectory conversion and replay validation.

Rules:

- public/default robot controllers may be registered in Core;
- unsupported robot-specific controllers may begin as task-private Part A implementation;
- validated reusable controllers may later be promoted to Core;
- locomotion is not forced through manipulation controller conversion.

### 3.4 Planning / expert-route APIs

Core provides documented entry points for expert-route execution and provenance.

Current manipulation reference:

```text
IK -> trajectory optimizer -> controller/action conversion -> executable rollout
```

Core must preserve the distinction between:

- task feasibility evidence;
- current expert solver success/failure.

A solver failure is not automatically labeled task infeasibility.

### 3.5 Validator APIs

Automatic validation includes, at minimum:

- config/schema validity;
- asset/reference validity;
- runtime/provider capability admission;
- reset/initial-state validity;
- controller/action compatibility;
- observation contract validity;
- finite/sanity checks required before expert rollout.

### 3.6 Recorder / replay APIs

Reuse and stabilize the existing recording infrastructure rather than replacing it.

Core must support:

- transition/trajectory recording;
- vector provenance where applicable;
- H5 or equivalent canonical dataset representation;
- replay;
- action/observation metadata;
- trajectory/video references for Evidence.

Each major reference task must eventually have a collection -> save -> load -> replay oracle.

### 3.7 Learning integration

Baseline imitation-learning algorithms live in the existing `agent_factory` library.

Core owns:

- learner integration/adapters;
- training configuration binding;
- dataset/policy provenance;
- evaluation invocation;
- Experiment integration.

Core does **not** need to duplicate algorithm implementation from `agent_factory`.

First manipulation learning route:

1. oracle/state route: `state + privileged_state`;
2. visuomotor route: `RGB + proprioception`.

Diffusion Policy is the primary initial IL route; Flow Matching may be supported as another reference route through `agent_factory`.

Locomotion remains an RL route and may use the existing Go2/RSL reference path.

### 3.8 Runner API

`runner(env, policy)` is the common rollout executor.

Expected usage is conceptually:

```python
runner = Runner(env=env, policy=policy, ...)
result = runner.run()
```

Runner unifies **closed-loop rollout execution**, not learning algorithms.

Runner must depend on stable environment and policy contracts rather than on GeoPhys/Taichi/robot-SDK internals.

Long-term target:

```text
SimulationEnv -> GeoPhys/MuJoCo/... provider
RealRobotEnv  -> robot SDK
                  
Both satisfy the Geochora environment contract used by Runner.
```

Real-robot deployment is not required for the first milestone.

### 3.9 Evaluation and reporting APIs

Core owns structured evaluation execution and report production.

Core produces facts; Judge produces acceptance decisions.

Required split:

```text
evaluation_report.json / report.md   # facts and metrics
judge_decision.yaml                  # approve/reject + reasons + required changes
```

## 4. Experiment Evidence construction skill documentation

In addition to the public API documentation, `task_env` must include an internal skill/how-to document that explicitly teaches an Agent or Codex:

- where Task Artifacts are created;
- where Experiments are created;
- how a frozen Task Artifact is referenced;
- how to record trajectories and videos;
- how to store external dataset/checkpoint references;
- how to create `evaluation_report.json` and `report.md`;
- how to create/consume `judge_decision.yaml`;
- how to finalize `evidence.json`;
- which artifacts are eligible for cleanup/archive;
- which facts must be retained for Part B.

This document is an operational skill for using Core; it is not Part B's skill-distillation implementation.

## 5. Provider scope

### First milestone

- physics: GeoPhys;
- renderer on Linux: GeoPhys default renderer;
- Flora: provider integration later/when platform allows;
- MuJoCo/SAPIEN: future provider adapters.

Do not create a UniversalSolver abstraction. Maintain Runtime Port/provider boundaries and capability admission.

## 6. Reference paths

### Primary feature-development route

Manipulation / IL:

```text
PickCube -> NutAssembly -> agent-generated similar unseen manipulation task
```

### Regression/reference route

Locomotion / RL:

```text
Go2 walk / RSL
```

The Core must preserve the existing qualified Go2 route while expanding manipulation capability.

## 7. Explicit non-goals for first milestone

- Part B storage/retrieval implementation;
- automatic skill distillation;
- automatic Core patch generation;
- soft-body tasks;
- phone-video-to-digital-twin;
- 3DGS real-to-sim-to-real;
- large-scale VLA/WAM training;
- mandatory real-robot deployment;
- immediate MuJoCo/SAPIEN/Flora full support.
