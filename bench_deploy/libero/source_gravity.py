"""Source-bound gravity-bias primitive for the bounded LIBERO task route."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Mapping

import numpy as np

from task_env.assembly.assets import _source_closure_digest

from .task_contracts import TASK_1


SOURCE_GRAVITY_PROFILE_V1 = "libero-source-mjcf-gravity-bias-v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MujocoSourceGravityBiasV1:
    """Compute static arm gravity bias from an independently compiled source MJCF.

    The helper consumes the exact immutable source closure already written by
    the worker. It never reads a live Env or provider-private model/data object,
    and it never advances physics with ``mj_step``.
    """

    profile_id = SOURCE_GRAVITY_PROFILE_V1

    def __init__(self, *, bundle_root: Path, source_closure_files: Mapping[str, bytes],
                 source_xml_sha256: str, source_closure_digest: str,
                 composition_plan_sha256: str, mujoco_api=None):
        bundle = Path(bundle_root)
        if bundle.is_symlink():
            raise ValueError("gravity-bias bundle root must not be a symlink")
        bundle = bundle.resolve(strict=True)
        closure_root = bundle / "source_inputs/closure"
        if closure_root.is_symlink() or closure_root.resolve(strict=True) != closure_root:
            raise ValueError("gravity-bias source closure root is unsafe")
        if bundle not in closure_root.parents:
            raise ValueError("gravity-bias source closure escaped its worker bundle")

        files = dict(source_closure_files)
        if not files or any(type(name) is not str or not name or type(raw) is not bytes
                            for name, raw in files.items()):
            raise ValueError("gravity-bias source closure must map safe names to bytes")
        for logical in files:
            path = PurePosixPath(logical)
            if (path.is_absolute() or path.as_posix() != logical or "\\" in logical
                    or any(part in {"", ".", ".."} for part in logical.split("/"))):
                raise ValueError("gravity-bias source closure contains an unsafe logical path")
        xml = files.get("canonical-source.xml")
        if (xml is None or files.get("scene.xml") != xml
                or _sha256(xml) != source_xml_sha256
                or _source_closure_digest(files) != source_closure_digest):
            raise ValueError("gravity-bias source XML or closure identity does not recompute")

        expected_paths = set(files)
        actual_paths: set[str] = set()
        for path in closure_root.rglob("*"):
            if path.is_symlink():
                raise ValueError("gravity-bias source closure contains a symlink")
            if path.is_file():
                actual_paths.add(path.relative_to(closure_root).as_posix())
        if actual_paths != expected_paths:
            raise ValueError("gravity-bias source closure has missing or unlisted files")
        for logical, expected in files.items():
            source_path = (closure_root / Path(*PurePosixPath(logical).parts)).resolve(strict=True)
            if closure_root not in source_path.parents or source_path.read_bytes() != expected:
                raise ValueError(f"gravity-bias source bytes differ from the verified closure: {logical}")

        plan_path = bundle / "source_inputs/composition_plan.json"
        plan_bytes = plan_path.read_bytes()
        if _sha256(plan_bytes) != composition_plan_sha256:
            raise ValueError("gravity-bias composition plan hash differs from the selected source")
        plan = json.loads(plan_bytes.decode("utf-8"))
        if (plan.get("identity", {}).get("task_uid") != TASK_1
                or plan.get("output", {}).get("composed_mjcf_sha256") != source_xml_sha256):
            raise ValueError("gravity-bias composition plan names a different task or XML")

        if mujoco_api is None:
            import mujoco as mujoco_api  # noqa: PLC0415 - selected native primitive only
        self._mujoco = mujoco_api
        self._model = mujoco_api.MjModel.from_xml_path(str(closure_root / "canonical-source.xml"))
        self._data = mujoco_api.MjData(self._model)
        self.source_xml_sha256 = source_xml_sha256
        self.source_closure_digest = source_closure_digest
        self.composition_plan_sha256 = composition_plan_sha256
        self.source_model_path = str(closure_root / "canonical-source.xml")
        self._qpos_addresses: list[int] = []
        self._dof_addresses: list[int] = []
        for index in range(1, 8):
            joint_id = int(mujoco_api.mj_name2id(
                self._model, mujoco_api.mjtObj.mjOBJ_JOINT, f"robot0_joint{index}",
            ))
            if joint_id < 0:
                self._model = None
                self._data = None
                raise ValueError(f"source gravity model omitted robot0_joint{index}")
            self._qpos_addresses.append(int(self._model.jnt_qposadr[joint_id]))
            self._dof_addresses.append(int(self._model.jnt_dofadr[joint_id]))
        runtime = {
            "mujoco_version": str(getattr(mujoco_api, "__version__", "unknown")),
            "api_version": int(mujoco_api.mj_version()),
        }
        identity_payload = {
            "schema_version": "libero-source-gravity-model-identity-v1",
            "profile_id": self.profile_id,
            "task_uid": TASK_1,
            "source_xml_sha256": source_xml_sha256,
            "source_closure_digest": source_closure_digest,
            "composition_plan_sha256": composition_plan_sha256,
            "model_dimensions": {
                "nq": int(self._model.nq), "nv": int(self._model.nv),
                "nbody": int(self._model.nbody), "njnt": int(self._model.njnt),
            },
            "runtime": runtime,
            "calculation": "zero_velocity_qfrc_bias_minus_qfrc_passive_v1",
        }
        self.model_identity_sha256 = hashlib.sha256(json.dumps(
            identity_payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        self.model_dimensions = identity_payload["model_dimensions"]
        self.runtime_identity = runtime
        self.forward_calls = 0
        self.mj_step_calls = 0
        self.closed = False

    def gravity_torque(self, joint_position_rad) -> np.ndarray:
        if self.closed or self._model is None or self._data is None:
            raise RuntimeError("source gravity model is closed")
        q = np.asarray(joint_position_rad, dtype=np.float64)
        if q.shape != (7,) or not np.isfinite(q).all():
            raise ValueError("source gravity query requires seven finite named arm joint positions")
        self._data.qpos[:] = self._model.qpos0
        self._data.qvel[:] = 0.0
        for address, value in zip(self._qpos_addresses, q, strict=True):
            self._data.qpos[address] = float(value)
        self._mujoco.mj_forward(self._model, self._data)
        self.forward_calls += 1
        torque = np.asarray([
            self._data.qfrc_bias[address] - self._data.qfrc_passive[address]
            for address in self._dof_addresses
        ], dtype=np.float64)
        if torque.shape != (7,) or not np.isfinite(torque).all():
            raise ValueError("source gravity model produced invalid arm force terms")
        return torque

    def identity_mapping(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "model_identity_sha256": self.model_identity_sha256,
            "source_xml_sha256": self.source_xml_sha256,
            "source_closure_digest": self.source_closure_digest,
            "composition_plan_sha256": self.composition_plan_sha256,
            "model_dimensions": dict(self.model_dimensions),
            "runtime_identity": dict(self.runtime_identity),
            "calculation": "zero_velocity_qfrc_bias_minus_qfrc_passive_v1",
            "forward_call_count": self.forward_calls,
            "mj_step_call_count": self.mj_step_calls,
        }

    def close(self) -> dict[str, object]:
        if self.closed:
            raise RuntimeError("source gravity model close may be called only once")
        self._data = None
        self._model = None
        self._mujoco = None
        self.closed = True
        return {
            "schema_version": "libero-source-gravity-model-close-v1",
            "profile_id": self.profile_id,
            "model_identity_sha256": self.model_identity_sha256,
            "source_xml_sha256": self.source_xml_sha256,
            "source_closure_digest": self.source_closure_digest,
            "model_created": True,
            "forward_call_count": self.forward_calls,
            "mj_step_call_count": self.mj_step_calls,
            "closed": self.closed,
            "model_released": self._model is None,
            "data_released": self._data is None,
        }


__all__ = ["MujocoSourceGravityBiasV1", "SOURCE_GRAVITY_PROFILE_V1"]
