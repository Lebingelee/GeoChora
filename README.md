# GeoChora

GeoChora provides public task/environment APIs and supporting tools for embodied-task research. `task_env/` is the single Core owner; physics providers expose their own public/runtime-facing APIs.

## Version state

- **v1.1.0** is the published release, sourced from `7ed9e78a60d407fa1150c99209e06c70bfa0ed87`. Its bounded approvals and limitations remain frozen in the [release record](docs/releases/v1.1/README.md).
- **v2.0.0** is a frozen source tag at `3759f917b80adb0b7df361c0928d6aff2e4cf1ec`. This repository does not assert a publication date or a separate release acceptance for it; see the [tag snapshot notes](docs/releases/v2.0.0/README.md).
- **v2.1.0** is the historical source baseline; its candidate records retain their original scope without determining current publication status. Its contracts and bounded evidence are in the [v2.1.0 TaskEnv docs](docs/module/task_env/v2.1.0/README.md) and [release candidate notes](docs/releases/v2.1.0/README.md).
- **v2.1.1** is [published](https://github.com/Lebingelee/GeoChora/releases/tag/v2.1.1) at `15f85f35`. All seven Goals / twenty-two substages have bounded acceptance; batch R3 remains a separate future package. See the [release record](docs/releases/v2.1.1/README.md) and [remaining work](docs/releases/v2.1.1/remaining-work.md). Start with the [learning guides](docs/module/task_env/v2.1.1/guides/README.md), then the [current state](docs/module/task_env/v2.1.1/maintenance/current-state.md) and [G06 implementation summary](docs/module/task_env/v2.1.1/maintenance/g06/implementation-summary.md) for tested routes, limitations and evidence.

## Start with the public API

The repository has no root packaging metadata; do not use `pip install -e .`. Start with the [installation and launch guide](docs/module/task_env/v2.1.1/guides/installation-and-start.md) to select an existing Python, provider and source paths. The [v2.1.1 learning guides](docs/module/task_env/v2.1.1/guides/README.md) continue with state-only tasks, rendering, device batches, authoring and controllers. The following is an API illustration for an already prepared environment; it has not been rerun as part of the ongoing maintenance:

```bash
export PYTHONPATH=GeoPhys/src:.
python - <<'PY'
from task_env import make_env

env = make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})
try:
    observation, info = env.reset(seed=73)
    action = env.action_space.sample()
    observation, reward, terminated, truncated, info = env.step(action)
finally:
    env.close()
PY
```

For TaskEnv navigation, start at the [developer documentation](task_env/doc/index.md). The [v2.1.1 guide](docs/module/task_env/v2.1.1/guides/installation-and-start.md) records the current path selection and unverified installation gaps. Core and GeoPhys declare incompatible MuJoCo dependency ranges, so installing both sets of requirements together is not an established setup recipe.

This is a basic scalar API example, not a qualification claim. Optional learning dependencies are listed separately in `task_env/requirements-rl.txt`; Isaac Sim uses a separate installed environment and is not installed by these requirements.

## Offline task validation

[`validation/`](validation/README.md) independently reads existing experiment evidence for
numeric measurements and terminal review. Install `validation/requirements.txt` for this
offline route; TaskEnv and a physics runtime are not required. Trajectory-wide validation
is a future extension. Validation results do not grant formal Qualification.

## Documentation

- [Documentation index](docs/README.md)
- [System architecture](docs/global/architecture.md) and [ownership boundaries](docs/global/ownership.md)
- [TaskEnv version index](docs/module/task_env/README.md)
- [Examples](examples/README.md)
- [Repository and contribution rules](AGENTS.md)
- [Agent setup for Codex and Claude Code](docs/global/agent-setup.md): one-command setup, `doctor.py`, MCP registration

Importability, a demo, or a registered task does not establish an end-to-end task/provider capability. Use the versioned capability matrix for exact task, source, provider, backend, controller, and evidence boundaries. Generated run data belongs in ignored `workspace/` paths and is not part of the source release.
