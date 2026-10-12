# Versioned integer native clock contract

The original v0 one-ULP rule and its reader/writer remain byte unchanged. It cannot represent accumulated GeoPhys boundary-time rounding reliably at TB100/TB50. No historical acceptance is reinterpreted.

The additive `canonical-execution-trajectory-v2` identifies `canonical-integer-native-clock-v1`. Control boundary k has exact integer native index n=k*control_substeps. Each interval contains exactly the declared native-step count, with contiguous applied-substep indices. physics_dt remains .002 s; control_dt equals physics_dt*control_substeps. Actual floating clocks remain stored separately, not overwritten with projected time.

For positive repeated binary64 additions of the represented dt, unit roundoff u=2^-53 and gamma_n=nu/(1-nu). The forward accumulated error is bounded by gamma_n*abs(n*dt). One projection ULP accounts for evaluating n*dt. Public outer clocks permit one additional ULP for evaluating k*control_dt. Unsupported n with nu>=1 fails closed. This is a step-derived representation bound, not a fixed physics tolerance.

The six Stage A live traces are explicitly promoted to the new version without changing any observed state, native time, target or acknowledgment. Originals remain available. This conversion adds only schema/version semantics; it is not a new physics run. Full episodes expose accumulated drift over approximately 3490–3501 native steps; their prefixes also cover short trajectories. Longer synthetic accumulated sums supplement, rather than replace, real evidence.

Result files: `stage_b_clock_results.json`, `stage_b_negatives.json`, `stage_b_synthetic.json`. The final status is governed by these files and the final acceptance JSON. Version-v1 H5 remains readable; new version-v2 H5 is separately hashed and checked for exact logical roundtrip. Skipped/duplicated ordering, corrupted counts, wrong timebases, clock jumps and nonfinite clocks must reject.
