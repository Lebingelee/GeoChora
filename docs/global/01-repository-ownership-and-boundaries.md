# Geochora Repository Ownership and Boundaries

> Status: canonical ownership contract, v0.1  
> Date: 2026-09-12

## 1. Repository intent

A new `Geochora` repository is the canonical project repository.

The previous `task_env` implementation was developed on the GeoPhys `env_task_design` branch. GeoPhys **main** does not contain `task_env`. After migration, `Geochora/task_env` becomes the sole canonical owner of Core task/environment code.

There must not be two actively maintained canonical copies of `task_env`.

## 2. Target repository shape

The exact names of Agent/Memory/Skill team-owned directories may evolve, but the ownership model is fixed.

```text
Geochora/
├── task_env/              # Geochora Core; owned primarily by Core/API maintainer
├── asset/                 # asset import/resolution interface; separate owner(s)
├── ...                    # Agent / Memory / Skill team-owned directories
├── GeoPhys/               # GeoPhys git submodule provider for development
├── docs/
└── workspace/             # task artifacts / experiments; NOT committed to Git
```

`agent_factory` is an existing algorithm library used for baseline imitation-learning algorithms. Geochora Core integrates with it; Core does not need to duplicate its algorithm implementations.

## 3. Canonical ownership

### 3.1 `Geochora/task_env`

Primary owner: Core/API maintainer.

Responsibilities:

- public environment/task APIs;
- task/runtime lifecycle;
- runtime/provider boundary;
- controller/action conversion infrastructure;
- planning/expert-route integration points;
- validator infrastructure;
- recorder/replay;
- runner/environment-policy execution;
- learner integration and training/evaluation orchestration;
- Experiment / Evidence infrastructure;
- Task Artifact contract and loader;
- Core qualification and regression.

### 3.2 Agent / Part B / Skill implementation

Primary owner: Agent/Memory/Skill team.

Responsibilities:

- Agent reasoning/orchestration logic;
- Part B storage;
- retrieval / RAG;
- experience-to-knowledge distillation;
- skill generation/validation/promotion logic;
- workflow/improvement-skill logic when later enabled.

Core owner responsibilities here are limited to:

- defining directory/API boundaries;
- exposing stable Core tools/capabilities;
- emitting structured Experiment Evidence;
- reviewing proposed Core changes.

Core must not import or depend on internal Part B storage/retrieval implementation.

### 3.3 Asset interface

`Geochora/asset` owns reusable asset import/resolution APIs.

Simple task-local assets may live inside a Task Artifact. Reusable/complex robot or object assets should be resolved through the asset interface.

### 3.4 GeoPhys

GeoPhys is a solver/physics dependency and remains independently owned by the GeoPhys development team.

Boundary:

```text
Geochora/task_env -> GeoPhys public/runtime-facing API
GeoPhys           -X-> Geochora/task_env
```

Core defines required behavior and conformance tests. GeoPhys owns numerical implementation, storage/kernel ABI, contact implementation, and other solver internals.

### 3.5 Renderer providers

Near-term Linux development uses the GeoPhys default renderer.

Flora is an external renderer provider, currently mainly used on Windows. Flora integration is a provider-boundary task, not a Core-internal rendering reimplementation.

Future MuJoCo/SAPIEN physics-provider integration is in the Core owner's scope, but not part of the first implementation milestone.

## 4. GeoPhys dependency resolution

Development layout:

```text
Geochora/GeoPhys  # git submodule tracking GeoPhys main
```

Long-term preferred dependency:

1. use a released/installable `geophys` Python package when a compatible stable package exists;
2. otherwise use the repository submodule for development.

The exact packaging/bootstrap mechanism may evolve, but these rules are invariant:

- dependency version/capability must be explicit and inspectable;
- no silent fallback to an incompatible GeoPhys version;
- Core provider admission/qualification decides whether a requested route is supported;
- GeoPhys does not import Geochora.

## 5. Core vs provider responsibilities

### Geochora Core owns

- task semantics;
- reset/step transaction and lifecycle;
- public state/action contracts;
- controller/planner orchestration;
- named capability requirements;
- experiment/evidence/reporting;
- provider admission and conformance tests.

### Physics provider owns

- physics state storage;
- solver numerical algorithm;
- contact workspace;
- solver-specific caching/graph lifecycle;
- provider-specific realization of randomization;
- physics-facing render source contract where applicable.

### Render provider owns

- rendering implementation;
- device/backend-specific render resources;
- source consumption according to Core render contract.

Core must not repair missing provider behavior by reading private solver/renderer internals.

## 6. Change governance

Changes fall into three categories:

### Task-local change

Belongs in Part A Task Artifact. No Core patch is required.

### Reusable knowledge/skill change

Belongs in Part B and is owned by the Agent/Memory/Skill team.

### Core capability change

Requires:

1. evidence-backed proposal;
2. Core code review;
3. Core qualification/regression;
4. approve/reject decision;
5. versioned Core update.

Part B may propose Core changes but cannot directly mutate canonical Core without review.
