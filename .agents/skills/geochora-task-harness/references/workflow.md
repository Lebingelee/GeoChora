# CLI workflow

Use the caller's paths; examples below use `PY`, `CORE`, `RT`, `UP` and `OUT` as task-local shell variables. `PY` is the Core venv's Python, `RT` contains the CLI files, `UP` is the upstream directory, `OUT` is a fresh writable workspace. Set `PYTHONDONTWRITEBYTECODE=1` and run with `OUT` as the working directory so native logs do not dirty Core.

The CLIs can be called directly or imported with their directory on `PYTHONPATH`. They do not need an LLM or a package installation. No implicit engine fallback: choose a provider explicitly. Current physical acceptance is MuJoCo CPU; other provider names can be queried, and unsupported ones fail.

## A. Catalog and initial spec

```sh
"$PY" "$RT/catalog_query.py" --core-repo "$CORE" --asset-bundle "$UP/asset_bundle.json" --providers mujoco --output "$OUT/catalog.json"
```

Read `catalog.json`. Its `template_details.pick-lift-v0.spec_template` contains all required fields; template limits are adjacent. This template is Panda + table + one box-collision object, fixed z, fixed 0.002 × 5 timebase; lift is the only success predicate. Reach and grasp thresholds are diagnostics. Unsupported fixtures/templates must be reported.

For upstream schema `harness-upstream-task-v0`, map `task_id`, `scene`, `initial_pos_xy`, `initial_reset_half_extent_m` and `goal.height_m` to their corresponding spec fields. Use `requested_asset_uid` and `asset_sha256` from the explicit supplied resource handoff. Keep `source_request_uid` as upstream provenance; do not pretend the mock UID is the original asset. The template provides fields the upstream does not specify. Write a new `round1.spec.json`; do not use a prior final spec or the regression script as the answer.

## B–C. Reserve, check, register

```sh
"$PY" "$RT/construction_ledger.py" init --ledger "$OUT/construction.json" --task "$UP/task.json" --catalog "$OUT/catalog.json" --provider mujoco
"$PY" "$RT/construction_ledger.py" begin --ledger "$OUT/construction.json" --spec "$OUT/round1.spec.json"
"$PY" "$RT/check_candidate.py" --core-repo "$CORE" --spec "$OUT/round1.spec.json" --catalog "$OUT/catalog.json" --examples "$UP/semantic_examples.json" --provider mujoco --count 20 --base-seed 0 --output-dir "$OUT/round1"
```

`check_candidate` composes assets → compile/admission → semantic → feasibility, stopping at the first failing stage. Its final stdout lists exactly the report files it produced. Feed those files to:

```sh
"$PY" "$RT/construction_ledger.py" finish --ledger "$OUT/construction.json" --reports <the actual emitted report paths>
```

Check exits: 0=pass, 1=expected failure, 2=input/tool error. Ledger exits: 0=registered/ready/candidate_ready, 1=stopped/escalate, 2=invalid evidence or operation. Read JSON, not only exit codes. Every output directory must be new; reports are not overwritten.

The current feasibility report records raw completion and cleanup facts for
every attempted seed. `finish` independently revalidates those rows, their
declared order and totals; a passing 20-seed report without the current
completion contract is rejected. Historical reports missing these facts are
preserved as-is and cannot establish a passing candidate.

Unified findings have `check, category, locality, spec_path, observed, expected, evidence, revision_hint`. Categories: spec_invalid, asset_missing, capability_unsupported, semantic_mismatch, init_infeasible, expert_failed, execution_fault, template_missing. `unknown` locality means unestablished ownership. Semantic endpoint examples must include positive and negative cases; synthetic cases only test the checker, not real source-demo equivalence.

If a diagnostic is needed, make an explicit separate spec and run `feasibility_probe.py --core-repo ... --spec ... --catalog ... --provider ... --seeds ... --output ...`. Diagnostic probes are evidence, not new accepted candidates. Isolate relevant variables using the failure's actual reset poses and stage; keep failed diagnostics. Do not count a one-seed diagnostic as the final 20-seed check.

For a supported repair, write a new spec and a revision JSON:

```json
{
  "report_sha256": "SHA-256 of the exact previous report file bytes",
  "finding_index": 0,
  "reason": "Explain the observed finding, proposed field change and limited inference.",
  "diagnostic_reports": ["absolute paths to actual probe reports, required for unknown locality"],
  "diagnostic_specs": ["corresponding absolute paths to the actual diagnostic specs, in the same order"]
}
```

Each diagnostic must bind to its actual saved spec. Its report hash and spec hash must differ from the cited failed candidate. Copying or renaming the same report is not independent diagnosis. Both diagnostic reports and specs are preserved in the ledger and Judge package.

Run `begin --revision <file> --spec <new spec>`, then the same checks and `finish`. The runtime refuses stale report bytes, unrelated report citations, empty diffs, a sixth round and adjacent repeated findings. `status --ledger ...` revalidates file hashes. Runtime files must remain unchanged during the attempt; code fixes belong in a separately identified harness version, not hidden inside an existing run.

## D. Oracle Candidate

```sh
"$PY" "$RT/oracle_candidate.py" --core-repo "$CORE" --spec <final spec> --catalog "$OUT/catalog.json" --provider mujoco --seed 0 --time-limit-s 120 --output-dir "$OUT/oracle-seed0"
```

Output: `oracle.h5`, `oracle.check.json`, `inspect.json`, source snapshots and input identities. Canonical v0 H5 stores measured boundaries and transitions; same-run completion is in the hash-bound sidecar. `logical_mapping_exact` comes from Core's finish/save/load comparison; inspector `storage_roundtrip` is only its existing validation label. Both remain storage evidence, not replay qualification. The timeout budget covers execution/finalization/inspection; faults and cleanup errors remain failures.

## E. Stage-1 pending package

After reading the Core evidence Skill:

```sh
"$PY" "$RT/judge_package.py" --core-repo "$CORE" prepare --validation-dir <passing check_candidate directory> --construction-log "$OUT/construction.json" --oracle-dirs "$OUT/oracle-seed0" --upstream-dir "$UP" --output "$OUT/workspace/tasks/<task-id>/artifacts/ver_001"
"$PY" "$RT/judge_package.py" --core-repo "$CORE" verify --directory <that package directory>
```

The validation directory holds candidate.spec.json, candidate.artifact.json and the four reports. The package copies raw bytes, checks original semantic/upstream/asset/H5/source hashes and produces a relative evidence index. Mutable Human decision is outside the digest it will cite, avoiding a hash cycle. `pending` means no Human decision; the eventual final decision is approve/reject. No video is claimed on the selected route, whose render config is unsupported. Original absolute history refs are preserved with a relocation map.

For this bounded implementation, `prepare` accepts the supplied synthetic upstream bundle contract. Real asset bundle formats, additional templates and Isaac native execution require their respective owner implementations and new acceptance; do not infer support from a provider parameter.
