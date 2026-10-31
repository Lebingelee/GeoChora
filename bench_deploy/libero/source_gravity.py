"""Source-bound gravity-bias and operational-space dynamics for LIBERO."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
from typing import Mapping

import numpy as np

from task_env.assembly.assets import _source_closure_digest, _source_closure_manifest

from .task_contracts import TASK_1


SOURCE_GRAVITY_PROFILE_V1 = "libero-source-mjcf-gravity-bias-v1"
SOURCE_OPERATIONAL_SPACE_PROFILE_V1 = "libero-source-operational-space-state-v1"
_MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
_MAX_EXPANDED_BYTES = 128 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 1024
_TCP_SITE_NAME = "gripper0_grip_site"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_source_closure_archive(path: Path, expected_manifest) -> dict[str, bytes]:
    """Read a bounded tar closure and reject aliases, links and special members."""
    archive_path = Path(path)
    if archive_path.is_symlink():
        raise ValueError("source closure archive must not be a symlink")
    archive_path = archive_path.resolve(strict=True)
    if not archive_path.is_file() or archive_path.stat().st_size > _MAX_ARCHIVE_BYTES:
        raise ValueError("source closure archive is not a bounded regular file")
    expected = {}
    for row in expected_manifest:
        if not isinstance(row, Mapping):
            raise ValueError("source closure archive manifest row is malformed")
        logical = row.get("path")
        if (type(logical) is not str or not logical or logical in expected
                or logical.startswith("/") or "\\" in logical
                or any(part in {"", ".", ".."} for part in logical.split("/"))):
            raise ValueError("source closure archive manifest has an unsafe or duplicate path")
        size = row.get("size_bytes")
        sha = row.get("sha256")
        if (type(size) is not int or size < 0 or type(sha) is not str
                or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)):
            raise ValueError("source closure archive manifest has invalid byte identity")
        expected[logical] = (size, sha)
    if not expected:
        raise ValueError("source closure archive manifest is empty")
    expected_dirs = {"closure"}
    for logical in expected:
        parts = PurePosixPath("closure", logical).parts
        for i in range(1, len(parts)):
            expected_dirs.add("/".join(parts[:i]))
    files: dict[str, bytes] = {}
    directories: set[str] = set()
    expanded = 0
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            if len(members) > _MAX_ARCHIVE_MEMBERS:
                raise ValueError("source closure archive has too many members")
            seen = set()
            for member in members:
                name = member.name
                if (type(name) is not str or not name or name.startswith("/")
                        or "\\" in name or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))):
                    raise ValueError("source closure archive has an unsafe member path")
                if name in seen:
                    raise ValueError("source closure archive has duplicate members")
                seen.add(name)
                normalized = name.rstrip("/")
                if member.isdir():
                    if normalized not in expected_dirs or member.size != 0:
                        raise ValueError("source closure archive has an unlisted directory")
                    directories.add(normalized)
                    continue
                if not member.isfile() or not name.startswith("closure/"):
                    raise ValueError("source closure archive contains a link or non-regular member")
                logical = name[len("closure/"):]
                if logical not in expected or logical in files:
                    raise ValueError("source closure archive member set differs from its manifest")
                expected_size, expected_sha = expected[logical]
                if member.size != expected_size:
                    raise ValueError("source closure archive member size differs from its manifest")
                expanded += member.size
                if expanded > _MAX_EXPANDED_BYTES:
                    raise ValueError("source closure archive exceeds the expanded byte limit")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("source closure archive member could not be read")
                content = stream.read(expected_size + 1)
                if len(content) != expected_size or _sha256(content) != expected_sha:
                    raise ValueError("source closure archive member bytes differ from its manifest")
                files[logical] = content
    except (OSError, tarfile.TarError) as exc:
        raise ValueError("source closure archive is not a valid bounded tar.gz") from exc
    if set(files) != set(expected):
        raise ValueError("source closure archive is missing manifest members")
    return files


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
        source_root = bundle / "source_inputs"
        if source_root.is_symlink() or source_root.resolve(strict=True) != source_root:
            raise ValueError("gravity-bias source root is unsafe")
        if bundle not in source_root.parents:
            raise ValueError("gravity-bias source root escaped its worker bundle")
        closure_root = source_root / "closure"
        archive_path = source_root / "closure.tar.gz"

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
        if closure_root.exists():
            if closure_root.is_symlink() or closure_root.resolve(strict=True) != closure_root:
                raise ValueError("gravity-bias source closure root is unsafe")
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
            source_xml_path = closure_root / "canonical-source.xml"
        else:
            archive_files = read_source_closure_archive(archive_path, _source_closure_manifest(files))
            if archive_files != files:
                raise ValueError("gravity-bias source archive differs from the verified closure")
            source_xml_path = None

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
        if source_xml_path is not None:
            self._model = mujoco_api.MjModel.from_xml_path(str(source_xml_path))
            self.source_model_path = str(source_xml_path)
        else:
            with tempfile.TemporaryDirectory(prefix=".source-gravity-", dir=source_root) as scratch:
                scratch_root = Path(scratch) / "closure"
                for logical, content in files.items():
                    target = scratch_root.joinpath(*PurePosixPath(logical).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                model_path = scratch_root / "canonical-source.xml"
                self._model = mujoco_api.MjModel.from_xml_path(str(model_path))
                self.source_model_path = f"{archive_path}#closure/canonical-source.xml"
        self._data = mujoco_api.MjData(self._model)
        self.source_xml_sha256 = source_xml_sha256
        self.source_closure_digest = source_closure_digest
        self.composition_plan_sha256 = composition_plan_sha256
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
        self._tcp_site_id = int(mujoco_api.mj_name2id(
            self._model, mujoco_api.mjtObj.mjOBJ_SITE, _TCP_SITE_NAME,
        ))
        if self._tcp_site_id < 0:
            self._model = None
            self._data = None
            raise ValueError(f"source dynamics model omitted the bound TCP site: {_TCP_SITE_NAME}")
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

    def operational_space_state_v1(self, joint_position_rad, joint_velocity_rad_s):
        """Return copied source-model M/J/TCP/bias values for one public boundary.

        This task-local calculation uses only the pinned source model and named
        Panda coordinates. It never reads a live RuntimeSession or Provider
        model/data object and never advances physics.
        """
        if self.closed or self._model is None or self._data is None:
            raise RuntimeError("source dynamics model is closed")
        q = np.asarray(joint_position_rad, dtype=np.float64)
        qdot = np.asarray(joint_velocity_rad_s, dtype=np.float64)
        if (q.shape != (7,) or qdot.shape != (7,)
                or not np.isfinite(q).all() or not np.isfinite(qdot).all()):
            raise ValueError("source OSC state requires seven finite named arm positions and velocities")
        self._data.qpos[:] = self._model.qpos0
        self._data.qvel[:] = 0.0
        for qpos_address, dof_address, position, velocity in zip(
                self._qpos_addresses, self._dof_addresses, q, qdot, strict=True):
            self._data.qpos[qpos_address] = float(position)
            self._data.qvel[dof_address] = float(velocity)
        self._mujoco.mj_forward(self._model, self._data)
        self.forward_calls += 1

        nv = int(self._model.nv)
        mass_full = np.zeros((nv, nv), dtype=np.float64)
        self._mujoco.mj_fullM(self._model, mass_full, self._data.qM)
        jacp = np.zeros((3, nv), dtype=np.float64)
        jacr = np.zeros((3, nv), dtype=np.float64)
        self._mujoco.mj_jacSite(
            self._model, self._data, jacp, jacr, self._tcp_site_id,
        )
        dofs = np.asarray(self._dof_addresses, dtype=np.int64)
        mass = mass_full[np.ix_(dofs, dofs)].copy()
        jacobian = np.vstack((jacp[:, dofs], jacr[:, dofs])).copy()
        site_position = np.asarray(self._data.site_xpos[self._tcp_site_id], dtype=np.float64).copy()
        site_rotation = np.asarray(
            self._data.site_xmat[self._tcp_site_id], dtype=np.float64,
        ).reshape(3, 3).copy()
        bias = np.asarray([
            self._data.qfrc_bias[address] - self._data.qfrc_passive[address]
            for address in self._dof_addresses
        ], dtype=np.float64)
        if (mass.shape != (7, 7) or jacobian.shape != (6, 7)
                or site_position.shape != (3,) or site_rotation.shape != (3, 3)
                or bias.shape != (7,)
                or any(not np.isfinite(value).all()
                       for value in (mass, jacobian, site_position, site_rotation, bias))):
            raise ValueError("source OSC model produced non-finite or incomplete dynamics")
        return {
            "schema_version": "libero-source-operational-space-state-v1",
            "profile_id": SOURCE_OPERATIONAL_SPACE_PROFILE_V1,
            "model_identity_sha256": self.model_identity_sha256,
            "source_xml_sha256": self.source_xml_sha256,
            "source_closure_digest": self.source_closure_digest,
            "tcp_site_name": _TCP_SITE_NAME,
            "site_position_world_m": site_position,
            "site_rotation_world": site_rotation,
            "jacobian_world": jacobian,
            "mass_matrix_arm": mass,
            "bias_minus_passive_arm_Nm": bias,
            "forward_call_count": self.forward_calls,
            "mj_step_call_count": self.mj_step_calls,
        }

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
            "operations": {
                "gravity_torque": {
                    "profile_id": SOURCE_GRAVITY_PROFILE_V1,
                    "calculation": "zero_velocity_qfrc_bias_minus_qfrc_passive_v1",
                },
                "operational_space_state": {
                    "profile_id": SOURCE_OPERATIONAL_SPACE_PROFILE_V1,
                    "inputs": ["named_arm_joint_position_rad", "named_arm_joint_velocity_rad_s"],
                    "outputs": [
                        "arm_mass_matrix", "world_tcp_jacobian", "world_tcp_pose",
                        "bias_minus_passive_arm_torque",
                    ],
                    "physics_steps": 0,
                    "runtime_identity": dict(self.runtime_identity),
                },
            },
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


__all__ = ["MujocoSourceGravityBiasV1", "SOURCE_GRAVITY_PROFILE_V1",
           "SOURCE_OPERATIONAL_SPACE_PROFILE_V1"]
