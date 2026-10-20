"""Provider-free S1 checks for Phase II typed frames and articulation topology."""

import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

from task_env.artifacts import (
    ArticulationDefinition,
    AssetDefinition,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    PoseWorld,
    SceneDefinition,
)


def _asset():
    return AssetDefinition(
        "asset-definition-v1", "robot/panda", "v1", "procedural://geochora/panda"
    )


def _entity(entity_id):
    return EntityInstance("entity-instance-v1", entity_id, "robot/panda", "v1")


def _frame(entity_id, frame_id, *, kind="runtime", parent=None, pose=None):
    return FrameDefinition("frame-definition-v1", entity_id, frame_id, kind, parent, pose)


def _joint(entity_id, joint_id, parent, child, *, kind="revolute", axis=(0.0, 0.0, 1.0),
           position="radian", velocity="radian_per_second", position_size=1, velocity_size=1,
           parent_joint_pose=None, child_joint_pose=None):
    return JointDefinition(
        "joint-definition-v1",
        joint_id,
        FrameReference(entity_id, parent),
        FrameReference(entity_id, child),
        parent_joint_pose or PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
        child_joint_pose or PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
        kind,
        axis,
        position,
        velocity,
        position_size,
        velocity_size,
    )


def _articulation(entity_id, *, joint_id="joint1"):
    return ArticulationDefinition(
        "articulation-definition-v1",
        entity_id,
        "base",
        ("base", "hand"),
        (_joint(entity_id, joint_id, "base", "hand"),),
    )


def _scene_v2(*, frames, articulations=(), entity_ids=("robot",), scene_id="scene-v2"):
    return SceneDefinition(
        "scene-definition-v2",
        scene_id,
        (_asset(),),
        tuple(_entity(entity_id) for entity_id in entity_ids),
        tuple(frames),
        tuple(articulations),
    )


def test_authored_frame_composition_matches_independent_world_base_hand_camera_oracle():
    half = math.sqrt(0.5)
    entity_id = "robot"
    base = FrameReference(entity_id, "base")
    hand = FrameReference(entity_id, "hand")
    camera = FrameReference(entity_id, "camera-mount")
    scene = _scene_v2(
        frames=(
            _frame(entity_id, "base", kind="authored_fixed", pose=PoseWorld((1, 2, 3), (half, 0, 0, half))),
            _frame(entity_id, "hand", kind="authored_fixed", parent=base,
                   pose=PoseWorld((1, 0, 0), (half, half, 0, 0))),
            _frame(entity_id, "camera-mount", kind="authored_fixed", parent=hand,
                   pose=PoseWorld((0, 2, 0), (1, 0, 0, 0))),
        ),
    )

    world_camera = scene.resolve_frame_pose(camera)
    assert world_camera.position == pytest.approx((1, 3, 5), abs=1e-12)
    assert world_camera.quaternion_wxyz == pytest.approx((0.5, 0.5, 0.5, 0.5), abs=1e-12)
    hand_camera = scene.resolve_frame_pose(camera, relative_to=hand)
    assert hand_camera.position == pytest.approx((0, 2, 0), abs=1e-12)
    assert hand_camera.quaternion_wxyz == pytest.approx((1, 0, 0, 0), abs=1e-12)


def test_runtime_link_anchor_is_distinct_from_authored_fixed_frames():
    hand = FrameReference("robot", "hand")
    camera = FrameReference("robot", "camera-mount")
    scene = _scene_v2(
        frames=(
            _frame("robot", "base"),
            _frame("robot", "hand"),
            _frame("robot", "camera-mount", kind="authored_fixed", parent=hand,
                   pose=PoseWorld((0, 0, 0.1), (1, 0, 0, 0))),
        ),
        articulations=(_articulation("robot"),),
    )
    assert scene.resolve_frame_pose(camera, relative_to=hand).position == pytest.approx((0, 0, 0.1))
    with pytest.raises(ValueError, match="D02 canonical state"):
        scene.resolve_frame_pose(camera)


def test_dynamic_free_body_frame_can_exist_without_an_articulation():
    scene = _scene_v2(frames=(_frame("robot", "free-body"),))

    with pytest.raises(ValueError, match="D02 canonical state"):
        scene.resolve_frame_pose(FrameReference("robot", "free-body"))


def test_articulation_names_are_entity_local_and_free_joint_layout_keeps_7_over_6():
    right_joint = _joint("robot-right", "joint1", "base", "hand")
    left_joint = _joint("robot-left", "joint1", "base", "hand")
    floating = JointDefinition(
        "joint-definition-v1",
        "floating_base",
        FrameReference("robot-right", "base"),
        FrameReference("robot-right", "hand"),
        PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
        PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
        "floating",
        None,
        "xyz_meter_quaternion_wxyz",
        "linear_xyz_meter_per_second_angular_xyz_radian_per_second",
        7,
        6,
    )
    right = ArticulationDefinition("articulation-definition-v1", "robot-right", "base",
                                   ("base", "hand"), (right_joint,))
    left = ArticulationDefinition("articulation-definition-v1", "robot-left", "base",
                                  ("base", "hand"), (left_joint,))

    assert right.joints[0].joint_id == left.joints[0].joint_id == "joint1"
    assert (floating.position_size, floating.velocity_size) == (7, 6)


def test_joint_representation_axis_and_size_mismatches_fail_closed():
    with pytest.raises(ValueError, match="sizes do not match"):
        _joint("robot", "free", "base", "hand", kind="floating", axis=None,
               position="xyz_meter_quaternion_wxyz",
               velocity="linear_xyz_meter_per_second_angular_xyz_radian_per_second",
               position_size=6, velocity_size=6)
    with pytest.raises(ValueError, match="unit axis"):
        _joint("robot", "bad-axis", "base", "hand", axis=(0, 0, 2))
    with pytest.raises(ValueError, match="position representation"):
        _joint("robot", "bad-units", "base", "hand", position="meter")
    with pytest.raises(ValueError, match="unsupported joint kind"):
        _joint("robot", "unknown", "base", "hand", kind="planar")


@pytest.mark.parametrize(
    "kind, axis, position, velocity, position_size, velocity_size",
    [
        ("fixed", None, "none", "none", 0, 0),
        ("revolute", (0, 0, 1), "radian", "radian_per_second", 1, 1),
        ("continuous", (0, 0, 1), "radian", "radian_per_second", 1, 1),
        ("prismatic", (1, 0, 0), "meter", "meter_per_second", 1, 1),
        ("spherical", None, "quaternion_wxyz", "angular_xyz_radian_per_second", 4, 3),
        ("floating", None, "xyz_meter_quaternion_wxyz",
         "linear_xyz_meter_per_second_angular_xyz_radian_per_second", 7, 6),
    ],
)
def test_supported_joint_types_have_explicit_coordinate_layouts(
    kind, axis, position, velocity, position_size, velocity_size
):
    joint = _joint("robot", kind, "base", "hand", kind=kind, axis=axis,
                   position=position, velocity=velocity,
                   position_size=position_size, velocity_size=velocity_size)
    assert (joint.position_representation, joint.velocity_representation,
            joint.position_size, joint.velocity_size) == (
                position, velocity, position_size, velocity_size
            )


def test_frame_and_articulation_graphs_reject_missing_nodes_cycles_and_duplicate_parents():
    root = FrameReference("robot", "root")
    child = FrameReference("robot", "child")
    identity = PoseWorld((0, 0, 0), (1, 0, 0, 0))
    with pytest.raises(ValueError, match="missing parent"):
        _scene_v2(frames=(_frame("robot", "child", kind="authored_fixed",
                                 parent=FrameReference("robot", "absent"), pose=identity),))
    with pytest.raises(ValueError, match="cycle"):
        _scene_v2(frames=(
            _frame("robot", "root", kind="authored_fixed", parent=child, pose=identity),
            _frame("robot", "child", kind="authored_fixed", parent=root, pose=identity),
        ))
    with pytest.raises(ValueError, match="more than one parent joint"):
        ArticulationDefinition(
            "articulation-definition-v1", "robot", "root", ("root", "left", "right", "hand"),
            (_joint("robot", "left_joint", "root", "left"),
             _joint("robot", "right_joint", "root", "right"),
             _joint("robot", "left_hand", "left", "hand"),
             _joint("robot", "right_hand", "right", "hand")),
        )
    with pytest.raises(ValueError, match="disconnected or cyclic"):
        ArticulationDefinition(
            "articulation-definition-v1", "robot", "root", ("root", "a", "b"),
            (_joint("robot", "ab", "a", "b"), _joint("robot", "ba", "b", "a")),
        )


def test_scene_v2_roundtrip_and_entity_qualified_structure_identity_are_deterministic():
    frames = (
        _frame("robot-right", "base"),
        _frame("robot-right", "hand"),
        _frame("robot-left", "base"),
        _frame("robot-left", "hand"),
    )
    articulations = (_articulation("robot-right"), _articulation("robot-left"))
    first = _scene_v2(frames=frames, articulations=articulations,
                      entity_ids=("robot-right", "robot-left"))
    reversed_input = _scene_v2(frames=tuple(reversed(frames)),
                               articulations=tuple(reversed(articulations)),
                               entity_ids=("robot-left", "robot-right"))

    assert first.identity_hash == reversed_input.identity_hash
    assert SceneDefinition.from_mapping(first.to_mapping()) == first
    assert SceneDefinition.from_mapping(first.to_mapping()).identity_hash == first.identity_hash
    assert "frames" not in SceneDefinition("scene-definition-v1", "legacy", (_asset(),),
                                           (_entity("legacy"),)).to_mapping()


def test_one_entity_can_own_multiple_disjoint_articulation_trees():
    scene = _scene_v2(
        frames=tuple(_frame("robot", name) for name in ("arm-base", "arm-hand", "leg-base", "leg-foot")),
        articulations=(
            ArticulationDefinition("articulation-definition-v1", "robot", "arm-base",
                                   ("arm-base", "arm-hand"),
                                   (_joint("robot", "arm-joint", "arm-base", "arm-hand"),)),
            ArticulationDefinition("articulation-definition-v1", "robot", "leg-base",
                                   ("leg-base", "leg-foot"),
                                   (_joint("robot", "leg-joint", "leg-base", "leg-foot"),)),
        ),
    )

    assert len(scene.articulations) == 2


def test_v1_mapping_remains_strict_when_scene_definition_v2_fields_are_added():
    legacy = SceneDefinition("scene-definition-v1", "legacy", (_asset(),), (_entity("legacy"),))
    mapping = legacy.to_mapping()
    mapping["frames"] = []
    with pytest.raises(ValueError, match="unknown SceneDefinition fields for scene-definition-v1"):
        SceneDefinition.from_mapping(mapping)


def test_scene_definition_v2_rejects_invalid_entity_and_joint_frame_references():
    with pytest.raises(ValueError, match="undeclared scene entity"):
        _scene_v2(frames=(_frame("other", "base"),))
    with pytest.raises(ValueError, match="endpoints must belong to the same entity"):
        JointDefinition("joint-definition-v1", "cross", FrameReference("left", "base"),
                        FrameReference("right", "hand"), PoseWorld((0, 0, 0), (1, 0, 0, 0)),
                        PoseWorld((0, 0, 0), (1, 0, 0, 0)), "fixed", None, "none", "none", 0, 0)


def test_scene_v2_hash_captures_joint_frame_offsets_and_codec_rejects_unknown_fields():
    frames = (_frame("robot", "base"), _frame("robot", "hand"))
    first_joint = _joint(
        "robot", "joint1", "base", "hand",
        parent_joint_pose=PoseWorld((0, 0, 0.1), (1, 0, 0, 0)),
    )
    changed_joint = _joint(
        "robot", "joint1", "base", "hand",
        parent_joint_pose=PoseWorld((0, 0, 0.2), (1, 0, 0, 0)),
    )
    first = _scene_v2(frames=frames, articulations=(ArticulationDefinition(
        "articulation-definition-v1", "robot", "base", ("base", "hand"), (first_joint,)
    ),))
    changed = _scene_v2(frames=frames, articulations=(ArticulationDefinition(
        "articulation-definition-v1", "robot", "base", ("base", "hand"), (changed_joint,)
    ),))
    values = first.to_mapping()
    values["unreviewed_extension"] = True

    assert first.identity_hash != changed.identity_hash
    with pytest.raises(ValueError, match="unknown SceneDefinition fields for scene-definition-v2"):
        SceneDefinition.from_mapping(values)
    values = first.to_mapping()
    values.pop("frames")
    with pytest.raises(ValueError, match="missing SceneDefinition fields for scene-definition-v2"):
        SceneDefinition.from_mapping(values)


def test_scene_v2_structure_resolution_does_not_load_provider_or_native_runtime(tmp_path):
    code = r'''
import sys
from task_env.artifacts import AssetDefinition, EntityInstance, FrameDefinition, FrameReference, PoseWorld, SceneDefinition
scene = SceneDefinition("scene-definition-v2", "scene", (AssetDefinition("asset-definition-v1", "cube", "v1", "procedural://geochora/cube"),),
    (EntityInstance("entity-instance-v1", "cube-01", "cube", "v1"),),
    (FrameDefinition("frame-definition-v1", "cube-01", "root", "authored_fixed", None, PoseWorld((0,0,0), (1,0,0,0))),), ())
assert scene.resolve_frame_pose(FrameReference("cube-01", "root")).position == (0.0, 0.0, 0.0)
for name in sys.modules:
    assert name.split(".", 1)[0] not in {"mujoco", "geophys", "solvers", "scene", "visualization"}, name
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[3]), PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
