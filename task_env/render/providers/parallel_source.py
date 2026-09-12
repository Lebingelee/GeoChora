"""Selected-world render bridge for the P2-S18c batch layouts.

The batch physics owners remain the only owners of mutable world state.  This
module allocates one renderer-side proxy and one bounded snapshot ring, then
copies only the requested world into that proxy on device.  The existing
``SceneVisualizationSource`` and internal raster/raytracer backends consume
the resulting snapshot exactly as they do for a single environment.
"""

from dataclasses import replace
from typing import Any, Sequence
import time

import numpy as np
import taichi as ti

from visualization.rigid_provider import ExplicitRigidRenderProvider
from visualization.rigid_source import GeometryVisualizationSource
from visualization.scene_source import SceneVisualizationSource
from visualization.snapshot_source import create_scene_render_snapshot_binding

from .parallel import ParallelRenderSourceProtocol
from ..tools.processing import RenderProcessor


@ti.kernel
def _copy_flat_vec3_with_offset(
    start: ti.i32,
    target_start: ti.i32,
    count: ti.i32,
    offset: ti.types.vector(3, ti.f32),
    source: ti.template(),
    target: ti.template(),
):
    for index in range(count):
        target[target_start + index][0] = source[start + index][0] + offset[0]
        target[target_start + index][1] = source[start + index][1] + offset[1]
        target[target_start + index][2] = source[start + index][2] + offset[2]


@ti.kernel
def _copy_flat_vec4(
    start: ti.i32,
    target_start: ti.i32,
    count: ti.i32,
    source: ti.template(),
    target: ti.template(),
):
    for index in range(count):
        for component in ti.static(range(4)):
            target[target_start + index][component] = source[start + index][component]


@ti.kernel
def _copy_batched_vec3_with_offset(
    world: ti.i32,
    target_start: ti.i32,
    count: ti.i32,
    offset: ti.types.vector(3, ti.f32),
    source: ti.template(),
    target: ti.template(),
):
    for index in range(count):
        target[target_start + index][0] = source[world, index][0] + offset[0]
        target[target_start + index][1] = source[world, index][1] + offset[1]
        target[target_start + index][2] = source[world, index][2] + offset[2]


@ti.kernel
def _copy_batched_vec4(
    world: ti.i32,
    target_start: ti.i32,
    count: ti.i32,
    source: ti.template(),
    target: ti.template(),
):
    for index in range(count):
        for component in ti.static(range(4)):
            target[target_start + index][component] = source[world, index][component]


@ti.kernel
def _copy_selected_batched_vec3_with_offset(
    world_ids: ti.types.ndarray(dtype=ti.i32, ndim=1),
    offsets: ti.types.ndarray(dtype=ti.f32, ndim=2),
    count: ti.i32,
    source: ti.template(),
    target: ti.template(),
):
    """Gather selected worlds directly from a Taichi batched vector field."""

    for ordinal, index in ti.ndrange(world_ids.shape[0], count):
        world = world_ids[ordinal]
        target[ordinal * count + index][0] = source[world, index][0] + offsets[ordinal, 0]
        target[ordinal * count + index][1] = source[world, index][1] + offsets[ordinal, 1]
        target[ordinal * count + index][2] = source[world, index][2] + offsets[ordinal, 2]


@ti.kernel
def _copy_selected_batched_vec4(
    world_ids: ti.types.ndarray(dtype=ti.i32, ndim=1),
    count: ti.i32,
    source: ti.template(),
    target: ti.template(),
):
    """Gather selected worlds directly from a Taichi batched quaternion field."""

    for ordinal, index in ti.ndrange(world_ids.shape[0], count):
        world = world_ids[ordinal]
        for component in ti.static(range(4)):
            target[ordinal * count + index][component] = source[world, index][component]


@ti.kernel
def _copy_selected_flat_vec3_with_offset(
    world_ids: ti.types.ndarray(dtype=ti.i32, ndim=1),
    offsets: ti.types.ndarray(dtype=ti.f32, ndim=2),
    source_stride: ti.i32,
    count: ti.i32,
    source: ti.template(),
    target: ti.template(),
):
    """Gather selected worlds directly from a Taichi flat vector field."""

    for ordinal, index in ti.ndrange(world_ids.shape[0], count):
        source_index = world_ids[ordinal] * source_stride + index
        target[ordinal * count + index][0] = source[source_index][0] + offsets[ordinal, 0]
        target[ordinal * count + index][1] = source[source_index][1] + offsets[ordinal, 1]
        target[ordinal * count + index][2] = source[source_index][2] + offsets[ordinal, 2]


@ti.kernel
def _copy_selected_flat_vec4(
    world_ids: ti.types.ndarray(dtype=ti.i32, ndim=1),
    source_stride: ti.i32,
    count: ti.i32,
    source: ti.template(),
    target: ti.template(),
):
    """Gather selected worlds directly from a Taichi flat quaternion field."""

    for ordinal, index in ti.ndrange(world_ids.shape[0], count):
        source_index = world_ids[ordinal] * source_stride + index
        for component in ti.static(range(4)):
            target[ordinal * count + index][component] = source[source_index][component]


class _SelectedWorldRenderProxy:
    """One renderer-owned local field set, never a physics solver."""

    def __init__(
        self,
        *,
        body_count: int,
        geom_count: int,
        objects: Sequence[object],
        ground: object | None,
        domain_min: object,
        domain_max: object,
        geom_bodyid: object,
        geom_shape_type: object,
        geom_shape_data: object,
    ) -> None:
        self._rigid_materialization_identity = "task_env:parallel-render-proxy"
        self.execution_layout = "scalar"
        self.n_bodies_actual = int(body_count)
        self.n_bodies = int(body_count)
        self.n_geoms = int(geom_count)
        self.objects = list(objects)
        self.ground = ground
        self.domain_min_vec = np.ascontiguousarray(domain_min, dtype=np.float32)
        self.domain_max_vec = np.ascontiguousarray(domain_max, dtype=np.float32)
        body_capacity = max(1, self.n_bodies_actual)
        geom_capacity = max(1, self.n_geoms)
        self.positions = ti.Vector.field(3, ti.f32, shape=body_capacity)
        self.orientations = ti.Vector.field(4, ti.f32, shape=body_capacity)
        self.linear_velocities = ti.Vector.field(3, ti.f32, shape=body_capacity)
        self.angular_velocities = ti.Vector.field(3, ti.f32, shape=body_capacity)
        self.geom_world_pos = ti.Vector.field(3, ti.f32, shape=geom_capacity)
        self.geom_world_quat = ti.Vector.field(4, ti.f32, shape=geom_capacity)
        self.geom_bodyid = geom_bodyid
        self.geom_shape_type = geom_shape_type
        self.geom_shape_data = geom_shape_data
        self.physical_ground_plane_height = (
            float(getattr(ground, "height"))
            if ground is not None and hasattr(ground, "height")
            else None
        )


def _shape(field: object) -> tuple[int, ...]:
    try:
        return tuple(int(value) for value in field.shape)
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "parallel render state must expose a device field shape"
        ) from exc


def _as_torch_device(field: object):
    device = getattr(field, "device", None)
    if device is not None:
        return str(device)
    return "cuda" if str(getattr(field, "backend", "")).lower() == "cuda" else "cpu"


def _tint_hard_render_scene(render_scene: object) -> object:
    """为 asset-render 的模型提供与地板区分开的中性灰阶材质。"""

    from visualization.render_scene import RenderMaterialTable

    materials = []
    for material in render_scene.material_table.records:
        base = np.asarray(material.base_color[:3], dtype=np.float32)
        luminance = float(np.mean(base))
        if luminance < 0.12:
            color = (0.06, 0.06, 0.06)
        elif luminance >= 0.78:
            color = (0.78, 0.78, 0.78)
        else:
            color = (0.42, 0.42, 0.42)
        materials.append(
            replace(
                material,
                base_color=(*color, float(material.base_color[3])),
            )
        )
    return replace(
        render_scene,
        material_table=RenderMaterialTable(tuple(materials)),
        scene_revision=int(getattr(render_scene, "scene_revision", 0)) + 1,
    )


def _replicate_render_scene_for_parallel(
    render_scene: object,
    *,
    render_num: int,
    base_body_count: int,
) -> object:
    """复制动态 visual instance，资产和材质表保持单份共享。"""

    count = int(render_num)
    body_count = int(base_body_count)
    if count < 1 or body_count < 1:
        raise ValueError("hard parallel render replication counts must be positive")

    from visualization.render_scene import RenderInstanceTable

    base_instances = tuple(render_scene.instance_table.records)
    dynamic_entities = {
        str(instance.entity_id)
        for instance in base_instances
        if int(getattr(instance, "body_id", -1)) >= 0
    }
    base_infos = tuple(getattr(render_scene, "entity_infos", ()))
    instances = []
    entity_infos = []
    for ordinal in range(count):
        prefix = f"hard:{ordinal}"
        for instance in base_instances:
            body_id = int(getattr(instance, "body_id", -1))
            if body_id < 0:
                if ordinal == 0:
                    instances.append(instance)
                continue
            instances.append(
                replace(
                    instance,
                    instance_id=f"{prefix}:{instance.instance_id}",
                    entity_id=f"{prefix}:{instance.entity_id}",
                    body_id=ordinal * body_count + body_id,
                    part_id=(
                        f"{prefix}:{instance.part_id}"
                        if str(getattr(instance, "part_id", ""))
                        else instance.part_id
                    ),
                )
            )
        for info in base_infos:
            entity_id = str(getattr(info, "entity_id", ""))
            if entity_id in dynamic_entities:
                entity_infos.append(
                    replace(
                        info,
                        entity_id=f"{prefix}:{entity_id}",
                        owner_id=(
                            ordinal * body_count + int(info.owner_id)
                            if int(getattr(info, "owner_id", -1)) >= 0
                            else int(getattr(info, "owner_id", -1))
                        ),
                    )
                )
            elif ordinal == 0:
                entity_infos.append(info)

    return replace(
        render_scene,
        instance_table=RenderInstanceTable(tuple(instances)),
        entity_infos=tuple(entity_infos),
        scene_revision=int(getattr(render_scene, "scene_revision", 0)) + 1,
    )


class BatchParallelRenderSource(ParallelRenderSourceProtocol):
    """Render source shared by merged-scene and static-template runtimes."""

    def __init__(
        self,
        *,
        runtime: object,
        compiled_scene: object,
        layout_kind: str,
        render_config: object,
    ) -> None:
        self.runtime = runtime
        self.compiled_scene = compiled_scene
        self.layout_kind = str(layout_kind)
        self.render_config = render_config
        self._render_processor = RenderProcessor(render_config)
        self.num_envs = int(getattr(runtime, "num_envs"))
        self._visualizer = None
        self._window = None
        self._canvas = None
        self._closed = False
        self._fixed_camera_pose = None
        self._desired_render_num = 1
        self._hard_render = False
        self._hard_render_budget_bypass = False
        self._hard_render_budget_bytes: int | None = None
        self._renderer_stage = "idle"
        self._render_mode = "rgb_array"
        self._renderer_build_count = 0
        self._render_count = 0
        self._snapshot_publish_count = 0
        self._last_render_elapsed_s = 0.0
        self._window_open_count = 0
        self._window_reopen_count = 0
        self._render_toggle_key = "f"
        self._render_disable_key = "Escape"
        self._render_key_held: set[str] = set()
        self._pending_render_events: dict[str, bool] | None = None

        self._state_owner, self._state_layout = self._resolve_state_owner()
        base_model = compiled_scene.scene_model
        self._base_model = base_model
        self._base_objects = tuple(base_model.objects)
        self._base_ground = getattr(base_model, "ground", None)
        joint_data = dict(getattr(base_model, "joint_data", None) or {})
        # Counts are render-scene facts.  Derive them from the compiled scene
        # contract instead of reaching into a runtime facade's private layout.
        self.base_body_count = len(self._base_objects)
        self.base_geom_count = int(
            joint_data.get(
                "n_geoms",
                len(joint_data.get("geom_bodyid", ())),
            )
        )
        self._body_positions = self._state_field(
            "positions", "body_xpos", "_body_xpos"
        )
        self._body_orientations = self._state_field(
            "orientations", "body_xquat", "_body_xquat"
        )
        self._geom_positions = self._state_field(
            "geom_world_pos", "geom_xpos", "_geom_xpos"
        )
        self._geom_orientations = self._state_field(
            "geom_world_quat", "geom_xquat", "_geom_xquat"
        )

        source_domain_min = getattr(
            self._state_owner,
            "domain_min_vec",
            np.asarray((0.0, 0.0, 0.0), dtype=np.float32),
        )
        source_domain_max = getattr(
            self._state_owner,
            "domain_max_vec",
            np.asarray((1.0, 1.0, 1.0), dtype=np.float32),
        )
        self._source_domain_min = np.ascontiguousarray(source_domain_min, dtype=np.float32)
        self._source_domain_max = np.ascontiguousarray(source_domain_max, dtype=np.float32)
        self._base_geom_bodyid = np.asarray(
            joint_data.get(
                "geom_bodyid",
                np.zeros(self.base_geom_count, dtype=np.int32),
            ),
            dtype=np.int32,
        )[: self.base_geom_count]
        self._base_geom_shape_type = np.asarray(
            joint_data.get(
                "geom_type",
                np.zeros(self.base_geom_count, dtype=np.int32),
            ),
            dtype=np.int32,
        )[: self.base_geom_count]
        self._base_geom_shape_data = np.asarray(
            joint_data.get(
                "geom_size",
                np.zeros((self.base_geom_count, 3), dtype=np.float32),
            ),
            dtype=np.float32,
        ).reshape(-1, 3)[: self.base_geom_count]
        self._proxy = None
        self._scene_source = None
        self._binding = None
        self._publisher = None

    def set_parallel_render_num(self, count: int) -> None:
        value = int(count)
        if value < 1 or value > self.num_envs:
            raise ValueError("parallel render count is outside the runtime world range")
        if value == self._desired_render_num:
            return
        self._desired_render_num = value
        if self._visualizer is not None:
            self._close_renderer()

    def set_parallel_render_hard(self, enabled: bool) -> None:
        """切换资产渲染；关闭时始终回到 primitive 快路径。"""

        value = bool(enabled)
        if value == self._hard_render:
            return
        self._hard_render = value
        if self._visualizer is not None:
            self._close_renderer()

    def set_parallel_render_budget_bypass(self, enabled: bool) -> None:
        """仅为一次显式诊断跳过保守预算预检。"""

        value = bool(enabled)
        if value == self._hard_render_budget_bypass:
            return
        self._hard_render_budget_bypass = value
        if self._visualizer is not None:
            self._close_renderer()

    def _hard_render_preset_overrides(self, render_num: int) -> dict[str, object]:
        """为 16/32/64/96/128/256 个资产 world 预留可控预算。"""

        backend = str(getattr(self.render_config, "backend", "")).lower()

        def _overrides(budget: int) -> dict[str, object]:
            values: dict[str, object] = {
                "memory_budget_bytes": int(budget),
            }
            # These are Rasterizer-only preset fields.  RayTracer owns a
            # separate preset schema and must receive only the shared budget
            # contract; passing unknown fields would fail before allocation.
            if backend == "rasterizer":
                values.update(
                    {
                        "enable_ssao": False,
                        "enable_fxaa": False,
                        "enable_fog": False,
                    }
                )
            return values

        if self._hard_render_budget_bypass:
            # This is intentionally much larger than any supported topology.
            # It disables only the conservative planner gate; the backend still
            # owns the real CUDA allocations and may raise OOM during build.
            budget = 64 * 1024**3
            self._hard_render_budget_bytes = int(budget)
            return _overrides(budget)

        default_budget = (
            4
            if int(render_num) <= 16
            else 8
            if int(render_num) <= 32
            else 12
            if int(render_num) <= 64
            else 20
        ) * 1024**3
        budget = int(default_budget)
        if backend in {"rasterizer", "raytracer", "ray"}:
            try:
                import torch

                if torch.cuda.is_available():
                    free_bytes, _ = torch.cuda.mem_get_info()
                    budget = min(budget, max(16 * 1024**2, int(free_bytes * 0.70)))
            except (ImportError, RuntimeError, OSError):
                pass
        self._hard_render_budget_bytes = int(budget)
        return _overrides(budget)

    def set_parallel_render_layout(self) -> None:
        """Invalidate the camera/static renderer when grid geometry changes."""

        if self._visualizer is not None:
            self._close_renderer()

    def set_parallel_render_mode(self, mode: object) -> None:
        self._render_mode = str(getattr(mode, "value", mode))

    def set_render_control_keys(self, *, toggle: str, disable: str) -> None:
        """Configure keys owned by the training render control surface."""

        toggle_key = str(toggle).strip()
        disable_key = str(disable).strip()
        if not toggle_key or not disable_key or toggle_key == disable_key:
            raise ValueError("parallel render control keys must be non-empty and distinct")
        self._render_toggle_key = toggle_key
        self._render_disable_key = disable_key
        self._render_key_held.clear()

    @staticmethod
    def _window_key_pressed(window: object, key: str) -> bool:
        try:
            if bool(window.is_pressed(key)):
                return True
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return False
        if len(key) != 1 or not key.isalpha():
            return False
        try:
            return bool(window.is_pressed(key.upper()))
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return False

    def _poll_render_window(self) -> dict[str, bool]:
        """Pump input and cache rising-edge training render events."""

        window = self._window
        if window is None:
            events = {"running": True, "toggle": False, "disable": False}
            self._pending_render_events = events
            return events
        if not bool(getattr(window, "running", True)):
            self._render_key_held.clear()
            events = {"running": False, "toggle": False, "disable": False}
            self._pending_render_events = events
            return events
        poll_events = getattr(window, "poll_events", None)
        if callable(poll_events):
            poll_events()
        visualizer = self._visualizer
        process_camera_input = getattr(visualizer, "_process_camera_input", None)
        if callable(process_camera_input):
            process_camera_input(window)

        watched = (self._render_toggle_key, self._render_disable_key)
        pressed_now = {
            key for key in watched if self._window_key_pressed(window, key)
        }
        rising = pressed_now - self._render_key_held
        self._render_key_held = pressed_now
        events = {
            "running": True,
            "toggle": self._render_toggle_key in rising,
            "disable": self._render_disable_key in rising,
        }
        self._pending_render_events = events
        return events

    def poll_render_events(self) -> dict[str, bool]:
        """Pump the headed window without acquiring a physics snapshot."""

        return dict(self._poll_render_window())

    def consume_render_events(self) -> dict[str, bool]:
        """Consume events generated during the most recent render/poll."""

        if self._pending_render_events is None:
            return {
                "running": bool(
                    self._window is None
                    or getattr(self._window, "running", True)
                ),
                "toggle": False,
                "disable": False,
            }
        events = dict(self._pending_render_events)
        self._pending_render_events = None
        return events

    def _close_renderer(self) -> None:
        self._close_window()
        if (
            self._visualizer is not None
            and str(getattr(self.render_config, "backend", "")).lower() == "flora"
        ):
            close = getattr(self._visualizer, "close", None)
            if callable(close):
                close()
        self._visualizer = None
        self._fixed_camera_pose = None
        self._proxy = None
        self._scene_source = None
        self._binding = None
        self._publisher = None
        self._renderer_stage = "closed"

    def _build_renderer(self, render_num: int) -> None:
        object_instances = []
        for ordinal in range(int(render_num)):
            for base_object in self._base_objects:
                base_id = int(getattr(base_object, "object_id", 0))
                object_key = str(getattr(base_object, "object_key", "object"))
                instance = replace(
                    base_object,
                    object_id=ordinal * self.base_body_count + base_id,
                    object_key=f"parallel:{ordinal}:{object_key}",
                )
                object_instances.append(instance)

        geom_bodyid = np.concatenate(
            [
                self._base_geom_bodyid + ordinal * self.base_body_count
                for ordinal in range(int(render_num))
            ],
            axis=0,
        ) if self.base_geom_count else np.zeros(0, dtype=np.int32)
        geom_shape_type = np.tile(self._base_geom_shape_type, int(render_num))
        geom_shape_data = np.tile(self._base_geom_shape_data, (int(render_num), 1))
        self.body_count = int(render_num) * self.base_body_count
        self.geom_count = int(render_num) * self.base_geom_count
        self._proxy = _SelectedWorldRenderProxy(
            body_count=self.body_count,
            geom_count=self.geom_count,
            objects=object_instances,
            ground=self._base_ground,
            domain_min=self._source_domain_min,
            domain_max=self._source_domain_max,
            geom_bodyid=geom_bodyid,
            geom_shape_type=geom_shape_type,
            geom_shape_data=geom_shape_data,
        )
        rigid_source = GeometryVisualizationSource(
            ExplicitRigidRenderProvider(self._proxy)
        )
        if self._hard_render:
            imported_scene_source = (
                self.compiled_scene.imported_scene.build_scene_visualization_source(
                    self._base_model,
                    geometry_source=rigid_source,
                )
            )
            if int(render_num) == 1:
                tinted_scene = _tint_hard_render_scene(
                    imported_scene_source.read_render_scene(
                        backend=str(getattr(self.render_config, "backend", "rasterizer"))
                    )
                )
                self._scene_source = SceneVisualizationSource(
                    geometry_sources=(rigid_source,),
                    _render_scene_template=tinted_scene,
                )
            else:
                imported_render_scene = imported_scene_source.read_render_scene(
                    backend=str(getattr(self.render_config, "backend", "rasterizer"))
                )
                imported_render_scene = _tint_hard_render_scene(imported_render_scene)
                replicated_scene = _replicate_render_scene_for_parallel(
                    imported_render_scene,
                    render_num=int(render_num),
                    base_body_count=self.base_body_count,
                )
                self._scene_source = SceneVisualizationSource(
                    geometry_sources=(rigid_source,),
                    _render_scene_template=replicated_scene,
                )
        else:
            self._scene_source = SceneVisualizationSource(
                geometry_sources=(rigid_source,)
            )
            # A direct generic scene source exposes both analytic and surface
            # representations for primitive bodies.  The analytic bridge only
            # knows the body pose and therefore cannot consume a one-to-one
            # MJCF geom's local position/quaternion.  Select the surface
            # representation explicitly so SubGeomDesc's local transform is
            # preserved for every repeated world record.
            for instance in object_instances:
                self._scene_source.set_render_representation(
                    f"rigid:{int(instance.object_id)}",
                    "mesh",
                )
        self._binding = create_scene_render_snapshot_binding(
            self._scene_source,
            consumer_mode="slot",
        )
        self._publisher = self._binding.publisher
        self._renderer_build_count += 1

    def _resolve_state_owner(self) -> tuple[object, str]:
        if self.layout_kind not in {"merged_scene", "static_template"}:
            raise ValueError(f"unsupported parallel render layout: {self.layout_kind!r}")
        resolver = getattr(self.runtime, "parallel_render_state_source", None)
        if not callable(resolver):
            raise RuntimeError(
                "runtime does not expose the parallel render state port"
            )
        binding = resolver()
        if (
            not isinstance(binding, tuple)
            or len(binding) != 2
            or binding[0] is None
            or binding[1] not in {"flat", "batched", "local_solver_sequence"}
        ):
            raise RuntimeError("runtime parallel render state port is malformed")
        return binding[0], binding[1]

    def _state_field(self, *names: str):
        owner = self._state_owner
        if self._state_layout == "local_solver_sequence":
            for name in names:
                fields = tuple(getattr(item, name, None) for item in owner)
                if fields and all(field is not None for field in fields):
                    return fields
            raise RuntimeError(
                "parallel render local-solver sequence is missing selected-world state field: "
                + "/".join(names)
            )
        for name in names:
            field = getattr(owner, name, None)
            if field is not None:
                return field
        raise RuntimeError(
            "parallel render runtime is missing selected-world state field: "
            + "/".join(names)
        )

    @property
    def source_kind(self) -> str:
        return self.layout_kind

    def _copy_field(
        self,
        source: object,
        target: object,
        *,
        world_id: int,
        target_start: int,
        count: int,
        source_stride: int,
        offset: tuple[float, float, float],
        vector_width: int,
        target_count: int,
    ) -> None:
        if count <= 0:
            return
        if self._state_layout == "local_solver_sequence":
            source = source[int(world_id)]
        target_shape = _shape(target)
        # Vector width identifies the component count only.  Body quaternions
        # are vec4 just like geom quaternions, so infer the target record
        # count explicitly from the semantic field owner.
        expected_target = (max(1, int(target_count)),)
        if target_shape != expected_target:
            raise RuntimeError(
                f"parallel render proxy field shape {target_shape} does not match {expected_target}"
            )
        is_torch_tensor = source.__class__.__module__.startswith("torch")
        # Taichi fields expose ``to_torch`` too, but keeping the selection in a
        # Taichi kernel is important: a merged field is flat and the static
        # field is (world, local), so neither path needs a full-B materialized
        # tensor.  Only the fused static runtime owns native Torch tensors.
        if is_torch_tensor:
            import torch

            source_device = _as_torch_device(source)
            if callable(getattr(source, "to_torch", None)):
                value = source.to_torch(device=source_device)
            else:
                value = source
            if self._state_layout == "batched":
                selected = value[int(world_id), :count]
            elif self._state_layout == "flat":
                start = int(world_id) * int(source_stride)
                selected = value[start : start + count]
            else:
                selected = value[:count]
            if vector_width == 3:
                delta = torch.as_tensor(offset, dtype=selected.dtype, device=selected.device)
                selected = selected + delta
            target_tensor = target.to_torch(device=str(selected.device))
            target_tensor[target_start : target_start + count].copy_(selected)
            # Taichi 0.6 returns a Torch staging tensor here rather than a
            # writable zero-copy view for Vector.field.  ``copy_`` therefore
            # does not publish the update back to the renderer-owned field;
            # explicitly commit the complete staging tensor.
            target.from_torch(target_tensor)
            return

        if vector_width == 3:
            delta = ti.Vector(
                [float(offset[0]), float(offset[1]), float(offset[2])]
            )
            if self._state_layout == "batched":
                _copy_batched_vec3_with_offset(
                    int(world_id), int(target_start), int(count), delta, source, target
                )
            elif self._state_layout == "flat":
                _copy_flat_vec3_with_offset(
                    int(world_id) * int(source_stride),
                    int(target_start),
                    int(count),
                    delta,
                    source,
                    target,
                )
            else:
                _copy_flat_vec3_with_offset(
                    0, int(target_start), int(count), delta, source, target
                )
            return

        if self._state_layout == "batched":
            _copy_batched_vec4(
                int(world_id), int(target_start), int(count), source, target
            )
        elif self._state_layout == "flat":
            _copy_flat_vec4(
                int(world_id) * int(source_stride),
                int(target_start),
                int(count),
                source,
                target,
            )
        else:
            _copy_flat_vec4(0, int(target_start), int(count), source, target)

    def _copy_field_batch(
        self,
        source: object,
        target: object,
        *,
        world_ids: Sequence[int],
        world_transforms: Sequence[tuple[float, ...]],
        count: int,
        source_stride: int,
        vector_width: int,
        target_count: int,
    ) -> bool:
        """Copy a fused state field into the proxy with one device submission.

        Static-template CUDA state is native Torch with shape ``(B, local,
        width)``; gather selected worlds in one Torch operation and publish one
        complete proxy field.  Taichi batched/flat fields use the equivalent
        native gather kernels.  Local-solver sequences return ``False`` and
        retain the compatibility per-world path.
        """

        if count <= 0 or not world_ids:
            return True
        if self._state_layout == "local_solver_sequence":
            return False
        is_torch_tensor = source.__class__.__module__.startswith("torch")

        target_shape = _shape(target)
        expected_target = (max(1, int(target_count)),)
        if target_shape != expected_target:
            raise RuntimeError(
                f"parallel render proxy field shape {target_shape} does not match {expected_target}"
            )

        if not is_torch_tensor:
            # A Taichi-native static/merged state stays in Taichi all the way
            # into the renderer proxy.  The only host payload here is the
            # small selection/layout metadata, not the body/geom state.
            ids = np.ascontiguousarray(
                [int(world_id) for world_id in world_ids],
                dtype=np.int32,
            )
            offsets = np.ascontiguousarray(
                [
                    (float(transform[3]), float(transform[7]), float(transform[11]))
                    for transform in world_transforms
                ],
                dtype=np.float32,
            )
            if vector_width == 3:
                if self._state_layout == "batched":
                    _copy_selected_batched_vec3_with_offset(
                        ids, offsets, int(count), source, target
                    )
                elif self._state_layout == "flat":
                    _copy_selected_flat_vec3_with_offset(
                        ids,
                        offsets,
                        int(source_stride),
                        int(count),
                        source,
                        target,
                    )
                else:
                    return False
            elif vector_width == 4:
                if self._state_layout == "batched":
                    _copy_selected_batched_vec4(ids, int(count), source, target)
                elif self._state_layout == "flat":
                    _copy_selected_flat_vec4(
                        ids,
                        int(source_stride),
                        int(count),
                        source,
                        target,
                    )
                else:
                    return False
            else:
                raise ValueError(f"unsupported parallel render vector width: {vector_width}")
            return True

        import torch

        source_device = _as_torch_device(source)
        if callable(getattr(source, "to_torch", None)):
            value = source.to_torch(device=source_device)
        else:
            value = source
        ids = torch.as_tensor(
            tuple(int(world_id) for world_id in world_ids),
            dtype=torch.long,
            device=value.device,
        )
        if self._state_layout == "batched":
            selected = value.index_select(0, ids)[:, :count]
        elif self._state_layout == "flat":
            selected = value.reshape(-1, int(source_stride), int(vector_width))
            selected = selected.index_select(0, ids)[:, :count]
        else:
            selected = value[:count].unsqueeze(0).expand(len(world_ids), -1, -1)
        if vector_width == 3:
            offsets = torch.as_tensor(
                [
                    (float(transform[3]), float(transform[7]), float(transform[11]))
                    for transform in world_transforms
                ],
                dtype=selected.dtype,
                device=selected.device,
            )
            selected = selected + offsets[:, None, :]

        target_tensor = target.to_torch(device=str(selected.device))
        target_tensor[: len(world_ids) * count].copy_(selected.reshape(-1, vector_width))
        target.from_torch(target_tensor)
        return True

    def _publish_selected(
        self,
        *,
        world_id: int,
        ordinal: int,
        world_transform: tuple[float, ...],
    ) -> None:
        if world_id < 0 or world_id >= self.num_envs:
            raise ValueError(f"parallel render world id is outside [0, {self.num_envs})")
        offset = (
            float(world_transform[3]),
            float(world_transform[7]),
            float(world_transform[11]),
        )
        self._copy_field(
            self._body_positions,
            self._proxy.positions,
            world_id=world_id,
            target_start=int(ordinal) * self.base_body_count,
            count=self.base_body_count,
            source_stride=self.base_body_count,
            offset=offset,
            vector_width=3,
            target_count=self.body_count,
        )
        self._copy_field(
            self._body_orientations,
            self._proxy.orientations,
            world_id=world_id,
            target_start=int(ordinal) * self.base_body_count,
            count=self.base_body_count,
            source_stride=self.base_body_count,
            offset=(0.0, 0.0, 0.0),
            vector_width=4,
            target_count=self.body_count,
        )
        if self.base_geom_count > 0:
            self._copy_field(
                self._geom_positions,
                self._proxy.geom_world_pos,
                world_id=world_id,
                target_start=int(ordinal) * self.base_geom_count,
                count=self.base_geom_count,
                source_stride=self.base_geom_count,
                offset=offset,
                vector_width=3,
                target_count=self.geom_count,
            )
            self._copy_field(
                self._geom_orientations,
                self._proxy.geom_world_quat,
                world_id=world_id,
                target_start=int(ordinal) * self.base_geom_count,
                count=self.base_geom_count,
                source_stride=self.base_geom_count,
                offset=(0.0, 0.0, 0.0),
                vector_width=4,
                target_count=self.geom_count,
            )

    def _publish_selected_batch(
        self,
        *,
        world_ids: Sequence[int],
        world_transforms: Sequence[tuple[float, ...]],
    ) -> bool:
        """Publish all selected static-template Torch state in one batch."""

        if len(world_ids) != len(world_transforms) or not world_ids:
            raise ValueError("parallel render selection and transforms must be non-empty and aligned")
        for world_id in world_ids:
            if int(world_id) < 0 or int(world_id) >= self.num_envs:
                raise ValueError(f"parallel render world id is outside [0, {self.num_envs})")
        copied = self._copy_field_batch(
            self._body_positions,
            self._proxy.positions,
            world_ids=world_ids,
            world_transforms=world_transforms,
            count=self.base_body_count,
            source_stride=self.base_body_count,
            vector_width=3,
            target_count=self.body_count,
        )
        copied = self._copy_field_batch(
            self._body_orientations,
            self._proxy.orientations,
            world_ids=world_ids,
            world_transforms=world_transforms,
            count=self.base_body_count,
            source_stride=self.base_body_count,
            vector_width=4,
            target_count=self.body_count,
        ) and copied
        if self.base_geom_count > 0:
            copied = self._copy_field_batch(
                self._geom_positions,
                self._proxy.geom_world_pos,
                world_ids=world_ids,
                world_transforms=world_transforms,
                count=self.base_geom_count,
                source_stride=self.base_geom_count,
                vector_width=3,
                target_count=self.geom_count,
            ) and copied
            copied = self._copy_field_batch(
                self._geom_orientations,
                self._proxy.geom_world_quat,
                world_ids=world_ids,
                world_transforms=world_transforms,
                count=self.base_geom_count,
                source_stride=self.base_geom_count,
                vector_width=4,
                target_count=self.geom_count,
            ) and copied
        return copied

    def _set_parallel_camera_domain(
        self,
        world_transforms: Sequence[tuple[float, ...]],
    ) -> None:
        if len(world_transforms) == 1 and all(
            abs(float(world_transforms[0][index])) <= 1.0e-12
            for index in (3, 7, 11)
        ):
            return
        lower = np.asarray(self._scene_source.domain_min_vec, dtype=np.float32)
        upper = np.asarray(self._scene_source.domain_max_vec, dtype=np.float32)
        offsets = np.asarray(
            [[float(transform[3]), float(transform[7]), float(transform[11])] for transform in world_transforms],
            dtype=np.float32,
        )
        if offsets.size:
            lower = np.minimum(lower, np.min(lower[None, :] + offsets, axis=0))
            upper = np.maximum(upper, np.max(upper[None, :] + offsets, axis=0))
        self._binding.snapshot_source.domain_min_vec = lower
        self._binding.snapshot_source.domain_max_vec = upper
        template = self._binding.snapshot_source._render_scene_template
        if template is None:
            return
        center = 0.5 * (lower + upper)
        extent = upper - lower
        max_dim = max(float(np.max(extent)), 1.0e-3)
        camera = template.camera
        position = (
            float(center[0]),
            float(center[1] - 1.5 * max_dim),
            float(center[2] + 0.6 * max_dim),
        )
        look_at = tuple(float(value) for value in center)
        self._binding.snapshot_source._render_scene_template = replace(
            template,
            camera=replace(camera, position=position, look_at=look_at),
        )

    def read_metrics(self) -> dict[str, object]:
        """Return renderer-owned lifecycle metrics without reading physics fields."""

        elapsed = float(self._last_render_elapsed_s)
        backend = str(getattr(self.render_config, "backend", "")).lower()
        if backend == "flora":
            render_mode = "flora_asset_scene"
        else:
            render_mode = "hard_assets" if self._hard_render else "simple_geometry"
        metrics = {
            "schema": "task_env.parallel_render_metrics.v1",
            "parallel_render_num": int(self._desired_render_num),
            "render_backend": backend,
            "render_mode": render_mode,
            "hard_render_budget_bypass": bool(self._hard_render_budget_bypass),
            "hard_render_budget_bytes": self._hard_render_budget_bytes,
            "renderer_stage": self._renderer_stage,
            "num_envs": int(self.num_envs),
            "renderer_builds": int(self._renderer_build_count),
            "render_frames": int(self._render_count),
            "snapshot_publishes": int(self._snapshot_publish_count),
            "last_render_ms": float(elapsed * 1000.0),
            "render_fps": float(1.0 / elapsed) if elapsed > 0.0 else 0.0,
            "window_opens": int(self._window_open_count),
            "window_reopens": int(self._window_reopen_count),
            "window_attached": self._window is not None,
            "window_running": bool(
                self._window is not None
                and getattr(self._window, "running", True)
            ),
        }
        if self._visualizer is not None:
            read_resources = getattr(self._visualizer, "read_resources", None)
            if callable(read_resources):
                resources = read_resources()
                if isinstance(resources, dict):
                    metrics["renderer_resources"] = dict(resources)
                    engine_resources = resources.get("engine", {})
                    mesh_resources = (
                        engine_resources.get("mesh", {})
                        if isinstance(engine_resources, dict)
                        else {}
                    )
                    if isinstance(mesh_resources, dict):
                        for source_key, metric_key in (
                            ("unique_assets", "unique_asset_count"),
                            ("instances", "instance_count"),
                            ("geometry_estimated_bytes", "geometry_estimated_bytes"),
                            (
                                "acceleration_estimated_bytes",
                                "acceleration_estimated_bytes",
                            ),
                        ):
                            if source_key in mesh_resources:
                                metrics[metric_key] = mesh_resources[source_key]
        return metrics

    def _ensure_visualizer(
        self,
        world_transforms: Sequence[tuple[float, ...]],
    ):
        if self._closed:
            raise RuntimeError("parallel render source is closed")
        if self._visualizer is None:
            self._renderer_stage = "scene_template_and_proxy"
            try:
                self._build_renderer(self._desired_render_num)
            except Exception as exc:
                self._renderer_stage = (
                    f"failed:scene_template_and_proxy:{type(exc).__name__}"
                )
                raise RuntimeError(
                    "parallel renderer failed during scene template/proxy "
                    f"construction: {exc}"
                ) from exc
            self._set_parallel_camera_domain(world_transforms)
            self._renderer_stage = "visualizer_and_gpu_allocation"
            try:
                backend = str(getattr(self.render_config, "backend", "")).lower()
                if backend == "flora":
                    create_parallel = getattr(
                        self._render_processor.backend,
                        "create_parallel_visualizer",
                        None,
                    )
                    if not callable(create_parallel):
                        raise RuntimeError(
                            "Flora backend does not expose create_parallel_visualizer()"
                        )
                    self._visualizer = create_parallel(
                        self._binding.snapshot_source,
                        compiled_scene=self.compiled_scene,
                        render_num=self._desired_render_num,
                        width=int(self.render_config.width),
                        height=int(self.render_config.height),
                    )
                    set_domain = getattr(
                        self._visualizer,
                        "set_parallel_camera_domain",
                        None,
                    )
                    if callable(set_domain):
                        set_domain(world_transforms)
                else:
                    self._visualizer = self._render_processor.build_visualizer(
                        self._binding.snapshot_source,
                        use_render_snapshot=False,
                        render_preset_overrides=(
                            self._hard_render_preset_overrides(self._desired_render_num)
                            if self._hard_render
                            else None
                        ),
                    )
            except Exception as exc:
                self._renderer_stage = (
                    f"failed:visualizer_and_gpu_allocation:{type(exc).__name__}"
                )
                raise RuntimeError(
                    "parallel renderer failed during visualizer/GPU "
                    f"allocation: {exc}"
                ) from exc
            self._renderer_stage = "ready"
            pose = getattr(self._visualizer, "_initial_camera_pose", None)
            if pose is None or len(pose) != 3:
                raise RuntimeError("parallel visualizer has no initial camera pose")
            self._fixed_camera_pose = tuple(
                tuple(float(value) for value in component) for component in pose
            )
        return self._visualizer

    def _close_window(self) -> None:
        window = self._window
        self._window = None
        self._canvas = None
        close = getattr(window, "close", None)
        if not callable(close):
            close = getattr(window, "destroy", None)
        if callable(close):
            close()

    def _ensure_window(self, visualizer: object):
        window = self._window
        if window is not None and bool(getattr(window, "running", True)):
            return window, self._canvas
        was_reopen = window is not None
        self._close_window()
        import taichi as ti_module

        disable_ime = getattr(visualizer, "_disable_ime_for_process", None)
        if callable(disable_ime):
            disable_ime()
        window = ti_module.ui.Window(
            "GeoPhys Parallel TaskEnv",
            res=(int(self.render_config.width), int(self.render_config.height)),
            vsync=False,
            fps_limit=60,
        )
        self._window = window
        self._canvas = window.get_canvas()
        self._window_open_count += 1
        if was_reopen:
            self._window_reopen_count += 1
        return self._window, self._canvas

    def _draw_metrics_overlay(self, window: object) -> None:
        """Draw compact parallel-render metrics in headed mode only."""

        get_gui = getattr(window, "get_gui", None)
        if not callable(get_gui):
            return
        gui = get_gui()
        metrics = self.read_metrics()
        lines = (
            "GeoPhys Parallel Render",
            f"Worlds: {metrics['parallel_render_num']}/{metrics['num_envs']}",
            f"Frame: {metrics['last_render_ms']:.2f} ms ({metrics['render_fps']:.1f} FPS)",
            f"Renderer rebuilds: {metrics['renderer_builds']}",
            f"Snapshot publishes: {metrics['snapshot_publishes']}",
            f"Window reopens: {metrics['window_reopens']}",
        )
        edge_region = getattr(gui, "edge_region", None)
        if callable(edge_region):
            with edge_region("left", "Parallel Render") as panel:
                if panel is not None:
                    for line in lines:
                        panel.text(line)
            return
        text = getattr(gui, "text", None)
        if callable(text):
            for line in lines:
                text(line)

    def render_parallel(
        self,
        *,
        world_ids: tuple[int, ...],
        world_transforms: tuple[tuple[float, ...], ...],
        snapshot: object,
        width: int,
        height: int,
    ) -> np.ndarray:
        del snapshot
        if len(world_ids) != len(world_transforms) or not world_ids:
            raise ValueError("parallel render selection and transforms must be non-empty and aligned")
        visualizer = self._ensure_visualizer(world_transforms)
        self._poll_render_window()
        frame_started_at = time.perf_counter()
        if not self._publish_selected_batch(
            world_ids=world_ids,
            world_transforms=world_transforms,
        ):
            for ordinal, (world_id, transform) in enumerate(
                zip(world_ids, world_transforms)
            ):
                self._publish_selected(
                    world_id=int(world_id),
                    ordinal=int(ordinal),
                    world_transform=transform,
                )
        self._publisher.publish()
        self._snapshot_publish_count += 1
        if self._fixed_camera_pose is not None and self._render_mode == "rgb_array":
            visualizer.set_camera_pose(*self._fixed_camera_pose)
        frame = visualizer.read_frame(
            width=int(width),
            height=int(height),
            synchronized=True,
        )
        self._last_render_elapsed_s = max(
            0.0,
            time.perf_counter() - frame_started_at,
        )
        self._render_count += 1
        return np.ascontiguousarray(np.asarray(frame, dtype=np.float32))

    def present_parallel(
        self,
        *,
        frame: np.ndarray,
        world_ids: tuple[int, ...],
        world_transforms: tuple[tuple[float, ...], ...],
    ) -> None:
        del frame, world_ids, world_transforms
        visualizer = self._visualizer
        if visualizer is None:
            raise RuntimeError("parallel render visualizer is not initialized")
        window, canvas = self._ensure_window(visualizer)
        if not bool(getattr(window, "running", True)):
            self._close_window()
            return
        visualizer._synchronize_taichi_runtime()
        visualizer._present_rendered_frame(canvas)
        visualizer._mark_displayed_snapshot()
        self._draw_metrics_overlay(window)
        window.show()

    def close(self) -> None:
        if self._closed:
            return
        self._close_renderer()
        self._closed = True


__all__ = ["BatchParallelRenderSource"]
