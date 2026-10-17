# Installation and Clean-Checkout Reproduction

**RELEASE_CANDIDATE — NOT_PUBLISHED**

## Distribution model

This is a source-based repository release. The repository has no root
`pyproject.toml`, `setup.py`, or `setup.cfg`, so `pip install .` and editable
installation are not supported claims. Run from the repository root and set
`PYTHONPATH=GeoPhys/src:.`.

The release-candidate source was exercised on **Ubuntu 24.04.4 LTS, x86_64,
Python 3.12.14**. Other operating systems and Python versions were not
reproduced as part of this candidate preparation.

## Checkout and submodules

Use a clean clone at the approved release-candidate source commit. The current
candidate code commit is `bee498d1d784015f034c5b4af34320fdffa61411`; the root
repository pins these Gitlinks:

| Path | Gitlink identity | Purpose |
| --- | --- | --- |
| `GeoPhys` | `c665ce5028a12bb4d2afe49f05e015fa9b684a39` | GeoPhys provider and CPU runtime dependency. |
| `asset/external/mujoco_menagerie` | `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` | Robot assets used by the selected MuJoCo tasks. |

The exact commits above were also resolved by a read-only `git fetch --dry-run` against their declared remotes; each pinned object is locally available. Current upstream branch heads may advance independently of these Gitlinks. Initialize the required root submodules:

```bash
git clone https://github.com/Lebingelee/GeoChora.git
cd GeoChora
git checkout bee498d1d784015f034c5b4af34320fdffa61411
git submodule update --init GeoPhys asset/external/mujoco_menagerie
```

The GeoPhys repository lists nested `dexjoco` and nested Menagerie submodules.
They were not initialized for the bounded scalar task reproduction described
here. Initialize them only if a separately documented workflow requires them.

## Dependencies

Create an isolated Python 3.12 environment and install the tracked core
requirements:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r task_env/requirements.txt
export PYTHONPATH=GeoPhys/src:.
```

The optional `task_env/requirements-rl.txt` adds SB3, Torch, and RSL-RL
dependencies. Install it only for the corresponding learning workflow. A fresh
dependency installation was **NOT_RUN** during this RC preparation; these are
the repository's documented requirements, not a newly verified lockfile.

## Supported task/provider smoke

Selected bounded full-route evidence exists for these exact intersections:

| Task | Provider/backend | Control | Reset | Bounded result |
| --- | --- | --- | --- | --- |
| PickCube P1.6 | GeoPhys / CPU | 100 Hz | seed 31 | Full expert, measured lift success, canonical recording checks. |
| PickCube P1.6 | MuJoCo / CPU | 100 Hz | seed 31 | Full expert, measured lift success, canonical recording checks. |
| NutAssembly Outcome V1 | GeoPhys / CPU | 100 Hz | NA-S0 seed 19 | Full 11-stage route and physical task outcome; strict Expert failure and admitted readiness warning remain separately recorded. |
| NutAssembly Outcome V1 | MuJoCo / CPU | 100 Hz | NA-S0 seed 19 | Full 11-stage route and physical task outcome; strict Expert completed without readiness warning. |

Minimal task/example commands from repository root:

```bash
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --seed 31 --horizon 6000
PYTHONPATH=GeoPhys/src:. python examples/tasks/nut_assembly.py --provider geophys --seed 19 --horizon 6000
```

The second command runs the guarded NutAssembly expert. Task outcome,
trajectory completion, and original Expert lifecycle are reported separately.
For a bounded, successful recording example:

```bash
PYTHONPATH=GeoPhys/src:. python examples/recording/record_expert.py \
  --env-id pick-cube-p16-reference-v1 --provider mujoco --seed 31 \
  --horizon 600 --output workspace/new-run/pickcube.h5
PYTHONPATH=GeoPhys/src:. python examples/recording/inspect_h5.py \
  --input workspace/new-run/pickcube.h5
```

H5 storage validation does not establish D0 reconstruction. See
[`examples/README.md`](../../../examples/README.md) for the full current
workflow command matrix.

## Clean source-checkout reproduction result

A detached worktree at `bee498d1d784015f034c5b4af34320fdffa61411` was created,
the two root Gitlinks above were initialized and read back at their exact
commits, and public `make_env` construct/reset/close smokes passed for both
selected UIDs on both GeoPhys/CPU and MuJoCo/CPU. The output is retained under
the ignored local evidence path
`workspace/maintenance/p2_0_v1_1_clean_checkout_20261017/workspace/maintenance/p2_0_s5_b_20261017/clean_checkout_smoke.json`.
This was not a fresh Python dependency installation, and it did not rerun full
trajectories.

Artifact/configuration/task-source hashes matched the accepted candidate.
PickCube's generated controller identity differed by checkout root because
the production controller fingerprints raw MJCF bytes containing an absolute
checkout path. The observed alternate identity is recorded separately in the
source-recovery manifest; it does not indicate a task source or Artifact
change, but callers should retain the resolved source/controller identity
generated by their own checkout.
