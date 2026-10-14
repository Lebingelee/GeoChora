# Canonical Solution Guarded Transitions

> Status: additive internal transition mechanism, development use. It does not
> change task-success semantics, controller behavior, public TaskEnv contracts,
> provider capabilities, or historical qualification results. NutAssembly's
> alternative 8 N authorization is an opt-in candidate and is not a universal
> grasp requirement or a production default.

## Purpose and ownership

A Canonical Solution owns expert stages and their transitions. The controller
owns tracking and actuator regulation, while Task Semantics owns physical task
outcomes. A controller readiness signal is evidence available to a Solution;
it is not itself a task-success event or an expert-completion decision.

The guarded-transition evaluator provides deterministic, provider-neutral
evaluation for declared transition guards. It consumes timestamped canonical
evidence and returns `WAIT`, `AUTHORIZED`, `RECOVERY_REQUIRED`, or `FAILED`.
The evaluator does not know about NutAssembly, Panda, force thresholds, assets,
MuJoCo, contact arrays, or solver storage. Task-specific code maps canonical
state, task metrics, and controller feedback into named boolean conditions.

The conceptual stage graph is

\[
\mathcal G=(\mathcal V,\mathcal E), \qquad
e_{ij}=(S_i,S_j,G_{ij},T_{ij},O_{ij}),
\]

where each edge names a source stage, target stage, guard, physical-time
constraints, and recorded outcome. The first implementation is deterministic;
it does not use learned transition probabilities.

## Physical-time guard semantics

Each observation represents a measured interval

\[
I_k=[t_k,t_k+\Delta t_k),
\]

with named conditions and measured values. A guard is true for an interval only
when every declared condition is present and exactly `true`. The evaluator adds
the measured interval duration to that guard's continuous dwell only when
intervals are consecutive at the declared sample period:

\[
D_g(k)=
\begin{cases}
D_g(k-1)+\Delta t_k,&G_g(k)=1\text{ and }t_k-t_{k-1}=\Delta t_k,\\
0,&G_g(k)=0\text{ or a sample is missing.}
\end{cases}
\]

Missing observations are not interpolated. A false condition or clock gap
resets continuity; the evaluator does not average force, ignore brief drops,
or use a majority vote. A guard can authorize only when its complete dwell
ends by its deadline. Samples outside that deadline do not extend the window.

For the current native 500 Hz evidence clock, \(\Delta t=0.002\,\mathrm s\).
Fifty consecutive measured intervals therefore represent 100 ms. The Solution
consumes the decision at an outer control boundary; outer-frequency action
updates do not change the native evidence timestamps or create synthetic
samples. This sampling route requires the execution adapter to expose each
canonical state/feedback substep. If that capability is absent, the route must
declare its lower-rate observation semantics and cannot claim native-rate
equivalence.

## Primary and alternative authorization

The current NutAssembly development candidate declares two guards for
`close_gripper` → `verify_lift`:

| Guard | Conditions | Meaning |
|---|---|---|
| `primary_controller_close_ready` | Controller Close Readiness, Nut grasped, EE pose ready | Historical primary authorization route |
| `alternative_force_8n` | Measured closing force at least 8 N, force mode active and initialized, Nut grasped, EE pose ready | Opt-in task-facing alternative route |

Both require the same 100 ms continuous evidence window and the same 1.5 s
deadline. The alternative route is separately identified and is never recorded
as primary Controller Readiness. If multiple guards become eligible on one
sample, the lowest declared priority number wins; a same-sample tie therefore
selects the primary guard. The candidate explicitly allows an alternative
guard to authorize as soon as its own complete dwell is met, even if the
primary guard has not completed. A policy that disables early alternatives
instead waits for the primary route and fails closed at the deadline.

The alternative threshold changes Solution authorization only. NutAssembly's
R3 force-regulation target and cap remain 10 N, and controller feedback,
force-mode behavior, task predicates, capture bounds, and task assets remain
owned by their existing components. An 8 N authorization result does not
establish an 8 N universal safe grasp or retroactively pass the historical
primary-only contract.

After authorization, the Solution executes the existing physical 100 ms
post-close regulated hold. It does not synthesize that hold or advance on a
timeout warning. If neither declared guard meets its dwell before the deadline,
the Solution fails closed.

## Lifecycle and evidence

Task success, expert completion, and environment termination remain distinct.
Guard authorization only selects the next expert stage. Lifecycle V2 still
requires the declared terminal stage and final task success before Expert
Completion; see the [Canonical Solution Lifecycle Contract](canonical-solution-lifecycle-contract.md).

The candidate identity includes its solution version, guard policy and
evaluator identity, timebase, source hashes, and selected trajectory base.
Owner snapshots serialize guard continuity history, selected authorization,
and lifecycle state under a versioned checkpoint schema. Incomplete or
identity-mismatched guard state must fail restore rather than invent history.

Replay claims have separate meanings:

- D0 reconstructs Canonical Solution/controller behavior from recorded state,
  feedback, and measured native samples.
- D1 executes the recorded native control stream without recomputing the
  adaptive controller.
- D2 starts from the frozen ResetSample and recomputes control from live
  canonical state and feedback.

Exact H5 load/save integrity alone does not establish any of these replay
properties. Candidate-scoped MuJoCo development replay also does not qualify a
cross-provider route or replace Human Review.

## Development boundary

The guard evaluator is reusable internal infrastructure. The 8 N alternative,
the 500 Hz canonical sample projection, the current NutAssembly candidate,
and any resulting multi-frequency FULL or D0/D1/D2 evidence remain
version-specific development claims. Check the matching Evidence manifest and
report before describing a candidate as physically validated. The current
candidate-scoped MuJoCo FULL and D0/D1/D2 development results are summarized in
the [dated P1.8 guarded-transition and replay report](p1_8_integration/guarded_transitions_full_replay_20261014/Report.md);
they do not change the historical primary-only 9 N qualification result. No
probabilistic transition learning is implemented; future action-selection
models must not change the meaning of deterministic authorization guards.
