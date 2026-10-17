# v1.1.0 S5-C3 Publication Checklist Draft

**RELEASE_CANDIDATE — NOT_PUBLISHED**
**Publication status: BLOCKED**

This checklist is a future gate. It authorizes no tag, release, `main` change,
or publication.

## Before release approval

- [ ] Re-fetch `public`; verify `develop` still contains the approved integrated
  S4.5 functional unit and S5-B documents, currently read back as
  `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`.
- [ ] Review S5-C1 commit `2f8555a4c86470fb63cd2386a6e88729d4795a23`, S5-C2
  documentation commit `9de96ddd6b42d8d29f7e513a8f17a3adc64bc7bf`, and the
  local S5-C3 package/report. Integrate documentation only after separate
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
- [ ] Review the [S5-C3 release acceptance evidence package](evidence/README.md)
  and verify its L1 file inventory and L2 local size/SHA checks.
- [ ] Explicitly approve or reject the proposed scoped retention policy. The
  previous full-workspace `BACKUP_NOT_VERIFIED` gate remains active until this
  decision is recorded. If approved, record `RELEASE_METADATA_PRESERVED`,
  `RAW_EVIDENCE_BACKUP_NOT_VERIFIED`,
  `HISTORICAL_WORKSPACE_BACKUP_NOT_VERIFIED`, and
  `MAINTAINER_RISK_ACCEPTANCE_REQUIRED` separately.
- [ ] Accept or reject the residual risk that L2 raw H5/log files and L3
  historical workspace data have no verified independent copy. SHA-256
  metadata cannot restore missing data. Do not claim a full backup PASS.
- [ ] Keep all L2/L3 source files untouched. If an independent archive is
  later authorized, define its destination and perform copy/hash/restore checks
  before changing either unverified status.
- [ ] After separate maintainer authorization, integrate the local L1 evidence
  commit to public `develop` by normal fast-forward. Read back the remote commit
  and verify every L1 file and hash remotely; reject unexpected binaries,
  credentials, or secrets. No such remote integration has occurred yet.
- [ ] Re-run focused provider-free release checks on the exact final candidate
  commit; rerun native task routes only if selected execution source changed or
  a specific uncovered risk requires it.
- [ ] Re-read public `main`, the annotated v1.0.0 tag object and peeled commit;
  ensure all remain unchanged.

## Publication authorization gate

- [ ] Maintainer approves the release notes, migration guide, capability
  matrix, version policy, known limitations, and final candidate commit.
- [ ] The scoped preservation policy and unbacked L2/L3 risks are explicitly
  accepted by the maintainer, or the previously required full independent
  backup and restore checks are PASS.
- [ ] Maintainer explicitly authorizes creating the annotated `v1.1.0` tag and
  publishing the GitHub Release as separate actions.
- [ ] Create the tag only on the specifically approved `develop` commit; read
  back tag object and peeled commit. Publish only after tag verification.
- [ ] Record the release commit, tag object, peeled commit, backup manifest
  hash, Gitlinks, final tests, and publication timestamp. Do not modify
  `main` or v1.0.0 without separate authorization.

No checklist item above is represented as complete solely because its code or
documentation exists. The retention-scope decision, residual-risk acceptance,
remote evidence verification, and final publication authorization remain open.
