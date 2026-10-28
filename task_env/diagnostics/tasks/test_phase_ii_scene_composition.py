"""Provider-free S1 checks for Phase II Robot and ControlGroup composition."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from task_env.artifacts import (
    ActuatorReference,
    ActuatorResourceDefinition,
    ArticulationDefinition,
    AssetDefinition,
    ControlGroup,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    JointDefinition,
    PoseWorld,
    RobotInstance,
    SceneDefinition,
)


ROOT = Path(__file__).resolve().parents[3]
IDENTITY = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))


def _asset(asset_id, *, version="v1"):
    return AssetDefinition(
        "asset-definition-v1", asset_id, version, f"procedural://geochora/{asset_id}"
    )


def _entity(entity_id, asset_id="franka/panda"):
    return EntityInstance("entity-instance-v1", entity_id, asset_id, "v1")


def _joint(entity_id, joint_id="joint/shared"):
    return JointDefinition(
        "joint-definition-v1",
        joint_id,
        FrameReference(entity_id, "base"),
        FrameReference(entity_id, "tool"),
        IDENTITY,
        IDENTITY,
        "revolute",
        (0.0, 0.0, 1.0),
        "radian",
        "radian_per_second",
        1,
        1,
    )


def _frame(entity_id, frame_id, *, kind="runtime", parent=None, pose=None):
    return FrameDefinition(
        "frame-definition-v1", entity_id, frame_id, kind, parent, pose
    )


def _articulation(entity_id):
    return ArticulationDefinition(
        "articulation-definition-v1",
        entity_id,
        "base",
        ("base", "tool"),
        (_joint(entity_id),),
    )


def _default_scene_parts():
    robot_entity_ids = ("robot", "robot/arm")
    entities = (
        _entity("robot"),
        _entity("robot/arm"),
        _entity("object/cube", "object/cube"),
        _entity("sensor/camera", "sensor/camera"),
    )
    frames = (
        _frame("robot", "base"),
        _frame("robot", "tool"),
        _frame("robot/arm", "base"),
        _frame("robot/arm", "tool"),
        _frame("object/cube", "origin", kind="authored_fixed", pose=IDENTITY),
        _frame(
            "sensor/camera",
            "optical",
            kind="authored_fixed",
            parent=FrameReference("robot", "tool"),
            pose=PoseWorld((0.0, 0.0, 0.1), (1.0, 0.0, 0.0, 0.0)),
        ),
    )
    articulations = tuple(_articulation(entity_id) for entity_id in robot_entity_ids)
    robots = tuple(
        RobotInstance(
            "robot-instance-v1",
            entity_id,
            (FrameReference(entity_id, "base"),),
        )
        for entity_id in robot_entity_ids
    )
    resources = (
        ActuatorResourceDefinition("actuator-resource-v1", "robot", "arm/grip"),
        ActuatorResourceDefinition("actuator-resource-v1", "robot", "hand:finger"),
        ActuatorResourceDefinition("actuator-resource-v1", "robot", "shared"),
        ActuatorResourceDefinition("actuator-resource-v1", "robot/arm", "grip"),
        ActuatorResourceDefinition("actuator-resource-v1", "robot/arm", "shared"),
    )
    groups = (
        ControlGroup(
            "control-group-v1",
            "robot",
            "arm",
            (ActuatorReference("robot", "arm/grip"),),
        ),
        ControlGroup(
            "control-group-v1",
            "robot",
            "hand",
            (ActuatorReference("robot", "hand:finger"),),
        ),
        ControlGroup(
            "control-group-v1",
            "robot/arm",
            "arm",
            (ActuatorReference("robot/arm", "grip"),),
        ),
        ControlGroup(
            "control-group-v1",
            "robot",
            "shared",
            (ActuatorReference("robot", "shared"),),
        ),
        ControlGroup(
            "control-group-v1",
            "robot/arm",
            "shared",
            (ActuatorReference("robot/arm", "shared"),),
        ),
    )
    return entities, frames, articulations, robots, resources, groups


def _scene_v3(*, entities=None, frames=None, articulations=None, robots=None,
              actuator_resources=None, control_groups=None, scene_id="dual-robot-scene"):
    defaults = _default_scene_parts()
    return SceneDefinition(
        "scene-definition-v3",
        scene_id,
        (_asset("franka/panda"), _asset("object/cube"), _asset("sensor/camera")),
        defaults[0] if entities is None else tuple(entities),
        defaults[1] if frames is None else tuple(frames),
        defaults[2] if articulations is None else tuple(articulations),
        defaults[3] if robots is None else tuple(robots),
        defaults[4] if actuator_resources is None else tuple(actuator_resources),
        defaults[5] if control_groups is None else tuple(control_groups),
    )


def test_single_and_dual_robot_scene_resolves_entity_qualified_actuators():
    scene = _scene_v3()
    entities, frames, articulations, robots, resources, groups = _default_scene_parts()
    single_robot = _scene_v3(
        entities=(entities[0], entities[2], entities[3]),
        frames=(*frames[:2], *frames[4:]),
        articulations=articulations[:1],
        robots=robots[:1],
        actuator_resources=resources[:2],
        control_groups=groups[:2],
    )

    assert tuple(robot.entity_id for robot in single_robot.robots) == ("robot",)
    assert scene.resolve_robot("robot").entity_id == "robot"
    assert scene.resolve_robot("robot/arm").entity_id == "robot/arm"
    assert scene.resolve_control_group("robot", "arm").actuator_refs == (
        ActuatorReference("robot", "arm/grip"),
    )
    assert scene.resolve_control_group("robot", "hand").actuator_refs == (
        ActuatorReference("robot", "hand:finger"),
    )
    assert scene.resolve_actuator(ActuatorReference("robot", "arm/grip")).entity_id == "robot"
    assert scene.resolve_actuator(ActuatorReference("robot/arm", "grip")).entity_id == "robot/arm"
    assert scene.resolve_actuator(ActuatorReference("robot", "shared")) != scene.resolve_actuator(
        ActuatorReference("robot/arm", "shared")
    )
    assert scene.resolve_control_group("robot", "shared") != scene.resolve_control_group(
        "robot/arm", "shared"
    )
    with pytest.raises(KeyError, match="unknown entity-qualified actuator"):
        scene.resolve_actuator(ActuatorReference("robot", "missing"))
    camera = FrameReference("sensor/camera", "optical")
    tool = FrameReference("robot", "tool")
    assert scene.resolve_frame_pose(camera, relative_to=tool).position == (0.0, 0.0, 0.1)
    with pytest.raises(ValueError, match="D02 canonical state"):
        scene.resolve_frame_pose(camera)
    assert {entity.entity_id for entity in scene.entities} == {
        "robot", "robot/arm", "object/cube", "sensor/camera"
    }


def test_entity_and_resource_names_are_not_resolved_by_delimiter_concatenation():
    scene = _scene_v3()
    left = scene.resolve_actuator(ActuatorReference("robot", "arm/grip"))
    right = scene.resolve_actuator(ActuatorReference("robot/arm", "grip"))

    # Both would become "robot/arm/grip" under a naive entity + '/' + resource key.
    assert left != right
    assert (left.entity_id, left.actuator_id) == ("robot", "arm/grip")
    assert (right.entity_id, right.actuator_id) == ("robot/arm", "grip")


def test_v3_scene_roundtrip_and_identity_are_stable_under_declaration_order():
    first = _scene_v3()
    entities, frames, articulations, robots, resources, groups = _default_scene_parts()
    reordered = _scene_v3(
        entities=reversed(entities),
        frames=reversed(frames),
        articulations=reversed(articulations),
        robots=reversed(robots),
        actuator_resources=reversed(resources),
        control_groups=reversed(groups),
    )
    assert first.identity_hash == reordered.identity_hash
    assert first.identity_hash == "fee77d95cb729b4008d90618618dfee00c0941b195e16641044c27336db60a99"
    assert SceneDefinition.from_mapping(first.to_mapping()) == first
    assert SceneDefinition.from_mapping(first.to_mapping()).identity_hash == first.identity_hash


def test_scene_v1_v2_mappings_and_hashes_are_preserved_by_v3_evolution():
    asset = AssetDefinition(
        "asset-definition-v1", "robot/panda", "v1", "procedural://geochora/panda"
    )
    entity = EntityInstance("entity-instance-v1", "robot", "robot/panda", "v1")
    scene_v1 = SceneDefinition("scene-definition-v1", "scene-v1", (asset,), (entity,))
    frames = (_frame("robot", "base"), _frame("robot", "hand"))
    baseline_joint = JointDefinition(
        "joint-definition-v1",
        "joint1",
        FrameReference("robot", "base"),
        FrameReference("robot", "hand"),
        IDENTITY,
        IDENTITY,
        "revolute",
        (0.0, 0.0, 1.0),
        "radian",
        "radian_per_second",
        1,
        1,
    )
    scene_v2 = SceneDefinition(
        "scene-definition-v2",
        "scene-v2",
        (asset,),
        (entity,),
        frames,
        (ArticulationDefinition(
            "articulation-definition-v1", "robot", "base", ("base", "hand"),
            (baseline_joint,),
        ),),
    )

    assert scene_v1.identity_hash == "283fcf2766ce4b0eb1eaf83d27856d2b37472f8f46c92605dd587f0f2a81b36a"
    assert scene_v2.identity_hash == "af5618c3404100c82c5083fbf59466230d7bc1b7db8b8ba30bae99f145f81467"
    assert tuple(scene_v1.to_mapping()) == ("schema_version", "scene_id", "assets", "entities")
    assert tuple(scene_v2.to_mapping()) == (
        "schema_version", "scene_id", "assets", "entities", "frames", "articulations"
    )
    assert SceneDefinition.from_mapping(scene_v1.to_mapping()) == scene_v1
    assert SceneDefinition.from_mapping(scene_v2.to_mapping()) == scene_v2


def test_v3_rejects_unknown_actuators_duplicate_writers_and_cross_entity_groups():
    entities, frames, articulations, robots, resources, groups = _default_scene_parts()
    unknown_group = ControlGroup(
        "control-group-v1",
        "robot",
        "unknown",
        (ActuatorReference("robot", "missing"),),
    )
    with pytest.raises(ValueError, match="unknown actuator"):
        _scene_v3(control_groups=(*groups, unknown_group))

    duplicate_writer = ControlGroup(
        "control-group-v1",
        "robot/arm",
        "also-grip",
        (ActuatorReference("robot/arm", "grip"),),
    )
    with pytest.raises(ValueError, match="more than one statically declared writer"):
        _scene_v3(control_groups=(*groups, duplicate_writer))

    with pytest.raises(ValueError, match="belong to its robot entity"):
        ControlGroup(
            "control-group-v1",
            "robot",
            "cross-entity",
            (ActuatorReference("robot/arm", "grip"),),
        )


def test_v3_rejects_duplicate_owners_unknown_roots_and_unowned_resources():
    entities, frames, articulations, robots, resources, groups = _default_scene_parts()
    with pytest.raises(ValueError, match="scene robot entity IDs"):
        _scene_v3(robots=(*robots, robots[0]))

    with pytest.raises(ValueError, match="exactly identify its entity articulations"):
        _scene_v3(robots=(RobotInstance(
            "robot-instance-v1", "robot", (FrameReference("robot", "missing"),)
        ), robots[1]))

    duplicate_resource = ActuatorResourceDefinition("actuator-resource-v1", "robot", "arm/grip")
    with pytest.raises(ValueError, match="duplicate entity-qualified actuator resource IDs"):
        _scene_v3(actuator_resources=(*resources, duplicate_resource))

    unowned = ActuatorResourceDefinition("actuator-resource-v1", "object/cube", "motor")
    with pytest.raises(ValueError, match="must belong to a RobotInstance entity"):
        _scene_v3(actuator_resources=(*resources, unowned))


def test_v3_codecs_are_strict_and_legacy_versions_do_not_admit_composition_fields():
    values = _scene_v3().to_mapping()
    values["unreviewed_extension"] = True
    with pytest.raises(ValueError, match="unknown SceneDefinition fields for scene-definition-v3"):
        SceneDefinition.from_mapping(values)

    values = _scene_v3().to_mapping()
    values.pop("control_groups")
    with pytest.raises(ValueError, match="missing SceneDefinition fields for scene-definition-v3"):
        SceneDefinition.from_mapping(values)

    legacy = SceneDefinition("scene-definition-v1", "legacy", (_asset("legacy"),), (_entity("legacy", "legacy"),))
    legacy_mapping = legacy.to_mapping()
    legacy_mapping["robots"] = []
    with pytest.raises(ValueError, match="unknown SceneDefinition fields for scene-definition-v1"):
        SceneDefinition.from_mapping(legacy_mapping)

    scene_v2 = SceneDefinition(
        "scene-definition-v2", "v2", (_asset("robot/panda"),),
        (_entity("robot", "robot/panda"),),
        (_frame("robot", "base"),), (),
    )
    v2_mapping = scene_v2.to_mapping()
    v2_mapping["robots"] = []
    with pytest.raises(ValueError, match="unknown SceneDefinition fields for scene-definition-v2"):
        SceneDefinition.from_mapping(v2_mapping)

    with pytest.raises(ValueError, match="requires scene-definition-v3"):
        scene_v2.resolve_robot("robot")


def test_v3_static_artifact_path_does_not_load_provider_or_native_runtime(tmp_path):
    code = r'''
import sys
from task_env.artifacts import (
    ActuatorReference, ActuatorResourceDefinition, ArticulationDefinition,
    AssetDefinition, ControlGroup, EntityInstance, FrameDefinition,
    FrameReference, JointDefinition, PoseWorld, RobotInstance, SceneDefinition,
)
pose = PoseWorld((0,0,0), (1,0,0,0))
asset = AssetDefinition("asset-definition-v1", "robot", "v1", "procedural://test/robot")
entity = EntityInstance("entity-instance-v1", "robot", "robot", "v1")
frames = (
    FrameDefinition("frame-definition-v1", "robot", "base", "runtime", None, None),
    FrameDefinition("frame-definition-v1", "robot", "tool", "runtime", None, None),
)
joint = JointDefinition(
    "joint-definition-v1", "joint", FrameReference("robot", "base"),
    FrameReference("robot", "tool"), pose, pose, "revolute", (0,0,1),
    "radian", "radian_per_second", 1, 1,
)
articulation = ArticulationDefinition(
    "articulation-definition-v1", "robot", "base", ("base", "tool"), (joint,),
)
scene = SceneDefinition(
    "scene-definition-v3", "scene", (asset,), (entity,), frames, (articulation,),
    (RobotInstance("robot-instance-v1", "robot", (FrameReference("robot", "base"),)),),
    (ActuatorResourceDefinition("actuator-resource-v1", "robot", "arm"),),
    (ControlGroup("control-group-v1", "robot", "arm", (ActuatorReference("robot", "arm"),)),),
)
assert scene.resolve_actuator(ActuatorReference("robot", "arm")).actuator_id == "arm"
for name in sys.modules:
    assert name.split(".", 1)[0] not in {"mujoco", "geophys", "solvers", "scene", "visualization"}, name
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=dict(
            os.environ,
            PYTHONPATH=str(ROOT),
            PYTHONDONTWRITEBYTECODE="1",
        ),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
