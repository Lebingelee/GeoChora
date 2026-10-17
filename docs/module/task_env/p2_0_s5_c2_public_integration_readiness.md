# GeoChora P2.0-B S5-C2 — Public Integration & Backup Gate

**Status: INTEGRATION_COMPLETE — PUBLICATION_BLOCKED**
**Target:** v1.1.0, release candidate only.

## Ref preservation and local work

The local branch is `codex/p2-0-b-s4-5-b-workflow-consolidation`. The S5-B
candidate was `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`; S5-C1 was preserved in
a separate documentation-only commit, `2f8555a4c86470fb63cd2386a6e88729d4795a23`,
whose parent is exactly `2fb60de`. It does not alter task, runtime, controller,
provider, learner, or renderer implementation. The current S5-C2 report and
readiness updates are local documentation changes; no ignored workspace data
was cleaned or overwritten.

The ignored `workspace/` tree is approximately 71 GB and remains intact. It
contains about 62 GB under `workspace/qualification/` and about 3.5 GB under
`workspace/maintenance/`; the remainder includes detached checkouts and other
preserved experiment data. The first provider-free invocation used the default
Python 3.14 environment without pytest; its observed error was retained as a
separate receipt. The successful rerun used the validated Python 3.12.14
`geochora` environment.

## Public integration receipts

Both operations below are ordinary fast-forward pushes to `develop`; neither
used force, rewrote history, changed `main`, or published a release.

| Unit | Required parent at operation | Target | Public readback |
| --- | --- | --- | --- |
| S4.5-A/B plus converter argv fix | `0ff2d846a36c7014d2b40a530f52d99e64266ff9` | `bee498d1d784015f034c5b4af34320fdffa61411` | `bee498d1d784015f034c5b4af34320fdffa61411` |
| S5-B release-candidate documents | `bee498d1d784015f034c5b4af34320fdffa61411` | `2fb60de7851bf2e5651c2dc99fff7451c16e1a94` | `2fb60de7851bf2e5651c2dc99fff7451c16e1a94` |

Post-integration readback: public `develop` is `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`;
public `main` remains `e4e39883fbe01d4be4b172a53a535ef0095b3d64`; annotated
`v1.0.0` remains tag object `17c3100d4fabcb061c23569dea49973ebd177d51`, peeled
to `42787f5e4f658a3f81fdd2140cf7544d6342c783`. The independent machine
receipts are in the ignored S5-C2 workspace directory.

The expected ancestry is:

```text
0ff2d846 -> 5d57272d -> 59105726 -> 929dd8fa -> fc12780
         -> bee498d1 -> e0e4dbc -> 2fb60de -> 2f8555a (local S5-C1 docs only)
```

`fc12780` was independently reviewed as documentation/recovery metadata.
`bee498d` fixes converter argv forwarding and adds focused regression coverage;
it does not change the conversion algorithm, H5 schema, or action semantics.
The `bee..2fb` diff changes 31 paths: documentation, two requirements-file
installation path comments, and the provider-free retired-import test helper.
Selected task files, Runtime/Controller/Provider/Objects implementation,
provider behavior, and submodule Gitlinks are unchanged. `docs/releases/v1.0/`
matches the immutable v1.0.0 tree.

S5-C1’s documentation commit is kept separate from both integrated targets.
S5-C2’s updated readiness report and this receipt are not yet integrated. The
v1.1.0 package remains `RELEASE_CANDIDATE — NOT_PUBLISHED`.

## Bounded regression and identity

Command on the exact integrated code/document source `2fb60de`:

```bash
PYTHONPATH=GeoPhys/src:. /home/lly/miniconda3/envs/geochora/bin/python -m pytest -q task_env/diagnostics/tasks task_env/diagnostics/render/test_backend_registry.py
```

Result: **147 passed, 6 subtests passed, 1 upstream Taichi locale deprecation
warning, 160.07 s**. The successful log SHA-256 is
`077f593c60258c00ffc3eb9c693b1a3c97c695d10c8d0b7acec1335bf9c0f8b2`.
The default Python 3.14 attempt reported `No module named pytest` and is not a
test result; its separate receipt is retained. No native trajectory was
repeated because the selected execution-source closures are unchanged. The
four manipulation/provider intersections remain **TESTED_BOUNDED**, not
formally qualified by this regression.

The controller portability analysis remains unchanged from [S5-C1](p2_0_s5_c1_final_release_gate.md):
the raw generated MJCF embeds the absolute compiler `meshdir`, and raw XML bytes
feed the controller identity. The normalized XML, task/config/source hashes,
assets, FK/Jacobian probes, and identity-independent physical target fields
matched. Complete controller hashes differ by checkout path. The historical
relocated exploration remains **139 PASS / 8 FAIL** and was not rerun after the
test-helper corrections. No relocated full native rollout or applied-control
readback was performed. Option B—retain the current algorithm—is still a
recommendation requiring maintainer acceptance.

## Independent backup assessment

`lsblk` and `findmnt` show the repository and `/home` on the same physical
`/dev/sda`; no independent physical device or authorized external/network
destination was identified. The local `/home` volume has about 492 GB free, but
it is the same disk and is not an eligible backup target. No external endpoint,
path, capacity, access policy, or credentials were supplied; no private data
was sent anywhere.

The complete requested preservation set is large: `workspace/` is about 71 GB
(including 62 GB qualification records), while the root Git object database is
about 690 MB, GeoPhys about 188 MB, and the Menagerie checkout about 1.8 GB.
Backing up all of these is approximately 74 GB before bundle overhead or
duplicate safety margin. No independent destination capacity can be verified.
The list of eight enumerated ignored H5/checkpoint files and 19 current release-candidate document files
have local size/SHA receipts, but that is not a full hash inventory or
backup of the 71 GB workspace.

No copy, bundle creation, restore, H5 read-from-backup, Evidence read-from-
backup, or submodule restore was attempted. Status remains
**`BACKUP_NOT_VERIFIED` / `RELEASE_BLOCKED`**. Preserve the original files.
The [backup manifest](../../releases/v1.1/backup_manifest.json) defines the
future source set and recovery checks.

## Remaining release gates

- Independent storage destination, capacity, transfer hashes, Git bundle
  validation, and representative restore reads: **BLOCKED**.
- Maintainer acceptance of controller Option B: **MAINTAINER_DECISION_REQUIRED**.
- Fresh Python install and full relocated-checkout suite: **NOT_RUN**; obtain a
  decision on whether the documented source-based scope is sufficient.
- Candidate capability matrix approval and publication authorization:
  **MAINTAINER_DECISION_REQUIRED**.
- Integrate S5-C1/S5-C2 release-gate documentation through an independently
  reviewed local docs commit before publication; that local documentation is
  not yet part of public `develop`.

See the [updated release readiness](../../releases/v1.1/release_readiness.md)
and [S5-C3 checklist draft](../../releases/v1.1/s5_c3_publication_checklist_draft.md).
