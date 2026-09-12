"""基础 state observation builder。

该模块只消费 RuntimeBoundary 已经 materialize 的 CPU snapshot，不读取 solver，
也不创建新的物理同步点。
"""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
from gymnasium.spaces import Box, Dict

from ..environment import (
    ObservationConfig,
    ObservationFieldSpec,
    ObservationSchema,
    RenderConfig,
    SensorObservation,
    RuntimeSnapshot,
    freeze_observation,
)
from ..assembly import TaskReferences


def _as_float32(value: np.ndarray) -> np.ndarray:
    return np.asarray(value, dtype=np.float32).copy()


def _camera_rgb(value: np.ndarray, *, layout: str, dtype: str) -> np.ndarray:
    """Materialize the CameraSpec-declared RGB leaf without recorder policy."""

    image = np.asarray(value, dtype=np.float32)
    if image.ndim != 3 or image.shape[-1] != 3:
        raise ValueError("RGB render observation must have HWC channel-last shape")
    if layout == "CHW":
        image = np.moveaxis(image, -1, 0)
    if dtype == "uint8":
        return np.rint(np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)
    return image.astype(np.float32, copy=True)


def _object_key(uid: str, suffix: str) -> str:
    return f"{uid.replace('-', '_')}_{suffix}"


class StateObservationBuilder:
    """从同一个 RuntimeSnapshot 构造 state / privileged_state observation。"""

    def __init__(
        self,
        *,
        references: TaskReferences,
        config: ObservationConfig,
        render_config: RenderConfig | None = None,
    ) -> None:
        self.references = references
        self.config = config
        self.render_config = render_config if render_config is not None else RenderConfig()
        self._panda = references.agents.get("panda-v1")
        self._state_v2 = config.schema_version == "task-env-state-v2"
        self._private_state_enabled = bool(
            self._state_v2
            and config.include_privileged_state
            and self._panda is not None
        )
        private_fields = self._private_state_fields()
        fields = [
            *self._state_fields(),
            *self._privileged_fields(),
            *private_fields,
            *self._vision_fields(),
        ]
        groups = ["state", "privileged_state"]
        if private_fields:
            groups.append("private_state")
        if self._state_v2:
            if any(field.name.startswith("rgb.") for field in fields):
                groups.append("rgb")
            if any(field.name.startswith("depth.") for field in fields):
                groups.append("depth")
        elif any(field.name.startswith("vision.") for field in fields):
            groups.append("vision")
        self._schema = ObservationSchema(
            version=config.schema_version,
            fields=tuple(fields),
            quaternion_convention="wxyz",
            groups=tuple(groups),
        )
        self._observation_space = Dict(self._spaces_from_fields(fields))

    @property
    def observation_space(self) -> Dict:
        return self._observation_space

    @property
    def schema(self) -> ObservationSchema:
        return self._schema

    def build(
        self,
        snapshot: RuntimeSnapshot,
        sensor_observation: SensorObservation | None = None,
    ) -> OrderedDict[str, OrderedDict[str, np.ndarray]]:
        state = self._build_state(snapshot)
        privileged = (
            self._build_privileged_state(snapshot)
            if self.config.include_privileged_state
            else OrderedDict()
        )
        values = [
            ("state", state),
            ("privileged_state", privileged),
        ]
        if self._private_state_enabled:
            values.append(("private_state", self._build_private_state(snapshot)))
        if "vision" in self._schema.field_names or "rgb" in self._schema.field_names:
            if sensor_observation is None:
                raise ValueError("vision observation requires SensorObservation")
            vision = self._build_vision(sensor_observation)
            if self._state_v2:
                values.extend(vision.items())
            else:
                values.append(("vision", vision))
        observation = freeze_observation(tuple(values))
        self._schema.validate(observation)
        return observation

    def _spaces_from_fields(self, fields: list[ObservationFieldSpec]) -> OrderedDict:
        spaces = OrderedDict((group, OrderedDict()) for group in self._schema.field_names)

        def _insert(cursor: OrderedDict, parts: tuple[str, ...], field: ObservationFieldSpec) -> None:
            key = parts[0]
            if len(parts) == 1:
                dtype = np.dtype(field.dtype)
                if np.issubdtype(dtype, np.integer):
                    limits = np.iinfo(dtype)
                    low, high = limits.min, limits.max
                elif np.issubdtype(dtype, np.bool_):
                    low, high = 0, 1
                else:
                    low, high = -np.inf, np.inf
                cursor[key] = Box(
                    low=low,
                    high=high,
                    shape=field.shape,
                    dtype=dtype,
                )
                return
            cursor = cursor.setdefault(key, OrderedDict())
            _insert(cursor, parts[1:], field)

        for field in fields:
            group, *leaf_parts = field.name.split(".")
            _insert(spaces[group], tuple(leaf_parts), field)

        def _to_space(value: OrderedDict):
            return Dict(
                OrderedDict(
                    (key, _to_space(child) if isinstance(child, OrderedDict) else child)
                    for key, child in value.items()
                )
            )

        return OrderedDict((group, _to_space(leaves)) for group, leaves in spaces.items())

    def _state_fields(self) -> list[ObservationFieldSpec]:
        if self._panda is None:
            return []
        fields = [
            ObservationFieldSpec(
                name="state.qpos",
                shape=(7,),
                semantic="panda arm joint positions",
            ),
            ObservationFieldSpec(
                name="state.qvel",
                shape=(7,),
                semantic="panda arm joint velocities",
            ),
            ObservationFieldSpec(
                name="state.gripper_qpos",
                shape=(2,),
                semantic="panda gripper joint positions",
            ),
            ObservationFieldSpec(
                name="state.ee_pose",
                shape=(7,),
                semantic="end-effector pose as xpos[3]+xquat_wxyz[4]",
            ),
        ]
        if self._state_v2:
            # Keep the v1 name above unchanged.  This explicit duplicate makes
            # the world frame evidence unambiguous for offline pose conversion.
            fields.append(
                ObservationFieldSpec(
                    name="state.ee_pose_world",
                    shape=(7,),
                    semantic="end-effector world pose as xpos[3]+xquat_wxyz[4]",
                )
            )
        return fields

    def _vision_fields(self) -> list[ObservationFieldSpec]:
        if not self.render_config.camera_obs:
            return []
        fields: list[ObservationFieldSpec] = []
        prefix = "rgb" if self._state_v2 else "vision.rgb"
        for camera in self.render_config.cameras:
            if camera.rgb:
                fields.append(
                    ObservationFieldSpec(
                        name=f"{prefix}.{camera.name}",
                        shape=(
                            (3, camera.height, camera.width)
                            if camera.rgb_layout == "CHW"
                            else (camera.height, camera.width, 3)
                        ),
                        dtype=camera.rgb_dtype,
                        semantic=f"{camera.name} RGB image",
                    )
                )
            if camera.depth:
                fields.append(
                    ObservationFieldSpec(
                        name=(
                            f"depth.{camera.name}"
                            if self._state_v2
                            else f"vision.depth.{camera.name}"
                        ),
                        shape=(camera.height, camera.width),
                        semantic=f"{camera.name} depth image",
                    )
                )
        return fields

    def _build_vision(
        self,
        sensor_observation: SensorObservation,
    ) -> OrderedDict[str, OrderedDict[str, np.ndarray]]:
        rgb = OrderedDict()
        for camera in self.render_config.cameras:
            if not camera.rgb:
                continue
            if camera.name not in sensor_observation.rgb:
                raise ValueError(f"missing RGB render observation for {camera.name}")
            rgb[camera.name] = _camera_rgb(
                sensor_observation.rgb[camera.name],
                layout=camera.rgb_layout,
                dtype=camera.rgb_dtype,
            )
        values = []
        if rgb:
            values.append(("rgb", rgb))
        depth = OrderedDict()
        for camera in self.render_config.cameras:
            if not camera.depth:
                continue
            if camera.name not in sensor_observation.depth:
                raise ValueError(f"missing depth render observation for {camera.name}")
            depth[camera.name] = _as_float32(sensor_observation.depth[camera.name])
        if depth:
            values.append(("depth", depth))
        return OrderedDict(values)

    def _build_state(self, snapshot: RuntimeSnapshot) -> OrderedDict[str, np.ndarray]:
        if self._panda is None:
            return OrderedDict()
        refs = self._panda
        if snapshot.site_xpos is None or snapshot.site_xquat is None:
            raise ValueError("state observation requires site pose in RuntimeSnapshot")
        ee_pose_world = np.concatenate(
            (
                snapshot.site_xpos[int(refs.eef_site_id)],
                snapshot.site_xquat[int(refs.eef_site_id)],
            )
        ).astype(np.float32, copy=True)
        values = OrderedDict(
            (
                ("qpos", _as_float32(snapshot.qpos[refs.arm_qpos_ids])),
                ("qvel", _as_float32(snapshot.qvel[refs.arm_dof_ids])),
                ("gripper_qpos", _as_float32(snapshot.qpos[refs.gripper_qpos_ids])),
                ("ee_pose", ee_pose_world.copy()),
            )
        )
        if self._state_v2:
            values["ee_pose_world"] = ee_pose_world
        return values

    def _private_state_fields(self) -> list[ObservationFieldSpec]:
        if not self._private_state_enabled:
            return []
        return [
            ObservationFieldSpec(
                name="private_state.robot_base_pose_world",
                shape=(7,),
                semantic="resolved robot base world pose as xpos[3]+xquat_wxyz[4]",
            )
        ]

    def _build_private_state(self, snapshot: RuntimeSnapshot) -> OrderedDict[str, np.ndarray]:
        if self._panda is None or snapshot.body_xpos is None or snapshot.body_xquat is None:
            raise ValueError("private_state requires resolved robot base body pose")
        base_id = int(self._panda.base_body_id)
        return OrderedDict(
            (
                (
                    "robot_base_pose_world",
                    np.concatenate(
                        (snapshot.body_xpos[base_id], snapshot.body_xquat[base_id])
                    ).astype(np.float32, copy=True),
                ),
            )
        )

    def _privileged_fields(self) -> list[ObservationFieldSpec]:
        if not self.config.include_privileged_state:
            return []
        fields: list[ObservationFieldSpec] = []
        for refs in self.references.objects.values():
            prefix = "privileged_state"
            if refs.qpos_ids.size:
                fields.append(
                    ObservationFieldSpec(
                        name=f"{prefix}.{_object_key(refs.uid, 'qpos')}",
                        shape=(int(refs.qpos_ids.size),),
                        semantic=f"{refs.uid} free/object joint qpos",
                    )
                )
            if refs.body_ids.size:
                fields.append(
                    ObservationFieldSpec(
                        name=f"{prefix}.{_object_key(refs.uid, 'body_pose')}",
                        shape=(int(refs.body_ids.size), 7),
                        semantic=f"{refs.uid} body poses as xpos[3]+xquat_wxyz[4]",
                    )
                )
            if refs.site_ids.size:
                fields.append(
                    ObservationFieldSpec(
                        name=f"{prefix}.{_object_key(refs.uid, 'site_pos')}",
                        shape=(int(refs.site_ids.size), 3),
                        semantic=f"{refs.uid} task site world positions",
                    )
                )
        if self.references.objects and self._panda is not None:
            fields.extend(
                [
                    ObservationFieldSpec(
                        name="privileged_state.first_object_to_ee_pos",
                        shape=(3,),
                        semantic="first object body position minus end-effector position",
                    ),
                    ObservationFieldSpec(
                        name="privileged_state.first_object_to_ee_dist",
                        shape=(1,),
                        semantic="euclidean distance from first object body to end-effector",
                    ),
                ]
            )
        return fields

    def _build_privileged_state(
        self,
        snapshot: RuntimeSnapshot,
    ) -> OrderedDict[str, np.ndarray]:
        if not self.references.objects:
            return OrderedDict()
        if snapshot.body_xpos is None or snapshot.body_xquat is None:
            raise ValueError("privileged observation requires body pose in RuntimeSnapshot")
        if snapshot.site_xpos is None:
            raise ValueError("privileged observation requires site pose in RuntimeSnapshot")

        values: OrderedDict[str, np.ndarray] = OrderedDict()
        first_body_position: np.ndarray | None = None
        for refs in self.references.objects.values():
            if refs.qpos_ids.size:
                values[_object_key(refs.uid, "qpos")] = _as_float32(
                    snapshot.qpos[refs.qpos_ids]
                )
            if refs.body_ids.size:
                body_pose_parts = []
                for body_id in refs.body_ids:
                    position = snapshot.body_xpos[int(body_id)]
                    if first_body_position is None:
                        first_body_position = position
                    body_pose_parts.append(
                        np.concatenate((position, snapshot.body_xquat[int(body_id)]))
                    )
                values[_object_key(refs.uid, "body_pose")] = np.asarray(
                    body_pose_parts, dtype=np.float32
                )
            if refs.site_ids.size:
                values[_object_key(refs.uid, "site_pos")] = _as_float32(
                    snapshot.site_xpos[refs.site_ids]
                )
        if first_body_position is not None and self._panda is not None:
            eef_position = snapshot.site_xpos[int(self._panda.eef_site_id)]
            relative_pos = _as_float32(first_body_position - eef_position)
            values["first_object_to_ee_pos"] = relative_pos
            values["first_object_to_ee_dist"] = np.asarray(
                [np.linalg.norm(relative_pos)], dtype=np.float32
            )
        return values
