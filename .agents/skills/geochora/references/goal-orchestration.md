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

An **attempt is one planned autonomous execution window**, not one test run,
code edit, native process or repair cycle. Luna may diagnose, change code,
rerun targeted checks and repeat native verification within the window without
asking Sol for a new prompt. A successful window ends when its gates pass.
An unresolved window ends when its planned timebox is exhausted or Luna needs
external guidance, information or authorization from Sol to make progress.
A routine failure with an actionable in-scope fix is work inside the current
attempt, not a reason to hand it back immediately.

Freeze the timebox and resource envelope before dispatch. Track attempt ID,
individual run IDs, cumulative active time, external waiting time and actual
resource use separately. Bound wall time, memory, disk and exclusive resources
per run and where needed across the window. Do not invent a one-launch/no-retry
cap as the default. A separate launch/retry cap needs an explicit maintainer
constraint or a concrete documented resource/safety reason. Failures requiring
resource recovery pause execution safely; they do not silently grant extra
resources or force an additional attempt number. Keep failed runs immutable,
freeze changed code/inputs for each rerun, and accept only evidence belonging
to the intended successful run; never combine partial runs into a fake pass.

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

Ordinary substage work has at most **three attempts**. Count completed execution
windows in the index, with their success, timebox or external-guidance handoff
reason; record repeat tests/native runs under that window. Do not reset the
count through renamed packages, new threads/branches or preparation rounds.
Recovery or maintainer-directed contract correction may continue the same
attempt: preserve its code, evidence, consumed time and run ledger, and freeze
any explicitly changed limits before resuming. A pause or prompt revision does
not itself spend an attempt. Preserve pre-existing historical attempts without
relabeling them. If the limit is already reached, do not issue another attempt
under this procedure; report the unresolved result and obtain a maintainer decision on
the plan. An exhausted limit does not make the substage accepted.

<a id="post-limit-diagnostic-conversation"></a>

### Post-limit diagnostic conversation

After three unsuccessful ordinary attempts, report the unresolved result.
Opening diagnostic conversations is discouraged because it consumes maintainer
attention and usage; resolve routine defects inside existing execution windows.
The maintainer may explicitly open a temporary conversation dedicated to
locating and resolving a persistent blocker. Do not create or message another
conversation automatically.
Hand over the original objective and acceptance gates, current branch/HEAD and
writer ownership, three frozen packages and results, established facts versus
hypotheses, and exact unresolved owner/method boundaries.

Use that conversation to check upstream construction and reset semantics,
existing production callers, and whether a claimed missing input is absent
from the available delivery or absent upstream altogether. Separate an
implementation gap from an external-data gap and from an unnecessarily strict
or changed acceptance gate. Verify these distinctions before asking for more
assets, changing task semantics, or extending execution.

Once explicitly designated by the maintainer, diagnostic work has **no fixed
attempt-count limit**. Preserve the original three-attempt result and record
diagnostic attempts and individual runs separately. This exception must not be
self-declared by renaming ordinary work. Each diagnostic attempt should resolve
an identified cause or deliver an implementation/validation increment; do not
repeat the same audit or ask the user to reopen conversations for routine fixes.
Maintain bounded time and resource budgets and one complete prompt per window.
Reassess the approach when repeated work makes no progress.

Opening the conversation alone authorizes no implementation, native execution,
branch changes or concurrent writes. Its default is read-only diagnosis; edits
and execution need maintainer scope and coordination with the current writer.
Return the root cause, reusable owners, smallest repair and validation plan,
and any concrete maintainer decision to the phase record. Resume implementation
under the agreed scope, acceptance contract and execution budget. An explicit
diagnostic mandate does not erase failed evidence or automatically grant
substage acceptance.

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
At the planned timebox, unresolved work should produce a preserved handoff;
Sol still waits for its final report and released window before the next
prompt. Elapsed time or a failed individual run alone is not a completed handoff.

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
