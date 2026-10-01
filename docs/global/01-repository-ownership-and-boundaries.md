# Geochora Repository Ownership and Boundaries

> Status: canonical ownership contract, v0.2
> Date: 2026-10-01

## 1. Repository intent

This repository is the canonical owner of Geochora: a reusable multi-simulator, multi-renderer, embodied-task API and tool hub.

Historical task environment code and documents may have originated on branches of other projects. They are migration context, not continuing architectural authority. There must not be two actively maintained canonical copies of Geochora Core or task_env.

PhysPi is a separate pi-based Agent project and an intended consumer of Geochora. Geochora may later be checked out or referenced beneath a PhysPi project path, but that location does not merge ownership: PhysPi owns Agent behavior and experience; Geochora owns executable simulation, rendering, task, experiment, and evidence contracts.

## 2. Target repository shape

~~~text
Geochora/
|-- task_env/              # Geochora Core implementation
|-- asset/                 # reusable asset import/resolution interface
|   +-- external/mujoco_menagerie/  # external asset link/submodule
|-- GeoPhys/               # development provider link/submodule
|-- docs/                  # canonical and module documentation
|-- .agents/skills/        # repository workflow and governance skills
+-- workspace/             # generated task artifacts/experiments; not committed
~~~

External providers remain external dependencies. Their source is linked, installed, or resolved; it is not vendored into Geochora merely to make a public review branch self-contained.

## 3. Canonical ownership

### 3.1 Geochora Core and task_env

Geochora owns:

- public environment and task APIs;
- task/runtime lifecycle;
- simulator and renderer provider boundaries;
- provider discovery, capability reporting, and admission;
- observation, action, controller, and planner contracts;
- recorder, replay, runner, and environment-policy execution;
- learner integration and training/evaluation orchestration;
- Task Artifact, Experiment, and Experiment Evidence contracts;
- provider-neutral render and UI presentation contracts;
- Core and provider qualification and regression.

Reference tasks in task_env are maintained as qualification routes. Task-local implementation belongs to its Task Artifact unless it proves reusable across tasks and is deliberately promoted into Core.

### 3.2 PhysPi

PhysPi owns:

- Agent and LLM orchestration;
- prompt and model strategy;
- tool selection, sequencing, recovery, and retry behavior;
- persistent experience, memory, retrieval, and knowledge distillation;
- reusable Agent skills and their validation/promotion process;
- reasoning over Geochora evidence.

Geochora exposes stable APIs, tools, capability metadata, and evidence for PhysPi. Geochora must not import PhysPi internals or require a particular PhysPi model, memory store, or skill format.

The intended dependency is:

~~~text
PhysPi -> Geochora public API -> provider public API
~~~

### 3.3 Assets and OpenUSD

Geochora owns the reusable asset resolution interface. Simple assets may be local to a Task Artifact; reusable robot and object resources should be resolved through that interface.

OpenUSD may later support scene interchange, composition, or visualization. Until a design is accepted, it is a candidate integration rather than a canonical repository format or required dependency.

### 3.4 Providers

GeoPhys is the currently qualified physics/runtime and default rendering provider. Additional providers such as MuJoCo, SAPIEN, and Flora must enter through explicit adapters and capability declarations.

Core and task code may depend on provider public APIs. They must not depend on provider-private internals, mutable singleton state, or undeclared backend-specific behavior.

Provider repositories and large external asset collections should remain links, submodules, or installation dependencies. Public Geochora branches should publish the reference and setup contract, not duplicate their source.

### 3.5 Rendering and UI

Geochora owns the provider-neutral boundary for render frames, cameras, viewports, overlays, interaction events, and presentation metadata. Render backends and UI clients implement or consume that boundary.

A specific renderer, desktop toolkit, browser stack, or future OpenUSD integration does not own the Core presentation contract.

### 3.6 agent_factory and learning libraries

Existing algorithm libraries may provide baseline imitation-learning or policy implementations. Geochora integrates them through explicit learner/policy boundaries instead of duplicating their algorithms.

## 4. Change classification

Classify every proposed change before implementation:

1. Task-local: belongs in one Task Artifact and does not change shared contracts.
2. PhysPi experience or skill: changes how an Agent chooses or combines existing Geochora capabilities.
3. Geochora Core: adds or changes reusable APIs, lifecycle, schemas, provider boundaries, UI/render contracts, or evidence semantics.
4. Provider: changes backend-specific simulation or rendering behavior behind an existing boundary.

Do not promote a task workaround into Core merely because it solved one scenario. Do not encode Agent reasoning or accumulated experience in Geochora APIs. Do not solve a missing Core capability with undocumented provider-private access.

## 5. Capability and evidence governance

Claims must be labeled accurately:

- implemented: code exists;
- tested: automated checks exercise it;
- qualified: an agreed acceptance route and evidence pass;
- planned: design direction only;
- aspirational: long-term objective without a committed interface.

Real -> sim -> policy -> real support may be qualified incrementally and by partial routes. It is not a present repository-wide capability claim.

Experiment Evidence can motivate a PhysPi skill update, a new regression, or a reviewed Core proposal. It cannot directly rewrite Core or bypass review. Recursive self-improvement is not a current Geochora responsibility.

## 6. Dependency and public-review rules

For the public review repository:

- Geochora-owned source, docs, tests, and skills may be published;
- GeoPhys, mujoco_menagerie, PhysPi, and other external projects remain references or links unless their own distribution policy explicitly says otherwise;
- generated workspaces, experiments, caches, credentials, and large local artifacts remain untracked;
- README setup instructions must state which external dependencies are required for each qualified route.

## 7. Conflict resolution

Use current implementation and reproducible evidence first, followed by docs/global, module documentation, README summaries, and historical notes. If packaging, old figures, or previous branch history implies different ownership, this contract governs until deliberately revised.
