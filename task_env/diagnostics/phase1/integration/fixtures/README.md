# Recorder contract fixture

`execution_prefix_fixture.json.gz` contains two transitions, three boundaries,
and ten native control applications from a bounded MuJoCo 100 Hz prefix smoke.
It exercises the existing canonical execution v2 schema, native 500 Hz gripper
cadence, guarded V2/V5 owner snapshots and content-addressed stage plans.

The fixture retains exact float values and identities. It is self-contained;
tests do not construct a simulator or require local Evidence paths. The source
smoke stopped after four transitions and was intentionally task-incomplete.
Neither this fixture nor the recorder tests establish FULL success or replay
qualification. Compression is deterministic (`mtime=0`).
