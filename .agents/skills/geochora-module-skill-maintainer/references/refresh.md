# Module refresh procedure

Review on public API/export changes, registry/task/provider additions/removals, owner/lifecycle moves,
new execution workflows, capability status updates, important bug fixes, retired/replaced interfaces,
and changed tests/failure behavior. Review can conclude that no Skill edit is needed, with evidence.

1. Record current repository/branch/commit, dirty paths, module name, request/mode and scope.
2. Inspect public facade, defining owners, registry/admission routes, production callers and selected
   examples. Use current CodeGraph when present; do not rebuild an index as unrelated work.
3. Extract the actual public surface: import/symbol/signature, required config, lifecycle/state owner,
   errors, dependencies and provider/backend/task intersections. Distinguish use API, extension hooks,
   internal helper and historical recovery; a package docstring alone is not sufficient.
4. Compare current Skill/references with actual surface and canonical docs. For each drift, record
   old route/claim, source evidence, impact, proposed repair and whether capability review is needed.
5. Update the existing Skill in place. Keep operational routing in SKILL.md and conditional detail in
   references. Point to the canonical capability schema and Experiment/Evidence owner rather than copying them.
6. Validate metadata/frontmatter and all source/doc/API references. Run
   `python .agents/skills/geochora-module-skill-maintainer/scripts/check_module_skill.py <skill-dir>`.
   Also use the available system skill-creator quick_validate.py when present; this repo does not depend
   on that personal installation path. Neither checker proves behavior.
7. Execute supported help/import/schema/examples within a declared bounded envelope. Native
   qualifications are separate gated work. A source diff, import, fake test or one smoke is not qualification.
8. Cold-start walkthrough: give a new Agent only repo, AGENTS, module Skill and a concrete task; verify
   public construction, recording/evaluation routes, unsupported intersections, and locating existing
   owners before proposing new implementation. Use read-only/provider-free scope unless native execution
   is explicitly part of the requested validation. Record failures and correct demonstrated gaps.
9. Produce a compact receipt and retain Human review for API/qualification-sensitive updates.

Receipt fields: date/module/mode; source commit/dirty scope; public owners/callers/tests inspected;
trigger and verified limitation; seven-step reuse evidence and classification (improve); drift/fix table;
commands/results and retained output refs; task/provider/backend/config/source envelope;
cold-start outcome/fixes; NOT_RUN items and limits; review status/required Human decision.

For a future module without a Skill, first establish that the module exists and identify its owner,
then create one concise module Skill via skill-creator conventions. Do not duplicate overlapping Skills
or fill missing implementation with planned APIs. Skill changes are knowledge maintenance; PhysPi
owns Agent orchestration, memory, experience and autonomous evolution.
