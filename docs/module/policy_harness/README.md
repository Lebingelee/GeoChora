# Policy Harness

**Status:** training, evaluation, and report routes are owned by existing TaskEnv learning/evaluation modules and benchmark-specific consumers. This page is an ownership entry, not evidence that a general Policy Harness module exists.

A policy experiment binds a task and source contract, provider/backend, action/observation representation, training configuration, checkpoint, and evaluation protocol. Keep Experiment configuration, observed Evidence, evaluation reports, Judge decisions, and Qualification separate. A learner smoke or a successful import is not convergence or task qualification.

Start from the current [recording and learning contract](../task_env/v2.1.0/contracts/recording-and-learning.md), [qualification contract](../task_env/v2.1.0/contracts/qualification.md), and current [capability matrix](../task_env/v2.1.0/capabilities/capability-matrix.json). Optional SB3/RSL dependencies are listed separately in `task_env/requirements-rl.txt`.

Future notes should live under `docs/module/task_env/<version>/` or the owning benchmark. Do not add a second environment factory, recorder, task evaluator, or hidden training service.
