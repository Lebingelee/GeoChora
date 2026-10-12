# Pre-D0–D2 handoff

Branch codex/p1.8-integration; start ff46c7822708d43f682e983b2b0ab30589545ef7; prototype source commit dd2258622f6c0ebd46774109730029e2f4aea8d3. Reports-only ending commit can be resolved with git rev-parse HEAD. No push; public/main unchanged.

Evidence root: workspace/qualification/phase1/p1_8_pre_d0_d2_readiness/. Compact reports mirrored here; all large trace/contact/H5 remains workspace/independent archive.

Run commands (new output directories required):

```sh
PYTHONPATH=.:GeoPhys/src:GeoPhys MUJOCO_GL=egl /home/lly/miniconda3/envs/geochora/bin/python -m task_env.diagnostics.phase1.integration.stable_grasp --rate 100 --provider geophys --output NEW_DIR
PYTHONPATH=. /home/lly/miniconda3/envs/geochora/bin/python -m task_env.diagnostics.phase1.integration.readiness_synthetic --output NEW_DIR
PYTHONPATH=. /home/lly/miniconda3/envs/geochora/bin/python -m task_env.diagnostics.phase1.p1_1_contracts --output NEW_JSON
```

Exact orchestration/audit programs preserved in Evidence audit_programs/. Six physical G0 cells run; MuJoCo3PASS, GeoPhys3preclose-heightFAIL. NoT1/full/D0–D2/boundary-provider experiments. Fresh MuJoCo4550physicalboundaries exactly match independent archive; only historical source identity/hash differences are separated. PickCube archived1091/1092 v0H5 roundtrip exact, no fresh PickCube physics in this audit.

Owner/interval prototypes are diagnostic imports only, not root exports or replacement schemas. Synthetic mock tests and all real target interval reconstruction pass, but real live checkpoint/recorder integration plus GeoPhys clock projection remain blockers. Prequalification lock refers to source commit above; later report-only commits do not change frozen behavior. All source files protected by provenance hashes.

Archive3576 originalhashes and10 selectedentries recovered. Zero deletion/compression/space reclaim; sole local archive retained. Video exactSHA/container check only, decoder unavailable. Previous instrumentation attempts (scalar type, mock-force timing, ack/request equality, missing GeoPhys PYTHONPATH/ffmpeg tools) preserved/identified; no physical changes used to fix tests.

Next first action: Human Review the ~0.64–0.65mm GeoPhys stable-height mismatch against frozen0.1mm gate and authorize a bounded separate diagnostic. In parallel review versioned recording clock/owner/interval recipe; then implement real recorder restore equivalence. Only after blockers and auxiliary-pad risk are dispositioned may a separately authorized campaign perform G0/T1/full experts/sixgoldens/D0(6)/D1(12)/D2(12). P1.6/P1.7 unwaived; PhaseI not closed.
