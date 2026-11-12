"""MuJoCo-owned source lowering for a declared task/robot composition.

This module only prepares importer input.  It does not create a session, apply
commands, or turn a composition plan into runtime admission.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math
import xml.etree.ElementTree as ET
from .source_scene_import import declare_panda_scene


def panda_effort_source_limits(root_xml):
    """Verify the declared Panda MJCF transmission and return its drive limits."""
    defaults = root_xml.find("./default/default[@class='panda']/general")
    actuators = {node.get('name'): node for node in root_xml.findall('./actuator/general')}
    tendon = root_xml.find("./tendon/fixed[@name='split']")
    equality = root_xml.find("./equality/joint[@joint1='finger_joint1'][@joint2='finger_joint2']")
    if (defaults is None or tendon is None or equality is None
            or tuple((x.get('joint'), x.get('coef')) for x in tendon.findall('joint'))
            != (('finger_joint1', '0.5'), ('finger_joint2', '0.5'))
            or equality.get('polycoef', '0 1 0 0 0').split() != ['0', '1', '0', '0', '0']
            or equality.get('active', 'true').lower() not in {'true', '1'}
            or any(node.get('gear') is not None for node in root_xml.findall('.//default/general'))):
        raise ValueError('Panda tendon/equality/default gear source is not the declared pair')
    limits = []
    for i in range(1, 9):
        actuator = actuators.get(f'actuator{i}')
        expected = {'joint': f'joint{i}'} if i < 8 else {'tendon': 'split'}
        if (actuator is None or any(actuator.get(k) != v for k, v in expected.items())
                or actuator.get('class') != 'panda' or actuator.get('gear') is not None
                or actuator.get('biastype', defaults.get('biastype')) != 'affine'):
            raise ValueError('Panda actuator mapping differs from the declared source')
        gain = tuple(float(x) for x in actuator.get('gainprm', '').split())
        bias = tuple(float(x) for x in actuator.get('biasprm', '').split())
        if (not gain or len(bias) < 3 or not all(math.isfinite(v) for v in (*gain, *bias))
                or gain[0] <= 0 or bias[1] >= 0 or bias[2] > 0):
            raise ValueError('Panda source does not declare the expected position drive')
        raw = actuator.get('forcerange', defaults.get('forcerange'))
        pair = tuple(float(x) for x in raw.split()) if raw else ()
        if len(pair) != 2 or not all(math.isfinite(v) for v in pair) or not pair[0] < 0 < pair[1]:
            raise ValueError('Panda actuator requires a finite signed force range')
        limits.append(pair)
    return limits


def checked_panda_effort_source_limits(source, scene):
    """Verify the bound MJCF closure and read its Panda transmission limits."""
    from .source import verify_projected_scene_source

    verify_projected_scene_source(source.scene_source, scene, source.source_closure_digest)
    return panda_effort_source_limits(ET.fromstring(source.scene_source.xml))


def extract_task_world_mjcf(*, task_xml: str, expected_xml_sha256: str,
                            retained_roots: tuple[str, ...],
                            replaced_robot_roots: tuple[str, ...]) -> str:
    """Preserve declared task world children and remove exactly the robot roots.

    The caller must separately verify the full task closure.  The digest here
    binds this projection to the exact task XML used by the composition plan.
    Unaccounted named root bodies fail closed; unnamed or repeated roots fail
    before any provider is imported.  MuJoCo's documented free-joint spelling
    is used with the existing attributes retained, matching the legacy adapter.
    """
    if type(task_xml) is not str:
        raise TypeError('task XML must be immutable text')
    if hashlib.sha256(task_xml.encode('utf-8')).hexdigest() != expected_xml_sha256:
        raise ValueError('task XML digest differs from composition input')
    for label, values in (('retained', retained_roots), ('replaced', replaced_robot_roots)):
        if (type(values) is not tuple or not values or any(type(v) is not str or not v for v in values)
                or len(set(values)) != len(values)):
            raise ValueError(f'{label} root names must be a nonempty unique tuple')
    retained, replaced = set(retained_roots), set(replaced_robot_roots)
    if retained & replaced:
        raise ValueError('retained and replaced roots must be disjoint')
    source = ET.fromstring(task_xml)
    if source.tag != 'mujoco':
        raise ValueError('task source must be MuJoCo XML')
    worlds = source.findall('worldbody')
    if len(worlds) != 1:
        raise ValueError('task source must contain exactly one worldbody')
    world = worlds[0]
    roots = [body.get('name') for body in world.findall('body')]
    if any(not name for name in roots) or len(roots) != len(set(roots)):
        raise ValueError('task source root bodies must be uniquely named')
    if set(roots) != retained | replaced:
        raise ValueError('task root bodies differ from the declared ownership partition')
    result = ET.Element('mujoco', {'model': 'declared-task-world'})
    result_world = ET.SubElement(result, 'worldbody', dict(world.attrib))
    for element in world:
        if element.tag != 'body' or element.get('name') in retained:
            result_world.append(deepcopy(element))
    for element in result_world.iter('freejoint'):
        element.tag = 'joint'
        element.set('type', 'free')
    return ET.tostring(result, encoding='unicode')


def coalesce_identical_world_elements(*, robot_xml: str, task_world_xml: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Keep the task-owned copy of exactly identical named world elements.

    A shared name with different contents is ambiguous and must not be silently
    discarded. Body ownership is handled separately by the composition plan.
    """
    robot = ET.fromstring(robot_xml)
    task = ET.fromstring(task_world_xml)
    robot_world, task_world = robot.find('worldbody'), task.find('worldbody')
    if robot_world is None or task_world is None:
        raise ValueError('both source projections require worldbody')
    def named(world):
        result = {}
        for element in world:
            name = element.get('name')
            if element.tag == 'body' or name is None:
                continue
            key = (element.tag, name)
            if key in result:
                raise ValueError('world source has duplicate named elements')
            result[key] = element
        return result
    task_elements = named(task_world)
    robot_elements = named(robot_world)
    coalesced = []
    for key in sorted(set(task_elements) & set(robot_elements)):
        left, right = deepcopy(robot_elements[key]), deepcopy(task_elements[key])
        left.tail = right.tail = None
        if ET.tostring(left) != ET.tostring(right):
            raise ValueError(f'conflicting task and robot world element: {key!r}')
        robot_world.remove(robot_elements[key])
        coalesced.append(key)
    return ET.tostring(robot, encoding='unicode'), tuple(coalesced)


def materialize_fixed_robot_task(*, composition, task_receipt, fixed_declaration,
                                 retained_roots, replaced_robot_roots,
                                 entity_body_names, allowed_free_joints,
                                 task_site_transfers=()):
    """Materialize the verified task world and exact fixed robot in one model.

    The caller owns the returned MuJoCo model and any subsequent MjData. This
    bounded build does not perform reset, control, or advance the solver.
    The input task receipt must still own its immutable source snapshot.
    """
    from ...assembly.source_composition import (
        CompositionMaterializationReceiptV1, SourceCompositionPlanV1,
    )
    from ...assembly.panda_fixed_source import PandaFixedSourceDeclarationV1
    from ...assembly.fixed_attachment import lower_fixed_attachment_sources
    from .source import ExecutionSourceReceiptV1
    import mujoco

    if type(composition) is not SourceCompositionPlanV1 or composition.mode != 'replace':
        raise TypeError('fixed robot materialization requires a replacement composition plan')
    if type(task_receipt) is not ExecutionSourceReceiptV1:
        raise TypeError('fixed robot materialization requires a verified task source receipt')
    if type(fixed_declaration) is not PandaFixedSourceDeclarationV1:
        raise TypeError('fixed robot materialization requires the exact fixed source declaration')
    task_receipt.validate_snapshot()
    if (tuple(retained_roots) != tuple(name for _, name in composition.task_entity_source_roots)
            or tuple(replaced_robot_roots) != composition.replaced_robot_source_roots
            or tuple(allowed_free_joints) != tuple(name for _, name in composition.task_free_joints)):
        raise ValueError('native task source partition differs from the composition plan')
    if (composition.task_source.source_id, composition.task_source.closure_sha256) != (
            task_receipt.source_id, task_receipt.source_closure_digest):
        raise ValueError('task source receipt differs from composition plan')
    fixed = fixed_declaration.attachment_plan
    if (composition.assembly_identity_sha256 != fixed_declaration.assembly.logical_content_sha256
            or composition.attachment_identity_sha256 != fixed.identity_hash):
        raise ValueError('fixed robot assembly or attachment differs from composition plan')
    sources = fixed_declaration.source_by_entity
    expected_sources = {(sources[entity].source_id, fixed.source_closure_sha256, entity)
                        for entity in (fixed.parent_entity_id, fixed.child_entity_id)}
    declared_sources = {(source.source_id, source.closure_sha256, entity)
                        for source in composition.robot_sources for entity in source.entity_ids}
    if declared_sources != expected_sources:
        raise ValueError('fixed robot source ownership differs from composition plan')
    lowered = lower_fixed_attachment_sources(
        parent_source=fixed_declaration.parent_source, source_by_entity=sources,
        scene=fixed_declaration.scene, plan=fixed, assembly=fixed_declaration.assembly)
    task_xml = task_receipt.closure_files['canonical-source.xml'].decode('utf-8')
    task_world_xml = extract_task_world_mjcf(
        task_xml=task_xml, expected_xml_sha256=task_receipt.canonical_xml_sha256,
        retained_roots=retained_roots, replaced_robot_roots=replaced_robot_roots)

    def without_keyframes(xml):
        root = ET.fromstring(xml)
        for element in tuple(root.findall('keyframe')):
            root.remove(element)
        return ET.tostring(root, encoding='unicode')
    parent_xml, coalesced = coalesce_identical_world_elements(
        robot_xml=without_keyframes(lowered.parent_xml), task_world_xml=task_world_xml)
    parent = mujoco.MjSpec.from_string(parent_xml, assets=lowered.parent_assets)
    if type(task_site_transfers) is not tuple:
        raise TypeError('task site transfers must be an immutable tuple')
    if task_site_transfers != composition.task_site_transfers:
        raise ValueError('task site transfers differ from the composition plan')
    child_xml = without_keyframes(lowered.child_xml)
    for transfer in task_site_transfers:
        if type(transfer) is not tuple or len(transfer) != 3:
            raise ValueError('task site transfer requires source body, site and target body')
        child_xml = transfer_declared_task_site(
            task_xml=task_xml, expected_xml_sha256=task_receipt.canonical_xml_sha256,
            source_body=transfer[0], site_name=transfer[1],
            robot_xml=child_xml, target_body=transfer[2])
    child = mujoco.MjSpec.from_string(child_xml, assets=lowered.child_assets)
    child_body = child.body(fixed.child_mount_body_name.removeprefix(fixed.namespace_prefix))
    if child_body is None:
        raise ValueError('fixed robot child source lacks the declared root')
    frame = child.worldbody.add_frame(pos=fixed.attach_frame_from_child_worldbody.position,
                                      quat=fixed.attach_frame_from_child_worldbody.quaternion_wxyz)
    child_body.set_frame(frame)
    if parent.attach(child, site=fixed.parent_mount_site_name, prefix=fixed.namespace_prefix) is None:
        raise ValueError('MuJoCo failed to attach the declared fixed robot')
    task_spec = mujoco.MjSpec.from_string(task_world_xml)
    if parent.attach(task_spec, frame=parent.worldbody.add_frame(), prefix='') is None:
        raise ValueError('MuJoCo failed to attach the task world')
    model = parent.compile()
    if type(entity_body_names) is not tuple or len(dict(entity_body_names)) != len(entity_body_names):
        raise ValueError('entity mapping must contain unique canonical names')
    mapping = dict(entity_body_names)
    if set(mapping) != set(composition.entity_ids):
        raise ValueError('native entity mapping differs from composition ownership')
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('native entity body mapping must be unique')
    for name in mapping.values():
        if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name) < 1:
            raise ValueError(f'composition body is absent from native model: {name}')
    if {mapping[entity] for entity in composition.task_entity_ids} != set(retained_roots):
        raise ValueError('task entity bindings differ from retained task roots')
    for entity, root in ((fixed.parent_entity_id, fixed.parent_root),
                         (fixed.child_entity_id, fixed.child_root)):
        expected_root = fixed.native_body_names[f'{entity}/{root.frame_id}']
        if mapping.get(entity) != expected_root:
            raise ValueError('robot entity root differs from the fixed source plan')
    actual_free = tuple(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
                        for index in range(model.njnt)
                        if model.jnt_type[index] == mujoco.mjtJoint.mjJNT_FREE)
    if type(allowed_free_joints) is not tuple or set(actual_free) != set(allowed_free_joints) or len(actual_free) != len(allowed_free_joints):
        raise ValueError('native free joints differ from declared task free joints')
    for entity, name in composition.task_free_joints:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, mapping[entity])
        if joint_id < 0 or model.jnt_bodyid[joint_id] != body_id:
            raise ValueError('free joint does not belong to its declared task entity')
    site = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, fixed.parent_mount_site_name)
    child_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, fixed.child_mount_body_name)
    if site < 0 or child_id < 1 or model.body_parentid[child_id] != model.site_bodyid[site]:
        raise ValueError('native attachment parent differs from declared mount')
    import numpy as np
    expected_pos = np.empty(3, dtype=np.float64)
    expected_quat = np.empty(4, dtype=np.float64)
    mujoco.mju_mulPose(expected_pos, expected_quat, model.site_pos[site], model.site_quat[site],
        np.asarray(fixed.parent_site_from_child_root.position, dtype=np.float64),
        np.asarray(fixed.parent_site_from_child_root.quaternion_wxyz, dtype=np.float64))
    actual_pos, actual_quat = model.body_pos[child_id], model.body_quat[child_id]
    position_error = float(np.linalg.norm(actual_pos - expected_pos))
    quaternion_error = float(min(np.linalg.norm(actual_quat - expected_quat),
                                 np.linalg.norm(actual_quat + expected_quat)))
    if position_error > 1e-9 or quaternion_error > 1e-9:
        raise ValueError('native attachment transform differs from the declared fixed pose')
    attachment_facts = {'parent_body_id': int(model.site_bodyid[site]),
        'child_body_id': int(child_id), 'site_name': fixed.parent_mount_site_name,
        'child_name': fixed.child_mount_body_name,
        'site_position': model.site_pos[site].tolist(), 'site_quaternion_wxyz': model.site_quat[site].tolist(),
        'declared_site_from_child': fixed.parent_site_from_child_root.to_mapping(),
        'actual_child_position': actual_pos.tolist(), 'actual_child_quaternion_wxyz': actual_quat.tolist(),
        'position_error_m': position_error, 'quaternion_sign_invariant_error': quaternion_error}
    for _source_body, site_name, target_body in task_site_transfers:
        site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, fixed.namespace_prefix + site_name)
        target_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, fixed.namespace_prefix + target_body)
        if site_id < 0 or target_id < 1 or model.site_bodyid[site_id] != target_id:
            raise ValueError('transferred task site differs from declared target body')
    for kind, objtype, names in (
        ('body', mujoco.mjtObj.mjOBJ_BODY, fixed.native_body_names),
        ('site', mujoco.mjtObj.mjOBJ_SITE, fixed.native_site_names),
        ('joint', mujoco.mjtObj.mjOBJ_JOINT, fixed.native_joint_names),
        ('actuator', mujoco.mjtObj.mjOBJ_ACTUATOR, fixed.native_actuator_names),
        ('tendon', mujoco.mjtObj.mjOBJ_TENDON, fixed.native_tendon_names),
    ):
        for name in names.values():
            if mujoco.mj_name2id(model, objtype, name) < 0:
                raise ValueError(f'declared native {kind} is absent: {name}')
    source_closures = {composition.task_source.source_id: composition.task_source.closure_sha256}
    source_closures.update((x.source_id, x.closure_sha256) for x in composition.robot_sources)
    # This construction identity identifies the build, not a live RuntimeSession.
    receipt = CompositionMaterializationReceiptV1(
        composition.identity_hash, tuple(sorted(source_closures.items())),
        tuple(entity_body_names), f'mujoco-build:{composition.identity_hash}')
    receipt.validate_against(composition)
    return model, receipt, {'attachment': attachment_facts, 'coalesced_world_elements': coalesced,
                            'free_joints': actual_free,
                            'task_site_transfers': task_site_transfers,
                            'robot_closure_sha256': lowered.source_closure_sha256}


def transfer_declared_task_site(*, task_xml: str, expected_xml_sha256: str,
                                source_body: str, site_name: str,
                                robot_xml: str, target_body: str) -> str:
    """Carry a task-owned semantic site onto the selected robot body.

    The caller declares both source and target owners. The copied site is
    unchanged; ambiguous body/site names and an existing target site fail.
    The provider's attachment namespace is applied later by MuJoCo.
    """
    if type(task_xml) is not str or hashlib.sha256(task_xml.encode('utf-8')).hexdigest() != expected_xml_sha256:
        raise ValueError('task XML digest differs from site source')
    if any(type(v) is not str or not v for v in (source_body, site_name, target_body)):
        raise ValueError('site and body names must be nonempty')
    task_root, robot_root = ET.fromstring(task_xml), ET.fromstring(robot_xml)
    sources = [node for node in task_root.iter('body') if node.get('name') == source_body]
    targets = [node for node in robot_root.iter('body') if node.get('name') == target_body]
    if len(sources) != 1 or len(targets) != 1:
        raise ValueError('site source and target bodies must resolve uniquely')
    sites = [node for node in sources[0].findall('site') if node.get('name') == site_name]
    if len(sites) != 1:
        raise ValueError('declared task site must exist exactly once on its source body')
    if any(node.get('name') == site_name for node in robot_root.iter('site')):
        raise ValueError('task site name already exists in robot source')
    targets[0].append(deepcopy(sites[0]))
    return ET.tostring(robot_root, encoding='unicode')


def validate_composed_source_names(source) -> None:
    """Preflight source-owned names without claiming native build success."""
    from ...assembly.source_composition import CompositionRuntimeInputV1
    from ...assembly.panda_fixed_source import PandaFixedSourceDeclarationV1
    from ...assembly.fixed_attachment import lower_fixed_attachment_sources
    value = source.composition_runtime_input
    if type(value) is not CompositionRuntimeInputV1 or type(value.fixed_declaration) is not PandaFixedSourceDeclarationV1:
        raise TypeError('composition preflight requires the exact declared source owners')
    declaration, plan = value.fixed_declaration, value.plan
    fixed = declaration.attachment_plan
    receipt = source.execution_source_receipt
    if receipt is None:
        raise ValueError('composition preflight requires task source receipt')
    receipt.validate_snapshot()
    if (receipt.source_id, receipt.source_closure_digest) != (
            plan.task_source.source_id, plan.task_source.closure_sha256):
        raise ValueError('composition task closure differs from its plan')
    if (declaration.assembly.logical_content_sha256, fixed.identity_hash) != (
            plan.assembly_identity_sha256, plan.attachment_identity_sha256):
        raise ValueError('composition assembly or attachment differs from its plan')
    lowered = lower_fixed_attachment_sources(
        parent_source=declaration.parent_source, source_by_entity=declaration.source_by_entity,
        scene=declaration.scene, plan=fixed, assembly=declaration.assembly)
    expected_robot_sources = {(declaration.source_by_entity[e].source_id,
                               fixed.source_closure_sha256, e)
                              for e in (fixed.parent_entity_id, fixed.child_entity_id)}
    if {(s.source_id, s.closure_sha256, entity) for s in plan.robot_sources
            for entity in s.entity_ids} != expected_robot_sources:
        raise ValueError('composition robot source ownership differs from its plan')
    task_xml = receipt.closure_files['canonical-source.xml'].decode('utf-8')
    task_world = extract_task_world_mjcf(
        task_xml=task_xml, expected_xml_sha256=receipt.canonical_xml_sha256,
        retained_roots=value.retained_roots, replaced_robot_roots=value.replaced_robot_roots)
    child_xml = lowered.child_xml
    for source_body, site_name, target_body in plan.task_site_transfers:
        child_xml = transfer_declared_task_site(task_xml=task_xml,
            expected_xml_sha256=receipt.canonical_xml_sha256, source_body=source_body,
            site_name=site_name, robot_xml=child_xml, target_body=target_body)
    roots = ((ET.fromstring(task_world), ''), (ET.fromstring(lowered.parent_xml), ''),
             (ET.fromstring(child_xml), fixed.namespace_prefix))
    available = {name: set() for name in ('joint', 'body', 'frame', 'actuator')}
    for root, prefix in roots:
        for key, tags in (('joint', ('joint', 'freejoint')), ('body', ('body',)), ('frame', ('site',))):
            for tag in tags:
                available[key].update(prefix + node.get('name') for node in root.iter(tag) if node.get('name'))
        actuators = root.find('actuator')
        if actuators is not None:
            available['actuator'].update(prefix + node.get('name') for node in actuators if node.get('name'))
    required = {
        'joint': (*source.joints.values(), *source.free_joints.values()),
        'body': source.bodies.values(), 'frame': source.frames.values(),
        'actuator': (*source.joint_targets.values(), *source.open_actuators,
                     *source.torque_actuators.values(), *source.position_actuators.values()),
    }
    for kind, names in required.items():
        missing = set(names) - available[kind]
        if missing:
            raise ValueError(f'composed source missing named {kind}: {sorted(missing)}')


def derive_task_compatible_attachment(*, declaration, task_receipt, task_hand_name, source_hand_name):
    """Derive the fixed mount that preserves the task's authored hand frame.

    Both source closures are verified first. The old exact attachment plan is
    not modified; a new immutable plan binds the derived transform to the task
    source identity through the outer composition plan.
    """
    import math
    from dataclasses import replace
    from ...artifacts import PoseWorld
    from ...assembly.panda_fixed_source import PandaFixedSourceDeclarationV1
    from ...assembly.fixed_attachment import lower_fixed_attachment_sources
    from .source import ExecutionSourceReceiptV1
    if type(declaration) is not PandaFixedSourceDeclarationV1 or type(task_receipt) is not ExecutionSourceReceiptV1:
        raise TypeError('task mount requires verified task and fixed robot declarations')
    task_receipt.validate_snapshot()
    fixed = declaration.attachment_plan
    lower_fixed_attachment_sources(parent_source=declaration.parent_source,
        source_by_entity=declaration.source_by_entity, scene=declaration.scene,
        plan=fixed, assembly=declaration.assembly)
    task = ET.fromstring(task_receipt.closure_files['canonical-source.xml'])
    arm = ET.fromstring(declaration.parent_source.xml)
    hand = ET.fromstring(declaration.source_by_entity[fixed.child_entity_id].xml)

    def named(root, tag, name):
        values = [node for node in root.iter(tag) if node.get('name') == name]
        if len(values) != 1: raise ValueError(f'source mount name is not unique: {name}')
        return values[0]
    def parent(root, target):
        values = [node for node in root.iter() if target in list(node)]
        if len(values) != 1: raise ValueError('source mount parent is not unique')
        return values[0]
    def quat(raw):
        values = tuple(float(v) for v in (raw or '1 0 0 0').split())
        if len(values) != 4: raise ValueError('mount quaternion requires four values')
        norm = math.sqrt(sum(v*v for v in values))
        if not math.isfinite(norm) or norm == 0: raise ValueError('mount quaternion is invalid')
        return tuple(v / norm for v in values)
    def pos(raw):
        values = tuple(float(v) for v in (raw or '0 0 0').split())
        if len(values) != 3 or not all(math.isfinite(v) for v in values):
            raise ValueError('mount position is invalid')
        return values
    def multiply(a, b):
        w,x,y,z=a; v,i,j,k=b
        return (w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
                w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v)
    def conjugate(q): return (q[0],-q[1],-q[2],-q[3])
    def rotate(q, v):
        result=multiply(multiply(q,(0.,*v)),conjugate(q)); return result[1:]
    def compose(a,b):
        rotated=rotate(a[1],b[0]); return (tuple(x+y for x,y in zip(a[0],rotated,strict=True)), multiply(a[1],b[1]))
    def inverse(a):
        q=conjugate(a[1]); return (rotate(q,tuple(-v for v in a[0])),q)
    def pose(node):
        if any(node.get(k) is not None for k in ('euler','axisangle','xyaxes','zaxis')):
            raise ValueError('mount source uses an unsupported rotation spelling')
        return (pos(node.get('pos')),quat(node.get('quat')))

    task_hand = named(task,'body',task_hand_name)
    mount_site = named(arm,'site',fixed.parent_mount_site_name)
    mount_body = parent(arm,mount_site)
    source_hand = named(hand,'body',source_hand_name)
    task_parent, arm_parent = parent(task,task_hand), parent(arm,mount_body)
    if (task_parent.tag != 'body' or arm_parent.tag != 'body'
            or task_parent.get('name') != arm_parent.get('name')):
        raise ValueError('task hand and robot mount do not share a named parent frame')
    # Every arm body must have matching local frame transforms in the two
    # frozen sources; the task may add collision/visual children separately.
    for index in range(8):
        name=f'link{index}'
        task_node, arm_node = named(task, 'body', name), named(arm, 'body', name)
        task_parent_node, arm_parent_node = parent(task, task_node), parent(arm, arm_node)
        if (task_parent_node.tag, task_parent_node.get('name')) != (arm_parent_node.tag, arm_parent_node.get('name')):
            raise ValueError(f'task and robot arm frame parent differs: {name}')
        left, right = pose(task_node), pose(arm_node)
        if math.dist(left[0],right[0])>1e-12 or min(math.dist(left[1],right[1]),
                                                   math.dist(left[1],tuple(-v for v in right[1])))>1e-12:
            raise ValueError(f'task and robot arm frame transform differs: {name}')
    site_in_parent=compose(pose(mount_body),pose(mount_site))
    site_from_task_hand=compose(inverse(site_in_parent),pose(task_hand))
    attach_frame=compose(site_from_task_hand,inverse(pose(source_hand)))
    derived=replace(fixed,
        parent_site_from_child_root=PoseWorld(site_from_task_hand[0],quat(' '.join(map(str,site_from_task_hand[1])))),
        attach_frame_from_child_worldbody=PoseWorld(attach_frame[0],quat(' '.join(map(str,attach_frame[1])))))
    derived.validate()
    return replace(declaration, attachment_plan=derived)


def compose_robot_source(source, *, robot, composition_intent, artifact, controller, task_entities,
                                  existing_robot_entity, task_body_names, task_site_transfers,
                                  robot_recipe=None, controller_profile=None):
    """Provider-owned adapter for neutral Task and Robot source recipes.

    Robot classes expose only a ``RobotSourceRecipeV1``. This adapter owns
    RuntimeSource checks, source parsing, native mappings, and MuJoCo-specific
    materialization input construction. The V2 request is frozen before the
    MuJoCo model is built and remains alongside the legacy V1 receipt identity.
    """
    from dataclasses import replace
    from ...assembly.source_composition import (
        CompositionAttachmentV2, CompositionRuntimeInputV1, CompositionSourceV1,
        CompositionSourceV2, PositionSubjectControlBindingV1,
        SourceCompositionPlanV1, SourceCompositionRequestV2,
    )

    from .source_composition_adapters import validate_robot_source_request
    recipe = validate_robot_source_request(source, robot=robot, composition_intent=composition_intent,
        task_entities=task_entities, existing_robot_entity=existing_robot_entity,
        task_body_names=task_body_names, task_site_transfers=task_site_transfers,
        robot_recipe=robot_recipe, controller_profile=controller_profile)

    if recipe.mode == 'reference-task-source':
        from .source_composition_adapters import _compose_checked_reference_source
        return _compose_checked_reference_source(source, robot=robot, recipe=recipe,
            composition_intent=composition_intent, artifact=artifact, controller=controller,
            task_entities=task_entities, existing_robot_entity=existing_robot_entity)

    if recipe.mode != 'replace-task-subtree':
        raise ValueError('MuJoCo adapter does not admit this Robot recipe mode')
    if len(task_site_transfers) != 1:
        raise ValueError('assembled Panda requires one declared Task end-effector site')
    task_hand, _site, source_hand = task_site_transfers[0]
    from ...assembly.panda_fixed_source import declare_panda_fixed_source
    manifest = robot.asset_manifest()
    if (manifest.owner_uid != robot.uid
            or any(item.source_revision != manifest.source_revision for item in recipe.sources)):
        raise ValueError('Robot source manifest differs from the selected source recipe')
    declaration = declare_panda_fixed_source(manifest)
    declaration = derive_task_compatible_attachment(
        declaration=declaration, task_receipt=source.execution_source_receipt,
        task_hand_name=task_hand, source_hand_name=source_hand)
    fixed = declaration.attachment_plan
    arm, hand = fixed.parent_entity_id, fixed.child_entity_id
    control_plan, subject_identity, subjects = robot.compile_position_binding(
        declaration, artifact=artifact, controller=controller,
        task_closure_sha256=source.source_closure_digest)
    position = PositionSubjectControlBindingV1(control_plan, subject_identity, tuple(
        (entity, actuator, fixed.native_actuator_names[f'{entity}/{actuator}'])
        for entity, actuator, _ in control_plan.resource_writers), tuple(
        (f'{existing_robot_entity}/{name}', entity, name,
         fixed.native_joint_names[f'{entity}/{name}'], actuator)
        for entity, names, actuator_names in robot.position_source_joint_ownership(fixed)
        for name, actuator in zip(names, actuator_names, strict=True)), subjects=subjects)
    robot_sources = tuple(CompositionSourceV1(
        declaration.source_by_entity[entity].source_id, fixed.source_closure_sha256, (entity,))
        for entity in (arm, hand))
    legacy = SourceCompositionPlanV1(
        CompositionSourceV1(source.source_id, source.source_closure_digest,
                            (*task_entities, existing_robot_entity)),
        task_entities, (existing_robot_entity,), robot.uid, robot_sources, 'replace',
        declaration.assembly.logical_content_sha256, fixed.identity_hash, task_site_transfers,
        control_plan.identity_hash, subject_identity,
        task_entity_source_roots=task_body_names,
        replaced_robot_source_roots=(fixed.native_body_names[f'{arm}/{fixed.parent_root.frame_id}'],),
        task_free_joints=tuple(source.free_joints.items()),
        position_binding_identity_sha256=position.identity_hash)
    robot_bodies = ((arm, fixed.native_body_names[f'{arm}/{fixed.parent_root.frame_id}']),
                    (hand, fixed.native_body_names[f'{hand}/{fixed.child_root.frame_id}']))
    composition = CompositionRuntimeInputV1(
        legacy, declaration, tuple(name for _, name in task_body_names),
        (fixed.native_body_names[f'{arm}/{fixed.parent_root.frame_id}'],),
        (*task_body_names, *robot_bodies), tuple(source.free_joints.values()),
        control_plan, subject_identity)
    v2_robot_sources = tuple(CompositionSourceV2(item.source_id, item.closure_sha256, item.entity_ids)
                             for item in robot_sources)
    source_by_entity = declaration.source_by_entity
    edge = CompositionAttachmentV2(arm, fixed.parent_mount_site_name, hand,
        fixed.child_root.frame_id, 'fixed-transform-from-task-authored-tcp-v1',
        source_by_entity[arm].source_id, fixed.source_closure_sha256,
        source_by_entity[hand].source_id, fixed.source_closure_sha256)
    request = SourceCompositionRequestV2('source-composition-request-v2',
        CompositionSourceV2(source.source_id, source.source_closure_digest,
                             (*task_entities, existing_robot_entity)),
        task_entities, (existing_robot_entity,), robot.uid, v2_robot_sources, 'replace',
        declaration.assembly.logical_content_sha256, (edge,), tuple(control_plan.resource_writers),
        composition_intent.identity_hash)
    if set(recipe.resource_writers) != set(request.resource_writers):
        raise ValueError('resolved Panda resource writers differ from its pre-parse recipe')

    joints = dict(source.joints)
    for semantic, _entity, declared_joint, native_joint, _actuator in position.joint_native_ownership:
        if joints.get(semantic) != declared_joint:
            raise ValueError('Task joint binding differs from the declared Robot source')
        joints[semantic] = native_joint
    frames = dict(source.frames)
    for source_body, site, _target_body in task_site_transfers:
        matching = [key for key, native in frames.items() if native == site]
        if len(matching) != 1 or not matching[0].startswith(existing_robot_entity + '/'):
            raise ValueError('Task site binding does not uniquely belong to its Robot')
        frames[matching[0]] = fixed.namespace_prefix + site
    open_actuators = robot.position_open_actuators(fixed)
    if source.open_actuators != tuple(actuator for _entity, actuator in open_actuators):
        raise ValueError('Task open actuators differ from the declared Robot source')
    native_open_actuators = tuple(fixed.native_actuator_names[f'{entity}/{actuator}']
                                  for entity, actuator in open_actuators)
    return replace(source, joints=joints, frames=frames,
        open_actuators=native_open_actuators,
        composition_runtime_input=composition, position_subject_binding=position,
        source_composition_request=request, source_composition_intent=composition_intent)
