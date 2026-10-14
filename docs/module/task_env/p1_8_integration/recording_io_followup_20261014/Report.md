# P1.8 Recorder I/O Follow-up — 2026-10-14

**Status: read-only semantic audit passed; no rollout, replay, or qualification was run.**

The bounded summary audit added in `ac38e1e16340fcf8416f3a540a0280e30e6f78bc`
was run against the exact archived H5 used for the earlier full-mapping
measurement. Its logical payload hash and all semantic predicates passed while
peak process RSS remained 118,688 KiB. This reduces observed peak RSS from
6,165,508 KiB to 118,688 KiB (51.95× lower, a 98.07% reduction).

The memory reduction came with a time cost in this single-run comparison: the
new audit profile took 103.494 s compared with the earlier 89.365 s profile, a
15.81% increase. The current process wall time was 103.94 s. The new path parses
the ordered episode in two passes so it can validate boundaries without
retaining the full boundary and transition arrays. It reports
`max_episode_records_retained=1`. This is an
observed memory/time tradeoff, not evidence that full replay loading is now
bounded or faster.

A single 8 MiB read-buffer counterfactual produced the same semantic PASS and
logical hash, but took 104.369 s profile time and 158,848 KiB peak RSS. Relative
to the 1 MiB run, that is 0.85% slower and 33.84% more RSS. The default remains
1 MiB; increasing the buffer did not improve this workload. The output and
`/usr/bin/time -v` log are retained in local Evidence.

## Reproduction and provenance

The source H5 is 253,645,379 bytes, SHA-256
`301a494f90cbf86d03b4ddcf939eb4ebcf578f8e6b048513e85ea85eff02f997`, with
2,044,311,447 logical JSON bytes, 11,868 transitions and 11,869 boundaries.
The new audit returned semantic validation PASS, the same canonical logical
hash, and `full_expert_status=NOT_ADJUDICATED`. The recorded last lifecycle
state is completed and task success is true, but this audit does not determine
FULL acceptance or replay validity.

The run used the repository's GeoChora Python 3.12 environment with a 4,500,000
KiB virtual-memory ceiling. `/usr/bin/time -v` reported 118,688 KiB maximum RSS,
no process swap, and 103.94 s wall time. The validator profile reported
45.248 s for its first pass, 58.246 s for semantic streaming, and 103.494 s
total. The profile and exact output are retained in the local Evidence tree;
their hashes and the audited source hashes are in [results.json](results.json).

The baseline used the earlier full-mapping `load_streaming` audit against the
same source H5: 89.365 s total and 6,165,508 KiB peak RSS. Because each
implementation was measured once, the timing difference should guide the next
profiling step rather than be treated as a stable benchmark. The current result
does establish that semantic verification no longer requires a multi-GiB
resident episode mapping.

## Remaining optimization boundary

The audit improvement is memory-focused. Python parsing and per-record semantic
checks still take about 103 s for this 2.04 GB logical payload, and D0/D1 replay
loaders still need their current replay representation. Any further latency
reduction should preserve raw and canonical hashes, every semantic predicate,
T/T+1 and native-clock checks, and malformed-file rejection. A lazy replay
reader or a structured H5 storage format would need separate design and
compatibility evidence; neither is claimed here.
