"""Provider-free rejection of coherent but source-inconsistent Scene declarations."""
from dataclasses import replace

import pytest

from task_env.artifacts import ExecutionSpec, FrameReference, PoseWorld
from task_env.runtime.sessions import api
from task_env.tasks.position_candidate.fixed_attachment_candidate import build_fixed_attachment_candidate


@pytest.fixture(scope="module")
def candidate():
    return build_fixed_attachment_candidate()


def _rebind(candidate, scene):
    """Recompute all declaration pins so a stale hash cannot mask the defect."""
    pin = replace(candidate.assembly.scene_pin, scene_identity_sha256=scene.identity_hash)
    assembly = replace(candidate.assembly, scene_pin=pin)
    plan = replace(candidate.attachment_plan, scene_pin=pin,
                   logical_content_sha256=assembly.logical_content_sha256)
    artifact = replace(candidate.artifact, scene_identity_hash=scene.identity_hash)
    parent = replace(candidate.runtime_source.scene_source,
                     source_id=f"scene-definition-v3:{scene.identity_hash}")
    source = replace(candidate.runtime_source, task_artifact_hash=artifact.identity_hash,
                     scene_definition=scene, scene_source=parent,
                     fixed_attachment_plan=plan, fixed_attachment_assembly=assembly,
                     fixed_attachment_sources={"panda-arm": parent, "panda-hand":
                         candidate.runtime_source.fixed_attachment_sources["panda-hand"]})
    return artifact, source


@pytest.mark.parametrize("entity_index", (0, 1))
@pytest.mark.parametrize("defect", ("axis", "parent", "kind", "parent_pose", "child_pose",
                                    "asset_hash", "asset_revision", "asset_reference", "asset_license"))
def test_materialization_rejects_source_inconsistent_declarations(candidate, monkeypatch, entity_index, defect):
    scene = candidate.scene
    if defect.startswith("asset_"):
        change = {
            "asset_hash": {"source_content_sha256": "0" * 64},
            "asset_revision": {"source_revision": "wrong-revision"},
            "asset_reference": {"source_reference": "menagerie:wrong.xml"},
            "asset_license": {"license_id": "wrong-license"},
        }[defect]
        scene = replace(scene, assets=tuple(
            replace(asset, **change) if index == entity_index else asset
            for index, asset in enumerate(scene.assets)
        ))
    else:
        articulation = scene.articulations[entity_index]
        joints = list(articulation.joints)
        joint = joints[1]
        if defect == "axis":
            joints[1] = replace(joint, axis=(1.0, 0.0, 0.0))
        elif defect == "parent":
            frame_id = "link0" if entity_index == 0 else "left_finger"
            joints[1] = replace(joint, parent_frame=FrameReference(articulation.entity_id, frame_id))
        elif defect == "kind":
            kind, position, velocity = (("prismatic", "meter", "meter_per_second") if entity_index == 0
                                       else ("revolute", "radian", "radian_per_second"))
            joints[1] = replace(joint, kind=kind, position_representation=position, velocity_representation=velocity)
        elif defect == "parent_pose":
            joints[1] = replace(joint, pose_parent_from_joint=PoseWorld((1.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)))
        elif defect == "child_pose":
            joints[1] = replace(joint, pose_child_from_joint=PoseWorld((0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0)))
        scene = replace(scene, articulations=tuple(
            replace(item, joints=tuple(joints)) if index == entity_index else item
            for index, item in enumerate(scene.articulations)
        ))
    artifact, source = _rebind(candidate, scene)
    calls = []
    monkeypatch.setattr(api, "_materialize_admitted", lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="differs from source|topology/type/axis|pose differs|provenance differs"):
        api.materialize(artifact, ExecutionSpec("mujoco", "p1_2_scalar_cpu_v0", "none", "cpu", 31, "strict"), source=source)
    assert calls == []


def test_measured_candidate_still_reaches_native_boundary_unchanged(candidate, monkeypatch):
    before = (candidate.scene.identity_hash, candidate.assembly.identity_hash,
              candidate.attachment_plan.identity_hash, candidate.artifact.identity_hash)
    calls = []
    monkeypatch.setattr(api, "_materialize_admitted", lambda *args: calls.append(args) or "NATIVE_IO_STUB")
    result = api.materialize(candidate.artifact,
        ExecutionSpec("mujoco", "p1_2_scalar_cpu_v0", "none", "cpu", 31, "strict"),
        source=candidate.runtime_source)
    assert result == "NATIVE_IO_STUB"
    assert len(calls) == 1
    assert before == (candidate.scene.identity_hash, candidate.assembly.identity_hash,
                      candidate.attachment_plan.identity_hash, candidate.artifact.identity_hash)
