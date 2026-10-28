# Coordinating a goal across substages

Use this procedure when the maintainer assigns a goal spanning multiple
substages. Sol owns planning, scheduling and acceptance review; Luna or another
authorized execution agent owns its frozen package. Apply the
[single-prompt protocol](../SKILL.md#one-complete-prompt-per-luna-execution-window)
throughout. A future intention to use goals does not start one now.

## Plan before dispatch

Locate the substage in the existing phase planning document and record its
dependencies, current behavior, exact implementation owners/files/methods,
known gaps, proposed changes, acceptance gates and required evidence. Trace
actual callers and contracts before selecting patches. Resolve mandatory
unknowns or state them explicitly; do not let a high-level execution order
substitute for an implementable package.

Maintain a compact orchestration index in the existing goal/phase records:
substage and planning anchor, attempt number, assigned agent/thread,
checkout/branch, package path/hash, input HEAD, expected duration, execution
budgets, last observed progress/time, evidence/report/commit paths, Sol review
decision, blockers and next eligible substage. Preserve earlier attempts and
reuse the planned stage branches. Parallelism requires independently writable
scopes/checkouts and existing shared resource coordination.

## Attempt targets and limit

1. **Attempt 1 — research and implement.** Luna investigates the actual call
   chain, confirms the patch locations and existing reusable owners, implements
   the bounded changes and performs the package's authorized checks. Include
   success/failure cleanup and report generation in the package, so trivial
   field, serialization or finalizer errors are caught before native execution.
   The final report identifies the decisions, implementation, evidence and any
   remaining core issue. Sol may accept a complete first attempt; a second is
   not mandatory when the original gates already pass.
2. **Attempt 2 — resolve review findings and accept.** Prefer a focused review,
   necessary repairs and acceptance over another broad investigation. Reuse
   unchanged evidence; rerun only checks affected by a change or unresolved
   concern, within the authorized execution budget. Aim to close the substage.
3. **Attempt 3 — final bounded repair and closure.** Do not dispatch until the
   reassessment below is complete. Include the chosen repair, its validation
   and final substage disposition in one package.

Each substage has at most **three attempts**. Count actual implementation and
rework attempts in the index; do not reset the count through renamed packages,
new threads/branches or newly numbered preparation rounds. Recovery from an
interruption may continue the same attempt only when its scope/progress and
remaining execution allowance are preserved; it does not replenish retries or
native starts. Preserve pre-existing historical attempts without relabeling
them. If the limit is already reached, do not issue another attempt under this
procedure; report the unresolved result and obtain a maintainer decision on
the plan. An exhausted limit does not make the substage accepted.

## Mandatory reassessment before attempt 3

When attempt 2 has not resolved the core issue, Sol first consolidates the
actual code/HEAD, earlier diffs, raw failure evidence, checks already passed,
remaining blockers and hypotheses. Distinguish an implementation defect from
missing public capability, unavailable external input or an infeasible gate.

Search relevant open-source communities and primary sources: official docs,
source repositories, examples and upstream issues. Inspect comparable
implementations or reusable libraries, checking version/API fit, maintenance,
license, dependencies and fit with Geochora ownership. Record concrete links,
what can be reused/adapted, rejected alternatives and remaining uncertainty;
also record a negative search result when no suitable implementation exists.
Reuse existing Core owners before introducing another abstraction.

Update the substage planning entry with the root cause supported by evidence,
chosen approach, patch locations, check sequence, execution budget and a
reasoned feasibility decision against the **original** acceptance criteria.
If a required external input is still missing or no credible route exists,
report the blocker and required maintainer/external decision before spending
attempt 3. Do not weaken the gate or promise success merely to fit the limit.

## Observe without changing the active package

Set a read-only observation interval in the package; 5–10 minutes is a useful
default, adjusted to task duration and expected checkpoints. Use event waits
and compact status snapshots rather than frequent full conversation reads;
follow the tool's wait limits. Inspect relevant visible conversation/tool
outputs when progress changes, a blocker appears, or expected duration passes.
Record the latest stage, completed work, blockers and last observation time.
Elapsed time alone neither permits another prompt nor implies completion.

When visible updates show code/validation are finished and Luna is assembling
reports, Sol may review stable evidence read-only and privately draft next
steps. Do not write in Luna's owned scope, change its frozen inputs or send the
draft. Freeze the next package's actual HEAD and scope only after the final
handoff and review; respect dependencies and explicit authorization.

## Verify the completed handoff

After Luna returns a complete final response and releases its window, map the
original requirements to actual changes, commands/results and raw evidence.
Check the returned HEAD/commits and hashes, that the exercised public path
matches the claimed route, and that reported outcomes agree with visible
research notes, implementation decisions, execution logs and failure history.
Use this observable record; do not request private chain-of-thought.

Perform independent, defect-sensitive verification where needed, reusing
unchanged stronger evidence. Do not reflexively repeat every test or launch
native execution without its required authorization. Record accepted scope,
remaining limitations and Sol's decision in the planning record before one
consolidated continuation or the next eligible substage. A reported PASS is
not automatic acceptance; a report on failed gates may be complete without
completing the substage or the overall goal.
