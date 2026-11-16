# Selected TaskEnv configuration

## Resolution order

For selected reference environments, one resolver combines values in this order:

1. Core defaults;
2. task-class `selected_execution_defaults`;
3. the selected task YAML's `execution` section;
4. caller-supplied configuration.

Later values override earlier values only for known fields. Unknown keys, duplicate YAML keys, conflicting legacy aliases, invalid types, and a `ResolvedSelectedConfig` for a different task are rejected. Values are resolved once and passed into construction and recording metadata; callers should not independently rebuild execution defaults.

## Sections and fields

New selected configuration uses `execution`, `episode`, `task`, and `render` sections. `execution` accepts `physics_provider`, `physics_backend`, `physics_device`, `source_delivery_manifest`, and `render_default`. Scalar construction also accepts the public `render` section, which is applied to the existing single-environment renderer. `episode` accepts `horizon`. `task` accepts only the selected task's declared parameters and controller profile.

The selected task YAML files explicitly declare the current defaults: GeoPhys / CPU / CPU device, with state-only rendering. PickCube defaults to controller profile `r3_continuous_v1`; use `r1` only when the caller explicitly requests it. NutAssembly defaults and its source/reset profile remain task-owned.

For a scalar render request, keep the renderer declaration in `config.render` and
keep the UI mode in the factory call. A single configured camera is reused by the
observer `env.render()` route, so callers do not need to repeat it as a separate
constructor keyword.

```python
env = make_env(
    "pick-cube-p16-reference-v1",
    config={
        "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
        "render": {
            "camera_obs": True,
            "backend": "mujoco_reference",
            "width": 320,
            "height": 240,
            "cameras": [{"name": "observer", "width": 320, "height": 240}],
        },
    },
    render_mode="rgb_array",
)
```

The selected task and controller still need an admitted observer route. The
configuration change only makes the scalar render fields pass through the same
public resolver and preserves them in the resolved configuration.

```yaml
execution:
  physics_provider: geophys
  physics_backend: cpu
  physics_device: cpu
  render_default:
    schema_version: renderer-selection-v1
    provider: none
    backend: cpu
    profile: none
    device: null
episode:
  horizon: 6000
task:
  controller_profile: r3_continuous_v1
```

The YAML above shows the shape, not a promise that the same task fields or horizon are valid for every selected task. See each task's versioned configuration and parameter limits.

## Provider and renderer selection

Physics and rendering are separate choices. `render_default` is a full `RendererSelectionV1` value, not a string alias. The selected reference currently admits the state-only mapping (`none` / `cpu` / `none` / `null`). A non-`none` selected renderer and an unsupported Physics × Renderer pairing raise an error; they are not silently downgraded.

Changing provider or backend while inheriting an incompatible device is rejected. Specify a compatible provider/backend/device combination explicitly. Current selected support is bounded to GeoPhys CPU, MuJoCo CPU, and the documented PickCube Isaac CUDA/PhysX source route; consult the [matrix](../capabilities/capability-matrix.json).

## Compatibility inputs and recording

The old task `recipe` / `environment` configuration shape and supported flat aliases continue through the existing compatibility normalization. New examples should use the nested selected sections. Supplying both a legacy alias and its nested field with different values is an error.

The resolved value, including renderer selection, is serialized into the environment's recorded configuration metadata. Task identity parameters remain separate from execution configuration. Pre-resolved configuration can be passed back through construction only for its owning task and only if validation produces the same resolved value.
