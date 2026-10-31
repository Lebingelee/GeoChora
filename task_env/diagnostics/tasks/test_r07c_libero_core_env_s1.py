"""R07c D01 same-SelectedReferenceEnv provider-free S1.

Only the MuJoCo C/API leaf is synthetic.  The candidate builder, capability
admission, SelectedReferenceEnv, RuntimeSession, Controller, state/contact
projection, Generic H5 v3 Recorder, finalizer, worker, and independent reader
remain the production implementations.
"""
from __future__ import annotations

import builtins
from dataclasses import replace
import hashlib
import importlib.abc
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types
import xml.etree.ElementTree as ET

import h5py
import numpy as np
import pytest

from bench_deploy.libero.core_candidate_worker import (
    _equivalent_wxyz_quaternions, consume_libero_candidate_bundle,
    run_libero_candidate_worker,
)
from bench_deploy.libero.evaluation import (
    PILOT_TASK_UID, OnBowlPlateEvidenceV1, evaluate_on_bowl_plate_v1,
)
from task_env.recorders import load_structured_control_records_h5


_FORBIDDEN_ROOTS = {"geophys", "taichi", "isaacsim", "omni", "robosuite", "libero", "torch", "genesis"}


def test_solution_reader_accepts_only_unit_quaternion_sign_equivalence():
    quaternion = (0.02003903, -0.72548007, -0.68784862, 0.01188998)
    antipodal = tuple(-value for value in quaternion)
    different = (0.02003903, 0.72548007, -0.68784862, 0.01188998)
    assert _equivalent_wxyz_quaternions(quaternion, antipodal)
    assert not _equivalent_wxyz_quaternions(quaternion, different)
    assert not _equivalent_wxyz_quaternions(quaternion, (2.0, 0.0, 0.0, 0.0))


class _GravityBiasDouble:
    """Provider-free lowest-primitive substitute for the source bias query."""

    profile_id = "libero-source-mjcf-gravity-bias-v1"

    def __init__(self, source_xml_sha256, source_closure_digest, kinematics=None):
        self.source_xml_sha256 = source_xml_sha256
        self.source_closure_digest = source_closure_digest
        self.kinematics = kinematics
        self.model_identity_sha256 = hashlib.sha256(
            f"{source_xml_sha256}:{source_closure_digest}:gravity-double".encode()
        ).hexdigest()
        self.forward_calls = 0
        self.closed = False
        self.close_calls = 0

    def gravity_torque(self, joint_position_rad):
        values = np.asarray(joint_position_rad, dtype=np.float64)
        assert values.shape == (7,) and np.isfinite(values).all()
        self.forward_calls += 1
        return np.asarray((0.0, -19.2, 0.1, 18.1, 0.0, 2.1, 0.0), dtype=np.float64)

    def operational_space_state_v1(self, joint_position_rad, joint_velocity_rad_s):
        assert self.kinematics is not None
        q = np.asarray(joint_position_rad, dtype=np.float64)
        qdot = np.asarray(joint_velocity_rad_s, dtype=np.float64)
        assert q.shape == qdot.shape == (7,) and np.isfinite(q).all() and np.isfinite(qdot).all()
        transform, jacobian = self.kinematics.fk_jacobian(q)
        self.forward_calls += 1
        return {
            "schema_version": "libero-source-operational-space-state-v1",
            "profile_id": "libero-source-operational-space-state-v1",
            "model_identity_sha256": self.model_identity_sha256,
            "source_xml_sha256": self.source_xml_sha256,
            "source_closure_digest": self.source_closure_digest,
            "tcp_site_name": "gripper0_grip_site",
            "site_position_world_m": transform[:3, 3].copy(),
            "site_rotation_world": transform[:3, :3].copy(),
            "jacobian_world": jacobian.copy(),
            "mass_matrix_arm": np.eye(7, dtype=np.float64),
            "bias_minus_passive_arm_Nm": np.zeros(7, dtype=np.float64),
            "forward_call_count": self.forward_calls,
            "mj_step_call_count": 0,
        }

    def identity_mapping(self):
        return {
            "profile_id": self.profile_id,
            "model_identity_sha256": self.model_identity_sha256,
            "source_xml_sha256": self.source_xml_sha256,
            "source_closure_digest": self.source_closure_digest,
            "composition_plan_sha256": "c" * 64,
            "model_dimensions": {"nq": 48, "nv": 43, "nbody": 38, "njnt": 18},
            "runtime_identity": {"mujoco_version": "3.8.1", "api_version": 3008001},
            "calculation": "zero_velocity_qfrc_bias_minus_qfrc_passive_v1",
            "forward_call_count": self.forward_calls,
            "mj_step_call_count": 0,
        }

    def close(self):
        assert not self.closed
        self.close_calls += 1
        self.closed = True
        return {
            "schema_version": "libero-source-gravity-model-close-v1",
            "profile_id": self.profile_id,
            "model_identity_sha256": self.model_identity_sha256,
            "source_xml_sha256": self.source_xml_sha256,
            "source_closure_digest": self.source_closure_digest,
            "model_created": True,
            "forward_call_count": self.forward_calls,
            "mj_step_call_count": 0,
            "closed": True,
            "model_released": True,
            "data_released": True,
        }


class _ImportTripwire(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        del path, target
        if fullname.split(".", 1)[0].lower() in _FORBIDDEN_ROOTS:
            raise AssertionError(f"forbidden provider/runtime import during D01 S1: {fullname}")
        return None


class _Id:
    def __init__(self, value: int):
        self.id = value


class _World:
    """Explicit source fixture and low-level primitive witness for S1 only."""
    def __init__(self):
        self.calls = {name: 0 for name in ("compile", "reset", "step1", "step", "forward")}
        self.last_model = None
        self.last_data = None
        self.fail_compile = None
        self.fail_step_after = None
        self.fail_forward = None
        self.contact_pair = None
        self.partial_ctrl_after = None
        self.ctrl_write_count = 0
        self.bad_joint_address = None
        self.closes = 0
        self.last_compile_xml = None
        self.last_assets = None
        self.joint_excursion_at_step = None
        self.warning_at_step = None
        self.enable_panda_kinematics = False


class _Contact:
    def __init__(self, geom1: int, geom2: int):
        self.geom1, self.geom2 = geom1, geom2


class _FaultableVector:
    def __init__(self, values: np.ndarray, world: _World):
        self.values = np.asarray(values, dtype=np.float64).copy()
        self.world = world

    def __getitem__(self, key):
        return self.values[key]

    def __setitem__(self, key, value):
        threshold = self.world.partial_ctrl_after
        if threshold is not None and self.world.ctrl_write_count >= threshold:
            raise RuntimeError("synthetic partial actuator control write")
        self.world.ctrl_write_count += 1
        self.values[key] = value

    def copy(self):
        return self.values.copy()

    def __array__(self, dtype=None):
        return np.asarray(self.values, dtype=dtype)


def _floats(raw: str | None, count: int, default: tuple[float, ...]) -> tuple[float, ...]:
    if raw is None:
        return default
    values = tuple(float(value) for value in raw.split())
    if len(values) != count or not np.isfinite(values).all():
        raise ValueError(f"fake MuJoCo source field expected {count} finite values")
    return values


class _FakeModel:
    def __init__(self, xml: str, world: _World):
        root = ET.fromstring(xml)
        worldbody = root.find("worldbody")
        if worldbody is None:
            raise ValueError("synthetic source omitted worldbody")
        option = root.find("option")
        self.opt = types.SimpleNamespace(
            timestep=float(option.get("timestep", "0.002")) if option is not None else 0.002,
        )
        self._world = world
        joint_defaults = {}
        for default in root.iter("default"):
            class_name = default.get("class")
            joint_default = default.find("joint")
            if class_name and joint_default is not None:
                joint_defaults[class_name] = dict(joint_default.attrib)
        self._joint_ids: dict[str, int] = {}
        self._body_ids: dict[str, int] = {"world": 0}
        self._site_ids: dict[str, int] = {}
        self._geom_ids: dict[str, int] = {}
        self._actuator_ids: dict[str, int] = {}
        self._joint_body: list[int] = []
        self._body_nodes: list[ET.Element | None] = [None]
        self._site_body: list[int] = []
        self._site_nodes: list[ET.Element] = []
        self._free_by_body: dict[int, tuple[int, int]] = {}
        self._body_children: dict[int, list[int]] = {0: []}

        self.body_parentid = np.asarray([0], dtype=np.int32)
        self.body_pos = np.zeros((1, 3), dtype=np.float64)
        self.body_quat = np.asarray([[1.0, 0.0, 0.0, 0.0]], dtype=np.float64)
        body_parents = [0]
        body_positions = [(0.0, 0.0, 0.0)]
        body_quaternions = [(1.0, 0.0, 0.0, 0.0)]

        def visit_body(node: ET.Element, parent: int) -> None:
            name = node.get("name")
            body_id = len(self._body_nodes)
            if name:
                if name in self._body_ids:
                    raise ValueError(f"duplicate fake body name {name}")
                self._body_ids[name] = body_id
            self._body_nodes.append(node)
            body_parents.append(parent)
            body_positions.append(_floats(node.get("pos"), 3, (0.0, 0.0, 0.0)))
            body_quaternions.append(_floats(node.get("quat"), 4, (1.0, 0.0, 0.0, 0.0)))
            self._body_children.setdefault(parent, []).append(body_id)
            self._body_children[body_id] = []
            joints = [*node.findall("joint"), *node.findall("freejoint")]
            for joint in joints:
                jname = joint.get("name")
                if not jname or jname in self._joint_ids:
                    raise ValueError(f"missing or duplicate fake joint name: {jname}")
                self._joint_ids[jname] = len(self._joint_body)
                self._joint_body.append(body_id)
            for site in node.findall("site"):
                sname = site.get("name")
                if sname:
                    if sname in self._site_ids:
                        raise ValueError(f"duplicate fake site name {sname}")
                    self._site_ids[sname] = len(self._site_body)
                    self._site_body.append(body_id)
                    self._site_nodes.append(site)
            for geom in node.findall("geom"):
                gname = geom.get("name")
                if gname:
                    if gname in self._geom_ids:
                        raise ValueError(f"duplicate fake geom name {gname}")
                    self._geom_ids[gname] = len(self._geom_ids)
            for child in node.findall("body"):
                visit_body(child, body_id)

        for body in worldbody.findall("body"):
            visit_body(body, 0)
        # Geoms directly under worldbody are also part of the model inventory.
        for geom in worldbody.findall("geom"):
            gname = geom.get("name")
            if gname:
                self._geom_ids.setdefault(gname, len(self._geom_ids))
        self.body_parentid = np.asarray(body_parents, dtype=np.int32)
        self.body_pos = np.asarray(body_positions, dtype=np.float64)
        self.body_quat = np.asarray(body_quaternions, dtype=np.float64)

        joint_nodes: list[ET.Element] = []
        for body in worldbody.iter("body"):
            joint_nodes.extend(body.findall("joint"))
            joint_nodes.extend(body.findall("freejoint"))
        self.njnt = len(joint_nodes)
        self.jnt_type = np.zeros(self.njnt, dtype=np.int32)
        self.jnt_axis = np.zeros((self.njnt, 3), dtype=np.float64)
        self.jnt_qposadr = np.zeros(self.njnt, dtype=np.int32)
        self.jnt_dofadr = np.zeros(self.njnt, dtype=np.int32)
        self.jnt_limited = np.zeros(self.njnt, dtype=np.uint8)
        self.jnt_range = np.zeros((self.njnt, 2), dtype=np.float64)
        self.jnt_bodyid = np.asarray(self._joint_body, dtype=np.int32)
        qpos_cursor = dof_cursor = 0
        for jid, node in enumerate(joint_nodes):
            inherited = joint_defaults.get(node.get("class"), {})
            kind = "free" if node.tag == "freejoint" else node.get("type", inherited.get("type", "hinge"))
            self.jnt_type[jid] = {"free": 0, "hinge": 1, "slide": 2}.get(kind, 99)
            self.jnt_axis[jid] = _floats(
                node.get("axis", inherited.get("axis")), 3, (0.0, 0.0, 1.0),
            )
            self.jnt_qposadr[jid], self.jnt_dofadr[jid] = qpos_cursor, dof_cursor
            if kind == "free":
                self._free_by_body[self._joint_body[jid]] = (qpos_cursor, dof_cursor)
                qpos_cursor += 7
                dof_cursor += 6
            else:
                qpos_cursor += 1
                dof_cursor += 1
            raw_range = node.get("range", inherited.get("range"))
            if raw_range is not None:
                self.jnt_range[jid] = _floats(raw_range, 2, (0.0, 0.0))
                self.jnt_limited[jid] = node.get("limited", inherited.get("limited", "auto")) != "false"
        self.nq, self.nv, self.na = qpos_cursor, dof_cursor, 0
        self.qpos0 = np.zeros(self.nq, dtype=np.float64)
        for qpos, _ in self._free_by_body.values():
            self.qpos0[qpos + 3] = 1.0

        actuator_root = root.find("actuator")
        actuator_nodes = [] if actuator_root is None else list(actuator_root)
        self.nu = len(actuator_nodes)
        self.actuator_ctrlrange = np.zeros((self.nu, 2), dtype=np.float64)
        self.actuator_ctrllimited = np.zeros(self.nu, dtype=np.uint8)
        self.actuator_trntype = np.zeros(self.nu, dtype=np.int32)
        self.actuator_trnid = np.full((self.nu, 2), -1, dtype=np.int32)
        # The Core adapter admits drive units from public compiled actuator
        # metadata. These synthetic arrays model only the MuJoCo public fields
        # consumed by that admission path; no solver or integration is faked
        # above the leaf primitive boundary.
        self.actuator_gaintype = np.zeros(self.nu, dtype=np.int32)
        self.actuator_biastype = np.zeros(self.nu, dtype=np.int32)
        self.actuator_gainprm = np.zeros((self.nu, 10), dtype=np.float64)
        self.actuator_biasprm = np.zeros((self.nu, 10), dtype=np.float64)
        self.actuator_gear = np.zeros((self.nu, 6), dtype=np.float64)
        self.actuator_dyntype = np.zeros(self.nu, dtype=np.int32)
        for aid, actuator in enumerate(actuator_nodes):
            name = actuator.get("name")
            if not name or name in self._actuator_ids:
                raise ValueError(f"missing or duplicate fake actuator name {name}")
            self._actuator_ids[name] = aid
            self.actuator_ctrlrange[aid] = _floats(
                actuator.get("ctrlrange"), 2, (-np.inf, np.inf),
            )
            self.actuator_ctrllimited[aid] = actuator.get("ctrllimited", "auto") != "false" and actuator.get("ctrlrange") is not None
            self.actuator_gear[aid, 0] = _floats(actuator.get("gear"), 1, (1.0,))[0]
            if actuator.tag == "motor":
                self.actuator_gainprm[aid, 0] = 1.0
            elif actuator.tag == "position":
                self.actuator_biastype[aid] = 1  # fixed-gain affine servo
                self.actuator_gainprm[aid, 0] = float(actuator.get("kp", "1"))
                self.actuator_biasprm[aid, 1] = -self.actuator_gainprm[aid, 0]
                self.actuator_biasprm[aid, 2] = -float(actuator.get("kv", "0"))
            joint_name = actuator.get("joint")
            if joint_name in self._joint_ids:
                self.actuator_trnid[aid, 0] = self._joint_ids[joint_name]
        self.nbody, self.nsite, self.ngeom = len(self._body_nodes), len(self._site_body), len(self._geom_ids)
        self.actuator_forcelimited = np.zeros(self.nu, dtype=np.uint8)
        self.actuator_forcerange = np.zeros((self.nu, 2), dtype=np.float64)
        self._joint_nodes = joint_nodes
        self._actuator_nodes = actuator_nodes
        self._site_lookup = {node.get("name"): (self._site_body[i], node)
                             for i, node in enumerate(self._site_nodes)}
        self._panda_kinematics = None
        if world.enable_panda_kinematics and "gripper0_grip_site" in self._site_ids:
            from task_env.controllers.canonical import PandaKinematics
            from task_env.controllers.canonical.kinematics import derive_panda_tcp_profile_v2
            profile = derive_panda_tcp_profile_v2(
                xml, tcp_id="libero-mounted-panda-v1/gripper0-grip-site-v1",
                hand_frame_id="robot0_right_hand", site_name="gripper0_grip_site",
            )
            self._panda_kinematics = PandaKinematics(
                xml, tcp_profile=profile, native_prefix="robot0_", base_body_id="robot0_link0",
            )

    @classmethod
    def from_xml_string(cls, xml: str, *, assets=None):
        world = _FAKE_WORLD
        world.calls["compile"] += 1
        world.last_compile_xml = xml
        world.last_assets = dict(assets or {})
        if world.fail_compile:
            raise RuntimeError(world.fail_compile)
        model = cls(xml, world)
        if world.bad_joint_address is not None:
            joint_id = model._joint_ids[world.bad_joint_address]
            model.jnt_qposadr[joint_id] += 1
        world.last_model = model
        return model

    def joint(self, name: str): return _Id(self._joint_ids.get(name, -1))
    def body(self, name: str): return _Id(self._body_ids.get(name, -1))
    def site(self, name: str): return _Id(self._site_ids.get(name, -1))
    def actuator(self, name: str): return _Id(self._actuator_ids.get(name, -1))


class _FakeData:
    def __init__(self, model: _FakeModel):
        self._model = model
        self.qpos = model.qpos0.copy()
        self.qvel = np.zeros(model.nv, dtype=np.float64)
        self.qacc = np.zeros(model.nv, dtype=np.float64)
        self.ctrl = _FaultableVector(np.zeros(model.nu, dtype=np.float64), model._world)
        self.act = np.zeros(model.na, dtype=np.float64)
        self.time = 0.0
        self.xpos = np.zeros((model.nbody, 3), dtype=np.float64)
        self.xquat = np.zeros((model.nbody, 4), dtype=np.float64)
        if model.nbody: self.xquat[:, 0] = 1.0
        self.site_xpos = np.zeros((model.nsite, 3), dtype=np.float64)
        self.site_xmat = np.tile(np.eye(3, dtype=np.float64).reshape(1, 9), (model.nsite, 1))
        self.contact: list[_Contact] = []
        self.ncon = 0
        self.warning = [types.SimpleNamespace(number=0) for _ in range(7)]
        self._write_counter = 0
        self._world = model._world
        self._world.last_data = self


_FAKE_WORLD = _World()


def _quat_matrix(q):
    w, x, y, z = (float(value) for value in q)
    return np.asarray([
        [1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
        [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
        [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)],
    ], dtype=np.float64)


def _fake_api(monkeypatch):
    """Install a marked fake public API while retaining exact pinned file hashes."""
    spec = importlib.util.find_spec("mujoco")
    if spec is None or spec.origin is None:
        raise RuntimeError("the frozen MuJoCo package files are not installed for identity readback")
    package_file = Path(spec.origin).resolve()
    package_dir = package_file.parent
    binding = next(package_dir.glob("_functions*.so"), None)
    library = package_dir / "libmujoco.so.3.8.1"
    header = package_dir / "include/mujoco/mujoco.h"
    if not all(path.is_file() for path in (binding, library, header)):
        raise RuntimeError("pinned MuJoCo API identity files are incomplete")
    fake = types.ModuleType("mujoco")
    fake.__file__ = str(package_file)
    fake.__path__ = [str(package_dir)]
    fake.__spec__ = spec
    fake.__r07c_s1_synthetic_fixture__ = True
    fake.__version__ = "3.8.1"
    fake.mj_version = lambda: 3008001
    fake.mj_versionString = lambda: "3.8.1"
    fake.MjModel = types.SimpleNamespace(from_xml_string=_FakeModel.from_xml_string)
    fake.MjData = _FakeData
    fake.mjtJoint = types.SimpleNamespace(mjJNT_FREE=0, mjJNT_HINGE=1, mjJNT_SLIDE=2)
    fake.mjtTrn = types.SimpleNamespace(mjTRN_JOINT=0)
    fake.mjtGain = types.SimpleNamespace(mjGAIN_FIXED=0)
    fake.mjtBias = types.SimpleNamespace(mjBIAS_NONE=0, mjBIAS_AFFINE=1)
    fake.mjtDyn = types.SimpleNamespace(mjDYN_NONE=0)
    fake.mjtObj = types.SimpleNamespace(mjOBJ_JOINT=1, mjOBJ_BODY=2, mjOBJ_SITE=3, mjOBJ_ACTUATOR=4, mjOBJ_GEOM=5)

    def name2id(model, kind, name):
        table = {
            fake.mjtObj.mjOBJ_JOINT: model._joint_ids,
            fake.mjtObj.mjOBJ_BODY: model._body_ids,
            fake.mjtObj.mjOBJ_SITE: model._site_ids,
            fake.mjtObj.mjOBJ_ACTUATOR: model._actuator_ids,
            fake.mjtObj.mjOBJ_GEOM: model._geom_ids,
        }.get(kind)
        return -1 if table is None else table.get(name, -1)

    fake.mj_name2id = name2id
    fake.mj_resetData = lambda model, data: _reset_data(model, data)
    fake.mj_step1 = lambda model, data: _count_call(data, "step1")
    fake.mj_step = lambda model, data: _step(model, data)
    fake.mj_forward = lambda model, data: _forward(model, data)
    fake.mju_mat2Quat = _mat2quat
    functions = types.ModuleType("mujoco._functions")
    functions.__file__ = str(binding)
    functions.__spec__ = importlib.util.spec_from_file_location("mujoco._functions", binding)
    monkeypatch.setitem(sys.modules, "mujoco", fake)
    monkeypatch.setitem(sys.modules, "mujoco._functions", functions)
    real_open = builtins.open

    def fake_open(file, *args, **kwargs):
        if os.fspath(file) == "/proc/self/maps":
            return io.StringIO(f"7f000000-7f001000 r-xp 00000000 00:00 0 {library}\n")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(sys, "meta_path", [_ImportTripwire(), *sys.meta_path])
    return fake


def _count_call(data, name):
    data._world.calls[name] += 1
    if name == "step1":
        return


def _reset_data(model: _FakeModel, data: _FakeData):
    model._world.calls["reset"] += 1
    data.qpos[:] = model.qpos0
    data.qvel[:] = 0.0
    data.qacc[:] = 0.0
    data.ctrl[:] = 0.0
    data._world.ctrl_write_count = 0
    data.act[:] = 0.0
    data.time = 0.0
    data.contact = []
    data.ncon = 0
    for warning in data.warning:
        warning.number = 0


def _step(model: _FakeModel, data: _FakeData):
    world = model._world
    world.calls["step"] += 1
    if world.fail_step_after is not None and world.calls["step"] > world.fail_step_after:
        raise RuntimeError("synthetic native-step leaf fault")
    dt = model.opt.timestep
    for aid, joint_id in enumerate(model.actuator_trnid[:, 0]):
        if joint_id < 0:
            continue
        qpos = int(model.jnt_qposadr[joint_id])
        dof = int(model.jnt_dofadr[joint_id])
        actuator = model._actuator_nodes[aid]
        if actuator.tag == "position":
            error = float(data.ctrl[aid] - data.qpos[qpos])
            data.qvel[dof] += (error * 18.0 - data.qvel[dof] * 3.0) * dt
        else:
            data.qvel[dof] += float(data.ctrl[aid]) * dt * 1.2
        data.qpos[qpos] += data.qvel[dof] * dt
        if model.jnt_limited[joint_id]:
            low, high = model.jnt_range[joint_id]
            data.qpos[qpos] = float(np.clip(data.qpos[qpos], low, high))
    excursion = world.joint_excursion_at_step
    if excursion is not None and world.calls["step"] == excursion[2]:
        joint_name, value, _step_number = excursion
        joint_id = model._joint_ids[joint_name]
        data.qpos[int(model.jnt_qposadr[joint_id])] = float(value)
    if world.warning_at_step is not None and world.calls["step"] == world.warning_at_step:
        data.warning[0].number = 1
    data.time += dt


def _forward(model: _FakeModel, data: _FakeData):
    world = model._world
    world.calls["forward"] += 1
    if world.fail_forward:
        raise RuntimeError(world.fail_forward)
    data.xpos[:] = 0.0
    data.xquat[:] = (1.0, 0.0, 0.0, 0.0)
    for body_id in range(1, model.nbody):
        parent = int(model.body_parentid[body_id])
        position = model.body_pos[body_id].copy()
        quaternion = model.body_quat[body_id].copy()
        free = model._free_by_body.get(body_id)
        if free is not None:
            qpos, _ = free
            position = data.qpos[qpos:qpos + 3].copy()
            quaternion = data.qpos[qpos + 3:qpos + 7].copy()
        data.xpos[body_id] = data.xpos[parent] + _quat_matrix(data.xquat[parent]) @ position
        data.xquat[body_id] = quaternion
    for index, (body_id, node) in enumerate(model._site_lookup.values()):
        local_position = np.asarray(_floats(node.get("pos"), 3, (0.0, 0.0, 0.0)))
        data.site_xpos[index] = data.xpos[body_id] + _quat_matrix(data.xquat[body_id]) @ local_position
        data.site_xmat[index] = _quat_matrix(data.xquat[body_id]).reshape(9)
    if model._panda_kinematics is not None:
        q = np.asarray([
            data.qpos[int(model.jnt_qposadr[model._joint_ids[f"robot0_joint{joint}"]])]
            for joint in range(1, 8)
        ], dtype=np.float64)
        transform, _ = model._panda_kinematics.fk_jacobian(q)
        site_id = model._site_ids["gripper0_grip_site"]
        data.site_xpos[site_id] = transform[:3, 3]
        data.site_xmat[site_id] = transform[:3, :3].reshape(9)
    data.contact = []
    pair = world.contact_pair(model, data) if callable(world.contact_pair) else world.contact_pair
    if pair is not None:
        left, right = pair
        if type(left) is int and type(right) is int:
            left_ids, right_ids = [left], [right]
        else:
            left_ids = [value for name, value in model._geom_ids.items()
                        if name.startswith(f"libero_contact_{left}_")]
            right_ids = [value for name, value in model._geom_ids.items()
                         if name.startswith(f"libero_contact_{right}_")]
        if left_ids and right_ids:
            data.contact = [_Contact(left_ids[0], right_ids[0])]
    data.ncon = len(data.contact)


def _mat2quat(out: np.ndarray, matrix: np.ndarray):
    from task_env.utils.rotation import matrix_to_quat_wxyz
    out[:] = matrix_to_quat_wxyz(np.asarray(matrix, dtype=np.float64).reshape(3, 3))


def _candidate(monkeypatch, *, horizon=4):
    from bench_deploy.libero.selected_candidate import (
        DEFAULT_INSTALL_ROOT, DEFAULT_OUTPUT_ROOT, build_libero_selected_candidate,
    )
    xml_path = Path(os.environ["R07C_COMPOSED_MJCF"])
    xml = xml_path.read_bytes()
    digest = __import__("hashlib").sha256(xml).hexdigest()
    env = build_libero_selected_candidate(
        xml=xml, composed_mjcf_sha256=digest, install_root=DEFAULT_INSTALL_ROOT,
        composition_plan_path=DEFAULT_OUTPUT_ROOT / "source/composition_plan.json",
        horizon=horizon,
    )
    return env


def _synthetic_mixed_candidate(monkeypatch, *, horizon=4, integrator="implicitfast"):
    """Build a different-name, different-dimension candidate through production owners."""
    import hashlib
    from gymnasium.spaces import Box, Dict

    from task_env.artifacts import (
        ActionIntent, EntityDefinition, ExecutionSpec, InitializationContract,
        PoseWorld, RequiredCapabilitySet, ResetSampleV1, SemanticDefinition,
        TaskArtifact, Timebase, WorldDefinition,
    )
    from task_env.assembly.source import TaskSceneSource
    from task_env.controllers.canonical.contracts import (
        AppliedMixedActuatorCommandV1, ControlGroupActionV1,
        MixedActuatorChannelV1, MixedActuatorCommandV1, MixedActuatorPlanV1,
        StructuredActionRequestV1, digest,
    )
    from task_env.environment.configuration import resolve_env_config
    from task_env.environment.types import TaskEvaluation
    from task_env.runtime.sessions.source import ExecutionSourceReceiptV1, RuntimeSource
    from task_env.tasks.reference_env import ReferenceTaskBinding, SelectedReferenceEnv

    _fake_api(monkeypatch)
    _FAKE_WORLD.contact_pair = lambda model, data: (
        model._geom_ids["anchor_collision"], model._geom_ids["payload_collision"],
    )
    xml = f'''<mujoco model="synthetic_three_channel_fixture">
      <compiler angle="radian"/>
      <option timestep="0.002" integrator="{integrator}"/>
      <worldbody>
        <body name="anchor_body" pos="0 0 0">
          <joint name="hinge_orchid" type="hinge" range="-2 2" limited="true"/>
          <joint name="hinge_cobalt" type="hinge" range="-1 1" limited="true"/>
          <geom name="anchor_collision" type="sphere" size="0.04"/>
        </body>
        <body name="slider_carriage" pos="0.1 0 0">
          <joint name="slide_fern" type="slide" axis="1 0 0" range="0 0.2" limited="true"/>
          <geom name="carriage_collision" type="sphere" size="0.02"/>
        </body>
        <body name="payload_body" pos="0.3 0 0.1">
          <freejoint name="payload_free"/>
          <geom name="payload_collision" type="sphere" size="0.03"/>
        </body>
      </worldbody>
      <actuator>
        <motor name="motor_orchid" joint="hinge_orchid" ctrllimited="true" ctrlrange="-2 2"/>
        <motor name="motor_cobalt" joint="hinge_cobalt" ctrllimited="true" ctrlrange="-1 1"/>
        <position name="servo_fern" joint="slide_fern" kp="25" kv="1" ctrllimited="true" ctrlrange="0 0.2"/>
      </actuator>
    </mujoco>'''.encode("utf-8")
    artifact = TaskArtifact(
        "task-artifact-v0", "synthetic-three-channel-v1", "synthetic-contact-motion-v1", "fixture-v1",
        WorldDefinition(
            "world-v0", "SI_right_handed_z_up_wxyz",
            (
                EntityDefinition("anchor", "scene", "asset:synthetic-anchor-v1", (),
                                 ("torque_orchid", "torque_cobalt"), "synthetic-rigid", "source-collision", {}),
                EntityDefinition("carriage", "movable", "asset:synthetic-carriage-v1", (),
                                 ("slide_fern",), "synthetic-rigid", "source-collision", {}),
                EntityDefinition("payload", "movable", "asset:synthetic-payload-v1", (), (),
                                 "synthetic-rigid", "source-collision", {}),
            ),
            ActionIntent("absolute_joint", None, "none", "arm_joint_position_and_gripper"),
            ("joint_state_query", "body_pose_query", "contact_detection"), (),
        ),
        InitializationContract(
            "initialization-v0", {"payload": PoseWorld((0.3, 0.0, 0.1), (1.0, 0.0, 0.0, 0.0))},
            {"torque_orchid": 0.0, "torque_cobalt": 0.0, "slide_fern": 0.03}, (),
            "source_bound_named_reset_sample", "synthetic_row_v1", 0,
        ),
        SemanticDefinition(
            "semantics-v0", "synthetic_contact_semantics_v1", ("anchor", "payload"),
            ("torque_orchid", "torque_cobalt", "slide_fern"), {}, "synthetic_bounded_motion",
        ),
        Timebase(0.002, 2, 0.004),
        RequiredCapabilitySet((
            "joint_position_actuation", "joint_state_query", "body_pose_query", "contact_detection",
        )),
    )
    source_id = "synthetic-three-channel-source-v1"
    receipt = ExecutionSourceReceiptV1.create(
        source_id=source_id, canonical_xml=xml, importer_xml=xml,
        closure_files={"canonical-source.xml": xml},
    )
    scene_source = TaskSceneSource(xml.decode(), receipt.snapshot_root, source_id)
    controller_identity = hashlib.sha256(b"synthetic-controller-v1").hexdigest()
    config = resolve_env_config(
        task_uid=artifact.task_id, scene_uid="synthetic-scene-v1",
        runtime={
            "backend": "cpu", "physics_dt": 0.002, "control_substeps": 2,
            "integrator": integrator, "prewarm": False,
        },
        render={"camera_obs": False}, episode={"horizon": horizon, "ignore_done": False},
        success_definition="synthetic_bounded_motion",
    )

    class _SyntheticController:
        identity = controller_identity
        profile_id = "synthetic-three-channel-controller-v1"
        plan_identity_hash = ""

        def reset(self, _state):
            return None

        def identity_mapping(self):
            return {
                "schema_version": "synthetic-controller-v1",
                "identity_sha256": self.identity,
                "profile_id": self.profile_id,
                "components": ["torque_orchid_Nm", "torque_cobalt_Nm", "slide_fern_m"],
                "hold_policy": "zero_order_hold_per_control_interval_v1",
            }

        def compute_target(self, values, state, *, task_artifact_hash, source_id,
                           source_closure_digest, provider_materialization_id,
                           episode_id, reset_sample_id, state_revision):
            values = tuple(float(value) for value in values)
            return MixedActuatorCommandV1(
                "mixed-actuator-command-v1", self.plan_identity_hash,
                task_artifact_hash, source_id, source_closure_digest, self.identity,
                provider_materialization_id, episode_id, reset_sample_id,
                int(state.control_step), int(state_revision), float(state.simulation_time),
                {"torque_orchid": values[0], "torque_cobalt": values[1], "slide_fern": values[2]},
                {"torque_orchid": "N*m", "torque_cobalt": "N*m", "slide_fern": "m"},
            )

    active = {}
    reset_receipts = {}
    action_schema = {
        "schema_id": "synthetic-three-channel-action-v1", "schema_version": 1,
        "controller_kind": "mixed_actuator_v1", "dimension": 3,
        "components": ("torque_orchid_Nm", "torque_cobalt_Nm", "slide_fern_m"),
    }
    component_names = action_schema["components"]

    def build_value(provider, backend):
        if (provider, backend) != ("mujoco", "cpu"):
            raise ValueError("synthetic fixture admits MuJoCo CPU only")
        controller = _SyntheticController()
        plan = MixedActuatorPlanV1(
            "mixed-actuator-plan-v1", artifact.identity_hash, source_id,
            receipt.source_closure_digest, controller.identity,
            (
                MixedActuatorChannelV1(
                    "torque_orchid", "motor_orchid", "hinge_orchid", "joint_torque", "N*m", (-2.0, 2.0),
                ),
                MixedActuatorChannelV1(
                    "torque_cobalt", "motor_cobalt", "hinge_cobalt", "joint_torque", "N*m", (-1.0, 1.0),
                ),
                MixedActuatorChannelV1(
                    "slide_fern", "servo_fern", "slide_fern", "joint_position", "m", (0.0, 0.2),
                ),
            ),
        )
        controller.plan_identity_hash = plan.identity_hash
        source = RuntimeSource(
            task_artifact_hash=artifact.identity_hash, scene_source=scene_source,
            joints={"torque_orchid": "hinge_orchid", "torque_cobalt": "hinge_cobalt", "slide_fern": "slide_fern"},
            bodies={"anchor": "anchor_body", "payload": "payload_body"}, frames={},
            free_joints={"payload": "payload_free"}, joint_targets={}, open_actuators=(),
            composition=None, config=config, scene=None, agents=(), objects=("payload",),
            source_closure_digest=receipt.source_closure_digest,
            execution_source_receipt=receipt,
            torque_actuators={"torque_orchid": "motor_orchid", "torque_cobalt": "motor_cobalt"},
            position_actuators={"slide_fern": "servo_fern"},
            actuator_units={"motor_orchid": "N*m", "motor_cobalt": "N*m", "servo_fern": "m"},
            contact_geom_groups={"anchor": ("anchor_collision",), "payload": ("payload_collision",)},
            mixed_actuator_plan=plan,
        )
        value = {
            "artifact": artifact, "source": source, "controller": controller,
            "selected_controller_kind": "mixed_actuator_v1", "solution": None,
            "construction_id": digest({"artifact": artifact.identity_hash, "plan": plan.identity_hash}),
            "action_schema": action_schema,
            "action_space": Box(-np.inf, np.inf, (3,), dtype=np.float64),
            "observation_space": Dict({
                "state": Dict({
                    "joint_position": Box(-np.inf, np.inf, (3,), dtype=np.float32),
                    "boundary_identity_sha256": Box(0, 255, (32,), dtype=np.uint8),
                }),
                "privileged_state": Dict({
                    "payload_body_pose": Box(-np.inf, np.inf, (1, 7), dtype=np.float32),
                }),
            }),
            "reset_realizations": reset_receipts,
        }
        active["value"] = value
        return value

    def reset_sample_with_options(task_artifact, seed, options, source):
        if task_artifact.identity_hash != artifact.identity_hash or source.scene_source.source_id != source_id:
            raise ValueError("synthetic reset source/artifact identity mismatch")
        if type(seed) is not int or seed < 0:
            raise ValueError("synthetic reset seed must be a nonnegative integer")
        pose = PoseWorld((0.3, 0.0, 0.1), (1.0, 0.0, 0.0, 0.0))
        sample = ResetSampleV1.create(
            schema_version="reset-sample-v1", task_artifact_hash=artifact.identity_hash,
            source_id=source_id, source_closure_digest=source.source_closure_digest,
            sampler_id="synthetic-source-bound-row-v1", sampler_version="v1",
            task_seed=seed, init_row_index=0,
            init_row_sha256=hashlib.sha256(f"synthetic-row:{seed}".encode()).hexdigest(),
            joint_position={"torque_orchid": 0.0, "torque_cobalt": 0.0, "slide_fern": 0.03},
            joint_velocity={"torque_orchid": 0.0, "torque_cobalt": 0.0, "slide_fern": 0.0},
            sampled_poses_world={"payload": pose}, poses_world={"payload": pose},
            free_joint_velocity={"payload": (0.0,) * 6},
            free_joint_velocity_frame="mujoco_world_linear_local_angular_v1",
            fixture_pose_world={}, simulation_time_s=0.0,
            velocity_policy="named_qvel_and_free_joint_qvel_v1",
            control_policy="named_mixed_actuator_channels_by_source_v1",
            initialization_order=(
                "sample_source_properties", "native_preprocess", "sample_task_placements",
                "restore_source_bound_state", "forward_derived_state",
            ),
            settle_steps=0,
        )
        reset_receipts[sample.sample_id] = {
            "schema_version": "synthetic-reset-realization-v1",
            "source_id": source_id, "source_closure_digest": source.source_closure_digest,
            "reset_sample_id": sample.sample_id, "seed": seed,
            "synthetic_fixture": True,
        }
        return sample

    def prepare(env, action, state):
        vector = np.asarray(action, dtype=np.float64)
        if vector.shape != (3,) or not np.isfinite(vector).all():
            raise ValueError("synthetic action must be a finite three-channel vector")
        values = tuple(float(value) for value in vector)
        source = env.value["source"]
        plan = source.mixed_actuator_plan
        request = StructuredActionRequestV1(
            "structured-action-request-v1", source.execution_source_receipt.canonical_xml_sha256,
            plan.identity_hash, (ControlGroupActionV1(
                "control-group-action-v1", "anchor", "mixed-drive", action_schema["schema_id"], values,
            ),),
        )
        target = env.controller.compute_target(
            values, state, task_artifact_hash=env.artifact.identity_hash,
            source_id=source.scene_source.source_id, source_closure_digest=source.source_closure_digest,
            provider_materialization_id=env.session.provider_materialization_id,
            episode_id=env.session.episode_id, reset_sample_id=env.sample.sample_id,
            state_revision=env.session.state_revision,
        )
        return {
            "action_values": values, "universal_action": values, "request": request, "target": target,
            "writer_control": {
                "writer_id": "synthetic-three-channel-writer-v1",
                "action_schema_id": action_schema["schema_id"],
                "components": component_names,
                "groups": ({"entity_id": "anchor", "group_id": "mixed-drive",
                            "action_components": component_names},),
                "requested_action": {"schema_version": action_schema["schema_id"],
                                     "values": values, "unit": "N*m,N*m,m"},
                "canonical_action": {"schema_version": "synthetic-canonical-action-v1",
                                     "interpreted_values": values,
                                     "controller_identity": env.controller.identity,
                                     "hold_policy": "zero_order_hold_per_control_interval_v1"},
            },
        }

    def observe(env, state):
        source = env.value["source"]
        contact = env.session.read_contact_summary_v2((("anchor", "payload"),))
        contact_mapping = {
            "schema_version": contact.schema_version,
            "source_id": contact.source_id,
            "source_closure_digest": contact.source_closure_digest,
            "provider_materialization_id": contact.provider_materialization_id,
            "episode_id": contact.episode_id,
            "reset_sample_id": contact.reset_sample_id,
            "control_step": contact.control_step,
            "state_revision": contact.state_revision,
            "simulation_time_s": contact.simulation_time_s,
            "requested_pairs": [list(pair) for pair in contact.requested_pairs],
            "covered_pairs": [list(pair) for pair in contact.covered_pairs],
            "pair_counts": dict(contact.pair_counts),
            "geom_groups": {name: list(values) for name, values in contact.geom_groups.items()},
            "status": contact.status, "reason": contact.reason,
        }
        boundary = {
            "source_id": source.scene_source.source_id,
            "source_closure_digest": source.source_closure_digest,
            "provider_materialization_id": env.session.provider_materialization_id,
            "episode_id": env.session.episode_id,
            "reset_sample_id": env.sample.sample_id,
            "control_step": int(state.control_step),
            "state_revision": int(env.session.state_revision),
            "simulation_time_s": float(state.simulation_time),
        }
        boundary_hash = digest(boundary)
        pose = state.pose_world["payload"]
        observation = {
            "state": {
                "joint_position": np.asarray([
                    state.joint_position[name] for name in ("torque_orchid", "torque_cobalt", "slide_fern")
                ], dtype=np.float32),
                "boundary_identity_sha256": np.frombuffer(bytes.fromhex(boundary_hash), dtype=np.uint8).copy(),
            },
            "privileged_state": {
                "payload_body_pose": np.asarray([(*pose.position, *pose.quaternion_wxyz)], dtype=np.float32),
            },
        }
        context = {
            "schema_version": "synthetic-task-observation-context-v1",
            **boundary, "state_boundary_identity_sha256": boundary_hash,
            "contact_summary_v2": contact_mapping,
            "task_semantics": {"schema_version": "synthetic-contact-semantic-v1", "contact_available": contact.status == "available"},
        }
        info = {**boundary, "contact_summary_v2": contact_mapping,
                "boundary_context_v1": context, "state_boundary_identity_sha256": boundary_hash,
                "synthetic_task_context": {"fixture": True}}
        return observation, info, TaskEvaluation(0.0, False, {"synthetic": True})

    def record_metadata(env):
        source = env.value["source"]
        context = {
            "schema_version": "synthetic-task-episode-context-v1",
            "task_artifact_identity_hash": env.artifact.identity_hash,
            "source_id": source.scene_source.source_id,
            "source_closure_digest": source.source_closure_digest,
            "provider_materialization_id": env.session.provider_materialization_id,
            "episode_id": env.session.episode_id,
            "reset_sample_id": env.sample.sample_id,
            "reset_sample_v1": env.sample.to_mapping(),
        }
        return {
            "env_metadata": {
                "env_name": "SelectedReferenceEnv.SyntheticMixedControlFixtureV1",
                "task_name": env.artifact.task_id, "task_version": env.artifact.artifact_version,
                "physics_dt": env.artifact.timebase.physics_dt,
                "control_substeps": env.artifact.timebase.control_substeps,
                "control_frequency": 1.0 / env.artifact.timebase.control_dt,
                "action_schema": {"schema_id": action_schema["schema_id"],
                                  "components": list(component_names), "units": ["N*m", "N*m", "m"]},
                "observation_schema": {"state.joint_position": "two hinge radians then one slide meter"},
                "provider": env.provider, "backend": env.backend,
                "evidence_class": "synthetic_fixture",
            },
            "universal_action_schema": {"version": action_schema["schema_id"],
                                        "dimension": 3, "components": list(component_names)},
            "resolved_config": {"provider": env.provider, "backend": env.backend,
                                "physics_dt": env.artifact.timebase.physics_dt,
                                "control_substeps": env.artifact.timebase.control_substeps,
                                "control_dt": env.artifact.timebase.control_dt,
                                "integrator": source.config.runtime.integrator,
                                "controller_profile_id": env.controller.profile_id,
                                "controller_identity": env.controller.identity,
                                "hold_policy": "zero_order_hold_per_control_interval_v1"},
            "control_plan": env.controller.identity_mapping(),
            "task_context": context,
            "candidate_identity": {"task_artifact_identity_hash": env.artifact.identity_hash,
                                   "source_id": source.scene_source.source_id,
                                   "source_closure_digest": source.source_closure_digest,
                                   "provider_materialization_id": env.session.provider_materialization_id,
                                   "controller_identity": env.controller.identity,
                                   "plan_identity_hash": source.mixed_actuator_plan.identity_hash},
        }

    def validate_compiled(session, value):
        receipt = session.compiled_layout_receipt
        plan = value["source"].mixed_actuator_plan
        if (receipt.get("schema_version") != "compiled-model-layout-v1"
                or receipt.get("plan_identity_hash") != plan.identity_hash
                or receipt.get("dimensions", {}).get("nu") != 3
                or set(receipt.get("named_actuator_channels", {})) != {item.semantic_id for item in plan.channels}
                or set(receipt.get("named_joint_addresses", {})) != set(value["source"].joints)):
            raise ValueError("synthetic pre-reset compiled receipt differs from its typed three-channel plan")
        return {"schema_version": "synthetic-pre-reset-validation-v1",
                "compiled_layout": receipt, "reset_not_yet_applied": True,
                "runtime_identity": session.runtime_identity}

    binding = ReferenceTaskBinding(
        build=lambda provider: build_value(provider, "cpu"),
        reset_sample=lambda task_artifact, seed: reset_sample_with_options(
            task_artifact, seed, {}, active["value"]["source"],
        ),
        evaluate=lambda _evidence, _semantics: None,
        object_poses=(("payload", "payload"),), external_actions=True,
        interval_mode="grouped", recorder_mode="canonical", reset_seed=lambda seed: seed,
        runtime_episode_identity=True, build_mixed_control_profile=build_value,
        reset_sample_with_options=reset_sample_with_options,
        prepare_mixed_control=prepare, observe_mixed_control=observe,
        mixed_record_metadata=record_metadata, pre_reset_session_validator=validate_compiled,
    )
    env = SelectedReferenceEnv.from_mixed_control_candidate(
        binding, provider="mujoco", backend="cpu", horizon=horizon,
    )
    return env


@pytest.mark.parametrize("integrator", ("implicitfast", "euler"))
def test_generic_mixed_actuator_admits_source_bound_cpu_integrators(
        monkeypatch, integrator):
    """Both admitted source integrators materialize through the shared Core Runtime."""
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _synthetic_mixed_candidate(monkeypatch, horizon=1, integrator=integrator)
    try:
        observation, info = env.reset(seed=51)
        assert env.value["source"].config.runtime.integrator == integrator
        assert info["control_step"] == 0
        assert env.session is not None
        assert observation["state"]["joint_position"].shape == (3,)
        _, _, _, _, step_info = env.step(np.asarray([0.0, 0.0, 0.03]))
        assert step_info["mixed_actuator_command_v1"]["channel_values"]["slide_fern"] == pytest.approx(0.03)
    finally:
        env.close()
    assert env.close_receipt["session_closed"] is True


def test_generic_mixed_actuator_rejects_unadmitted_source_integrator(monkeypatch):
    """An arbitrary MJCF integrator stays outside the generic strict CPU envelope."""
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _synthetic_mixed_candidate(monkeypatch, horizon=1, integrator="rk4")
    try:
        with pytest.raises(ValueError, match="implicitfast or euler integrator"):
            env.reset(seed=52)
        assert env.session is None
    finally:
        env.close()


def _read_synthetic_mixed_h5(path: Path):
    """Independent fixture reader for the generic public v3 boundary/control contract."""
    loaded = load_structured_control_records_h5(path)
    if loaded["observation_count"] != loaded["transition_count"] + 1:
        raise ValueError("synthetic H5 is missing a complete T+1 observation boundary")
    contexts = loaded["boundary_contexts"]
    if not isinstance(contexts, list) or len(contexts) != loaded["observation_count"]:
        raise ValueError("synthetic H5 is missing its owner-defined boundary context")
    for index, context in enumerate(contexts):
        if context.get("schema_version") != "synthetic-task-observation-context-v1":
            raise ValueError("synthetic H5 contains an unknown task context schema")
        contact = context.get("contact_summary_v2")
        if not isinstance(contact, dict):
            raise ValueError("synthetic H5 is missing the public contact query")
        for key in (
            "source_id", "source_closure_digest", "provider_materialization_id",
            "episode_id", "reset_sample_id", "control_step", "state_revision",
            "simulation_time_s",
        ):
            if contact.get(key) != context.get(key):
                raise ValueError(f"synthetic H5 contact identity is stale at {key}")
        if context.get("control_step") != index:
            raise ValueError("synthetic H5 boundary order is not contiguous")
    for index, transition in enumerate(loaded["structured_controls"]):
        if transition is None or len(transition.writer_controls) != 1:
            raise ValueError("synthetic H5 is missing a typed request/target/ack transition")
        writer = transition.writer_controls[0]
        target = writer["controller_target"]["payload"]
        applied = writer["applied_control"]["payload"]
        expected_names = {"torque_orchid", "torque_cobalt", "slide_fern"}
        if set(target["channel_values"]) != expected_names or set(applied["channel_values"]) != expected_names:
            raise ValueError("synthetic H5 mixed-control channels differ from the typed plan")
        if (target["channel_values"] != applied["channel_values"]
                or target["channel_units"] != applied["channel_units"]
                or applied["target_hash"] != writer["controller_target"]["identity_hash"]
                or target["control_step"] != index):
            raise ValueError("synthetic H5 target/Ack or control boundary identity differs")
    return loaded


def test_generic_three_channel_candidate_uses_shared_core_runtime_and_recorder(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _synthetic_mixed_candidate(monkeypatch, horizon=2)
    rows = []
    try:
        for seed in (31, 32, 33):
            observation, reset_info = env.reset(seed=seed)
            assert env.value["artifact"].task_id == "synthetic-contact-motion-v1"
            dimensions = reset_info["compiled_model_layout_v1"]["dimensions"]
            assert (dimensions["nq"], dimensions["nv"], dimensions["nu"]) == (10, 9, 3)
            assert reset_info["contact_summary_v2"]["state_revision"] == env.session.state_revision
            assert observation["state"]["joint_position"].shape == (3,)
            output = tmp_path / f"synthetic_episode_{seed}.h5"
            env.start_recording(output)
            for _ in range(2):
                observation, _, _, truncated, info = env.step(np.asarray([0.25, -0.15, 0.05]))
                assert info["contact_summary_v2"]["state_revision"] == env.session.state_revision
                assert set(info["mixed_actuator_command_v1"]["channel_values"]) == {
                    "torque_orchid", "torque_cobalt", "slide_fern",
                }
            assert truncated is True
            final = env.finish_recording("horizon_reached")
            assert final["transition_count"] == 2
            assert final["observation_count"] == 3
            loaded = _read_synthetic_mixed_h5(output)
            assert loaded["transition_count"] == 2
            assert loaded["observation_count"] == 3
            assert [row["control_step"] for row in loaded["boundary_contexts"]] == [0, 1, 2]
            rows.append({
                "seed": seed, "episode_id": loaded["outcome"].episode_id,
                "reset_sample_id": reset_info["reset_sample_v1"]["sample_id"],
                "h5_path": output.name, "h5_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "transition_count": loaded["transition_count"],
                "observation_count": loaded["observation_count"],
                "source_id": reset_info["source_id"],
                "source_closure_digest": reset_info["source_closure_digest"],
                "mixed_actuator_plan_identity": env.value["source"].mixed_actuator_plan.identity_hash,
                "compiled_dimensions": reset_info["compiled_model_layout_v1"]["dimensions"],
                "evidence_class": "synthetic_provider_free_s1",
            })
        # A stale owner context must be rejected by the independent reader.
        stale = tmp_path / "stale_contact_revision.h5"
        shutil.copy2(tmp_path / "synthetic_episode_31.h5", stale)
        with h5py.File(stale, "r+") as handle:
            contexts = json.loads(handle["meta/boundary_context_v1_json"][()].decode("utf-8"))
            contexts[1]["contact_summary_v2"]["state_revision"] -= 1
            handle["meta/boundary_context_v1_json"][()] = json.dumps(
                contexts, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        with pytest.raises(ValueError, match="contact identity is stale at state_revision"):
            _read_synthetic_mixed_h5(stale)
    finally:
        env.close()
    assert env.close_receipt["session_closed"] is True

    # Exercise the same generic route's partial-writer failure and close path.
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    failed = _synthetic_mixed_candidate(monkeypatch, horizon=2)
    try:
        observation, _ = failed.reset(seed=41)
        initial_steps = _FAKE_WORLD.calls["step"]
        _FAKE_WORLD.partial_ctrl_after = _FAKE_WORLD.ctrl_write_count + 1
        with pytest.raises(RuntimeError, match="partial actuator control write"):
            failed.step(np.asarray([0.25, -0.15, 0.05]))
        assert _FAKE_WORLD.calls["step"] == initial_steps
        assert failed.execution_fault is not None
        assert failed.execution_fault.phase == "mixed_control_application"
    finally:
        failed.close()
    assert failed.close_receipt["session_closed"] is True


def test_reset_schema_and_provider_rejection_precede_runtime_mutation(tmp_path, monkeypatch):
    global _FAKE_WORLD
    from task_env.artifacts import ExecutionSpec, PoseWorld, ResetSampleV1
    from task_env.artifacts.execution import ResetSample

    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _synthetic_mixed_candidate(monkeypatch, horizon=2)
    try:
        observation, _ = env.reset(seed=51)
        session = env.session
        state_before = session.snapshot()
        reset_calls = _FAKE_WORLD.calls["reset"]
        legacy_sample = ResetSample.create(
            schema_version="reset-sample-v0", task_artifact_hash=env.artifact.identity_hash,
            sampler_id="legacy-schema-negative", sampler_version="v1", task_seed=51,
            joint_position=dict(env.sample.joint_position), poses_world=dict(env.sample.poses_world),
            velocity_policy="zero_named_joint_and_entity_velocities",
            control_policy="arm_targets_at_initial_joints_gripper_open", settle_steps=0,
        )
        with pytest.raises(TypeError, match="requires ResetSampleV1 before native reset"):
            session.reset(legacy_sample)
        assert _FAKE_WORLD.calls["reset"] == reset_calls
        assert env.session is session and session.snapshot() == state_before
        action = np.asarray([0.1, -0.1, 0.04], dtype=np.float64)
        env.step(action)  # Rejected reset left the previously admitted episode usable.
    finally:
        env.close()
    assert env.close_receipt["session_closed"] is True

    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate

    package = build_position_candidate(tmp_path / "legacy_position", provider="mujoco", horizon=2)
    legacy_env = package.env
    try:
        legacy_env.reset(seed=package.reset_plan.reset_sample.task_seed)
        session = legacy_env.session
        calls_before = dict(_FAKE_WORLD.calls)
        source_sample = package.reset_plan.reset_sample
        # This is a well-formed v1 value intentionally unrelated to the
        # legacy source.  The legacy session must reject the schema before it
        # inspects source identity or mutates/reset native state.
        unrelated_pose = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
        mixed_sample = ResetSampleV1.create(
            schema_version="reset-sample-v1", task_artifact_hash=package.artifact.identity_hash,
            source_id=package.source.scene_source.source_id,
            source_closure_digest=package.source.source_closure_digest,
            sampler_id="wrong-profile-reset", sampler_version="v1",
            task_seed=source_sample.task_seed, init_row_index=0,
            init_row_sha256=hashlib.sha256(b"legacy-reset-negative-row").hexdigest(),
            joint_position=dict(source_sample.joint_position),
            joint_velocity={name: 0.0 for name in source_sample.joint_position},
            sampled_poses_world={"unrelated_free_body": unrelated_pose},
            poses_world={"unrelated_free_body": unrelated_pose},
            free_joint_velocity={"unrelated_free_body": (0.0,) * 6},
            free_joint_velocity_frame="mujoco_world_linear_local_angular_v1",
            fixture_pose_world={}, simulation_time_s=0.0,
            velocity_policy="named_qvel_and_free_joint_qvel_v1",
            control_policy="named_mixed_actuator_channels_by_source_v1",
            initialization_order=(
                "sample_source_properties", "native_preprocess", "sample_task_placements",
                "restore_source_bound_state", "forward_derived_state",
            ),
            settle_steps=0,
        )
        with pytest.raises(TypeError, match="requires ResetSample v0 before reset"):
            session.reset(mixed_sample)
        assert _FAKE_WORLD.calls == calls_before
        assert legacy_env.session is session
    finally:
        legacy_env.close()
    assert legacy_env._closed is True
    assert session._closed is True

    # Process-local mixed admission must reject an unsupported provider before
    # it reaches provider import or any native materialization path.
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    unsupported = _synthetic_mixed_candidate(monkeypatch, horizon=2)
    try:
        from task_env.runtime.sessions.api import materialize

        with pytest.raises(ValueError, match="strict MuJoCo CPU state-only"):
            materialize(
                unsupported.artifact,
                ExecutionSpec("geophys", "p1_2_scalar_cpu_v0", "none", "cpu", 0, "strict"),
                source=unsupported.value["source"],
            )
        assert _FAKE_WORLD.calls["compile"] == 0
        assert _FAKE_WORLD.calls["reset"] == 0
    finally:
        unsupported.close()


@pytest.mark.parametrize('provider, class_name', (
    ('geophys', '_GeoPhysSession'), ('sapien', '_SapienSession'),
    ('genesis', '_GenesisSession'),
))
def test_other_provider_v1_reset_rejected_before_lifecycle_mutation(provider, class_name, monkeypatch):
    """A new reset schema must not enter legacy zero-velocity provider paths."""
    from dataclasses import replace
    import importlib

    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _synthetic_mixed_candidate(monkeypatch, horizon=2)
    try:
        env.reset(seed=51)
        cls = getattr(importlib.import_module('task_env.runtime.sessions.' + provider), class_name)
        # Initialize only the real shared value owner. Native provider objects
        # deliberately do not exist: schema rejection must precede touching them.
        session = cls.__new__(cls)
        source = replace(env.value['source'], mixed_actuator_plan=None)
        session._initialize_values(env.artifact, source, provider)
        session._reset_done = True
        session._episode_id = 'preserved-episode'
        session._reset_force_measurement = 'preserved-feedback'
        before = dict(_FAKE_WORLD.calls)
        with pytest.raises(TypeError, match='requires an admitted MuJoCo mixed actuator session'):
            session.reset(env.sample)
        assert session._reset_done is True
        assert session._episode_id == 'preserved-episode'
        assert session._reset_force_measurement == 'preserved-feedback'
        assert _FAKE_WORLD.calls == before
    finally:
        env.close()


@pytest.mark.parametrize('bias_slot, value', ((0, 1.0), (2, 1.0)))
def test_position_drive_rejects_offset_and_antidamping_before_reset(bias_slot, value, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    env = _synthetic_mixed_candidate(monkeypatch, horizon=2)
    fake = sys.modules['mujoco']
    original = fake.MjModel.from_xml_string

    def unsupported_servo(*args, **kwargs):
        model = original(*args, **kwargs)
        for aid in range(model.nu):
            if model.actuator_biastype[aid] == fake.mjtBias.mjBIAS_AFFINE:
                model.actuator_biasprm[aid, bias_slot] = value
        return model

    monkeypatch.setattr(fake.MjModel, 'from_xml_string', unsupported_servo)
    try:
        with pytest.raises(ValueError, match='not a fixed-gain affine servo'):
            env.reset(seed=51)
        assert _FAKE_WORLD.calls['reset'] == 0
        assert _FAKE_WORLD.calls['step'] == 0
    finally:
        env.close()


@pytest.mark.parametrize('warning_count', (0, 6, 8))
def test_monitor_and_reader_reject_incomplete_warning_vector(warning_count, monkeypatch):
    from copy import deepcopy
    from bench_deploy.libero.core_candidate_worker import _validate_physical_state_monitor

    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch, horizon=2)
    try:
        observation, _ = env.reset(seed=19, options={'init_row_index': 0})
        progress = env.get_runtime_progress_receipt()
        monitor = deepcopy(progress['physical_state_monitor'])
        monitor['warning_counts'] = [0] * warning_count
        progress['physical_state_monitor'] = monitor
        joints = np.asarray([observation['state']['joint_position']], dtype=np.float64)
        with pytest.raises(ValueError, match='omits warning counters'):
            _validate_physical_state_monitor(monitor, progress, env.session.compiled_layout_receipt, joints)
        _FAKE_WORLD.last_data.warning = [types.SimpleNamespace(number=0) for _ in range(warning_count)]
        with pytest.raises(RuntimeError, match='all seven warning counters'):
            env.session._warning_counts()
    finally:
        env.close()


def test_contact_state_revision_rejected_before_recording_and_latched(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _synthetic_mixed_candidate(monkeypatch, horizon=2)
    try:
        env.reset(seed=61)
        session = env.session
        original_observer = env.binding.observe_mixed_control

        def stale_contact(environment, state):
            observation, info, evaluation = original_observer(environment, state)
            info = dict(info)
            contact = dict(info["contact_summary_v2"])
            contact["state_revision"] -= 1
            info["contact_summary_v2"] = contact
            return observation, info, evaluation

        object.__setattr__(env.binding, "observe_mixed_control", stale_contact)
        reset_revision = env.session.state_revision
        reset_steps = _FAKE_WORLD.calls["step"]
        with pytest.raises(ValueError, match="stale or belongs to another state revision"):
            env.observation(env.state)
        assert _FAKE_WORLD.calls["step"] == reset_steps
        assert env.session.state_revision == reset_revision

        env.start_recording(tmp_path / "stale_contact.h5")
        assert env.recorder.transition_count == 0
        assert env.recorder.observation_count == 1
        with pytest.raises(ValueError, match="stale or belongs to another state revision"):
            env.step(np.asarray([0.1, -0.1, 0.04], dtype=np.float64))
        assert env.execution_fault is not None
        assert env.execution_fault.phase == "mixed_observation"
        # Observation validation runs before the Recorder can append the
        # physically advanced but stale-contact boundary.
        assert env.recorder.transition_count == 0
        assert env.recorder.observation_count == 1
    finally:
        env.close()
    assert env.close_receipt["session_closed"] is True
    assert session._closed is True


@pytest.mark.parametrize("failure_kind", ("joint_limit", "warning"))
def test_physical_monitor_fails_on_first_native_step(failure_kind, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch, horizon=2)
    session = None
    try:
        observation, _ = env.reset(seed=19, options={"init_row_index": 0})
        session = env.session
        action = np.asarray([*observation["state"]["joint_position"][:7], 0.04], dtype=np.float64)
        prepared = env.binding.prepare_mixed_control(env, action, env.state)
        plan = env.value["source"].mixed_actuator_plan
        target = prepared["target"]
        channel_by_name = {channel.semantic_id: channel for channel in plan.channels}
        assert set(target.channel_values) == set(channel_by_name)
        assert all(
            channel_by_name[name].control_range[0] <= value <= channel_by_name[name].control_range[1]
            for name, value in target.channel_values.items()
        )
        next_native_step = _FAKE_WORLD.calls["step"] + 1
        if failure_kind == "joint_limit":
            limit = session.compiled_layout_receipt["named_joint_limits"]["joint1"]["range"][1]
            _FAKE_WORLD.joint_excursion_at_step = ("robot0_joint1", limit + 1.0e-4, next_native_step)
            message = "joint limit excursion"
        else:
            _FAKE_WORLD.warning_at_step = next_native_step
            message = "MuJoCo warning"
        with pytest.raises(RuntimeError, match="physical state monitor.*" + message):
            env.step(action)
        monitor = session.physical_state_monitor_receipt
        assert monitor["status"] == "failed"
        assert monitor["native_step_count"] == 1
        assert monitor["samples_including_reset"] == 2
        if failure_kind == "joint_limit":
            assert monitor["first_violation"]["kind"] == "joint_limit_exceeded"
            assert monitor["first_violation"]["native_step"] == 1
            assert monitor["first_violation"]["control_boundary"] == 1
            assert monitor["first_violation"]["excursion"] == pytest.approx(1.0e-4)
        else:
            assert monitor["first_violation"] is None
            assert monitor["warning_counts"][0] == 1
        assert env.execution_fault is not None
        assert env.execution_fault.phase == "mixed_physics_step"
    finally:
        env.close()
    assert env.close_receipt["session_closed"] is True
    assert env.close_receipt["physical_state_monitor"]["status"] == "failed"


def test_r07c_d01_motion_gate_uses_signed_finger_aperture_delta():
    from bench_deploy.libero.core_candidate_worker import (
        _public_motion_metrics, _validate_public_motion_gate,
    )

    initial_joints = np.zeros(9, dtype=np.float64)
    initial_joints[7:9] = (0.02, -0.02)
    final_joints = initial_joints.copy()
    final_joints[0] += 0.06
    final_joints[7:9] = (0.01, -0.01)
    ee_pose = np.asarray([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0])

    summary = _public_motion_metrics(initial_joints, final_joints, ee_pose, ee_pose)
    assert summary["aggregate_finger_position_delta_m"] == pytest.approx(0.02)
    assert summary["arm_joint_max_abs_delta_rad"] == pytest.approx(0.06)
    assert _validate_public_motion_gate(
        summary, initial_joints, final_joints, ee_pose, ee_pose, require_thresholds=True,
    ) == summary

    no_aperture_change = final_joints.copy()
    no_aperture_change[7:9] = initial_joints[7:9]
    insufficient_summary = _public_motion_metrics(
        initial_joints, no_aperture_change, ee_pose, ee_pose,
    )
    with pytest.raises(ValueError, match="aggregate finger opening delta"):
        _validate_public_motion_gate(
            insufficient_summary, initial_joints, no_aperture_change, ee_pose, ee_pose,
            require_thresholds=True,
        )


def test_compiled_libero_assets_use_receipt_bound_unique_vfs_aliases(monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch)
    try:
        env.reset(seed=19, options={"init_row_index": 0})
        receipt = env.value["source"].execution_source_receipt
        assert receipt is not None
        composition = env.value["source"].composition
        asset_merge = composition["asset_merge_receipt"]
        assert composition["schema_version"] == "libero-source-composition-mjcf-v4"
        assert asset_merge["schema_version"] == "libero-source-asset-merge-v1"
        stove_texture_rows = [
            row for row in asset_merge["duplicate_definitions"]
            if row["semantic_id"] == "flat_stove_1"
            and row["asset_type"] == "texture"
            and row["source_name"] == "tex-stove_knob"
        ]
        assert len(stove_texture_rows) == 1
        assert stove_texture_rows[0]["kept_attributes"]["file"].endswith("/metal.png")
        assert stove_texture_rows[0]["discarded_attributes"]["file"].endswith("/button_dark_texture.png")
        composed_root = ET.parse(os.environ["R07C_COMPOSED_MJCF"]).getroot()
        composed_asset = composed_root.find("asset")
        names_by_type = {}
        for node in composed_asset:
            if node.get("name"):
                names_by_type.setdefault(node.tag, []).append(node.get("name"))
        assert all(len(names) == len(set(names)) for names in names_by_type.values())
        texture_files = {
            node.get("name"): node.get("file") for node in composed_asset.findall("texture")
        }
        stove_material_textures = {
            node.get("name"): texture_files[node.get("texture")]
            for node in composed_asset.findall("material")
            if node.get("name") in {
                "stove_knob_base", "stove_knob_button",
            }
        }
        assert stove_material_textures == {
            "stove_knob_base": "upstream/libero/libero/libero/assets/articulated_objects/flat_stove/metal.png",
            "stove_knob_button": "upstream/libero/libero/libero/assets/articulated_objects/flat_stove/metal.png",
        }
        source_root = ET.fromstring(receipt.importer_xml)
        compiled_root = ET.fromstring(_FAKE_WORLD.last_compile_xml)
        source_files = [node.get("file") for node in source_root.iter() if node.get("file")]
        compiled_files = [node.get("file") for node in compiled_root.iter() if node.get("file")]
        aliases = env.session.compiled_layout_receipt["compiler_asset_aliases"]
        rows_by_source = {row["source_path"]: row for row in aliases}
        assert len(rows_by_source) == len(aliases)
        assert set(rows_by_source) == set(source_files)
        assert set(_FAKE_WORLD.last_assets) == {row["vfs_name"] for row in aliases}
        assert set(compiled_files) == set(_FAKE_WORLD.last_assets)
        assert len(set(compiled_files)) == len(rows_by_source)
        assert all("/" not in name and "\\" not in name for name in _FAKE_WORLD.last_assets)
        for source_path, row in rows_by_source.items():
            payload = receipt.closure_files[source_path]
            assert row["sha256"] == hashlib.sha256(payload).hexdigest()
            assert row["size_bytes"] == len(payload)
            assert _FAKE_WORLD.last_assets[row["vfs_name"]] == payload
        metal_paths = [path for path in rows_by_source if path.endswith("/metal.png")]
        assert len(metal_paths) >= 2
        assert len({rows_by_source[path]["vfs_name"] for path in metal_paths}) == len(metal_paths)
        # Repeated references to one source path share one compiler alias, while
        # the immutable importer snapshot retains its original path strings.
        assert len(source_files) > len(set(source_files))
        assert receipt.importer_xml == receipt.closure_files["scene.xml"]
    finally:
        env.close()


def test_failed_materialization_preserves_primary_error_and_reports_cleanup(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    _FAKE_WORLD.fail_compile = "synthetic primary source compile failure"
    env = _candidate(monkeypatch)
    result = run_libero_candidate_worker(
        env, output_dir=tmp_path / "failed_materialization", steps=1,
    )
    assert result["status"] == "failed"
    assert result["worker_error"] == {
        "type": "RuntimeError", "message": "synthetic primary source compile failure",
    }
    assert result["close_error"] is None
    close = result["final_session_close_receipt"]
    assert close["schema_version"] == "mixed-control-selected-close-v1"
    assert close["session_closed"] is True
    assert close["session_materialized"] is False
    assert close["session_close_status"] == "not_materialized"
    assert close["environment_closed"] is True
    assert close["cleanup_completed"] is True
    with pytest.raises(ValueError, match="incomplete or reports a lifecycle failure"):
        consume_libero_candidate_bundle(tmp_path / "failed_materialization/worker_result.json")


def _contact_pair_only_when_source_pose_is_on(model, data):
    bowl = data.xpos[model._body_ids["akita_black_bowl_1_main"]]
    plate = data.xpos[model._body_ids["plate_1_main"]]
    delta_xy = np.asarray(bowl[:2]) - np.asarray(plate[:2])
    if float(np.linalg.norm(delta_xy)) < 0.03 and float(bowl[2]) >= float(plate[2]):
        return ("akita_black_bowl_1", "plate_1")
    return None


def _rewrite_h5_json(path: Path, dataset: str, update):
    with h5py.File(path, "r+") as handle:
        value = json.loads(handle[dataset][()].decode("utf-8"))
        update(value)
        handle[dataset][()] = json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")


def _reseal_bundle(result_path: Path, episode_index=0):
    result = json.loads(result_path.read_text(encoding="utf-8"))
    episode = result["episodes"][episode_index]
    h5_path = result_path.parent / episode["h5"]["relative_path"]
    raw = h5_path.read_bytes()
    episode["h5"]["bytes"] = len(raw)
    episode["h5"]["sha256"] = hashlib.sha256(raw).hexdigest()
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    result["result_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    result_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return h5_path


def _write_synthetic_parent_run_record(root: Path, bundle_path: Path, result: dict,
                                       *, lock_path: Path):
    run_dir = root / "runs" / "run-parent"
    run_dir.mkdir(parents=True)
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    stdout_path.write_text(json.dumps({
        "status": result["status"], "episode_count": result["episode_count"],
        "transition_count": result["transition_count"],
        "observation_count": result["observation_count"],
        "native_step_count": result["native_step_count"],
        "result_sha256": result["result_sha256"],
    }) + "\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    record = {
        "schema_version": "r07c-d01-run-record-v1",
        "argv": [sys.executable, "-m", "bench_deploy.libero.core_candidate_worker",
                 "--run-worker", str(bundle_path.parent.resolve()), "--steps", "12"],
        "cwd": "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora",
        "exit_code": 0,
        "termination_reason": None,
        "stdout_path": "runs/run-parent/stdout.log",
        "stderr_path": "runs/run-parent/stderr.log",
        "stdout_bytes": stdout_path.stat().st_size,
        "stderr_bytes": 0,
        "lock_path": str(lock_path.resolve()),
        "lock_acquired": True,
        "lock_released_after_group_exit": True,
        "process_group_confirmed_exited": True,
        "environment": {
            "PYTHONPATH": "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora/GeoPhys/src:"
                          "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora",
        },
    }
    record_path = run_dir / "run_record.json"
    record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return record_path


def test_same_selected_env_three_rows_full_recorder_worker_and_independent_reader(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    fake = _fake_api(monkeypatch)
    assert getattr(fake, "__r07c_s1_synthetic_fixture__", False) is True
    import bench_deploy.libero.selected_candidate as selected_candidate
    from task_env.artifacts import ResetSampleV1

    original_sampler = selected_candidate.sample_libero_normal_reset_v1

    def nonzero_reset_sample(**kwargs):
        sample, receipt = original_sampler(**kwargs)
        payload = sample.to_mapping()
        joint_velocity = dict(payload["joint_velocity"])
        joint_velocity["joint1"] = 0.125
        free_velocity = dict(payload["free_joint_velocity"])
        free_velocity["akita_black_bowl_1"] = [0.01, -0.02, 0.03, 0.1, -0.2, 0.3]
        payload.update(
            joint_velocity=joint_velocity,
            free_joint_velocity=free_velocity,
            simulation_time_s=1.25,
        )
        return ResetSampleV1.create(**payload), {
            **receipt, "s1_nonzero_time_velocity_fixture": True,
        }

    monkeypatch.setattr(selected_candidate, "sample_libero_normal_reset_v1", nonzero_reset_sample)
    _FAKE_WORLD.contact_pair = _contact_pair_only_when_source_pose_is_on
    env = _candidate(monkeypatch, horizon=12)
    result = run_libero_candidate_worker(env, output_dir=tmp_path / "bundle", steps=12)
    assert result["status"] == "complete"
    assert all(
        action["planner_action"][7] == pytest.approx(-0.6)
        and action["selected_public_action"][7] == pytest.approx(0.016)
        for episode in result["episodes"] for action in episode["action_trace"]
    )
    assert result["episodes"][0]["control_plan"]["kp_Nm_per_rad"] == [20.0] * 7
    assert result["episodes"][0]["control_plan"]["kd_Nm_s_per_rad"] == [4.0, 8.0, 4.0, 4.0, 4.0, 4.0, 4.0]
    assert [episode["row_index"] for episode in result["episodes"]] == [0, 1, 2]
    assert result["transition_count"] == 36
    assert result["observation_count"] == 39
    assert result["native_step_count"] == 900
    assert _FAKE_WORLD.calls["compile"] == 5
    assert _FAKE_WORLD.calls["reset"] == 5
    assert _FAKE_WORLD.calls["step1"] == 5
    assert _FAKE_WORLD.calls["step"] == 900
    assert _FAKE_WORLD.calls["forward"] == 41
    assert result["reset_count"] == 5
    assert [item["endpoint"] for item in result["diagnostic_endpoints"]] == ["negative", "positive"]
    assert [item["core_predicate_v1"]["value"] for item in result["diagnostic_endpoints"]] == [False, True]
    assert [item["source_predicate_oracle"]["value"] for item in result["diagnostic_endpoints"]] == [False, True]
    assert all(item["runtime_progress"]["native_step_count"] == 0 for item in result["diagnostic_endpoints"])
    from bench_deploy.libero.init_state import (
        PILOT_FIXTURES, PILOT_MOVABLES, PILOT_MOVABLE_OBJECT_CLASSES,
    )

    readback = consume_libero_candidate_bundle(tmp_path / "bundle/worker_result.json")
    assert readback["status"] == "verified_complete"
    assert (readback["transition_count"], readback["observation_count"]) == (36, 39)
    for episode in result["episodes"]:
        realization = episode["reset_realization"]
        sampler = realization["placement_sampler"]
        assert sampler["bddl_problem_name"] == "libero_tabletop_manipulation"
        assert sampler["movable_object_classes"] == PILOT_MOVABLE_OBJECT_CLASSES
        assert sampler["append_order"] == [name for name, _, _ in (*PILOT_MOVABLES, *PILOT_FIXTURES)]
        assert realization["object_property_initializers"] == []
        assert realization["mj_step1"].startswith("called once before placements")
        draws = {item["object"]: item for item in realization["placements_before_pruned_init_restore"]}
        assert tuple(draws) == tuple(sampler["append_order"])
        geometry = realization["asset_placement_geometry"]
        from bench_deploy.libero.init_state import PILOT_TABLE_TOP_Z_M, PILOT_MOVABLE_Z_OFFSET_M, PILOT_FIXTURE_Z_OFFSET_M
        for object_name, _region, asset_path in PILOT_MOVABLES:
            draw = draws[object_name]
            radius = geometry[asset_path]["horizontal_radius_m"]
            raw_x0, raw_y0, raw_x1, raw_y1 = draw["region_ranges_m"]
            assert draw["source_sampler"].endswith("TableRegionSampler")
            assert draw["object_class"] == PILOT_MOVABLE_OBJECT_CLASSES[object_name]
            assert draw["horizontal_radius_margin_m"] == radius
            assert draw["x_sample_bounds_m"] == pytest.approx([raw_x0 + radius, raw_x1 - radius])
            assert draw["y_sample_bounds_m"] == pytest.approx([raw_y0 + radius, raw_y1 - radius])
            assert draw["x_sample_interval_m"] == pytest.approx(sorted(draw["x_sample_bounds_m"]))
            assert draw["y_sample_interval_m"] == pytest.approx(sorted(draw["y_sample_bounds_m"]))
            assert draw["x_sample_interval_m"][0] <= draw["position"][0] <= draw["x_sample_interval_m"][1]
            assert draw["y_sample_interval_m"][0] <= draw["position"][1] <= draw["y_sample_interval_m"][1]
            assert draw["z_offset_m"] == PILOT_MOVABLE_Z_OFFSET_M == 0.01
            assert draw["position"][2] == pytest.approx(
                PILOT_MOVABLE_Z_OFFSET_M + PILOT_TABLE_TOP_Z_M - geometry[asset_path]["bottom_offset_m"][2],
            )
            assert draw["rotation_axis"] == "x"
            assert draw["rotation_range_rad"] == pytest.approx([np.pi / 2, np.pi / 2])
            assert draw["rotation_angle_rad"] == pytest.approx(np.pi / 2)
        for fixture_name, _region, asset_path in PILOT_FIXTURES:
            draw = draws[fixture_name]
            raw_x0, raw_y0, raw_x1, raw_y1 = draw["region_ranges_m"]
            assert draw["source_sampler"].endswith("MultiRegionRandomSampler")
            assert draw["horizontal_radius_margin_m"] == 0.0
            assert draw["x_sample_bounds_m"] == [raw_x0, raw_x1]
            assert draw["y_sample_bounds_m"] == [raw_y0, raw_y1]
            assert draw["x_sample_interval_m"] == pytest.approx(sorted(draw["x_sample_bounds_m"]))
            assert draw["y_sample_interval_m"] == pytest.approx(sorted(draw["y_sample_bounds_m"]))
            assert draw["x_sample_interval_m"][0] <= draw["position"][0] <= draw["x_sample_interval_m"][1]
            assert draw["y_sample_interval_m"][0] <= draw["position"][1] <= draw["y_sample_interval_m"][1]
            assert draw["z_offset_m"] == PILOT_FIXTURE_Z_OFFSET_M == -0.04
            assert draw["position"][2] == pytest.approx(
                PILOT_FIXTURE_Z_OFFSET_M + PILOT_TABLE_TOP_Z_M - geometry[asset_path]["bottom_offset_m"][2],
            )
            assert draw["rotation_axis"] == "z"
            assert draw["rotation_range_rad"][0] <= draw["rotation_angle_rad"] <= draw["rotation_range_rad"][1]
            angle = draw["rotation_angle_rad"]
            assert draw["quaternion_wxyz"] == pytest.approx(
                [np.cos(angle / 2), 0.0, 0.0, np.sin(angle / 2)],
            )
        assert episode["reset_sample"]["simulation_time_s"] == 1.25
        assert episode["reset_readback"]["simulation_time_s"] == 1.25
        assert episode["reset_sample"]["joint_velocity"]["joint1"] == 0.125
        assert episode["reset_readback"]["joint_velocity"]["joint1"] == 0.125
        assert episode["reset_sample"]["free_joint_velocity"]["akita_black_bowl_1"] == [
            0.01, -0.02, 0.03, 0.1, -0.2, 0.3,
        ]
        assert episode["reset_readback"]["free_joint_velocity"]["akita_black_bowl_1"] == [
            0.01, -0.02, 0.03, 0.1, -0.2, 0.3,
        ]
        assert episode["action_trace"][0]["simulation_time_s"] == pytest.approx(0.05)
        h5_path = tmp_path / "bundle" / episode["h5"]["relative_path"]
        semantic = load_structured_control_records_h5(h5_path)
        assert semantic["transition_count"] == 12
        assert semantic["observation_count"] == 13
        assert semantic["outcome"].episode_id == episode["episode_id"]
        with h5py.File(h5_path, "r") as handle:
            context = json.loads(handle["meta/task_context_json"][()].decode("utf-8"))
            assert context["init_row_index"] == episode["row_index"]
            assert context["init_row_sha256"] == episode["reset_sample"]["init_row_sha256"]
            assert handle["obs/state/joint_position"].shape == (13, 9)

    # Re-seal copied H5 and worker receipts so each case reaches the semantic
    # reader gates instead of stopping at a byte/digest mismatch.
    original = tmp_path / "bundle"
    contact_copy = tmp_path / "tampered_contact"
    shutil.copytree(original, contact_copy)
    contact_result = contact_copy / "worker_result.json"
    contact_h5 = contact_copy / result["episodes"][0]["h5"]["relative_path"]
    _rewrite_h5_json(contact_h5, "meta/boundary_context_v1_json", lambda rows: rows[1]["contact_summary_v2"].update(
        requested_pairs=[], covered_pairs=[], pair_counts={},
    ))
    _reseal_bundle(contact_result)
    with pytest.raises(ValueError, match="contact query coverage"):
        consume_libero_candidate_bundle(contact_result)

    freshness_copy = tmp_path / "tampered_contact_freshness"
    shutil.copytree(original, freshness_copy)
    freshness_result = freshness_copy / "worker_result.json"
    freshness_h5 = freshness_copy / result["episodes"][0]["h5"]["relative_path"]
    _rewrite_h5_json(freshness_h5, "meta/boundary_context_v1_json", lambda rows: rows[1][
        "contact_summary_v2"].update(state_revision=99,
    ))
    _reseal_bundle(freshness_result)
    with pytest.raises(ValueError, match="stale state revision"):
        consume_libero_candidate_bundle(freshness_result)

    action_copy = tmp_path / "tampered_action"
    shutil.copytree(original, action_copy)
    action_result = action_copy / "worker_result.json"
    action_h5 = action_copy / result["episodes"][0]["h5"]["relative_path"]
    with h5py.File(action_h5, "r+") as handle:
        handle["universal_action/joint1"][0, 0] += 0.25
    _reseal_bundle(action_result)
    with pytest.raises(ValueError, match="typed request differs"):
        consume_libero_candidate_bundle(action_result)

    clock_copy = tmp_path / "tampered_clock"
    shutil.copytree(original, clock_copy)
    clock_result = clock_copy / "worker_result.json"
    clock_h5 = clock_copy / result["episodes"][0]["h5"]["relative_path"]
    _rewrite_h5_json(clock_h5, "meta/boundary_context_v1_json", lambda rows: rows[-1].update(
        simulation_time_s=rows[-1]["simulation_time_s"] + 0.001,
    ))
    _reseal_bundle(clock_result)
    with pytest.raises(ValueError, match="boundary order, clock"):
        consume_libero_candidate_bundle(clock_result)

    ack_copy = tmp_path / "tampered_ack"
    shutil.copytree(original, ack_copy)
    ack_result = ack_copy / "worker_result.json"
    ack_h5 = ack_copy / result["episodes"][0]["h5"]["relative_path"]
    _rewrite_h5_json(ack_h5, "meta/structured_controls_v1_json", lambda rows: rows[0]["writer_controls"][0][
        "applied_control"]["payload"].update(target_hash="0" * 64,
    ))
    _reseal_bundle(ack_result)
    with pytest.raises(ValueError, match="target/Ack identity"):
        consume_libero_candidate_bundle(ack_result)

    unit_copy = tmp_path / "tampered_unit"
    shutil.copytree(original, unit_copy)
    unit_result = unit_copy / "worker_result.json"
    unit_h5 = unit_copy / result["episodes"][0]["h5"]["relative_path"]
    _rewrite_h5_json(unit_h5, "meta/structured_controls_v1_json", lambda rows: rows[0][
        "writer_controls"][0]["requested_action"].update(unit="millimeters_and_radians",
    ))
    _reseal_bundle(unit_result)
    with pytest.raises(ValueError, match="unit metadata"):
        consume_libero_candidate_bundle(unit_result)

    final_state_copy = tmp_path / "tampered_final_state"
    shutil.copytree(original, final_state_copy)
    final_state_result = final_state_copy / "worker_result.json"
    final_state_h5 = final_state_copy / result["episodes"][0]["h5"]["relative_path"]
    with h5py.File(final_state_h5, "r+") as handle:
        handle["obs/state/joint_position"][-1, 0] += 0.5
    _reseal_bundle(final_state_result)
    with pytest.raises(ValueError, match="native-step monitor extrema"):
        consume_libero_candidate_bundle(final_state_result)

    row_copy = tmp_path / "tampered_row"
    shutil.copytree(original, row_copy)
    row_result = row_copy / "worker_result.json"
    row_report = json.loads(row_result.read_text(encoding="utf-8"))
    row_report["episodes"][0]["row_index"] = 9
    row_payload = {key: value for key, value in row_report.items() if key != "result_sha256"}
    row_report["result_sha256"] = hashlib.sha256(json.dumps(
        row_payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    row_result.write_text(json.dumps(row_report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row/seed/order identity"):
        consume_libero_candidate_bundle(row_result)

    source_copy = tmp_path / "tampered_source"
    shutil.copytree(original, source_copy)
    source_result = source_copy / "worker_result.json"
    source_report = json.loads(source_result.read_text(encoding="utf-8"))
    source_report["episodes"][0]["source_id"] = "wrong-source"
    source_result.write_text(json.dumps(source_report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _reseal_bundle(source_result)
    with pytest.raises(ValueError, match="compiled model was not validated before reset"):
        consume_libero_candidate_bundle(source_result)

    layout_copy = tmp_path / "tampered_compiled_layout"
    shutil.copytree(original, layout_copy)
    layout_result = layout_copy / "worker_result.json"
    layout_report = json.loads(layout_result.read_text(encoding="utf-8"))
    for receipt_path in (
        ("compiled_model_layout_v1",),
        ("pre_reset_compiled_validation_v1", "compiled_layout"),
    ):
        receipt = layout_report["episodes"][0]
        for key in receipt_path:
            receipt = receipt[key]
        receipt["named_actuator_channels"]["joint1"]["transmission_target"] = "robot0_joint2"
    layout_result.write_text(json.dumps(layout_report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _reseal_bundle(layout_result)
    with pytest.raises(ValueError, match="compiled actuator transmission/drive/range"):
        consume_libero_candidate_bundle(layout_result)

    runtime_copy = tmp_path / "tampered_runtime_identity"
    shutil.copytree(original, runtime_copy)
    runtime_result = runtime_copy / "worker_result.json"
    runtime_report = json.loads(runtime_result.read_text(encoding="utf-8"))
    runtime_report["episodes"][0]["pre_reset_compiled_validation_v1"][
        "runtime_identity"]["runtime"]["api_version"] = 30801
    runtime_result.write_text(json.dumps(runtime_report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _reseal_bundle(runtime_result)
    with pytest.raises(ValueError, match="runtime identity differs"):
        consume_libero_candidate_bundle(runtime_result)

    sign_copy = tmp_path / "tampered_finger_sign"
    shutil.copytree(original, sign_copy)
    sign_result = sign_copy / "worker_result.json"
    sign_h5 = sign_copy / result["episodes"][0]["h5"]["relative_path"]
    from task_env.controllers.canonical.contracts import MixedActuatorCommandV1

    def reverse_second_finger(rows):
        writer = rows[0]["writer_controls"][0]
        target_payload = writer["controller_target"]["payload"]
        target_payload["channel_values"]["finger_joint2"] = 0.01
        target = MixedActuatorCommandV1.from_mapping(target_payload)
        writer["controller_target"]["payload"] = target.to_mapping()
        writer["controller_target"]["identity_hash"] = target.identity_hash
        applied = writer["applied_control"]
        applied["target_hash"] = target.identity_hash
        applied["payload"].update(
            target_hash=target.identity_hash,
            channel_values=dict(target.channel_values),
            channel_units=dict(target.channel_units),
        )
    _rewrite_h5_json(sign_h5, "meta/structured_controls_v1_json", reverse_second_finger)
    _reseal_bundle(sign_result)
    with pytest.raises(ValueError, match="finger sign or aggregate-opening"):
        consume_libero_candidate_bundle(sign_result)

    monitor_copy = tmp_path / "tampered_physical_monitor"
    shutil.copytree(original, monitor_copy)
    monitor_result = monitor_copy / "worker_result.json"
    monitor_payload = json.loads(monitor_result.read_text(encoding="utf-8"))
    monitor_payload["episodes"][0]["physical_state_monitor"]["joint_ranges"][
        "finger_joint2"]["maximum_observed"] = 0.001
    monitor_result.write_text(json.dumps(monitor_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _reseal_bundle(monitor_result)
    with pytest.raises(ValueError, match="differs from public RuntimeSession progress"):
        consume_libero_candidate_bundle(monitor_result)

    warning_copy = tmp_path / "tampered_physical_warning"
    shutil.copytree(original, warning_copy)
    warning_result = warning_copy / "worker_result.json"
    warning_payload = json.loads(warning_result.read_text(encoding="utf-8"))
    warning_payload["episodes"][0]["physical_state_monitor"]["warning_counts"] = [1]
    warning_payload["episodes"][0]["runtime_progress"]["physical_state_monitor"]["warning_counts"] = [1]
    warning_result.write_text(json.dumps(warning_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _reseal_bundle(warning_result)
    with pytest.raises(ValueError, match="MuJoCo warning"):
        consume_libero_candidate_bundle(warning_result)

    missing_warning_copy = tmp_path / "missing_physical_warning_counters"
    shutil.copytree(original, missing_warning_copy)
    missing_warning_result = missing_warning_copy / "worker_result.json"
    missing_warning_payload = json.loads(missing_warning_result.read_text(encoding="utf-8"))
    missing_warning_payload["episodes"][0]["physical_state_monitor"].pop("warning_counts")
    missing_warning_payload["episodes"][0]["runtime_progress"][
        "physical_state_monitor"].pop("warning_counts")
    missing_warning_result.write_text(
        json.dumps(missing_warning_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    _reseal_bundle(missing_warning_result)
    with pytest.raises(ValueError, match="omits warning counters"):
        consume_libero_candidate_bundle(missing_warning_result)

    model_monitor_copy = tmp_path / "wrong_compiled_physical_monitor"
    shutil.copytree(original, model_monitor_copy)
    model_monitor_result = model_monitor_copy / "worker_result.json"
    model_monitor_payload = json.loads(model_monitor_result.read_text(encoding="utf-8"))
    model_monitor_payload["episodes"][0]["physical_state_monitor"][
        "compiled_model_identity_sha256"] = "0" * 64
    model_monitor_payload["episodes"][0]["runtime_progress"]["physical_state_monitor"][
        "compiled_model_identity_sha256"] = "0" * 64
    model_monitor_result.write_text(
        json.dumps(model_monitor_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    _reseal_bundle(model_monitor_result)
    with pytest.raises(ValueError, match="bound to a different compiled model"):
        consume_libero_candidate_bundle(model_monitor_result)

    recovered_excursion_copy = tmp_path / "midtrajectory_excursion_then_recovery"
    shutil.copytree(original, recovered_excursion_copy)
    recovered_excursion_result = recovered_excursion_copy / "worker_result.json"
    recovered_excursion_h5 = recovered_excursion_copy / result["episodes"][0]["h5"]["relative_path"]
    with h5py.File(recovered_excursion_h5, "r+") as handle:
        # Keep every typed target/Ack valid and the final observation unchanged.
        # This single interior public state is out of range and later recovers.
        handle["obs/state/joint_position"][1, 0] = 100.0
        assert handle["obs/state/joint_position"][-1, 0] != 100.0
    _reseal_bundle(recovered_excursion_result)
    with pytest.raises(ValueError, match="H5 joint observations escape the native-step monitor extrema"):
        consume_libero_candidate_bundle(recovered_excursion_result)

    episode_copy = tmp_path / "tampered_episode"
    shutil.copytree(original, episode_copy)
    episode_result = episode_copy / "worker_result.json"
    episode_report = json.loads(episode_result.read_text(encoding="utf-8"))
    episode_report["episodes"][0]["episode_id"] = "wrong-episode"
    episode_result.write_text(json.dumps(episode_report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _reseal_bundle(episode_result)
    with pytest.raises(ValueError, match="reset/progress identity"):
        consume_libero_candidate_bundle(episode_result)

    fixture_copy = tmp_path / "tampered_fixture_readback"
    shutil.copytree(original, fixture_copy)
    fixture_result = fixture_copy / "worker_result.json"
    fixture_report = json.loads(fixture_result.read_text(encoding="utf-8"))
    fixture = next(iter(fixture_report["episodes"][0]["reset_readback"]["fixture_pose_world"].values()))
    fixture["position"][0] += 0.1
    fixture_result.write_text(json.dumps(fixture_report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _reseal_bundle(fixture_result)
    with pytest.raises(ValueError, match="reset/progress identity"):
        consume_libero_candidate_bundle(fixture_result)

    endpoint_copy = tmp_path / "tampered_reset_plan_endpoint"
    shutil.copytree(original, endpoint_copy)
    endpoint_result = endpoint_copy / "worker_result.json"
    endpoint_report = json.loads(endpoint_result.read_text(encoding="utf-8"))
    endpoint_report["diagnostic_endpoints"][0]["reset_plan_v1"]["reset_sample"][
        "poses_world"]["akita_black_bowl_1"]["position"][0] += 0.1
    endpoint_result.write_text(json.dumps(endpoint_report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _reseal_bundle(endpoint_result)
    with pytest.raises((TypeError, ValueError), match="sample identity|sample_id|reset sample"):
        consume_libero_candidate_bundle(endpoint_result)

    # Bind native completion to the parent's exit, process-group and lock
    # receipts; exercise those gates with an explicitly synthetic receipt.
    lock_path = Path("/home/lly/Program_Files/Geochora/workspace/maintenance/") / (
        "phase_ii_01_sol_luna_handoff_20261023_001/shared_native_execution.lock"
    )
    parent_record = _write_synthetic_parent_run_record(
        tmp_path, original / "worker_result.json", result, lock_path=lock_path,
    )
    verified_parent = consume_libero_candidate_bundle(
        original / "worker_result.json", parent_run_record_path=parent_record,
        expected_lock_path=lock_path,
    )
    assert verified_parent["parent_process"]["status"] == "verified_parent_exit_and_lock_release"

    bad_exit = json.loads(parent_record.read_text(encoding="utf-8"))
    bad_exit["exit_code"] = 2
    bad_exit_path = parent_record.parent / "bad_exit.json"
    bad_exit_path.write_text(json.dumps(bad_exit), encoding="utf-8")
    with pytest.raises(ValueError, match="did not exit successfully"):
        consume_libero_candidate_bundle(
            original / "worker_result.json", parent_run_record_path=bad_exit_path,
            expected_lock_path=lock_path,
        )

    bad_lock = json.loads(parent_record.read_text(encoding="utf-8"))
    bad_lock["lock_released_after_group_exit"] = False
    bad_lock_path = parent_record.parent / "bad_lock.json"
    bad_lock_path.write_text(json.dumps(bad_lock), encoding="utf-8")
    with pytest.raises(ValueError, match="lock receipt"):
        consume_libero_candidate_bundle(
            original / "worker_result.json", parent_run_record_path=bad_lock_path,
            expected_lock_path=lock_path,
        )

    bad_worker_copy = tmp_path / "tampered_worker_result"
    shutil.copytree(original, bad_worker_copy)
    bad_worker_result = bad_worker_copy / "worker_result.json"
    bad_worker_payload = json.loads(bad_worker_result.read_text(encoding="utf-8"))
    bad_worker_payload["result_sha256"] = "0" * 64
    bad_worker_result.write_text(json.dumps(bad_worker_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="worker result digest"):
        consume_libero_candidate_bundle(bad_worker_result)

    partial_copy = tmp_path / "partial_worker_result"
    shutil.copytree(original, partial_copy)
    partial_result = partial_copy / "worker_result.json"
    partial_payload = json.loads(partial_result.read_text(encoding="utf-8"))
    partial_payload["episodes"] = partial_payload["episodes"][:2]
    partial_payload["episode_count"] = 2
    partial_result.write_text(json.dumps(partial_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _reseal_bundle(partial_result)
    with pytest.raises(ValueError, match="does not contain all three source rows"):
        consume_libero_candidate_bundle(partial_result)

    missing_h5_copy = tmp_path / "missing_h5_worker_result"
    shutil.copytree(original, missing_h5_copy)
    missing_h5_result = missing_h5_copy / "worker_result.json"
    missing_h5_payload = json.loads(missing_h5_result.read_text(encoding="utf-8"))
    (missing_h5_copy / missing_h5_payload["episodes"][0]["h5"]["relative_path"]).unlink()
    with pytest.raises(ValueError, match="missing a required H5"):
        consume_libero_candidate_bundle(missing_h5_result)

    missing_channel_copy = tmp_path / "missing_action_channel"
    shutil.copytree(original, missing_channel_copy)
    missing_channel_result = missing_channel_copy / "worker_result.json"
    missing_channel_payload = json.loads(missing_channel_result.read_text(encoding="utf-8"))
    missing_channel_h5 = missing_channel_copy / missing_channel_payload["episodes"][0]["h5"]["relative_path"]
    with h5py.File(missing_channel_h5, "r+") as handle:
        del handle["universal_action/joint1"]
    _reseal_bundle(missing_channel_result)
    with pytest.raises(ValueError, match="action channels are incomplete"):
        consume_libero_candidate_bundle(missing_channel_result)


def test_selected_mixed_partial_control_write_faults_without_physics(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch)
    try:
        observation, _ = env.reset(seed=19, options={"init_row_index": 0})
        initial_step_calls = _FAKE_WORLD.calls["step"]
        _FAKE_WORLD.partial_ctrl_after = _FAKE_WORLD.ctrl_write_count + 1
        action = np.asarray([*observation["state"]["joint_position"][:7], 0.04], dtype=np.float64)
        with pytest.raises(RuntimeError, match="partial actuator control write"):
            env.step(action)
        assert _FAKE_WORLD.calls["step"] == initial_step_calls
        assert env.execution_fault is not None
        assert env.execution_fault.phase == "mixed_control_application"
        with pytest.raises(RuntimeError, match="execution is faulted"):
            env.step(action)
        assert _FAKE_WORLD.calls["step"] == initial_step_calls
    finally:
        env.close()
    assert env.close_receipt["session_closed"] is True


def test_selected_partial_physics_interval_latches_and_worker_closes(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch)
    observation, _ = env.reset(seed=19, options={"init_row_index": 0})
    _FAKE_WORLD.fail_step_after = _FAKE_WORLD.calls["step"] + 2
    action = np.asarray([*observation["state"]["joint_position"][:7], 0.04], dtype=np.float64)
    with pytest.raises(RuntimeError, match="synthetic native-step leaf fault"):
        env.step(action)
    fault = env.execution_fault
    assert fault is not None
    assert fault.phase == "mixed_physics_step"
    assert fault.interval_attempted is True
    assert fault.interval_completed is False
    partial_count = _FAKE_WORLD.calls["step"]
    with pytest.raises(RuntimeError, match="execution is faulted"):
        env.step(action)
    assert _FAKE_WORLD.calls["step"] == partial_count
    env.close()
    assert env.close_receipt["session_closed"] is True

    # The worker must publish a failed result after cleanup, and the separate
    # reader must refuse it rather than treating partial progress as complete.
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    failed_env = _candidate(monkeypatch)
    _FAKE_WORLD.partial_ctrl_after = 4  # reset uses three ctrl writes; permit one target write
    result = run_libero_candidate_worker(failed_env, output_dir=tmp_path / "failed_bundle", steps=2)
    assert result["status"] == "failed"
    assert result["episode_count"] == 0
    assert result["close_error"] is None
    assert result["final_session_close_receipt"]["session_closed"] is True
    with pytest.raises(ValueError, match="incomplete or reports a lifecycle failure"):
        consume_libero_candidate_bundle(tmp_path / "failed_bundle/worker_result.json")


def test_selected_rejects_invalid_action_before_native_and_reset_forward_failure(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch)
    try:
        env.reset(seed=19, options={"init_row_index": 0})
        steps_before = _FAKE_WORLD.calls["step"]
        with pytest.raises(ValueError, match="finite vector matching its declared action schema"):
            env.step(np.asarray([np.nan] * 8))
        assert _FAKE_WORLD.calls["step"] == steps_before
        assert env.execution_fault is None
    finally:
        env.close()

    _FAKE_WORLD = _World()
    _FAKE_WORLD.fail_forward = "synthetic reset forward failure"
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch)
    try:
        with pytest.raises(RuntimeError, match="reset forward failure"):
            env.reset(seed=19, options={"init_row_index": 0})
        assert _FAKE_WORLD.calls["step"] == 0
        assert env.execution_fault is not None
        assert env.execution_fault.phase == "runtime_reset"
    finally:
        env.close()


def test_contact_query_and_semantic_oracle_use_same_real_core_path(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch, horizon=3)
    try:
        reset_obs, _ = env.reset(seed=19, options={"init_row_index": 0})
        _FAKE_WORLD.contact_pair = ("akita_black_bowl_1", "plate_1")
        current = np.asarray(reset_obs["state"]["joint_position"], dtype=np.float64)
        _, _, _, _, positive = env.step(np.asarray([*current[:7], 0.04]))
        contact = positive["contact_summary_v2"]
        assert contact["status"] == "available"
        assert contact["requested_pairs"] == contact["covered_pairs"]
        assert contact["pair_counts"]["akita_black_bowl_1/plate_1"] == 1
        _FAKE_WORLD.contact_pair = None
        _, _, _, _, negative = env.step(np.asarray([*current[:7], 0.04]))
        assert negative["contact_summary_v2"]["pair_counts"]["akita_black_bowl_1/plate_1"] == 0
        assert negative["predicate_v1"]["on_bowl_plate"]["value"] is False

        read_contact = env.session.read_contact_summary_v2

        def stale_contact(requested_pairs):
            current_contact = read_contact(requested_pairs)
            return replace(current_contact, state_revision=current_contact.state_revision - 1)

        monkeypatch.setattr(env.session, "read_contact_summary_v2", stale_contact)
        with pytest.raises(ValueError, match="contact summary is stale"):
            env.step(np.asarray([*current[:7], 0.04]))
        assert env.execution_fault is not None
        assert env.execution_fault.phase == "mixed_observation"
    finally:
        env.close()
    common = {
        "task_uid": PILOT_TASK_UID,
        "source_manifest_sha256": "4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75",
        "frame_id": "world",
        "bowl_center_m": (0.0, 0.0, 0.90),
        "plate_center_m": (0.0, 0.0, 0.80),
        "geom_group_contact": True,
    }
    source_manifest = "4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75"
    positive_oracle = evaluate_on_bowl_plate_v1(
        OnBowlPlateEvidenceV1(**common), expected_source_manifest_sha256=source_manifest,
    )
    assert positive_oracle.value is True
    assert evaluate_on_bowl_plate_v1(
        OnBowlPlateEvidenceV1(**{**common, "bowl_center_m": (0.03, 0.0, 0.90)}),
        expected_source_manifest_sha256=source_manifest,
    ).value is False


def test_r07v210_solution_finger_contact_groups_cover_source_collision_shapes_without_materializing(
    tmp_path, monkeypatch,
):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _FAKE_WORLD.enable_panda_kinematics = True
    fake = _fake_api(monkeypatch)
    assert getattr(fake, "__r07c_s1_synthetic_fixture__", False) is True
    import hashlib
    from bench_deploy.libero.selected_candidate import (
        DEFAULT_INSTALL_ROOT, DEFAULT_OUTPUT_ROOT, build_libero_solution_candidate,
    )

    xml_path = Path(os.environ.get("R07_V210_COMPOSED_MJCF") or os.environ["R07C_COMPOSED_MJCF"])
    xml = xml_path.read_bytes()
    env = build_libero_solution_candidate(
        xml=xml, composed_mjcf_sha256=hashlib.sha256(xml).hexdigest(),
        install_root=Path(os.environ.get("R07_V210_INSTALL_ROOT") or DEFAULT_INSTALL_ROOT),
        composition_plan_path=Path(os.environ.get(
            "R07_V210_COMPOSITION_PLAN",
            str(DEFAULT_OUTPUT_ROOT / "source/composition_plan.json"),
        )),
        horizon=2,
    )
    try:
        groups = env.value["source"].contact_geom_groups
        assert groups["panda-v1/finger-left"] == (
            "gripper0_finger1_collision", "gripper0_finger1_pad_collision",
        )
        assert groups["panda-v1/finger-right"] == (
            "gripper0_finger2_collision", "gripper0_finger2_pad_collision",
        )
        assert env.session is None
        assert _FAKE_WORLD.calls["reset"] == 0
    finally:
        env.close()


def test_r07v210_external_solution_uses_same_selected_mixed_core_and_recorder(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _FAKE_WORLD.enable_panda_kinematics = True
    fake = _fake_api(monkeypatch)
    assert getattr(fake, "__r07c_s1_synthetic_fixture__", False) is True
    import hashlib
    from bench_deploy.libero.selected_candidate import (
        DEFAULT_INSTALL_ROOT, DEFAULT_OUTPUT_ROOT, build_libero_solution_candidate,
    )
    from bench_deploy.libero.solution import LiberoPickPlaceSolutionV5
    from task_env.runtime.sessions.source import source_asset_bytes
    from task_env.recorders import load_structured_control_records_h5

    xml_path = Path(os.environ.get("R07_V210_COMPOSED_MJCF") or os.environ["R07C_COMPOSED_MJCF"])
    xml = xml_path.read_bytes()
    xml_sha = hashlib.sha256(xml).hexdigest()
    plan_path = Path(os.environ.get(
        "R07_V210_COMPOSITION_PLAN",
        str(DEFAULT_OUTPUT_ROOT / "source/composition_plan.json"),
    ))
    env = build_libero_solution_candidate(
        xml=xml, composed_mjcf_sha256=xml_sha,
        install_root=Path(os.environ.get("R07_V210_INSTALL_ROOT") or DEFAULT_INSTALL_ROOT),
        composition_plan_path=plan_path,
        horizon=100,
    )
    assert env.value["source"].contact_geom_groups["panda-v1/finger-left"] == (
        "gripper0_finger1_collision", "gripper0_finger1_pad_collision",
    )
    assert env.value["source"].contact_geom_groups["panda-v1/finger-right"] == (
        "gripper0_finger2_collision", "gripper0_finger2_pad_collision",
    )
    closure_digest = env.metadata["source_closure_digest"]
    resolver_identity = env.value['arm_resolver'].iterative_resolution_identity_v1()
    solution = LiberoPickPlaceSolutionV5(
        xml, source_closure_digest=closure_digest,
        arm_resolver_identity=resolver_identity,
    )
    gravity_model = _GravityBiasDouble(
        xml_sha, closure_digest, kinematics=env.value["arm_resolver"].model,
    )
    env.controller.set_source_gravity_model(
        gravity_model, source_xml_sha256=xml_sha, source_closure_digest=closure_digest,
    )
    wrong_xml = xml + b"\n<!-- different immutable source bytes -->\n"
    wrong_source_solution = LiberoPickPlaceSolutionV5(
        wrong_xml, source_closure_digest=closure_digest,
        arm_resolver_identity=resolver_identity,
    )
    try:
        assert env.observation_space["state"]["joint_position"].shape == (9,)
        with pytest.raises(ValueError, match="does not match the selected task/source/profile"):
            env.reset_for_solution(wrong_source_solution, seed=19, options={"init_row_index": 0})
        assert env.session is None
        assert _FAKE_WORLD.calls["reset"] == 0

        reset_obs, reset_info = env.reset_for_solution(
            solution, seed=19, options={"init_row_index": 0},
        )
        assert reset_info["reset_sample_v1"]["sample_id"] == reset_info["reset_sample_id"]
        assert reset_obs["state"]["joint_position"].shape == (9,)

        # Source reset row 0 places the bowl above the pose it reaches after
        # settling. The world-pose Solution follows this public pose until
        # grasp, then freezes it so object motion remains lift evidence.
        bowl_reset = np.asarray(
            reset_obs["privileged_state"]["bowl_body_pose"], dtype=np.float64,
        ).copy()
        reference_before = solution._initial_bowl.copy()
        settled_obs = dict(reset_obs)
        settled_obs["privileged_state"] = dict(reset_obs["privileged_state"])
        settled_bowl = bowl_reset.copy()
        settled_bowl[0, 2] -= 0.072
        settled_obs["privileged_state"]["bowl_body_pose"] = settled_bowl
        assert solution._refresh_bowl_reference_from_public_pose(settled_obs) is True
        assert solution._initial_bowl == pytest.approx(reference_before + (0.0, 0.0, -0.072))
        solution.stage = "grasp"
        grasp_reference = solution._initial_bowl.copy()
        settled_bowl[0, 2] -= 0.01
        settled_obs["privileged_state"]["bowl_body_pose"] = settled_bowl
        assert solution._refresh_bowl_reference_from_public_pose(settled_obs) is False
        assert solution._initial_bowl == pytest.approx(grasp_reference)
        solution._initial_bowl = reference_before
        solution.stage = "approach"

        # Feed two real CartesianPosePlanner outputs through the selected task
        # binding and the canonical arm resolver at the same state boundary.
        # The changed pose must alter qdesired and the final actuator Target.
        current_pose = np.asarray(reset_obs["state"]["ee_pose"], dtype=np.float64)
        goal_a = current_pose.copy()
        goal_a[0] += 0.008
        goal_b = current_pose.copy()
        goal_b[0] += 0.009
        planner_action_a = solution.pose_planner.plan_to_pose(
            current_pose=current_pose, goal_pose=goal_a, gripper=0.5, settle_steps=0,
        )[0]
        planner_action_b = solution.pose_planner.plan_to_pose(
            current_pose=current_pose, goal_pose=goal_b, gripper=0.25, settle_steps=0,
        )[0]
        assert not np.array_equal(planner_action_a, planner_action_b)
        state_boundary = env.state
        prepared_a = env.binding.prepare_mixed_control(env, planner_action_a, state_boundary)
        prepared_b = env.binding.prepare_mixed_control(env, planner_action_b, state_boundary)
        qdesired_a = np.asarray(
            prepared_a["writer_control"]["canonical_action"]["qdesired_rad"], dtype=np.float64,
        )
        qdesired_b = np.asarray(
            prepared_b["writer_control"]["canonical_action"]["qdesired_rad"], dtype=np.float64,
        )
        assert qdesired_a.shape == qdesired_b.shape == (7,)
        target_a = prepared_a["target"].channel_values
        target_b = prepared_b["target"].channel_values
        assert target_a["finger_joint1"] != target_b["finger_joint1"]
        assert target_a["finger_joint2"] == pytest.approx(-target_a["finger_joint1"])
        canonical_action_a = prepared_a["writer_control"]["canonical_action"]
        control_receipt_a = canonical_action_a["controller_receipt"]
        assert np.allclose(canonical_action_a["qdesired_rad"], qdesired_a, rtol=0.0, atol=1e-10)
        assert np.allclose(
            [target_a[f"joint{index}"] for index in range(1, 8)],
            control_receipt_a["applied_torque_Nm"], rtol=0.0, atol=1e-10,
        )
        assert prepared_a["writer_control"]["canonical_action"]["arm_target_schema_version"] == "canonical-arm-target-v1"

        env.start_recording(tmp_path / "libero_solution_s1.h5")
        observation, _reward, terminated, truncated, info = env.step_with_solution(solution)
        assert not terminated and not truncated
        assert info["selected_solution_action_v1"]["solution_identity"] == solution.identity
        assert info["selected_solution_action_v1"]["stage"] == "approach"
        assert float(info["external_action"][-1]) == pytest.approx(0.125)
        diagnostics = info["selected_solution_action_v1"]["diagnostics"]
        assert diagnostics["planner_owner"] == "CartesianPosePlanner.plan_to_pose"
        assert diagnostics["source_pose_observation_used"] is True
        control_receipt = env.controller.last_control_receipt
        expected_raw = (
            np.asarray(control_receipt["task_torque_Nm"])
            + np.asarray(control_receipt["nullspace_torque_Nm"])
            + np.asarray(control_receipt["bias_minus_passive_Nm"])
        )
        assert np.allclose(control_receipt["raw_torque_Nm"], expected_raw, rtol=0.0, atol=1e-10)
        target = info["mixed_actuator_command_v1"]["channel_values"]
        assert np.allclose(
            [target[f"joint{i}"] for i in range(1, 8)],
            control_receipt["applied_torque_Nm"], rtol=0.0, atol=1e-10,
        )
        assert info["control_step"] == 1
        assert env.recorder.transition_count == 1
        assert env.execution_fault is None

        end = env.stop("provider_free_solution_s1_complete")
        assert end.outcome.solution_completed is False
        finalized = env.finish_recording(end.outcome.end_reason)
        readback = load_structured_control_records_h5(finalized["path"])
        assert readback["transition_count"] == 1
        assert readback["observation_count"] == 2
        assert readback["outcome"].solution_completed is False
        assert observation["state"]["boundary_identity_sha256"].shape == (32,)
    finally:
        env.close()


def test_r07v210_task_resource_cleanup_belongs_to_env_lifecycle(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _FAKE_WORLD.enable_panda_kinematics = True
    _fake_api(monkeypatch)
    from bench_deploy.libero.selected_candidate import (
        DEFAULT_INSTALL_ROOT, DEFAULT_OUTPUT_ROOT, build_libero_solution_candidate,
    )

    xml_path = Path(os.environ.get("R07_V210_COMPOSED_MJCF") or os.environ["R07C_COMPOSED_MJCF"])
    xml = xml_path.read_bytes()
    xml_sha = hashlib.sha256(xml).hexdigest()
    plan_path = Path(os.environ.get(
        "R07_V210_COMPOSITION_PLAN",
        str(DEFAULT_OUTPUT_ROOT / "source/composition_plan.json"),
    ))
    install_root = Path(os.environ.get("R07_V210_INSTALL_ROOT") or DEFAULT_INSTALL_ROOT)

    ordinary = build_libero_solution_candidate(
        xml=xml, composed_mjcf_sha256=xml_sha, install_root=install_root,
        composition_plan_path=plan_path, horizon=2,
    )
    ordinary_model = _GravityBiasDouble(
        xml_sha, ordinary.metadata["source_closure_digest"],
        kinematics=ordinary.value["arm_resolver"].model,
    )
    ordinary.value["bind_source_gravity_model"](ordinary_model)
    ordinary.close()
    ordinary.close()
    assert ordinary_model.close_calls == 1
    assert ordinary.close_receipt["task_resource_close_receipt"]["closed"] is True

    failed_binding = build_libero_solution_candidate(
        xml=xml, composed_mjcf_sha256=xml_sha, install_root=install_root,
        composition_plan_path=plan_path, horizon=2,
    )
    wrong_model = _GravityBiasDouble(
        "0" * 64, failed_binding.metadata["source_closure_digest"],
        kinematics=failed_binding.value["arm_resolver"].model,
    )
    with pytest.raises(ValueError, match="differs from its selected source identity"):
        failed_binding.value["bind_source_gravity_model"](wrong_model)
    failed_binding.close()
    failed_binding.close()
    assert wrong_model.close_calls == 1
    assert failed_binding.close_receipt["task_resource_close_receipt"]["closed"] is True


def test_r07v210_solution_worker_and_independent_reader_close_all_rows(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _FAKE_WORLD.enable_panda_kinematics = True
    _fake_api(monkeypatch)
    from bench_deploy.libero.selected_candidate import (
        DEFAULT_INSTALL_ROOT, DEFAULT_OUTPUT_ROOT, build_libero_solution_candidate,
    )
    from bench_deploy.libero.solution import LiberoPickPlaceSolutionV5
    from task_env.runtime.sessions.source import source_asset_bytes

    xml_path = Path(os.environ.get("R07_V210_COMPOSED_MJCF") or os.environ["R07C_COMPOSED_MJCF"])
    xml = xml_path.read_bytes()
    xml_sha = hashlib.sha256(xml).hexdigest()
    plan_path = Path(os.environ.get(
        "R07_V210_COMPOSITION_PLAN",
        str(DEFAULT_OUTPUT_ROOT / "source/composition_plan.json"),
    ))
    install_root = Path(os.environ.get("R07_V210_INSTALL_ROOT") or DEFAULT_INSTALL_ROOT)
    env = build_libero_solution_candidate(
        xml=xml, composed_mjcf_sha256=xml_sha,
        install_root=install_root,
        composition_plan_path=plan_path, horizon=100,
    )
    parent_dir = tmp_path / "runs" / "native_synthetic_001"
    bundle = parent_dir / "bundle"
    closure_files = {
        "canonical-source.xml": xml,
        "scene.xml": xml,
        **source_asset_bytes(install_root, xml.decode("utf-8")),
    }
    closure_digest = env.metadata["source_closure_digest"]
    gravity_model = _GravityBiasDouble(
        xml_sha, closure_digest, kinematics=env.value["arm_resolver"].model,
    )
    env.controller.set_source_gravity_model(
        gravity_model, source_xml_sha256=xml_sha, source_closure_digest=closure_digest,
    )

    class _SolutionFactory:
        worker_result_schema_version = "r07-v210-task-solution-worker-result-v5"

        def __call__(self, _bundle_root):
            env.value["bind_source_gravity_model"](gravity_model)
            return LiberoPickPlaceSolutionV5(
                xml, source_closure_digest=closure_digest,
                arm_resolver_identity=env.value['arm_resolver'].iterative_resolution_identity_v1(),
            )

    result = run_libero_candidate_worker(
        # A second outer interval exercises the fresh substep command path
        # after MuJoCo's native clock has accumulated one interval of dt.
        env, output_dir=bundle, steps=2,
        solution_factory=_SolutionFactory(),
        source_closure_files=closure_files,
        composition_plan_bytes=plan_path.read_bytes(),
        solution_resource_closer=env.value["close_task_resources"],
    )
    assert result["status"] == "complete"
    assert result["episode_count"] == 3
    assert result["reset_count"] == 3
    assert result["native_step_count"] == 150
    assert len(result["attempted_episode_receipts"]) == 3
    assert all(
        item["receipt"]["pre_reset_compiled_validation_v1"]["reset_not_yet_applied"] is True
        for item in result["attempted_episode_receipts"]
    )
    assert [item["row_index"] for item in result["episodes"]] == [0, 1, 2]
    assert result["episodes"][0]["prior_session_close_receipt"] is None
    assert all(
        item["prior_session_close_receipt"]["session_closed"] is True
        for item in result["episodes"][1:]
    )
    assert all(item["solution_completed"] is False for item in result["episodes"])
    assert result["close_error"] is None
    assert result["final_session_close_receipt"]["session_closed"] is True
    assert result["solution_resource_close_receipt"]["closed"] is True
    assert result["solution_resource_close_receipt"]["forward_call_count"] == 150
    assert gravity_model.close_calls == 1
    assert env.close_receipt["task_resource_close_receipt"]["closed"] is True
    assert not (bundle / "source_inputs/closure").exists()
    assert (bundle / "source_inputs/closure.tar.gz").is_file()

    receipt = consume_libero_candidate_bundle(bundle / "worker_result.json")
    assert receipt["schema_version"] == "r07-v210-task-solution-independent-reader-v5"
    assert receipt["status"] == "verified_complete"
    assert receipt["episode_count"] == 3
    assert receipt["observation_count"] == 9
    assert receipt["solution_completed_episodes"] == 0
    runtime_receipt = consume_libero_candidate_bundle(
        bundle / "worker_result.json", require_mujoco_runtime_identity=True,
    )
    assert runtime_receipt["mujoco_runtime_identity_required"] is True
    tampered_worker_path = bundle / "tampered_runtime_worker_result.json"
    tampered_worker = json.loads((bundle / "worker_result.json").read_text())
    tampered_worker["episodes"][0]["pre_reset_compiled_validation_v1"][
        "runtime_identity"]["provider_build"]["package_version"] = "3.8.2"
    tampered_payload = {key: value for key, value in tampered_worker.items() if key != "result_sha256"}
    tampered_worker["result_sha256"] = hashlib.sha256(json.dumps(
        tampered_payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    tampered_worker_path.write_text(json.dumps(tampered_worker, sort_keys=True))
    with pytest.raises(ValueError, match="pinned MuJoCo runtime"):
        consume_libero_candidate_bundle(
            tampered_worker_path, require_mujoco_runtime_identity=True,
        )

    tampered_substep_h5 = bundle / "episode_00_row_00" / "tampered_stepwise_trajectory.h5"
    shutil.copy2(bundle / result["episodes"][0]["h5"]["relative_path"], tampered_substep_h5)
    def tamper_substep_torque(rows):
        receipt = rows[0]["writer_controls"][0]["canonical_action"][
            "physics_rate_control_v1"]["substeps"][1]["controller_receipt"]
        receipt["raw_torque_Nm"][0] += 0.01

    _rewrite_h5_json(
        tampered_substep_h5, "meta/structured_controls_v1_json", tamper_substep_torque,
    )
    tampered_substep_worker_path = bundle / "tampered_stepwise_worker_result.json"
    tampered_substep_worker = json.loads((bundle / "worker_result.json").read_text())
    tampered_substep_worker["episodes"][0]["h5"]["relative_path"] = (
        tampered_substep_h5.relative_to(bundle).as_posix()
    )
    tampered_substep_worker_path.write_text(json.dumps(tampered_substep_worker, sort_keys=True))
    _reseal_bundle(tampered_substep_worker_path)
    with pytest.raises(ValueError, match="independently recomputed OSC torque law"):
        consume_libero_candidate_bundle(tampered_substep_worker_path)

    _FAKE_WORLD = _World()
    _FAKE_WORLD.enable_panda_kinematics = True
    _fake_api(monkeypatch)
    failed_env = build_libero_solution_candidate(
        xml=xml, composed_mjcf_sha256=xml_sha,
        install_root=install_root,
        composition_plan_path=plan_path, horizon=100,
    )
    _FAKE_WORLD.fail_step_after = 0
    failed_closure_digest = failed_env.metadata["source_closure_digest"]
    failed_gravity_model = _GravityBiasDouble(
        xml_sha, failed_closure_digest, kinematics=failed_env.value["arm_resolver"].model,
    )
    failed_env.controller.set_source_gravity_model(
        failed_gravity_model, source_xml_sha256=xml_sha,
        source_closure_digest=failed_closure_digest,
    )

    class _FailedSolutionFactory:
        worker_result_schema_version = "r07-v210-task-solution-worker-result-v5"

        def __call__(self, _bundle_root):
            failed_env.value["bind_source_gravity_model"](failed_gravity_model)
            return LiberoPickPlaceSolutionV5(
                xml, source_closure_digest=failed_closure_digest,
                arm_resolver_identity=failed_env.value['arm_resolver'].iterative_resolution_identity_v1(),
            )

    failure_result = run_libero_candidate_worker(
        failed_env, output_dir=tmp_path / "solution_worker_failure_bundle", steps=1,
        solution_factory=_FailedSolutionFactory(),
        source_closure_files=closure_files,
        composition_plan_bytes=plan_path.read_bytes(),
        solution_resource_closer=failed_env.value["close_task_resources"],
    )
    assert failure_result["status"] == "failed"
    assert len(failure_result["attempted_episode_receipts"]) == 1
    assert len(failure_result["failed_episode_receipts"]) == 1
    failure = failure_result["failed_episode_receipts"][0]["receipt"]
    assert failure["last_successful_control_step"] == 0
    assert failure["next_control_step_attempted"] == 1
    assert len(failure["solution"]["last_action_receipt"]["action"]) == 8
    assert failure["execution_fault"]["phase"] == "mixed_physics_substep_interval"
    assert failed_gravity_model.close_calls == 1

    parent_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = parent_dir / "stdout.log"
    stderr_path = parent_dir / "stderr.log"
    stdout_summary = {
        "status": result["status"], "result_sha256": result["result_sha256"],
        "episode_count": result["episode_count"],
        "transition_count": result["transition_count"],
        "observation_count": result["observation_count"],
        "native_step_count": result["native_step_count"],
    }
    stdout_path.write_text(json.dumps(stdout_summary) + "\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    expected_lock = Path(
        "/home/lly/Program_Files/Geochora/workspace/maintenance/"
        "phase_ii_01_sol_luna_handoff_20261023_001/shared_native_execution.lock"
    )
    argv = [
        sys.executable, "-m", "bench_deploy.libero.core_candidate_worker",
        "--run-worker", str(bundle), "--steps", "2", "--task-solution-1",
        "--source-xml", str(xml_path), "--composition-plan", str(plan_path),
        "--install-root", str(install_root),
    ]
    parent_record = {
        "schema_version": "r07-v210-required123-run-record-v1",
        "exit_code": 0, "termination_reason": None,
        "process_group_confirmed_exited": True,
        "lock_path": str(expected_lock), "lock_acquired": True,
        "lock_released_after_group_exit": True,
        "argv": argv,
        "cwd": str(parent_dir),
        "environment": {
            "PYTHONPATH": (
                "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora/GeoPhys/src:"
                "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora"
            ),
        },
        "stdout_path": str(stdout_path.relative_to(tmp_path)),
        "stdout_bytes": stdout_path.stat().st_size,
        "stderr_path": str(stderr_path.relative_to(tmp_path)),
        "stderr_bytes": stderr_path.stat().st_size,
    }
    parent_record_path = parent_dir / "run_record.json"
    parent_record_path.write_text(json.dumps(parent_record, sort_keys=True), encoding="utf-8")
    parent_verified = consume_libero_candidate_bundle(
        bundle / "worker_result.json", parent_run_record_path=parent_record_path,
        expected_lock_path=expected_lock,
    )
    assert parent_verified["parent_process"]["status"] == "verified_parent_exit_and_lock_release"
    parent_record["cwd"] = "/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora"
    parent_record_path.write_text(json.dumps(parent_record, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="task Solution parent run directory"):
        consume_libero_candidate_bundle(
            bundle / "worker_result.json", parent_run_record_path=parent_record_path,
            expected_lock_path=expected_lock,
        )
    parent_record["cwd"] = str(parent_dir)
    parent_record_path.write_text(json.dumps(parent_record, sort_keys=True), encoding="utf-8")
    reader_code = """
import importlib.abc, sys
DENIED = {"mujoco", "taichi", "isaacsim", "omni", "torch"}
class BlockNativeEngines(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in DENIED:
            raise AssertionError(f"native engine import during independent readback: {fullname}")
        return None
sys.meta_path.insert(0, BlockNativeEngines())
from bench_deploy.libero.core_candidate_worker import main
result = main(["--read-bundle", sys.argv[1], "--parent-run-record", sys.argv[2],
               "--expected-lock-path", sys.argv[3]])
assert not any(name.split(".", 1)[0] in DENIED for name in sys.modules)
raise SystemExit(result)
"""
    reader_process = subprocess.run(
        [sys.executable, "-c", reader_code, str(bundle / "worker_result.json"),
         str(parent_record_path), str(expected_lock)],
        cwd="/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True, text=True, timeout=300, check=False,
    )
    assert reader_process.returncode == 0, reader_process.stderr
    assert json.loads(reader_process.stdout)["parent_process"]["lock_released_after_group_exit"] is True
    tampered_worker_path.unlink()

    h5_path = bundle / result["episodes"][0]["h5"]["relative_path"]
    with h5_path.open("r+b") as handle:
        handle.seek(0)
        original_byte = handle.read(1)
        handle.seek(0)
        handle.write(bytes([original_byte[0] ^ 1]))
    try:
        with pytest.raises(ValueError, match="H5 bytes or digest differ"):
            consume_libero_candidate_bundle(bundle / "worker_result.json")
    finally:
        with h5_path.open("r+b") as handle:
            handle.seek(0)
            handle.write(original_byte)

    archive_path = bundle / "source_inputs/closure.tar.gz"
    with archive_path.open("r+b") as handle:
        handle.seek(-1, 2)
        archive_byte = handle.read(1)
        handle.seek(-1, 2)
        handle.write(bytes([archive_byte[0] ^ 1]))
    try:
        with pytest.raises(ValueError, match="source archive or manifest bytes differ"):
            consume_libero_candidate_bundle(bundle / "worker_result.json")
    finally:
        with archive_path.open("r+b") as handle:
            handle.seek(-1, 2)
            handle.write(archive_byte)


def test_reset_plan_preflight_rejects_seed_mismatch_without_closing_live_session(monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch)
    try:
        _, info = env.reset(seed=19, options={"init_row_index": 0})
        from task_env.artifacts import ResetPlanV1, ResetSampleV1

        sample = ResetSampleV1.from_mapping(info["reset_sample_v1"])
        plan = ResetPlanV1("reset-plan-v1", sample, "diagnostic_contact_endpoint")
        session = env.session
        close_calls = []
        original_close = session.close

        def counted_close():
            close_calls.append(True)
            return original_close()

        session.close = counted_close
        compile_count = _FAKE_WORLD.calls["compile"]
        reset_count = _FAKE_WORLD.calls["reset"]
        with pytest.raises(ValueError, match="seed differs from reset seed"):
            env.reset(seed=20, options={"reset_plan_v1": plan})

        assert env.session is session
        assert env._mixed_reset_plan is None
        assert close_calls == []
        assert _FAKE_WORLD.calls["compile"] == compile_count
        assert _FAKE_WORLD.calls["reset"] == reset_count
        assert _FAKE_WORLD.calls["step"] == 0
    finally:
        env.close()


def test_reset_plan_source_layout_and_range_preflight_preserve_live_session(monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch)
    try:
        observation, info = env.reset(seed=19, options={"init_row_index": 0})
        from task_env.artifacts import ResetPlanV1, ResetSampleV1

        session = env.session
        state_before = session.snapshot()
        reset_count = _FAKE_WORLD.calls["reset"]
        step_count = _FAKE_WORLD.calls["step"]
        sample_map = info["reset_sample_v1"]

        wrong_source_map = dict(sample_map)
        wrong_source_map["source_id"] = "wrong-source-identity"
        wrong_source = ResetSampleV1.create(**wrong_source_map)
        wrong_source_plan = ResetPlanV1("reset-plan-v1", wrong_source, "task_episode")
        with pytest.raises(ValueError, match="Artifact/source identity"):
            env.reset(seed=19, options={"reset_plan_v1": wrong_source_plan})
        assert env.session is session
        assert session.snapshot() == state_before
        assert _FAKE_WORLD.calls["reset"] == reset_count

        missing_channel_map = dict(sample_map)
        missing_channel_map["joint_position"] = dict(sample_map["joint_position"])
        missing_channel_map["joint_velocity"] = dict(sample_map["joint_velocity"])
        missing_channel_map["joint_position"].pop("joint1")
        missing_channel_map["joint_velocity"].pop("joint1")
        missing_channel = ResetSampleV1.create(**missing_channel_map)
        missing_channel_plan = ResetPlanV1("reset-plan-v1", missing_channel, "task_episode")
        with pytest.raises(ValueError, match="reset semantic bindings mismatch"):
            session.reset_plan(missing_channel_plan)
        assert session.snapshot() == state_before
        assert session._reset_plan_gate_required is False
        assert _FAKE_WORLD.calls["reset"] == reset_count

        out_of_range_map = dict(sample_map)
        out_of_range_map["joint_position"] = dict(sample_map["joint_position"])
        out_of_range_map["joint_position"]["joint1"] = 100.0
        out_of_range = ResetSampleV1.create(**out_of_range_map)
        out_of_range_plan = ResetPlanV1("reset-plan-v1", out_of_range, "task_episode")
        with pytest.raises(ValueError, match="reset position exceeds source joint limits"):
            session.reset_plan(out_of_range_plan)
        assert env.session is session
        assert session.snapshot() == state_before
        assert session._reset_plan_gate_required is False
        assert _FAKE_WORLD.calls["reset"] == reset_count

        action = np.asarray([*observation["state"]["joint_position"][:7], 0.04], dtype=np.float64)
        env.step(action)
        assert _FAKE_WORLD.calls["step"] == step_count + 25
    finally:
        env.close()


@pytest.mark.parametrize("failure", ["compile", "named_layout"])
def test_selected_compile_and_named_layout_fail_before_reset_or_step(monkeypatch, failure):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    if failure == "compile":
        _FAKE_WORLD.fail_compile = "synthetic source compile failure"
    else:
        _FAKE_WORLD.bad_joint_address = "robot0_joint1"
    env = _candidate(monkeypatch)
    message = "synthetic source compile failure" if failure == "compile" else "compiled scalar joint order"
    try:
        with pytest.raises((RuntimeError, ValueError), match=message):
            env.reset(seed=19, options={"init_row_index": 0})
        assert _FAKE_WORLD.calls["reset"] == 0
        assert _FAKE_WORLD.calls["step"] == 0
        assert env.execution_fault is not None
        assert env.execution_fault.phase == "session_materialization"
    finally:
        env.close()
        env.close()


def test_recorder_append_and_finalizer_failures_keep_fault_and_close_receipt(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch)
    observation, _ = env.reset(seed=19, options={"init_row_index": 0})
    env.start_recording(tmp_path / "append_failure.h5")

    def fail_append(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("synthetic recorder append failure")

    env.recorder.append_transition = fail_append
    current = np.asarray(observation["state"]["joint_position"], dtype=np.float64)
    with pytest.raises(RuntimeError, match="synthetic recorder append failure"):
        env.step(np.asarray([*current[:7], 0.04]))
    assert env.execution_fault is not None
    assert env.execution_fault.phase == "mixed_recorder_append"
    assert env.execution_fault.transition_status == "not_recorded"
    assert env.execution_fault.interval_completed is True
    env.close()
    env.close()
    assert env.close_receipt["session_closed"] is True

    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    finalize_env = _candidate(monkeypatch)
    finalize_env.reset(seed=19, options={"init_row_index": 0})
    finalize_env.start_recording(tmp_path / "finalizer_failure.h5")
    end = finalize_env.stop("s1_finalizer_failure")

    def fail_save(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("synthetic H5 finalizer failure")

    finalize_env.recorder.save_h5 = fail_save
    with pytest.raises(RuntimeError, match="synthetic H5 finalizer failure"):
        finalize_env.finish_recording(end.outcome.end_reason)
    finalize_env.close()
    assert finalize_env.close_receipt["session_closed"] is True


def test_worker_result_serialization_failure_occurs_after_close(tmp_path, monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    _FAKE_WORLD.contact_pair = _contact_pair_only_when_source_pose_is_on
    env = _candidate(monkeypatch, horizon=2)
    import bench_deploy.libero.core_candidate_worker as worker

    def fail_write(path, value):
        del path, value
        raise RuntimeError("synthetic worker result serialization failure")

    monkeypatch.setattr(worker, "_write_json", fail_write)
    with pytest.raises(RuntimeError, match="synthetic worker result serialization failure"):
        run_libero_candidate_worker(env, output_dir=tmp_path / "serialization_failure", steps=1)
    assert env.close_receipt["session_closed"] is True
