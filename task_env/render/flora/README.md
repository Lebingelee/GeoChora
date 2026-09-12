# TaskEnv Flora adapter

This directory owns the Linux Flora boundary used by TaskEnv.  It does not
vendor Flora or alter `task_env/runtime`.

The intended data flow is:

1. The public `RenderSceneDesc` (or explicit
   `RenderAssemblyDesc` / `RenderPartDesc` / `RenderMeshAssetDesc`) is lowered
   once into GLB files plus one Flora SceneFile.
2. Each parallel environment contributes graph nodes that reference the same
   model table.
3. `FloraScene.update_from_provider()` consumes the existing rigid transform
   provider and updates all selected world/body nodes in one native batch.

For parallel TaskEnv rendering, `FloraParallelVisualizer` builds the asset
scene once for the selected render count, then receives only the selected
snapshot provider each frame.  It does not import one asset per physical
environment.  The live path reports `shared_scene_file_model_table`,
`scene_graph_instances`, and `host_batch_explicit_readback` separately so
asset sharing and transform transport remain visible in diagnostics.

The headed parallel scene also contains one shared checker-floor model. The
floor is authored as two colored mesh groups, so its checker pattern remains
visible even when the Flora texture-repeat path is unavailable. Its geometry is
not duplicated for each world instance.

The live backend does not parse MJCF/URDF and does not identify Go2.  It first
consumes explicit `RenderAssemblyDesc` entries and otherwise lowers the
compiled public `RenderSceneDesc`; the compiled scene model's public
`object_key` order names body nodes for the rigid transform provider.  The
Flora package does not own a private robot body-order table or asset path.

Set `FLORA_ROOT` or pass `runtime_root` explicitly.  The expected Linux build
layout is `bin/linux-x64/FloraRenderPyNative.so` and `python/{flora,flora_backend}`.

## Headed training controls

When PPO uses `--render`, the common TaskEnv training controller owns the
window lifecycle.  Flora uses the shared camera tool: hold RMB to rotate, hold
Ctrl+RMB to translate in the current view plane, use the wheel to dolly along
the view direction, and press `F` to toggle continuous rendering. Ctrl+RMB
does not alter the view rotation. The translation scale follows the fitted
parallel-world camera distance, so it remains usable for 256 worlds.
`Escape` disables rendering without stopping PPO.
