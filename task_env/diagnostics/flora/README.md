# Flora diagnostics

Run from the Geochora repository root with `PYTHONPATH=GeoPhys/src:.`:

```bash
python -m task_env.diagnostics.flora.runtime_probe \
  --flora-root /home/zyf/lly_project/Flora

python -m task_env.diagnostics.flora.asset_bundle --force

python -m task_env.diagnostics.flora.shared_asset_256 \
  --flora-root /home/zyf/lly_project/Flora

python -m task_env.diagnostics.flora.single_scene \
  --flora-root /home/zyf/lly_project/Flora
```

`asset_bundle` and `shared_asset_256` are offline SceneFile checks unless
`--flora-root` is supplied.  The latter then loads the 256-instance SceneFile
in Flora, applies a 3328-body native transform batch, writes a frame, and
checks native `unique_meshes` / `mesh_instances` statistics.
