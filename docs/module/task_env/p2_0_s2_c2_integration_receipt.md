# P2.0-B S2-C2 — Integration receipt

Date: 2026-10-16. The selected four-file NutAssembly authoring route is integrated into canonical public `develop`.

## Fast-forward record

- Fetched baseline: `a6372099ac2055045cca16c03a0514825d635e8f`.
- Final tested NutAssembly execution source: `4d6d65c55eca994b4317bcfb80797c69e48452c6`.
- S2-C2 implementation commits: `ce1cd782ff26b52c4fd8738fbb1b595cfd6f44f2`, `4d6d65c55eca994b4317bcfb80797c69e48452c6`.
- Review and authoring-convention documentation was committed at `5408d053be920ab6e3d9e88337b45ccf87ad757e` and pushed with a normal fast-forward from `a637209…`.
- Immediate remote readback after push: `public/develop = 5408d053be920ab6e3d9e88337b45ccf87ad757e`.
- Readback of protected refs: `main = e4e39883fbe01d4be4b172a53a535ef0095b3d64`; annotated `v1.0.0` tag object `17c3100d4fabcb061c23569dea49973ebd177d51`, peeled commit `42787f5e4f658a3f81fdd2140cf7544d6342c783`. They were not modified.

## Final acceptance gates

The complete C2 diff was reviewed against `a637209…`: the NutAssembly task directory contains only `__init__.py`, `task.py`, `solution.py`, and `config.yaml`; the selected TaskArtifact and Outcome Completion V1 identities are unchanged; the selected solution has no historical candidate inheritance. Guarded close authorization, measured physical limits, the one admitted readiness warning, and original strict lifecycle reporting remain separately recorded. The selected route reads its tracked recipe and has no runtime dependency on ignored workspace configuration. RuntimeSession, generic provider/runtime APIs, and shared controller/recorder contracts are unchanged.

The final provider-free suite passed **93 tests in 154.63 s** on final execution source `4d6d65c…`. Final-source CPU full routes passed at 100 Hz, NA-S0 seed19 on GeoPhys and MuJoCo. All 11 authored stages, `release_retreat`, measured insertion/release, `task_success`, `planned_trajectory_completed`, `outcome_complete`, control/native-step counts, T/T+1 boundaries, and canonical H5 roundtrip passed. H5 SHA-256 values are `e539d5b2662d191c0a70b1ac9dd593842279397b8627f0e3871d8852c78c2271` (GeoPhys) and `f7000d28e1a47363542bef8909341d5a13582175941b394987ad31f0ea4f5931` (MuJoCo). The evidence is bounded functional regression only and does not inherit P1.8 FULL or D0–D2 qualification.

All 27 removed task-local paths resolve to the recorded pre-consolidation Git blobs at `a637209…`; the 19 paths present in v1.0.0 match their recorded immutable tag blobs. The remaining eight paths were introduced after v1.0.0 and are recoverable from the pre-consolidation commit. Frozen Evidence and historical decisions were not edited.

## Public authoring convention review

PickCube currently re-exports `build_reference` from its package root; NutAssembly explicitly rejects its former package-level builder and keeps the task-owned helper in `task.py`. Recommend `task_env.make_env(uid, …)` as the canonical public environment API and keep implementation builders on their exact task module paths. This integration does not silently restore NutAssembly's old alias or remove PickCube's existing export; retiring the latter requires a separate explicit migration and compatibility decision.

The previously reported single-disk SATA/BadCRC risk and lack of verified independent backup remain open. S3 starts from the integrated C2 develop history; no S4 Static Physics work is included here.
