# v2.1.0 candidate installation notes

This local candidate uses the repository's checked-in requirements and explicit source paths; there is no root packaging metadata for editable installation.

```bash
python -m pip install -r task_env/requirements.txt
# Optional learner dependencies:
python -m pip install -r task_env/requirements-rl.txt
git submodule update --init GeoPhys asset/external/mujoco_menagerie
export PYTHONPATH="GeoPhys/src:."
```

The candidate pins GeoPhys P=`67da1165149486d3ae3e779c13ce31af49e17d50` and Menagerie=`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`. The listed requirements do not install Isaac Sim. The tested Isaac 6.2/CUDA PhysX route requires a separate installation, accepted EULA, and the exact source delivery; those are not packaged here.

The local USD deliveries, LIBERO/robosuite source installation, H5 files, mesh/data closures, benchmark installation, filtered Isaac overlay, and ignored workspace outputs are excluded. See [third-party assets](third-party-assets.md). Installation instructions do not establish runtime support outside the exact rows of the [matrix](../../module/task_env/v2.1.0/capabilities/capability-matrix.json).
