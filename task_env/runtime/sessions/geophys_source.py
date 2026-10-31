"""The only conversion of a neutral MJCF description to GeoPhys SceneSource."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

import numpy as np

from ...assembly.assets import _source_closure_digest
from ...assembly.source import TaskSceneSource
from .source import project_scene_definition_v3_to_mjcf


def native_scene_source(source: TaskSceneSource):
    from scene import SceneSource
    return SceneSource.mjcf_string(source.xml, base_dir=source.base_dir, label=source.source_id)


def source_closure_digest_for_import(imported_scene, source: TaskSceneSource, source_xml: str) -> str:
    """Digest exactly the root XML and external bytes consumed by one import."""

    if source.base_dir is None:
        if imported_scene.dependency_paths:
            raise ValueError('imported source dependencies require a bounded base_dir')
        files = {'scene.xml': source_xml.encode('utf-8')}
    else:
        base = Path(source.base_dir).resolve()
        files = {'scene.xml': source_xml.encode('utf-8')}
        for raw_path in imported_scene.dependency_paths:
            path = Path(raw_path).resolve()
            try:
                logical_path = path.relative_to(base).as_posix()
            except ValueError as exc:
                raise ValueError(f'import dependency escaped the declared source closure: {path}') from exc
            if logical_path == 'scene.xml':
                raise ValueError('scene.xml cannot also be an external importer dependency')
            files[logical_path] = path.read_bytes()
    return _source_closure_digest(files)


def _pose_matrix(pose) -> np.ndarray:
    w, x, y, z = (float(value) for value in pose.quaternion_wxyz)
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = (
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
        (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
        (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
    )
    matrix[:3, 3] = tuple(float(value) for value in pose.position)
    return matrix


def _imported_pose_matches_canonical_source(actual, expected) -> bool:
    """Compare source-derived transforms at the USD importer float precision.

    The public USD IR stores authored joint-frame values after Float32
    conversion. The tolerance is the exact per-element quantization residual
    of the canonical value plus 1e-9 for matrix composition roundoff; this is
    not a geometric fitting tolerance.
    """
    actual64 = np.asarray(actual, dtype=np.float64).reshape(4, 4)
    expected64 = np.asarray(expected, dtype=np.float64).reshape(4, 4)
    if not np.all(np.isfinite(actual64)) or not np.all(np.isfinite(expected64)):
        return False
    rounded = expected64.astype(np.float32).astype(np.float64)
    tolerance = np.abs(rounded - expected64) + 1e-9
    return bool(np.all(np.abs(actual64 - expected64) <= tolerance))


def validate_canonical_scene_import(scene_definition, imported_scene) -> dict[str, object]:
    """Fail closed unless the public ImportedScene matches the v3 projection."""

    scene_definition.validate()
    if scene_definition.schema_version != 'scene-definition-v3':
        raise ValueError('GeoPhys import mapping requires scene-definition-v3')
    bodies = {body.name: body for body in imported_scene.ir.bodies}
    if len(bodies) != len(imported_scene.ir.bodies):
        raise ValueError('GeoPhys import contains ambiguous body names')
    expected_frames = [frame for frame in scene_definition.frames or () if frame.frame_kind == 'runtime']
    expected_names = [frame.frame_id for frame in expected_frames]
    if len(set(expected_names)) != len(expected_names):
        raise ValueError('D01a projection requires globally unique native frame names')
    if set(expected_names) != set(bodies):
        missing = sorted(set(expected_names) - set(bodies))
        extra = sorted(set(bodies) - set(expected_names))
        raise ValueError(f'canonical Frame mapping mismatch: missing={missing}, extra={extra}')

    body_names_by_id = {body.body_id: body.name for body in imported_scene.ir.bodies}
    frames_by_id = {frame.node_id: frame for frame in imported_scene.ir.frames}
    joints_by_name = {
        str(joint.dynamics.get('source_name')): joint
        for joint in imported_scene.ir.joints
        if joint.dynamics.get('source_name')
    }
    canonical_dynamic: dict[str, object] = {}
    canonical_fixed = []
    for articulation in scene_definition.articulations or ():
        for joint in articulation.joints:
            if joint.kind == 'fixed':
                canonical_fixed.append((articulation.entity_id, joint))
            else:
                if joint.joint_id in canonical_dynamic:
                    raise ValueError(f'ambiguous canonical joint ID: {joint.joint_id!r}')
                canonical_dynamic[joint.joint_id] = joint
    if set(canonical_dynamic) != set(joints_by_name):
        missing = sorted(set(canonical_dynamic) - set(joints_by_name))
        extra = sorted(set(joints_by_name) - set(canonical_dynamic))
        raise ValueError(f'canonical Joint mapping mismatch: missing={missing}, extra={extra}')

    joint_rows = []
    for name, definition in sorted(canonical_dynamic.items()):
        imported = joints_by_name[name]
        parent_name = body_names_by_id.get(imported.body_a)
        child_name = body_names_by_id.get(imported.body_b)
        if (parent_name, child_name) != (
            definition.parent_frame.frame_id,
            definition.child_frame.frame_id,
        ):
            raise ValueError(f'canonical Joint endpoints do not match imported joint {name!r}')
        if not np.allclose(np.asarray(imported.axis), np.asarray(definition.axis), rtol=0.0, atol=1e-9):
            raise ValueError(f'canonical Joint axis was not consumed for {name!r}')
        if not np.allclose(
            np.asarray(imported.frame_a, dtype=np.float64).reshape(4, 4),
            _pose_matrix(definition.pose_parent_from_joint), rtol=0.0, atol=1e-8,
        ) or not np.allclose(
            np.asarray(imported.frame_b, dtype=np.float64).reshape(4, 4),
            _pose_matrix(definition.pose_child_from_joint), rtol=0.0, atol=1e-8,
        ):
            raise ValueError(f'canonical Joint frame transforms do not match import for {name!r}')
        joint_rows.append({
            'entity_id': definition.parent_frame.entity_id,
            'joint_id': name,
            'parent_frame_id': parent_name,
            'child_frame_id': child_name,
            'axis': tuple(float(value) for value in definition.axis),
            'core_disposition': 'CANONICAL_REPRESENTED',
            'provider_consumption': 'ImportedScene.ir.joints',
        })

    fixed_rows = []
    for entity_id, definition in canonical_fixed:
        parent_body = bodies.get(definition.parent_frame.frame_id)
        child_body = bodies.get(definition.child_frame.frame_id)
        if parent_body is None or child_body is None:
            raise ValueError(f'canonical fixed Joint {definition.joint_id!r} has a missing Frame')
        child_frame = frames_by_id.get(child_body.frame_id)
        if child_frame is None or child_frame.parent_id != parent_body.frame_id:
            raise ValueError(f'canonical fixed Joint {definition.joint_id!r} does not match imported frame tree')
        if not np.allclose(
            np.asarray(child_frame.local_transform, dtype=np.float64).reshape(4, 4),
            _pose_matrix(definition.pose_parent_from_joint), rtol=0.0, atol=1e-8,
        ):
            raise ValueError(f'canonical fixed Joint transform does not match import for {definition.joint_id!r}')
        fixed_rows.append({
            'entity_id': entity_id,
            'joint_id': definition.joint_id,
            'parent_frame_id': definition.parent_frame.frame_id,
            'child_frame_id': definition.child_frame.frame_id,
            'core_disposition': 'CANONICAL_REPRESENTED',
            'provider_consumption': 'ImportedScene.ir.frames',
        })

    expected_actuators = {resource.actuator_id for resource in scene_definition.actuator_resources or ()}
    imported_actuators = {
        str(actuator.parameters.get('source_name'))
        for actuator in imported_scene.ir.actuators
        if actuator.parameters.get('source_name')
    }
    if expected_actuators != imported_actuators:
        missing = sorted(expected_actuators - imported_actuators)
        extra = sorted(imported_actuators - expected_actuators)
        raise ValueError(f'canonical Actuator mapping mismatch: missing={missing}, extra={extra}')
    return {
        'schema_version': 'geochora.scene-v3-import-mapping-v1',
        'scene_identity': scene_definition.identity_hash,
        'frames': [
            {'entity_id': frame.entity_id, 'frame_id': frame.frame_id,
             'core_disposition': 'CANONICAL_REPRESENTED',
             'provider_consumption': 'ImportedScene.ir.bodies'}
            for frame in expected_frames
        ],
        'joints': joint_rows + fixed_rows,
        'actuator_resources': [
            {'actuator_id': actuator_id, 'core_disposition': 'CANONICAL_REPRESENTED',
             'provider_consumption': 'ImportedScene.ir.actuators'}
            for actuator_id in sorted(expected_actuators)
        ],
        'source_geometry_disposition': 'SOURCE_RETAINED',
        'source_inertial_disposition': 'SOURCE_RETAINED',
        'source_contact_disposition': 'SOURCE_RETAINED',
        'source_constraint_disposition': 'SOURCE_RETAINED',
        'source_transmission_disposition': 'SOURCE_RETAINED',
    }


def validate_usd_runtime_source_import(runtime_source, imported_scene) -> dict[str, object]:
    """Bind canonical USD names and authored paths to public ImportedScene IR."""
    from .source import UsdRuntimeSourceV1

    if type(runtime_source) is not UsdRuntimeSourceV1:
        raise TypeError('USD import mapping requires the exact UsdRuntimeSourceV1')
    runtime_source.validate()
    if imported_scene.ir.source_ref.format != 'usd':
        raise ValueError('USD RuntimeSource requires public USD ImportedScene input')

    scene = runtime_source.scene_definition
    runtime_frames = {
        f'{frame.entity_id}/{frame.frame_id}': frame
        for frame in (scene.frames or ()) if frame.frame_kind == 'runtime'
    }
    frame_bindings = {**dict(runtime_source.bodies), **dict(runtime_source.frames)}
    if set(frame_bindings) != set(runtime_frames):
        raise ValueError('USD source Frame bindings do not cover exact runtime Scene Frames')

    body_by_path = {
        body.source_ref.element_path: body for body in imported_scene.ir.bodies
        if body.source_ref is not None and body.source_ref.element_path
    }
    frame_by_path = {
        frame.source_ref.element_path: frame for frame in imported_scene.ir.frames
        if frame.source_ref is not None and frame.source_ref.element_path
    }

    joints_by_name = {}
    for joint in imported_scene.ir.joints:
        source_name = joint.dynamics.get('source_name')
        if source_name:
            name = str(source_name)
            if name in joints_by_name:
                raise ValueError(f'ambiguous USD Joint source name: {name!r}')
            joints_by_name[name] = joint

    scalar, floating = {}, {}
    for articulation in scene.articulations or ():
        for joint in articulation.joints:
            name = f'{articulation.entity_id}/{joint.joint_id}'
            if joint.kind in {'revolute', 'continuous', 'prismatic'}:
                scalar[name] = joint
            elif joint.kind == 'floating':
                floating[f'{joint.child_frame.entity_id}/{joint.child_frame.frame_id}'] = joint

    # A free-root parent Frame is the canonical world anchor. Some earlier
    # F04 source bindings used the child rigid-body path for both names because
    # the USD file represents the free root through RigidBodyAPI rather than a
    # separate body/Joint prim. Resolve that one alias only when public IR
    # proves an implicit world-to-body free Joint at the child's exact source
    # path; ordinary Frame/body aliases remain invalid.
    world_anchor_to_child: dict[str, str] = {}
    free_ir_by_child: dict[str, object] = {}
    scene_free_by_child = {
        child: definition
        for articulation in (scene.articulations or ())
        for definition in articulation.joints if definition.kind == 'floating'
        for child in (f'{definition.child_frame.entity_id}/{definition.child_frame.frame_id}',)
    }
    for child, definition in scene_free_by_child.items():
        parent = f'{definition.parent_frame.entity_id}/{definition.parent_frame.frame_id}'
        if parent not in frame_bindings or child not in frame_bindings:
            raise ValueError(f'USD free Joint Frame bindings are incomplete: {child!r}')
        parent_path, child_path = frame_bindings[parent], frame_bindings[child]
        if parent_path != child_path:
            continue
        child_body = body_by_path.get(child_path)
        if child_body is None:
            raise ValueError(f'USD free Joint child body is absent from public IR: {child_path!r}')
        candidates = []
        for joint in imported_scene.ir.joints:
            source_path = None if joint.source_ref is None else joint.source_ref.element_path
            source_name = str(joint.dynamics.get('source_name', ''))
            if (joint.type == 'free' and joint.body_a is None
                    and joint.body_b == child_body.body_id
                    and source_path == child_path
                    and source_name == f'{child_path}:implicit_free'
                    and bool(joint.dynamics.get('implicit'))
                    and joint.dynamics.get('source_semantic') == 'UsdPhysics.RigidBodyAPI'):
                candidates.append(joint)
        if len(candidates) != 1:
            raise ValueError(
                f'USD free-root alias lacks one public implicit world-to-body Joint: {child!r}'
            )
        if parent in world_anchor_to_child or child in world_anchor_to_child.values():
            raise ValueError('USD source contains overlapping world-anchor free-root aliases')
        world_anchor_to_child[parent] = child
        free_ir_by_child[child] = candidates[0]

    resolved_binding_paths = {
        canonical: native_path
        for canonical, native_path in frame_bindings.items()
        if canonical not in world_anchor_to_child
    }
    if len(set(resolved_binding_paths.values())) != len(resolved_binding_paths):
        raise ValueError('USD source Frame bindings alias distinct canonical runtime Frames')
    for canonical, native_path in runtime_source.bodies.items():
        if canonical in world_anchor_to_child:
            continue
        if native_path not in body_by_path:
            raise ValueError(f'USD body binding {canonical!r} is absent from public IR: {native_path!r}')
    for canonical, native_path in runtime_source.frames.items():
        if native_path not in frame_by_path:
            raise ValueError(f'USD Frame binding {canonical!r} is absent from public IR: {native_path!r}')

    if set(runtime_source.joints) != set(scalar):
        raise ValueError('USD scalar Joint map does not cover exact canonical joints')
    if len(set(runtime_source.joints.values())) != len(runtime_source.joints):
        raise ValueError('USD scalar Joint map aliases native names')
    body_by_id = {body.body_id: body for body in imported_scene.ir.bodies}
    joint_rows = []
    for canonical, definition in sorted(scalar.items()):
        native = runtime_source.joints[canonical]
        imported = joints_by_name.get(native)
        if imported is None:
            raise ValueError(f'USD scalar Joint is missing from public IR: {native!r}')
        parent = f'{definition.parent_frame.entity_id}/{definition.parent_frame.frame_id}'
        child = f'{definition.child_frame.entity_id}/{definition.child_frame.frame_id}'
        body_a, body_b = body_by_id.get(imported.body_a), body_by_id.get(imported.body_b)
        endpoints = tuple(
            None if body is None or body.source_ref is None else body.source_ref.element_path
            for body in (body_a, body_b)
        )
        if endpoints != (frame_bindings[parent], frame_bindings[child]):
            raise ValueError(f'USD Joint endpoints differ from canonical mapping: {canonical!r}')
        if not np.allclose(np.asarray(imported.axis), np.asarray(definition.axis), rtol=0.0, atol=1e-9):
            raise ValueError(f'USD Joint axis differs from canonical Scene: {canonical!r}')
        if (not _imported_pose_matches_canonical_source(
                imported.frame_a, _pose_matrix(definition.pose_parent_from_joint))
                or not _imported_pose_matches_canonical_source(
                    imported.frame_b, _pose_matrix(definition.pose_child_from_joint))):
            raise ValueError(f'USD Joint frame transforms differ from canonical Scene: {canonical!r}')
        drives = tuple(imported.dynamics.to_dict().get('usd_drives', ()))
        if not drives:
            raise ValueError(f'USD Joint has no retained authored DriveAPI facts: {canonical!r}')
        joint_rows.append({'canonical_joint': canonical, 'native_joint': native,
                           'drive_facts': tuple(dict(drive) for drive in drives)})

    if set(runtime_source.free_joints) != set(floating):
        raise ValueError('USD free Joint map does not cover exact floating Scene roots')
    free_rows = []
    for canonical_frame, _definition in sorted(floating.items()):
        native = runtime_source.free_joints[canonical_frame]
        joint = free_ir_by_child.get(canonical_frame)
        if joint is not None:
            child_path = frame_bindings[canonical_frame]
            if native != f'{child_path}/rootJoint':
                raise ValueError(f'USD implicit free Joint locator differs from the bound child root: {native!r}')
            free_rows.append({
                'canonical_frame': canonical_frame,
                'native_joint': native,
                'resolved_public_joint_name': str(joint.dynamics.get('source_name')),
                'resolved_public_source_path': str(joint.source_ref.element_path),
                'parent_frame_resolution': 'canonical_world_anchor_from_public_body_a_none',
                'joint_resolution': 'implicit_free_from_usd_rigidbody_api',
            })
            continue
        if native not in joints_by_name:
            raise ValueError(f'USD free Joint name is absent from public IR: {native!r}')
        free_rows.append({'canonical_frame': canonical_frame, 'native_joint': native,
                          'parent_frame_resolution': 'explicit_public_joint_endpoints'})
    if set(runtime_source.joint_targets) != set(scalar):
        raise ValueError('USD Position-target map does not cover exact scalar Scene joints')
    return {
        'schema_version': 'geophys.usd-runtime-source-import-v1',
        'source_id': runtime_source.source_id,
        'scene_identity_sha256': scene.identity_hash,
        'delivery_sha256': runtime_source.scene_source.loaded_delivery.delivery_sha256,
        'closure_sha256': runtime_source.source_closure_digest,
        'runtime_frame_count': len(frame_bindings),
        'scalar_joints': joint_rows,
        'floating_joints': free_rows,
        'geometry_disposition': 'public_imported_ir_retained',
    }


def inspect_usd_position_drive_model(runtime_source, imported_scene, scene_model) -> dict[str, object]:
    """Inspect, without stepping, source drives bound to compiled public channels.

    This proves a model-bound affine command equation. It is not itself a
    RuntimeSession adapter or production admission decision.
    """
    from .source import UsdRuntimeSourceV1

    if type(runtime_source) is not UsdRuntimeSourceV1:
        raise TypeError('drive inspection requires the exact UsdRuntimeSourceV1')
    runtime_source.validate()
    data = scene_model.joint_data
    actuator_by_name = data.get('name_to_actuator')
    joint_by_name = data.get('name_to_joint')
    if not isinstance(actuator_by_name, dict) or not isinstance(joint_by_name, dict):
        raise ValueError('public rigid model must expose named joint and actuator metadata')
    metadata = imported_scene.ir.metadata
    length_unit_m = float(metadata.length_unit_m)
    mass_unit_kg = float(metadata.mass_unit_kg)
    if not all(np.isfinite(value) and value > 0 for value in (length_unit_m, mass_unit_kg)):
        raise ValueError('USD stage length and mass units must be finite and positive')
    joints_by_name = {
        str(joint.dynamics.get('source_name')): joint
        for joint in imported_scene.ir.joints
        if joint.dynamics.get('source_name')
    }
    actuator_trnid = np.asarray(data['actuator_trnid'])
    if actuator_trnid.ndim == 1:
        actuator_target_ids = actuator_trnid.reshape(-1)
    elif actuator_trnid.ndim == 2 and actuator_trnid.shape[1] >= 1:
        actuator_target_ids = actuator_trnid[:, 0].reshape(-1)
    else:
        raise ValueError('public model actuator_trnid has an unsupported shape')
    gain = np.asarray(data['actuator_gainprm'], dtype=np.float64)
    bias = np.asarray(data['actuator_biasprm'], dtype=np.float64)
    force_range = np.asarray(data['actuator_forcerange'], dtype=np.float64).reshape(-1, 2)
    force_limited = np.asarray(data['actuator_forcelimited'], dtype=np.bool_).reshape(-1)
    acceleration = np.asarray(data['actuator_acceleration'], dtype=np.bool_).reshape(-1)
    ctrl_range = np.asarray(data['actuator_ctrlrange'], dtype=np.float64).reshape(-1, 2)
    ctrl_limited = np.asarray(data['actuator_ctrllimited'], dtype=np.bool_).reshape(-1)
    joint_qpos = np.asarray(data['jnt_qposadr'], dtype=np.int64).reshape(-1)
    qpos0 = np.asarray(data['qpos0'], dtype=np.float64).reshape(-1)
    rows = []
    for canonical, native in sorted(runtime_source.joint_targets.items()):
        imported = joints_by_name.get(native)
        if imported is None:
            raise ValueError(f'Position target Joint is absent from public IR: {native!r}')
        drives = tuple(imported.dynamics.to_dict().get('usd_drives', ()))
        if len(drives) != 1:
            raise ValueError(f'Position target requires exactly one authored scalar drive: {canonical!r}')
        drive = drives[0]
        axis = str(drive['axis'])
        joint_type = str(imported.type)
        expected_axis = 'angular' if joint_type == 'revolute' else 'linear' if joint_type == 'prismatic' else None
        if axis != expected_axis:
            raise ValueError(f'USD drive axis does not match scalar Joint type: {canonical!r}')
        if drive['type'] != 'force':
            raise ValueError(f'GeoPhys Position target mapping does not admit {drive["type"]!r} drive semantics')
        actuator_name = f'{native}:usd_drive:{axis}'
        if actuator_name not in actuator_by_name or native not in joint_by_name:
            raise ValueError(f'public model lacks named source drive channel: {actuator_name!r}')
        actuator_index = int(actuator_by_name[actuator_name])
        joint_index = int(joint_by_name[native])
        if not 0 <= actuator_index < len(actuator_target_ids) or not 0 <= joint_index < len(joint_qpos):
            raise ValueError(f'public model named index is outside its compiled array: {canonical!r}')
        if int(actuator_target_ids[actuator_index]) != joint_index:
            raise ValueError(f'USD drive actuator transmission does not target its named Joint: {canonical!r}')

        angular = axis == 'angular'
        coordinate_scale = np.pi / 180.0 if angular else length_unit_m
        effort_scale = mass_unit_kg * length_unit_m ** (2 if angular else 1)
        gain_scale = effort_scale / coordinate_scale
        expected_k = float(drive['stiffness']) * gain_scale
        expected_d = float(drive['damping']) * gain_scale
        row_gain = gain[actuator_index]
        row_bias = bias[actuator_index]
        if row_gain.shape[0] < 1 or not np.isclose(row_gain[0], 1.0, rtol=0.0, atol=1e-7):
            raise ValueError(f'USD position mapping requires the public fixed unit actuator gain: {canonical!r}')
        if not np.isclose(-row_bias[1], expected_k, rtol=1e-5, atol=1e-5):
            raise ValueError(f'USD DriveAPI stiffness unit conversion differs in public model: {canonical!r}')
        if not np.isclose(-row_bias[2], expected_d, rtol=1e-5, atol=1e-5):
            raise ValueError(f'USD DriveAPI damping unit conversion differs in public model: {canonical!r}')
        expected_bias0 = expected_k * float(drive['target_position']) * coordinate_scale
        expected_bias0 += expected_d * float(drive['target_velocity']) * coordinate_scale
        if not np.isclose(row_bias[0], expected_bias0, rtol=1e-5, atol=1e-5):
            raise ValueError(f'USD source target offset is not represented by this Position mapping: {canonical!r}')
        source_cap = drive['max_force']
        expected_cap = None if source_cap is None else float(source_cap) * effort_scale
        if expected_cap is None:
            if force_limited[actuator_index]:
                raise ValueError(f'compiled USD drive added an unsupported force cap: {canonical!r}')
        elif (not force_limited[actuator_index]
              or not np.allclose(force_range[actuator_index], (-expected_cap, expected_cap), rtol=1e-5, atol=1e-5)):
            raise ValueError(f'compiled USD drive force cap differs from authored DriveAPI: {canonical!r}')
        if acceleration[actuator_index]:
            raise ValueError(f'compiled model classifies a force drive as acceleration: {canonical!r}')
        q0 = float(qpos0[int(joint_qpos[joint_index])])
        # The compiled affine law is f = gain*ctrl + b0 - k*q - d*qd.
        # Therefore this input holds the compiled q0 with zero joint velocity.
        hold_input = (expected_k * q0 - float(row_bias[0])) / float(row_gain[0])
        if ctrl_limited[actuator_index] and not (
            float(ctrl_range[actuator_index, 0]) <= hold_input <= float(ctrl_range[actuator_index, 1])
        ):
            raise ValueError(f'model-bound Position hold command exceeds native ctrl range: {canonical!r}')
        rows.append({
            'canonical_joint': canonical,
            'native_joint': native,
            'native_actuator': actuator_name,
            'native_actuator_index': actuator_index,
            'native_joint_index': joint_index,
            'position_unit': 'radian' if angular else 'meter',
            'source_drive_type': drive['type'],
            'source_target_position': float(drive['target_position']),
            'source_target_velocity': float(drive['target_velocity']),
            'source_stiffness': float(drive['stiffness']),
            'source_damping': float(drive['damping']),
            'length_unit_m': length_unit_m,
            'mass_unit_kg': mass_unit_kg,
            'coordinate_scale': float(coordinate_scale),
            'effort_scale': float(effort_scale),
            'compiled_gain': tuple(float(value) for value in row_gain),
            'compiled_bias': tuple(float(value) for value in row_bias),
            'compiled_force_range': tuple(float(value) for value in force_range[actuator_index]),
            'compiled_force_limited': bool(force_limited[actuator_index]),
            'compiled_ctrl_range': tuple(float(value) for value in ctrl_range[actuator_index]),
            'compiled_ctrl_limited': bool(ctrl_limited[actuator_index]),
            'joint_q0': q0,
            'hold_input': hold_input,
            'hold_input_unit': 'N*m' if angular else 'N',
            'control_mapping': 'ctrl=(k*q_target + d*qdot_target - bias0)/gain; source force cap remains model-owned',
        })
    return {
        'schema_version': 'geophys.usd-position-drive-model-inspection-v1',
        'source_id': runtime_source.source_id,
        'source_closure_sha256': runtime_source.source_closure_digest,
        'public_model_n_actuators': int(data.get('n_actuators', len(actuator_target_ids))),
        'rows': rows,
    }


def _usd_ir_semantic_hash_for_snapshot(imported_scene, runtime_source):
    """Hash imported USD semantics without lease-specific temporary paths.

    OpenUSD SourceRef URIs point into the owned snapshot directory.  That
    directory is intentionally fresh for each lease, so hashing the raw IR
    would make the same immutable delivery produce a different model receipt
    on every reset.  Replace only those owned-snapshot URI roots with a
    closure-qualified URI; retain each relative dependency path and prim path.
    """
    from pathlib import Path, PurePosixPath
    import hashlib
    import json

    from .source import UsdRuntimeSourceV1

    if type(runtime_source) is not UsdRuntimeSourceV1:
        raise TypeError('stable USD IR identity requires exact UsdRuntimeSourceV1')
    entry = PurePosixPath(runtime_source.scene_source.loaded_delivery.delivery.entry_file)
    source_path = Path(imported_scene.source.path).resolve(strict=False)
    snapshot_root = source_path
    for _part in entry.parts:
        snapshot_root = snapshot_root.parent
    if snapshot_root == source_path:
        raise ValueError('USD snapshot entry path must be relative and nonempty')
    snapshot_root = snapshot_root.resolve(strict=False)

    def normalize_snapshot_uri(value, *, required=False):
        path_text, marker, suffix = value.partition('#')
        path = Path(path_text).resolve(strict=False)
        try:
            relative = path.relative_to(snapshot_root)
        except ValueError as error:
            if required:
                raise ValueError('USD IR SourceRef escapes its owned snapshot closure') from error
            return value
        if not relative.parts:
            raise ValueError('USD IR URI cannot name the snapshot directory')
        normalized = f"usd-closure://{runtime_source.source_closure_digest}/{relative.as_posix()}"
        return normalized + (marker + suffix if marker else '')

    def normalize(value):
        if isinstance(value, dict):
            result = {key: normalize(item) for key, item in value.items()}
            if {'uri', 'element_path', 'format'} <= set(value):
                uri = value['uri']
                if type(uri) is not str:
                    raise TypeError('USD IR SourceRef URI must be a string')
                result['uri'] = normalize_snapshot_uri(uri, required=True)
            return result
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, str):
            return normalize_snapshot_uri(value)
        return value

    payload = normalize(imported_scene.ir.to_dict())
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
        allow_nan=False,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def compile_geophys_usd_position_drive_receipt(
    runtime_source, imported_scene, scene_model, execution, *,
    provider_build_identity: str, provenance_kind: str = 'synthetic_fixture',
    host_model_producer_identity=None,
    writer_id: str = 'panda-main/position-servo-v1',
):
    """Freeze public GeoPhys USD model channels into the existing drive owner.

    The receipt is model-bound and can be used by a low-level adapter to map
    canonical position targets into the public affine force-drive controls.
    Compiling it does not initialize a solver or admit production execution.
    """
    from ...artifacts import ExecutionSpecV1, JointReference
    from .leaf_control import (
        GeoPhysHostModelProducerIdentityV1,
        GeoPhysUsdPositionDriveReceiptV1, GeoPhysUsdPositionDriveV1,
    )

    if type(execution) is not ExecutionSpecV1:
        raise TypeError('GeoPhys USD drive receipt requires exact ExecutionSpecV1')
    execution.validate()
    if execution.physics_provider != 'geophys':
        raise ValueError('GeoPhys USD drive receipt requires a GeoPhys ExecutionSpec')
    if type(provider_build_identity) is not str or not provider_build_identity.startswith('geophys-'):
        raise ValueError('GeoPhys USD drive receipt requires an exact provider build identity')
    if provenance_kind not in {'synthetic_fixture', 'native_runtime'}:
        raise ValueError('GeoPhys USD drive receipt provenance must be explicit')
    if host_model_producer_identity is not None:
        if type(host_model_producer_identity) is not GeoPhysHostModelProducerIdentityV1:
            raise TypeError('GeoPhys host-model receipt requires its exact producer identity contract')
        expected_provider_build = (
            host_model_producer_identity.actual_provider_build_identity
            if provenance_kind == 'native_runtime'
            else host_model_producer_identity.requested_target_build_identity
        )
        if expected_provider_build != provider_build_identity:
            raise ValueError('GeoPhys receipt build identity differs from its requested target or actual producer identity')
        host_model_producer_identity.validate_current_tree()
    runtime_source.validate()
    if runtime_source.scene_source.representation.provider != 'geophys':
        raise ValueError('GeoPhys USD drive receipt requires a GeoPhys representation')

    report = inspect_usd_position_drive_model(runtime_source, imported_scene, scene_model)
    data = scene_model.joint_data
    joint_by_name = dict(data['name_to_joint'])
    actuator_by_name = dict(data['name_to_actuator'])
    model_payload = {
        'semantic_hash': _usd_ir_semantic_hash_for_snapshot(imported_scene, runtime_source),
        'source_graph_hash': imported_scene.source_graph_hash,
        'provider_build_identity': provider_build_identity,
        'name_to_joint': sorted((str(name), int(index)) for name, index in joint_by_name.items()),
        'name_to_actuator': sorted((str(name), int(index)) for name, index in actuator_by_name.items()),
    }
    if host_model_producer_identity is not None:
        model_payload['host_model_producer_identity_sha256'] = host_model_producer_identity.identity_sha256
    for key in (
        'n_dof', 'n_qpos', 'n_actuators', 'n_bodies', 'n_geoms',
        'qpos0', 'jnt_qposadr', 'jnt_dofadr', 'jnt_type',
        'actuator_trnid', 'actuator_gainprm', 'actuator_biasprm',
        'actuator_forcerange', 'actuator_forcelimited',
        'actuator_ctrlrange', 'actuator_ctrllimited',
    ):
        value = data.get(key)
        if value is not None:
            model_payload[key] = np.asarray(value).tolist()
    public_model_identity = hashlib.sha256(json.dumps(
        model_payload, sort_keys=True, separators=(',', ':'), allow_nan=False,
    ).encode()).hexdigest()
    limits_by_name = {}
    joints_by_name = {
        str(joint.dynamics.get('source_name')): joint
        for joint in imported_scene.ir.joints if joint.dynamics.get('source_name')
    }
    for canonical, native in runtime_source.joints.items():
        joint = joints_by_name.get(native)
        if joint is None:
            raise ValueError(f'GeoPhys USD target Joint is absent from public IR: {native!r}')
        joint_limits = joint.limits.to_dict()
        if not bool(joint_limits.get('enabled')):
            raise ValueError(f'GeoPhys USD target requires bounded public joint limits: {native!r}')
        if joint_limits.get('unit') not in {'radian', 'meter'}:
            raise ValueError(f'GeoPhys USD target has unsupported native coordinate unit: {native!r}')
        lo, hi = float(joint_limits.get('lower')), float(joint_limits.get('upper'))
        if not np.isfinite((lo, hi)).all() or lo >= hi:
            raise ValueError(f'GeoPhys USD target limits are not finite/increasing: {native!r}')
        expected_unit = 'meter' if canonical.endswith(('finger_joint1', 'finger_joint2')) else 'radian'
        if joint_limits.get('unit') != expected_unit:
            raise ValueError(f'GeoPhys USD target unit differs from canonical Joint: {canonical!r}')
        limits_by_name[native] = (lo, hi)

    rows_by_name = {row['native_joint']: row for row in report['rows']}
    dof_order = tuple(sorted(runtime_source.joints.values(), key=lambda name: int(joint_by_name[name])))
    if set(dof_order) != set(runtime_source.joints.values()):
        raise ValueError('GeoPhys public named scalar joint map is incomplete')
    dof_index_by_name = {name: index for index, name in enumerate(dof_order)}
    drives = []
    for canonical, native in sorted(runtime_source.joint_targets.items()):
        row = rows_by_name.get(native)
        joint = joints_by_name.get(native)
        if row is None or joint is None:
            raise ValueError(f'GeoPhys model-bound drive row is missing: {canonical!r}')
        q_index = int(joint_by_name[native])
        actuator_index = int(actuator_by_name[row['native_actuator']])
        qpos_address = int(np.asarray(data['jnt_qposadr']).reshape(-1)[q_index])
        q0 = float(np.asarray(data['qpos0'], dtype=np.float64).reshape(-1)[qpos_address])
        if not np.isfinite(q0):
            raise ValueError(f'GeoPhys model q0 is non-finite: {canonical!r}')
        # The Scene contract defines this Panda source's joint coordinates at
        # the authored zero; nonzero imported q0 has no separate canonical
        # offset declaration and therefore cannot be silently reinterpreted.
        if abs(q0) > 1e-9:
            raise ValueError(f'GeoPhys source q0 requires an explicit canonical coordinate offset: {canonical!r}')
        bias = tuple(float(value) for value in row['compiled_bias'])
        gain = tuple(float(value) for value in row['compiled_gain'])
        force_range = tuple(float(value) for value in row['compiled_force_range'])
        ctrl_range = tuple(float(value) for value in row['compiled_ctrl_range'])
        coordinate_scale = float(row['coordinate_scale'])
        drives.append(GeoPhysUsdPositionDriveV1(
            'geophys-usd-position-drive-v1', JointReference('panda-main', canonical.split('/', 1)[1]),
            native, dof_index_by_name[native], row['native_actuator'], actuator_index,
            row['position_unit'], *limits_by_name[native], float(gain[0]), float(bias[0]),
            float(-bias[1]), float(-bias[2]),
            float(row['source_target_velocity']) * coordinate_scale,
            0.0, q0, bool(row['compiled_ctrl_limited']), *ctrl_range,
            bool(row['compiled_force_limited']), *force_range,
        ))
    if tuple(name for name in dof_order) != tuple(
        row.native_dof_name for row in sorted(drives, key=lambda item: item.native_dof_index)
    ):
        raise ValueError('GeoPhys drive receipt DOF order differs from public model joint indices')
    return GeoPhysUsdPositionDriveReceiptV1(
        'geophys-usd-position-drive-receipt-v1', provenance_kind,
        runtime_source.scene_definition.identity_hash,
        runtime_source.source_closure_digest, public_model_identity, execution.identity_hash,
        provider_build_identity, execution.physics_profile, execution.physics_backend,
        str(execution.physics_device or execution.physics_backend), execution.determinism_mode,
        runtime_source.task_artifact.timebase.physics_dt,
        runtime_source.task_artifact.timebase.control_substeps, writer_id, 9,
        tuple(sorted(drives, key=lambda item: item.native_dof_index)),
        None if host_model_producer_identity is None else host_model_producer_identity.identity_sha256,
    )


def compile_geophys_usd_source_actuation_receipt_v2(
    runtime_source, imported_scene, scene_model, execution, *,
    provider_build_identity: str, provenance_kind: str = 'synthetic_fixture',
    host_model_producer_identity=None,
    writer_id: str = 'panda-main/source-actuation-v2',
):
    """Compile the source-authored seven-joint/one-tendon Panda channel map.

    This additive receipt keeps nine canonical scalar Position targets while
    binding the two fingers to one shared tendon actuator. It does not change
    the legacy one-actuator-per-DOF receipt contract.
    """
    from ...artifacts import ExecutionSpecV1, JointReference
    from .leaf_control import (
        GeoPhysHostModelProducerIdentityV1,
        GeoPhysUsdPositionDriveV1,
        GeoPhysUsdSourceActuationReceiptV2,
    )
    from .source import UsdRuntimeSourceV1

    if type(execution) is not ExecutionSpecV1 or type(runtime_source) is not UsdRuntimeSourceV1:
        raise TypeError('source-actuation receipt requires exact ExecutionSpecV1 and UsdRuntimeSourceV1')
    execution.validate(); runtime_source.validate()
    if execution.physics_provider != 'geophys' or imported_scene.format != 'usd':
        raise ValueError('source-actuation receipt requires the public GeoPhys USD route')
    if (type(provider_build_identity) is not str or not provider_build_identity.startswith('geophys-')
            or provenance_kind not in {'synthetic_fixture', 'native_runtime'}):
        raise ValueError('source-actuation receipt requires explicit provider/provenance identities')
    if host_model_producer_identity is not None:
        if type(host_model_producer_identity) is not GeoPhysHostModelProducerIdentityV1:
            raise TypeError('source-actuation producer identity has the wrong versioned type')
        expected_build = (host_model_producer_identity.actual_provider_build_identity
                          if provenance_kind == 'native_runtime'
                          else host_model_producer_identity.requested_target_build_identity)
        if expected_build != provider_build_identity:
            raise ValueError('source-actuation receipt differs from requested/actual provider build identity')
        host_model_producer_identity.validate_current_tree()

    data = scene_model.joint_data
    names_to_joint = data.get('name_to_joint')
    names_to_actuator = data.get('name_to_actuator')
    if (not isinstance(names_to_joint, dict) or not isinstance(names_to_actuator, dict)
            or int(data.get('n_dof', -1)) != 15 or int(data.get('n_actuators', -1)) != 8
            or int(data.get('n_tendons', -1)) != 1):
        raise ValueError('DG02 public model must expose the exact 15-DOF/8-actuator/1-tendon source counts')
    expected_joints = {
        **{f'panda-main/joint{i}': f'joint{i}' for i in range(1, 8)},
        'panda-main/finger_joint1': 'finger_joint1',
        'panda-main/finger_joint2': 'finger_joint2',
    }
    if dict(runtime_source.joints) != expected_joints or dict(runtime_source.joint_targets) != expected_joints:
        raise ValueError('DG02 source must bind all seven arm and two finger target joints by source name')

    joint_by_name = {
        str(row.dynamics.get('source_name')): row for row in imported_scene.ir.joints
        if row.dynamics.get('source_name')
    }
    actuator_by_source = {}
    for row in imported_scene.ir.actuators:
        parameters = row.parameters.to_dict()
        source_name = parameters.get('source_name')
        if type(source_name) is not str or source_name in actuator_by_source:
            raise ValueError('DG02 public IR has missing or ambiguous actuator source names')
        actuator_by_source[source_name] = (row, parameters, row.limits.to_dict())
    if set(actuator_by_source) != {f'actuator{i}' for i in range(1, 9)}:
        raise ValueError('DG02 public IR must expose exactly source actuator1 through actuator8')
    source_extensions = [row for row in imported_scene.ir.extensions
                         if row.namespace == 'GeoChora.F05SourceSemantics'
                         and row.schema_version == '1']
    if len(source_extensions) != 1:
        raise ValueError('DG02 public IR must expose exactly one versioned F05 source-identity block')
    source_identity = source_extensions[0].payload.to_dict().get('source_identity', {})
    if source_identity != {
            'family': 'menagerie-panda',
            'revision': 'b846dd12bc459d776cccb3dee0b1d02acbf7a9c7',
            'source_closure_sha256': 'a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a',
            'original_mjcf_sha256': '96ad67da03710f17f798c9478fd9e9efdf24a3bf8359f05e456dd9fb158ea273',
    }:
        raise ValueError('DG02 USD semantics do not bind the frozen original Menagerie source identity')

    gain = np.asarray(data['actuator_gainprm'], dtype=np.float64)
    bias = np.asarray(data['actuator_biasprm'], dtype=np.float64)
    force_range = np.asarray(data['actuator_forcerange'], dtype=np.float64).reshape(-1, 2)
    force_limited = np.asarray(data['actuator_forcelimited'], dtype=np.bool_).reshape(-1)
    ctrl_range = np.asarray(data['actuator_ctrlrange'], dtype=np.float64).reshape(-1, 2)
    ctrl_limited = np.asarray(data['actuator_ctrllimited'], dtype=np.bool_).reshape(-1)
    trnid = np.asarray(data['actuator_trnid'], dtype=np.int64)
    if trnid.ndim == 1:
        trnid = trnid.reshape(-1, 1)
    qadr = np.asarray(data['jnt_qposadr'], dtype=np.int64).reshape(-1)
    qpos0 = np.asarray(data['qpos0'], dtype=np.float64).reshape(-1)
    dof_order = tuple(sorted(runtime_source.joints.values(), key=lambda name: int(names_to_joint[name])))
    dof_index = {name: index for index, name in enumerate(dof_order)}
    rows = []

    def compiled_row(source_actuator_name, target_joint_name, canonical):
        desc, params, limits = actuator_by_source[source_actuator_name]
        if desc.target_kind != 'joint' or params.get('source_target') != target_joint_name:
            raise ValueError(f'{source_actuator_name} does not source-bind {target_joint_name}')
        if (params.get('gain_type') != 'fixed' or params.get('bias_type') != 'affine'
                or params.get('dyn_type') != 'none'):
            raise ValueError(f'{source_actuator_name} uses an unsupported source actuator law')
        if target_joint_name not in names_to_joint or source_actuator_name not in names_to_actuator:
            raise ValueError(f'public model misses source Joint/Actuator {target_joint_name}/{source_actuator_name}')
        ji, ai = int(names_to_joint[target_joint_name]), int(names_to_actuator[source_actuator_name])
        if int(trnid[ai, 0]) != ji:
            raise ValueError(f'{source_actuator_name} transmission does not target its source Joint')
        expected_gain = np.asarray(params['gain_prm'], dtype=np.float64)
        expected_bias = np.asarray(params['bias_prm'], dtype=np.float64)
        if (not np.allclose(gain[ai, :len(expected_gain)], expected_gain, rtol=0, atol=1e-7)
                or not np.allclose(bias[ai, :len(expected_bias)], expected_bias, rtol=0, atol=1e-7)):
            raise ValueError(f'{source_actuator_name} compiled affine law differs from public IR source parameters')
        fr = tuple(float(value) for value in force_range[ai])
        cr = tuple(float(value) for value in ctrl_range[ai])
        if (bool(force_limited[ai]) != bool(limits['force_limited'])
                or bool(ctrl_limited[ai]) != bool(limits['ctrl_limited'])
                or not np.allclose(fr, limits['force_range'], rtol=0, atol=1e-7)
                or not np.allclose(cr, limits['ctrl_range'], rtol=0, atol=1e-7)):
            raise ValueError(f'{source_actuator_name} compiled control/force limits differ from public IR')
        joint = joint_by_name[target_joint_name]
        joint_limits = joint.limits.to_dict()
        if not joint_limits.get('enabled') or joint_limits.get('unit') not in {'radian', 'meter'}:
            raise ValueError(f'{target_joint_name} lacks finite source-coordinate limits')
        lo, hi = float(joint_limits['lower']), float(joint_limits['upper'])
        q0 = float(qpos0[int(qadr[ji])])
        if not np.isfinite((lo, hi, q0)).all() or lo >= hi or abs(q0) > 1e-9:
            raise ValueError(f'{target_joint_name} source limits or q0 are not representable')
        compiled_gain = gain[ai]
        compiled_bias = bias[ai]
        if len(compiled_gain) < 1 or abs(float(compiled_gain[0])) < 1e-12:
            raise ValueError(f'{source_actuator_name} has no invertible compiled affine gain')
        return GeoPhysUsdPositionDriveV1(
            'geophys-usd-position-drive-v1',
            JointReference('panda-main', canonical.split('/', 1)[1]),
            target_joint_name, dof_index[target_joint_name], source_actuator_name, ai,
            str(joint_limits['unit']), lo, hi, float(compiled_gain[0]), float(compiled_bias[0]),
            float(-compiled_bias[1]), float(-compiled_bias[2]), 0.0, 0.0, q0,
            bool(ctrl_limited[ai]), *cr, bool(force_limited[ai]), *fr,
        )

    for index in range(1, 8):
        canonical = f'panda-main/joint{index}'
        rows.append(compiled_row(f'actuator{index}', f'joint{index}', canonical))

    tendon_desc, tendon_params, tendon_limits = actuator_by_source['actuator8']
    if tendon_desc.target_kind != 'tendon' or tendon_params.get('source_target') != 'split':
        raise ValueError('actuator8 must target the authored split fixed tendon')
    if (tendon_params.get('gain_type') != 'fixed' or tendon_params.get('bias_type') != 'affine'
            or tendon_params.get('dyn_type') != 'none'):
        raise ValueError('actuator8 uses an unsupported source tendon-actuator law')
    tendon_constraints = [row for row in imported_scene.ir.constraints
                          if row.kind == 'tendon' and row.parameters.get('source_name') == 'split']
    if len(tendon_constraints) != 1:
        raise ValueError('public IR must expose exactly one source split fixed tendon')
    wraps = tendon_constraints[0].parameters.to_dict().get('wraps', ())
    wrap_map = {str(row['target']): float(row.get('divisor', row.get('coefficient'))) for row in wraps}
    tendon_parameters = tendon_constraints[0].parameters.to_dict()
    if (len(wraps) != 2 or wrap_map != {'finger_joint1': 0.5, 'finger_joint2': 0.5}
            or tendon_parameters.get('stiffness') != 0.0
            or tendon_parameters.get('damping') != 0.0
            or tendon_parameters.get('friction_loss') != 0.0
            or tendon_parameters.get('limited') is not False
            or tuple(tendon_parameters.get('range', ())) != (0.0, 0.0)
            or tendon_parameters.get('margin') != 0.0):
        raise ValueError('public split tendon Jacobian differs from the source 0.5/0.5 wrap coefficients')
    transmissions = [row for row in imported_scene.ir.transmissions
                     if tendon_desc.actuator_id in row.actuator_ids]
    if (len(transmissions) != 1
            or len(transmissions[0].joint_ids) != 2
            or transmissions[0].mapping.get('target_kind') != 'tendon'
            or transmissions[0].mapping.get('source_target') != 'split'):
        raise ValueError('public source tendon Actuator must map through one two-joint fixed-tendon transmission')
    actuator8_index = int(names_to_actuator['actuator8'])
    if not 0 <= actuator8_index < len(trnid) or not 0 <= int(trnid[actuator8_index, 0]) < 1:
        raise ValueError('public model actuator8 does not target the exact compiled source tendon')
    params = tendon_params
    expected_gain = np.asarray(params['gain_prm'], dtype=np.float64)
    expected_bias = np.asarray(params['bias_prm'], dtype=np.float64)
    if (not np.allclose(gain[actuator8_index, :len(expected_gain)], expected_gain, rtol=0, atol=1e-7)
            or not np.allclose(bias[actuator8_index, :len(expected_bias)], expected_bias, rtol=0, atol=1e-7)
            or bool(force_limited[actuator8_index]) != bool(tendon_limits['force_limited'])
            or bool(ctrl_limited[actuator8_index]) != bool(tendon_limits['ctrl_limited'])
            or not np.allclose(force_range[actuator8_index], tendon_limits['force_range'], rtol=0, atol=1e-7)
            or not np.allclose(ctrl_range[actuator8_index], tendon_limits['ctrl_range'], rtol=0, atol=1e-7)):
        raise ValueError('actuator8 compiled affine law or force/ctrl caps differ from source IR')
    for target_joint, canonical in (
        ('finger_joint1', 'panda-main/finger_joint1'),
        ('finger_joint2', 'panda-main/finger_joint2'),
    ):
        joint = joint_by_name[target_joint]
        limits = joint.limits.to_dict()
        ji = int(names_to_joint[target_joint]); q0 = float(qpos0[int(qadr[ji])])
        if not limits.get('enabled') or limits.get('unit') != 'meter' or abs(q0) > 1e-9:
            raise ValueError(f'{target_joint} source limits/q0 differ from the Panda meter-coordinate contract')
        rows.append(GeoPhysUsdPositionDriveV1(
            'geophys-usd-position-drive-v1', JointReference('panda-main', canonical.split('/', 1)[1]),
            target_joint, dof_index[target_joint], 'actuator8', actuator8_index, 'meter',
            float(limits['lower']), float(limits['upper']), float(gain[actuator8_index, 0]),
            float(bias[actuator8_index, 0]), float(-bias[actuator8_index, 1]),
            float(-bias[actuator8_index, 2]), 0.0, 0.0, q0,
            bool(ctrl_limited[actuator8_index]), *tuple(float(x) for x in ctrl_range[actuator8_index]),
            bool(force_limited[actuator8_index]), *tuple(float(x) for x in force_range[actuator8_index]),
        ))

    equality = [row for row in imported_scene.ir.constraints
                if row.kind == 'joint' and row.parameters.get('constraint_role') == 'equality'
                and row.parameters.get('source_name') == 'finger_joint1_finger_joint2']
    if len(equality) != 1:
        raise ValueError('public IR must expose the active source finger equality')
    equality_params = equality[0].parameters.to_dict()
    if (equality_params.get('active') is not True
            or equality_params.get('source_target1') != 'finger_joint1'
            or equality_params.get('source_target2') != 'finger_joint2'
            or tuple(equality_params.get('poly_coef', ())) != (0.0, 1.0, 0.0, 0.0, 0.0)
            or tuple(equality_params.get('solref', ())) != (0.005, 1.0)
            or tuple(equality_params.get('solimp', ())) != (0.95, 0.99, 0.001)):
        raise ValueError('public source finger equality targets or active state differ')

    model_payload = {
        'semantic_hash': _usd_ir_semantic_hash_for_snapshot(imported_scene, runtime_source),
        'source_graph_hash': imported_scene.source_graph_hash,
        'provider_build_identity': provider_build_identity,
        'name_to_joint': sorted((str(name), int(index)) for name, index in names_to_joint.items()),
        'name_to_actuator': sorted((str(name), int(index)) for name, index in names_to_actuator.items()),
    }
    for key in ('n_dof', 'n_qpos', 'n_actuators', 'n_bodies', 'n_geoms', 'n_tendons',
                'qpos0', 'jnt_qposadr', 'jnt_dofadr', 'jnt_type', 'actuator_trnid',
                'actuator_gainprm', 'actuator_biasprm', 'actuator_forcerange',
                'actuator_forcelimited', 'actuator_ctrlrange', 'actuator_ctrllimited'):
        value = data.get(key)
        if value is not None:
            model_payload[key] = np.asarray(value).tolist()
    if host_model_producer_identity is not None:
        model_payload['host_model_producer_identity_sha256'] = host_model_producer_identity.identity_sha256
    model_identity = hashlib.sha256(json.dumps(
        model_payload, sort_keys=True, separators=(',', ':'), allow_nan=False,
    ).encode()).hexdigest()
    return GeoPhysUsdSourceActuationReceiptV2(
        'geophys-usd-source-actuation-receipt-v2', provenance_kind,
        runtime_source.scene_definition.identity_hash, runtime_source.source_closure_digest,
        model_identity, execution.identity_hash, provider_build_identity,
        execution.physics_profile, execution.physics_backend,
        str(execution.physics_device or execution.physics_backend), execution.determinism_mode,
        runtime_source.task_artifact.timebase.physics_dt,
        runtime_source.task_artifact.timebase.control_substeps, writer_id, 9,
        tuple(sorted(rows, key=lambda row: row.native_dof_index)), 'split',
        ('finger_joint1', 'finger_joint2'), (0.5, 0.5),
        'finger_joint1_finger_joint2', tuple(float(x) for x in equality_params['solref']),
        tuple(float(x) for x in equality_params['solimp']),
        None if host_model_producer_identity is None else host_model_producer_identity.identity_sha256,
    )


class GeoPhysSourceComposer:
    adapter_name = 'task_env_neutral_mjcf_bridge_v0'

    def __init__(self, source, *, scene_definition=None, source_closure_digest=None):
        from .source import UsdRuntimeSourceV1

        self._source = source
        self._usd_runtime_source = source if type(source) is UsdRuntimeSourceV1 else None
        self._snapshot_lease = None
        self._usd_mapping_report = None
        self._scene_definition = scene_definition
        self._source_closure_digest = source_closure_digest
        self._projected_xml = None
        if self._usd_runtime_source is not None:
            source.validate()
            if scene_definition is not None and scene_definition.identity_hash != source.scene_definition.identity_hash:
                raise ValueError('composer Scene differs from versioned USD RuntimeSource')
            if source_closure_digest is not None and source_closure_digest != source.source_closure_digest:
                raise ValueError('composer closure differs from versioned USD RuntimeSource')
            self._scene_definition = source.scene_definition
            self._source_closure_digest = source.source_closure_digest
            return
        if (scene_definition is None) != (source_closure_digest is None):
            raise ValueError('canonical Scene and source closure digest must be provided together')
        if scene_definition is not None and source.source_id != f'scene-definition-v3:{scene_definition.identity_hash}':
            raise ValueError('source ID does not bind the canonical Scene identity')

    def build_scene_source(self, composition, agents):
        if self._usd_runtime_source is not None:
            from scene import SceneSource

            self._usd_runtime_source.scene_source.assert_fresh()
            if self._snapshot_lease is not None:
                raise RuntimeError('USD snapshot lease is already active')
            self._snapshot_lease = self._usd_runtime_source.scene_source.acquire_snapshot()
            delivery = self._usd_runtime_source.scene_source.loaded_delivery.delivery
            entry = self._snapshot_lease.root.joinpath(*delivery.entry_file.split('/'))
            if not entry.is_file():
                self.close()
                raise ValueError('owned USD snapshot is missing its declared entry file')
            return (
                SceneSource.usd_path(
                    entry,
                    label=self._usd_runtime_source.source_id,
                    variant_selections=delivery.variant_selections,
                ),
                'task_env_verified_usd_snapshot_bridge_v1',
            )
        if self._scene_definition is None:
            return native_scene_source(self._source), self.adapter_name
        self._projected_xml = project_scene_definition_v3_to_mjcf(
            self._source.xml, self._scene_definition,
        )
        from scene import SceneSource
        return (
            SceneSource.mjcf_string(
                self._projected_xml,
                base_dir=self._source.base_dir,
                label=self._source.source_id,
            ),
            'task_env_scene_definition_v3_geophys_bridge_v1',
        )

    def build_scene_model(self, imported_scene, composition):
        if self._usd_runtime_source is not None:
            if self._snapshot_lease is None or self._snapshot_lease.closed:
                raise RuntimeError('USD snapshot lease must remain active through public import')
            self._usd_mapping_report = validate_usd_runtime_source_import(
                self._usd_runtime_source, imported_scene,
            )
            return imported_scene.build_rigid_scene_model(use_imported_meshes=True)
        if self._scene_definition is not None:
            if self._projected_xml is None:
                raise RuntimeError('canonical Scene source must be built before model lowering')
            actual_digest = source_closure_digest_for_import(
                imported_scene, self._source, self._projected_xml,
            )
            if actual_digest != self._source_closure_digest:
                raise ValueError('canonical Scene source closure digest mismatch')
            validate_canonical_scene_import(self._scene_definition, imported_scene)
        # The public lowering resolves canonical mesh IDs through its imported
        # resource table; disabling that table leaves IDs as unreadable paths.
        scene_model = imported_scene.build_rigid_scene_model(use_imported_meshes=True)
        if self._scene_definition is not None:
            raw_geom_count = sum(
                1 for geom in ET.fromstring(self._projected_xml).iter('geom')
                if geom.get('name')
            )
            if int(scene_model.joint_data.get('n_geoms', -1)) <= 0 or len(imported_scene.ir.shapes) < raw_geom_count:
                raise ValueError('canonical Scene source geometry was not fully imported')
        return scene_model

    @property
    def usd_mapping_report(self):
        return self._usd_mapping_report

    def close(self):
        lease, self._snapshot_lease = self._snapshot_lease, None
        if lease is not None:
            lease.close()
