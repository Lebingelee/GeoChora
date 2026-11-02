# Task Harness

**Status:** the repository has a task-candidate construction and feasibility workflow under `task_env/script/agent/`; this documentation entry does not announce a separate stable Python module.

Task Harness consumes an upstream task description and produces a bounded candidate through the existing catalog, spec, asset checks, construction ledger, feasibility checks, Oracle packaging, and Human Judge handoff. The Core task owner remains `task_env/`; Harness callers use its public construction and recording routes. A task-specific behavior belongs in its Task Artifact unless it is reusable Core behavior.

Start with the [TaskEnv current API](../task_env/v2.1.0/api/public-api.md), [task-authoring guide](../task_env/v2.1.0/guides/task-authoring.md), and the existing CLI README at `task_env/script/agent/README.md`. Candidate and Oracle evidence remain distinct from an accepted task, task success, Expert completion, and Qualification. Do not treat an example rollout as a passing candidate.

Future versioned Harness notes should follow `docs/module/task_env/<version>/` and link to the owning Core API. Do not add another task factory, Runtime, Recorder, Controller, or provider abstraction to this directory.
