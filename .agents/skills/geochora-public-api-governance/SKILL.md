---
name: geochora-public-api-governance
description: "Audit or change Geochora Core public exports, registries, task contracts, controllers, observation/action schemas, or compatibility routes while preserving a small qualified API surface."
---

# Geochora Public API Governance

Use this skill when changing `task_env/__init__.py`, `__all__`, registries,
configuration objects, environment/task protocols, controllers, observations,
render contracts, recorder interfaces, runner contracts, or documented import
routes. Internal implementation changes that leave the exposed contract intact
do not need this skill.

## API layers

Keep these layers explicit:

1. **Core public API**: common construction, lifecycle, task, observation,
   action, controller, recorder, runner, and evaluation routes.
2. **Advanced/diagnostic API**: explicit planning, readback, render, or
   qualification interfaces whose cost and support boundary are documented.
3. **Internal Python implementation**: exact modules used by production code
   and tests; importability does not make them public.
4. **Provider internals**: GeoPhys solver/runtime state and renderer layouts;
   Core must not expose or depend on them to complete its public contract.

`task_env/__init__.py` is the public facade. Registries and successful imports
are evidence of reachability, not by themselves a stable API promise.

## Invariants

- Prefer one canonical owner route per task or contract; do not add aliases for
  symmetry or convenience.
- Keep package roots small. Put advanced public types in their owner modules
  and keep implementation internals on exact module paths.
- Public docs and examples must use public or explicitly diagnostic routes;
  repository tests may use internal ABI without promoting it.
- Do not remove a compatibility route until production callers, examples,
  docs, and tests have migrated and the replacement owner is explicit.
- Public support claims must name the actual provider × capability ×
  backend/runtime × representation envelope, including render/readback or
  upload behavior where relevant.
- Unsupported controller, provider, or asset combinations must fail clearly;
  do not silently downgrade to another semantic route.

## Workflow

1. Record branch, HEAD, dirty paths, package/runtime provenance, and requested
   API scope.
2. Inspect the facade, registry/config declarations, exact implementation
   owner, real production/demo callers, and relevant docs/tests.
3. Classify the route as public, advanced/diagnostic, internal, compatibility,
   or unsupported. Explain the canonical owner and every affected alias.
4. Update exports and callers together. Keep provider behavior behind Core
   interfaces and capability admission.
5. Run import/bootstrap, contract, and the smallest affected golden-path
   checks. Inspect the public-surface and documentation delta.
6. Hand off added/removed routes, canonical imports, compatibility decisions,
   qualification evidence, and unsupported intersections.
