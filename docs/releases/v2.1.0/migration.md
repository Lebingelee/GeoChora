# v2.1.0 candidate migration

This guide applies to the local v2.1.0 candidate. Check the [public API](../../module/task_env/v2.1.0/api/public-api.md) and [configuration contract](../../module/task_env/v2.1.0/api/configuration.md) before moving a caller.

- Use `pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1`; the old selected UIDs fail explicitly. Do not silently map an old task identity to a new one.
- Use the nested `execution`, `episode`, and `task` sections for selected configuration. Legacy `recipe`/`environment` input and supported aliases remain normalized; conflicts and unknown fields fail closed.
- The selected default controller profile for PickCube is `r3_continuous_v1`; `r1` is explicit. Record source/task identity separately from provider/backend/device/render configuration.
- State-only rendering is represented by a complete `renderer-selection-v1` mapping. Non-`none` selected renderers and unsupported Physics × Renderer pairings are rejected.
- Existing historical H5 records keep their original schema and identity. Do not rewrite or promote them because the resolved configuration record gained fields.
- TaskDefinition migration is not complete for all tasks. The next API scope covers PickCube, NutAssembly, shared construction for LIBERO, and compatibility checks for other lightweight tasks.

The v2.1.0 source and API changes are not applied retroactively to v1.1.0 or the v2.0.0 frozen tag.
