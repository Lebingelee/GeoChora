# P1.8 Recorder I/O Optimization — 2026-10-14

Status: bounded development optimization and recorder regression. No new FULL
rollout, full D0/D1/D2 replay, qualification or remote publication was executed.
The optimization preserves task semantics, controllers, planner, geometry,
force caps, clocks and capture/readiness gates. Before editing, existing work
was committed as `fdbb0ff` (guarded-transition/replay development checkpoint).

Exact commands, measurements, preserved failure and source hashes are in
[measurements.json](measurements.json). Raw local Evidence remains under
`workspace/qualification/phase1/p1_8_guarded_transitions_20261014/recording_io_optimization_v1/`.
The interrupted source directory and its H5/native sidecar were not modified.

## Measured cause and scope

The interrupted 500 Hz H5 is 253,645,379 bytes on disk but contains
2,044,311,447 bytes of logical JSON. It has 11,868 transitions and 11,869
boundaries. The previous live finish retained the original recorder and traces,
materialized the whole JSON string/bytes, loaded a second complete object tree,
and repeated validation/hash/deep equality. This makes memory pressure and
swap activity much larger than the compressed file suggests.

Validation also expanded and deep-copied content-addressed stage plans at every
boundary and re-encoded those plans for owner snapshot hashing. Storage-level
deduplication therefore did not eliminate validation-level repeated work.
Prior progress messages could not identify the exact running function: they
must not be treated as proof that the process had reached final deep equality.

## Implemented changes

1. `canonical.streaming.save_streaming` writes individually encoded records
   through 1 MiB buffers into the existing H5 schema. Canonical JSON ordering,
   float representation, escaping, SHA-256, numeric projections, gzip level 4,
   atomic rename and no-overwrite behavior are preserved. `save` remains
   available unchanged as the legacy serialization route.
2. `verify_roundtrip` actually reads all persisted JSON bytes and compares them
   with the original mapping's canonical encoding, then checks the logical
   hash and numeric projections. Live finish no longer constructs a second
   complete object tree. Source semantics are still fully validated at freeze
   and save. Reports explicitly identify byte roundtrip and whether legacy
   full-object loading was performed.
3. `load_streaming` incrementally parses records and returns the same full
   mapping as the legacy reader. It still runs all semantic predicates,
   numeric-projection checks and a full canonical logical-hash recomputation.
   The old `load` remains available for compatibility. Replay diagnostics use
   the new reader; no replay equality gates were relaxed.
4. Owner integrity validation serializes each blob once per validation call,
   uses its exact encoded bytes in historical expanded snapshot hashes, and
   avoids deep-copying large fields. Caches do not persist across caller
   mutations. Mutable replay restore still uses owned deep copies.
5. Live recording explicitly opts into lossless content references for plans,
   guard state, authorization, guard decisions, events and lifecycle history.
   The generic recorder default remains `_actions` only. Expanded snapshots
   retain the same values and hashes. Recipe/source identities distinguish new
   recording provenance; no historical file is rewritten.
6. Contact JSONL is written as boundaries arrive and closed before final H5
   processing. Its filename, JSON formatting and complete content are preserved.
   This avoids accumulating the entire contact sidecar in RAM. Checkpoint
   selection also reads just the needed owner fields instead of expanding every
   complete snapshot into a second list.

With unchanged source data, canonical byte encoding and logical hashes are
identical. New recordings have separately declared recorder provenance and
lossless owner-reference layout, so they must not reuse a former source identity.

The principal memory changes are:

\[
M_{\mathrm{old\ finish}}\approx
M_{\mathrm{source}}+M_{\mathrm{loaded}}+M_{\mathrm{whole\ JSON\ temporaries}},
\]

\[
M_{\mathrm{new\ finish}}\approx
M_{\mathrm{source}}+M_{\mathrm{chunk}}+M_{\mathrm{largest\ record}}+M_{\mathrm{blob\ cache}}.
\]

The new reader still retains its final full mapping. It is not a lazy replay
interface, and the entire pipeline is not bounded to 1 MiB.

## Actual verification

| Check | Result |
|---|---|
| Archived complete payload scan/hash | PASS; 4.913 s; peak RSS 103,508 KiB |
| Archived parse + all semantic predicates + logical hash | PASS; 89.365 s; peak RSS 6,165,508 KiB |
| Incremental parse component | 32.864 s |
| Full semantic validation component | 34.931 s |
| Canonical logical-hash component | 21.569 s |
| Snapshot stress pattern, 100 hashes × 4,000 plan rows | Historical 1.573 s; optimized 0.0629 s; hashes exact |
| Recorder/guard/lifecycle contract tests | 47 PASS |
| MuJoCo 500 Hz native-ramp four-transition prefix | Byte roundtrip, old/new reader parity, action/control/owner reconstruction, every prefix owner restore: PASS |
| Contact sidecar before/after streaming, same prefix | Four lines byte-exact |
| Compilation and diff whitespace checks | PASS |

The archived source file SHA-256 is
`301a494f90cbf86d03b4ddcf939eb4ebcf578f8e6b048513e85ea85eff02f997`.
Its logical SHA-256 is
`f2fd057b02acae739cd930c828c4ae98cc0a36980e5e9e84f1d7301e595050f2`.

Tests cover v1/v2 file compatibility, byte-exact encoding, split UTF-8/numeric
tokens, T/T+1, skipped native substeps/counts, applied target identity, time and
owner integrity, stale/mutated blobs, truncated/extra payload, corrupted hash,
numeric projections and missing datasets. Valid JSON with a recomputed matching
hash but an invalid native count is still rejected by both readers.

The 25× snapshot result is a synthetic local algorithm measurement, not an
end-to-end rollout speedup. The interrupted old run and the new isolated reader
have different memory envelopes; they are not a controlled paired benchmark.
Actual size/peak-memory reduction for a newly recorded complete FULL episode
remains to be measured.

## Preserved failure and recovered source facts

An initial bounded smoke called the raw worker directly, bypassing native Arm
Ramp acknowledgment memory. Reconstruction failed at boundary 1 solely in
`arm_schedule.last_applied_arm`. The failure was saved, not suppressed. The
corrected smoke used the real lifecycle runner with a four-transition bound
and passed exact reconstruction and restore.

The interrupted H5 itself now passes complete structural/semantic/hash checks.
It records all 11 stages, final task success `true`, lifecycle status
`completed`, and completion reason `expert_sequence_completed` at 23.736 s.
These are recovered recorded facts. The final FULL acceptance report was never
written, native gzip completeness was not checked, and full replay was not run;
this optimization does not independently adjudicate FULL acceptance or promote
a source golden.

## Follow-up on the bounded semantic audit

After commit `ac38e1e`, the same archived H5 was rechecked through the
summary-only `validate_streaming` path. Its semantic and logical-hash checks
passed with 118,688 KiB peak RSS (about 116 MiB), compared with 6,165,508 KiB
in the earlier full-mapping audit. The reduction is about 52×. The current
validator profile took 103.49 s versus the earlier 89.36 s profile, about
15.8% slower; the current process wall time was 103.94 s. The comparison uses
the same source H5 and complete semantic
predicates, but one run per implementation; treat it as an observed resource
tradeoff, not a repeated benchmark. It confirms bounded audit memory, not faster
full replay loading. Details and hashes are in the
[follow-up report](../recording_io_followup_20261014/Report.md).

## Resume guidance and remaining work

For read-only audit of an existing source, use a fresh output file:

```bash
python -m task_env.diagnostics.phase1.integration.recording_io_audit \
  --input <source-execution.h5> --output <fresh-audit.json> --semantic
```

Main-thread work can first recover its original FULL oracle/report from the
preserved source, retaining the SIGTERM and missing-report provenance. A future
fresh FULL recorder run will use the versioned streaming verification and
lossless history blobs automatically, and should record end-to-end RSS, swap,
runtime and H5/sidecar sizes. No full run was launched here.

Remaining costs include the resident full mapping required by current replay,
the worker's retained general trace/stage rows, and snapshot generation before
content deduplication. A fully lazy replay API or structured numeric-H5 migration
would require another versioned contract and is outside this 30-minute change.
