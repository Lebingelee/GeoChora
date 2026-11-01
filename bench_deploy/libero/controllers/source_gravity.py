"""Source-bound gravity-bias and operational-space dynamics for LIBERO."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from task_env.runtime.sessions.source import ExecutionSourceReceiptV1

from bench_deploy.libero.artifacts.contracts import TASK_1, TASK_2, TASK_3


SOURCE_GRAVITY_PROFILE_V1 = "libero-source-mjcf-gravity-bias-v1"
SOURCE_OPERATIONAL_SPACE_PROFILE_V2 = "libero-source-operational-space-state-v2"
_TCP_SITE_NAME = "gripper0_grip_site"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MujocoSourceGravityBiasV1:
    """Compute OSC dynamics from the selected RuntimeSource's verified bytes."""

    profile_id = SOURCE_GRAVITY_PROFILE_V1

    def __init__(self, *, source_receipt: ExecutionSourceReceiptV1,
                 composition_plan_bytes: bytes, mujoco_api=None,
                 raw_source_xml_bytes: bytes | None = None,
                 model_profile_bytes: bytes | None = None,
                 task_uid: str = TASK_1):
        if task_uid not in {TASK_1, TASK_2, TASK_3}:
            raise ValueError("source gravity task identity is outside the pinned LIBERO task set")
        if not isinstance(source_receipt, ExecutionSourceReceiptV1):
            raise TypeError("source gravity model requires the selected RuntimeSource receipt")
        source_receipt.validate_snapshot()
        source_xml_bytes = source_receipt.closure_files.get("canonical-source.xml")
        if (type(source_xml_bytes) is not bytes
                or _sha256(source_xml_bytes) != source_receipt.canonical_xml_sha256):
            raise ValueError("source gravity receipt has no verified canonical XML bytes")
        if type(composition_plan_bytes) is not bytes:
            raise TypeError("source gravity model requires immutable composition plan bytes")
        source_xml_sha256 = source_receipt.canonical_xml_sha256
        source_closure_digest = source_receipt.source_closure_digest
        composition_plan_sha256 = _sha256(composition_plan_bytes)
        profiled_source = raw_source_xml_bytes is not None or model_profile_bytes is not None
        if profiled_source:
            if type(raw_source_xml_bytes) is not bytes or type(model_profile_bytes) is not bytes:
                raise ValueError("profiled gravity model requires raw MJCF and profile receipt bytes")
            try:
                profile_receipt = json.loads(model_profile_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("model profile receipt is not valid UTF-8 JSON") from exc
            canonical_profile = json.dumps(
                profile_receipt, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
            if canonical_profile != model_profile_bytes:
                raise ValueError("model profile receipt is not canonically serialized")
            from bench_deploy.libero.assembly.model_profile import (
                ROBOT_MODEL_PROFILE_V3_ID,
                normalize_libero_robosuite_model_xml_v3,
            )
            if profile_receipt.get("profile_id") != ROBOT_MODEL_PROFILE_V3_ID:
                raise ValueError("only the pinned compile-first LIBERO model profile remains supported")
            transformed, expected_profile = normalize_libero_robosuite_model_xml_v3(raw_source_xml_bytes)
            if (transformed != source_xml_bytes or canonical_profile != json.dumps(
                    expected_profile, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")):
                raise ValueError("profiled source XML differs from the deterministic task model transform")
            raw_sha = _sha256(raw_source_xml_bytes)
            if (profile_receipt.get("raw_source_xml_sha256") != raw_sha
                    or profile_receipt.get("runtime_model_xml_sha256") != source_xml_sha256
                    or profile_receipt.get("profile_id") != expected_profile.get("profile_id")):
                raise ValueError("model profile receipt does not bind the selected raw/runtime XML bytes")
            model_profile_id = profile_receipt["profile_id"]
            model_profile_receipt_sha256 = _sha256(model_profile_bytes)
        else:
            profile_receipt = None
            raw_sha = None
            model_profile_id = None
            model_profile_receipt_sha256 = None

        plan = json.loads(composition_plan_bytes.decode("utf-8"))
        plan_xml_sha = raw_sha if profiled_source else source_xml_sha256
        if (plan.get("identity", {}).get("task_uid") != task_uid
                or plan.get("output", {}).get("composed_mjcf_sha256") != plan_xml_sha):
            raise ValueError("gravity-bias composition plan names a different task or XML")

        if mujoco_api is None:
            import mujoco as mujoco_api  # noqa: PLC0415 - selected native primitive only
        self._mujoco = mujoco_api
        external_assets = {
            name: payload for name, payload in source_receipt.closure_files.items()
            if name not in {"canonical-source.xml", "scene.xml"}
        }
        self._model = mujoco_api.MjModel.from_xml_string(
            source_xml_bytes.decode("utf-8"), external_assets,
        )
        self._data = mujoco_api.MjData(self._model)
        self.source_xml_sha256 = source_xml_sha256
        self.source_closure_digest = source_closure_digest
        self.composition_plan_sha256 = composition_plan_sha256
        self.raw_source_xml_sha256 = raw_sha
        self.model_profile_id = model_profile_id
        self.model_profile_receipt_sha256 = model_profile_receipt_sha256
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
            "schema_version": "libero-source-dynamics-model-identity-v3",
            "profile_id": self.profile_id,
            "task_uid": task_uid,
            "source_xml_sha256": source_xml_sha256,
            "source_closure_digest": source_closure_digest,
            "composition_plan_sha256": composition_plan_sha256,
            "model_dimensions": {
                "nq": int(self._model.nq), "nv": int(self._model.nv),
                "nbody": int(self._model.nbody), "njnt": int(self._model.njnt),
            },
            "runtime": runtime,
            "calculation": "source_operational_space_qfrc_bias_v2",
        }
        if profiled_source:
            identity_payload.update({
                "raw_source_xml_sha256": raw_sha,
                "model_profile_id": model_profile_id,
                "model_profile_receipt_sha256": model_profile_receipt_sha256,
                "runtime_model_xml_sha256": source_xml_sha256,
            })
        self.model_identity_sha256 = hashlib.sha256(json.dumps(
            identity_payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        self.model_dimensions = identity_payload["model_dimensions"]
        self.runtime_identity = runtime
        self.forward_calls = 0
        self.mj_step_calls = 0
        self.closed = False
        self.close_receipt = None

    def operational_space_state_v2(self, joint_position_rad, joint_velocity_rad_s):
        """Return the pinned source model's OSC state and unmodified qfrc_bias."""
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
        qfrc_bias = np.asarray(
            [self._data.qfrc_bias[address] for address in self._dof_addresses],
            dtype=np.float64,
        )
        if (mass.shape != (7, 7) or jacobian.shape != (6, 7)
                or site_position.shape != (3,) or site_rotation.shape != (3, 3)
                or qfrc_bias.shape != (7,)
                or any(not np.isfinite(value).all()
                       for value in (mass, jacobian, site_position, site_rotation, qfrc_bias))):
            raise ValueError("source OSC model produced non-finite or incomplete dynamics")
        return {
            "schema_version": "libero-source-operational-space-state-v2",
            "profile_id": SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
            "model_identity_sha256": self.model_identity_sha256,
            "source_xml_sha256": self.source_xml_sha256,
            "source_closure_digest": self.source_closure_digest,
            "tcp_site_name": _TCP_SITE_NAME,
            "site_position_world_m": site_position,
            "site_rotation_world": site_rotation,
            "jacobian_world": jacobian,
            "mass_matrix_arm": mass,
            "qfrc_bias_arm_Nm": qfrc_bias.copy(),
            "forward_call_count": self.forward_calls,
            "mj_step_call_count": self.mj_step_calls,
        }

    def identity_mapping(self) -> dict[str, object]:
        identity = {
            "profile_id": self.profile_id,
            "model_identity_sha256": self.model_identity_sha256,
            "source_xml_sha256": self.source_xml_sha256,
            "source_closure_digest": self.source_closure_digest,
            "composition_plan_sha256": self.composition_plan_sha256,
            "model_dimensions": dict(self.model_dimensions),
            "runtime_identity": dict(self.runtime_identity),
            "calculation": "source_operational_space_qfrc_bias_v2",
            "operations": {
                "operational_space_state_v2": {
                    "profile_id": SOURCE_OPERATIONAL_SPACE_PROFILE_V2,
                    "inputs": ["named_arm_joint_position_rad", "named_arm_joint_velocity_rad_s"],
                    "outputs": [
                        "arm_mass_matrix", "world_tcp_jacobian", "world_tcp_pose",
                        "qfrc_bias_arm_torque",
                    ],
                    "physics_steps": 0,
                    "runtime_identity": dict(self.runtime_identity),
                },
            },
            "forward_call_count": self.forward_calls,
            "mj_step_call_count": self.mj_step_calls,
        }
        if self.model_profile_id is not None:
            identity.update({
                "raw_source_xml_sha256": self.raw_source_xml_sha256,
                "model_profile_id": self.model_profile_id,
                "model_profile_receipt_sha256": self.model_profile_receipt_sha256,
            })
        return identity

    def close(self) -> dict[str, object]:
        if self.closed:
            raise RuntimeError("source gravity model close may be called only once")
        self._data = None
        self._model = None
        self._mujoco = None
        self.closed = True
        receipt = {
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
        if self.model_profile_id is not None:
            receipt.update({
                "raw_source_xml_sha256": self.raw_source_xml_sha256,
                "model_profile_id": self.model_profile_id,
                "model_profile_receipt_sha256": self.model_profile_receipt_sha256,
            })
        self.close_receipt = receipt
        return receipt


__all__ = ["MujocoSourceGravityBiasV1", "SOURCE_GRAVITY_PROFILE_V1",
           "SOURCE_OPERATIONAL_SPACE_PROFILE_V2"]
