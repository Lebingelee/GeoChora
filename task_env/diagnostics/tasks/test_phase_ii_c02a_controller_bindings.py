"""C02a: bind A03 ControlGroups to existing Controller contracts, without dispatch."""

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from task_env.artifacts import (
    StateFieldRequirement,
    StateRequirements,
    SceneDefinition,
)
from task_env.controllers.canonical.contracts import (
    ControlGroupActionV1,
    RequestedAction,
    StructuredActionRequestV1,
)
from task_env.controllers.canonical.feedback import (
    CanonicalControlFeedback,
    CanonicalGripperFeedback,
)
from task_env.environment.types import ActionModeSpec
from task_env.runtime.sessions.control import (
    ControlBindingPlanV1,
    ControlGroupActionProjectionV1,
    ControllerBindingV1,
    compile_control_binding_plan,
    prepare_structured_action,
)


FIXTURE = Path(__file__).with_name("fixtures") / "phase_ii_d01a" / "a05_scene_definition_v3.json"
ARM_COMPONENTS = ("x", "y", "z", "qw", "qx", "qy", "qz")
GRIPPER_COMPONENTS = ("gripper",)
WRITER = "panda-main/production-r1"


def _scene() -> SceneDefinition:
    return SceneDefinition.from_mapping(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _action_schema() -> ActionModeSpec:
    return ActionModeSpec.from_controller_config(SimpleNamespace(
        kind="absolute_pose",
        reference="world",
        rotation_representation="quaternion_wxyz",
    ))


def _feedback_requirements(writer_id: str = WRITER) -> StateRequirements:
    entity = "panda-main"
    joints = (
        "joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "joint7",
        "finger_joint1", "finger_joint2",
    )
    requirements = [
        StateFieldRequirement(
            "state-field-requirement-v1", "joint_position", "joint", entity, joint,
            "required", "evaluation_boundary", "joint-definition", "joint_state_query",
        )
        for joint in joints
    ]
    requirements.extend((
        StateFieldRequirement(
            "state-field-requirement-v1", "frame_pose_world", "frame", entity, "hand",
            "required", "evaluation_boundary", "meter+quaternion_wxyz", "frame_pose_query",
        ),
        StateFieldRequirement(
            "state-field-requirement-v1", "actuator_force", "actuator", entity, "actuator8",
            "required", "evaluation_boundary", "newton", "actuator_force_query",
        ),
    ))
    return StateRequirements("state-requirements-v1", "controller", writer_id, tuple(requirements))


def _binding(*, writer_id: str = WRITER, groups=None) -> ControllerBindingV1:
    return ControllerBindingV1(
        "controller-binding-v1",
        writer_id,
        _action_schema(),
        "canonical-control-feedback",
        "canonical-control-feedback-v0",
        _feedback_requirements(writer_id),
        tuple(groups or (
            ControlGroupActionProjectionV1(
                "control-group-action-projection-v1", "panda-main", "arm", ARM_COMPONENTS,
            ),
            ControlGroupActionProjectionV1(
                "control-group-action-projection-v1", "panda-main", "gripper", GRIPPER_COMPONENTS,
            ),
        )),
    )


def _plan() -> ControlBindingPlanV1:
    return compile_control_binding_plan(_scene(), (_binding(),))


def _group(group_id: str, values, *, schema_id: str | None = None) -> ControlGroupActionV1:
    return ControlGroupActionV1(
        "control-group-action-v1", "panda-main", group_id,
        schema_id or _action_schema().schema_id, tuple(values),
    )


def _request(plan, groups=None, *, binding_hash=None) -> StructuredActionRequestV1:
    return StructuredActionRequestV1(
        "structured-action-request-v1",
        plan.scene_identity_hash,
        binding_hash or plan.identity_hash,
        tuple(groups or (
            _group("arm", (0.45, 0.0, 0.35, 1.0, 0.0, 0.0, 0.0)),
            _group("gripper", (1.0,)),
        )),
    )


def test_a05_arm_hand_bindings_partition_one_existing_panda_action_and_resources():
    scene = _scene()
    plan = compile_control_binding_plan(scene, (_binding(),))
    assert plan.scene_identity_hash == scene.identity_hash
    assert plan.resource_writers == tuple(
        ("panda-main", f"actuator{index}", WRITER) for index in range(1, 9)
    )

    prepared = prepare_structured_action(plan, _request(plan))
    assert len(prepared) == 1
    writer, action = prepared[0]
    assert writer == WRITER
    assert action == RequestedAction(
        "absolute_pose", "world", "quaternion_wxyz",
        (0.45, 0.0, 0.35, 1.0, 0.0, 0.0, 0.0, 1.0),
    )
    # The new structured contract is an input projection into the exact existing
    # one-controller Panda schema; it does not dispatch or duplicate its algorithm.
    assert plan.controller_bindings[0].feedback_schema_version == "canonical-control-feedback-v0"
    fields = {item.field_name for item in plan.controller_bindings[0].feedback_requirements.requirements}
    assert fields == {"joint_position", "frame_pose_world", "actuator_force"}


@pytest.mark.parametrize("groups, message", [
    ((_group("arm", (0.45, 0.0, 0.35, 1.0, 0.0, 0.0, 0.0)),), "every bound ControlGroup"),
    ((_group("arm", (0.45, 0.0, 0.35, 1.0, 0.0, 0.0, 0.0)),
      _group("gripper", (1.0,)), _group("unbound", (0.0,))), "every bound ControlGroup"),
    ((_group("arm", (0.45, 0.0, 0.35, 1.0, 0.0, 0.0)), _group("gripper", (1.0,)),), "dimension mismatch"),
    ((_group("arm", (0.45, 0.0, 0.35, 0.0, 0.0, 0.0, 0.0)), _group("gripper", (1.0,)),), "quaternion"),
    ((_group("arm", (0.45, 0.0, 0.35, 1.0, 0.0, 0.0, 0.0), schema_id="other.action.v1"),
      _group("gripper", (1.0,))), "schema identity mismatch"),
])
def test_invalid_complete_action_is_rejected_before_any_controller_or_runtime_call(groups, message):
    plan = _plan()
    request = _request(plan, groups)

    class OwnerProbe:
        controller_calls = 0
        runtime_calls = 0
        mutable_state = {"controller_epoch": 0, "provider_control_writes": 0}

        def compute(self, _action):
            self.controller_calls += 1
            self.mutable_state["controller_epoch"] += 1

        def apply(self, _target):
            self.runtime_calls += 1
            self.mutable_state["provider_control_writes"] += 1

    owners = OwnerProbe()
    before = dict(owners.mutable_state)
    with pytest.raises(ValueError, match=message):
        # A caller can reach the existing owners only after this whole-request
        # function returns all controller requests. There is no partial callback.
        prepared = prepare_structured_action(plan, request)
        for _writer, action in prepared:
            owners.compute(action)
            owners.apply(action)
    assert owners.controller_calls == owners.runtime_calls == 0
    assert owners.mutable_state == before


def test_nonfinite_group_action_unknown_fields_and_wrong_identity_fail_closed():
    plan = _plan()
    with pytest.raises(ValueError, match="finite"):
        _group("arm", (0.0, 0.0, 0.0, float("nan"), 0.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="unknown ControlGroupActionV1 fields"):
        ControlGroupActionV1.from_mapping({
            "schema_version": "control-group-action-v1",
            "entity_id": "panda-main",
            "group_id": "arm",
            "action_schema_id": _action_schema().schema_id,
            "values": [0.0] * 7,
            "actuator_refs": ["actuator1"],
        })
    with pytest.raises(ValueError, match="binding identity"):
        prepare_structured_action(plan, _request(plan, binding_hash="0" * 64))

    uncompiled = ControlBindingPlanV1(
        plan.schema_version, plan.scene_identity_hash, plan.controller_bindings, plan.resource_writers,
    )
    with pytest.raises(ValueError, match="Scene-validated"):
        prepare_structured_action(uncompiled, _request(uncompiled))


def test_binding_rejects_unknown_group_duplicate_writer_and_unresolved_feedback():
    scene = _scene()
    valid = _binding()
    unknown_group = replace(
        valid,
        groups=(ControlGroupActionProjectionV1(
            "control-group-action-projection-v1", "panda-main", "unknown", ARM_COMPONENTS,
        ), ControlGroupActionProjectionV1(
            "control-group-action-projection-v1", "panda-main", "gripper", GRIPPER_COMPONENTS,
        )),
    )
    with pytest.raises(ValueError, match="unknown ControlGroup"):
        compile_control_binding_plan(scene, (unknown_group,))

    duplicate_writer = replace(
        valid,
        writer_id="panda-main/second-writer",
        feedback_requirements=_feedback_requirements("panda-main/second-writer"),
        groups=(valid.groups[0],),
    )
    with pytest.raises(ValueError, match="overlapping Controller writers"):
        compile_control_binding_plan(scene, (valid, duplicate_writer))

    bad_feedback = replace(
        valid,
        feedback_requirements=StateRequirements(
            "state-requirements-v1", "controller", WRITER,
            (StateFieldRequirement(
                "state-field-requirement-v1", "actuator_force", "actuator", "panda-main",
                "unknown-actuator", "required", "evaluation_boundary", "newton", "actuator_force_query",
            ),),
        ),
    )
    with pytest.raises(ValueError, match="unknown actuator resource"):
        compile_control_binding_plan(scene, (bad_feedback,))

    bad_scene = scene.to_mapping()
    bad_scene["control_groups"][0]["actuator_refs"][0]["actuator_id"] = "unregistered"
    with pytest.raises(ValueError, match="unknown actuator"):
        SceneDefinition.from_mapping(bad_scene)


def test_feedback_and_legacy_requested_action_numeric_contracts_reject_nan():
    with pytest.raises(ValueError, match="finite"):
        CanonicalGripperFeedback("panda-main/gripper", float("nan"), 0.0)
    with pytest.raises(ValueError, match="finite"):
        RequestedAction("absolute_pose", "world", "quaternion_wxyz", (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, float("nan")))
    with pytest.raises(ValueError, match="NaN"):
        ActionModeSpec(
            "test.nan-bounds.v1", "task-env-action-v2", "absolute_pose", "world",
            "quaternion_wxyz", ("x",), (float("nan"),), (1.0,),
            quaternion_convention="wxyz",
        )


@pytest.mark.parametrize("provider", ["geophys", "mujoco"])
def test_legacy_panda_arm_hand_action_feedback_and_control_outputs_remain_compatible(provider):
    from task_env import make_env

    env = make_env("pick-cube-p16-reference-v1", config={"provider": provider, "horizon": 1})
    try:
        env.reset(seed=19)
        assert env.action_space.shape == (8,)
        assert env.metadata["action_schema"]["schema_id"] == "selected-reference-absolute-pose-v1"
        initial = env.state.pose_world["panda-v1/ee"]
        action_values = (*initial.position, *initial.quaternion_wxyz, 1.0)
        action = np.asarray(action_values, dtype=np.float64)
        captured = {}
        original_compute = env.controller.compute
        original_apply = env.session.apply_control

        def capture_compute(state, feedback, requested):
            result = original_compute(state, feedback, requested)
            captured["requested"] = requested
            captured["canonical"], captured["target"] = result
            return result

        def capture_apply(target):
            captured["applied"] = original_apply(target)
            return captured["applied"]

        env.controller.compute = capture_compute
        env.session.apply_control = capture_apply
        result = env.step(action)
        assert captured["requested"] == RequestedAction(
            "absolute_pose", "world", "quaternion_wxyz", tuple(float(value) for value in action),
        )
        assert captured["canonical"].schema_version == "canonical-action-v0"
        assert captured["target"].schema_version == "canonical-control-v0"
        assert captured["applied"].schema_version == "applied-canonical-control-v0"
        assert captured["applied"].target_hash == captured["target"].identity_hash
        assert captured["applied"].provider_name == provider
        assert env.state.control_step == env.feedback.control_step == 1
        assert result[2] is False and result[3] is True
    finally:
        env.close()
