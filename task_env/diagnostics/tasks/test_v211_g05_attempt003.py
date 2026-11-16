"""Attempt003 camera and selected non-Position production-lifecycle contracts."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import hashlib
import json

import numpy as np
import pytest

from task_env.artifacts import (
    ActionIntent,
    ArticulationDefinition,
    AssetDefinition,
    CanonicalStatePublicationV1,
    CanonicalStateViewV1,
    EntityDefinition,
    EntityInstance,
    FrameDefinition,
    FrameReference,
    InitializationContract,
    JointDefinition,
    JointReference,
    PoseWorld,
    RequiredCapabilitySet,
    SceneDefinition,
    StateBoundaryIdentity,
    StateSampleClock,
    StateViewLifetime,
    TaskArtifactV1,
    SemanticDefinition,
    Timebase,
    TypedFrameStateValue,
    TypedJointStateValue,
)
from task_env.environment import CameraRendererReadbackV1, CameraSpec, RuntimeSnapshot, TaskEvaluation
from task_env.environment.gym_compat import Box, Dict
from task_env.environment.reference_binding import ReferenceTaskBinding
from task_env.environment.reference_env import SelectedReferenceEnv
from task_env.environment.task_source import compile_declared_artifact_v1
from task_env.environment.task_source import TaskSourceV1
from task_env.assembly.source import TaskSceneSource
from task_env.observations.camera import CameraSensor
from task_env.observations.canonical_camera import CameraGeometry, CanonicalCameraObservation, resolve_camera
from task_env.observations.canonical_camera.contracts import IDENTITY
from task_env.observations.capture import CameraObservationProvider
from task_env.render.camera.source import CameraCaptureIdentityV1
from task_env.runtime.sessions.control import ControlBinding
from task_env.runtime.sessions.source import ExecutionSourceReceiptV1, RuntimeSource


def _controlled_source(tmp_path):
    entity_id = "controlled-body"
    base = FrameReference(entity_id, "base")
    link = FrameReference(entity_id, "link")
    joint = JointDefinition(
        "joint-definition-v1", "hinge", base, link, PoseWorld((0., 0., 0.), (1., 0., 0., 0.)),
        PoseWorld((0., 0., 0.), (1., 0., 0., 0.)), "revolute", (0., 0., 1.),
        "radian", "radian_per_second", 1, 1,
    )
    scene = SceneDefinition(
        "scene-definition-v3", "controlled-scene-v1",
        (AssetDefinition("asset-definition-v1", "controlled-hinge", "v1", "procedural://test/hinge"),),
        (EntityInstance("entity-instance-v1", entity_id, "controlled-hinge", "v1"),),
        (
            FrameDefinition("frame-definition-v1", entity_id, "base", "runtime", None, None),
            FrameDefinition("frame-definition-v1", entity_id, "link", "runtime", None, None),
        ),
        (ArticulationDefinition("articulation-definition-v1", entity_id, "base", ("base", "link"), (joint,)),),
        (), (), (),
    )
    task_source = TaskSourceV1.from_mapping({
        "schema_version": "task-source-v1",
        "identity": {"task_id": "controlled-nonposition", "version": "v1"},
        "scene": {"ref": scene.scene_id},
        "roles": {},
        "hooks": [],
    })
    legacy_entity = EntityDefinition(
        entity_id, "movable", "procedural://test/hinge", (f"{entity_id}/base", f"{entity_id}/link"),
        (f"{entity_id}/hinge",), "hinge-link", "test-only", {},
    )
    artifact = compile_declared_artifact_v1(
        task_source, scene,
        artifact_id="controlled-artifact-v1", task_id=task_source.task_id, version=task_source.version,
        entities=(legacy_entity,), action=ActionIntent("absolute_joint", None, "none", "arm_joint_position_and_gripper"),
        observations=("state",),
        initialization=InitializationContract("initialization-v0", {}, {f"{entity_id}/hinge": 0.}, (),
                                              "preserve", "finite", 0),
        semantics=SemanticDefinition("semantics-v0", "controlled-state-v1", (f"{entity_id}/link",),
                                     (f"{entity_id}/hinge",), {}, "controlled-success-v1"),
        timebase=Timebase(.01, 1, .01), capabilities=(),
    )
    scene_source_id = f"{scene.schema_version}:{scene.identity_hash}"
    xml = b'<mujoco model="controlled_hinge"><worldbody><body name="link"><joint name="hinge"/></body></worldbody></mujoco>'
    receipt = ExecutionSourceReceiptV1.create(
        source_id=scene_source_id, canonical_xml=xml, importer_xml=xml,
        closure_files={"canonical-source.xml": xml},
    )
    source = RuntimeSource(
        task_artifact_hash=artifact.identity_hash,
        scene_source=TaskSceneSource(xml.decode(), Path(tmp_path), scene_source_id),
        joints={f"{entity_id}/hinge": "hinge"},
        bodies={f"{entity_id}/link": "link"}, frames={f"{entity_id}/base": "world"},
        free_joints={}, joint_targets={}, open_actuators=(), composition=None, config=None,
        scene=None, agents=(), objects=(), scene_definition=scene,
        source_closure_digest=receipt.source_closure_digest,
    )
    return artifact, source, receipt


class _ControlledRuntime:
    """Contract Runtime whose readback changes at each public control boundary."""

    def __init__(self, artifact, source, *, foreign_publication=False):
        self.artifact, self.source = artifact, source
        self.foreign_publication = foreign_publication
        self.provider_materialization_id = f"materialization-{uuid4().hex}"
        self.episode_id = f"episode-{uuid4().hex}"
        self.scene_instance_id = f"scene-instance-{uuid4().hex}"
        self.reset_sample_id = None
        self.control_step = 0
        self.state_revision = 0
        self.simulation_time = 0.0
        self.position = 0.0
        self.closed = False

    def reset(self, sample):
        self.reset_sample_id = sample.sample_id
        self.control_step = self.state_revision = 0
        self.simulation_time = self.position = 0.0
        return self.snapshot()

    def snapshot(self):
        return RuntimeSnapshot(
            qpos=np.asarray((self.position,), dtype=np.float64),
            qvel=np.asarray((0.5,), dtype=np.float64),
            ctrl=np.asarray((0.0,), dtype=np.float64),
            simulation_time=self.simulation_time,
        )

    def state_boundary_identity(self):
        return StateBoundaryIdentity(
            "state-boundary-identity-v1", self.episode_id, self.reset_sample_id,
            self.source.scene_definition.identity_hash, self.scene_instance_id,
            self.provider_materialization_id, self.control_step, self.state_revision,
        )

    def snapshot_v1(self, *, scene, joint_bindings, frame_bindings, requirements):
        assert scene.identity_hash == self.source.scene_definition.identity_hash
        assert set(joint_bindings) == set(self.source.joints)
        assert set(frame_bindings) == {*self.source.bodies, *self.source.frames}
        requirements.validate()
        boundary = self.state_boundary_identity()
        clock = StateSampleClock("state-sample-clock-v1", "evaluation_boundary", self.control_step,
                                 self.simulation_time)
        definition = next(iter(joint_bindings.values()))
        angle = self.position
        joints = (TypedJointStateValue(
            "typed-joint-state-v1", definition.parent_frame.entity_id, definition.joint_id,
            definition.kind, definition.position_representation, (angle,),
            definition.velocity_representation, (0.5,),
        ),)
        frames = tuple(
            TypedFrameStateValue(
                "typed-frame-state-v1", reference,
                PoseWorld((0., 0., 0.), (float(np.cos(angle / 2)), 0., 0., float(np.sin(angle / 2))))
                if reference.frame_id == "link" else PoseWorld((0., 0., 0.), (1., 0., 0., 0.)),
            )
            for reference in frame_bindings.values()
        )
        view = CanonicalStateViewV1(
            "canonical-state-v1", "SI_right_handed_z_up_wxyz", boundary, clock, joints, frames,
        )
        view.validate_against_scene(scene)
        view.validate_requirements(requirements)
        lifetime = StateViewLifetime(
            "state-view-lifetime-v1", self.provider_materialization_id, boundary,
            self.state_revision, "owned_snapshot", "retained",
        )
        if self.foreign_publication:
            foreign_boundary = replace(boundary, episode_id="foreign-episode")
            view = replace(view, boundary=foreign_boundary)
            lifetime = replace(lifetime, boundary=foreign_boundary)
        return CanonicalStatePublicationV1("canonical-state-publication-v1", view, lifetime)

    def control_feedback(self, _state):
        return {"control_step": self.control_step}

    def apply_control(self, _target):
        return None

    def step(self):
        self.control_step += 1
        self.state_revision += 1
        self.position += .5
        self.simulation_time += .01
        return self.snapshot()

    def close(self):
        self.closed = True


class _ControlledController:
    identity = "controlled-nonposition-controller-v1"

    def reset(self, _state, _feedback):
        return None

    def compute(self, _state, _feedback, _request):
        return None, None

    def readiness(self, state, _feedback):
        from task_env.controllers.canonical.readiness import CanonicalControlReadiness, GripperReadiness
        control_step = int(_feedback["control_step"])
        return CanonicalControlReadiness(
            "canonical-control-readiness-v1", control_step, state.simulation_time,
            GripperReadiness("controlled-gripper", True, 0., 1., 1.),
        )


def _controlled_binding(artifact, source, receipt):
    from task_env.artifacts.execution import ResetSample
    from task_env.controllers.canonical.contracts import RequestedAction

    controller = _ControlledController()
    value = {
        "artifact": artifact, "source": source, "controller": controller,
        "solution": None, "solution_identity": "controlled-solution-v1",
        "construction_id": "controlled-construction-v1",
    }

    def sample(actual_artifact, seed):
        return ResetSample.create(
            schema_version="reset-sample-v0", task_artifact_hash=actual_artifact.identity_hash,
            sampler_id="controlled-reset", sampler_version="v1", task_seed=int(seed),
            joint_position={"controlled-body/hinge": 0.}, poses_world={},
            velocity_policy="zero_named_joint_and_entity_velocities",
            control_policy="arm_targets_at_initial_joints_gripper_open", settle_steps=0,
        )

    return ReferenceTaskBinding(
        build=lambda _provider: value, reset_sample=sample,
        evaluate=lambda *_args, **_kwargs: TaskEvaluation(0., False),
        object_poses=(), external_actions=True, interval_mode="grouped", recorder_mode="canonical",
        action_schema={"schema_id": "controlled-joint-action-v1"},
        action_space_factory=lambda: Box(-1., 1., shape=(1,), dtype=np.float32),
        prepare_action=lambda _action: RequestedAction("absolute_joint", None, "none", (0.,) * 8),
        observation_space_factory=lambda _env: {"state": Box(-np.inf, np.inf, shape=(1,), dtype=np.float32)},
        observation_projection=lambda _env, state: (
            {"state": np.asarray((state.qpos[0],), dtype=np.float32)}, {}, TaskEvaluation(0., False),
        ),
        scalar_control_binding=ControlBinding("controlled-gripper", .08),
        close_task_resources=receipt.close,
    )


def _camera_capture(camera, renderer, state, step_value):
    identity = CameraCaptureIdentityV1(
        "camera-capture-identity-v1", camera.task_artifact_hash, camera.camera_id,
        camera.identity_hash, "d" * 64, "e" * 64, renderer, "f" * 64,
        state.boundary, state.sample_clock, ("rgb",), "post_control_step",
    )
    return CanonicalCameraObservation(
        np.full((camera.height, camera.width, 3), step_value, dtype=np.float32),
        None, resolve_camera(camera, state), identity,
    )


class _ControlledCameraSession:
    def __init__(self, camera, renderer):
        self.camera, self.renderer, self.closed = camera, renderer, 0

    def capture(self, state):
        return _camera_capture(self.camera, self.renderer, state, float(state.boundary.control_step) / 4.)

    def close(self):
        self.closed += 1


def test_public_selected_nonposition_rgb_publishes_current_typed_state_on_reset_step_and_reset(
    tmp_path, monkeypatch,
):
    from task_env import registry
    import task_env.environment.reference_env as reference_env
    import task_env.render.camera as camera_module

    artifact, source, receipt = _controlled_source(tmp_path)
    uid = f"controlled-nonposition-{uuid4().hex}"
    binding = _controlled_binding(artifact, source, receipt)
    env_type = type(uid.replace("-", "_").title(), (SelectedReferenceEnv,), {"uid": uid, "binding": binding})
    registry.ENV_REGISTRY.register(uid, env_type)
    sessions = []
    monkeypatch.setattr(reference_env, "materialize_control", lambda actual_artifact, _execution, *, source, **_kwargs:
                        _ControlledRuntime(actual_artifact, source))

    def make_camera_session(camera, _execution, *, source, initial_state, **_kwargs):
        assert source.runtime_source is env.value["source"]
        assert source.artifact.identity_hash == artifact.identity_hash
        assert initial_state.boundary.control_step == 0
        session = _ControlledCameraSession(camera, _execution.renderer_for_camera(camera.camera_id))
        sessions.append(session)
        return session

    monkeypatch.setattr(camera_module, "create_dynamic_camera_session", make_camera_session)
    camera = CameraGeometry(
        "camera-observation-v0", artifact.identity_hash, "controlled-task-camera", "world",
        IDENTITY, IDENTITY, 4, 3, 1., .01, 10., True, False,
    )
    env = registry.make_env(
        uid, config={"provider": "mujoco", "backend": "cpu", "horizon": 4},
        task_rgb_camera=camera, task_renderer="mujoco",
    )
    try:
        reset, reset_info = env.reset(seed=7)
        first_binding = env.typed_state.view.boundary
        assert not env.position_profile
        assert reset["state"].tolist() == [0.]
        assert reset["task_rgb"].shape == (3, 4, 3)
        assert reset_info["task_rgb_v1"]["capture_identity"]["state_boundary"] == first_binding.to_mapping()
        step, _reward, terminated, truncated, step_info = env.step(np.asarray((0.,), dtype=np.float32))
        second_binding = env.typed_state.view.boundary
        assert not terminated and not truncated
        assert second_binding.control_step == 1 and second_binding != first_binding
        assert env.typed_state.view.joints[0].position == (.5,)
        assert step["state"].tolist() == [.5]
        assert np.all(step["task_rgb"] == .25)
        assert step_info["task_rgb_v1"]["capture_identity"]["state_boundary"] == second_binding.to_mapping()
        old_generation = reset_info["task_rgb_v1"]["renderer_generation"]
        next_reset, next_reset_info = env.reset(seed=8)
        assert env.typed_state.view.boundary.control_step == 0
        assert env.typed_state.view.boundary.episode_id != first_binding.episode_id
        assert next_reset["state"].tolist() == [0.]
        assert next_reset_info["task_rgb_v1"]["renderer_generation"] != old_generation
        assert sessions[0].closed == 1
    finally:
        env.close()
        registry.ENV_REGISTRY._entries.pop(uid, None)


def test_public_selected_nonposition_rejects_foreign_state_publication_before_observation(
    tmp_path, monkeypatch,
):
    from task_env import registry
    import task_env.environment.reference_env as reference_env

    artifact, source, receipt = _controlled_source(tmp_path)
    uid = f"controlled-nonposition-foreign-{uuid4().hex}"
    binding = _controlled_binding(artifact, source, receipt)
    env_type = type(uid.replace("-", "_").title(), (SelectedReferenceEnv,), {"uid": uid, "binding": binding})
    registry.ENV_REGISTRY.register(uid, env_type)
    runtimes = []

    def materialize(actual_artifact, _execution, *, source, **_kwargs):
        runtime = _ControlledRuntime(actual_artifact, source, foreign_publication=True)
        runtimes.append(runtime)
        return runtime

    monkeypatch.setattr(reference_env, "materialize_control", materialize)
    env = registry.make_env(
        uid, config={"provider": "mujoco", "backend": "cpu", "horizon": 4},
        task_rgb_camera=CameraGeometry(
            "camera-observation-v0", artifact.identity_hash, "controlled-task-camera", "world",
            IDENTITY, IDENTITY, 4, 3, 1., .01, 10., True, False,
        ),
        task_renderer="mujoco",
    )
    try:
        with pytest.raises(Exception) as error:
            env.reset(seed=7)
        chain = " ".join(str(item) for item in (error.value, error.value.__cause__) if item is not None)
        assert "typed state is stale or differs" in chain
        assert runtimes and env.typed_state is None
        assert "task_rgb" not in getattr(env, "obs", {})
    finally:
        env.close()
        registry.ENV_REGISTRY._entries.pop(uid, None)


class _SpyTaskCameraVisualizer:
    def __init__(self, bad_field=None):
        self.bad_field = bad_field
        self.request = None
        self.frame_reads = 0

    def bind_task_camera(self, **request):
        self.request = dict(request)
        return self._readback()

    def update_task_camera(self, **request):
        self.request = dict(request)
        return self._readback()

    def read_task_camera(self):
        return self._readback()

    def _readback(self):
        request = self.request
        result = {
            "camera_id": request["camera_id"], "binding_id": "native-binding-v1",
            "position": request["position"].tolist(),
            "forward": ((request["look_at"] - request["position"])
                        / np.linalg.norm(request["look_at"] - request["position"])).tolist(),
            "up": (request["up"] / np.linalg.norm(request["up"])).tolist(),
            "fov_degrees": request["fov_degrees"], "near": request["near"], "far": request["far"],
            "width": request["width"], "height": request["height"],
        }
        if self.bad_field == "fov_degrees":
            result["fov_degrees"] = 60.
        elif self.bad_field == "near":
            result["near"] = .001
        return result

    def read_task_camera_frame(self, *, synchronized):
        assert synchronized
        self.frame_reads += 1
        return np.ones((self.request["height"], self.request["width"], 3), dtype=np.float32) * .5

    def project_task_camera(self, point):
        return list(point)

    def close(self):
        return None


@pytest.mark.parametrize("bad_field", [None, "fov_degrees", "near"])
def test_component_camera_provider_binds_reads_and_rejects_wrong_native_optics(bad_field):
    spec = CameraSpec("task", width=4, height=3, fov_y=1.2, near=.05, far=5.)
    sensor = CameraSensor(spec=spec, references=SimpleNamespace())
    visualizer = _SpyTaskCameraVisualizer(bad_field)
    render_source = SimpleNamespace(build_visualizer=lambda **_kwargs: visualizer)
    provider = CameraObservationProvider(
        render_source=render_source, config=SimpleNamespace(backend="rasterizer"),
        camera_sensors=(sensor,), task_rgb_camera_name="task",
    )
    snapshot = RuntimeSnapshot(
        qpos=np.zeros(1), qvel=np.zeros(1), body_xpos=np.asarray(((2., 0., 0.),)),
        body_xquat=np.asarray(((1., 0., 0., 0.),)), simulation_time=0.,
    )
    try:
        if bad_field is None:
            observation = provider.capture(snapshot)
            realized = observation.camera_metadata["task"].renderer_readback
            assert type(realized) is CameraRendererReadbackV1
            assert realized.camera_id == "task" and realized.width == 4 and realized.height == 3
            assert realized.fov_degrees == pytest.approx(np.degrees(spec.fov_y), abs=2e-4)
            assert realized.near == pytest.approx(spec.near, abs=2e-7)
            assert realized.far == pytest.approx(spec.far, abs=1e-5)
            assert observation.rgb["task"].shape == (3, 4, 3)
            assert visualizer.frame_reads == 1
        else:
            with pytest.raises(ValueError, match="readback differs"):
                provider.capture(snapshot)
            assert visualizer.frame_reads == 0
    finally:
        provider.close()


def test_component_camera_provider_updates_a_body_mounted_camera_from_each_snapshot():
    spec = CameraSpec("body-task", width=4, height=3, frame="body", parent="moving-body",
                      position=(1., 0., 0.), fov_y=1.2, near=.05, far=5.)
    references = SimpleNamespace(names=SimpleNamespace(bodies={"moving-body": 0}, sites={}))
    sensor = CameraSensor(spec=spec, references=references)
    visualizer = _SpyTaskCameraVisualizer()
    provider = CameraObservationProvider(
        render_source=SimpleNamespace(build_visualizer=lambda **_kwargs: visualizer),
        config=SimpleNamespace(backend="rasterizer"), camera_sensors=(sensor,),
        task_rgb_camera_name="body-task",
    )
    try:
        for body_x in (2., 3.):
            snapshot = RuntimeSnapshot(
                qpos=np.zeros(1), qvel=np.zeros(1),
                body_xpos=np.asarray(((body_x, 0., 0.),)),
                body_xquat=np.asarray(((1., 0., 0., 0.),)), simulation_time=body_x - 2.,
            )
            observation = provider.capture(snapshot)
            assert observation.camera_metadata["body-task"].renderer_readback.position[0] == pytest.approx(body_x + 1.)
        assert visualizer.frame_reads == 2
        assert visualizer.request["position"].tolist() == [4., 0., 0.]
    finally:
        provider.close()


def test_component_task_rgb_rejects_multiple_camera_specs_and_nonfinite_optics():
    from task_env.environment.reference_env import SelectedReferenceEnv as Env
    from task_env.tasks.pendulum import PendulumEnv

    config = PendulumEnv.default_config()
    camera = CameraSpec("task", width=8, height=6, fov_y=1.2, near=.05, far=5.)
    extra = CameraSpec("extra", width=8, height=6)
    config_with_extra = replace(
        config, render=replace(config.render, backend="rasterizer", camera_obs=True, cameras=(extra,))
    )
    with pytest.raises(ValueError, match="one task camera"):
        Env._prepare_component_task_rgb(config_with_extra, camera, "geophys")
    # General CameraSpec keeps the legacy infinite-far state-only contract;
    # task RGB rejects it before constructing a renderer.
    state_only = CameraSpec("state-only", far=float("inf"))
    assert state_only.far == float("inf")
    invalid = CameraSpec("invalid", width=8, height=6, fov_y=float("nan"), near=.05, far=5.)
    sensor = CameraSensor(spec=invalid, references=SimpleNamespace(names=SimpleNamespace(bodies={}, sites={})))
    built = []
    with pytest.raises(ValueError, match="finite 0 < fov_y"):
        CameraObservationProvider(
            render_source=SimpleNamespace(build_visualizer=lambda **kwargs: built.append(kwargs)),
            config=SimpleNamespace(backend="rasterizer"), camera_sensors=(sensor,),
            task_rgb_camera_name="invalid",
        )
    assert built == []


def _independent_projection(point, realized):
    position = np.asarray(realized.position, dtype=np.float64)
    forward = np.asarray(realized.forward, dtype=np.float64)
    up = np.asarray(realized.up, dtype=np.float64)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    delta = np.asarray(point, dtype=np.float64) - position
    depth = float(np.dot(delta, forward))
    focal = .5 * realized.height / np.tan(np.radians(realized.fov_degrees) / 2.)
    return np.asarray((
        .5 * realized.width + np.dot(delta, right) * focal / depth,
        .5 * realized.height + np.dot(delta, up) * focal / depth,
        depth,
    ))


def _jsonable(value):
    if isinstance(value, np.ndarray):
        return {"dtype": str(value.dtype), "shape": list(value.shape), "values": value.tolist()}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return repr(value)


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_pendulum_component_rgb_uses_native_camera_optics_on_reset_step_reset(tmp_path):
    from task_env import make_env

    camera = CameraSpec(
        "pendulum-task", width=96, height=72, frame="world",
        position=(2., 0., .25), quaternion_wxyz=(0., 0., 0., 1.),
        fov_y=1.2, near=.05, far=5.,
    )
    env = make_env(
        "pendulum-v1", config={"runtime": {"backend": "cpu"}},
        task_rgb_camera=camera, task_renderer="geophys",
    )
    try:
        reset, reset_info = env.reset(seed=37)
        assert env.observation_space.contains(reset)
        assert reset["task_rgb"].shape == (72, 96, 3)
        assert reset["task_rgb"].dtype == np.float32 and reset["task_rgb"].flags.owndata
        reset_receipt = reset_info["task_rgb_v1"]
        reset_realized = reset_receipt["realized_camera"]
        assert reset_receipt["requested_camera"]["fov_y"] == pytest.approx(1.2)
        assert reset_realized["fov_degrees"] == pytest.approx(np.degrees(1.2), abs=2e-4)
        assert reset_realized["near"] == pytest.approx(.05, abs=2e-7)
        assert reset_realized["far"] == pytest.approx(5., abs=1e-5)
        assert reset_realized["width"] == 96 and reset_realized["height"] == 72
        assert np.unique(reset["task_rgb"].reshape(-1, 3), axis=0).shape[0] >= 2

        native = env._last_sensor_observation.camera_metadata[camera.name].renderer_readback
        forward = np.asarray(native.forward)
        up = np.asarray(native.up)
        right = np.cross(forward, up)
        right /= np.linalg.norm(right)
        point = np.asarray(native.position) + forward * 2. + right * .6 + up * .2
        native_pixel = np.asarray(env._sensor_provider.project_task_camera(point))
        expected_pixel = _independent_projection(point, native)
        assert np.allclose(native_pixel, expected_pixel, atol=2e-3)
        wrong_fov = replace(native, fov_degrees=60.)
        assert abs(expected_pixel[0] - _independent_projection(point, wrong_fov)[0]) > 2.

        step, _reward, terminated, truncated, step_info = env.step(np.asarray((0.,), dtype=np.float32))
        assert not terminated and not truncated
        assert env.observation_space.contains(step)
        assert step["task_rgb"].flags.owndata
        assert step_info["elapsed_steps"] == 1
        assert step_info["simulation_time_s"] == pytest.approx(.05, abs=1e-8)
        step_receipt = step_info["task_rgb_v1"]
        assert step_receipt["observation_boundary"]["control_step"] == 1
        assert step_receipt["observation_boundary"]["simulation_time_s"] == pytest.approx(.05)
        assert step_receipt["realized_camera"]["binding_id"] == reset_realized["binding_id"]

        next_reset, next_reset_info = env.reset(seed=38)
        assert env.observation_space.contains(next_reset)
        assert next_reset_info["elapsed_steps"] == 0
        assert next_reset_info["simulation_time_s"] == 0.
        assert next_reset_info["task_rgb_v1"]["observation_boundary"]["control_step"] == 0
        assert next_reset_info["task_rgb_v1"]["realized_camera"]["binding_id"] == reset_realized["binding_id"]

        evidence_dir = tmp_path / "pendulum-evidence"
        evidence_dir.mkdir()
        image_files = {}
        for label, observation in (("reset", reset), ("step", step), ("reset_again", next_reset)):
            path = evidence_dir / f"{label}-task-rgb.npy"
            np.save(path, observation["task_rgb"], allow_pickle=False)
            image_files[path.name] = {
                "sha256": _sha256(path), "shape": list(observation["task_rgb"].shape),
                "dtype": str(observation["task_rgb"].dtype),
            }
        report = {
            "schema_version": "v211-g05-attempt003-pendulum-task-rgb-evidence-v1",
            "task_uid": "pendulum-v1",
            "factory": "task_env.make_env",
            "execution": {"physics_backend": "cpu", "renderer": "geophys", "renderer_backend": "rasterizer",
                          "cuda_visible_devices": "-1", "physics_dt_s": 0.002,
                          "control_substeps": 25, "control_dt_s": 0.05,
                          "action": [0.0], "action_steps": 1},
            "task_identity_metadata": _jsonable(getattr(env, "metadata", {})),
            "requested_camera": _jsonable(reset_receipt["requested_camera"]),
            "renderer_readback": _jsonable(reset_realized),
            "observation_boundaries": {
                "reset": _jsonable(reset_info["task_rgb_v1"]["observation_boundary"]),
                "step": _jsonable(step_info["task_rgb_v1"]["observation_boundary"]),
                "reset_again": _jsonable(next_reset_info["task_rgb_v1"]["observation_boundary"]),
            },
            "state_observations_without_rgb": {
                "reset": _jsonable({key: value for key, value in reset.items() if key != "task_rgb"}),
                "step": _jsonable({key: value for key, value in step.items() if key != "task_rgb"}),
                "reset_again": _jsonable({key: value for key, value in next_reset.items() if key != "task_rgb"}),
            },
            "renderer_receipts": {
                "reset": _jsonable(reset_receipt),
                "step": _jsonable(step_receipt),
                "reset_again": _jsonable(next_reset_info["task_rgb_v1"]),
            },
            "independent_geometry_check": {
                "world_point": point.tolist(), "renderer_projected_pixel": native_pixel.tolist(),
                "independent_projected_pixel": expected_pixel.tolist(),
                "wrong_60_degree_fov_pixel": _independent_projection(point, wrong_fov).tolist(),
                "wrong_fov_horizontal_delta_px": abs(
                    expected_pixel[0] - _independent_projection(point, wrong_fov)[0]
                ),
                "projection_tolerance_px": 2e-3,
            },
            "capture_did_not_advance_physics": {
                "reset_control_step": reset_info["task_rgb_v1"]["observation_boundary"]["control_step"],
                "action_step_control_step": step_info["task_rgb_v1"]["observation_boundary"]["control_step"],
                "elapsed_steps": step_info["elapsed_steps"],
                "simulation_time_s": step_info["simulation_time_s"],
                "action_steps": 1,
            },
            "image_files": image_files,
        }
        report_path = evidence_dir / "evidence.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
        report["evidence_json_sha256"] = _sha256(report_path)
    finally:
        env.close()


def test_public_session_boundary_requires_matching_scene_materialization_and_episode(tmp_path):
    artifact, source, receipt = _controlled_source(tmp_path)
    runtime = _ControlledRuntime(artifact, source)
    runtime.reset_sample_id = 'reset-' + 'a' * 64
    env = object.__new__(SelectedReferenceEnv)
    env.session = runtime
    env.state = runtime.snapshot()
    try:
        assert env._current_control_step() == 0
        original = runtime.state_boundary_identity
        for field, value in (('scene_identity_hash', 'b' * 64),
                             ('provider_materialization_id', 'foreign-materialization'),
                             ('episode_id', 'foreign-episode')):
            runtime.state_boundary_identity = lambda field=field, value=value: replace(original(), **{field: value})
            with pytest.raises(ValueError, match='typed source binding'):
                env._current_control_step()
        runtime.source = SimpleNamespace(scene_definition=SimpleNamespace(identity_hash='c' * 64))
        with pytest.raises(ValueError, match='Scene differs from its typed Artifact'):
            env._current_control_step()
    finally:
        receipt.close()
