"""Provider-free S1 for the real BaseTaskEnv/compile/lifecycle/Recorder path."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import shutil
import sys
import types
import xml.etree.ElementTree as ET

import h5py
import numpy as np
import pytest
import yaml

from bench_deploy.libero.core_candidate import build_libero_pilot_env
from bench_deploy.libero.core_candidate_worker import (
    consume_candidate_episode_report,
    run_candidate_episode,
)
from bench_deploy.libero.task import PILOT_SOURCE_ID
from task_env.environment import ContactSummary
from task_env.recorders import (
    RecorderConfig,
    TransitionRecordWrapper,
    inspect_trajectory_h5,
    load_structured_control_records_h5,
)


def _preserve_h5(path: Path) -> Path:
    artifact_root = os.environ.get("R07C_S1_ARTIFACT_DIR")
    if not artifact_root:
        return path
    destination = Path(artifact_root) / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return destination


@dataclass(frozen=True)
class _FakeJoint:
    name: str


@dataclass(frozen=True)
class _FakeSite:
    name: str


@dataclass(frozen=True)
class _FakeLink:
    name: str
    joints: tuple[_FakeJoint, ...]
    sites: tuple[_FakeSite, ...]


@dataclass(frozen=True)
class _FakeActuator:
    name: str


@dataclass(frozen=True)
class _FakeArticulation:
    links: tuple[_FakeLink, ...]
    actuators: tuple[_FakeActuator, ...]


class _FakeSceneModel:
    def __init__(self, xml: str):
        root = ET.fromstring(xml)
        self.body_names = tuple(body.get("name", "") for body in root.iter("body"))
        self.site_names = tuple(site.get("name", "") for site in root.iter("site") if site.get("name"))
        self.geom_names = tuple(geom.get("name", "") for geom in root.iter("geom") if geom.get("name"))
        self.links = []
        joint_names = []
        qpos_addresses = []
        dof_addresses = []
        qpos_cursor = 0
        dof_cursor = 0
        for body in root.iter("body"):
            body_name = body.get("name", "")
            joints = []
            for joint in (*body.findall("joint"), *body.findall("freejoint")):
                name = joint.get("name") or f"{body_name}__free"
                kind = "free" if joint.tag == "freejoint" else joint.get("type", "hinge")
                qpos_addresses.append(qpos_cursor)
                dof_addresses.append(dof_cursor)
                qpos_cursor += 7 if kind == "free" else 1
                dof_cursor += 6 if kind == "free" else 1
                joint_names.append(name)
                joints.append(_FakeJoint(name))
            sites = tuple(_FakeSite(site.get("name", "")) for site in body.findall("site") if site.get("name"))
            self.links.append(_FakeLink(body_name, tuple(joints), sites))
        actuator_nodes = [node for node in root.findall("actuator/*") if node.get("name")]
        self.actuators = tuple(_FakeActuator(node.get("name", "")) for node in actuator_nodes)
        ctrl_range = []
        for node in actuator_nodes:
            raw = node.get("ctrlrange")
            if raw is None:
                ctrl_range.append((-np.inf, np.inf))
            else:
                values = np.fromstring(raw, sep=" ", dtype=np.float32)
                if values.shape != (2,):
                    raise ValueError(f"fake importer needs two-value ctrlrange for {node.get('name')}")
                ctrl_range.append((float(values[0]), float(values[1])))
        self.articulation = _FakeArticulation(tuple(self.links), self.actuators)
        self.joint_data = {
            "geom_names": list(self.geom_names),
            "n_qpos": qpos_cursor,
            "n_dof": dof_cursor,
            "n_actuators": len(actuator_nodes),
            "jnt_qposadr": np.asarray(qpos_addresses, dtype=np.int32),
            "jnt_dofadr": np.asarray(dof_addresses, dtype=np.int32),
            "actuator_ctrlrange": np.asarray(ctrl_range, dtype=np.float32),
            "initial_qpos": np.zeros(qpos_cursor, dtype=np.float32),
            "initial_qvel": np.zeros(dof_cursor, dtype=np.float32),
            "initial_ctrl": np.zeros(len(actuator_nodes), dtype=np.float32),
            "initial_act": np.zeros(len(actuator_nodes), dtype=np.float32),
        }

    def build_rigid_scene_model(self):
        return self


class _FakeImportedScene:
    def __init__(self, source):
        self.source = source
        self._model = _FakeSceneModel(source.xml)
        self.articulation = self._model.articulation

    def build_rigid_scene_model(self):
        return self._model


@dataclass(frozen=True)
class _FakeSceneSource:
    xml: str
    base_dir: Path | None
    label: str

    @classmethod
    def mjcf_string(cls, xml, *, base_dir=None, label=""):
        return cls(xml=str(xml), base_dir=base_dir, label=str(label))


class _FakePhysics:
    def __init__(self, model: _FakeSceneModel):
        data = model.joint_data
        self.n_qpos = data["n_qpos"]
        self.n_dof = data["n_dof"]
        self.n_actuators = data["n_actuators"]
        self.n_sites = len(model.site_names)
        self.n_bodies = len(model.body_names)
        self.qpos = np.asarray(data["initial_qpos"], dtype=np.float32).copy()
        self.qvel = np.asarray(data["initial_qvel"], dtype=np.float32).copy()
        self.qacc = np.zeros(self.n_dof, dtype=np.float32)
        self.ctrl = np.asarray(data["initial_ctrl"], dtype=np.float32).copy()
        self.act = np.asarray(data["initial_act"], dtype=np.float32).copy()
        self.positions = np.zeros((self.n_bodies, 3), dtype=np.float32)
        self.orientations = np.zeros((self.n_bodies, 4), dtype=np.float32)
        if self.n_bodies:
            self.orientations[:, 0] = 1.0
        self.site_positions = np.zeros((self.n_sites, 3), dtype=np.float32)
        self.site_orientations = np.zeros((self.n_sites, 4), dtype=np.float32)
        if self.n_sites:
            self.site_orientations[:, 0] = 1.0
        self.close_calls = 0
        self.fail_read_field = None
        self.contact_summary_value = None

    def snapshot(self):
        return {name: getattr(self, name).copy() for name in ("qpos", "qvel", "qacc", "ctrl", "act")}

    def restore(self, values):
        for name, value in values.items():
            if hasattr(self, name):
                setattr(self, name, np.asarray(value).copy())

    def write_qpos(self, value): self.qpos = np.asarray(value, dtype=np.float32).copy()
    def write_qvel(self, value): self.qvel = np.asarray(value, dtype=np.float32).copy()
    def write_qacc(self, value): self.qacc = np.asarray(value, dtype=np.float32).copy()
    def write_ctrl(self, value): self.ctrl = np.asarray(value, dtype=np.float32).copy()
    def write_act(self, value): self.act = np.asarray(value, dtype=np.float32).copy()
    def synchronize_kinematic_state(self, *, update_site_jacobians): del update_site_jacobians
    def read_qpos(self): return self.qpos.copy()
    def read_qvel(self): return self.qvel.copy()
    def read_qacc(self): return self.qacc.copy()
    def read_ctrl(self): return self.ctrl.copy()
    def read_positions(self):
        if self.fail_read_field == "positions":
            raise RuntimeError("synthetic fake-native position read fault")
        return self.positions.copy()
    def read_contact_summary(self):
        return self.contact_summary_value or ContactSummary.unavailable(
            "synthetic_contact_not_configured"
        )
    def read_orientations(self): return self.orientations.copy()
    def read_site_world_pos(self): return self.site_positions.copy()
    def read_site_world_quat(self): return self.site_orientations.copy()
    def close(self): self.close_calls += 1


class _FakeScheduler:
    def __init__(self):
        self.fail_next = False
        self.calls = []
        self.close_calls = 0

    def step(self, substeps):
        self.calls.append(int(substeps))
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("synthetic fake-native scheduler fault")

    def prewarm(self, *, profile): del profile
    def close(self): self.close_calls += 1


@dataclass(frozen=True)
class _FakeRuntime:
    solver: _FakePhysics
    simulator: _FakeScheduler
    render_source: None = None
    render_options: None = None


class _ForbiddenEngineImports(importlib.abc.MetaPathFinder):
    forbidden = ("mujoco", "taichi", "isaac", "robosuite", "libero", "torch", "genesis", "warp")

    def find_spec(self, fullname, path=None, target=None):
        del path, target
        if fullname.split(".", 1)[0].lower() in self.forbidden:
            raise AssertionError(f"provider/native import forbidden in R07c S1: {fullname}")
        return None


def _install_fake_native_leaves(monkeypatch):
    class GroundConfig:
        def __init__(self, **kwargs): self.kwargs = dict(kwargs)

    demo = types.ModuleType("geophys.demo_runtime")
    demo.assemble_mjcf_articulated_runtime = lambda imported, **kwargs: _FakeRuntime(
        solver=_FakePhysics(imported.build_rigid_scene_model()), simulator=_FakeScheduler()
    )
    test_runtime = types.ModuleType("geophys.test_runtime")
    test_runtime.init_test_backend = lambda backend: None
    geophys_pkg = types.ModuleType("geophys")
    geophys_pkg.__path__ = []
    geophys_pkg.__r07_fake_native_leaf__ = True
    solvers_pkg = types.ModuleType("solvers")
    solvers_pkg.__path__ = []
    solvers_pkg.__r07_fake_native_leaf__ = True
    solver_pkg = types.ModuleType("solvers.rigid")
    solver_pkg.RigidGroundConfig = GroundConfig
    control_pkg = types.ModuleType("control")
    control_pkg.__path__ = []
    robot_arm = types.ModuleType("control.robot_arm")
    robot_arm.RobotArmObservationConfig = lambda **kwargs: kwargs
    class NoopReader:
        def __init__(self, *args, **kwargs): pass
    robot_arm.RobotArmObservationReader = NoopReader
    monkeypatch.setitem(sys.modules, "geophys", geophys_pkg)
    monkeypatch.setitem(sys.modules, "solvers", solvers_pkg)
    monkeypatch.setitem(sys.modules, "geophys.demo_runtime", demo)
    monkeypatch.setitem(sys.modules, "geophys.test_runtime", test_runtime)
    monkeypatch.setitem(sys.modules, "solvers.rigid", solver_pkg)
    monkeypatch.setitem(sys.modules, "control", control_pkg)
    monkeypatch.setitem(sys.modules, "control.robot_arm", robot_arm)


def _candidate_xml() -> str:
    # Compact fixture for the integration lane. The same test can be replayed
    # against the exact verified 107 kB composition via R07C_COMPOSED_MJCF.
    xml_path = __import__("os").environ.get("R07C_COMPOSED_MJCF")
    if xml_path:
        return Path(xml_path).read_text(encoding="utf-8")
    return """<mujoco model="libero-s1-fixture">
      <option timestep="0.002" gravity="0 0 -9.81"/>
      <worldbody>
        <body name="main_table"><geom name="table_geom" type="box" size=".4 .4 .02"/></body>
        <body name="akita_black_bowl_1"><freejoint name="bowl_free"/><geom name="bowl_geom" type="sphere" size=".03"/></body>
        <body name="plate_1"><freejoint name="plate_free"/><geom name="plate_geom" type="cylinder" size=".1 .01"/></body>
        <body name="akita_black_bowl_2"><freejoint name="bowl2_free"/><geom name="bowl2_geom" type="sphere" size=".03"/></body>
        <body name="cookies_1"><freejoint name="cookies_free"/><geom name="cookies_geom" type="box" size=".03 .03 .01"/></body>
        <body name="glazed_rim_porcelain_ramekin_1"><freejoint name="ramekin_free"/><geom name="ramekin_geom" type="cylinder" size=".03 .02"/></body>
        <body name="flat_stove_1"><geom name="stove_geom" type="box" size=".1 .1 .02"/></body>
        <body name="wooden_cabinet_1"><geom name="cabinet_geom" type="box" size=".1 .1 .2"/></body>
        <body name="panda_base">
          <body name="robot__link0"><joint name="robot0_joint1" type="hinge"/>
            <body name="robot__link1"><joint name="robot0_joint2" type="hinge"/>
              <body name="robot__link2"><joint name="robot0_joint3" type="hinge"/>
                <body name="robot__link3"><joint name="robot0_joint4" type="hinge"/>
                  <body name="robot__link4"><joint name="robot0_joint5" type="hinge"/>
                    <body name="robot__link5"><joint name="robot0_joint6" type="hinge"/>
                      <body name="robot__link6"><joint name="robot0_joint7" type="hinge"/>
                        <body name="robot__link7"><body name="robot__right_hand">
                          <body name="right_gripper"><site name="grip_site"/>
                            <body name="eef"><body name="gripper__leftfinger"><joint name="gripper0_finger_joint1" type="slide"/></body>
                              <body name="gripper__rightfinger"><joint name="gripper0_finger_joint2" type="slide"/></body>
                            </body>
                          </body>
                        </body></body>
                      </body>
                    </body>
                  </body>
                </body>
              </body>
            </body>
          </body>
        </body>
      </worldbody>
      <actuator>
        <motor name="robot0_torq_j1" joint="robot0_joint1" ctrlrange="-80 80"/>
        <motor name="robot0_torq_j2" joint="robot0_joint2" ctrlrange="-80 80"/>
        <motor name="robot0_torq_j3" joint="robot0_joint3" ctrlrange="-80 80"/>
        <motor name="robot0_torq_j4" joint="robot0_joint4" ctrlrange="-80 80"/>
        <motor name="robot0_torq_j5" joint="robot0_joint5" ctrlrange="-80 80"/>
        <motor name="robot0_torq_j6" joint="robot0_joint6" ctrlrange="-12 12"/>
        <motor name="robot0_torq_j7" joint="robot0_joint7" ctrlrange="-12 12"/>
        <position name="gripper0_gripper_finger_joint1" joint="gripper0_finger_joint1" ctrlrange="0 .04"/>
        <position name="gripper0_gripper_finger_joint2" joint="gripper0_finger_joint2" ctrlrange="-.04 0"/>
      </actuator>
    </mujoco>"""


def test_real_core_env_compile_lifecycle_fault_recorder_h5_and_independent_read(tmp_path, monkeypatch):
    xml = _candidate_xml()
    xml_sha = hashlib.sha256(xml.encode("utf-8")).hexdigest()
    _install_fake_native_leaves(monkeypatch)
    fake_scene = types.ModuleType("scene")
    fake_scene.SceneSource = _FakeSceneSource
    fake_scene.import_scene_source = lambda source: _FakeImportedScene(source)
    fake_scene.__r07_fake_native_leaf__ = True
    monkeypatch.setitem(sys.modules, "scene", fake_scene)
    for name in list(sys.modules):
        if name.split(".", 1)[0].lower() in _ForbiddenEngineImports.forbidden:
            raise AssertionError(f"engine module was already imported before S1: {name}")
    finder = _ForbiddenEngineImports()
    sys.meta_path.insert(0, finder)
    env = None
    recording = None
    lifecycle = None
    try:
        env = build_libero_pilot_env(
            xml=xml,
            composed_mjcf_sha256=xml_sha,
            install_root=tmp_path,
            build_runtime=True,
        )
        assert env._runtime_assembly.compiled_scene.composition_adapter == "libero_verified_static_mjcf_v2"
        assert env._task_definition.source_xml_sha256 == xml_sha
        assert env.uid not in __import__("task_env.registry", fromlist=["ENV_REGISTRY"]).ENV_REGISTRY.uids()
        lifecycle = env._task_lifecycle
        scheduler = env._runtime_assembly.boundary._scheduler
        fake_physics = env._runtime_assembly.boundary._physics
        scene_source = env._runtime_assembly.compiled_scene.imported_scene.source
        assert Path(scene_source.base_dir).resolve() == tmp_path.resolve()
        assert scene_source.label == f"libero-pilot-static-mjcf:{xml_sha}"
        body_ids = env._runtime_assembly.compiled_scene.references.names.bodies
        bowl_id = body_ids["akita_black_bowl_1"]
        plate_id = body_ids["plate_1"]
        fake_physics.positions[bowl_id] = (0.029999, 0.0, 0.1)
        fake_physics.positions[plate_id] = (0.0, 0.0, 0.1)
        fake_physics.contact_summary_value = ContactSummary.available(
            {"akita_black_bowl_1/plate_1": 1}
        )

        recording = TransitionRecordWrapper(
            env,
            RecorderConfig(schema_version="v3", max_transitions=4, max_buffer_bytes=2_000_000),
        )
        recording.start_record()
        _, reset_info = recording.reset(seed=19)
        assert reset_info["task_uid"] == env.task_uid
        assert reset_info["is_success"] is True
        assert reset_info["task_metrics"]["on_bowl_plate_available"] is True
        action = np.asarray([-0.161037389, 0.0, 0.0, -2.44459747, 0.0, 2.2267522, np.pi / 4, 0.04], dtype=np.float32)
        with pytest.raises((TypeError, ValueError), match="action"):
            recording.step(action[:-1])
        assert scheduler.calls == []
        assert lifecycle.execution_fault is None
        fake_physics.contact_summary_value = ContactSummary.available({})
        _, _, terminated, truncated, step_info = recording.step(action)
        assert terminated is False and truncated is True
        assert step_info["is_success"] is False
        assert step_info["task_metrics"]["on_bowl_plate_available"] is True
        structured = step_info["structured_control_transition"]
        assert structured.request.scene_identity_hash == xml_sha
        assert structured.writer_controls[0]["canonical_action"]["gain_status"] == "synthetic_s1_fixture"
        assert scheduler.calls == [25]
        h5_path = recording.save_h5(tmp_path, "libero_core_candidate_success")
        _preserve_h5(h5_path)
        production = inspect_trajectory_h5(h5_path)
        assert production["schema_version"] == "v3"
        assert production["transition_count"] == 1
        success_records = load_structured_control_records_h5(h5_path)
        assert success_records["transition_count"] == 1
        assert success_records["observation_count"] == 2
        assert success_records["outcome"].episode_id == reset_info["episode_id"]
        assert success_records["outcome"].final_boundary == 1
        with h5py.File(h5_path, "r") as handle:
            assert len(handle["reward"]) == 1
            assert len(handle["action/robot0_joint1"]) == 1
            meta = yaml.safe_load(handle["meta/env_meta"][()].decode("utf-8"))
            assert meta["action_schema"]["schema_id"] == "libero.mounted_panda_mixed_action.v1"
            assert meta["reference_profile"]["composed_mjcf_sha256"] == xml_sha
            outcome_raw = json.loads(handle["meta/episode_outcome_v1_json"][()].decode("utf-8"))
            events_raw = json.loads(handle["meta/boundary_events_v1_json"][()].decode("utf-8"))
            assert int(handle.attrs["observation_count"]) == int(handle.attrs["transition_count"]) + 1
            assert outcome_raw["episode_id"] == reset_info["episode_id"]
            assert outcome_raw["final_boundary"] == 1
            assert events_raw[-1]["payload"]["end_reason"] == outcome_raw["end_reason"]

        # The same live Env exercises the Core fault latch and a zero-transition
        # structured Outcome after a fake-native step failure.
        # The public RuntimeSnapshot stores float32 poses: use the first
        # representable value above 0.03 m for a strict-threshold rejection.
        above_threshold = float(np.nextafter(np.float32(0.03), np.float32(np.inf)))
        fake_physics.positions[bowl_id] = (above_threshold, 0.0, 0.1)
        fake_physics.contact_summary_value = ContactSummary.available(
            {"akita_black_bowl_1/plate_1": 1}
        )
        _, above_threshold_info = recording.reset(seed=20)
        assert above_threshold_info["task_metrics"]["on_bowl_plate_available"] is True
        assert above_threshold_info["is_success"] is False
        recording.start_record()
        scheduler.fail_next = True
        with pytest.raises(RuntimeError, match="synthetic fake-native scheduler fault"):
            recording.step(action)
        assert lifecycle.execution_fault is not None
        assert lifecycle.execution_fault.phase == "physics_step"
        assert lifecycle.execution_fault.interval_attempted is True
        assert lifecycle.execution_fault.interval_completed is False
        assert recording.recorder.transition_count == 0
        assert recording.recorder.observation_count == 1
        calls_after_failure = len(scheduler.calls)
        with pytest.raises(RuntimeError, match=r"is faulted; reset\(\) is required"):
            recording.step(action)
        assert len(scheduler.calls) == calls_after_failure
        step_failed_end = recording.stop("failed_step_boundary")
        assert step_failed_end.outcome.end_reason == "execution_fault"
        assert step_failed_end.outcome.final_boundary == 0
        failed_path = recording.save_h5(tmp_path, "libero_core_candidate_step_failure")
        _preserve_h5(failed_path)
        failed_records = load_structured_control_records_h5(failed_path)
        assert failed_records["transition_count"] == 0
        assert failed_records["observation_count"] == 1
        assert failed_records["outcome"].episode_id == step_failed_end.outcome.episode_id

        # A successful fake interval followed by a failed public snapshot has
        # its own typed fault and cannot append a partial transition.
        fake_physics.positions[bowl_id] = (0.0, 0.0, 0.1)
        fake_physics.contact_summary_value = ContactSummary.available({})
        _, empty_contact_info = recording.reset(seed=21)
        assert empty_contact_info["task_metrics"]["on_bowl_plate_available"] is True
        assert empty_contact_info["is_success"] is False
        recording.start_record()
        fake_physics.fail_read_field = "positions"
        with pytest.raises(RuntimeError, match="synthetic fake-native position read fault"):
            recording.step(action)
        assert lifecycle.execution_fault is not None
        assert lifecycle.execution_fault.phase == "snapshot_readback"
        assert lifecycle.execution_fault.interval_completed is True
        assert "synthetic fake-native position read fault" in lifecycle.execution_fault.readback_error
        assert recording.recorder.transition_count == 0
        readback_failed_end = recording.stop("failed_readback_boundary")
        readback_failed_path = recording.save_h5(tmp_path, "libero_core_candidate_readback_failure")
        _preserve_h5(readback_failed_path)
        readback_failed_records = load_structured_control_records_h5(readback_failed_path)
        assert readback_failed_records["transition_count"] == 0
        assert readback_failed_records["observation_count"] == 1
        assert readback_failed_records["outcome"].episode_id == readback_failed_end.outcome.episode_id

        fake_physics.fail_read_field = None
        fake_physics.contact_summary_value = ContactSummary.unavailable(
            "synthetic_stale_source_contact_unavailable"
        )
        _, recovered_info = recording.reset(seed=22)
        assert lifecycle.execution_fault is None
        assert recovered_info["task_metrics"]["on_bowl_plate_available"] is False
        recording.start_record()
        _, _, _, recovered_truncated, _ = recording.step(action)
        assert recovered_truncated is True
        recovery_path = recording.save_h5(tmp_path, "libero_core_candidate_reset_recovery")
        _preserve_h5(recovery_path)
        recovery_records = load_structured_control_records_h5(recovery_path)
        assert recovery_records["outcome"].episode_id == recovered_info["episode_id"]
        assert recovery_records["transition_count"] == 1

        # Closing an active v3 recording uses the real public Stop/Outcome path.
        _, close_info = recording.reset(seed=23)
        recording.start_record()
        recording.close()
        assert lifecycle._closed is True
        assert env._closed is True
        assert env._last_episode_end.outcome.end_reason == "external_stop"
        assert env._last_episode_end.boundary_event.payload["requested_reason"] == "environment_close"
        close_path = recording.save_h5(tmp_path, "libero_core_candidate_close_finalizer")
        _preserve_h5(close_path)
        close_records = load_structured_control_records_h5(close_path)
        assert close_records["transition_count"] == 0
        assert close_records["observation_count"] == 1
        assert close_records["outcome"].episode_id == close_info["episode_id"]
        assert close_records["outcome"].end_reason == "external_stop"

        # Public owner predicate keeps provider contact absence unavailable.
        predicate = env._task_definition.evaluate_predicates(
            __import__("task_env.environment.task_definition", fromlist=["TaskEvaluationContextV1"])
            .TaskEvaluationContextV1(state=env._last_snapshot, elapsed_steps=0)
        ).resolve("on_bowl_plate")
        assert predicate.status == "unavailable"
        assert predicate.reason == "synthetic_stale_source_contact_unavailable"
    finally:
        if recording is not None:
            recording.close()
        elif env is not None:
            env.close()
        sys.meta_path.remove(finder)
    assert lifecycle is not None and lifecycle._closed is True
    assert env is not None and env._closed is True
    recording.close()
    assert recording._closed is True


def test_candidate_worker_finalizer_and_independent_report_consumer_success_and_failure(
    tmp_path, monkeypatch,
):
    xml = _candidate_xml()
    xml_sha = hashlib.sha256(xml.encode("utf-8")).hexdigest()
    _install_fake_native_leaves(monkeypatch)
    fake_scene = types.ModuleType("scene")
    fake_scene.SceneSource = _FakeSceneSource
    fake_scene.import_scene_source = lambda source: _FakeImportedScene(source)
    fake_scene.__r07_fake_native_leaf__ = True
    monkeypatch.setitem(sys.modules, "scene", fake_scene)
    for name in list(sys.modules):
        if name.split(".", 1)[0].lower() in _ForbiddenEngineImports.forbidden:
            raise AssertionError(f"engine module was already imported before S1: {name}")
    finder = _ForbiddenEngineImports()
    sys.meta_path.insert(0, finder)
    try:
        action = np.asarray(
            [-0.161037389, 0.0, 0.0, -2.44459747, 0.0, 2.2267522, np.pi / 4, 0.04],
            dtype=np.float32,
        )
        success_env = build_libero_pilot_env(
            xml=xml, composed_mjcf_sha256=xml_sha, install_root=tmp_path / "success"
        )
        artifact_root = Path(os.environ.get("R07C_S1_ARTIFACT_DIR", tmp_path / "worker_reports"))
        success_dir = artifact_root / "worker_success"
        failure_dir = artifact_root / "worker_failure"
        success_report = run_candidate_episode(
            success_env,
            action=action,
            output_dir=success_dir,
            run_id="success",
            seed=31,
        )
        success_consumed = consume_candidate_episode_report(
            success_dir / "success.result.json"
        )
        assert success_report["execution_status"] == "passed"
        assert success_report["task_success"] is False
        assert success_report["close_success"] is True
        assert success_report["finalizer"]["episode_id"] == success_report["episode_id"]
        assert success_consumed["status"] == "verified_success"
        assert success_consumed["observation_count"] == success_consumed["transition_count"] + 1

        failure_env = build_libero_pilot_env(
            xml=xml, composed_mjcf_sha256=xml_sha, install_root=tmp_path / "failure"
        )
        failure_env._runtime_assembly.boundary._scheduler.fail_next = True
        failure_report = run_candidate_episode(
            failure_env,
            action=action,
            output_dir=failure_dir,
            run_id="failure",
            seed=32,
        )
        failure_consumed = consume_candidate_episode_report(
            failure_dir / "failure.result.json"
        )
        assert failure_report["execution_status"] == "failed"
        assert failure_report["worker_error"]["type"] == "RuntimeError"
        assert failure_report["close_success"] is True
        assert failure_report["finalizer"]["end_reason"] == "execution_fault"
        assert failure_consumed["status"] == "verified_failure"
        assert failure_consumed["transition_count"] == 0

        forged_pass = dict(failure_report)
        forged_pass["execution_status"] = "passed"
        unsigned = {key: value for key, value in forged_pass.items() if key != "result_sha256"}
        forged_pass["result_sha256"] = hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        forged_path = failure_dir / "forged_pass.result.json"
        forged_path.write_text(json.dumps(forged_pass), encoding="utf-8")
        with pytest.raises(ValueError, match="success status lacks"):
            consume_candidate_episode_report(forged_path)
    finally:
        sys.meta_path.remove(finder)
