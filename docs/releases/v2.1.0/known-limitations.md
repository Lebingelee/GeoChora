# v2.1.0 candidate limitations

- This is a local draft candidate: no tag, push, formal release, or new Qualification.
- The two API fixes passed 10 focused offline tests on `0bf4a8e`; the native/provider matrix was tested on its own earlier Core heads and was not rerun after these API-only fixes.
- F06 is 9/9 runtime-valid but 0/9 task-success. Solution effectiveness remains unresolved.
- The six A123 full frozen replays passed software/runtime and independent-reader checks; every episode ended `external_stop` and task success is false. Task2 GeoPhys's accepted contact exception is strictly scoped; task3 MuJoCo uses its frozen monitor tolerance.
- Task1 GeoPhys fluid-parameter projection impact is `NOT_MEASURED`; GP07 camera/render evidence is reused from its historical provider and is not a P render run.
- Natural Kit destruction is not claimed fixed. Strict DG03/source-actuation work remains unresolved. F07 and further Solution work are deferred.
- LIBERO/robosuite file-level terms and attribution remain unresolved. GeoChora and GeoPhys project licenses are `UNDECLARED`; GeoPhys provider remote reachability is `NOT_VERIFIED`.
- Generalized LIBERO TaskDefinition construction and compatibility across all lightweight tasks remain future work.
