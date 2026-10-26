---
name: geochora-task-harness
description: Construct and revise GeoChora task candidates from an upstream task using catalog, declarative specs and check reports; record an Oracle candidate and prepare Stage-1 Human Judge evidence. Use for task construction, not Core/provider implementation or trajectory qualification.
---

# GeoChora Task Harness

Deliver a checked Candidate Spec + Artifact, hash-bound construction history, Oracle H5 and a pending Stage-1 review package. The host agent makes decisions; these Python CLIs contain no LLM client or autonomous loop.

Read [the CLI workflow](references/workflow.md). Resolve the supplied Core checkout, Python environment, runtime directory and task workspace. The runtime directory is `<Core>/task_env/script/agent/`; see its README for setup and input contracts. Core must be a clean known snapshot; regenerate the catalog when moving machines. Keep generated work in ignored `workspace/` or outside the checkout. Do not edit Core, register new tasks, install engines, or approve/freeze artifacts as part of this workflow.

## Construction decisions

1. Read the upstream task and its referenced asset bundle / semantic examples. Query the requested provider and available templates. Catalog `available` means a manifest is readable, not that physics has run. Unknown capabilities/providers must fail explicitly.
2. Construct a spec from the catalog's `template_details.*.spec_template`, replacing the task, scene, goal, object and initialization fields with the actual upstream data. Select only supported templates. Preserve explicit `synthetic` provenance; supplied mock resources may be consumed as such, with their original request UID and byte hash. Do not relabel a lift surrogate as LIBERO In/On.
3. Initialize the ledger. Reserve a round with `begin` before running candidate checks. An initial candidate counts as round 1. Run the four checks; register their real output files with `finish`. Read all findings and the raw probe rows.
4. Revise only on evidence. A `task_local` finding permits a corresponding spec edit. `harness`, `asset`, `core` or `provider` needs its owner. `unknown` expert failure requires additional diagnostic probe evidence before a bounded task-local revision; it is not proof of infeasibility. An execution fault remains an open escalation even if an independently justified candidate revision passes. Never cite an execution fault as permission to shrink the reset distribution. No inference from model self-assessment can replace a tool receipt.
5. Each revision supplies the immediately previous report's SHA-256, the exact finding index, reason and diagnostic refs when needed. The ledger computes the spec diff. Maximum 5 candidate rounds; the same finding in adjacent rounds stops the task. Do not reset/recreate the ledger to bypass a stop. If a report has no actionable finding (including unknown/truncated outcomes), report the gap rather than inventing a repair citation.
6. A passing candidate needs assets, compile, semantic and complete feasibility reports, with at least 20 distinct declared seeds solved. Keep task success, expert completion, invalid execution, unknown outcomes and termination distinct. Record limitations of a changed sampling distribution.

## Oracle and Human review

After candidate checks pass, use `oracle_candidate.py` with the same final spec/catalog/provider. It composes Core's selected recorder and completion helper, performs exact logical H5 save/load comparison and separately invokes the Core inspector. A successful recording requires the full expert route and task success, not merely an H5 file or its T+1 count.

Before packaging, read the existing `<Core>/task_env/.agents/skills/task-env-experiment-evidence/SKILL.md`. That Skill owns Artifact/Judge procedure. Use `judge_package.py` to preserve final and historical evidence and create `judge_decision.yaml` with `decision: pending`. Record any unsupported video/render capability as a review gap. Do not create a Stage-2 Experiment from an unfrozen candidate.

Completion is demonstrated by the ledger, checks, Oracle receipt and verified pending package. Report exactly what ran. One successful fresh session establishes that session's behavior only; it does not prove every Agent/LLM works. D0/D1/D2 and trajectory qualification remain independent work, and approval remains Human Judge's decision.
