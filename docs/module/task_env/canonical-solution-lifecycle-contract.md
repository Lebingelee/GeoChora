# Canonical Solution Lifecycle Contract

> Status: additive internal Core contract, v1.0. It standardizes versioned
> Canonical Solutions that adopt `CanonicalSolutionLifecycle`; it does not
> retroactively change frozen solution identities or qualify a provider route.

## Purpose and scope

A task can become successful before an expert has finished its declared action
sequence. A Canonical Solution therefore records task outcome and expert
completion independently. The environment/runtime separately owns whether the
episode terminated or was truncated. These are related events, not synonyms.

This contract defines a small state owner for lifecycle transitions. It does
not define task success predicates, task stages, controller behavior, planner
trajectories, provider state, or physics stepping. Task-specific readiness and
terminal-stage logic remain in the task's versioned Canonical Solution.

The current implementation is internal at
`task_env.tasks.canonical_solution_lifecycle`. It is not re-exported from the
`task_env` package facade. Provider-free transition tests verify the state
contract; they do not qualify any environment/provider intersection.

## Ownership

| Concern | Owner | Contract |
|---|---|---|
| Physical or semantic task outcome | Task Semantics | Computes `is_success` and task failure from task state. It does not inspect the expert's stage index. |
| Expert progression and completion | Canonical Solution | Owns stage plans, readiness, timeouts, action budgets, immutable completion policy, and expert terminal state. |
| Episode termination and truncation | Environment / Runtime | Reports whether execution can continue. A runtime that is terminal must not be stepped again. |
| What happened | Recorder | Preserves task-success boundaries, expert lifecycle events/state, termination flags, applied controls, and real T/T+1 boundaries. |
| Acceptance | Qualification / Judge | Checks the declared expert and task conditions; `solution.done` alone is not a qualification verdict. |

## Lifecycle state and policy

`CanonicalSolutionLifecycle` has an immutable `SolutionCompletionPolicy`:

- `ON_TASK_SUCCESS`: a valid task-success event completes an expert whose
  declared execution has no required post-success work.
- `ON_EXPERT_TERMINAL_STAGE`: task success is recorded but does not stop the
  solution. The task-specific solution must complete its terminal-stage
  readiness condition and submit the final task outcome before the lifecycle
  completes.

The selected policy is part of the solution identity and the recorded recipe.
It cannot be changed during an active rollout. A behavior change requires a
new solution version and identity.

The lifecycle owner records:

- `task_success_seen`, first success control step and simulation time, and the
  current task-success value;
- environment `terminated` and `truncated` values;
- `expert_complete` or `expert_failed`, never both;
- completion reason and boundary, or failure reason and outcome code;
- ordered lifecycle events, including first task success, later loss of
  success, expert completion, and expert failure.

`done` and `failed` are compatibility properties derived from lifecycle state.
After either terminal state, the solution cannot produce another action or
accept another lifecycle observation. Reset clears all rollout state and
event history while retaining the declared policy.

`ON_EXPERT_TERMINAL_STAGE` completion requires all of the following: the
terminal-stage predicate is true, task success was observed, and task success
is still true at that completion boundary. A past success event is not a
substitute for a currently valid final outcome.

If the environment terminates before required expert work is complete, the
solution stops. When task success had already occurred, the outcome is
`TASK_SUCCESS_EXPERT_INCOMPLETE`; it is not a successful expert completion.
Truncation also stops execution and cannot be accepted as completion. A later
task failure, readiness timeout, action-budget overrun, or loss of final task
success cannot be hidden by an earlier success event.

## Solution integration requirements

Each new or behaviorally revised Canonical Solution must declare:

1. its solution version and immutable completion policy;
2. the task-semantic success predicate it consumes;
3. whether success can occur before the final expert action;
4. the terminal stage and its unchanged readiness, timeout, and action-budget
   conditions;
5. whether task success must remain valid at expert completion;
6. how termination, truncation, task failure, and an unavailable next action
   stop the expert;
7. which lifecycle fields affect action generation and how they are restored.

Task-specific code calls `observe_task_outcome` for every observed boundary,
then either continues its own stage logic, calls `complete_expert` when its
terminal-stage predicate is satisfied, or calls `fail` with a concrete reason.
It does not directly mutate an independent `_done` boolean. The lifecycle
component accepts only task/runtime outcomes and clock values; it never reads
provider or solver storage.

## NutAssembly example

NutAssembly task success remains the existing semantic condition: the Nut is
inserted on the peg and released. `release_retreat` is not part of
`task_success`.

The frozen `NutAssemblyCanonicalSolutionV1` retains its historical immediate
on-success behavior. The new opt-in `NutAssemblyStableGraspCandidateV2` uses
`ON_EXPERT_TERMINAL_STAGE` and the following task-specific completion rule:

\[
\mathrm{ExpertComplete} =
\mathrm{TaskSuccessObserved}
\land \mathrm{OpenGripperReady}
\land \mathrm{ReleaseRetreatReady}
\land \mathrm{FinalTaskSuccess}.
\]

The success event is recorded when it first appears. The existing open-gripper
plan, readiness window, retreat plan, endpoint tolerance, timeouts, task
success semantics, capture limits, and action budget continue to apply. Only
after the retreat endpoint is observed with final task success still valid
does the V2 lifecycle report `expert_sequence_completed`.

The diagnostic worker must require actual `release_retreat` actions, a
recorded retreat endpoint with readiness satisfied, the lifecycle completion
event, and final task success. Merely entering the stage or observing
`solution.done` is insufficient.

## Existing solutions and migration

The current PickCube solution has an expert collection margin in addition to
the task's success threshold. Its completion rule is not equivalent to an
unconditional task-success stop, so it must declare that expert-specific
condition when migrated. The readiness variant also has a distinct terminal
contract. Existing PickCube and legacy NutAssembly implementations are not
silently migrated by this additive contract.

For every future task or revised Canonical Solution, use a new version when
completion behavior or serialized owner state changes. Do not rewrite old
recordings as if they used the new policy.

## Recording and replay

Task success remains represented by task evaluation at each recorded boundary.
Expert lifecycle events are recorded separately in transition diagnostics,
and the lifecycle state is included in the versioned solution-owner snapshot.
Episode `terminated` and `truncated` flags remain separate transition fields.
The final stop reason distinguishes `canonical_task_success_observed`,
`expert_sequence_completed`, `expert_sequence_failed`, environment
termination, and truncation.

Any lifecycle state that can affect action generation must be serialized or
deterministically reconstructed. For v1 this includes the policy, first
success step/time, current success state, terminal state, completion/failure
reason and boundary, environment outcome flags, and ordered event history.
Restore validates the solution identity, policy, state version, event clocks,
and terminal-state consistency before mutating the fresh owner. A historical
snapshot without these fields is not restorable as a V2 lifecycle snapshot.

When a stage has multiple evidence-based authorization routes, keep their
evaluation in a separately versioned, provider-neutral guard policy. The
[Canonical Solution Guarded Transitions](canonical-solution-guarded-transitions.md)
contract defines continuous physical-time dwell, deterministic guard selection,
recording, and replay boundaries. Guard authorization does not alter this
lifecycle's distinction among task success, expert completion, and environment
termination.

## Review boundary

This contract is a development implementation boundary. A provider-free unit
test, a single NutAssembly FULL run, or a successful H5 roundtrip does not
approve a frozen golden, establish cross-provider behavior, or authorize a
formal D0/D1/D2 campaign. Those claims require their separately governed
Evidence and Human Review.
