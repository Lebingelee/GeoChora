# v2.1.0 candidate capabilities

The single current matrix is the versioned [TaskEnv capability matrix](../../module/task_env/v2.1.0/capabilities/capability-matrix.json). It records exact task, provider, backend, source, control representation, evidence Core head, provider pin, status, and limitations.

The matrix includes bounded F06 runtime-only routes, A123 frozen action replay on MuJoCo/GeoPhys, F05/DG02 USD source-actuation, the official Panda named-drive Isaac route, short NutAssembly force-freshness probes, and provider-free API regressions. The rows do not generalize beyond their named source, version, backend, controller, horizon, and evidence head.

No formal Qualification or new task success is granted. All six A123 episodes ended `external_stop` with `task_success=false`; F06 records 9/9 runtime-valid and 0/9 task-success. GP07 reuses accepted historical camera evidence and is not a new render test on P.
