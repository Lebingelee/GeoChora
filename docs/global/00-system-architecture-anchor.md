# Geochora System Architecture Anchor

> Status: canonical architecture anchor, v0.2
> Date: 2026-10-01
> Scope: defines the stable system-level concepts, ownership boundaries, and lifecycle that other Geochora documents must follow.

## 1. What Geochora is

Geochora is a long-lived, provider-neutral API and tool hub for embodied task construction, multi-simulator execution, multi-renderer presentation, evaluation, and evidence capture.

Its first priority is reliability: one coherent task and lifecycle contract should work across simulator and renderer providers without leaking provider internals into task definitions. Geochora is directly usable by humans, scripts, CI, and other agents; PhysPi is the intended higher-level Agent consumer, but it is not required to use Geochora.

A concise positioning is:

- PhysPi: a pi-based Agent and LLM orchestration project that owns reasoning, experience, memory, skills, tool selection, and retry strategy.
- Geochora: stable executable APIs and tools for constructing, running, rendering, recording, evaluating, and qualifying embodied tasks.
- Simulator / solver provider: decides how the physical world evolves.
- Renderer / presentation provider: produces visual observations and UI-facing presentation data.
- Controller / planner / expert route: generates executable behavior or references.
- Policy / learner: learns how to act from observations.
- Task Artifact: declares one reproducible task.
- Experiment Evidence: records what ran, under which configuration, and with what result.

Geochora is not the Agent, not an autonomous self-improvement system, and not a replacement for simulator, renderer, controller, planner, or learner implementations.

## 2. Canonical architecture

~~~text
User Requirement
        |
        v
PhysPi Agent / Human / Other Client
        |
        | public Geochora APIs and tools
        v
Geochora Core
   |-- Task Artifact loading and validation
   |-- task/runtime lifecycle
   |-- observation, action, and controller contracts
   |-- experiment, recording, replay, evaluation, and evidence
   |-- unified render and UI presentation contracts
   |
   +-- physics/runtime provider --> GeoPhys now; MuJoCo, SAPIEN, and others later
   +-- render provider          --> GeoPhys now; Flora and others when qualified
   +-- asset resolver           --> task-local and reusable asset libraries
   +-- planner/controller       --> provider-neutral integration
   +-- learner/policy           --> agent_factory or other qualified integrations
   +-- optional interchange     --> OpenUSD candidate; not yet a committed dependency
~~~

The figure docs/figures/整体架构.png illustrates the broader product context. Its Agent and Part B blocks belong to PhysPi or another external consumer, not to Geochora Core. Where the older figure conflicts with this document, this v0.2 anchor is authoritative.

## 3. PhysPi boundary

PhysPi may use its accumulated experience to choose Geochora tools, compose Task Artifacts, diagnose failures, retry safely, and interpret evidence. The dependency direction is one-way:

~~~text
PhysPi -> Geochora public API -> qualified providers
~~~

Geochora must not import PhysPi internals or depend on a particular memory, prompt, model, or skill implementation. This boundary allows stronger models to establish validated procedures that can later help weaker models achieve comparable acceptance quality through reviewed PhysPi experience and stable Geochora interfaces.

If Geochora is later placed beneath a PhysPi project path, that packaging choice does not transfer ownership of Geochora Core contracts to PhysPi.

## 4. Geochora Core capabilities

Core owns the reusable contracts and lifecycle required across tasks:

- Task Artifact schema, loader, and validation;
- simulator-independent task and runtime lifecycle;
- provider admission, discovery, and capability reporting;
- observation, action, controller, planner, and expert-route interfaces;
- recorder, replay, runner, and environment-policy execution;
- learner integration and training/evaluation orchestration;
- deterministic configuration, seeding, and provenance capture;
- Experiment and Experiment Evidence contracts;
- render-frame, camera, viewport, overlay, and UI-facing presentation contracts;
- qualification and regression evidence for public capability claims.

Provider-specific code stays behind adapters. A task may request a capability, but it must not reach into provider-private scene, physics, or renderer state.

## 5. Rendering, UI, and OpenUSD

Geochora owns the provider-neutral presentation contract, not one mandatory desktop or web application. Render providers produce qualified frames and metadata; UI clients consume those contracts consistently.

OpenUSD is a candidate future layer for scene interchange, composition, and visualization. It is not yet an adopted canonical representation and must not become a required first-milestone dependency without a separate design decision and qualification plan.

## 6. Assets

The Asset Library answers which robot and object resources are available. It may contain URDF, MJCF, XML, meshes, textures, metadata, and conversion recipes.

Simple task-local assets may live inside a Task Artifact. Reusable or complex assets should be resolved through an explicit asset interface. Asset formats do not define the Core scene API.

## 7. Task Artifact

A Task Artifact is a frozen, reproducible declaration of one task. It owns task-local scene composition, success and failure criteria, initialization, action/observation selections, allowed controller routes, evaluation configuration, and local assets.

Reference tasks are qualification vehicles for Core and providers. They demonstrate contracts and regression coverage; they do not define the full product boundary.

## 8. Experiment and evidence lifecycle

The canonical lifecycle is:

~~~text
requirement
  -> construct Task Artifact
  -> validate schema and requested capabilities
  -> instantiate qualified providers
  -> run controller, planner, expert, or policy route
  -> record observations, actions, events, metrics, and provenance
  -> judge acceptance criteria
  -> freeze Experiment Evidence
~~~

Evidence must distinguish implemented, tested, qualified, planned, and aspirational capability. Passing one reference task does not prove general support for a provider, robot, scene format, or real-world transfer route.

## 9. Governed evolution, not current RSI

Evidence may be reviewed and distilled into:

- improved PhysPi experience, memory, and skills;
- clearer Task Artifact templates;
- additional provider qualification cases;
- reviewed Geochora API or implementation changes.

These are governed software and knowledge updates. Autonomous recursive self-improvement is not a current Geochora objective, and Experiment Evidence alone never authorizes a Core source change.

The figure docs/figures/改进方案.png should therefore be read as a long-term, review-gated feedback loop rather than an implemented RSI mechanism.

## 10. Roadmap priorities

Current priority:

1. establish reliable public contracts for multi-simulator execution and multi-renderer presentation;
2. qualify the GeoPhys path and reference tasks end to end;
3. make evidence and capability claims reproducible;
4. keep provider boundaries strict enough to admit additional backends.

Next priorities include additional simulator/render providers, better UI clients, richer assets, learning integrations, and a decision on OpenUSD.

Long-term goals include faster task construction and full or partial real -> sim -> policy -> real acceptance workflows. Those goals are directional until their interfaces and evidence routes are implemented and qualified.

## 11. Authority and conflict resolution

For architecture claims, use this order:

1. current implementation and reproducible evidence;
2. this canonical anchor and the repository ownership contract;
3. module documentation;
4. README summaries and figures;
5. historical migration notes.

When they conflict, update the lower-authority material or explicitly label it historical.
