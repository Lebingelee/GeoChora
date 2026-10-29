"""R07c D01 same-SelectedReferenceEnv provider-free S1.

Only the MuJoCo C/API leaf is synthetic.  The candidate builder, capability
admission, SelectedReferenceEnv, RuntimeSession, Controller, state/contact
projection, Generic H5 v3 Recorder, finalizer, worker, and independent reader
remain the production implementations.
"""
from __future__ import annotations

import builtins
import hashlib
import importlib.abc
import importlib.util
import io
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

from bench_deploy.libero.core_candidate_worker import (
    consume_libero_candidate_bundle, run_libero_candidate_worker,
)
from bench_deploy.libero.evaluation import (
    PILOT_TASK_UID, OnBowlPlateEvidenceV1, evaluate_on_bowl_plate_v1,
)
from task_env.recorders import load_structured_control_records_h5


_FORBIDDEN_ROOTS = {"geophys", "taichi", "isaacsim", "omni", "robosuite", "libero", "torch", "genesis"}


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
        self.jnt_qposadr = np.zeros(self.njnt, dtype=np.int32)
        self.jnt_dofadr = np.zeros(self.njnt, dtype=np.int32)
        self.jnt_limited = np.zeros(self.njnt, dtype=np.uint8)
        self.jnt_range = np.zeros((self.njnt, 2), dtype=np.float64)
        qpos_cursor = dof_cursor = 0
        for jid, node in enumerate(joint_nodes):
            kind = "free" if node.tag == "freejoint" else node.get("type", "hinge")
            self.jnt_type[jid] = {"free": 0, "hinge": 1, "slide": 2}.get(kind, 99)
            self.jnt_qposadr[jid], self.jnt_dofadr[jid] = qpos_cursor, dof_cursor
            if kind == "free":
                self._free_by_body[self._joint_body[jid]] = (qpos_cursor, dof_cursor)
                qpos_cursor += 7
                dof_cursor += 6
            else:
                qpos_cursor += 1
                dof_cursor += 1
            raw_range = node.get("range")
            if raw_range is not None:
                self.jnt_range[jid] = _floats(raw_range, 2, (0.0, 0.0))
                self.jnt_limited[jid] = node.get("limited", "auto") != "false"
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
        for aid, actuator in enumerate(actuator_nodes):
            name = actuator.get("name")
            if not name or name in self._actuator_ids:
                raise ValueError(f"missing or duplicate fake actuator name {name}")
            self._actuator_ids[name] = aid
            self.actuator_ctrlrange[aid] = _floats(
                actuator.get("ctrlrange"), 2, (-np.inf, np.inf),
            )
            self.actuator_ctrllimited[aid] = actuator.get("ctrllimited", "auto") != "false" and actuator.get("ctrlrange") is not None
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
        self._write_counter = 0
        self._world = model._world


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
    data.contact = []
    pair = world.contact_pair(model, data) if callable(world.contact_pair) else world.contact_pair
    if pair is not None:
        left, right = pair
        left_ids = [value for name, value in model._geom_ids.items()
                    if name.startswith(f"libero_contact_{left}_")]
        right_ids = [value for name, value in model._geom_ids.items()
                     if name.startswith(f"libero_contact_{right}_")]
        if left_ids and right_ids:
            data.contact = [_Contact(left_ids[0], right_ids[0])]
    data.ncon = len(data.contact)


def _mat2quat(out: np.ndarray, matrix: np.ndarray):
    m = np.asarray(matrix, dtype=np.float64).reshape(3, 3)
    trace = float(np.trace(m))
    if trace > 0:
        scale = np.sqrt(trace + 1.0) * 2
        q = (0.25 * scale, (m[2, 1] - m[1, 2]) / scale,
             (m[0, 2] - m[2, 0]) / scale, (m[1, 0] - m[0, 1]) / scale)
    else:
        q = (1.0, 0.0, 0.0, 0.0)
    out[:] = q


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


def test_compiled_libero_assets_use_receipt_bound_unique_vfs_aliases(monkeypatch):
    global _FAKE_WORLD
    _FAKE_WORLD = _World()
    _fake_api(monkeypatch)
    env = _candidate(monkeypatch)
    try:
        env.reset(seed=19, options={"init_row_index": 0})
        receipt = env.value["source"].execution_source_receipt
        assert receipt is not None
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
    assert close["schema_version"] == "r07c-d01-selected-close-v1"
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
    with pytest.raises(ValueError, match="final observation differs"):
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
        receipt["named_torque_actuator_layout"]["joint1"]["transmission_target"] = "robot0_joint2"
    layout_result.write_text(json.dumps(layout_report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _reseal_bundle(layout_result)
    with pytest.raises(ValueError, match="compiled torque transmission/range"):
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
    from task_env.controllers.canonical.contracts import MixedActuatorTargetV1

    def reverse_second_finger(rows):
        writer = rows[0]["writer_controls"][0]
        target_payload = writer["controller_target"]["payload"]
        target_payload["finger_position_m"]["finger_joint2"] = 0.01
        target = MixedActuatorTargetV1.from_mapping(target_payload)
        writer["controller_target"]["payload"] = target.to_mapping()
        writer["controller_target"]["identity_hash"] = target.identity_hash
        applied = writer["applied_control"]
        applied["target_hash"] = target.identity_hash
        applied["payload"].update(
            target_hash=target.identity_hash,
            joint_torque_Nm=dict(target.joint_torque_Nm),
            finger_position_m=dict(target.finger_position_m),
        )
    _rewrite_h5_json(sign_h5, "meta/structured_controls_v1_json", reverse_second_finger)
    _reseal_bundle(sign_result)
    with pytest.raises(ValueError, match="finger sign or aggregate-opening"):
        consume_libero_candidate_bundle(sign_result)

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
        with pytest.raises(ValueError, match="seven finite radians"):
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
    env = _candidate(monkeypatch, horizon=2)
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
        assert env._libero_reset_plan is None
        assert close_calls == []
        assert _FAKE_WORLD.calls["compile"] == compile_count
        assert _FAKE_WORLD.calls["reset"] == reset_count
        assert _FAKE_WORLD.calls["step"] == 0
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
