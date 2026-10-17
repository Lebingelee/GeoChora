# Public API and Selected Task Identities

**RELEASE_CANDIDATE — NOT_PUBLISHED**

## Current construction surface

Use the canonical scalar API:

```python
from task_env import make_env

env = make_env(
    "pick-cube-p16-reference-v1",
    config={"provider": "mujoco", "backend": "cpu"},
)
try:
    observation, info = env.reset(seed=31)
finally:
    env.close()
```

The selected task UIDs are:

| Public UID | Serialized TaskArtifact | Artifact SHA-256 | Task configuration SHA-256 | Status |
| --- | --- | --- | --- | --- |
| `pick-cube-p16-reference-v1` | `pick-cube-v1/p1_6_experimental_100hz` | `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4` | `0d6b26b08affd68c95a4f3209111f7c4ee2ce62088b664370f7c11b6045e9aa0` | `TESTED_BOUNDED`, GeoPhys/MuJoCo CPU, seed 31. |
| `nut-assembly-outcome-reference-v1` | `nut-assembly-square-v1/p1_8_e/nominal-v1` | `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe` | `749c78638a1e5c5e59374ceccd846767bacce5af969c2c50370482d2a288c531` | `TESTED_BOUNDED`, GeoPhys/MuJoCo CPU, NA-S0 seed 19. |

An environment UID is not the serialized Artifact identity. The selected task
directories each contain `__init__.py`, `task.py`, `solution.py`, and
`config.yaml`; task-specific construction is owned by those modules while
Core `TaskArtifact`, `RuntimeSession`, provider, controller, recorder, and
provenance contracts are reused.

PickCube preserves the selected P1.6 `experimental_100hz` Artifact and
lift-only success semantics. NutAssembly uses Outcome Completion V1 with
guarded `step_expert()` execution. For GeoPhys its accepted
`stable_height_mismatch` readiness warning and original strict Expert lifecycle
failure are both retained. Task success, full planned trajectory, outcome
completion, and Expert lifecycle are separate fields.

Other current built-in task UIDs include `pendulum-v1` and
`two-wheel-balance-v1`. The bounded Pendulum learning/batch/render smokes are
not general training or renderer qualification. Batch admission remains
capability-gated; the retired `static_template` layout is rejected.

## Current API and retired-route inventory

The full compatibility inventory, including removed import paths, task UIDs,
runtime configuration, CLI identities, migrations, and recovery refs, is
[`p2_0_s5_a_compatibility_inventory.json`](../../module/task_env/p2_0_s5_a_compatibility_inventory.json).
Current runnable commands are in [`examples/README.md`](../../../examples/README.md)
and the [migration guide](migration.md).

Task Artifact and task configuration hashes remain stable across the tested
clean checkout. PickCube's controller identity is computed from a kinematics
source hash that includes the generated MJCF bytes; those bytes include the
absolute checkout root. The canonical checkout recorded identity
`76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9`, while the
disposable checkout recorded
`a8ef891961d020721a35a032ea2093e8da61f36747babfe4bc4ff0e12195cbde`. The
normalized MJCF and TaskArtifact match. The generated provenance value for
each concrete checkout should be retained rather than compared as a
path-independent controller constant.
