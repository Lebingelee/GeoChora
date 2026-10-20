"""B02: deterministic Role selection and ResetSample-v0 rollout gate."""

from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from task_env.artifacts import (
    ActionIntent,
    ArticulationDefinition,
    AssetDefinition,
    EntityDefinition,
    EntityInstance,
    ExecutionSpec,
    FrameDefinition,
    FrameReference,
    InitializationContract,
    JointDefinition,
    PoseWorld,
    RequiredCapabilitySet,
    RobotInstance,
    SceneDefinition,
    SemanticDefinition,
    TaskArtifact,
    Timebase,
    UniformDimension,
    WorldDefinition,
)
from task_env.artifacts.execution import EpisodeResetPlanV1
from task_env.assembly.source import TaskSceneSource
from task_env.environment import (
    ReferenceSpec,
    TaskCompositionSpec,
    TaskInitializationV1,
    TaskRoleDeclarationV1,
    TaskSourceV1,
    adapt_legacy_recipe_task_source,
    resolve_role_binding,
    sample_episode_reset_plan,
)
from task_env.environment.configuration import resolve_env_config
from task_env.environment.configuration import load_yaml_mapping
from task_env.runtime.sessions.api import materialize
from task_env.runtime.sessions import common as session_common
from task_env.runtime.sessions.common import validate_reset_plan_realization
from task_env.runtime.sessions.source import RuntimeSource


IDENTITY = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
BASE_POSITIONS = {
    "block-a": PoseWorld((0.30, 0.0, 0.10), (1.0, 0.0, 0.0, 0.0)),
    "block-b": PoseWorld((0.50, 0.0, 0.10), (1.0, 0.0, 0.0, 0.0)),
    "block-c": PoseWorld((0.70, 0.0, 0.10), (1.0, 0.0, 0.0, 0.0)),
}
FREE_BODY_XML = """<mujoco model="b02-three-free-bodies">
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="floor" type="plane" size="2 2 0.1"/>
    <body name="block_a" pos="0.30 0 0.10">
      <freejoint name="block_a_free"/>
      <geom name="block_a_geom" type="box" size="0.05 0.05 0.05" mass="1"/>
    </body>
    <body name="block_b" pos="0.50 0 0.10">
      <freejoint name="block_b_free"/>
      <geom name="block_b_geom" type="box" size="0.05 0.05 0.05" mass="1"/>
    </body>
    <body name="block_c" pos="0.70 0 0.10">
      <freejoint name="block_c_free"/>
      <geom name="block_c_geom" type="box" size="0.05 0.05 0.05" mass="1"/>
    </body>
  </worldbody>
</mujoco>"""


class _ThreeFreeBodyScene:
    uid = "phase-ii-b02-three-free-bodies"

    def reference_spec(self):
        return ReferenceSpec(
            body_names=("block_a", "block_b", "block_c"),
            geom_names=("floor", "block_a_geom", "block_b_geom", "block_c_geom"),
        )


def _scene() -> SceneDefinition:
    asset = AssetDefinition(
        "asset-definition-v1", "free-cube-v1", "v1", "procedural://phase-ii-b02/free-cube",
    )
    entities = tuple(
        EntityInstance("entity-instance-v1", entity_id, asset.asset_id, asset.asset_version)
        for entity_id in BASE_POSITIONS
    )
    frames = []
    articulations = []
    for entity_id in BASE_POSITIONS:
        anchor = f"{entity_id}-anchor"
        root = f"{entity_id}-root"
        frames.extend((
            FrameDefinition("frame-definition-v1", entity_id, anchor, "runtime", None, None),
            FrameDefinition("frame-definition-v1", entity_id, root, "runtime", None, None),
        ))
        articulations.append(ArticulationDefinition(
            "articulation-definition-v1", entity_id, anchor, (anchor, root), (
                JointDefinition(
                    "joint-definition-v1", f"{entity_id}-free",
                    FrameReference(entity_id, anchor), FrameReference(entity_id, root),
                    IDENTITY, IDENTITY, "floating", None,
                    "xyz_meter_quaternion_wxyz",
                    "linear_xyz_meter_per_second_angular_xyz_radian_per_second", 7, 6,
                ),
            ),
        ))
    return SceneDefinition(
        "scene-definition-v2", "phase-ii-b02-three-free-bodies-v1",
        (asset,), entities, tuple(frames), tuple(articulations),
    )


def _artifact(*, include_y_dimension: bool = False, settle_steps: int = 0) -> TaskArtifact:
    dimensions = [
        UniformDimension(
            "target_block.position_world.x", (0.2, 0.8), (0.25, 0.75),
            (0.3, 0.7), (0.35, 0.65),
        ),
    ]
    if include_y_dimension:
        dimensions.append(UniformDimension(
            "target_block.position_world.y", (-0.4, 0.4), (-0.3, 0.3),
            (-0.2, 0.2), (-0.1, 0.1),
        ))
    dimension_names = tuple(item.name for item in dimensions)
    entity_definitions = []
    for entity_id in BASE_POSITIONS:
        entity_definitions.append(EntityDefinition(
            entity_id, "movable", "procedural://phase-ii-b02/free-cube@v1",
            (f"{entity_id}/{entity_id}-anchor", f"{entity_id}/{entity_id}-root"),
            (f"{entity_id}/{entity_id}-free",), "free_box", "retained", {},
        ))
    return TaskArtifact(
        "task-artifact-v0", "phase-ii-b02-reset-probe-v0", "phase-ii-b02-reset-probe", "candidate-v0",
        WorldDefinition(
            "world-v0", "SI_right_handed_z_up_wxyz",
            tuple(entity_definitions),
            ActionIntent("absolute_joint", None, "none", "arm_joint_position_and_gripper"),
            ("canonical-state-v0",), dimension_names,
        ),
        InitializationContract(
            "initialization-v0", BASE_POSITIONS, {}, tuple(dimensions),
            "zero_named_joint_and_entity_velocities", "fixed-b02-probe", settle_steps,
        ),
        SemanticDefinition(
            "semantics-v0", "b02_reset_probe", tuple(BASE_POSITIONS), (), {}, "b02-reset-only",
        ),
        Timebase(0.002, 1, 0.002),
        RequiredCapabilitySet(("rigid_body", "free_body", "body_pose_query")),
    )


def _source(*, candidates=("block-a", "block-b"), with_background_role=False, sampler_version="pcg64-domain-v1"):
    roles = [TaskRoleDeclarationV1(
        "target_block", "rigid_body", "ids", tuple(candidates), "exactly_one",
    )]
    if with_background_role:
        roles.append(TaskRoleDeclarationV1(
            "background_block", "rigid_body", "ids", ("block-c",), "exactly_one",
        ))
    return TaskSourceV1(
        "phase-ii-b02-reset-probe", "candidate-v0", "phase-ii-b02-three-free-bodies-v1",
        tuple(roles),
        TaskInitializationV1(
            "phase-ii-b02-uniform", sampler_version, "training",
            "zero_named_joint_and_entity_velocities", "arm_targets_at_initial_joints_gripper_open",
        ),
    )


def _runtime_source(scene: SceneDefinition, artifact: TaskArtifact) -> RuntimeSource:
    config = resolve_env_config(
        task_uid="phase-ii-b02-three-free-bodies", scene_uid="phase-ii-b02-three-free-bodies",
        runtime={"backend": "cpu", "physics_dt": 0.002, "control_substeps": 1, "prewarm": False},
        render={"camera_obs": False},
    )
    return RuntimeSource(
        artifact.identity_hash,
        TaskSceneSource(FREE_BODY_XML, None, f"{scene.schema_version}:{scene.identity_hash}"),
        joints={},
        bodies={"block-a": "block_a", "block-b": "block_b", "block-c": "block_c"},
        frames={},
        free_joints={
            "block-a": "block_a_free", "block-b": "block_b_free", "block-c": "block_c_free",
        },
        joint_targets={}, open_actuators=(),
        composition=TaskCompositionSpec("phase-ii-b02-three-free-bodies", "phase-ii-b02-three-free-bodies"),
        config=config, scene=_ThreeFreeBodyScene(), agents=(), objects=(),
    )


def _structured_scene_projection(artifact: TaskArtifact, scene_id: str) -> SceneDefinition:
    """Build a structural A Scene projection for legacy sample compatibility checks."""
    assets = []
    entities = []
    frames = []
    articulations = []
    robots = []
    for entity in artifact.world.entities:
        asset_id = f"asset-{entity.semantic_id}"
        assets.append(AssetDefinition(
            "asset-definition-v1", asset_id, "legacy-v0",
            f"legacy-task-artifact://{artifact.task_id}/{entity.semantic_id}",
        ))
        entities.append(EntityInstance(
            "entity-instance-v1", entity.semantic_id, asset_id, "legacy-v0",
        ))
        local_frames = {
            name.split("/", 1)[1] if name.startswith(f"{entity.semantic_id}/") else name
            for name in entity.frames
        }
        joint_ids = tuple(sorted(
            name.split("/", 1)[1] if name.startswith(f"{entity.semantic_id}/") else name
            for name in entity.joints
        ))
        if not local_frames and not joint_ids:
            continue

        if joint_ids:
            root = "base" if "base" in local_frames else "root"
            local_frames.add(root)
            children = []
            current_parent = root
            joint_definitions = []
            for index, joint_id in enumerate(joint_ids):
                child = "ee" if index == len(joint_ids) - 1 and "ee" in local_frames else f"link_{index}"
                local_frames.add(child)
                children.append(child)
                joint_definitions.append(JointDefinition(
                    "joint-definition-v1", joint_id,
                    FrameReference(entity.semantic_id, current_parent),
                    FrameReference(entity.semantic_id, child), IDENTITY, IDENTITY,
                    "revolute", (0.0, 0.0, 1.0), "radian", "radian_per_second", 1, 1,
                ))
                current_parent = child
            for frame_id in sorted(local_frames):
                frames.append(FrameDefinition(
                    "frame-definition-v1", entity.semantic_id, frame_id, "runtime", None, None,
                ))
            articulations.append(ArticulationDefinition(
                "articulation-definition-v1", entity.semantic_id, root,
                (root, *children), tuple(joint_definitions),
            ))
            if entity.kind == "embodiment":
                robots.append(RobotInstance(
                    "robot-instance-v1", entity.semantic_id,
                    (FrameReference(entity.semantic_id, root),),
                ))
        else:
            for frame_id in sorted(local_frames):
                frames.append(FrameDefinition(
                    "frame-definition-v1", entity.semantic_id, frame_id,
                    "authored_fixed", None, IDENTITY,
                ))

    return SceneDefinition(
        "scene-definition-v3", scene_id, tuple(assets), tuple(entities),
        tuple(frames), tuple(articulations), tuple(robots), (), (),
    )


def test_role_binding_is_stable_for_candidate_order_and_independent_of_unrelated_roles():
    scene = _scene()
    artifact = _artifact()
    source = _source()
    with pytest.raises(TypeError, match="artifact"):
        resolve_role_binding(source, scene, task_seed=31)
    reordered = _source(candidates=("block-b", "block-a"))
    assert source.identity_hash == reordered.identity_hash

    first = resolve_role_binding(source, scene, task_seed=31, artifact=artifact)
    second = resolve_role_binding(reordered, scene, task_seed=31, artifact=artifact)
    assert first == second

    with_background = _source(with_background_role=True)
    expanded = resolve_role_binding(with_background, scene, task_seed=31, artifact=artifact)
    assert expanded.bindings["target_block"] == first.bindings["target_block"]
    assert expanded.bindings["background_block"] == "block-c"

    # Legacy TaskArtifact asset references remain Artifact-owned; B02 checks
    # entity/topology correspondence without conflating AssetDeclaration identity.
    legacy_asset_reference = replace(
        artifact,
        world=replace(
            artifact.world,
            entities=tuple(
                replace(entity, asset_reference="legacy://pick-cube/cube-v1")
                if entity.semantic_id == "block-a" else entity
                for entity in artifact.world.entities
            ),
        ),
    )
    assert resolve_role_binding(source, scene, task_seed=31, artifact=legacy_asset_reference) == first


def test_reset_plan_uses_artifact_bounds_role_aliases_and_independent_rng_domains():
    scene = _scene()
    source = _source()
    task_seed = 47
    plan = sample_episode_reset_plan(source, scene, _artifact(), task_seed=task_seed)
    same = sample_episode_reset_plan(source, scene, _artifact(), task_seed=task_seed)
    expanded = sample_episode_reset_plan(
        source, scene, _artifact(include_y_dimension=True), task_seed=task_seed,
    )

    assert isinstance(plan, EpisodeResetPlanV1)
    assert plan == same
    assert plan.reset_sample.schema_version == "reset-sample-v0"
    assert plan.to_provider_sample() is plan.reset_sample
    selected = plan.role_binding.bindings["target_block"]
    x_name = "target_block.position_world.x"
    x_value = plan.reset_sample.poses_world[selected].position[0]
    assert 0.25 <= x_value <= 0.75
    assert x_value == expanded.reset_sample.poses_world[selected].position[0]
    assert plan.reset_sample.poses_world["block-c"] == BASE_POSITIONS["block-c"]

    role_added = sample_episode_reset_plan(
        _source(with_background_role=True), scene, _artifact(), task_seed=task_seed,
    )
    assert role_added.reset_sample.poses_world[selected].position[0] == x_value
    assert plan.reset_sample.sample_id.startswith("reset-")
    assert plan.reset_sample.task_artifact_hash == _artifact().identity_hash
    assert x_name in {dimension.name for dimension in _artifact().initialization.randomization}


@pytest.mark.parametrize("task_name", ("pick_cube", "nut_assembly"))
def test_legacy_task_factories_keep_their_exact_reset_sample_v0(task_name):
    if task_name == "pick_cube":
        from task_env.tasks.pick_cube import task as task_module
        task_dir = "pick_cube"
        task_seed = 31
    else:
        from task_env.tasks.nut_assembly import task as task_module
        task_dir = "nut_assembly"
        task_seed = 19

    task_root = Path(__file__).resolve().parents[3] / "task_env" / "tasks" / task_dir
    legacy_config = load_yaml_mapping(task_root / "config.yaml")
    source = adapt_legacy_recipe_task_source(legacy_config)
    artifact = task_module.build_artifact()
    scene = _structured_scene_projection(artifact, source.scene_ref)

    plan = sample_episode_reset_plan(source, scene, artifact, task_seed=task_seed)
    legacy_sample = task_module.sample_reset(artifact, task_seed)
    assert plan.to_provider_sample() == legacy_sample
    assert plan.reset_sample.schema_version == legacy_sample.schema_version == "reset-sample-v0"


def test_role_and_reset_planning_fail_closed_on_identity_overlap_topology_and_settle():
    scene = _scene()
    artifact = _artifact()
    source = _source()

    with pytest.raises(ValueError, match="Scene reference"):
        resolve_role_binding(replace(source, scene_ref="different-scene"), scene, task_seed=1, artifact=artifact)

    with pytest.raises(ValueError, match="TaskArtifact identity"):
        resolve_role_binding(source, scene, task_seed=1, artifact=replace(artifact, artifact_version="other-v0"))

    overlapping = TaskSourceV1(
        source.task_id, source.version, source.scene_ref,
        source.roles + (TaskRoleDeclarationV1(
            "second_target", "rigid_body", "ids", ("block-a",), "exactly_one",
        ),),
        source.initialization,
    )
    with pytest.raises(ValueError, match="overlapping candidates"):
        resolve_role_binding(overlapping, scene, task_seed=1, artifact=artifact)

    changed_topology = deepcopy(scene.to_mapping())
    for frame in changed_topology["frames"]:
        if frame["entity_id"] == "block-a" and frame["frame_id"] == "block-a-root":
            frame["frame_id"] = "block-a-tip"
    for articulation in changed_topology["articulations"]:
        if articulation["entity_id"] == "block-a":
            articulation["link_frame_ids"] = ["block-a-anchor", "block-a-tip"]
            articulation["joints"][0]["child_frame"]["frame_id"] = "block-a-tip"
    changed_topology_scene = SceneDefinition.from_mapping(changed_topology)
    with pytest.raises(ValueError, match="Scene/TaskArtifact topology mismatch"):
        resolve_role_binding(source, changed_topology_scene, task_seed=1, artifact=artifact)

    missing_artifact_entity = _artifact()
    missing_artifact_entity = replace(
        missing_artifact_entity,
        world=replace(
            missing_artifact_entity.world,
            entities=tuple(entity for entity in missing_artifact_entity.world.entities if entity.semantic_id != "block-b"),
        ),
        initialization=replace(
            missing_artifact_entity.initialization,
            poses_world={key: value for key, value in missing_artifact_entity.initialization.poses_world.items()
                         if key != "block-b"},
        ),
        semantics=replace(
            missing_artifact_entity.semantics,
            required_poses=tuple(name for name in missing_artifact_entity.semantics.required_poses if name != "block-b"),
        ),
    )
    with pytest.raises(ValueError, match="unresolved candidates"):
        resolve_role_binding(source, scene, task_seed=1, artifact=missing_artifact_entity)

    # The unselected block-c still belongs to the TaskArtifact reset/semantic
    # contract and must be present in the canonical Scene topology.
    missing_scene = deepcopy(scene.to_mapping())
    missing_scene["entities"] = [
        entity for entity in missing_scene["entities"] if entity["entity_id"] != "block-c"
    ]
    missing_scene["frames"] = [
        frame for frame in missing_scene["frames"] if frame["entity_id"] != "block-c"
    ]
    missing_scene["articulations"] = [
        articulation for articulation in missing_scene["articulations"]
        if articulation["entity_id"] != "block-c"
    ]
    with pytest.raises(ValueError, match="TaskArtifact Entities are absent from canonical Scene"):
        resolve_role_binding(
            source, SceneDefinition.from_mapping(missing_scene), task_seed=1, artifact=artifact,
        )

    scene_kind_artifact = replace(
        artifact,
        world=replace(
            artifact.world,
            entities=tuple(
                replace(entity, kind="scene") if entity.semantic_id == "block-a" else entity
                for entity in artifact.world.entities
            ),
        ),
    )
    with pytest.raises(ValueError, match="not a rigid-body TaskArtifact Entity"):
        resolve_role_binding(source, scene, task_seed=1, artifact=scene_kind_artifact)

    with pytest.raises(ValueError, match="nonzero settle_steps"):
        sample_episode_reset_plan(source, scene, _artifact(settle_steps=1), task_seed=1)


@pytest.mark.parametrize("provider", ("mujoco", "geophys"))
def test_real_provider_reset_plan_is_verified_before_first_rollout_step(provider, monkeypatch):
    scene = _scene()
    artifact = _artifact()
    source = _source()
    plan = sample_episode_reset_plan(source, scene, artifact, task_seed=53)
    runtime_source = _runtime_source(scene, artifact)
    session = materialize(
        artifact,
        ExecutionSpec(provider, "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict"),
        source=runtime_source,
    )
    try:
        wrong_scene_plan = replace(
            plan,
            role_binding=replace(plan.role_binding, scene_identity_hash="0" * 64),
        )
        with pytest.raises(ValueError, match="Scene identity differs"):
            session.reset_plan(wrong_scene_plan)
        with pytest.raises(RuntimeError, match="reset required"):
            session.step()

        def reject_realization_gate(*_args, **_kwargs):
            raise ValueError("injected realization rejection")

        with monkeypatch.context() as patcher:
            patcher.setattr(session_common, "validate_reset_plan_realization", reject_realization_gate)
            with pytest.raises(ValueError, match="injected realization rejection"):
                session.reset_plan(plan)
            with pytest.raises(RuntimeError, match="ResetPlan realization gate"):
                session.step()

        realized = session.reset_plan(plan)
        evidence = session.reset_plan_evidence
        assert evidence is not None
        assert evidence["episode_reset_plan_identity_hash"] == plan.identity_hash
        assert evidence["role_bindings"] == dict(plan.role_binding.bindings)
        assert evidence["joint_max_abs_error"] == 0.0
        assert evidence["pose_position_max_abs_error"] < 1.0e-6
        assert evidence["pose_orientation_max_error"] < 1.0e-6
        selected = plan.role_binding.bindings["target_block"]
        assert np.allclose(
            realized.measured_state.pose_world[selected].position,
            plan.reset_sample.poses_world[selected].position,
            atol=1.0e-6,
        )
        assert np.allclose(
            realized.measured_state.pose_world["block-c"].position,
            BASE_POSITIONS["block-c"].position,
            atol=1.0e-6,
        )

        wrong_plan = sample_episode_reset_plan(source, scene, artifact, task_seed=54)
        with pytest.raises(ValueError, match="does not belong"):
            validate_reset_plan_realization(wrong_plan, realized)

        selected_pose = realized.measured_state.pose_world[selected]
        bad_pose = replace(
            selected_pose,
            position=(selected_pose.position[0] + 1.0e-2, *selected_pose.position[1:]),
        )
        bad_state = replace(
            realized.measured_state,
            pose_world={**realized.measured_state.pose_world, selected: bad_pose},
        )
        bad_realization = replace(realized, measured_state=bad_state)
        with pytest.raises(ValueError, match="pose position realization exceeds tolerance"):
            validate_reset_plan_realization(plan, bad_realization)
        assert session.snapshot().control_step == 0
        assert session.step().control_step == 1
    finally:
        session.close()
