# Interval stream and clock audit

Opt-in ControlIntervalRecord prototype preserves ordered canonical requests plus independent AppliedCanonicalControl acknowledgments. Existing v0 contracts/H5 reader and legacy session.step unchanged.

| Provider | Hz | boundaries | exact native target count | max clock projection error s | first v0 clock rejection |
|---|---:|---:|---:|---:|---|
| geophys | 500 | 1565 | 1565 | 1.23e-13 | none |
| geophys | 100 | 314 | 1570 | 1.243e-13 | {'boundary': 3, 'previous_time': 0.020000000000000004, 'native_time': 0.030000000000000013, 'delta_error': 8.673617379884035e-18, 'v0_bound': 3.469446951953614e-18} |
| geophys | 50 | 158 | 1580 | 1.266e-13 | {'boundary': 2, 'previous_time': 0.020000000000000004, 'native_time': 0.04000000000000002, 'delta_error': 1.734723475976807e-17, 'v0_bound': 6.938893903907228e-18} |
| mujoco | 500 | 3500 | 3500 | 5.489e-13 | none |
| mujoco | 100 | 700 | 3500 | 0 | none |
| mujoco | 50 | 350 | 3500 | 0 | none |

Each outer boundary updates gripper once, at substep0; arm and gripper request targets are held on remaining1/5/10 native steps. Target hashes, ordering, acknowledgments, native counts and10N cap reconstructed from every real trace. No hidden native steps observed. GeoPhys actuator acknowledgments reflect existing float32 storage, not bitwise requested targets: preserve both representations rather than using a tolerance. First prototype audit incorrectly required request=ack; real_interval_attempt1.json is preserved, corrected only in diagnostic codec.

For n positive binary64 additions, u=2^-53, gamma_n=n*u/(1-n*u); legal accumulation error <=gamma_n*abs(n*dt)+ulp(n*dt). Tested10,000 additions and all real intervals, with independently exact native counts. GeoPhys raw time accumulates native dt; MuJoCo slower boundary projection is canonicalized by its existing readback. No dt or solver modification. v0 clock rejection occurs GeoPhys TB100 boundary3 and TB50 boundary2. Proposed extension must store integer physics-step count, projected canonical clock and raw native clock with derived bound. Do not overwrite existing v0 data or silently broaden its one-ULP rule. Recipe/interval prototype is not yet connected to a live candidate CanonicalRecorder; Infrastructure NO-GO pending review and wiring.
