"""Synthetic logical scene and physical bindings shared by diagnostics only."""
from task_env.artifacts import (
    ActuatorReference, ActuatorResourceDefinition, ArticulationDefinition,
    AssetDefinition, ControlGroup, EntityInstance, FrameDefinition, FrameReference,
    JointDefinition, JointReference, LogicalAssemblyControlGroupReferenceV1,
    LogicalAssemblyEntityMemberV1, LogicalAssemblyNestedMemberV1,
    LogicalAssemblyScenePinV1, LogicalAssemblySubcomponentReferenceV1,
    LogicalAssemblyV1, PoseWorld, RobotInstance, SceneDefinition,
)
from task_env.artifacts.contracts import CapabilityAssessmentRowV1, CapabilityAssessmentV1
from task_env.artifacts.state import StateBoundaryIdentity, StateSampleClock
from task_env.controllers.canonical.physical_commands import (
    PhysicalCommandContextV1, ContributionPolicyV1, JointEffortV1,
    PhysicalJointChannelV1, PhysicalControlBindingV1, PhysicalJointBuildReceiptV1,
)
from task_env.runtime.sessions.physical_control import compile_physical_control_binding

IDENTITY = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
SHARED_ASSET = "robot/shared"

def _asset(asset_id=SHARED_ASSET, *, version="v1", source_revision=None):
    return AssetDefinition(
        "asset-definition-v1",
        asset_id,
        version,
        f"procedural://example/{asset_id}",
        source_revision=source_revision,
    )

def _entity(entity_id, asset_id=SHARED_ASSET, *, version="v1"):
    return EntityInstance("entity-instance-v1", entity_id, asset_id, version)

def _scene_v3(*, source_revision=None):
    entities = (_entity("arm"), _entity("hand"))
    frames = tuple(
        FrameDefinition("frame-definition-v1", entity.entity_id, frame_id, "runtime", None, None)
        for entity in entities
        for frame_id in ("base", "tool")
    )
    articulations = tuple(
        ArticulationDefinition(
            "articulation-definition-v1",
            entity.entity_id,
            "base",
            ("base", "tool"),
            (JointDefinition(
                "joint-definition-v1",
                "drive",
                FrameReference(entity.entity_id, "base"),
                FrameReference(entity.entity_id, "tool"),
                IDENTITY,
                IDENTITY,
                "revolute",
                (0.0, 0.0, 1.0),
                "radian",
                "radian_per_second",
                1,
                1,
            ),),
        )
        for entity in entities
    )
    actuators = (
        ActuatorResourceDefinition("actuator-resource-v1", "arm", "drive"),
        ActuatorResourceDefinition("actuator-resource-v1", "arm", "gripper"),
        ActuatorResourceDefinition("actuator-resource-v1", "hand", "drive"),
    )
    groups = (
        ControlGroup("control-group-v1", "arm", "arm-main", (ActuatorReference("arm", "drive"),)),
        ControlGroup("control-group-v1", "arm", "arm-hand", (ActuatorReference("arm", "gripper"),)),
        ControlGroup("control-group-v1", "hand", "hand-main", (ActuatorReference("hand", "drive"),)),
    )
    robots = tuple(
        RobotInstance("robot-instance-v1", entity.entity_id, (FrameReference(entity.entity_id, "base"),))
        for entity in entities
    )
    return SceneDefinition(
        "scene-definition-v3",
        "scene-main",
        (_asset(source_revision=source_revision),),
        entities,
        frames,
        articulations,
        robots,
        actuators,
        groups,
    )

def _pin(scene):
    return LogicalAssemblyScenePinV1(
        "logical-assembly-scene-pin-v1",
        scene.scene_id,
        scene.schema_version,
        scene.identity_hash,
    )

def _entity_member(entity_id, *, path=None, asset_id=SHARED_ASSET, asset_version="v1"):
    return LogicalAssemblyEntityMemberV1(
        "entity_member", path or (f"owner-{entity_id}",), entity_id, asset_id, asset_version
    )

def _sub(path, target, target_kind):
    return LogicalAssemblySubcomponentReferenceV1(
        "existing_entity_subcomponent_ref", tuple(path), target_kind, target
    )

def _nested(path, child, *, digest=None):
    return LogicalAssemblyNestedMemberV1(
        "nested_assembly",
        tuple(path),
        child.assembly_id,
        child.revision,
        child.logical_content_sha256 if digest is None else digest,
    )

def _assembly(scene, assembly_id, members=(), *, revision="r1", scene_pin=None):
    return LogicalAssemblyV1(
        "logical-assembly-v1", assembly_id, revision, scene_pin or _pin(scene), tuple(members)
    )

def _primary_closure(scene=None):
    scene = scene or _scene_v3()
    arm = _assembly(scene, "arm-leaf", (_entity_member("arm", path=("owner", "arm")),))
    hand = _assembly(scene, "hand-leaf", (_entity_member("hand", path=("owner", "hand")),))
    branch = _assembly(scene, "robot-branch", (
        _nested(("arm",), arm),
        _nested(("hand",), hand),
        _sub(("arm-base-view",), FrameReference("arm", "base"), "frame"),
        _sub(("arm-tool-view",), FrameReference("arm", "tool"), "frame"),
        _sub(("arm-drive-joint",), JointReference("arm", "drive"), "joint"),
        _sub(("arm-drive-actuator",), ActuatorReference("arm", "drive"), "actuator"),
        _sub(("arm-main-group",), LogicalAssemblyControlGroupReferenceV1("arm", "arm-main"), "control_group"),
        _sub(("arm-hand-group",), LogicalAssemblyControlGroupReferenceV1("arm", "arm-hand"), "control_group"),
        # This reference is read-only and points at the separately owned sibling hand leaf.
        _sub(("hand-group-view",), LogicalAssemblyControlGroupReferenceV1("hand", "hand-main"), "control_group"),
    ))
    root = _assembly(scene, "robot-root", (_nested(("robot",), branch),))
    return root, branch, arm, hand, {
        (branch.assembly_id, branch.revision): branch,
        (arm.assembly_id, arm.revision): arm,
        (hand.assembly_id, hand.revision): hand,
    }


def _joint_receipt(plan, context):
    return PhysicalJointBuildReceiptV1('physical-joint-build-receipt-v1',
        plan.binding.identity_hash, plan.binding.source_closure_sha256,
        context.boundary.provider_materialization_id, plan.binding.channels, 'synthetic_fixture')

def _case():
    scene = _scene_v3()
    root, _, _, _, catalog = _primary_closure(scene)
    channel = PhysicalJointChannelV1(
        'physical-joint-channel-v1', ('robot', 'arm-drive-joint'), ('controller-a',),
        'arm', 'drive', 'dof0', 'revolute', (0, 0, 1), FrameReference('arm', 'base'),
        1, 'N*m', (-5, 5), 'native-a', 'direct-a', 1, (-5, 5), 'disabled',
    )
    binding = PhysicalControlBindingV1('physical-control-binding-v1', scene.identity_hash,
        'a'*64, 'source-a', 'b'*64, root.logical_content_sha256, (channel,))
    plan = compile_physical_control_binding(scene, root, catalog, binding)
    boundary = StateBoundaryIdentity('state-boundary-identity-v1', 'episode-a',
        'reset-'+'d'*64, scene.identity_hash, 'instance-a', 'material-a', 0, 0)
    clock = StateSampleClock('state-sample-clock-v1', 'evaluation_boundary', 0, 0.0)
    context = PhysicalCommandContextV1('physical-command-context-v1', 'source-a',
        'b'*64, 'a'*64, boundary, clock, 0, 1, .01, .01)
    def effort(cid, value, composition='sum'):
        policy = ContributionPolicyV1('physical-contribution-policy-v1', cid, cid,
            'controller-a', composition, 'reject_outside', 'one_interval')
        return JointEffortV1('joint-effort-v1', context, policy, 'arm', 'drive', 'dof0',
            'revolute', (0,0,1), FrameReference('arm','base'), 1, 'N*m', value,
            (-5,5), 'direct_effort')
    def assessment(*capabilities):
        if 'joint_effort' in capabilities:
            capabilities = (*capabilities, 'transmission', 'native_drive_state')
        return CapabilityAssessmentV1('capability-assessment-v1', binding.identity_hash,
            'static_preflight', tuple(CapabilityAssessmentRowV1(
                'capability-assessment-row-v1', name, f'binding:{binding.identity_hash}',
                'required', 'supported', 'implemented', 'available', 'none',
                'static_preflight', 'synthetic test declaration', None, None)
                for name in capabilities))
    return plan, context, effort, assessment


def _readback():
    from task_env.runtime.sessions.free_joint_state import PublicRigidBodyReadbackV1
    return PublicRigidBodyReadbackV1(
        "public-rigid-body-readback-v1", FrameReference("cube-v1", "root"),
        (1.0, 2.0, 3.0),
        (0.7071067811865476, 0.0, 0.0, 0.7071067811865476),
        (0.2, -0.1, 0.3), (0.3, -0.4, 0.7), (0.6, 0.5, -0.2),
        "world", "center_of_mass",
    )
