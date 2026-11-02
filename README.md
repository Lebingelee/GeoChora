# GeoChora

GeoChora provides public task/environment APIs and supporting tools for embodied-task research. `task_env/` is the single Core owner; physics providers expose their own public/runtime-facing APIs.

## Version state

- **v1.1.0** is the published release, sourced from `7ed9e78a60d407fa1150c99209e06c70bfa0ed87`. Its bounded approvals and limitations remain frozen in the [release record](docs/releases/v1.1/README.md).
- **v2.0.0** is a frozen source tag at `3759f917b80adb0b7df361c0928d6aff2e4cf1ec`. This repository does not assert a publication date or a separate release acceptance for it; see the [tag snapshot notes](docs/releases/v2.0.0/README.md).
- **v2.1.0** is a local draft candidate, not a published release or new Qualification. Its current contracts and bounded evidence are in the [v2.1.0 TaskEnv docs](docs/module/task_env/v2.1.0/README.md) and [release candidate notes](docs/releases/v2.1.0/README.md).

## Start with the public API

The repository has no root packaging metadata. Install the documented runtime dependencies in a prepared Python environment; do not use `pip install -e .`:

```bash
python -m pip install -r task_env/requirements.txt
git submodule update --init GeoPhys asset/external/mujoco_menagerie
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

This is a basic scalar API example, not a qualification claim. Optional learning dependencies are listed separately in `task_env/requirements-rl.txt`; Isaac Sim uses a separate installed environment and is not installed by these requirements.

## Documentation

- [Documentation index](docs/README.md)
- [System architecture](docs/global/architecture.md) and [ownership boundaries](docs/global/ownership.md)
- [TaskEnv version index](docs/module/task_env/README.md)
- [Examples](examples/README.md)
- [Repository and contribution rules](AGENTS.md)

Importability, a demo, or a registered task does not establish an end-to-end task/provider capability. Use the versioned capability matrix for exact task, source, provider, backend, controller, and evidence boundaries. Generated run data belongs in ignored `workspace/` paths and is not part of the source release.
