"""Versioned effective control plans for the bounded Arm/Hand leaf owners.

This is an advanced, provider-free contract owner.  It reruns the current
Logical Assembly resolver and source declaration projection from caller-owned
inputs; it never treats a hand-built resolved object as admission evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re

from ...artifacts import SceneDefinition, resolve_logical_assembly
from ...assembly import project_logical_assembly_source
from ...environment import ActionConfig
from .leaf_profiles import (
    ARM_POSITION_ACTION_SCHEMA,
    ARM_POSITION_PROFILE_ID,
    HAND_POSITION_ACTION_SCHEMA,
    HAND_POSITION_PROFILE_ID,
    LeafProfileBindingV1,
    validate_leaf_bindings,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
_ARM_PARAMETERS = ("joint_position_correction_gain",)
_HAND_PARAMETERS = (
    "gripper_close_ctrl", "gripper_default_force_N", "gripper_open_ctrl",
    "gripper_opening_range_m", "gripper_position_stiffness_N_per_m",
)


def _digest(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _path(value):
    if type(value) not in (tuple, list) or not value:
        raise ValueError("leaf path must be a nonempty segment sequence")
    result = tuple(value)
    if any(type(item) is not str or not _SEGMENT.fullmatch(item)
           or item in {".", ".."} for item in result):
        raise ValueError("leaf path contains an invalid or ambiguous segment")
    return result


def _sha(value, label):
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")


def _token(value, label):
    if type(value) is not str or not _TOKEN.fullmatch(value):
        raise ValueError(f"{label} must be a stable nonempty token")


@dataclass(frozen=True)
class LeafProfileSectionV1:
    """A complete leaf profile section; no writer or native index is stored."""

    schema_version: str
    member_path: tuple[str, ...]
    profile_kind: str
    profile_id: str
    action_schema_id: str
    algorithm_id: str
    configuration: tuple[tuple[str, float], ...]

    def __post_init__(self):
        if type(self.schema_version) is not str or self.schema_version != "leaf-profile-section-v1":
            raise ValueError("unsupported leaf profile section schema")
        object.__setattr__(self, "member_path", _path(self.member_path))
        for value, label in ((self.profile_kind, "profile kind"),
                             (self.profile_id, "profile ID"),
                             (self.action_schema_id, "action schema ID"),
                             (self.algorithm_id, "algorithm ID")):
            _token(value, label)
        expected = {
            "arm_position": (ARM_POSITION_PROFILE_ID, ARM_POSITION_ACTION_SCHEMA, _ARM_PARAMETERS),
            "hand_position": (HAND_POSITION_PROFILE_ID, HAND_POSITION_ACTION_SCHEMA, _HAND_PARAMETERS),
        }.get(self.profile_kind)
        if expected is None:
            raise ValueError("Force-aware or unknown leaf profiles are not executable")
        if (self.profile_id, self.action_schema_id) != expected[:2]:
            raise ValueError("profile section identity does not match its profile kind")
        if self.algorithm_id != "canonical-joint-position-v1":
            raise ValueError("unregistered leaf algorithm is not supported")
        if type(self.configuration) is not tuple:
            raise TypeError("leaf configuration must be an immutable tuple")
        values = tuple(self.configuration)
        if any(type(item) is not tuple or len(item) != 2 for item in values):
            raise TypeError("leaf configuration values must be key/value pairs")
        keys = tuple(item[0] for item in values)
        if keys != tuple(sorted(set(keys))) or keys != expected[2]:
            raise ValueError("configuration must exactly replace the complete profile section")
        for name, value in values:
            if type(name) is not str or type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("configuration values must be finite real numbers")
            if name.endswith("force_N") or name.endswith("stiffness_N_per_m") or name.endswith("gain"):
                if value <= 0:
                    raise ValueError(f"{name} must be positive")
        if self.profile_kind == "hand_position":
            config = dict(values)
            if config["gripper_opening_range_m"] != 0.08:
                raise ValueError("Hand Position keeps the R02a 0.08 m opening range")
            if (config["gripper_close_ctrl"], config["gripper_open_ctrl"]) != (0.0, 255.0):
                raise ValueError("Hand Position keeps the source 0..255 ctrl endpoints")

    @property
    def configuration_identity_sha256(self) -> str:
        return _digest({
            "schema_version": self.schema_version,
            "profile_kind": self.profile_kind,
            "profile_id": self.profile_id,
            "action_schema_id": self.action_schema_id,
            "algorithm_id": self.algorithm_id,
            "configuration": self.configuration,
        })

    @property
    def identity_sha256(self) -> str:
        return _digest({
            "schema_version": self.schema_version,
            "member_path": self.member_path,
            "profile_kind": self.profile_kind,
            "profile_id": self.profile_id,
            "action_schema_id": self.action_schema_id,
            "algorithm_id": self.algorithm_id,
            "configuration": self.configuration,
        })

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "member_path": list(self.member_path),
            "profile_kind": self.profile_kind,
            "profile_id": self.profile_id,
            "action_schema_id": self.action_schema_id,
            "algorithm_id": self.algorithm_id,
            "configuration": [list(item) for item in self.configuration],
        }

    def values(self) -> dict[str, float]:
        return dict(self.configuration)


@dataclass(frozen=True)
class LeafControlPresetV1:
    """Immutable parent template with complete path-selected leaf sections."""

    schema_version: str
    preset_id: str
    revision: str
    sections: tuple[LeafProfileSectionV1, ...]

    def __post_init__(self):
        if type(self.schema_version) is not str or self.schema_version != "leaf-control-preset-v1":
            raise ValueError("unsupported leaf control preset schema")
        _token(self.preset_id, "preset ID")
        _token(self.revision, "preset revision")
        if type(self.sections) is not tuple or not self.sections:
            raise TypeError("preset sections must be a nonempty immutable tuple")
        if any(type(section) is not LeafProfileSectionV1 for section in self.sections):
            raise TypeError("preset sections require exact versioned leaf sections")
        paths = tuple(section.member_path for section in self.sections)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("preset sections must be unique and canonically path-sorted")

    @property
    def identity_sha256(self) -> str:
        return _digest({
            "schema_version": self.schema_version,
            "preset_id": self.preset_id,
            "revision": self.revision,
            "sections": [
                {"member_path": section.member_path,
                 "section": section.identity_sha256}
                for section in self.sections
            ],
        })

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "preset_id": self.preset_id,
            "revision": self.revision,
            "sections": [section.to_mapping() for section in self.sections],
        }


@dataclass(frozen=True)
class LeafProfileOverrideV1:
    """One full section replacement for one existing preset path."""

    schema_version: str
    member_path: tuple[str, ...]
    replacement: LeafProfileSectionV1

    def __post_init__(self):
        if type(self.schema_version) is not str or self.schema_version != "leaf-profile-override-v1":
            raise ValueError("unsupported leaf override schema")
        object.__setattr__(self, "member_path", _path(self.member_path))
        if type(self.replacement) is not LeafProfileSectionV1:
            raise TypeError("override requires one complete versioned leaf section")
        if self.member_path != self.replacement.member_path:
            raise ValueError("override path and replacement path disagree")

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "member_path": list(self.member_path),
            "replacement": self.replacement.to_mapping(),
        }


@dataclass(frozen=True)
class EffectiveLeafEntryV1:
    schema_version: str
    binding: LeafProfileBindingV1
    section: LeafProfileSectionV1
    base_configuration_identity_sha256: str
    effective_configuration_identity_sha256: str

    def __post_init__(self):
        if self.schema_version != "effective-leaf-entry-v1":
            raise ValueError("unsupported effective leaf entry schema")
        if type(self.binding) is not LeafProfileBindingV1 or type(self.section) is not LeafProfileSectionV1:
            raise TypeError("effective leaf entry requires an existing R02a binding and typed section")
        _sha(self.base_configuration_identity_sha256, "base configuration identity")
        _sha(self.effective_configuration_identity_sha256, "effective configuration identity")
        if self.effective_configuration_identity_sha256 != self.section.configuration_identity_sha256:
            raise ValueError("effective configuration digest does not identify the consumed section")


@dataclass(frozen=True)
class EffectiveLeafPlanV1:
    schema_version: str
    scene_identity_sha256: str
    root_assembly_id: str
    root_revision: str
    root_logical_content_sha256: str
    source_closure_sha256: str
    provider_name: str
    provider_version: str
    provider_build_sha256: str
    backend: str
    physics_dt_s: float
    control_substeps: int
    base_preset_id: str
    base_preset_revision: str
    base_preset_identity_sha256: str
    overrides: tuple[LeafProfileOverrideV1, ...]
    leaves: tuple[EffectiveLeafEntryV1, ...]
    resource_writers: tuple[tuple[str, str, str], ...]
    fixed_attachment_plan_identity_sha256: str | None = None
    _compiled: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.schema_version != "effective-leaf-plan-v1":
            raise ValueError("unsupported effective leaf plan schema")
        for field, label in ((self.scene_identity_sha256, "Scene"),
                             (self.root_logical_content_sha256, "root Assembly"),
                             (self.source_closure_sha256, "source closure"),
                             (self.provider_build_sha256, "Provider build"),
                             (self.base_preset_identity_sha256, "base preset")):
            _sha(field, label)
        if self.fixed_attachment_plan_identity_sha256 is not None:
            _sha(self.fixed_attachment_plan_identity_sha256, "fixed Attachment plan")
        if (type(self.overrides) is not tuple or type(self.leaves) is not tuple
                or type(self.resource_writers) is not tuple):
            raise TypeError("effective plan collections must be immutable tuples")
        if (any(type(item) is not LeafProfileOverrideV1 for item in self.overrides)
                or any(type(item) is not EffectiveLeafEntryV1 for item in self.leaves)):
            raise TypeError("effective plan requires exact typed override and leaf entries")
        for value, label in ((self.root_assembly_id, "root Assembly ID"),
                             (self.root_revision, "root Assembly revision"),
                             (self.provider_name, "Provider name"),
                             (self.provider_version, "Provider version"),
                             (self.backend, "backend"),
                             (self.base_preset_id, "base preset ID"),
                             (self.base_preset_revision, "base preset revision")):
            _token(value, label)
        if (type(self.physics_dt_s) not in (int, float)
                or isinstance(self.physics_dt_s, bool)
                or not math.isfinite(self.physics_dt_s) or self.physics_dt_s <= 0):
            raise ValueError("effective plan physics timestep must be finite and positive")
        if type(self.control_substeps) is not int or self.control_substeps <= 0:
            raise ValueError("effective plan control substeps must be a positive integer")
        paths = tuple(entry.section.member_path for entry in self.leaves)
        if paths != tuple(sorted(set(paths))) or not paths:
            raise ValueError("effective leaves must be nonempty, unique and path-sorted")
        override_paths = tuple(item.member_path for item in self.overrides)
        if override_paths != tuple(sorted(set(override_paths))):
            raise ValueError("effective plan overrides must be unique and canonically sorted")
        resources = self.resource_writers
        if any(type(item) is not tuple or len(item) != 3
               or any(type(value) is not str for value in item) for item in resources):
            raise TypeError("resource writer mappings must be immutable string triples")
        if resources != tuple(sorted(set(resources))):
            raise ValueError("resource writer mapping must be unique and sorted")

    @property
    def identity_sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "scene_identity_sha256": self.scene_identity_sha256,
            "root_assembly_id": self.root_assembly_id,
            "root_revision": self.root_revision,
            "root_logical_content_sha256": self.root_logical_content_sha256,
            "source_closure_sha256": self.source_closure_sha256,
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "provider_build_sha256": self.provider_build_sha256,
            "backend": self.backend,
            "physics_dt_s": self.physics_dt_s,
            "control_substeps": self.control_substeps,
            "base_preset_id": self.base_preset_id,
            "base_preset_revision": self.base_preset_revision,
            "base_preset_identity_sha256": self.base_preset_identity_sha256,
            "leaves": [
                {"binding_identity_sha256": entry.binding.identity_hash,
                 "section_identity_sha256": entry.section.identity_sha256,
                 "effective_configuration_identity_sha256": entry.effective_configuration_identity_sha256}
                for entry in self.leaves
            ],
            "resource_writers": self.resource_writers,
        }
        if self.fixed_attachment_plan_identity_sha256 is not None:
            payload["fixed_attachment_plan_identity_sha256"] = self.fixed_attachment_plan_identity_sha256
        return _digest(payload)

    @property
    def profile_status(self) -> str:
        changed = sum(
            entry.effective_configuration_identity_sha256
            != entry.base_configuration_identity_sha256
            for entry in self.leaves
        )
        if changed == 0:
            return "preset"
        if changed == len(self.leaves):
            return "custom"
        return "partially_overridden"

    def to_mapping(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "scene_identity_sha256": self.scene_identity_sha256,
            "root_assembly_id": self.root_assembly_id,
            "root_revision": self.root_revision,
            "root_logical_content_sha256": self.root_logical_content_sha256,
            "source_closure_sha256": self.source_closure_sha256,
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "provider_build_sha256": self.provider_build_sha256,
            "backend": self.backend,
            "physics_dt_s": self.physics_dt_s,
            "control_substeps": self.control_substeps,
            "base_preset_id": self.base_preset_id,
            "base_preset_revision": self.base_preset_revision,
            "base_preset_identity_sha256": self.base_preset_identity_sha256,
            "overrides": [
                {"schema_version": item.schema_version,
                 "member_path": list(item.member_path),
                 "replacement": item.replacement.to_mapping()}
                for item in self.overrides
            ],
            "leaves": [
                {"schema_version": entry.schema_version,
                 "binding": entry.binding.to_mapping(),
                 "section": entry.section.to_mapping(),
                 "base_configuration_identity_sha256": entry.base_configuration_identity_sha256,
                 "effective_configuration_identity_sha256": entry.effective_configuration_identity_sha256}
                for entry in self.leaves
            ],
            "resource_writers": [list(item) for item in self.resource_writers],
        }
        if self.fixed_attachment_plan_identity_sha256 is not None:
            payload["fixed_attachment_plan_identity_sha256"] = self.fixed_attachment_plan_identity_sha256
        return payload


def default_leaf_profile_section(binding: LeafProfileBindingV1) -> LeafProfileSectionV1:
    """Build the exact bounded force-free defaults from the existing config owner."""
    cfg = ActionConfig()
    if binding.profile_kind == "arm_position":
        values = (("joint_position_correction_gain", cfg.joint_position_correction_gain),)
    elif binding.profile_kind == "hand_position":
        values = tuple(sorted((
            ("gripper_close_ctrl", cfg.gripper_close_ctrl),
            ("gripper_default_force_N", cfg.gripper_default_force_N),
            ("gripper_open_ctrl", cfg.gripper_open_ctrl),
            ("gripper_opening_range_m", cfg.gripper_opening_range_m),
            ("gripper_position_stiffness_N_per_m", cfg.gripper_position_stiffness_N_per_m),
        )))
    else:
        raise ValueError("Force-aware profile remains NOT_ADMITTED")
    return LeafProfileSectionV1(
        "leaf-profile-section-v1", binding.member_path, binding.profile_kind,
        binding.profile_id, binding.action_schema_id, binding.algorithm_id, values,
    )


def compile_effective_leaf_plan(
    scene: SceneDefinition,
    root_assembly,
    child_assemblies,
    bindings: tuple[LeafProfileBindingV1, ...],
    preset: LeafControlPresetV1,
    overrides: tuple[LeafProfileOverrideV1, ...] = (),
    *,
    source_closure_sha256: str,
    fixed_attachment_plan_identity_sha256: str | None = None,
) -> EffectiveLeafPlanV1:
    """Re-resolve current authoring inputs and compile one complete leaf plan."""
    if type(scene) is not SceneDefinition or scene.schema_version != "scene-definition-v3":
        raise ValueError("effective leaf plans require the exact current Scene v3")
    if type(preset) is not LeafControlPresetV1:
        raise TypeError("effective leaf plan requires one versioned parent preset")
    if type(overrides) is not tuple or any(type(item) is not LeafProfileOverrideV1 for item in overrides):
        raise TypeError("leaf overrides must be an immutable tuple of complete replacements")
    _sha(source_closure_sha256, "source closure")
    if fixed_attachment_plan_identity_sha256 is not None:
        _sha(fixed_attachment_plan_identity_sha256, "fixed Attachment plan")

    # Never accept caller-created Resolved/Projection objects as proof.  Both
    # existing owners re-check the supplied root, child closure and Scene.
    resolved = resolve_logical_assembly(root_assembly, scene, child_assemblies)
    projected = project_logical_assembly_source(root_assembly, scene, child_assemblies)
    if (projected.root_assembly_id, projected.root_revision,
            projected.root_logical_content_sha256, projected.scene_identity_sha256) != (
            resolved.root_assembly_id, resolved.root_revision,
            resolved.root_logical_content_sha256, resolved.scene_identity_sha256):
        raise ValueError("current Assembly resolution and source projection disagree")
    validate_leaf_bindings(scene, bindings, resolved)
    if any(binding.provenance_kind != "declared" for binding in bindings):
        # Synthetic bindings are only accepted by explicitly synthetic S1 plans.
        if any(binding.provenance_kind != "synthetic_fixture" for binding in bindings):
            raise ValueError("leaf bindings cannot mix declared and synthetic provenance")

    binding_paths = {binding.member_path for binding in bindings}
    if len(binding_paths) != len(bindings):
        raise ValueError("one Assembly path cannot own multiple leaf writers")
    preset_by_path = {section.member_path: section for section in preset.sections}
    if set(preset_by_path) != binding_paths:
        raise ValueError("parent preset sections must exactly cover the selected leaf bindings")
    override_by_path = {}
    for override in overrides:
        if override.member_path in override_by_path:
            raise ValueError("duplicate local override path")
        if override.member_path not in binding_paths:
            raise ValueError("local override names an unknown or ambiguous leaf path")
        override_by_path[override.member_path] = override

    control_groups = {
        (group.entity_id, group.group_id): group for group in (scene.control_groups or ())
    }
    expected_groups = {(binding.entity_id, binding.control_group_id) for binding in bindings}
    if len(expected_groups) != len(bindings) or set(control_groups) != expected_groups:
        raise ValueError("leaf writers must uniquely cover every declared Scene ControlGroup")
    all_resources = {
        (resource.entity_id, resource.actuator_id)
        for resource in (scene.actuator_resources or ())
    }
    resource_writers = []
    for binding in bindings:
        group = control_groups[(binding.entity_id, binding.control_group_id)]
        group_resources = {(ref.entity_id, ref.actuator_id) for ref in group.actuator_refs}
        bound_resources = {(ref.entity_id, ref.actuator_id) for ref in binding.actuator_order}
        if group_resources != bound_resources:
            raise ValueError("leaf binding must completely cover its ControlGroup resources")
        resource_writers.extend((entity, actuator, binding.writer_id)
                                for entity, actuator in bound_resources)
    if {(entity, actuator) for entity, actuator, _ in resource_writers} != all_resources:
        raise ValueError("leaf plan must exactly cover all Scene ActuatorResources")
    if len({(entity, actuator) for entity, actuator, _ in resource_writers}) != len(resource_writers):
        raise ValueError("Scene actuator resource has more than one leaf writer")

    entries = []
    for binding in bindings:
        path = binding.member_path
        base_section = preset_by_path[path]
        if (base_section.profile_kind, base_section.profile_id,
                base_section.action_schema_id, base_section.algorithm_id) != (
                binding.profile_kind, binding.profile_id,
                binding.action_schema_id, binding.algorithm_id):
            raise ValueError("preset profile/action/algorithm differs from its R02a binding")
        if base_section.configuration_identity_sha256 != binding.configuration_identity_sha256:
            raise ValueError("base preset configuration identity differs from the R02a binding")
        section = override_by_path[path].replacement if path in override_by_path else base_section
        if (section.profile_kind, section.profile_id, section.action_schema_id,
                section.algorithm_id, section.member_path) != (
                binding.profile_kind, binding.profile_id, binding.action_schema_id,
                binding.algorithm_id, binding.member_path):
            raise ValueError("override cannot switch profile, algorithm, action or leaf path")
        if section.profile_kind == "hand_position":
            values = section.values()
            expected_scale = binding.actuator_command_scale_ctrl_per_opening_m
            if expected_scale is None or not math.isclose(
                (values["gripper_open_ctrl"] - values["gripper_close_ctrl"])
                / values["gripper_opening_range_m"], expected_scale, rel_tol=0.0, abs_tol=1.0e-12,
            ):
                raise ValueError("Hand affine command config differs from the source-bound mapping")
        entries.append(EffectiveLeafEntryV1(
            "effective-leaf-entry-v1", binding, section,
            base_section.configuration_identity_sha256,
            section.configuration_identity_sha256,
        ))

    providers = {(b.provider_name, b.provider_version, b.provider_build_sha256,
                  b.backend, b.physics_dt_s, b.control_substeps) for b in bindings}
    if len(providers) != 1:
        raise ValueError("all leaves in one Scene plan must share Provider/build/backend/timebase")
    provider_name, provider_version, provider_build, backend, physics_dt, substeps = next(iter(providers))
    if (physics_dt, substeps) != (0.002, 5):
        raise ValueError("R02b Position leaf plan requires the existing 2 ms / five substep timebase")
    if any(binding.source_closure_sha256 != source_closure_sha256 for binding in bindings):
        raise ValueError("current source closure differs from a leaf binding")

    result = EffectiveLeafPlanV1(
        "effective-leaf-plan-v1", scene.identity_hash, resolved.root_assembly_id,
        resolved.root_revision, resolved.root_logical_content_sha256,
        source_closure_sha256, provider_name, provider_version, provider_build,
        backend, physics_dt, substeps, preset.preset_id, preset.revision,
        preset.identity_sha256,
        tuple(sorted(overrides, key=lambda item: item.member_path)),
        tuple(sorted(entries, key=lambda item: item.section.member_path)),
        tuple(sorted(resource_writers)),
        fixed_attachment_plan_identity_sha256,
    )
    object.__setattr__(result, "_compiled", True)
    return result


def decode_leaf_profile_section(values) -> LeafProfileSectionV1:
    expected = {
        "schema_version", "member_path", "profile_kind", "profile_id",
        "action_schema_id", "algorithm_id", "configuration",
    }
    if type(values) is not dict or set(values) != expected:
        raise ValueError("leaf profile section mapping must use the exact versioned fields")
    member_path = values["member_path"]
    if type(member_path) not in (list, tuple):
        raise TypeError("leaf profile member_path must be an ordered segment sequence")
    configuration = values["configuration"]
    if type(configuration) not in (list, tuple):
        raise TypeError("leaf profile configuration must be a finite pair sequence")
    if any(type(item) not in (list, tuple) or len(item) != 2 for item in configuration):
        raise ValueError("leaf profile configuration entries must be exact key/value pairs")
    return LeafProfileSectionV1(
        values["schema_version"], tuple(member_path),
        values["profile_kind"], values["profile_id"], values["action_schema_id"],
        values["algorithm_id"], tuple(tuple(item) for item in configuration),
    )


def decode_leaf_control_preset(values) -> LeafControlPresetV1:
    expected = {"schema_version", "preset_id", "revision", "sections"}
    if type(values) is not dict or set(values) != expected:
        raise ValueError("leaf preset mapping must use the exact versioned fields")
    if type(values["sections"]) not in (list, tuple):
        raise TypeError("leaf preset sections must be an ordered sequence")
    if not values["sections"]:
        raise ValueError("leaf preset sections must be nonempty")
    sections = tuple(
        value if type(value) is LeafProfileSectionV1 else decode_leaf_profile_section(value)
        for value in values["sections"]
    )
    return LeafControlPresetV1(
        values["schema_version"], values["preset_id"], values["revision"], sections,
    )


def decode_leaf_profile_override(values) -> LeafProfileOverrideV1:
    expected = {"schema_version", "member_path", "replacement"}
    if type(values) is not dict or set(values) != expected:
        raise ValueError("leaf override mapping must use the exact versioned fields")
    replacement = values["replacement"]
    if type(replacement) is not LeafProfileSectionV1:
        replacement = decode_leaf_profile_section(replacement)
    member_path = values["member_path"]
    if type(member_path) not in (list, tuple):
        raise TypeError("leaf override member_path must be an ordered segment sequence")
    return LeafProfileOverrideV1(
        values["schema_version"], tuple(member_path), replacement,
    )


__all__ = [
    "LeafProfileSectionV1", "LeafControlPresetV1", "LeafProfileOverrideV1",
    "EffectiveLeafEntryV1", "EffectiveLeafPlanV1", "default_leaf_profile_section",
    "compile_effective_leaf_plan", "decode_leaf_profile_section",
    "decode_leaf_control_preset", "decode_leaf_profile_override",
]
