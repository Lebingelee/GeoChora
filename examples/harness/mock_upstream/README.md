# Mock upstream delivery

A synthetic upstream task for exercising the Task Harness without a real
upstream system or generated asset. Nothing here is a LIBERO demonstration or
source geometry.

| File | Content |
| --- | --- |
| `task.json` | `harness-upstream-task-v0`: task id, requested asset, lift goal, scene table and reset area |
| `asset_bundle.json` | `harness-mock-asset-bundle-v0`: one external asset with its sha256, collision proxy and mass contract |
| `mock_bowl.body.xml` | The MJCF body the bundle points at. Its sha256 is pinned in both JSON files; do not reformat it. |
| `semantic_examples.json` | Positive and negative lift-height cases for the semantic check |

Use it as the upstream input of the
[`geochora-task-harness`](../../../.agents/skills/geochora-task-harness/SKILL.md)
workflow, for example `catalog_query.py --asset-bundle examples/harness/mock_upstream/asset_bundle.json`.

[`test_mock_upstream_consistency.py`](../../../task_env/script/agent/test_mock_upstream_consistency.py)
runs catalog → spec → asset and semantic checks → compile on this sample
without stepping physics.

With the current PickCube construction entry, the candidate compiles as Core
task `pick-cube-v1`; the external asset contributes its collision and mass
contract and is identified by the spec hash. Its visual shell is not written
into the scene.
