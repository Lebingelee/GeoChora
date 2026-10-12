# Live executed-interval recorder

Stage A: PASS. Source checkpoint: 39479aa. Development infrastructure evidence only.

The opt-in `task_env.trajectory.canonical.execution` extension preserves original v0 contracts and H5 readers. It records EpisodeMetadata, full task artifact, reset/realized state, source-bound owner schemas, boundary state/feedback/readiness and complete canonical owner snapshots. Actual substep observations occur after each native step, using the pre-step public state/feedback and the target/application acknowledgment that actually executed. No zero-order-hold stream is fabricated after execution.

Every episode satisfies T+1 boundaries / T transitions. Equal-rate gripper updates once per outer boundary; applied targets and acknowledgments remain separately represented. Stage plans are losslessly content-addressed. H5 stores deterministic logical JSON plus checked integer projections; hashes and logical equality are checked on load. Native diagnostics remain separate.

Six live G0 episodes passed, followed by independent comparison against the prior shared +1 mm baseline: every common trace field matched exactly at every boundary. T: MuJoCo 3487/698/349, GeoPhys 3501/700/350 at 500/100/50 Hz. All six exact H5 roundtrips passed. Seven structural negative tests failed closed. Original PickCube v0 H5 roundtrip passed (1091 transitions / 1092 boundaries); v0 sources remain unchanged.

References: `stage_a_acceptance.json`, `stage_a_live_results_03.json`, `stage_a_independent_equivalence.json`, `stage_a_negatives.json`, `v0_regression.json`, `contracts.json`.

Implementation defects found and corrected before acceptance: boolean metrics projected to existing numeric metric fields while preserving their original types in raw metrics; NumPy scalar owner values received an explicit lossless codec; GeoPhys raw-time readback explicitly requested simulation time. Failed runs remain preserved. None changed controller/coordinator or physics behavior.

Stage A alone does not establish checkpoint restoration or formal replay qualification. No T1, full task or formal D0–D2 ran.
