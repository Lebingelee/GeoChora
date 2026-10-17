# NutAssembly Gripper/Contact Materialization Audit

## Status

**`materialization_boundary_localized`** — M0 rules out a static joint-to-pad geometry mismatch. M1 and M2 expose substantial dynamic provider differences; the MuJoCo lift failure is localized to loss of vertical traction followed by contact-patch escape. No behavioral correction was applied because no single shared or adapter defect is sufficiently isolated.

## Provenance and scope

- Branch: `codex/p1.8-e-r5-controller-architecture`; start and end HEAD: `e8ee54fa16e6537a39b61038d892f2646c0e1ac7`.
- Evidence root: `workspace/qualification/phase1/p1_8_nutassembly_r5_architecture/materialization_audit/`.
- Persistent-reference R3, planner, R1, task semantics, Nut mass/inertia, force thresholds, friction, and timeouts were not changed. No branch/worktree was created.
- Physics probes were limited to M0 static readback, M1 fixed-object TB100 close, and M2 free-grasp TB100 close/verify-lift. No T1/full task/D0-D2/boundary providers were run.

## M0 canonical opening → physical geometry

| Canonical opening | GeoPhys pad gap | MuJoCo pad gap | Difference |
|---:|---:|---:|---:|
| 40.0 mm | 42.999997 mm | 43.000000 mm | 0.003 µm |
| 35.0 mm | 37.999995 mm | 38.000000 mm | 0.005 µm |
| 30.0 mm | 32.999973 mm | 33.000000 mm | 0.027 µm |
| 25.0 mm | 27.999974 mm | 28.000000 mm | 0.026 µm |
| 20.0 mm | 22.999993 mm | 23.000000 mm | 0.007 µm |
| 15.0 mm | 17.999968 mm | 18.000000 mm | 0.032 µm |
| 10.0 mm | 12.999957 mm | 13.000000 mm | 0.043 µm |
| 5.0 mm | 7.999893 mm | 8.000000 mm | 0.107 µm |

The relationship is approximately `pad gap = canonical combined opening + 3.0 mm`. Maximum measured provider difference across the eight points is 0.107 µm. At the two authorization openings, 33.190 mm corresponds to a 36.190 mm pad gap, while 10.633 mm corresponds to a 13.633 mm pad gap. Thus, both values represent the same physical geometry when the joint coordinates are the same; the two authorization readings are different actual joint states, not two mappings of the same state.

| M0 question | Result |
|---|---|
| Does 33 mm mean the same physical gap? | Yes: ~36.19 mm on both providers. |
| Does 10.6 mm mean the same physical gap? | Yes: ~13.63 mm on both providers. |
| Are finger transforms consistent with authored kinematics? | Yes at equal q; inter-provider max difference ~0.15 µm. |
| Are collision pad sizes/offsets the same? | Authored/realized box dimensions and local offsets match; pair-resolved GeoPhys contact attribution unavailable. |
| Is Nut collision width the same? | Yes in the realized source geometry; handle width 31.75 mm excluding contact margin. |

Finger-body transforms match within approximately 0.15 µm at equal joint coordinates. Authored main pad collision is a box with half extents 8.5 × 4 × 8.5 mm and local pose (0, 5.5, 44.5) mm; four smaller box pads are also authored. The five Nut collision boxes and local poses match between the shared source, GeoPhys geometry arrays, and MuJoCo model arrays within float precision. The handle collision width along the finger closing direction is 31.75 mm (plus authored 1 mm margin per contact surface). M0 classification: **`kinematic_mapping_match`**. A pair-resolved GeoPhys contact proxy readback was not available, so M0 does not prove solver-level contact-response parity.

## Authored vs realized

| Quantity | Authored | GeoPhys realized | MuJoCo realized |
|---|---|---|---|
| Finger axis/limits | Slide axis (0,1,0), range 0–0.04 m | Equal-q FK matches; direct axis-array readback unavailable | Compiled axes/ranges match |
| Finger body transform | Left pos (0,0,58.4 mm); right same with 180° local Z quaternion | Body-pose parity within 0.15 µm at equal q | Matches authored MJCF |
| Main pad geom | Box half-size (8.5,4,8.5) mm; local pos (0,5.5,44.5) mm | Same shape data/local position | Same compiled box |
| Nut collisions | Five boxes; handle half-size (25.25,15.875,10) mm at local x=54 mm; 1 mm margin | Same five shape dimensions/positions | Same five box geoms and names |
| Nut friction | `1.6 0.08 0.001`; condim 4 | Expanded runtime array `[1.6,1.6,0.08,0.001,0.001]` | `[1.6,0.08,0.001]` |
| Finger/hand friction | `4.0 0.20 0.01`; condim 4 | Expanded runtime array `[4,4,0.20,0.01,0.01]` | `[4,0.20,0.01]` |
| Fixed tendon `split` | 0.5 × joint1 + 0.5 × joint2 | Source imported; direct runtime coefficient readback unavailable | Tendon length tracks mean finger q |
| Finger equality | joint1 = joint2; solimp `.95 .99 .001`, solref `.005 1` | M1 q difference reached 6.39 mm; equality-force readback unavailable | M1 q difference ≤18 µm |
| Gripper actuator 8 | Tendon transmission; ctrl 0–255; gain 0.78431372549; bias `0 -5000 -120`; source force range ±400 N | Runtime ctrl/force visible; model gain/bias/ctrlrange readback unavailable | Compiled values match source; controlled runtime force limit is clipped to ±30 N |

The realized friction arrays use different native layouts (three authored MJCF values versus five GeoPhys generalized values). The authored coefficients are present on both paths, but this audit does not establish exact friction-cone equivalence during sliding. Detailed source/model values are preserved in `authored_facts.json`.

## M1 fixed-object compression

Same fixed diagnostic Nut pose, held EE pose, TB100 outer loop and existing 500 Hz gripper inner servo; 4,420 close-stage inner samples per provider. Both probes ended at close timeout; neither authorized or ran verify-lift.

| Metric | GeoPhys | MuJoCo |
|---|---:|---:|
| First bilateral finger/Nut contact | Pair attribution unavailable | 2.570 s, at ~80.0 mm opening |
| First transient feedback ≥25 N | 2.596 s, 79.499 mm opening; 29.609 N | 2.596 s, 79.671 mm opening; 29.367 N |
| MuJoCo finger normal load at that sample | Unavailable | 2.379 N left + 2.447 N right |
| Final opening | 57.673 mm | 9.279 mm |
| Final canonical closing force | 30.0 N | 23.198 N |
| Final actuator ctrl / native force | 144.045 / −29.459 N | 0 / −23.198 N |
| Final finger q difference | 5.135 mm | 0.014 mm |
| Authorization / verify-lift | No / not run | No / not run |

M1 force/opening landmarks from the 2 ms traces:

| Event | GeoPhys opening / pad gap / feedback | MuJoCo opening / pad gap / feedback |
|---|---|---|
| Close start (~2.570 s) | 79.987 / 82.987 / 0.013 N | 80.000 / 83.000 / 0.000 N |
| First feedback ≥25 N (~2.596 s) | 79.499 / 82.499 / 29.609 N | 79.671 / 82.671 / 29.367 N |
| First 30 N reading | 77.367 mm opening at 2.632 s | Not observed; peak 29.367 N |
| Close timeout (~11.408 s) | 57.673 / 60.673 / 30.000 N | 9.279 / 12.279 / 23.198 N |

M1 shows a large provider difference in fixed-object close response, but does not isolate actuator, equality, or contact solver contributions. GeoPhys only reports object-level contacts here. In MuJoCo, canonical feedback uses the completed-step actuator-force cache while direct `MjData.actuator_force` is sampled after `mj_forward`; transient samples therefore are not phase-aligned and must not be interpreted as an exact force decomposition. The 29 N actuator feedback is not itself a contact-normal measurement.

## M2 free grasp

| Event | GeoPhys | MuJoCo |
|---|---|---|
| Authorization | controller-close-ready at 0.930 s; 33.190 mm; 30 N | stable fallback at 1.170 s; 10.633 mm; 26.549 N |
| Bilateral contact at authorization | Pair-level diagnostic unavailable | 22 points per finger; 16.050/16.233 N normal; ratio 0.989 |
| Verify-lift | PASS; max drift 0.0319 mm / 0.000927 rad | FAIL; max drift 101.927 mm / 0.005164 rad |

MuJoCo’s Nut center is laterally centered between the fingers at authorization (closing-axis offset 0.138 mm). This does not look like a gross lateral grasp-offset error. `grasped_nut` is separately recorded: its canonical predicate is reached-nut plus opening ≤45 mm, not mechanical contact. It stays true after native bilateral contact is lost.

### MuJoCo contact timeline and retention mechanics

- First bilateral contact: 2.570 s, while opening is still about 80 mm and the contact load is tiny; last bilateral contact: 4.368 s.
- Fallback authorization: 3.740 s. Bilateral contact is present with 22 contact points per finger, ~16.05 N / ~16.23 N normal load, and nearly symmetric load. The 25–27 N feedback at this event is mechanically accompanied by real bilateral Nut contact; **false-force readiness is not supported for this baseline authorization**.
- First relative drift >1 mm: 3.998 s. Bilateral contacts remain, with ~14.97 N / ~15.15 N normal loads. Net Nut contact resultant is about +0.980 N vertical, approximately its 0.981 N weight. Contact centroids are still on the handle side faces and have moved only modestly, so centroid migration is initially an effect of incipient slip rather than its first cause.
- First relative drift >8 mm: 4.208 s. Contacts remain bilateral (15 left / 14 right), but normal loads fall to ~6.57 N / ~5.98 N. Contact centroids have walked upward; contact normals now point approximately toward the Nut top face. Finger vertical force is about −8.71 N while table contact supplies +9.78 N; the Nut remains table-supported rather than following the EE.
- Force falls below 1 N at 4.358 s. Only three very weak finger/Nut contacts remain, while the table supports about 0.979 N. Bilateral contact is lost at 4.370 s; canonical `grasped_nut` is still true.

The best-supported MuJoCo failure description is **insufficient vertical contact traction at lift onset followed by contact-patch escape over the handle’s upper edge**. The available traces do not establish whether this comes from exact friction-cone realization, solver response, or interaction with lift acceleration. Friction coefficients are unchanged; no friction or geometry sweep was run.

## Root cause

- **Primary classification:** `mixed_materialization_boundary`
- **Confidence:** medium
- Static mapping/collision dimensions are matched. Dynamic close response and finger equality realization differ substantially between providers. MuJoCo authorization is mechanically real, but lift traction does not keep the Nut with the EE, and the contact patch then migrates onto the top edge. GeoPhys pair attribution is unavailable, preventing a complete force/geometry comparison.
- MuJoCo equality/tendon evidence does not implicate those constraints in the slip: at authorization its finger q coordinates differ by only 0.36 µm, equality force is ~0.026 N, and neither finger is near a joint limit. GeoPhys M1 has a large q asymmetry (max 6.39 mm), but this does not explain the MuJoCo failure.

## Correction

**None applied.** The evidence does not isolate a provider adapter bug, shared source-geometry defect, or shared servo-law defect. Repeating the prior arbitrary 3 mm grasp-z shift would be unsupported. A friction change would also be unsupported because the source values are present on both providers and no principled material correction was demonstrated. No post-correction TB100 run or rate expansion was performed.

## Preserved diagnostics

Large diagnostic JSON traces were gzip-compressed byte-for-byte after SHA-256 verification to keep the evidence footprint manageable. The preserved-file hashes and exact compressed paths are in `compressed_trace_manifest.json`; M1/M2 per-substep traces remain available in their `.gz` files.

## Integrity and next step

- Persistent R3, planner, timing, task semantics, Nut mass/inertia, 30 N target, 1 N deadband, 25 N fallback, readiness windows, and timeouts: unchanged.
- R1/PickCube: untouched. `public/main`: untouched. No behavioral sweep or correction.
- T1, full NutAssembly, D0–D2, SAPIEN, Genesis: **NOT RUN**.
- Next diagnostic should add pair-resolved GeoPhys finger/Nut contact and constraint-force readback, and align the per-substep actuator-force sample with the canonical feedback cache. Compare the fixed-object force-opening curve before selecting any behavior change.

