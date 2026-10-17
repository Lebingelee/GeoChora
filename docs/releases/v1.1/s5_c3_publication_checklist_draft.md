# v1.1.0 S5-C3 Publication Checklist Draft

**RELEASE_CANDIDATE — NOT_PUBLISHED**
**Publication status: BLOCKED**

This checklist is a future gate. It authorizes no tag, release, `main` change,
or publication.

## Before release approval

- [ ] Re-fetch `public`; verify `develop` still contains the approved integrated
  S4.5 functional unit and S5-B documents, currently read back as
  `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`.
- [ ] Review S5-C1 commit `2f8555a4c86470fb63cd2386a6e88729d4795a23` and final
  S5-C2 readiness/backup documents. Integrate those docs only after separate
  maintainer approval, by normal fast-forward, then read back the exact remote
  SHA. Stop on any public divergence.
- [ ] Obtain explicit maintainer acceptance of controller identity Option B:
  current controller hashes include path-derived raw MJCF identity and are not
  guaranteed equal across checkout roots. Preserve historical hashes.
- [ ] Decide whether fresh Python 3.12 dependency installation and a full
  relocated-checkout suite are mandatory. Keep current states `NOT_RUN` until
  actually completed; the prior relocated exploration is 139 PASS / 8 FAIL.
- [ ] Verify the candidate matrix, API migration inventory, source identities,
  all retired APIs, and the release scope. Confirm bounded results are not
  labeled QUALIFIED and there are no new D0-D2 or Phase II claims.
- [ ] Record a maintainer-approved independent backup destination and confirm
  it has capacity for approximately 74 GB plus safety margin. A path on
  `/dev/sda` does not qualify.
- [ ] Back up source, all Git refs/objects, required submodules, immutable
  v1.0.0 objects/Evidence, `workspace/qualification/`, maintenance receipts,
  H5/checkpoints, release documents, and test receipts. Verify bundle integrity,
  file sizes/SHA-256, exact Gitlinks, and representative restored source, H5,
  checkpoint, and qualification Evidence reads. Update the manifest only from
  observed results. Until then `BACKUP_NOT_VERIFIED` remains a hard blocker.
- [ ] Re-run focused provider-free release checks on the exact final candidate
  commit; rerun native task routes only if selected execution source changed or
  a specific uncovered risk requires it.
- [ ] Re-read public `main`, the annotated v1.0.0 tag object and peeled commit;
  ensure all remain unchanged.

## Publication authorization gate

- [ ] Maintainer approves the release notes, migration guide, capability
  matrix, version policy, known limitations, and final candidate commit.
- [ ] Independent backup and restore checks are PASS.
- [ ] Maintainer explicitly authorizes creating the annotated `v1.1.0` tag and
  publishing the GitHub Release as separate actions.
- [ ] Create the tag only on the specifically approved `develop` commit; read
  back tag object and peeled commit. Publish only after tag verification.
- [ ] Record the release commit, tag object, peeled commit, backup manifest
  hash, Gitlinks, final tests, and publication timestamp. Do not modify
  `main` or v1.0.0 without separate authorization.

No checklist item above is represented as complete solely because its code or
documentation exists. The independent backup remains the primary blocker.
