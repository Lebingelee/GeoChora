"""D02b: typed state views from existing GeoPhys/MuJoCo RuntimeSessions."""

from __future__ import annotations

import copy
from dataclasses import replace

import numpy as np
import pytest

from task_env.artifacts import (
    ActionIntent,
    ArticulationDefinition,
    AssetDefinition,
    CanonicalStatePublicationV1,
    CanonicalStateView,
    EntityDefinition,
    EntityInstance,
    ExecutionSpec,
    FrameDefinition,
    FrameReference,
    InitializationContract,
    JointDefinition,
    PoseWorld,
    RequiredCapabilitySet,
    SceneDefinition,
    SemanticDefinition,
    StateFieldRequirement,
    StateRequirements,
    TaskArtifact,
    Timebase,
    TypedJointStateValue,
    UnavailableStateValue,
    WorldDefinition,
)
from task_env.assembly.source import TaskSceneSource
from task_env.artifacts.execution import ResetSample
from task_env.environment.configuration import resolve_env_config
from task_env.environment import ReferenceSpec, TaskCompositionSpec
from task_env.runtime.sessions.api import materialize, provider_manifest
from task_env.runtime.sessions.source import RuntimeSource
from task_env.recorders import TransitionRecorder


IDENTITY = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
ROTATED_START = (0.7071067811865476, 0.7071067811865476, 0.0, 0.0)
FREE_BODY_XML = """<mujoco model="d02b-free-body">
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="floor" type="plane" size="2 2 0.1"/>
    <body name="cube" pos="0 0 1" quat="0.7071067811865476 0.7071067811865476 0 0">
      <freejoint name="cube_free"/>
      <geom name="cube-collision" type="box" size="0.05 0.05 0.05" mass="1"/>
    </body>
  </worldbody>
</mujoco>"""


class _FreeBodyScene:
    uid = "d02b-free-body-scene"

    def reference_spec(self):
        return ReferenceSpec(body_names=("cube",), geom_names=("floor", "cube-collision"))


def _scene() -> tuple[SceneDefinition, JointDefinition]:
    joint = JointDefinition(
        "joint-definition-v1", "free_root",
        FrameReference("cube-v1", "anchor"), FrameReference("cube-v1", "root"),
        IDENTITY, IDENTITY, "floating", None,
        "xyz_meter_quaternion_wxyz",
        "linear_xyz_meter_per_second_angular_xyz_radian_per_second", 7, 6,
    )
    scene = SceneDefinition(
        "scene-definition-v2", "phase-ii-d02b-free-body-v2",
        (AssetDefinition("asset-definition-v1", "free-cube-v1", "v1",
                         "procedural://phase-ii-d02b/free-cube"),),
        (EntityInstance("entity-instance-v1", "cube-v1", "free-cube-v1", "v1"),),
        (
            FrameDefinition("frame-definition-v1", "cube-v1", "anchor", "runtime", None, None),
            FrameDefinition("frame-definition-v1", "cube-v1", "root", "runtime", None, None),
        ),
        (ArticulationDefinition(
            "articulation-definition-v1", "cube-v1", "anchor", ("anchor", "root"), (joint,),
        ),),
    )
    return scene, joint


def _artifact_and_sample() -> tuple[TaskArtifact, ResetSample]:
    initial_pose = PoseWorld((0.0, 0.0, 1.0), ROTATED_START)
    artifact = TaskArtifact(
        "task-artifact-v0", "phase-ii-d02b-free-body-v0", "phase-ii-d02b-free-body", "candidate-v0",
        WorldDefinition(
            "world-v0", "SI_right_handed_z_up_wxyz",
            (EntityDefinition(
                "cube-v1", "static", "procedural://phase-ii-d02b/free-cube@v1",
                ("cube-v1/root",), (), "source_asset", "source_retained", {},
            ),),
            ActionIntent("absolute_joint", None, "none", "arm_joint_position_and_gripper"),
            ("canonical-state-v0",), (),
        ),
        InitializationContract(
            "initialization-v0", {"cube-v1": initial_pose}, {}, (),
            "zero_named_joint_and_entity_velocities", "fixed-d02b-sample", 0,
        ),
        SemanticDefinition(
            "semantics-v0", "typed_state_projection_probe", ("cube-v1",), (), {},
            "D02b-state-only",
        ),
        Timebase(0.002, 1, 0.002),
        RequiredCapabilitySet(("rigid_body", "free_body", "body_pose_query")),
    )
    sample = ResetSample.create(
        schema_version="reset-sample-v0", task_artifact_hash=artifact.identity_hash,
        sampler_id="d02b-fixed-reset", sampler_version="v1", task_seed=7,
        joint_position={}, poses_world={"cube-v1": initial_pose},
        velocity_policy="zero_named_joint_and_entity_velocities",
        control_policy="arm_targets_at_initial_joints_gripper_open", settle_steps=0,
    )
    return artifact, sample


def _requirements(*, contact_requiredness="optional") -> StateRequirements:
    return StateRequirements(
        "state-requirements-v1", "task", "d02b-state-probe",
        (
            StateFieldRequirement(
                "state-field-requirement-v1", "joint_position", "joint", "cube-v1", "free_root",
                "required", "evaluation_boundary", "joint-definition", "joint_state_query",
            ),
            StateFieldRequirement(
                "state-field-requirement-v1", "joint_velocity", "joint", "cube-v1", "free_root",
                "required", "evaluation_boundary", "joint-definition", "joint_state_query",
            ),
            StateFieldRequirement(
                "state-field-requirement-v1", "frame_pose_world", "frame", "cube-v1", "root",
                "required", "evaluation_boundary", "meter+quaternion_wxyz", "frame_pose_query",
            ),
            StateFieldRequirement(
                "state-field-requirement-v1", "contact_force", "entity", "cube-v1", "contacts",
                contact_requiredness, "evaluation_boundary", "newton", "contact_detection",
                FrameReference("cube-v1", "root"),
            ),
        ),
    )


def _runtime(provider: str):
    scene, joint = _scene()
    artifact, sample = _artifact_and_sample()
    source_id = f"{scene.schema_version}:{scene.identity_hash}"
    source = RuntimeSource(
        artifact.identity_hash,
        TaskSceneSource(FREE_BODY_XML, None, source_id),
        joints={}, bodies={"cube-v1": "cube"}, frames={},
        free_joints={"cube-v1": "cube_free"}, joint_targets={}, open_actuators=(),
        composition=TaskCompositionSpec("phase-ii-d02b-free-body", "phase-ii-d02b-free-body"),
        config=resolve_env_config(
            task_uid="phase-ii-d02b-free-body", scene_uid="phase-ii-d02b-free-body",
            runtime={"backend": "cpu", "physics_dt": 0.002, "control_substeps": 1, "prewarm": False},
            render={"camera_obs": False},
        ),
        scene=_FreeBodyScene(), agents=(), objects=(),
    )
    return scene, joint, artifact, sample, source


@pytest.mark.parametrize("provider", ("mujoco", "geophys"))
def test_free_joint_runtime_projection_preserves_v0_and_owned_v1_lifetime(provider):
    scene, joint, artifact, sample, source = _runtime(provider)
    session = materialize(
        artifact,
        ExecutionSpec(provider, "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict"),
        source=source,
    )
    try:
        realized = session.reset(sample)
        assert isinstance(realized.measured_state, CanonicalStateView)
        reqs = _requirements()
        publication0 = session.snapshot_v1(
            scene=scene,
            joint_bindings={"cube-v1": joint},
            frame_bindings={"cube-v1": FrameReference("cube-v1", "root")},
            requirements=reqs,
        )
        publication0_other_consumer = session.snapshot_v1(
            scene=scene,
            joint_bindings={"cube-v1": joint},
            frame_bindings={"cube-v1": FrameReference("cube-v1", "root")},
            requirements=reqs,
        )
        assert publication0_other_consumer.view.boundary == publication0.view.boundary
        assert publication0_other_consumer.view.to_mapping() == publication0.view.to_mapping()
        assert CanonicalStatePublicationV1.from_mapping(publication0.to_mapping()) == publication0
        value0 = publication0.view.joints_for_entity("cube-v1")[0]
        assert isinstance(value0, TypedJointStateValue)
        assert value0.kind == "floating"
        assert len(value0.position) == 7 and len(value0.velocity) == 6
        assert value0.velocity_expressed_in == FrameReference("cube-v1", "root")
        assert value0.velocity_reference_point == FrameReference("cube-v1", "root")
        assert np.allclose(value0.position[:3], sample.poses_world["cube-v1"].position)
        assert np.allclose(value0.position[3:], sample.poses_world["cube-v1"].quaternion_wxyz)
        assert np.allclose(value0.velocity, np.zeros(6), atol=1.0e-7)
        assert publication0.view.sample_clock.sample_index == 0
        assert publication0.view.sample_clock.simulation_time_s == 0.0
        assert publication0.lifetime.may_be_retained
        assert publication0.lifetime.owner_id == publication0.view.boundary.provider_materialization_id
        assert publication0.view.joints_for_entity("cube-v1")[0] is publication0.view.joints[0]
        assert publication0.view.frames_for_entity("cube-v1")[0] is publication0.view.frames[0]
        unavailable = next(item for item in publication0.view.unavailable if item.field_name == "contact_force")
        assert isinstance(unavailable, UnavailableStateValue)
        assert "does not publish contact_force" in unavailable.reason
        assert "contact_detection" not in {claim.name for claim in provider_manifest(provider).capabilities}

        saved_view = publication0.view.to_mapping()
        expected_recorded_state = copy.deepcopy(saved_view)
        recorder = TransitionRecorder()
        initial_observation = {"typed_state": saved_view}
        recorder.begin_episode(initial_observation, {}, {})
        recorder.append_transition(
            np.zeros(1, dtype=np.float32), np.zeros(1, dtype=np.float32),
            initial_observation, 0.0, False, False, False, {},
        )
        trajectory = recorder.end_episode("D02b owned state storage probe")
        initial_observation["typed_state"]["joints"][0]["position"][0] = 99.0
        assert trajectory.observations[0]["typed_state"] == expected_recorded_state

        legacy_after_reset = session.step()
        assert isinstance(legacy_after_reset, CanonicalStateView)
        assert legacy_after_reset.schema_version == "canonical-state-v0"
        publication1 = session.snapshot_v1(
            scene=scene,
            joint_bindings={"cube-v1": joint},
            frame_bindings={"cube-v1": FrameReference("cube-v1", "root")},
            requirements=reqs,
        )
        value1 = publication1.view.joints[0]
        assert publication1.view.boundary.control_step == 1
        assert publication1.view.sample_clock.simulation_time_s == pytest.approx(0.002)
        assert publication1.view.boundary.state_revision == publication0.view.boundary.state_revision + 1
        assert publication1.view.boundary.episode_id == publication0.view.boundary.episode_id
        assert np.allclose(value1.velocity[:3], (0.0, -9.81 * 0.002, 0.0), atol=2.0e-5)
        assert np.allclose(value1.velocity[3:], (0.0, 0.0, 0.0), atol=2.0e-5)

        with pytest.raises(ValueError, match="required state field unavailable"):
            session.snapshot_v1(
                scene=scene,
                joint_bindings={"cube-v1": joint},
                frame_bindings={"cube-v1": FrameReference("cube-v1", "root")},
                requirements=_requirements(contact_requiredness="required"),
            )
        with pytest.raises(ValueError, match="native interval requirement is not supported"):
            native = StateRequirements(
                "state-requirements-v1", "task", "d02b-native-guard",
                (replace(reqs.requirements[-1], sample_domain="native_step_interval"),),
            )
            session.snapshot_v1(
                scene=scene,
                joint_bindings={"cube-v1": joint},
                frame_bindings={"cube-v1": FrameReference("cube-v1", "root")},
                requirements=native,
            )

        changed_scene = SceneDefinition.from_mapping({
            **scene.to_mapping(),
            "assets": [{**scene.assets[0].to_mapping(), "source_revision": "changed"}],
        })
        with pytest.raises(ValueError, match="exact typed state Scene identity"):
            session.snapshot_v1(
                scene=changed_scene,
                joint_bindings={"cube-v1": joint},
                frame_bindings={"cube-v1": FrameReference("cube-v1", "root")},
                requirements=reqs,
            )
        episode0 = publication0.view.boundary.episode_id
        session.reset(sample)
        publication_after_reset = session.snapshot_v1(
            scene=scene,
            joint_bindings={"cube-v1": joint},
            frame_bindings={"cube-v1": FrameReference("cube-v1", "root")},
            requirements=reqs,
        )
        assert publication_after_reset.view.boundary.episode_id != episode0
        assert publication_after_reset.view.boundary.reset_sample_id == sample.sample_id
        assert publication_after_reset.view.boundary.state_revision == 0
    finally:
        session.close()
    # The value publication owns tuple data; provider teardown cannot invalidate it.
    assert publication0.view.to_mapping() == expected_recorded_state
