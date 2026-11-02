# Installation and environment setup

## Python environment

The repository has no root `pyproject.toml`, `setup.py`, or `setup.cfg`. Create/use a Python environment compatible with the selected route and install the checked-in TaskEnv requirements from the repository root:

```bash
python -m pip install -r task_env/requirements.txt
# Optional learning routes:
python -m pip install -r task_env/requirements-rl.txt
```

Run repository examples with the checkout root and GeoPhys source on `PYTHONPATH`:

```bash
export PYTHONPATH="GeoPhys/src:."
```

The base dependency list currently pins NumPy 2.2.6, PyVista 0.46.5, Pillow >11, and MuJoCo >=3.8.1,<3.9.0, with SciPy, psutil, Pydantic, PyYAML, Taichi Forge, trimesh, Gymnasium, and h5py constraints recorded in `task_env/requirements.txt`. These are dependency declarations, not a guarantee that every provider/backend is installed or supported.

## Git submodules and optional engines

Initialize only the source dependencies needed by the selected workflow:

```bash
git submodule update --init GeoPhys asset/external/mujoco_menagerie
```

The candidate uses GeoPhys P=`67da1165149486d3ae3e779c13ce31af49e17d50` and Menagerie pin `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`. GeoPhys's own project license is undeclared; Menagerie model files carry upstream license/notice files that must be checked for the files actually used.

Isaac Sim is installed and licensed separately; it is not installed by the Python requirements. The bounded route used Isaac Sim 6.2, CUDA PhysX, a filtered dependency overlay, and the accepted EULA environment setting. The USD/source deliveries and benchmark installations used for prior checks are not included with this source tree. A fresh user must obtain and review the exact assets, install, EULA, and source manifest for their route; do not copy maintainer machine paths from ignored workspaces.

Genesis and SAPIEN are optional examples and were `NOT_RUN_DEPENDENCY` in the cited F06 evidence. Do not install an engine just to read these docs. See the [capability matrix](../capabilities/capability-matrix.json) for provider-specific boundaries.

## Distribution and licensing

No simulator asset bundle, H5 evidence, local USD, LIBERO/robosuite installation, or ignored workspace output is included in this candidate. See the [asset record](../../../../releases/v2.1.0/third-party-assets.md) for source identity, exclusions, and unresolved terms. Do not treat code authorship or a third-party notice as a project license grant.
