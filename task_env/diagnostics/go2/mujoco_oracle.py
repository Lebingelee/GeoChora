"""Independent MuJoCo Go2 forward oracle for Stage 16 comparisons.

This file intentionally does not import ``task_env.tasks.go2_walk``.  It
loads the canonical menagerie XML directly and reproduces only the reference
policy transform (observation, PD torque, and one policy tick), so a later
GeoPhys-vs-MuJoCo comparison cannot accidentally compare code with itself.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np


from ...utils._paths import MUJOCO_MENAGERIE_ROOT

XML_PATH = MUJOCO_MENAGERIE_ROOT / "unitree_go2" / "go2.xml"
GO2_BASE_BODY_NAME = "base"
JOINT_NAMES = (
    "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
    "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
    "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
    "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
)
ACTUATOR_NAMES = (
    "FL_hip", "FL_thigh", "FL_calf", "FR_hip", "FR_thigh", "FR_calf",
    "RL_hip", "RL_thigh", "RL_calf", "RR_hip", "RR_thigh", "RR_calf",
)
DEFAULT_ANGLES = np.asarray((0.1, 0.8, -1.5, -0.1, 0.8, -1.5, 0.1, 1.0, -1.5, -0.1, 1.0, -1.5), dtype=np.float32)
GO2_BODY_NAMES = (
    GO2_BASE_BODY_NAME,
    "FL_hip", "FL_thigh", "FL_calf",
    "FR_hip", "FR_thigh", "FR_calf",
    "RL_hip", "RL_thigh", "RL_calf",
    "RR_hip", "RR_thigh", "RR_calf",
)

GO2_WALK_ENV_ID = "go2-walk-v1"
GO2_DEPLOY_ENV_ID = "go2-walk-deploy-v1"
GO2_DEPLOY_HEIGHT_ENV_ID = "go2-walk-deploy-height-v1"


@dataclass(frozen=True)
class Go2MujocoObservationContract:
    """MuJoCo-side projection of one registered Go2 policy contract."""

    env_id: str
    observation_dim: int
    command_dim: int
    include_linear_velocity: bool
    command_scale: tuple[float, ...]
    root_height: float
    default_height_command: float | None = None


GO2_MUJOCO_OBSERVATION_CONTRACTS = {
    GO2_WALK_ENV_ID: Go2MujocoObservationContract(
        env_id=GO2_WALK_ENV_ID,
        observation_dim=48,
        command_dim=3,
        include_linear_velocity=True,
        command_scale=(2.0, 2.0, 0.25),
        root_height=0.42,
    ),
    GO2_DEPLOY_ENV_ID: Go2MujocoObservationContract(
        env_id=GO2_DEPLOY_ENV_ID,
        observation_dim=45,
        command_dim=3,
        include_linear_velocity=False,
        command_scale=(1.0, 1.0, 0.25),
        root_height=0.34,
    ),
    GO2_DEPLOY_HEIGHT_ENV_ID: Go2MujocoObservationContract(
        env_id=GO2_DEPLOY_HEIGHT_ENV_ID,
        observation_dim=46,
        command_dim=4,
        include_linear_velocity=False,
        command_scale=(1.0, 1.0, 0.25, 1.0),
        root_height=0.34,
        default_height_command=0.34,
    ),
}

_GO2_MUJOCO_CONTRACTS_BY_DIM = {
    contract.observation_dim: contract
    for contract in GO2_MUJOCO_OBSERVATION_CONTRACTS.values()
}


def resolve_go2_mujoco_observation_contract(
    *, env_id: str | None = None, observation_dim: int | None = None
) -> Go2MujocoObservationContract:
    """Resolve a Go2 contract and reject ambiguous dimension/task combinations."""

    contract = None
    if env_id is not None:
        try:
            contract = GO2_MUJOCO_OBSERVATION_CONTRACTS[str(env_id)]
        except KeyError as exc:
            supported = ", ".join(sorted(GO2_MUJOCO_OBSERVATION_CONTRACTS))
            raise ValueError(f"unsupported Go2 env id {env_id!r}; choose one of {supported}") from exc
    if observation_dim is not None:
        try:
            by_dim = _GO2_MUJOCO_CONTRACTS_BY_DIM[int(observation_dim)]
        except KeyError as exc:
            supported = ", ".join(str(value) for value in sorted(_GO2_MUJOCO_CONTRACTS_BY_DIM))
            raise ValueError(
                f"unsupported Go2 observation dimension {observation_dim}; choose one of {supported}"
            ) from exc
        if contract is not None and contract.observation_dim != by_dim.observation_dim:
            raise ValueError(
                f"Go2 env id {contract.env_id!r} expects {contract.observation_dim}D, "
                f"but checkpoint provides {by_dim.observation_dim}D"
            )
        contract = by_dim
    if contract is None:
        raise ValueError("either env_id or observation_dim is required")
    return contract


def _disable_go2_self_collisions(root: ET.Element) -> None:
    """Match Unitree's Isaac asset flag without importing task code."""

    contact = root.find("contact")
    if contact is None:
        contact = ET.SubElement(root, "contact")
    existing = {
        (str(elem.get("body1", "")), str(elem.get("body2", "")))
        for elem in contact.findall("exclude")
    }
    for index, body_a in enumerate(GO2_BODY_NAMES):
        for body_b in GO2_BODY_NAMES[index + 1 :]:
            pair = (body_a, body_b)
            if pair in existing or (body_b, body_a) in existing:
                continue
            ET.SubElement(contact, "exclude", {"body1": body_a, "body2": body_b})


def _rotate_inverse(quat, value):
    q = np.asarray(quat, dtype=np.float32)
    v = np.asarray(value, dtype=np.float32)
    qv = q[..., 1:]
    t = 2.0 * np.cross(qv, v)
    return (v - q[..., :1] * t + np.cross(qv, t)).astype(np.float32)


class Go2MujocoOracle:
    def __init__(
        self,
        *,
        platform_box: bool = False,
        action_clip: float = 1.0,
        env_id: str = GO2_WALK_ENV_ID,
    ) -> None:
        try:
            import mujoco
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("MuJoCo oracle requires the mujoco package") from exc
        self.mujoco = mujoco
        self.observation_contract = resolve_go2_mujoco_observation_contract(env_id=env_id)
        self.action_clip = float(action_clip)
        if not np.isfinite(self.action_clip) or self.action_clip <= 0.0:
            raise ValueError("oracle action_clip must be finite and positive")
        root = ET.parse(XML_PATH).getroot()
        compiler = root.find("compiler")
        if compiler is None:
            compiler = ET.SubElement(root, "compiler")
        compiler.set("meshdir", str((XML_PATH.parent / "assets").resolve()).replace("\\", "/"))
        option = root.find("option")
        if option is None:
            option = ET.SubElement(root, "option")
        option.set("timestep", "0.005")
        option.set("gravity", "0 0 -9.81")
        _disable_go2_self_collisions(root)
        worldbody = root.find("worldbody")
        if worldbody is None:
            raise KeyError("canonical Go2 XML has no worldbody")
        support = {
            "name": "oracle_ground",
            "type": "box" if platform_box else "plane",
            "size": "20 20 0.005" if platform_box else "25 25 0.1",
            "friction": "1 0.02 0.01",
            "condim": "3",
            "contype": "1",
            "conaffinity": "1",
        }
        if platform_box:
            # Match the GeoPhys diagnostic asset: a no-joint static body makes
            # the support an ordinary rigid geom rather than the analytic
            # world-plane special case.
            support["pos"] = "0 0 0"
            platform = ET.SubElement(
                worldbody,
                "body",
                {"name": "go2_support_platform", "pos": "0 0 -0.005"},
            )
            ET.SubElement(platform, "geom", support)
        else:
            ET.SubElement(worldbody, "geom", support)
        self.model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
        self.data = mujoco.MjData(self.model)
        self.qpos_ids = np.asarray([self.model.jnt_qposadr[self.model.joint(name).id] for name in JOINT_NAMES], dtype=np.int32)
        self.dof_ids = np.asarray([self.model.jnt_dofadr[self.model.joint(name).id] for name in JOINT_NAMES], dtype=np.int32)
        self.actuator_ids = np.asarray([self.model.actuator(name).id for name in ACTUATOR_NAMES], dtype=np.int32)
        self.base_body_id = int(self.model.body(GO2_BASE_BODY_NAME).id)
        self.ctrl_low = self.model.actuator_ctrlrange[self.actuator_ids, 0].astype(np.float32)
        self.ctrl_high = self.model.actuator_ctrlrange[self.actuator_ids, 1].astype(np.float32)
        self.previous_action = np.zeros(12, dtype=np.float32)

    def reset(self, qpos=None, qvel=None) -> None:
        if qpos is None:
            self.data.qpos[:] = 0.0
            self.data.qpos[:7] = (
                0.0,
                0.0,
                self.observation_contract.root_height,
                1.0,
                0.0,
                0.0,
                0.0,
            )
            self.data.qpos[self.qpos_ids] = DEFAULT_ANGLES
        else:
            value = np.asarray(qpos, dtype=np.float64)
            if value.shape != self.data.qpos.shape:
                raise ValueError(
                    f"oracle qpos must have shape {self.data.qpos.shape}, got {value.shape}"
                )
            self.data.qpos[:] = value
        if qvel is None:
            self.data.qvel[:] = 0.0
        else:
            value = np.asarray(qvel, dtype=np.float64)
            if value.shape != self.data.qvel.shape:
                raise ValueError(
                    f"oracle qvel must have shape {self.data.qvel.shape}, got {value.shape}"
                )
            self.data.qvel[:] = value
        self.previous_action.fill(0.0)
        self.mujoco.mj_forward(self.model, self.data)

    def observation(self, command=None, action=None) -> np.ndarray:
        if action is None:
            action = self.previous_action
        quat = self.data.qpos[3:7].astype(np.float32)
        lin = _rotate_inverse(quat, self.data.qvel[:3])
        ang = _rotate_inverse(quat, self.data.qvel[3:6])
        gravity = _rotate_inverse(quat, (0.0, 0.0, -1.0))
        if command is None:
            cmd = np.zeros(self.observation_contract.command_dim, dtype=np.float32)
            if self.observation_contract.default_height_command is not None:
                cmd[-1] = self.observation_contract.default_height_command
        else:
            cmd = np.asarray(command, dtype=np.float32)
        expected_command_shape = (self.observation_contract.command_dim,)
        if cmd.shape != expected_command_shape:
            raise ValueError(
                f"{self.observation_contract.env_id} command must have shape "
                f"{expected_command_shape}, got {cmd.shape}"
            )
        command_values = cmd * np.asarray(
            self.observation_contract.command_scale, dtype=np.float32
        )
        parts = [ang * 0.25, gravity, command_values]
        if self.observation_contract.include_linear_velocity:
            parts.insert(0, lin * 2.0)
        parts.extend(
            (
                self.data.qpos[self.qpos_ids].astype(np.float32) - DEFAULT_ANGLES,
                self.data.qvel[self.dof_ids].astype(np.float32) * 0.05,
                np.asarray(action, dtype=np.float32),
            )
        )
        values = np.concatenate(parts)
        if values.shape != (self.observation_contract.observation_dim,):
            raise ValueError(
                f"oracle observation has shape {values.shape}, expected "
                f"({self.observation_contract.observation_dim},) for "
                f"{self.observation_contract.env_id}"
            )
        return values.astype(np.float32)

    def step(self, action: np.ndarray, *, command=None) -> dict[str, object]:
        """Advance one policy tick using an optional commanded velocity.

        The optional command is backward-compatible with the original oracle
        (which used a zero command) and lets policy evaluation construct the
        same 48-d observation layout used by the Go2 learner.
        """
        value = np.asarray(action, dtype=np.float32)
        if value.shape != (12,) or not np.isfinite(value).all() or np.any(np.abs(value) > self.action_clip):
            raise ValueError(
                f"oracle action must be finite with shape (12,) in "
                f"[-{self.action_clip:g},{self.action_clip:g}]"
            )
        target = DEFAULT_ANGLES + 0.25 * value
        torque = np.clip(20.0 * (target - self.data.qpos[self.qpos_ids]) - 0.5 * self.data.qvel[self.dof_ids], self.ctrl_low, self.ctrl_high).astype(np.float32)
        self.data.ctrl[self.actuator_ids] = torque
        for _ in range(4):
            self.mujoco.mj_step(self.model, self.data)
        obs = self.observation(command=command, action=value)
        self.previous_action = value.copy()
        return {"observation": obs.tolist(), "torque": torque.tolist(), "qpos": self.data.qpos.tolist(), "qvel": self.data.qvel.tolist()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--action", type=float, nargs=12, default=[0.0] * 12)
    args = parser.parse_args()
    oracle = Go2MujocoOracle()
    oracle.reset()
    rows = [oracle.step(np.asarray(args.action, dtype=np.float32)) for _ in range(args.steps)]
    print(json.dumps({"source": str(XML_PATH), "steps": rows}, indent=2))


if __name__ == "__main__":
    main()
