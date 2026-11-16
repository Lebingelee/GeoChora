# Dependency profiles

`mujoco-warp-4.0.1-python312.txt` records the exact packages resolved in the
G06a attempt001 isolated worker environment. The installation used the package
index's Linux x86-64 Python 3.12 wheels, with MuJoCo and MJWarp 4.0.1 and Warp
1.18.0. It is a worker environment, not a replacement for the main interpreter;
it does not include Torch. The tested learner interpreter used Torch
2.14.0+cu130 and CUDA Python bindings. The cross-interpreter CUDA IPC and
MJWarp/renderer checks are bounded diagnostics; the canonical device batch routes now have bounded G06 acceptance; exact
source/physics/render intersections remain limited to the tested system.
`pip check` passed in the isolated worker. Select the worker interpreter through
the explicit runtime configuration; no machine-specific path is embedded here.

G06b also uses a separate Isaac Sim 6.2 Python 3.12 worker with the same main
learner interpreter. Its measured native-batch routes have bounded G06 acceptance and remain
limited to the source and physics intersections documented in the current API.

For the merged GeoPhys main integration, the learner interpreter uses
`taichi-forge==0.7.0` and `taichi-forge-runtime==0.7.0`, matching GeoPhys's
declared version. CUDA framebuffer, finite clipping, a B=3 MJWarp task-camera
path, and device lifecycle tests were checked with that release. A separate
GeoPhys component AOT check still fails because this release does not export
`taichi.aot.Component`; these results do not qualify that component path.

The G06a integration advances the GeoPhys gitlink from
`c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7` to
`a2c85b7fb87e821b1e3b211c97ed2b695db8b3c1`, including the requested merge
of main at `2110d359a90f3fbcea89d35d7756a523ebd91cde`. The upstream main
navigation, package admission, and public API governance checks have known
failures outside the validated rendering intersection. They and the AOT
component gap are deferred by maintainer decision; this integration does not
claim those checks pass or qualify the wider GeoPhys API.

Create a separate Python 3.12 environment and install with
`python -m pip install -r task_env/dependencies/mujoco-warp-4.0.1-python312.txt`;
run the repository with its usual `PYTHONPATH` and do not mix site-packages.

G06 closes at GeoPhys `198d30ac64ce873a1467f55d2adfc471db18fbc5`; Menagerie
remains `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`. The upstream-to-stage
merge above was completed; merging the stage changes back to upstream main is
still deferred. See the [G06 implementation summary](../../docs/module/task_env/v2.1.1/maintenance/g06/implementation-summary.md)
for native/device evidence, full gitlink provenance and the explicit discrete/32
GeoPhys PickCube scope. No environment was upgraded during closeout.
