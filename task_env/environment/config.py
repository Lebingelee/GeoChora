"""TaskEnv 的领域配置类型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite, pi
from typing import Any, Literal


@dataclass(frozen=True)
class AssetConfig:
    asset_version: str = "stage0"


@dataclass(frozen=True)
class SceneBuildConfig:
    scene_uid: str = "tabletop-v1"


@dataclass(frozen=True)
class AgentConfig:
    agent_uids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObjectConfig:
    object_uids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StaticTemplateContactConfig:
    """Immutable contact policy owned by one static-template task profile.

    The policy is resolved before runtime construction so it can participate in
    CUDA Graph identity.  It deliberately exposes only the supported fixed
    production path; historical solver experiments are not configuration
    surface area.
    """

    response_backend: Literal["auto", "active_slot_cholesky_f32_v1"] = "auto"
    fixed_topology_child_schur: bool = False
    root_factor_6x6: bool = False

    def __post_init__(self) -> None:
        if self.response_backend not in {"auto", "active_slot_cholesky_f32_v1"}:
            raise ValueError(
                "static_template.contact.response_backend must be auto or "
                "active_slot_cholesky_f32_v1"
            )
        if not isinstance(self.fixed_topology_child_schur, bool):
            raise ValueError(
                "static_template.contact.fixed_topology_child_schur must be a bool"
            )
        if not isinstance(self.root_factor_6x6, bool):
            raise ValueError("static_template.contact.root_factor_6x6 must be a bool")
        if self.root_factor_6x6 and not self.fixed_topology_child_schur:
            raise ValueError(
                "static_template.contact.root_factor_6x6 requires "
                "fixed_topology_child_schur=True"
            )


@dataclass(frozen=True)
class StaticTemplateRuntimeConfig:
    """Build-time static-template policy for a task-owned parallel runtime."""

    profile: Literal[
        "auto",
        "hinge_or_slide_no_contact_v1",
        "articulated_fused_no_contact_v1",
        "articulated_fused_ground_contact_v1",
        "articulated_ground_contact_v1",
        "rigid_batch_v1",
    ] = "auto"
    kinematics_backend: Literal["torch", "taichi"] = "torch"
    contact_precision: Literal["f64", "f32"] = "f64"
    cuda_graph: bool = False
    contact: StaticTemplateContactConfig = field(
        default_factory=StaticTemplateContactConfig
    )

    def __post_init__(self) -> None:
        if self.profile not in {
            "auto",
            "hinge_or_slide_no_contact_v1",
            "articulated_fused_no_contact_v1",
            "articulated_fused_ground_contact_v1",
            "articulated_ground_contact_v1",
            "rigid_batch_v1",
        }:
            raise ValueError(
                "static_template.profile must be one of: auto, "
                "hinge_or_slide_no_contact_v1, articulated_fused_no_contact_v1, "
                "articulated_fused_ground_contact_v1, articulated_ground_contact_v1, "
                "rigid_batch_v1"
            )
        if self.kinematics_backend not in {"torch", "taichi"}:
            raise ValueError(
                "static_template.kinematics_backend must be one of: torch, taichi"
            )
        if self.contact_precision not in {"f64", "f32"}:
            raise ValueError(
                "static_template.contact_precision must be one of: f64, f32"
            )
        if not isinstance(self.cuda_graph, bool):
            raise ValueError("static_template.cuda_graph must be a bool")
        contact = self.contact
        if isinstance(contact, Mapping):
            contact = StaticTemplateContactConfig(**dict(contact))
        if not isinstance(contact, StaticTemplateContactConfig):
            raise TypeError("static_template.contact must be a mapping or StaticTemplateContactConfig")
        object.__setattr__(self, "contact", contact)


@dataclass(frozen=True)
class RuntimeConfig:
    physics_dt: float = 0.002
    control_substeps: int = 1
    backend: str = "cpu"
    gravity: tuple[float, float, float] = (0.0, 0.0, -9.81)
    # Position actuators use a stiff PD law.  The implicit velocity update is
    # the stable default for TaskEnv's public position-target controllers.
    integrator: str = "implicitfast"
    broadphase: str = "n2"
    prewarm: bool = True
    # ``None`` 保持 GeoPhys 默认的 row-PGS 路径；调用方可为单次运行显式切换后端。
    rigid_solver_backend: str | None = None
    # ``None`` keeps the scene-derived row-PGS contact sweep budget.  A positive
    # override is useful for highly coupled multi-contact grasps.
    body_contact_solver_iterations: int | None = None
    # Contact participation is an explicit runtime capability.  ``None`` keeps
    # the layout's historical default (merged scenes stay contact-disabled;
    # articulated static templates use the authored ground when present).
    enable_ground_contact: bool | None = None
    enable_domain_boundary_contact: bool = False
    # Parallel physics layout is deliberately separate from local/remote
    # execution.  ``merged_scene`` remains the compatibility default.
    batch_physics_layout: Literal["merged_scene", "static_template"] = "merged_scene"
    # Static runtime policy is nested so one task YAML declares every value
    # participating in construction and CUDA Graph identity.
    static_template: StaticTemplateRuntimeConfig = field(
        default_factory=StaticTemplateRuntimeConfig
    )
    # Reset-boundary task randomization remains data-only at this layer; the
    # task and runtime independently validate the concrete capability.
    world_randomization: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.physics_dt <= 0.0:
            raise ValueError("physics_dt must be positive")
        if self.control_substeps < 1:
            raise ValueError("control_substeps must be at least 1")
        if self.backend not in {"cpu", "vulkan", "cuda"}:
            raise ValueError("backend must be one of: cpu, vulkan, cuda")
        if self.batch_physics_layout not in {"merged_scene", "static_template"}:
            raise ValueError(
                "batch_physics_layout must be one of: merged_scene, static_template"
            )
        static_template = self.static_template
        if isinstance(static_template, Mapping):
            static_template = StaticTemplateRuntimeConfig(**dict(static_template))
        if not isinstance(static_template, StaticTemplateRuntimeConfig):
            raise TypeError("runtime.static_template must be a mapping or StaticTemplateRuntimeConfig")
        object.__setattr__(self, "static_template", static_template)
        if len(self.gravity) != 3:
            raise ValueError("gravity must have three components")
        if self.rigid_solver_backend is not None:
            backend = str(self.rigid_solver_backend).strip().lower().replace("-", "_")
            if backend not in {"row_pgs", "soft_efc"}:
                raise ValueError(
                    "rigid_solver_backend must be one of: row_pgs, soft_efc"
                )
            object.__setattr__(self, "rigid_solver_backend", backend)
        if self.body_contact_solver_iterations is not None and (
            not isinstance(self.body_contact_solver_iterations, int)
            or isinstance(self.body_contact_solver_iterations, bool)
            or self.body_contact_solver_iterations < 1
        ):
            raise ValueError("body_contact_solver_iterations must be a positive integer")
        if self.enable_ground_contact is not None and not isinstance(
            self.enable_ground_contact, bool
        ):
            raise ValueError("enable_ground_contact must be a bool or None")
        if not isinstance(self.enable_domain_boundary_contact, bool):
            raise ValueError("enable_domain_boundary_contact must be a bool")
        if not isinstance(self.world_randomization, Mapping):
            raise ValueError("world_randomization must be a mapping")
        object.__setattr__(self, "world_randomization", dict(self.world_randomization))

@dataclass(frozen=True)
class ActionConfig:
    """Shared DLS-IK, servo and gripper tuning for the three controllers."""

    # Learner-boundary semantic profile.  Non-RSL environments leave it inert.
    rsl_action_profile: str | None = None
    ik_damping: float = 0.02
    ik_position_gain: float = 0.9
    ik_rotation_gain: float = 0.65
    ik_rotation_row_weight: float = 0.22
    ik_max_delta_q: float = 0.10
    ik_position_deadband: float = 0.006
    ik_rotation_deadband: float = 0.035
    cartesian_max_position_step: float = 0.025
    cartesian_max_rotation_step: float = 0.20
    cartesian_error_growth_margin: float = 0.004
    cartesian_velocity_brake_gain: float = 0.025
    cartesian_max_brake_step: float = 0.06
    cartesian_velocity_deadband: float = 0.03
    joint_position_correction_gain: float = 2.5
    gripper_close_ctrl: float = 0.0
    gripper_open_ctrl: float = 255.0
    gripper_opening_range_m: float = 0.08
    gripper_default_force_N: float = 5.0
    # Panda reports physical opening as the sum of two finger qpos values;
    # actuator tendon length is half that opening, hence 5000 / 2.
    gripper_position_stiffness_N_per_m: float = 2500.0

    def __post_init__(self) -> None:
        for name in (
            "ik_damping",
            "ik_position_gain",
            "ik_rotation_gain",
            "ik_rotation_row_weight",
            "ik_max_delta_q",
            "ik_position_deadband",
            "ik_rotation_deadband",
            "cartesian_max_position_step",
            "cartesian_max_rotation_step",
            "cartesian_error_growth_margin",
            "cartesian_velocity_brake_gain",
            "cartesian_max_brake_step",
            "cartesian_velocity_deadband",
            "joint_position_correction_gain",
            "gripper_opening_range_m",
            "gripper_default_force_N",
            "gripper_position_stiffness_N_per_m",
        ):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class RobotControllerConfig:
    """Public controller selection shared by all robot TaskEnv instances.

    ``reference`` is deliberately an enum-like semantic value, not an MJCF
    name.  The robot resolves ``base`` and ``ee`` to its declared references
    after scene compilation.
    """

    kind: Literal["absolute_joint", "absolute_pose", "delta_pose"]
    reference: Literal["world", "base", "ee"] | None = None
    rotation_representation: Literal["quaternion_wxyz", "rotvec"] = (
        "quaternion_wxyz"
    )
    delta_translation_unit: Literal["meters"] = "meters"
    max_translation_delta_m: float = 0.03
    max_rotation_delta_rad: float = 0.20
    max_absolute_rotvec_angle_rad: float = pi

    def __post_init__(self) -> None:
        allowed_references = {
            "absolute_joint": {None},
            "absolute_pose": {"world", "base"},
            "delta_pose": {"world", "base", "ee"},
        }
        if self.reference not in allowed_references[self.kind]:
            allowed = ", ".join(
                "none" if value is None else value
                for value in sorted(
                    allowed_references[self.kind], key=lambda value: value is not None
                )
            )
            raise ValueError(
                f"{self.kind} reference must be one of: {allowed}"
            )
        if self.max_translation_delta_m <= 0.0:
            raise ValueError("max_translation_delta_m must be positive")
        if self.max_rotation_delta_rad <= 0.0:
            raise ValueError("max_rotation_delta_rad must be positive")
        if not 0.0 < self.max_absolute_rotvec_angle_rad <= pi:
            raise ValueError("max_absolute_rotvec_angle_rad must be in (0, pi]")


@dataclass(frozen=True)
class GripperConfig:
    """Public Panda gripper configuration, independent of arm controller choice.

    ``force_limit_N`` is the sole source for both the physical actuator cap and
    the experimental controller's hold-force setpoint.  The remaining tuning
    values apply when ``kind`` is ``experimental_rate_limited``.
    """

    kind: Literal["legacy", "experimental_rate_limited"] = "experimental_rate_limited"
    force_limit_N: float = 30.0
    opening_step_m: float = 0.002
    force_deadband_N: float = 1.0
    force_adjust_step_m: float = 1.0e-4

    def __post_init__(self) -> None:
        if self.kind not in {
            "legacy",
            "experimental_rate_limited",
        }:
            raise ValueError(
                "gripper.kind must be legacy or experimental_rate_limited"
            )
        if not isfinite(self.force_limit_N) or self.force_limit_N <= 0.0:
            raise ValueError("gripper.force_limit_N must be finite and positive")
        if (
            not isfinite(self.opening_step_m)
            or self.opening_step_m <= 0.0
        ):
            raise ValueError(
                "gripper.opening_step_m must be finite and positive"
            )
        if (
            not isfinite(self.force_deadband_N)
            or self.force_deadband_N < 0.0
        ):
            raise ValueError("gripper.force_deadband_N must be finite and non-negative")
        if (
            not isfinite(self.force_adjust_step_m)
            or self.force_adjust_step_m <= 0.0
        ):
            raise ValueError(
                "gripper.force_adjust_step_m must be finite and positive"
            )


@dataclass(frozen=True)
class RobotConfig:
    """Robot-scoped public configuration; optional for non-robot environments."""

    controller: RobotControllerConfig | None = None
    gripper: GripperConfig = field(default_factory=GripperConfig)


@dataclass(frozen=True)
class ObservationConfig:
    schema_version: str = "task-env-state-v1"
    include_privileged_state: bool = True

    def __post_init__(self) -> None:
        if not self.schema_version.strip():
            raise ValueError("schema_version cannot be empty")


@dataclass(frozen=True)
class CameraSpec:
    name: str
    width: int = 128
    height: int = 128
    rgb: bool = True
    depth: bool = False
    # This is an observation contract, not a recorder preference.  Consumers
    # can therefore interpret every RGB leaf before a first reset.
    rgb_layout: Literal["HWC", "CHW"] = "HWC"
    rgb_dtype: Literal["float32", "uint8"] = "float32"
    frame: Literal["world", "body", "site"] = "world"
    parent: str | None = None
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    quaternion_wxyz: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    fov_y: float = 1.5707963267948966
    near: float = 0.01
    far: float = 100.0

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise ValueError("camera name cannot be empty")
        if self.width < 1 or self.height < 1:
            raise ValueError("camera width/height must be positive")
        if self.frame not in {"world", "body", "site"}:
            raise ValueError("camera frame must be one of: world, body, site")
        parent = None if self.parent is None else str(self.parent).strip()
        if self.frame != "world" and not parent:
            raise ValueError("body/site camera must declare a parent")
        if self.frame == "world" and parent:
            raise ValueError("world camera cannot declare a parent")
        if not (self.rgb or self.depth):
            raise ValueError("camera must enable at least one modality")
        if self.rgb_layout not in {"HWC", "CHW"}:
            raise ValueError("camera rgb_layout must be HWC or CHW")
        if self.rgb_dtype not in {"float32", "uint8"}:
            raise ValueError("camera rgb_dtype must be float32 or uint8")
        if self.fov_y <= 0.0:
            raise ValueError("camera fov_y must be positive")
        if self.near <= 0.0 or self.far <= self.near:
            raise ValueError("camera near/far planes are invalid")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "parent", parent)
        object.__setattr__(
            self,
            "position",
            tuple(float(value) for value in self.position),
        )
        object.__setattr__(
            self,
            "quaternion_wxyz",
            tuple(float(value) for value in self.quaternion_wxyz),
        )
        if len(self.position) != 3:
            raise ValueError("camera position must have three components")
        if len(self.quaternion_wxyz) != 4:
            raise ValueError("camera quaternion_wxyz must have four components")


@dataclass(frozen=True)
class ParallelRenderConfig:
    """Renderer-provider settings applied to a raw parallel environment."""

    num: int | None = 256
    columns: int = 16
    cell_width: float = 1.0
    cell_depth: float = 1.0
    padding: float = 0.0

    def __post_init__(self) -> None:
        if self.num is not None and (
            isinstance(self.num, bool) or int(self.num) < 1
        ):
            raise ValueError("render.parallel.num must be positive or None")
        if isinstance(self.columns, bool) or int(self.columns) < 1:
            raise ValueError("render.parallel.columns must be a positive integer")
        if float(self.cell_width) <= 0.0:
            raise ValueError("render.parallel.cell_width must be positive")
        if float(self.cell_depth) <= 0.0:
            raise ValueError("render.parallel.cell_depth must be positive")
        if float(self.padding) < 0.0:
            raise ValueError("render.parallel.padding must be non-negative")
        if self.num is not None:
            object.__setattr__(self, "num", int(self.num))
        object.__setattr__(self, "columns", int(self.columns))
        object.__setattr__(self, "cell_width", float(self.cell_width))
        object.__setattr__(self, "cell_depth", float(self.cell_depth))
        object.__setattr__(self, "padding", float(self.padding))


@dataclass(frozen=True)
class TrainingRenderConfig:
    """PPO-wrapper settings; these are not raw environment parameters."""

    every: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.every, bool) or int(self.every) < 1:
            raise ValueError("render.training.every must be a positive integer")
        object.__setattr__(self, "every", int(self.every))


@dataclass(frozen=True)
class RenderConfig:
    camera_obs: bool = False
    backend: str = "raytracer"
    cameras: tuple[CameraSpec, ...] = ()
    width: int = 640
    height: int = 480
    render_preset: str = "interactive"
    parallel: ParallelRenderConfig = field(default_factory=ParallelRenderConfig)
    training: TrainingRenderConfig = field(default_factory=TrainingRenderConfig)

    def __post_init__(self) -> None:
        if self.backend not in {
            "raytracer",
            "rasterizer",
            "flora",
            "mujoco_reference",
        }:
            raise ValueError(
                "render backend must be raytracer, rasterizer, flora, or "
                "mujoco_reference"
            )
        if int(self.width) < 1 or int(self.height) < 1:
            raise ValueError("render width and height must be positive")
        if not str(self.render_preset).strip():
            raise ValueError("render_preset cannot be empty")
        parallel = (
            self.parallel
            if isinstance(self.parallel, ParallelRenderConfig)
            else ParallelRenderConfig(**dict(self.parallel))
        )
        training = (
            self.training
            if isinstance(self.training, TrainingRenderConfig)
            else TrainingRenderConfig(**dict(self.training))
        )
        cameras = tuple(
            camera if isinstance(camera, CameraSpec) else CameraSpec(**dict(camera))
            for camera in self.cameras
        )
        names = tuple(camera.name for camera in cameras)
        if len(names) != len(set(names)):
            raise ValueError("camera names cannot contain duplicates")
        if self.camera_obs and not cameras:
            raise ValueError("camera_obs requires at least one camera")
        if cameras and not self.camera_obs:
            raise ValueError("camera_obs must be true when cameras are configured")
        object.__setattr__(self, "width", int(self.width))
        object.__setattr__(self, "height", int(self.height))
        object.__setattr__(self, "render_preset", str(self.render_preset).strip())
        object.__setattr__(self, "parallel", parallel)
        object.__setattr__(self, "training", training)
        object.__setattr__(self, "cameras", cameras)

    @property
    def camera_names(self) -> tuple[str, ...]:
        return tuple(camera.name for camera in self.cameras)


@dataclass(frozen=True)
class TaskConfig:
    task_uid: str = "empty-v1"
    success_definition: str = "none"


@dataclass(frozen=True)
class EpisodeConfig:
    horizon: int = 1000
    seed: int | None = None
    ignore_done: bool = False

    def __post_init__(self) -> None:
        if self.horizon < 1:
            raise ValueError("horizon must be at least 1")


@dataclass(frozen=True)
class ResolvedEnvConfig:
    asset: AssetConfig = field(default_factory=AssetConfig)
    scene: SceneBuildConfig = field(default_factory=SceneBuildConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)
    objects: ObjectConfig = field(default_factory=ObjectConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    robot: RobotConfig = field(default_factory=RobotConfig)
    action: ActionConfig = field(default_factory=ActionConfig)
    observation: ObservationConfig = field(default_factory=ObservationConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    episode: EpisodeConfig = field(default_factory=EpisodeConfig)
