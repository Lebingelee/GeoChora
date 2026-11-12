"""Private MuJoCo peer adapter. No comparison/oracle or controller implementation."""
import xml.etree.ElementTree as ET
import math
import hashlib
import json
import numpy as np
from pathlib import PurePosixPath

from .common import _SessionValues, pose
from .source import lower_mujoco_scene_source, source_asset_bytes




def _source_asset_bytes(base_dir, source_xml):
    """Backward-compatible private spelling for the shared source owner."""

    return source_asset_bytes(base_dir, source_xml)


def _lower_receipt_mjcf_assets(receipt):
    """Give every receipt-bound asset a unique flat MuJoCo VFS name.

    MuJoCo's in-memory VFS rejects distinct source files that share a
    basename.  The source receipt remains byte-for-byte authoritative; only
    this compiler input copy receives deterministic aliases.
    """
    root = ET.fromstring(receipt.importer_xml)
    compiler = root.find('compiler')
    if compiler is not None and any(compiler.get(key) for key in ('meshdir', 'texturedir')):
        raise ValueError('mixed actuator receipt MJCF must use explicit source asset paths without compiler directories')
    payloads = {
        name: payload for name, payload in receipt.closure_files.items()
        if name not in {'scene.xml', 'canonical-source.xml'}
    }
    referenced: set[str] = set()
    aliases: dict[str, str] = {}
    alias_payloads: dict[str, bytes] = {}
    for node in root.iter():
        raw_path = node.get('file')
        if raw_path is None:
            continue
        if node.tag == 'include':
            raise ValueError('mixed actuator mixed source does not admit nested MJCF includes')
        if (not raw_path or raw_path.startswith('/') or '\\' in raw_path
                or any(part in {'', '.', '..'} for part in raw_path.split('/'))):
            raise ValueError(f'mixed actuator source asset path is not canonical: {raw_path!r}')
        if raw_path not in payloads:
            raise ValueError(f'mixed actuator source asset is missing from its immutable receipt: {raw_path!r}')
        referenced.add(raw_path)
        alias = aliases.get(raw_path)
        if alias is None:
            suffix = PurePosixPath(raw_path).suffix
            alias = f'gch_{hashlib.sha256(raw_path.encode("utf-8")).hexdigest()}{suffix}'
            if alias in alias_payloads:
                raise ValueError('mixed actuator deterministic MuJoCo asset alias collision')
            aliases[raw_path] = alias
            alias_payloads[alias] = payloads[raw_path]
        node.set('file', alias)
    if referenced != set(payloads):
        raise ValueError(
            'mixed actuator source asset references differ from the immutable receipt: '
            f'unreferenced={sorted(set(payloads) - referenced)}'
        )
    rows = [
        {
            'source_path': logical,
            'vfs_name': aliases[logical],
            'sha256': hashlib.sha256(payloads[logical]).hexdigest(),
            'size_bytes': len(payloads[logical]),
        }
        for logical in sorted(aliases)
    ]
    return ET.tostring(root, encoding='unicode'), alias_payloads, rows


def _mujoco_model_facts(model, mj):
    """Read compiled public MjModel values, with inertia about COM in body axes."""
    bodies = []
    for i in range(model.nbody):
        rotation = np.empty(9, dtype=np.float64)
        mj.mju_quat2Mat(rotation, model.body_iquat[i])
        rotation = rotation.reshape(3, 3)
        tensor = rotation @ np.diag(model.body_inertia[i]) @ rotation.T
        bodies.append({'name': mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, i),
                       'mass_kg': float(model.body_mass[i]),
                       'com_body_m': model.body_ipos[i].tolist(),
                       'inertia_body_at_com_kg_m2': tensor.tolist(),
                       'inertial_quaternion_body_wxyz': model.body_iquat[i].tolist()})
    joints = []
    for i in range(model.njnt):
        joints.append({'name': mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, i), 'id': i,
                       'type': int(model.jnt_type[i]), 'axis_body': model.jnt_axis[i].tolist(),
                       'limited': bool(model.jnt_limited[i]), 'range': model.jnt_range[i].tolist(),
                       'child_body_id': int(model.jnt_bodyid[i]),
                       'qpos_address': int(model.jnt_qposadr[i]), 'dof_address': int(model.jnt_dofadr[i])})
    actuators = []
    for i in range(model.nu):
        actuators.append({'name': mj.mj_id2name(model, mj.mjtObj.mjOBJ_ACTUATOR, i), 'id': i,
                          'transmission_type': int(model.actuator_trntype[i]),
                          'transmission_ids': model.actuator_trnid[i].tolist(),
                          'gear': model.actuator_gear[i].tolist(),
                          'gain_type': int(model.actuator_gaintype[i]),
                          'bias_type': int(model.actuator_biastype[i]),
                          'dynamics_type': int(model.actuator_dyntype[i]),
                          'gain_parameters': model.actuator_gainprm[i].tolist(),
                          'bias_parameters': model.actuator_biasprm[i].tolist(),
                          'control_limited': bool(model.actuator_ctrllimited[i]),
                          'control_range': model.actuator_ctrlrange[i].tolist(),
                          'force_limited': bool(model.actuator_forcelimited[i]),
                          'force_range': model.actuator_forcerange[i].tolist()})
    equality = [{'name': mj.mj_id2name(model, mj.mjtObj.mjOBJ_EQUALITY, i),
                 'type': int(model.eq_type[i]), 'object1_id': int(model.eq_obj1id[i]),
                 'object2_id': int(model.eq_obj2id[i]), 'active': bool(model.eq_active0[i]),
                 'data': model.eq_data[i].tolist()} for i in range(model.neq)]
    tendons = []
    for i in range(model.ntendon):
        start, count = int(model.tendon_adr[i]), int(model.tendon_num[i])
        tendons.append({'name': mj.mj_id2name(model, mj.mjtObj.mjOBJ_TENDON, i), 'id': i,
                        'wraps': [{'type': int(model.wrap_type[j]), 'object_id': int(model.wrap_objid[j]),
                                   'parameter': float(model.wrap_prm[j])}
                                  for j in range(start, start + count)]})
    return {'schema_version': 'mujoco-public-model-facts-v1', 'bodies': bodies,
            'joints': joints, 'actuators': actuators, 'native_timestep_s': float(model.opt.timestep),
            'inertia_reference': 'center_of_mass', 'inertia_frame': 'body',
            'equalities': equality, 'tendons': tendons}


def check_mujoco_named_layout(model, mj, source):
    """Resolve this source's names and address shapes in a compiled model."""
    result = {'joints': {}, 'free_joints': {}, 'bodies': {}, 'frames': {}, 'actuators': {}}
    joint_ids = {}
    for field, free in (('joints', False), ('free_joints', True)):
        for semantic, native in getattr(source, field).items():
            joint = int(model.joint(native).id)
            if joint < 0 or joint >= min(len(model.jnt_type), len(model.jnt_qposadr), len(model.jnt_dofadr)):
                raise ValueError(f'named joint is missing or has an invalid index: {semantic}')
            kind = int(model.jnt_type[joint])
            allowed = ((int(mj.mjtJoint.mjJNT_FREE),) if free else
                       (int(mj.mjtJoint.mjJNT_HINGE), int(mj.mjtJoint.mjJNT_SLIDE)))
            if kind not in allowed:
                raise ValueError(f'unsupported named joint type for {semantic}: {kind}')
            q, v = int(model.jnt_qposadr[joint]), int(model.jnt_dofadr[joint])
            nq, nv = (7, 6) if free else (1, 1)
            if q < 0 or v < 0 or q+nq > int(model.nq) or v+nv > int(model.nv):
                raise ValueError(f'named joint addresses exceed compiled dimensions: {semantic}')
            result[field][semantic] = {'native': native, 'id': joint, 'type': kind,
                                       'qpos': q, 'dof': v, 'qpos_width': nq, 'dof_width': nv}
            joint_ids[semantic] = joint
    for field, accessor in (('bodies', model.body), ('frames', model.site)):
        for semantic, native in getattr(source, field).items():
            index = int(accessor(native).id)
            if index < 0:
                raise ValueError(f'named {field} object is missing: {semantic}')
            result[field][semantic] = {'native': native, 'id': index}
    for semantic, native in source.joint_targets.items():
        actuator = int(model.actuator(native).id)
        if actuator < 0 or actuator >= min(len(model.actuator_trntype), len(model.actuator_trnid)):
            raise ValueError(f'named actuator is missing or has an invalid index: {semantic}')
        if semantic not in joint_ids:
            raise ValueError(f'actuator binding lacks its declared joint: {semantic}')
        if (int(model.actuator_trntype[actuator]) != int(mj.mjtTrn.mjTRN_JOINT)
                or int(model.actuator_trnid[actuator][0]) != joint_ids[semantic]):
            raise ValueError(f'actuator transmission does not target the declared joint: {semantic}')
        result['actuators'][semantic] = {'native': native, 'id': actuator,
                                         'joint_id': joint_ids[semantic]}
    for native in source.open_actuators:
        actuator = int(model.actuator(native).id)
        if actuator < 0 or actuator >= min(len(model.actuator_trntype), len(model.actuator_trnid)):
            raise ValueError(f'named opening actuator is missing or invalid: {native}')
        fact = {'native': native, 'id': actuator}
        if source.scene_definition is None:
            composition = getattr(source, 'composition_runtime_input', None)
            prefix = ''
            declaration_xml, declaration_name = source.scene_source.xml, native
            if composition is not None:
                fixed = composition.fixed_declaration.attachment_plan
                names = fixed.native_actuator_names
                owned = [key for key, value in names.items() if value == native]
                if len(owned) != 1:
                    raise ValueError(f'opening actuator has no unique composition owner: {native}')
                entity, declaration_name = owned[0].split('/', 1)
                declaration_xml = composition.fixed_declaration.source_by_entity[entity].xml
                if entity == fixed.child_entity_id:
                    prefix = fixed.namespace_prefix
            actuator_section = ET.fromstring(declaration_xml).find('actuator')
            candidates = [] if actuator_section is None else [
                node for node in actuator_section if node.get('name') == declaration_name]
            if len(candidates) != 1:
                raise ValueError(f'opening actuator has no unique source declaration: {native}')
            declaration = candidates[0]
            tendon_name, joint_name = declaration.get('tendon'), declaration.get('joint')
            tendon_name = prefix + tendon_name if tendon_name else None
            joint_name = prefix + joint_name if joint_name else None
            if tendon_name and not joint_name:
                expected_type, target = int(mj.mjtTrn.mjTRN_TENDON), int(model.tendon(tendon_name).id)
                fact.update(target_kind='tendon', target_native=tendon_name, target_id=target)
            elif joint_name and not tendon_name:
                expected_type, target = int(mj.mjtTrn.mjTRN_JOINT), int(model.joint(joint_name).id)
                fact.update(target_kind='joint', target_native=joint_name, target_id=target)
            else:
                raise ValueError(f'opening actuator has an unsupported transmission declaration: {native}')
            if (int(model.actuator_trntype[actuator]) != expected_type
                    or int(model.actuator_trnid[actuator][0]) != target):
                raise ValueError(f'opening actuator transmission differs from source: {native}')
        result['actuators']['open:'+native] = fact
    for field in ('torque_actuators', 'position_actuators'):
        for semantic, native in getattr(source, field, {}).items():
            actuator = int(model.actuator(native).id)
            if actuator < 0 or actuator >= min(len(model.actuator_trntype), len(model.actuator_trnid)):
                raise ValueError(f'named mixed actuator is missing or invalid: {semantic}')
            if semantic not in joint_ids:
                raise ValueError(f'mixed actuator lacks its declared joint: {semantic}')
            if (int(model.actuator_trntype[actuator]) != int(mj.mjtTrn.mjTRN_JOINT)
                    or int(model.actuator_trnid[actuator][0]) != joint_ids[semantic]):
                raise ValueError(f'mixed actuator transmission mismatch: {semantic}')
            result['actuators'][semantic] = {'native': native, 'id': actuator,
                                             'joint_id': joint_ids[semantic]}
    return result


class _MuJoCoSession(_SessionValues):
    def physical_source_dynamics_model(self):
        """Create a source-bound, no-step model for the current physical episode."""
        if getattr(self, '_physical_port', None) is None:
            raise ValueError('source dynamics requires an admitted physical port')
        from .mujoco_dynamics import MuJoCoSourceDynamicsV1
        return MuJoCoSourceDynamicsV1(self)

    def bind_physical_control(self, execution):
        """Bind one verified physical profile to this materialized session."""
        if getattr(self, '_physical_port', None) is not None or self._reset_done:
            raise ValueError('physical port must be bound once before reset')
        if getattr(self._source, 'position_subject_binding', None) is not None:
            raise ValueError('physical effort port cannot share position-subject actuator ownership')
        from .mujoco_physical import MuJoCoPhysicalPort
        versions = execution.controller_versions()
        self._physical_port = MuJoCoPhysicalPort(self, execution)
        self._physical_controller_versions = versions
        self.physical_control_generation = execution.generation

    def assess_physical_control(self, binding):
        return self._physical_port.assessment(binding)

    def physical_joint_build_receipt(self, binding):
        return self._physical_port.joints(binding)

    def physical_body_build_receipt(self, binding):
        return self._physical_port.body(binding)

    def physical_buffer_policy(self, binding):
        return self._physical_port.policy(binding)

    def apply_physical_command_batch(self, resolved):
        return self._physical_port.write(resolved)

    def apply_physical_command_sequence(self, sequence):
        return self._physical_port.write_sequence(sequence)

    def abort_physical_control(self):
        """Discard this session's pending physical batch after an interval fault."""
        port = getattr(self, '_physical_port', None)
        if port is not None and port.pending is not None:
            port.finish_interval()

    def __init__(self, artifact, source, *, mixed_actuator_plan=None):
        self._initialize_values(artifact, source, 'mujoco')
        self._mixed_actuator_plan = mixed_actuator_plan
        if source.fixed_attachment_plan is not None:
            try:
                self._initialize_fixed_attachment(artifact, source)
                checked = check_mujoco_named_layout(self._model, self._mj, source)
                self._build_layout_facts = {
                    'helper': 'task_env.runtime.sessions.mujoco:check_mujoco_named_layout',
                    'provider': 'mujoco', 'source_id': source.scene_source.source_id,
                    'source_closure': source.source_closure_digest, 'objects': checked,
                    'materialization_id': self.provider_materialization_id,
                }
            except Exception:
                # The existing adapter owns every partially-created native value.
                self.close()
                raise
            return
        if mixed_actuator_plan is not None:
            from ...controllers.canonical.contracts import MixedActuatorPlanV1
            if type(mixed_actuator_plan) is not MixedActuatorPlanV1:
                raise TypeError('unsupported typed mixed actuator plan')
            try:
                self._initialize_mixed_actuator(artifact, source)
                checked = check_mujoco_named_layout(self._model, self._mj, source)
                self._build_layout_facts = {
                    'helper': 'task_env.runtime.sessions.mujoco:check_mujoco_named_layout',
                    'provider': 'mujoco', 'source_id': source.scene_source.source_id,
                    'source_closure': source.source_closure_digest, 'objects': checked,
                    'materialization_id': self.provider_materialization_id,
                }
            except BaseException as error:
                try:
                    self.close()
                except BaseException as cleanup_error:
                    error.add_note(
                        'mixed actuator RuntimeSession constructor cleanup also failed: '
                        f'{type(cleanup_error).__name__}: {cleanup_error}'
                    )
                raise
            return
        import mujoco
        self._mj = mujoco
        composition = getattr(source, 'composition_runtime_input', None)
        if composition is not None:
            from .mujoco_composition import materialize_fixed_robot_task
            self._model, self._composition_receipt, self._composition_details = materialize_fixed_robot_task(
                composition=composition.plan, task_receipt=source.execution_source_receipt,
                fixed_declaration=composition.fixed_declaration,
                retained_roots=composition.retained_roots,
                replaced_robot_roots=composition.replaced_robot_roots,
                entity_body_names=composition.entity_body_names,
                allowed_free_joints=composition.allowed_free_joints,
                task_site_transfers=composition.plan.task_site_transfers,
            )
            from dataclasses import replace
            self._composition_receipt = replace(
                self._composition_receipt, materialization_id=self.provider_materialization_id)
            self._composition_receipt.validate_against(composition.plan)
        else:
            assets = None
            if source.scene_definition is not None:
                source_xml, assets = lower_mujoco_scene_source(
                    source.scene_source,
                    source.scene_definition,
                    source.source_closure_digest,
                )
            else:
                receipt = source.execution_source_receipt
                if receipt is None:
                    source_xml = source.scene_source.xml
                else:
                    receipt.validate_snapshot()
                    source_xml = receipt.importer_xml.decode('utf-8')
                    assets = {name: payload for name, payload in receipt.closure_files.items()
                              if name not in {'scene.xml', 'canonical-source.xml'}}
                legacy_root = ET.fromstring(source_xml)
                for element in legacy_root.iter('freejoint'):
                    element.tag = 'joint'
                    element.set('type', 'free')
                for element in legacy_root.findall('keyframe'):
                    legacy_root.remove(element)
                source_xml = ET.tostring(legacy_root, encoding='unicode')
            root = ET.fromstring(source_xml)
            self._model = mujoco.MjModel.from_xml_string(
                ET.tostring(root, encoding='unicode'), assets=assets,
            )
        self._data = mujoco.MjData(self._model)
        self._native_steps = 0
        self._fixed_forward_calls = 0
        self._fixed_attachment_close_receipt = None
        self._force_sample_sequence = 0
        self._force_configuration_revision = 0
        self._last_force_limit_N = None
        self._completed_actuator_ctrl = None
        self._completed_force_measurement = None
        if self._model.opt.timestep != artifact.timebase.physics_dt:
            raise ValueError('MuJoCo native timestep mismatch')
        try:
            checked = check_mujoco_named_layout(self._model, self._mj, source)
            self._joint_addresses = {k: (v['qpos'], v['dof']) for k, v in checked['joints'].items()}
            self._free_addresses = {k: (v['qpos'], v['dof']) for k, v in checked['free_joints'].items()}
            self._bodies = {k: v['id'] for k, v in checked['bodies'].items()}
            self._frames = {k: v['id'] for k, v in checked['frames'].items()}
            self._target_actuators = {k: checked['actuators'][k]['id'] for k in source.joint_targets}
            self._open_actuators = tuple(checked['actuators']['open:'+n]['id'] for n in source.open_actuators)
            self._build_layout_facts = {'helper': 'task_env.runtime.sessions.mujoco:check_mujoco_named_layout',
                'provider': 'mujoco', 'source_id': source.scene_source.source_id,
                'source_closure': source.source_closure_digest, 'objects': checked,
                'materialization_id': self.provider_materialization_id,
                'composition_intent_sha256': getattr(source.source_composition_intent, 'identity_hash', None),
                'composition_request_v2_sha256': getattr(source.source_composition_request, 'identity_hash', None),
                'physical_model': _mujoco_model_facts(self._model, self._mj)}
            if source.source_reference_plan is not None:
                self._build_layout_facts['source_reference'] = {
                    'schema_version': 'source-composition-materialization-receipt-v1',
                    'plan_sha256': source.source_reference_plan.identity_hash,
                    'composition_intent_sha256': getattr(source.source_composition_intent, 'identity_hash', None),
                    'composition_request_v2_sha256': getattr(source.source_composition_request, 'identity_hash', None),
                    'materialization_id': self.provider_materialization_id,
                    'task_source_id': source.source_reference_plan.task_source.source_id,
                    'task_closure_sha256': source.source_reference_plan.task_source.closure_sha256,
                    'robot_entities': list(source.source_reference_plan.existing_robot_entity_ids),
                    'objects': checked, 'physical_model': self._build_layout_facts['physical_model'],
                    'controller_binding_sha256': source.position_subject_binding.plan.identity_hash,
                    'subject_binding_sha256': source.position_subject_binding.subject_identity_sha256,
                    'resource_writers': list(source.position_subject_binding.plan.resource_writers),
                }
            if composition is not None:
                self._build_layout_facts['source_composition'] = {
                    'schema_version': 'source-composition-materialization-receipt-v1',
                    'plan_sha256': self._composition_receipt.plan_sha256,
                    'composition_intent_sha256': getattr(source.source_composition_intent, 'identity_hash', None),
                    'composition_request_v2_sha256': getattr(source.source_composition_request, 'identity_hash', None),
                    'source_closures': list(self._composition_receipt.source_closures),
                    'entity_native_names': list(self._composition_receipt.entity_native_names),
                    'materialization_id': self._composition_receipt.materialization_id,
                    'details': self._composition_details,
                    'objects': checked, 'physical_model': self._build_layout_facts['physical_model'],
                    'controller_binding_sha256': source.position_subject_binding.plan.identity_hash,
                    'subject_binding_sha256': source.position_subject_binding.subject_identity_sha256,
                    'resource_writers': list(source.position_subject_binding.plan.resource_writers),
                }
        except BaseException:
            self.close()
            raise
        self._validate_canonical_scene_model()

    def _initialize_mixed_actuator(self, artifact, source):
        """Compile one receipt-bound mixed actuator model and preflight every named slot."""
        from .provenance import provider_build_identity
        from ...assembly.assets import _source_closure_manifest

        receipt = source.execution_source_receipt
        if receipt is None:
            raise ValueError('mixed actuator materialization requires its immutable source receipt')
        receipt.validate_snapshot()
        import mujoco

        self._mj = mujoco
        self._runtime_identity = self._fixed_runtime_identity(mujoco)
        self._provider_build_identity = provider_build_identity('mujoco')
        compile_xml, assets, asset_aliases = _lower_receipt_mjcf_assets(receipt)
        self._model = mujoco.MjModel.from_xml_string(
            compile_xml, assets=assets,
        )
        self._data = mujoco.MjData(self._model)
        self._native_steps = 0
        self._preprocess_calls = 0
        self._forward_calls = 0
        self._reset_count = 0
        self._last_close_receipt = None
        self._mixed_fault = None
        self._mixed_pending_target = None
        self._mixed_consumed_boundaries = set()
        self._reset_time_origin = 0.0
        self._last_reset_readback_v1 = None
        self._fixed_attachment_close_receipt = None
        self._force_sample_sequence = 0
        self._force_configuration_revision = 0
        self._last_force_limit_N = None
        self._completed_actuator_ctrl = None
        self._completed_force_measurement = None
        self._mixed_actuator_plan.validate()
        if (self._mixed_actuator_plan.task_artifact_hash != artifact.identity_hash
                or self._mixed_actuator_plan.source_id != source.scene_source.source_id
                or self._mixed_actuator_plan.source_closure_digest != source.source_closure_digest):
            raise ValueError('compiled mixed actuator plan differs from the admitted Artifact/source')
        if float(self._model.opt.timestep) != artifact.timebase.physics_dt:
            raise ValueError('compiled mixed actuator MuJoCo timestep differs from TaskArtifact')
        self._joint_addresses = {
            semantic: self._addresses(native, free=False) for semantic, native in source.joints.items()
        }
        self._free_addresses = {
            semantic: self._addresses(native, free=True) for semantic, native in source.free_joints.items()
        }
        self._bodies = {
            semantic: int(self._model.body(native).id) for semantic, native in source.bodies.items()
        }
        self._frames = {
            semantic: int(self._model.site(native).id) for semantic, native in source.frames.items()
        }
        self._torque_actuators = {
            semantic: int(self._model.actuator(native).id)
            for semantic, native in source.torque_actuators.items()
        }
        self._position_actuators = {
            semantic: int(self._model.actuator(native).id)
            for semantic, native in source.position_actuators.items()
        }
        self._channel_actuator_ids = {}
        self._channel_records = {}
        for channel in self._mixed_actuator_plan.channels:
            if channel.semantic_id in source.torque_actuators:
                actuator_map = source.torque_actuators
                expected_mode = 'joint_torque'
            elif channel.semantic_id in source.position_actuators:
                actuator_map = source.position_actuators
                expected_mode = 'joint_position'
            else:
                raise ValueError(f'mixed actuator channel is not mapped by RuntimeSource: {channel.semantic_id}')
            if channel.drive_mode != expected_mode:
                raise ValueError(f'mixed actuator drive mode differs from RuntimeSource: {channel.semantic_id}')
            aid = int(self._mj.mj_name2id(
                self._model, self._mj.mjtObj.mjOBJ_ACTUATOR, channel.actuator_name,
            ))
            joint_id = int(self._mj.mj_name2id(
                self._model, self._mj.mjtObj.mjOBJ_JOINT, channel.joint_name,
            ))
            if (aid < 0 or joint_id < 0 or actuator_map[channel.semantic_id] != channel.actuator_name
                    or source.joints.get(channel.semantic_id) != channel.joint_name):
                raise ValueError(f'mixed actuator channel does not resolve through named source bindings: {channel.semantic_id}')
            if (int(self._model.actuator_trntype[aid]) != int(self._mj.mjtTrn.mjTRN_JOINT)
                    or int(self._model.actuator_trnid[aid, 0]) != joint_id):
                raise ValueError(f'mixed actuator must drive its declared source joint: {channel.semantic_id}')
            gear = np.asarray(self._model.actuator_gear[aid], dtype=np.float64).reshape(-1)
            if (gear.shape != (6,) or not np.isfinite(gear).all()
                    or not np.array_equal(gear, np.asarray((1.0, 0, 0, 0, 0, 0), dtype=np.float64))
                    or int(self._model.actuator_dyntype[aid]) != int(self._mj.mjtDyn.mjDYN_NONE)):
                raise ValueError(f'mixed actuator must use a unit scalar gear and stateless drive law: {channel.semantic_id}')
            joint_type = int(self._model.jnt_type[joint_id])
            unit_for_joint = {
                int(self._mj.mjtJoint.mjJNT_HINGE): 'rad',
                int(self._mj.mjtJoint.mjJNT_SLIDE): 'm',
            }.get(joint_type)
            if channel.drive_mode == 'joint_torque':
                if joint_type != int(self._mj.mjtJoint.mjJNT_HINGE) or channel.unit != 'N*m':
                    raise ValueError(f'torque channel requires a hinge and N*m units: {channel.semantic_id}')
                if (int(self._model.actuator_gaintype[aid]) != int(self._mj.mjtGain.mjGAIN_FIXED)
                        or int(self._model.actuator_biastype[aid]) != int(self._mj.mjtBias.mjBIAS_NONE)
                        or float(self._model.actuator_gainprm[aid, 0]) != 1.0):
                    raise ValueError(f'torque channel is not a unit-gain motor: {channel.semantic_id}')
            else:
                if channel.unit != unit_for_joint:
                    raise ValueError(f'position channel unit differs from compiled joint type: {channel.semantic_id}')
                if (int(self._model.actuator_gaintype[aid]) != int(self._mj.mjtGain.mjGAIN_FIXED)
                        or int(self._model.actuator_biastype[aid]) != int(self._mj.mjtBias.mjBIAS_AFFINE)
                        or not math.isfinite(float(self._model.actuator_gainprm[aid, 0]))
                        or float(self._model.actuator_gainprm[aid, 0]) <= 0.0
                        or float(self._model.actuator_biasprm[aid, 0]) != 0.0
                        or float(self._model.actuator_biasprm[aid, 2]) > 0.0
                        or not np.isclose(
                            float(self._model.actuator_biasprm[aid, 1]),
                            -float(self._model.actuator_gainprm[aid, 0]),
                            rtol=0.0, atol=1.0e-12,
                        )
                        or not np.isfinite(np.asarray(self._model.actuator_biasprm[aid], dtype=np.float64)).all()):
                    raise ValueError(f'position channel is not a fixed-gain affine servo: {channel.semantic_id}')
            low, high = (float(value) for value in self._model.actuator_ctrlrange[aid])
            if (not bool(self._model.actuator_ctrllimited[aid])
                    or not np.allclose((low, high), channel.control_range, rtol=0.0, atol=1.0e-10)):
                raise ValueError(f'compiled actuator range differs from its source-bound plan: {channel.semantic_id}')
            self._channel_actuator_ids[channel.semantic_id] = aid
            self._channel_records[channel.semantic_id] = {
                'actuator_name': channel.actuator_name, 'actuator_id': aid,
                'joint_name': channel.joint_name, 'joint_id': joint_id,
                'drive_mode': channel.drive_mode, 'unit': channel.unit,
                'control_limited': True, 'control_range': [low, high],
                'transmission_type': 'joint',
                'gain_type': int(self._model.actuator_gaintype[aid]),
                'bias_type': int(self._model.actuator_biastype[aid]),
            }
        self._contact_geom_ids = {}
        for semantic, names in source.contact_geom_groups.items():
            ids = tuple(int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_GEOM, name)) for name in names)
            if not ids or any(index < 0 for index in ids):
                raise ValueError(f'compiled geom group is incomplete: {semantic}')
            self._contact_geom_ids[semantic] = frozenset(ids)
        for semantic, record in self._channel_records.items():
            record['transmission_target'] = source.joints[semantic]
        self._current_ctrl = self._data.ctrl.copy()
        self._compiled_layout_receipt = {
            'schema_version': 'compiled-model-layout-v1',
            'dimensions': {'nq': int(self._model.nq), 'nv': int(self._model.nv),
                           'na': int(self._model.na), 'nu': int(self._model.nu),
                           'njnt': int(self._model.njnt), 'nbody': int(self._model.nbody),
                           'nsite': int(self._model.nsite), 'ngeom': int(self._model.ngeom)},
            'source_closure_digest': source.source_closure_digest,
            'source_id': source.scene_source.source_id,
            'plan_identity_hash': self._mixed_actuator_plan.identity_hash,
            'canonical_xml_sha256': receipt.canonical_xml_sha256,
            'source_files': list(_source_closure_manifest(receipt.closure_files)),
            'compiler_asset_aliases': asset_aliases,
            'named_joint_addresses': {key: list(value) for key, value in self._joint_addresses.items()},
            'named_free_joint_addresses': {key: list(value) for key, value in self._free_addresses.items()},
            'named_joint_limits': {
                semantic: {
                    'joint_name': source.joints[semantic],
                    'joint_id': int(self._mj.mj_name2id(
                        self._model, self._mj.mjtObj.mjOBJ_JOINT, source.joints[semantic],
                    )),
                    'limited': bool(self._model.jnt_limited[int(self._mj.mj_name2id(
                        self._model, self._mj.mjtObj.mjOBJ_JOINT, source.joints[semantic],
                    ))]),
                    'range': [float(value) for value in self._model.jnt_range[int(self._mj.mj_name2id(
                        self._model, self._mj.mjtObj.mjOBJ_JOINT, source.joints[semantic],
                    ))]],
                }
                for semantic in self._joint_addresses
            },
            'named_body_ids': dict(self._bodies), 'named_frame_ids': dict(self._frames),
            'named_torque_actuator_ids': dict(self._torque_actuators),
            'named_position_actuator_ids': dict(self._position_actuators),
            'named_actuator_channels': self._channel_records,
            'named_contact_geom_groups': {
                semantic: [
                    {'name': name, 'id': int(self._mj.mj_name2id(
                        self._model, self._mj.mjtObj.mjOBJ_GEOM, name,
                    ))}
                    for name in names
                ]
                for semantic, names in source.contact_geom_groups.items()
            },
        }
        integrator_names = {
            int(self._mj.mjtIntegrator.mjINT_EULER): 'euler',
            int(self._mj.mjtIntegrator.mjINT_RK4): 'rk4',
            int(self._mj.mjtIntegrator.mjINT_IMPLICIT): 'implicit',
            int(self._mj.mjtIntegrator.mjINT_IMPLICITFAST): 'implicitfast',
        }
        solver_names = {
            int(self._mj.mjtSolver.mjSOL_PGS): 'pgs',
            int(self._mj.mjtSolver.mjSOL_CG): 'cg',
            int(self._mj.mjtSolver.mjSOL_NEWTON): 'newton',
        }
        cone_names = {
            int(self._mj.mjtCone.mjCONE_PYRAMIDAL): 'pyramidal',
            int(self._mj.mjtCone.mjCONE_ELLIPTIC): 'elliptic',
        }
        option = self._model.opt
        option_scalars = {
            'timestep': float(option.timestep),
            'impratio': float(option.impratio),
            'tolerance': float(option.tolerance),
            'ls_tolerance': float(option.ls_tolerance),
            'noslip_tolerance': float(option.noslip_tolerance),
            'ccd_tolerance': float(option.ccd_tolerance),
            'density': float(option.density),
            'viscosity': float(option.viscosity),
            'o_margin': float(option.o_margin),
            'sleep_tolerance': float(option.sleep_tolerance),
            'integrator': int(option.integrator),
            'cone': int(option.cone),
            'solver': int(option.solver),
            'jacobian': int(option.jacobian),
            'iterations': int(option.iterations),
            'ls_iterations': int(option.ls_iterations),
            'noslip_iterations': int(option.noslip_iterations),
            'ccd_iterations': int(option.ccd_iterations),
            'sdf_initpoints': int(option.sdf_initpoints),
            'sdf_iterations': int(option.sdf_iterations),
            'disableflags': int(option.disableflags),
            'enableflags': int(option.enableflags),
        }
        option_arrays = {
            'gravity': [float(value) for value in option.gravity],
            'wind': [float(value) for value in option.wind],
            'magnetic': [float(value) for value in option.magnetic],
            'o_friction': [float(value) for value in option.o_friction],
            'o_solref': [float(value) for value in option.o_solref],
            'o_solimp': [float(value) for value in option.o_solimp],
            'disableactuator': int(option.disableactuator),
        }
        compiled_model_binary_sha256 = None
        size_model = getattr(self._mj, 'mj_sizeModel', None)
        save_model = getattr(self._mj, 'mj_saveModel', None)
        if callable(size_model) and callable(save_model):
            try:
                model_binary = np.zeros(int(size_model(self._model)), dtype=np.uint8)
                save_model(self._model, buffer=model_binary)
                compiled_model_binary_sha256 = hashlib.sha256(
                    model_binary.tobytes(),
                ).hexdigest()
            except (AttributeError, TypeError, ValueError, RuntimeError):
                # Binary identity is optional diagnostic data. Keep model
                # materialization available when a MuJoCo build cannot export MJB.
                compiled_model_binary_sha256 = None
        self._compiled_model_options_receipt_v1 = {
            'schema_version': 'compiled-model-options-v1',
            'provider': 'mujoco',
            'backend': 'cpu',
            'source_id': source.scene_source.source_id,
            'source_closure_digest': source.source_closure_digest,
            'canonical_xml_sha256': receipt.canonical_xml_sha256,
            'plan_identity_hash': self._mixed_actuator_plan.identity_hash,
            'compiled_model_binary_sha256': compiled_model_binary_sha256,
            'mujoco_runtime': {
                'package_version': self._runtime_identity['package_version'],
                'runtime_version': self._runtime_identity['runtime_version'],
                'api_version': self._runtime_identity['api_version'],
            },
            'options': {
                **option_scalars,
                **option_arrays,
                'integrator_name': integrator_names.get(int(option.integrator), 'unknown'),
                'solver_name': solver_names.get(int(option.solver), 'unknown'),
                'cone_name': cone_names.get(int(option.cone), 'unknown'),
            },
            'model_sizes': {
                'njmax': int(self._model.njmax),
                'nconmax': int(self._model.nconmax),
            },
        }

    @property
    def compiled_layout_receipt(self):
        if self._mixed_actuator_plan is None:
            raise RuntimeError('compiled mixed actuator layout is unavailable for this session')
        return json.loads(json.dumps(self._compiled_layout_receipt, sort_keys=True))

    @property
    def compiled_model_options_receipt_v1(self):
        if self._mixed_actuator_plan is None:
            raise RuntimeError('compiled model options are unavailable for this session')
        return json.loads(json.dumps(
            self._compiled_model_options_receipt_v1, sort_keys=True,
        ))

    @property
    def compiled_model_physics_fingerprint_v1(self):
        if self._mixed_actuator_plan is None:
            raise RuntimeError('compiled model physics fingerprint is unavailable for this session')
        cached = getattr(self, '_compiled_model_physics_fingerprint_v1_cache', None)
        if cached is None:
            model = self._model
            object_specs = {
                'bodies': ('nbody', self._mj.mjtObj.mjOBJ_BODY),
                'joints': ('njnt', self._mj.mjtObj.mjOBJ_JOINT),
                'geoms': ('ngeom', self._mj.mjtObj.mjOBJ_GEOM),
                'sites': ('nsite', self._mj.mjtObj.mjOBJ_SITE),
                'actuators': ('nu', self._mj.mjtObj.mjOBJ_ACTUATOR),
            }
            object_names = {
                kind: [
                    self._mj.mj_id2name(model, object_type, index)
                    for index in range(int(getattr(model, count_name)))
                ]
                for kind, (count_name, object_type) in object_specs.items()
            }
            dimensions = {}
            for name in dir(model):
                if not name.startswith('n'):
                    continue
                try:
                    value = getattr(model, name)
                except (AttributeError, RuntimeError):
                    continue
                if type(value) is int:
                    dimensions[name] = value
            prefixes = (
                'body_', 'jnt_', 'dof_', 'geom_', 'site_', 'actuator_',
                'tendon_', 'pair_', 'exclude_', 'eq_', 'mesh_', 'hfield_',
                'flex_', 'wrap_',
            )
            numeric_arrays = {}
            for name in sorted(dir(model)):
                if not name.startswith(prefixes) or name.endswith(('_pathadr', '_nameadr')):
                    continue
                try:
                    value = getattr(model, name)
                except (AttributeError, RuntimeError):
                    continue
                if not isinstance(value, np.ndarray) or value.dtype.kind not in 'biufc':
                    continue
                array = np.ascontiguousarray(value)
                numeric_arrays[name] = {
                    'dtype': array.dtype.str,
                    'shape': [int(size) for size in array.shape],
                    'sha256': hashlib.sha256(array.tobytes()).hexdigest(),
                }
            cached = {
                'schema_version': 'compiled-model-physics-fingerprint-v1',
                'provider': 'mujoco',
                'backend': 'cpu',
                'source_id': self._source.scene_source.source_id,
                'source_closure_digest': self._source.source_closure_digest,
                'canonical_xml_sha256': self._compiled_layout_receipt['canonical_xml_sha256'],
                'compiled_model_binary_sha256': self._compiled_model_options_receipt_v1[
                    'compiled_model_binary_sha256'
                ],
                'model_dimensions': dimensions,
                'object_names': object_names,
                'numeric_array_fields': numeric_arrays,
            }
            self._compiled_model_physics_fingerprint_v1_cache = cached
        return json.loads(json.dumps(cached, sort_keys=True))

    @property
    def runtime_identity(self):
        if self._mixed_actuator_plan is None:
            raise RuntimeError('pinned MuJoCo runtime identity is unavailable for this profile')
        return json.loads(json.dumps({
            'runtime': self._runtime_identity,
            'provider_build': self._provider_build_identity,
        }, sort_keys=True))

    @property
    def runtime_progress_receipt(self):
        if self._mixed_actuator_plan is None:
            raise RuntimeError('mixed runtime progress is unavailable for this session profile')
        return {
            'schema_version': 'runtime-progress-v1',
            'provider_materialization_id': self._provider_materialization_id,
            'episode_id': self._episode_id,
            'reset_sample_id': self._reset_sample_id,
            'reset_count': int(self._reset_count),
            'control_step': int(self._control_step),
            'state_revision': int(self._state_revision),
            'native_step_count': int(self._native_steps),
            'preprocess_call_count': int(self._preprocess_calls),
            'forward_call_count': int(self._forward_calls),
            'simulation_time_native_s': float(self._data.time),
            'simulation_time_episode_s': float(self._data.time - self._reset_time_origin),
            'source_id': self._source.scene_source.source_id,
            'source_closure_digest': self._source.source_closure_digest,
            'plan_identity_hash': self._mixed_actuator_plan.identity_hash,
            'physical_state_monitor': self.physical_state_monitor_receipt,
        }

    @property
    def close_receipt(self):
        if self._mixed_actuator_plan is None:
            raise RuntimeError('mixed close evidence is unavailable for this session profile')
        if self._last_close_receipt is None:
            raise RuntimeError('mixed RuntimeSession close has not completed')
        return json.loads(json.dumps(self._last_close_receipt, sort_keys=True))

    @property
    def reset_readback_v1(self):
        self._require_reset()
        if self._last_reset_readback_v1 is None:
            raise RuntimeError('versioned reset readback is unavailable before the admitted reset')
        return self._last_reset_readback_v1

    @staticmethod
    def _fixed_runtime_identity(mujoco):
        """Verify the authorized MuJoCo package, binding and loaded CPU library."""
        from pathlib import Path
        import mujoco._functions as functions

        expected = {
            "package": "f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497",
            "binding": "9067239d3126392729430d12d077ab4b298c61d2ea1209c9333823be410359e3",
            "library": "8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592",
            "header": "d5ccfb227eb06586edfb4def5812a8082c1cbdf8e6dc5c3176abd9772a57fd07",
        }
        expected_paths = {
            "package": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/__init__.py",
            "binding": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/_functions.cpython-312-x86_64-linux-gnu.so",
            "library": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/libmujoco.so.3.8.1",
            "header": "/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages/mujoco/include/mujoco/mujoco.h",
        }
        package_path = Path(mujoco.__file__).resolve()
        binding_path = Path(functions.__file__).resolve()
        if (mujoco.__version__ != "3.8.1" or int(mujoco.mj_version()) != 3008001
                or mujoco.mj_versionString() != "3.8.1"):
            raise ValueError("loaded MuJoCo runtime is not the pinned 3.8.1/API 3008001 build")
        if hashlib.sha256(package_path.read_bytes()).hexdigest() != expected["package"]:
            raise ValueError("loaded MuJoCo Python package bytes differ from the frozen input")
        if hashlib.sha256(binding_path.read_bytes()).hexdigest() != expected["binding"]:
            raise ValueError("loaded MuJoCo binding bytes differ from the frozen input")
        if str(package_path) != expected_paths["package"] or str(binding_path) != expected_paths["binding"]:
            raise ValueError("loaded MuJoCo package/binding paths differ from the frozen input")
        mapped_paths = set()
        with open("/proc/self/maps", encoding="utf-8") as maps:
            for line in maps:
                if "libmujoco.so.3.8.1" in line:
                    raw = line.rstrip().split()[-1]
                    if raw.startswith("/"):
                        mapped_paths.add(str(Path(raw.removesuffix(" (deleted)")).resolve()))
        libraries = sorted(mapped_paths)
        if len(libraries) != 1:
            raise ValueError(f"expected exactly one mapped MuJoCo 3.8.1 core library, found {libraries}")
        library_path = Path(libraries[0])
        library_sha256 = hashlib.sha256(library_path.read_bytes()).hexdigest()
        if (library_sha256 != expected["library"]
                or str(library_path) != expected_paths["library"]):
            raise ValueError("loaded MuJoCo core library path or bytes differ from the frozen input")
        header_path = package_path.parent / "include/mujoco/mujoco.h"
        header_sha256 = hashlib.sha256(header_path.read_bytes()).hexdigest()
        if (str(header_path.resolve()) != expected_paths["header"]
                or header_sha256 != expected["header"]):
            raise ValueError("installed MuJoCo public header path or bytes differ from the frozen input")
        return {
            "package_version": mujoco.__version__, "runtime_version": mujoco.mj_versionString(),
            "api_version": int(mujoco.mj_version()),
            "package_path": str(package_path),
            "package_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
            "binding_path": str(binding_path),
            "binding_sha256": hashlib.sha256(binding_path.read_bytes()).hexdigest(),
            "mapped_native_libraries": [{"path": str(library_path), "sha256": library_sha256}],
            "public_header_path": str(header_path.resolve()),
            "public_header_sha256": header_sha256,
            "renderer_initialized": False,
        }

    def _initialize_fixed_attachment(self, artifact, source):
        import mujoco
        from .provenance import provider_build_identity
        from ...assembly.fixed_attachment import lower_fixed_attachment_sources
        from ...assembly import panda_source_profiles

        self._mj = mujoco
        runtime_identity = self._fixed_runtime_identity(mujoco)
        lowered = lower_fixed_attachment_sources(
            parent_source=source.scene_source,
            source_by_entity=source.fixed_attachment_sources,
            scene=source.scene_definition,
            plan=source.fixed_attachment_plan,
            assembly=source.fixed_attachment_assembly,
            source_profile=panda_source_profiles,
        )
        parent_root = ET.fromstring(lowered.parent_xml)
        for keyframe in tuple(parent_root.findall("keyframe")):
            parent_root.remove(keyframe)
        child_root = ET.fromstring(lowered.child_xml)
        for keyframe in tuple(child_root.findall("keyframe")):
            child_root.remove(keyframe)
        parent_xml = ET.tostring(parent_root, encoding="unicode")
        child_xml = ET.tostring(child_root, encoding="unicode")
        parent_spec = mujoco.MjSpec.from_string(parent_xml, assets=lowered.parent_assets)
        child_spec = mujoco.MjSpec.from_string(child_xml, assets=lowered.child_assets)
        plan = source.fixed_attachment_plan
        child_body = child_spec.body(plan.child_mount_body_name.removeprefix(plan.namespace_prefix))
        if child_body is None:
            raise ValueError("MuJoCo MjSpec child source has no measured hand root body")
        compensation = child_spec.worldbody.add_frame(
            pos=plan.attach_frame_from_child_worldbody.position,
            quat=plan.attach_frame_from_child_worldbody.quaternion_wxyz,
        )
        child_body.set_frame(compensation)
        attached = parent_spec.attach(
            child_spec, site=plan.parent_mount_site_name, prefix=plan.namespace_prefix,
        )
        if attached is None:
            raise ValueError("MuJoCo MjSpec public attach returned no attached frame")
        model = parent_spec.compile()
        data = mujoco.MjData(model)
        self._model, self._data = model, data
        self._native_steps = 0
        self._fixed_forward_calls = 0
        self._fixed_attachment_close_receipt = None
        self._force_sample_sequence = 0
        self._force_configuration_revision = 0
        self._last_force_limit_N = None
        self._completed_actuator_ctrl = None
        self._completed_force_measurement = None
        if model.opt.timestep != artifact.timebase.physics_dt:
            raise ValueError("MuJoCo fixed Attachment timestep differs from the TaskArtifact")
        self._joint_addresses = {
            semantic: self._addresses(native, free=False)
            for semantic, native in source.joints.items()
        }
        self._free_addresses = {}
        self._bodies = {
            semantic: model.body(native).id for semantic, native in source.bodies.items()
        }
        self._frames = {
            semantic: model.site(native).id for semantic, native in source.frames.items()
        }
        self._target_actuators = {
            semantic: model.actuator(native).id for semantic, native in source.joint_targets.items()
        }
        self._open_actuators = tuple(model.actuator(native).id for native in source.open_actuators)
        self._validate_canonical_scene_model()
        self._fixed_attachment_runtime_identity = runtime_identity
        self._fixed_attachment_provider_build = provider_build_identity("mujoco")
        self._fixed_attachment_lowering = {
            "method": "MuJoCo public MjSpec.from_string + parent_spec.attach(child_spec, site, prefix)",
            "keyframe_disposition": "source bytes retained in closure; source keyframes removed for ResetPlan-owned reset",
            "attach_frame_compensation": plan.attach_frame_from_child_worldbody.to_mapping(),
            "source_closure_sha256": lowered.source_closure_sha256,
            "source_closure_bytes": lowered.closure_bytes,
        }
        self._fixed_attachment_receipt = self._make_fixed_attachment_receipt()

    @property
    def fixed_attachment_receipt(self):
        if not hasattr(self, "_fixed_attachment_receipt"):
            raise RuntimeError("MuJoCo RuntimeSession has no admitted fixed Attachment")
        return json.loads(json.dumps(self._fixed_attachment_receipt, sort_keys=True))

    @property
    def fixed_attachment_diagnostics(self):
        self._require_reset()
        return {
            "provider_materialization_id": self._provider_materialization_id,
            "episode_id": self._episode_id,
            "reset_sample_id": self._reset_sample_id,
            "control_step": self._control_step,
            "state_revision": self._state_revision,
            "native_step_count": self._native_steps,
            "forward_call_count": self._fixed_forward_calls,
            "native_time_s": float(self._data.time),
            "ctrl": [float(value) for value in self._data.ctrl],
            "warning_counts": [int(item.number) for item in self._data.warning],
        }

    @property
    def fixed_attachment_close_evidence(self):
        value = self._fixed_attachment_close_receipt
        return None if value is None else json.loads(json.dumps(value, sort_keys=True))

    def _make_fixed_attachment_receipt(self):
        plan = self._source.fixed_attachment_plan
        model, mj = self._model, self._mj
        dimensions = {
            "nq": int(model.nq), "nv": int(model.nv), "nu": int(model.nu),
            "njnt": int(model.njnt), "nbody": int(model.nbody),
            "nsite": int(model.nsite), "nmesh": int(model.nmesh),
            "ngeom": int(model.ngeom), "neq": int(model.neq),
            "ntendon": int(model.ntendon), "nexclude": int(model.nexclude),
        }
        joint_maps = {}
        for canonical, native_name in plan.native_joint_names.items():
            jid = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, native_name))
            joint_maps[canonical] = {
                "native_name": native_name, "joint_id": jid,
                "qpos_address": int(model.jnt_qposadr[jid]),
                "dof_address": int(model.jnt_dofadr[jid]),
                "type": int(model.jnt_type[jid]),
                "axis": [float(item) for item in model.jnt_axis[jid]],
                "limited": bool(model.jnt_limited[jid]),
                "range": [float(item) for item in model.jnt_range[jid]],
                "body_id": int(model.jnt_bodyid[jid]),
            }
        actuator_maps = {}
        for canonical, native_name in plan.native_actuator_names.items():
            aid = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, native_name))
            target_type = int(model.actuator_trntype[aid])
            target_id = int(model.actuator_trnid[aid, 0])
            object_type = mj.mjtObj.mjOBJ_TENDON if target_type == int(mj.mjtTrn.mjTRN_TENDON) else mj.mjtObj.mjOBJ_JOINT
            target_name = mj.mj_id2name(model, object_type, target_id)
            actuator_maps[canonical] = {
                "native_name": native_name, "actuator_id": aid, "ctrl_slot": aid,
                "transmission_type": target_type, "target_native_name": target_name,
                "ctrl_limited": bool(model.actuator_ctrllimited[aid]),
                "ctrl_range": [float(item) for item in model.actuator_ctrlrange[aid]],
                "force_limited": bool(model.actuator_forcelimited[aid]),
                "force_range": [float(item) for item in model.actuator_forcerange[aid]],
            }
        body_maps = {}
        for canonical, native_name in plan.native_body_names.items():
            bid = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, native_name))
            parent_id = int(model.body_parentid[bid])
            body_maps[canonical] = {
                "native_name": native_name, "body_id": bid,
                "parent_body_id": parent_id,
                "parent_native_name": mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, parent_id),
            }
        site_maps = {}
        for canonical, native_name in plan.native_site_names.items():
            sid = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, native_name))
            site_maps[canonical] = {
                "native_name": native_name, "site_id": sid,
                "body_id": int(model.site_bodyid[sid]),
                "body_native_name": mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, int(model.site_bodyid[sid])),
            }
        tendon_maps = {}
        for canonical, native_name in plan.native_tendon_names.items():
            tid = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_TENDON, native_name))
            address, count = int(model.tendon_adr[tid]), int(model.tendon_num[tid])
            wraps = []
            for index in range(address, address + count):
                joint_id = int(model.wrap_objid[index])
                wraps.append({
                    "wrap_type": int(model.wrap_type[index]),
                    "joint_native_name": mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, joint_id),
                    "coefficient": float(model.wrap_prm[index]),
                })
            tendon_maps[canonical] = {"native_name": native_name, "tendon_id": tid, "wraps": wraps}
        excludes = []
        for signature in model.exclude_signature:
            body1, body2 = int(signature) >> 16, int(signature) & 0xFFFF
            names = [
                mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, body1),
                mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, body2),
            ]
            excludes.append(sorted(names))
        joint_order = [mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, index) for index in range(model.njnt)]
        actuator_order = [mj.mj_id2name(model, mj.mjtObj.mjOBJ_ACTUATOR, index) for index in range(model.nu)]
        body_order = [mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, index) for index in range(model.nbody)]
        collision_geoms = []
        for index in range(model.ngeom):
            collision_geoms.append({
                "native_name": mj.mj_id2name(model, mj.mjtObj.mjOBJ_GEOM, index),
                "body_native_name": mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, int(model.geom_bodyid[index])),
                "contype": int(model.geom_contype[index]),
                "conaffinity": int(model.geom_conaffinity[index]),
            })
        payload = {
            "schema_version": "fixed-attachment-model-receipt-v1",
            "provider": "mujoco", "backend": "cpu",
            "provider_build": self._fixed_attachment_provider_build,
            "runtime_identity": self._fixed_attachment_runtime_identity,
            "provider_materialization_id": self._provider_materialization_id,
            "task_artifact_sha256": self._artifact.identity_hash,
            "scene_identity_sha256": self._source.scene_definition.identity_hash,
            "assembly_identity_sha256": plan.logical_content_sha256,
            "attachment_plan_sha256": plan.identity_hash,
            "source_closure_sha256": self._source.source_closure_digest,
            "fixed_root": {
                "parent_entity_id": plan.parent_entity_id,
                "parent_root": f"{plan.parent_root.entity_id}/{plan.parent_root.frame_id}",
                "child_entity_id": plan.child_entity_id,
                "child_root": f"{plan.child_root.entity_id}/{plan.child_root.frame_id}",
                "parent_mount": f"{plan.parent_mount.entity_id}/{plan.parent_mount.frame_id}",
                "child_mount": f"{plan.child_mount.entity_id}/{plan.child_mount.frame_id}",
                "parent_site_from_child_root": plan.parent_site_from_child_root.to_mapping(),
                "root_policy": plan.root_policy,
            },
            "dimensions": dimensions,
            "native_body_order": body_order,
            "native_joint_order": joint_order,
            "native_actuator_order": actuator_order,
            "native_body_mappings": body_maps,
            "native_site_mappings": site_maps,
            "native_joint_mappings": joint_maps,
            "native_actuator_mappings": actuator_maps,
            "native_tendon_mappings": tendon_maps,
            "native_body_inverse": {value["native_name"]: key for key, value in body_maps.items()},
            "native_site_inverse": {value["native_name"]: key for key, value in site_maps.items()},
            "native_joint_inverse": {value["native_name"]: key for key, value in joint_maps.items()},
            "native_actuator_inverse": {value["native_name"]: key for key, value in actuator_maps.items()},
            "source_collision_policy": plan.collision_policy,
            "compiled_exclusions": sorted(excludes),
            "compiled_geoms": collision_geoms,
            "lowering": self._fixed_attachment_lowering,
        }
        payload["receipt_identity_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        return payload

    def _cache_completed_actuator_force(self):
        """Read force only when the admitted Controller state contract requires it."""
        if getattr(self, '_force_feedback_required', False):
            self._completed_actuator_force = self._data.actuator_force.copy()
            self._completed_actuator_ctrl = self._data.ctrl.copy()
            self._force_sample_sequence += 1
            from ...environment.types import ActuatorForceMeasurementV1
            actuator_index = self._open_actuators[0]
            signed_force = float(self._completed_actuator_force[actuator_index])
            actuator_ctrl = float(self._completed_actuator_ctrl[actuator_index])
            valid = math.isfinite(signed_force) and math.isfinite(actuator_ctrl)
            native_sample_time = (
                0.0 if self._native_steps == 0
                else float(self._native_steps - 1) * self._artifact.timebase.physics_dt
            )
            self._completed_force_measurement = ActuatorForceMeasurementV1(
                schema_version='task-env-actuator-force-sample-v1',
                source_generation=1,
                sample_sequence=self._force_sample_sequence,
                state_revision=self._native_steps,
                configuration_revision=self._force_configuration_revision,
                native_step_index=self._native_steps,
                phase='reset_forward' if self._native_steps == 0 else 'native_step_pre_integration',
                valid=valid,
                force_unit='N',
                invalid_reason=None if valid else 'MuJoCo completed actuator-force cache is non-finite',
                episode_id=str(self._episode_id) if self._episode_id is not None else None,
                reset_sample_id=str(self._reset_sample_id) if self._reset_sample_id is not None else None,
                actuator_id=str(self._source.open_actuators[0]),
                actuator_ctrl=actuator_ctrl if valid else None,
                signed_force_N=signed_force if valid else None,
                native_sample_time_s=native_sample_time,
            )
        else:
            self._completed_actuator_force = None
            self._completed_actuator_ctrl = None
            self._completed_force_measurement = None

    def _validate_canonical_scene_model(self):
        scene = self._source.scene_definition
        if scene is None:
            return
        if self._source.fixed_attachment_plan is not None:
            self._validate_fixed_attachment_scene_model()
            return
        frame_ids = {
            frame.frame_id
            for frame in scene.frames or ()
            if frame.frame_kind == 'runtime'
        }
        for name in sorted(frame_ids):
            body_id = self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_BODY, name)
            site_id = self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_SITE, name)
            if body_id < 0 and site_id < 0:
                raise ValueError(f'canonical runtime Frame {name!r} is absent from the MuJoCo model')

        expected_joint_type = {
            'revolute': self._mj.mjtJoint.mjJNT_HINGE,
            'continuous': self._mj.mjtJoint.mjJNT_HINGE,
            'prismatic': self._mj.mjtJoint.mjJNT_SLIDE,
            'floating': self._mj.mjtJoint.mjJNT_FREE,
        }
        for articulation in scene.articulations or ():
            for joint in articulation.joints:
                if joint.kind == 'fixed':
                    expected_type = None
                else:
                    expected_type = expected_joint_type.get(joint.kind)
                    if expected_type is None:
                        raise ValueError(
                            f'MuJoCo D01b does not admit canonical Joint kind {joint.kind!r}'
                        )
                try:
                    parent_id = self._model.body(joint.parent_frame.frame_id).id
                    child_id = self._model.body(joint.child_frame.frame_id).id
                except Exception as exc:
                    raise ValueError(
                        f'canonical Joint {joint.joint_id!r} endpoints must resolve to MuJoCo bodies'
                    ) from exc
                if int(self._model.body_parentid[child_id]) != parent_id:
                    raise ValueError(
                        f'canonical Joint {joint.joint_id!r} parent/child topology differs in MuJoCo'
                    )
                if expected_type is None:
                    continue
                joint_id = self._mj.mj_name2id(
                    self._model, self._mj.mjtObj.mjOBJ_JOINT, joint.joint_id,
                )
                if joint_id < 0:
                    raise ValueError(f'canonical Joint {joint.joint_id!r} is absent from MuJoCo')
                if (
                    self._model.jnt_type[joint_id] != expected_type
                    or int(self._model.jnt_bodyid[joint_id]) != child_id
                ):
                    raise ValueError(
                        f'canonical Joint {joint.joint_id!r} type/child binding differs in MuJoCo'
                    )
                if joint.kind == 'floating':
                    matches = [semantic for semantic, native in self._source.free_joints.items()
                               if native == joint.joint_id
                               and self._artifact.legacy_frame_bindings.get(semantic) == joint.child_frame]
                    if len(matches) != 1:
                        raise ValueError('canonical floating Joint differs from its source binding')
                    continue
                if not np.allclose(
                    self._model.jnt_axis[joint_id], joint.axis, rtol=0.0, atol=1.0e-9,
                ):
                    raise ValueError(
                        f'canonical Joint {joint.joint_id!r} axis differs in MuJoCo'
                    )

    def _validate_fixed_attachment_scene_model(self):
        """Bind the exact fixed-pair Scene to the compiled MjSpec model."""
        plan, model, mj = self._source.fixed_attachment_plan, self._model, self._mj
        expected_dimensions = {
            "nq": 9, "nv": 9, "nu": 8, "njnt": 9, "nsite": 1,
            "nmesh": 67, "ngeom": 81, "neq": 1, "ntendon": 1,
            "nexclude": 3, "nbody": 13,
        }
        actual_dimensions = {
            "nq": int(model.nq), "nv": int(model.nv), "nu": int(model.nu),
            "njnt": int(model.njnt), "nsite": int(model.nsite),
            "nmesh": int(model.nmesh), "ngeom": int(model.ngeom),
            "neq": int(model.neq), "ntendon": int(model.ntendon),
            "nexclude": int(model.nexclude), "nbody": int(model.nbody),
        }
        if actual_dimensions != expected_dimensions:
            raise ValueError(f"fixed Attachment compiled dimensions differ from the source receipt: {actual_dimensions}")
        if any(int(kind) == int(mj.mjtJoint.mjJNT_FREE) for kind in model.jnt_type):
            raise ValueError("fixed Attachment model unexpectedly contains a free joint")
        order_variant = plan.parent_asset_version == "menagerie-b846dd12-r06b-order-v1"
        expected_hand_fingers = (
            ["probe_hand_right_finger", "probe_hand_left_finger"] if order_variant
            else ["probe_hand_left_finger", "probe_hand_right_finger"]
        )
        expected_bodies = [
            "world", "link0", "link1", "link2", "link3", "link4", "link5", "link6",
            "link7", "attachment", "probe_hand_hand", *expected_hand_fingers,
        ]
        actual_bodies = [mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, index) for index in range(model.nbody)]
        if actual_bodies != expected_bodies:
            raise ValueError(f"fixed Attachment body order differs from the source oracle: {actual_bodies}")
        expected_joints = [
            *(f"joint{index}" for index in range(1, 8)),
            *(('probe_hand_finger_joint2', 'probe_hand_finger_joint1') if order_variant
              else ('probe_hand_finger_joint1', 'probe_hand_finger_joint2')),
        ]
        actual_joints = [mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, index) for index in range(model.njnt)]
        if actual_joints != expected_joints:
            raise ValueError(f"fixed Attachment Joint order differs from the source oracle: {actual_joints}")
        expected_arm_actuators = (range(7, 0, -1) if order_variant else range(1, 8))
        expected_actuators = [
            *(f"actuator{index}" for index in expected_arm_actuators), "probe_hand_actuator8",
        ]
        actual_actuators = [
            mj.mj_id2name(model, mj.mjtObj.mjOBJ_ACTUATOR, index) for index in range(model.nu)
        ]
        if actual_actuators != expected_actuators:
            raise ValueError(f"fixed Attachment Actuator order differs from the source oracle: {actual_actuators}")
        top_roots = [
            mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, index)
            for index, parent_id in enumerate(model.body_parentid)
            if index > 0 and int(parent_id) == 0
        ]
        if top_roots != ["link0"]:
            raise ValueError(f"fixed Attachment must compile exactly one physical root, found {top_roots}")
        for canonical, native_name in plan.native_body_names.items():
            body_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, native_name))
            if body_id <= 0 or mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, body_id) != native_name:
                raise ValueError(f"fixed Attachment Body mapping failed for {canonical!r}")
        parent_site_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, plan.parent_mount_site_name))
        child_root_id = int(mj.mj_name2id(
            model, mj.mjtObj.mjOBJ_BODY, plan.native_body_names[
                f"{plan.child_root.entity_id}/{plan.child_root.frame_id}"
            ],
        ))
        mount_parent_id = int(model.site_bodyid[parent_site_id])
        if int(model.body_parentid[child_root_id]) != mount_parent_id:
            raise ValueError("fixed child root is not physically attached below the parent mount Site body")

        expected_limits = {
            "joint1": (-2.8973, 2.8973), "joint2": (-1.7628, 1.7628),
            "joint3": (-2.8973, 2.8973), "joint4": (-3.0718, -0.0698),
            "joint5": (-2.8973, 2.8973), "joint6": (-0.0175, 3.7525),
            "joint7": (-2.8973, 2.8973),
            "probe_hand_finger_joint1": (0.0, 0.04),
            "probe_hand_finger_joint2": (0.0, 0.04),
        }
        for canonical, native_name in plan.native_joint_names.items():
            jid = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, native_name))
            native_range = tuple(float(value) for value in model.jnt_range[jid])
            if (not bool(model.jnt_limited[jid]) or native_range != expected_limits[native_name]):
                raise ValueError(f"fixed Attachment Joint limits differ from source for {native_name!r}")
            if native_name.startswith("probe_hand_") and int(model.jnt_type[jid]) != int(mj.mjtJoint.mjJNT_SLIDE):
                raise ValueError("fixed Attachment Hand finger Joint is not a prismatic source Joint")
            if not native_name.startswith("probe_hand_") and int(model.jnt_type[jid]) != int(mj.mjtJoint.mjJNT_HINGE):
                raise ValueError("fixed Attachment Arm Joint is not a revolute source Joint")

        expected_arm_ctrl = {
            "actuator1": (-2.8973, 2.8973), "actuator2": (-1.7628, 1.7628),
            "actuator3": (-2.8973, 2.8973), "actuator4": (-3.0718, -0.0698),
            "actuator5": (-2.8973, 2.8973), "actuator6": (-0.0175, 3.7525),
            "actuator7": (-2.8973, 2.8973), "probe_hand_actuator8": (0.0, 255.0),
        }
        for canonical, native_name in plan.native_actuator_names.items():
            aid = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, native_name))
            if not bool(model.actuator_ctrllimited[aid]) or tuple(
                float(value) for value in model.actuator_ctrlrange[aid]
            ) != expected_arm_ctrl[native_name]:
                raise ValueError(f"fixed Attachment Actuator ctrlrange differs from source for {native_name!r}")
            target_id = int(model.actuator_trnid[aid, 0])
            if native_name == "probe_hand_actuator8":
                if (int(model.actuator_trntype[aid]) != int(mj.mjtTrn.mjTRN_TENDON)
                        or mj.mj_id2name(model, mj.mjtObj.mjOBJ_TENDON, target_id) != "probe_hand_split"):
                    raise ValueError("fixed Attachment Hand actuator lost its source split-tendon transmission")
            elif (int(model.actuator_trntype[aid]) != int(mj.mjtTrn.mjTRN_JOINT)
                  or mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, target_id)
                  != native_name.replace("actuator", "joint")):
                raise ValueError(f"fixed Attachment Arm actuator transmission differs for {native_name!r}")

        tendon_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_TENDON, "probe_hand_split"))
        tendon_address, tendon_count = int(model.tendon_adr[tendon_id]), int(model.tendon_num[tendon_id])
        wraps = []
        for index in range(tendon_address, tendon_address + tendon_count):
            wraps.append((
                int(model.wrap_type[index]),
                mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, int(model.wrap_objid[index])),
                float(model.wrap_prm[index]),
            ))
        if wraps != [
            (int(mj.mjtWrap.mjWRAP_JOINT), "probe_hand_finger_joint1", 0.5),
            (int(mj.mjtWrap.mjWRAP_JOINT), "probe_hand_finger_joint2", 0.5),
        ]:
            raise ValueError(f"fixed Attachment split tendon wraps differ from source: {wraps}")
        if (int(model.eq_type[0]) != int(mj.mjtEq.mjEQ_JOINT)
                or {int(model.eq_obj1id[0]), int(model.eq_obj2id[0])} != {
                    int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, "probe_hand_finger_joint1")),
                    int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, "probe_hand_finger_joint2")),
                }):
            raise ValueError("fixed Attachment Hand finger equality differs from the exact source pair")

        compiled_exclusions = set()
        for signature in model.exclude_signature:
            body1, body2 = int(signature) >> 16, int(signature) & 0xFFFF
            compiled_exclusions.add(tuple(sorted((
                mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, body1),
                mj.mj_id2name(model, mj.mjtObj.mjOBJ_BODY, body2),
            ))))
        expected_exclusions = {
            ("link0", "link1"), ("probe_hand_hand", "probe_hand_left_finger"),
            ("probe_hand_hand", "probe_hand_right_finger"),
        }
        if compiled_exclusions != expected_exclusions:
            raise ValueError(f"fixed Attachment compiled source exclusions differ: {compiled_exclusions}")
        if not any(int(value) != 0 for value in model.geom_contype) or not any(
            int(value) != 0 for value in model.geom_conaffinity
        ):
            raise ValueError("fixed Attachment collision source was globally disabled")


    def _addresses(self, name, *, free):
        joint = self._model.joint(name).id
        joint_type = int(self._model.jnt_type[joint])
        allowed = ((int(self._mj.mjtJoint.mjJNT_FREE),) if free else
                   (int(self._mj.mjtJoint.mjJNT_HINGE), int(self._mj.mjtJoint.mjJNT_SLIDE)))
        if joint_type not in allowed:
            raise ValueError('unsupported source joint representation')
        return int(self._model.jnt_qposadr[joint]), int(self._model.jnt_dofadr[joint])

    def reset(self, sample):
        if self._mixed_actuator_plan is not None:
            from ...artifacts import ResetSampleV1
            if type(sample) is not ResetSampleV1:
                raise TypeError('source-bound mixed actuator session requires ResetSampleV1 before native reset')
            return self._reset_mixed_actuator(sample)
        from ...artifacts.execution import ResetSample, ResetSampleV1
        physical_sample = (type(sample) is ResetSampleV1 and
            sample.control_policy == 'named_physical_effort_by_source_v1')
        if type(sample) is not ResetSample and not physical_sample:
            raise TypeError('MuJoCo RuntimeSession requires an admitted reset sample')
        self._validate_sample(sample)
        if physical_sample:
            self._preflight_physical_reset(sample)
        external = getattr(self, '_external_com_port', None)
        if external is not None:
            external.preflight_reset()
            external.finish()
        physical_port = getattr(self, '_physical_port', None)
        if physical_port is not None:
            if (np.any(self._data.xfrc_applied)
                    or (physical_port.pending is None and np.any(self._data.qfrc_applied))
                    or (physical_port.pending is not None
                        and not np.array_equal(self._data.qfrc_applied, physical_port.pending_values))):
                raise RuntimeError('physical reset cannot clear a foreign force buffer')
            if physical_port.pending is not None:
                physical_port.finish_interval()
        self._begin_reset()
        self._pending_position_sequence = None
        self._last_position_sequence_applied = None
        self._last_position_sequence_progress = None
        self._last_typed_force_publication = None
        self._mj.mj_resetData(self._model, self._data)
        self._native_steps = 0
        self._force_sample_sequence = 0
        self._force_configuration_revision = 0
        self._last_force_limit_N = None
        self._completed_actuator_force = None
        self._completed_actuator_ctrl = None
        self._completed_force_measurement = None
        for name, value in sample.joint_position.items():
            self._data.qpos[self._joint_addresses[name][0]] = value
        for name, requested in sample.poses_world.items():
            address = self._free_addresses[name][0]
            self._data.qpos[address:address+7] = (*requested.position, *requested.quaternion_wxyz)
        self._data.qvel[:] = 0
        if physical_sample:
            for name, value in sample.joint_velocity.items():
                self._data.qvel[self._joint_addresses[name][1]] = value
        self._data.act[:] = 0
        for name, actuator in self._target_actuators.items():
            self._data.ctrl[actuator] = sample.joint_position[name]
        for actuator in self._open_actuators:
            self._data.ctrl[actuator] = self._model.actuator_ctrlrange[actuator, 1]
        if self._source.fixed_attachment_plan is not None:
            self._data.ctrl[self._open_actuators[0]] = (
                255.0 * self._source.fixed_attachment_plan.reset_hand_opening_m / 0.08
            )
        self._current_ctrl = self._data.ctrl.copy()
        self._mj.mj_forward(self._model, self._data)
        if self._source.fixed_attachment_plan is not None:
            self._fixed_forward_calls += 1
        realized = self._realized(sample)
        self._cache_completed_actuator_force()
        return realized

    def _preflight_physical_reset(self, sample):
        self._validate_sample(sample)
        if sample.control_policy != 'named_physical_effort_by_source_v1':
            raise ValueError('physical reset requires the named effort policy')
        for name, value in sample.joint_position.items():
            joint = int(self._model.joint(self._source.joints[name]).id)
            if bool(self._model.jnt_limited[joint]):
                low, high = self._model.jnt_range[joint]
                if not float(low) <= float(value) <= float(high):
                    raise ValueError(f'physical reset joint position exceeds source limits: {name}')

    def _preflight_mixed_actuator_reset(self, sample):
        """Validate a source-bound reset completely before changing session state."""
        from ...artifacts import ResetSampleV1

        if type(sample) is not ResetSampleV1:
            raise TypeError('mixed actuator mixed materialization requires ResetSampleV1')
        self._validate_sample(sample)
        if self._mixed_fault is not None:
            raise RuntimeError('mixed actuator MuJoCo session is fault-latched')
        model, data, mj = self._model, self._data, self._mj
        # Every name/value/range is checked before the first mutable native write.
        if (set(sample.joint_position) != set(self._joint_addresses)
                or set(sample.joint_velocity) != set(self._joint_addresses)
                or set(sample.poses_world) != set(self._free_addresses)
                or set(sample.free_joint_velocity) != set(self._free_addresses)
                or set(sample.fixture_pose_world) != set(self._source.fixture_bodies)):
            raise ValueError('mixed actuator ResetSampleV1 does not cover the compiled source layout')
        for semantic, value in sample.joint_position.items():
            qpos, _ = self._joint_addresses[semantic]
            native_name = self._source.joints[semantic]
            jid = int(model.joint(native_name).id)
            if bool(model.jnt_limited[jid]):
                low, high = (float(item) for item in model.jnt_range[jid])
                if not low <= float(value) <= high:
                    raise ValueError(f'mixed actuator reset position exceeds source joint limits: {semantic}')
            if not math.isfinite(float(sample.joint_velocity[semantic])):
                raise ValueError(f'mixed actuator reset velocity is non-finite: {semantic}')
        for semantic, pose_value in sample.fixture_pose_world.items():
            body_id = self._bodies[semantic]
            if int(model.body_parentid[body_id]) != 0:
                raise ValueError(f'mixed actuator fixture root is not a world child: {semantic}')
            pose_value.validate()
        for semantic, pose_value in sample.poses_world.items():
            pose_value.validate()
            velocity = sample.free_joint_velocity[semantic]
            if len(velocity) != 6 or any(not math.isfinite(float(item)) for item in velocity):
                raise ValueError(f'mixed actuator free-body velocity is invalid: {semantic}')
        for semantic, aid in self._position_actuators.items():
            value = sample.joint_position[semantic]
            low, high = (float(item) for item in model.actuator_ctrlrange[aid])
            if not low <= float(value) <= high:
                raise ValueError(f'mixed actuator initial position target exceeds source actuator range: {semantic}')
        return model, data, mj

    def _preflight_reset_plan_sample(self, sample):
        if self._mixed_actuator_plan is not None:
            self._preflight_mixed_actuator_reset(sample)

    def _reset_mixed_actuator(self, sample):
        """Apply the exact v1 time, qvel, free-root, and fixture reset in one pass."""
        from ...artifacts import ResetReadbackV1

        model, data, mj = self._preflight_mixed_actuator_reset(sample)

        # Preserve an existing valid episode when schema, source, names or
        # ranges fail preflight. The reset gate changes only when the complete
        # source-bound sample is ready for its first native write.
        self._begin_reset()
        try:
            mj.mj_resetData(model, data)
            self._native_steps = 0
            self._reset_count += 1
            self._preprocess_calls = 0
            self._forward_calls = 0
            self._reset_time_origin = float(sample.simulation_time_s)
            # Source-bound ResetSampleV1 declares the non-integrating native
            # preprocessing and restore order before this single reset pass.
            mj.mj_step1(model, data)
            self._preprocess_calls += 1
            for semantic, fixture_pose in sample.fixture_pose_world.items():
                body_id = self._bodies[semantic]
                model.body_pos[body_id, :] = fixture_pose.position
                model.body_quat[body_id, :] = fixture_pose.quaternion_wxyz
            # ResetSampleV1 fixture roots are applied after MJCF compilation.
            # Refresh the optional model fingerprints so post-reset admission
            # observes the same transforms LIBERO writes onto its compiled model.
            self._compiled_model_physics_fingerprint_v1_cache = None
            size_model = getattr(mj, 'mj_sizeModel', None)
            save_model = getattr(mj, 'mj_saveModel', None)
            if callable(size_model) and callable(save_model):
                try:
                    model_binary = np.zeros(int(size_model(model)), dtype=np.uint8)
                    save_model(model, buffer=model_binary)
                    self._compiled_model_options_receipt_v1['compiled_model_binary_sha256'] = (
                        hashlib.sha256(model_binary.tobytes()).hexdigest()
                    )
                except (AttributeError, TypeError, ValueError, RuntimeError):
                    self._compiled_model_options_receipt_v1['compiled_model_binary_sha256'] = None
            for semantic, sampled_pose in sample.sampled_poses_world.items():
                qpos, dof = self._free_addresses[semantic]
                data.qpos[qpos:qpos + 7] = (*sampled_pose.position, *sampled_pose.quaternion_wxyz)
                data.qvel[dof:dof + 6] = 0.0
            # Restore the complete source-bound scalar/free state after task
            # placements; fixture root transforms remain sampler-owned.
            for semantic, value in sample.joint_position.items():
                qpos, dof = self._joint_addresses[semantic]
                data.qpos[qpos] = float(value)
                data.qvel[dof] = float(sample.joint_velocity[semantic])
            for semantic, pose_value in sample.poses_world.items():
                qpos, dof = self._free_addresses[semantic]
                data.qpos[qpos:qpos + 7] = (*pose_value.position, *pose_value.quaternion_wxyz)
                data.qvel[dof:dof + 6] = sample.free_joint_velocity[semantic]
            data.time = self._reset_time_origin
            data.ctrl[:] = 0.0
            for semantic, actuator_id in self._position_actuators.items():
                data.ctrl[actuator_id] = float(sample.joint_position[semantic])
            self._current_ctrl = data.ctrl.copy()
            mj.mj_forward(model, data)
            self._forward_calls = 1
            self._mixed_consumed_boundaries.clear()
            self._mixed_pending_target = None
            realized = self._realized(sample)
            self._initialize_physical_monitor()
            joints = {name: float(data.qpos[address[0]])
                      for name, address in self._joint_addresses.items()}
            velocities = {name: float(data.qvel[address[1]])
                          for name, address in self._joint_addresses.items()}
            free_poses = {
                name: pose(data.qpos[qpos:qpos + 3], data.qpos[qpos + 3:qpos + 7])
                for name, (qpos, _) in self._free_addresses.items()
            }
            free_velocities = {
                name: tuple(float(value) for value in data.qvel[dof:dof + 6])
                for name, (_, dof) in self._free_addresses.items()
            }
            fixture_poses = {
                name: pose(data.xpos[body_id], data.xquat[body_id])
                for name, body_id in ((key, self._bodies[key]) for key in self._source.fixture_bodies)
            }
            receipt = ResetReadbackV1(
                schema_version='runtime-reset-readback-v1',
                source_id=self._source.scene_source.source_id,
                source_closure_digest=self._source.source_closure_digest,
                provider_materialization_id=self._provider_materialization_id,
                episode_id=self._episode_id, reset_sample_id=self._reset_sample_id,
                simulation_time_s=float(data.time), joint_position=joints,
                joint_velocity=velocities, poses_world=free_poses,
                free_joint_velocity=free_velocities,
                free_joint_velocity_frame='mujoco_world_linear_local_angular_v1',
                fixture_pose_world=fixture_poses,
                native_step_count=int(self._native_steps),
                preprocess_call_count=int(self._preprocess_calls),
                forward_call_count=int(self._forward_calls),
            )
            receipt.validate()
            if (receipt.joint_position != sample.joint_position
                    or receipt.joint_velocity != sample.joint_velocity
                    or receipt.free_joint_velocity != sample.free_joint_velocity
                    or receipt.simulation_time_s != sample.simulation_time_s):
                raise ValueError('mixed actuator reset readback does not match the frozen row receipt')
            for name, expected in sample.fixture_pose_world.items():
                actual = receipt.fixture_pose_world[name]
                if (not np.allclose(actual.position, expected.position, rtol=0.0, atol=1e-12)
                        or not np.allclose(actual.quaternion_wxyz, expected.quaternion_wxyz,
                                           rtol=0.0, atol=1e-12)):
                    raise ValueError(f'mixed actuator fixture readback differs from sampled root pose: {name}')
            self._last_reset_readback_v1 = receipt
            self._assert_physical_monitor_clean_at_reset()
            return realized
        except BaseException as error:
            self._mixed_fault = {'phase': 'reset', 'error': f'{type(error).__name__}: {error}'}
            self._reset_done = False
            raise

    def _snapshot_with_native_free_joints(self):
        self._require_reset()
        data = self._data
        positions = {name: float(data.qpos[address[0]]) for name, address in self._joint_addresses.items()}
        velocities = {name: float(data.qvel[address[1]]) for name, address in self._joint_addresses.items()}
        poses = {name: pose(data.xpos[index], data.xquat[index]) for name, index in self._bodies.items()}
        for name, index in self._frames.items():
            quaternion = np.zeros(4)
            self._mj.mju_mat2Quat(quaternion, data.site_xmat[index])
            poses[name] = pose(data.site_xpos[index], quaternion)
        time = data.time
        if self._mixed_actuator_plan is not None:
            elapsed = float(data.time) - self._reset_time_origin
            expected = self._native_steps * self._artifact.timebase.physics_dt
            bound = (self._native_steps + 2) * max(
                math.ulp(float(data.time)), math.ulp(self._reset_time_origin),
                math.ulp(expected), math.ulp(self._artifact.timebase.physics_dt),
            )
            if not math.isfinite(elapsed) or abs(elapsed - expected) > bound:
                raise ValueError('mixed actuator native/reset-origin clock or integration count mismatch')
            if self._inner_interval_active:
                # The physics-rate mixed seam publishes fresh owned snapshots
                # between outer evaluation boundaries.  At the interval's
                # first and final substep boundaries, use the canonical outer
                # clock so a prepared outer target and its first native apply
                # share the exact same timestamp.  MuJoCo accumulates dt (for
                # example, 25 * 0.002 may be 0.05000000000000003), while the
                # ordinary public boundary is control_step * control_dt.
                substeps = int(self._artifact.timebase.control_substeps)
                completed_in_interval = self._native_steps - self._control_step * substeps
                if not 0 <= completed_in_interval <= substeps:
                    raise ValueError('mixed actuator substep clock escaped its active outer interval')
                if completed_in_interval == 0:
                    time = self._control_step * self._artifact.timebase.control_dt
                elif completed_in_interval == substeps:
                    time = (self._control_step + 1) * self._artifact.timebase.control_dt
                else:
                    time = elapsed
            else:
                if self._native_steps != self._control_step * self._artifact.timebase.control_substeps:
                    raise ValueError('mixed actuator native/canonical step-count mismatch')
                time = self._control_step * self._artifact.timebase.control_dt
        elif self._artifact.timebase.control_substeps > 1 and not self._inner_interval_active:
            if self._native_steps != self._control_step * self._artifact.timebase.control_substeps:
                raise ValueError('MuJoCo native/canonical step-count mismatch')
            expected = self._native_steps * self._artifact.timebase.physics_dt
            # Standard binary64 summation roundoff bound, not a physics tolerance.
            nu = self._native_steps * 2.0**-53
            if nu >= 1:
                raise ValueError('native clock accumulation bound unavailable')
            bound = nu / (1.0 - nu) * abs(expected) + math.ulp(expected)
            self._native_time_audit = {'native_time_s': float(data.time),
                'completed_native_steps': self._native_steps, 'expected_native_elapsed_s': expected,
                'binary64_summation_roundoff_bound_s': bound}
            if not math.isfinite(data.time) or abs(data.time - expected) > bound:
                raise ValueError('MuJoCo measured native time/count mismatch')
            time = self._control_step * self._artifact.timebase.control_dt
        elif self._inner_interval_active:
            time = float(data.time)
        state = self._state(positions, velocities, poses, time)
        free_joint_native = {
            name: (
                tuple(float(value) for value in data.qpos[qpos:qpos + 7]),
                tuple(float(value) for value in data.qvel[dof:dof + 6]),
            )
            for name, (qpos, dof) in self._free_addresses.items()
        }
        return state, free_joint_native

    def snapshot(self):
        self._require_reset()
        return self._snapshot_with_native_free_joints()[0]

    def control_feedback(self, state, *, actuator_force=None):
        from .control import feedback_value
        self._require_reset()
        if not hasattr(self, '_control_binding'):
            raise ValueError('control session admission required')
        if not getattr(self, '_force_feedback_required', False):
            raise ValueError('actuator-force feedback is not admitted for this Controller profile')
        if self._completed_actuator_force is None or self._completed_force_measurement is None:
            raise ValueError('MuJoCo required actuator-force cache is unavailable')
        measurement = self._completed_force_measurement
        if not measurement.valid or measurement.signed_force_N is None:
            raise ValueError(
                'MuJoCo required actuator-force cache is invalid: '
                f'{measurement.invalid_reason or "unknown reason"}'
            )
        if actuator_force is not None:
            raise ValueError('external typed actuator-force injection is not admitted')
        signed_force = float(measurement.signed_force_N)
        return feedback_value(self, state, signed_force)

    def _snapshot_typed_actuator_force_values(self, boundary, sample_clock, requirements):
        from ...artifacts import UnavailableStateValue
        return (), tuple(UnavailableStateValue(
            'unavailable-state-value-v1', item.field_name, item.subject_kind,
            item.entity_id, item.subject_id, item.sample_domain,
            'MuJoCo typed actuator-force publication is not admitted for this source',
        ) for item in requirements)

    def native_control_feedback_sample(self, state, feedback):
        """Publish provenance for the exact cached force used by control_feedback()."""
        from ...controllers.canonical.feedback import NativeControlFeedbackSampleV1
        from dataclasses import replace

        self._require_reset()
        index = self._open_actuators[0]
        if (not getattr(self, '_force_feedback_required', False)
                or self._completed_actuator_force is None
                or self._completed_actuator_ctrl is None
                or self._completed_force_measurement is None
                or not self._completed_force_measurement.valid):
            raise ValueError('MuJoCo native force sample is not admitted for this Controller profile')
        signed_force = float(self._completed_force_measurement.signed_force_N)
        measurement = replace(
            self._completed_force_measurement,
            evaluation_control_step=int(state.control_step),
            evaluation_simulation_time_s=float(state.simulation_time),
        )
        if feedback.gripper.closing_force_N != max(0.0, -signed_force):
            raise ValueError('MuJoCo native force sample differs from canonical Controller feedback')
        sample = NativeControlFeedbackSampleV1(
            'native-control-feedback-sample-v1', self._provider,
            self._provider_materialization_id, self._source.scene_source.source_id,
            self._source.source_closure_digest, str(self._episode_id),
            str(self._reset_sample_id), feedback, measurement,
        )
        sample.validate()
        return sample

    def configure_gravity_compensation(self):
        """Admit source-bound arm gravity on the exact affine MuJoCo drive.

        This profile composes the torque through a position-reference offset;
        it is not a general effort interface. The existing actuator's native
        force limit remains in effect and the actual adjusted target is acked.
        """
        if self._mixed_actuator_plan is not None or self._source.fixed_attachment_plan is not None:
            raise ValueError('gravity compensation does not admit mixed or attached sources')
        if self._reset_done or hasattr(self, '_gravity_model'):
            raise ValueError('gravity compensation must be configured once before reset')
        if int(self._model.opt.disableflags) & int(self._mj.mjtDisableBit.mjDSBL_GRAVITY):
            raise ValueError('gravity compensation requires native gravity to be enabled')
        from ...controllers.canonical.kinematics import PandaKinematics, PANDA_HAND_ORIGIN_TCP_V1
        source_xml = self._source.scene_source.xml
        model = PandaKinematics(source_xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
        bodies = model._compile_gravity_bodies()
        model._gravity_bodies = bodies
        base = int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_BODY, model._gravity_root_body_id))
        if base <= 0:
            raise ValueError('gravity compensation requires the exact named fixed Panda base')
        ancestor = base
        while ancestor:
            if int(self._model.body_jntnum[ancestor]) != 0:
                raise ValueError('gravity compensation requires a fixed base and fixed ancestors')
            ancestor = int(self._model.body_parentid[ancestor])
        indices = []
        for name, parent, fixed, joint, kind, axis, pivot, mass, com in bodies:
            body = int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_BODY, name))
            parent_id = int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_BODY, parent))
            native_rotation = np.empty(9, dtype=np.float64)
            if body >= 0:
                self._mj.mju_quat2Mat(native_rotation, self._model.body_quat[body])
            if (body < 0 or int(self._model.body_parentid[body]) != parent_id
                    or abs(float(self._model.body_mass[body]) - mass) > 1e-10
                    or not np.allclose(self._model.body_ipos[body], com, rtol=0, atol=1e-10)
                    or not np.allclose(self._model.body_pos[body], fixed[:3, 3], rtol=0, atol=1e-10)
                    or not np.allclose(native_rotation.reshape(3, 3), fixed[:3, :3], rtol=0, atol=1e-10)
                    or abs(float(self._model.body_gravcomp[body])) > 0):
                raise ValueError(f'gravity source/compiled mass, COM, parent or compensation differs: {name}')
            if joint:
                jid = int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_JOINT, joint))
                expected_type = self._mj.mjtJoint.mjJNT_HINGE if kind == 'hinge' else self._mj.mjtJoint.mjJNT_SLIDE
                if (jid < 0 or int(self._model.jnt_bodyid[jid]) != body
                        or int(self._model.jnt_type[jid]) != int(expected_type)
                        or not np.allclose(self._model.jnt_axis[jid], axis, rtol=0, atol=1e-10)
                        or not np.allclose(self._model.jnt_pos[jid], pivot, rtol=0, atol=1e-10)):
                    raise ValueError(f'gravity source/compiled joint differs: {joint}')
        for i in range(1, 8):
            semantic = f'panda-v1/joint{i}'
            if semantic not in self._target_actuators or semantic not in self._joint_addresses:
                raise ValueError('gravity compensation requires seven exact panda-v1 arm joints')
            actuator = self._target_actuators[semantic]
            gain = float(self._model.actuator_gainprm[actuator, 0])
            bias = self._model.actuator_biasprm[actuator]
            gear = self._model.actuator_gear[actuator]
            jid = int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_JOINT, self._source.joints[semantic]))
            if (int(self._model.actuator_trntype[actuator]) != int(self._mj.mjtTrn.mjTRN_JOINT)
                    or int(self._model.actuator_trnid[actuator, 0]) != jid
                    or int(self._model.actuator_dyntype[actuator]) != int(self._mj.mjtDyn.mjDYN_NONE)
                    or int(self._model.actuator_gaintype[actuator]) != int(self._mj.mjtGain.mjGAIN_FIXED)
                    or int(self._model.actuator_biastype[actuator]) != int(self._mj.mjtBias.mjBIAS_AFFINE)
                    or not np.isfinite(gain) or gain <= 0 or not np.isfinite(gear).all()
                    or abs(float(gear[0])) < 1e-12 or not np.allclose(gear[1:], 0, rtol=0, atol=0)
                    or abs(float(bias[0])) > 1e-12 or abs(float(bias[1]) + gain) > 1e-9
                    or not bool(self._model.actuator_ctrllimited[actuator])
                    or not bool(self._model.actuator_forcelimited[actuator])):
                raise ValueError(f'gravity compensation cannot represent this position actuator: {semantic}')
            indices.append((semantic, actuator, gain, float(gear[0])))
        for name in ('panda-v1/finger_joint1', 'panda-v1/finger_joint2'):
            if name not in self._joint_addresses:
                raise ValueError('gravity compensation requires both named finger positions')
        finger_ids = [int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_JOINT,
                      self._source.joints[f'panda-v1/finger_joint{i}'])) for i in (1, 2)]
        equalities = [i for i in range(self._model.neq)
                      if int(self._model.eq_type[i]) == int(self._mj.mjtEq.mjEQ_JOINT)
                      and bool(self._model.eq_active0[i])
                      and [int(self._model.eq_obj1id[i]), int(self._model.eq_obj2id[i])] == finger_ids
                      and np.allclose(self._model.eq_data[i, :5], [0, 1, 0, 0, 0], rtol=0, atol=1e-12)]
        if len(equalities) != 1 or len(self._open_actuators) != 1:
            raise ValueError('gravity compensation requires the exact coupled Panda finger equality and one tendon')
        opening = self._open_actuators[0]
        if {item[1] for item in indices} | {opening} != set(range(self._model.nu)):
            raise ValueError('gravity compensation refuses additional or shared source actuators')
        if int(self._model.actuator_trntype[opening]) != int(self._mj.mjtTrn.mjTRN_TENDON):
            raise ValueError('gravity compensation requires the Panda opening tendon')
        tendon = int(self._model.actuator_trnid[opening, 0])
        if not 0 <= tendon < self._model.ntendon:
            raise ValueError('gravity compensation opening tendon is unavailable')
        start, count = int(self._model.tendon_adr[tendon]), int(self._model.tendon_num[tendon])
        wraps = [(int(self._model.wrap_type[i]), int(self._model.wrap_objid[i]), float(self._model.wrap_prm[i]))
                 for i in range(start, start + count)]
        if wraps != [(int(self._mj.mjtWrap.mjWRAP_JOINT), finger_ids[0], 0.5),
                     (int(self._mj.mjtWrap.mjWRAP_JOINT), finger_ids[1], 0.5)]:
            raise ValueError('gravity compensation requires the exact symmetric opening tendon')
        if not np.isfinite(self._model.opt.gravity).all():
            raise ValueError('gravity compensation requires finite scene gravity')
        self._gravity_model = model
        self._gravity_base_body = base
        self._gravity_actuators = tuple(indices)
        self._gravity_interval_receipts = []

    @property
    def gravity_compensation_receipt(self):
        import copy
        if not hasattr(self, '_gravity_model'):
            return None
        return copy.deepcopy(self._gravity_interval_receipts)

    def _gravity_adjusted_targets(self, target):
        if np.any(self._data.qfrc_applied) or np.any(self._data.xfrc_applied):
            raise ValueError('gravity contribution refuses unaccounted applied force contributions')
        model = self._gravity_model
        q = [float(self._data.qpos[self._joint_addresses[f'panda-v1/joint{i}'][0]]) for i in range(1, 8)]
        fingers = [float(self._data.qpos[self._joint_addresses[f'panda-v1/finger_joint{i}'][0]]) for i in (1, 2)]
        rotation = np.asarray(self._data.xmat[self._gravity_base_body]).reshape(3, 3).copy()
        gravity = np.asarray(self._model.opt.gravity).copy()
        torque, finger_force = model.gravity_support(q, fingers, gravity, rotation, include_fingers=True)
        # The current Panda hand has one equality-coupled tendon, not two
        # independent effort actuators. Equal travel is gravity-neutral only
        # when the sum of the two finger loads vanishes. Fail closed rather
        # than silently pretending to compensate an unrepresentable load.
        if abs(float(np.sum(finger_force))) > 1e-9:
            raise ValueError('gravity compensation cannot represent net coupled finger gravity')
        rows, adjusted = [], {}
        for (semantic, actuator, gain, gear), support in zip(self._gravity_actuators, torque, strict=True):
            original = float(target.arm_servo_position[semantic])
            requested = original + float(support) / (gain * gear)
            low, high = self._model.actuator_ctrlrange[actuator]
            actual = float(np.clip(requested, low, high))
            adjusted[semantic] = actual
            rows.append({'joint': semantic, 'unit': 'N*m', 'computed_support_torque': float(support),
                         'original_position_target_rad': original, 'requested_position_target_rad': requested,
                         'applied_position_target_rad': actual, 'gain': gain, 'gear': gear,
                         'position_target_clamped': actual != requested})
        if not self._gravity_interval_receipts or self._gravity_interval_receipts[-1]['control_step'] != self._control_step:
            self._gravity_interval_receipts = []
        self._gravity_interval_receipts.append({
            'schema_version': 'panda-gravity-position-contribution-v1',
            'calculation_kind': 'source_body_mass_com_gravity_only',
            'source_closure_digest': self._source.source_closure_digest,
            'kinematics_source_sha256': model.source_sha256,
            'body_names': [item[0] for item in model._gravity_bodies],
            'provider_materialization_id': self.provider_materialization_id,
            'episode_id': self._episode_id, 'reset_sample_id': self._reset_sample_id,
            'control_step': self._control_step, 'native_step_before': self._native_steps,
            'target_identity_sha256': target.identity_hash,
            'joint_position_rad': q, 'finger_position_m': fingers,
            'finger_gravity_support_force_N': finger_force.tolist(),
            'coupled_finger_gravity_support_force_N': float(np.sum(finger_force)),
            'gravity_world_m_s2': gravity.tolist(), 'world_from_base_rotation': rotation.tolist(),
            'mapping': 'affine_position_target_offset_with_native_force_limits', 'joints': rows,
            'actual_actuator_force_samples': [],
        })
        return adjusted

    def _record_gravity_force_sample(self):
        if not getattr(self, '_gravity_interval_receipts', None):
            return
        values = []
        for semantic, actuator, _gain, gear in self._gravity_actuators:
            force = float(self._data.actuator_force[actuator])
            low, high = self._model.actuator_forcerange[actuator]
            values.append({'joint': semantic, 'native_actuator_force': force,
                           'generalized_actuator_torque_Nm': gear * force,
                           'force_limit_reached': bool(force <= low + 1e-9 or force >= high - 1e-9)})
        self._gravity_interval_receipts[-1]['actual_actuator_force_samples'].append({
            'native_step': self._native_steps, 'values': values,
            'provenance': 'provider_actuator_force_not_external_sensor',
        })

    def apply_control(self, target):
        if self._mixed_actuator_plan is not None:
            return self.apply_mixed_actuator_command(target)
        from .control import validate_target
        from ...controllers.canonical.contracts import AppliedCanonicalControl
        validate_target(self, target)
        gravity_targets = self._gravity_adjusted_targets(target) if hasattr(self, '_gravity_model') else None
        clipped = False
        realized = {}
        for name, requested in target.arm_servo_position.items():
            index = self._target_actuators[name]
            low, high = self._model.actuator_ctrlrange[index]
            candidate = requested if gravity_targets is None else gravity_targets[name]
            value = float(np.clip(candidate, low, high)) if self._model.actuator_ctrllimited[index] else candidate
            self._data.ctrl[index] = value
            realized[name] = value
            clipped = clipped or value != candidate or (gravity_targets is not None and any(
                row['position_target_clamped'] for row in self._gravity_interval_receipts[-1]['joints']))
        index = getattr(self, '_open_actuators_by_semantic', {}).get(
            target.gripper.semantic_id, self._open_actuators[0],
        )
        if self._last_force_limit_N != float(target.gripper.force_limit_N):
            self._force_configuration_revision += 1
            self._last_force_limit_N = float(target.gripper.force_limit_N)
        control_binding = getattr(self, '_position_control_bindings_by_semantic', {}).get(
            target.gripper.semantic_id, self._control_binding,
        )
        low, high = self._model.actuator_ctrlrange[index]
        opening = float(np.clip(target.gripper.servo_opening_m, 0, control_binding.opening_range_m))
        self._data.ctrl[index] = low + opening/control_binding.opening_range_m*(high-low)
        self._model.actuator_forcelimited[index] = 1
        self._model.actuator_forcerange[index] = (-target.gripper.force_limit_N, target.gripper.force_limit_N)
        self._current_ctrl = self._data.ctrl.copy()
        return AppliedCanonicalControl('applied-canonical-control-v0', target.identity_hash, 'mujoco',
            realized, opening, target.gripper.force_limit_N, clipped,
            ('named_position_servo_plus_source_gravity_offset_and_affine_tendon_force_limit_ZOH'
             if gravity_targets is not None else
             'named_position_servo_plus_affine_tendon_opening_force_limit_ZOH'))

    def bind_mixed_controller(self, controller_identity):
        if self._mixed_actuator_plan is None:
            raise RuntimeError('mixed Controller binding is restricted to the mixed actuator profile')
        if self._reset_done or hasattr(self, '_mixed_controller_identity'):
            raise RuntimeError('mixed Controller can be bound exactly once before reset')
        if type(controller_identity) is not str or not controller_identity.strip():
            raise ValueError('mixed Controller identity must be a nonempty stable value')
        if controller_identity != self._mixed_actuator_plan.controller_identity:
            raise ValueError('mixed Controller identity differs from the source-bound admission')
        self._mixed_controller_identity = controller_identity

    def apply_mixed_actuator_command(self, target):
        from ...controllers.canonical.contracts import (
            AppliedMixedActuatorCommandV1, MixedActuatorCommandV1,
        )
        self._require_reset()
        if self._mixed_fault is not None:
            raise RuntimeError('mixed actuator MuJoCo session is fault-latched')
        if type(target) is not MixedActuatorCommandV1:
            raise TypeError('mixed actuator RuntimeSession requires MixedActuatorCommandV1')
        target.validate()
        state = self.snapshot()
        if (not hasattr(self, '_mixed_controller_identity')
                or target.controller_identity != self._mixed_controller_identity
                or target.plan_identity_hash != self._mixed_actuator_plan.identity_hash
                or target.task_artifact_hash != self._artifact.identity_hash
                or target.source_id != self._source.scene_source.source_id
                or target.source_closure_digest != self._source.source_closure_digest
                or target.provider_materialization_id != self._provider_materialization_id
                or target.episode_id != self._episode_id
                or target.reset_sample_id != self._reset_sample_id
                or target.control_step != self._control_step
                or target.state_revision != self._state_revision
                or target.simulation_time_s != state.simulation_time):
            raise ValueError('mixed actuator target identity or boundary is stale/mismatched')
        boundary = (target.episode_id, target.reset_sample_id, target.control_step, target.state_revision)
        if boundary in self._mixed_consumed_boundaries or self._mixed_pending_target is not None:
            raise ValueError('mixed actuator target boundary was already consumed or is still pending')
        channels = {item.semantic_id: item for item in self._mixed_actuator_plan.channels}
        requested = dict(target.channel_values)
        units = dict(target.channel_units)
        if set(requested) != set(channels) or set(units) != set(channels):
            raise ValueError('mixed actuator command does not cover the declared source channels')
        values, applied_values = {}, {}
        for semantic, channel in channels.items():
            value = float(requested[semantic])
            aid = self._channel_actuator_ids[semantic]
            low, high = channel.control_range
            actual_low, actual_high = (float(item) for item in self._model.actuator_ctrlrange[aid])
            if (units[semantic] != channel.unit
                    or not math.isfinite(value)
                    or not low <= value <= high
                    or (actual_low, actual_high) != (low, high)):
                raise ValueError(f'mixed actuator command is outside its typed source range: {semantic}')
            values[aid] = value
            applied_values[semantic] = value
        try:
            for aid, value in values.items():
                self._data.ctrl[aid] = value
            self._current_ctrl = self._data.ctrl.copy()
        except BaseException as error:
            self._mixed_fault = {'phase': 'partial_control_apply', 'error': f'{type(error).__name__}: {error}'}
            raise
        self._mixed_consumed_boundaries.add(boundary)
        self._mixed_pending_target = target
        result = AppliedMixedActuatorCommandV1(
            'applied-mixed-actuator-command-v1', target.identity_hash, 'mujoco',
            applied_values, units, False,
            'source_bound_named_actuator_channels_zero_order_hold_v1',
        )
        result.validate()
        return result

    def read_contact_summary_v2(self, requested_pairs):
        from ...environment.types import ContactSummaryV2
        self._require_reset()
        if self._mixed_actuator_plan is None:
            raise RuntimeError('geom-group contact is limited to the admitted mixed actuator profile')
        normalized = []
        for pair in requested_pairs:
            if len(pair) != 2 or pair[0] == pair[1]:
                raise ValueError('contact query requires distinct entity pairs')
            normalized.append(tuple(sorted((str(pair[0]), str(pair[1])))))
        if len(set(normalized)) != len(normalized):
            raise ValueError('contact query contains duplicate/reversed entity pairs')
        requested = tuple(sorted(normalized))
        groups = self._source.contact_geom_groups
        if any(left not in groups or right not in groups for left, right in requested):
            return ContactSummaryV2.unavailable(
                source_id=self._source.scene_source.source_id,
                source_closure_digest=self._source.source_closure_digest,
                provider_materialization_id=self._provider_materialization_id,
                episode_id=self._episode_id, reset_sample_id=self._reset_sample_id,
                control_step=self._control_step, state_revision=self._state_revision,
                simulation_time_s=self.snapshot().simulation_time,
                requested_pairs=requested, reason='unknown_entity_or_geom_group',
            )
        counts = {f'{left}/{right}': 0 for left, right in requested}
        for index in range(int(self._data.ncon)):
            contact = self._data.contact[index]
            left_geom, right_geom = int(contact.geom1), int(contact.geom2)
            for left, right in requested:
                left_ids, right_ids = self._contact_geom_ids[left], self._contact_geom_ids[right]
                if ((left_geom in left_ids and right_geom in right_ids)
                        or (right_geom in left_ids and left_geom in right_ids)):
                    counts[f'{left}/{right}'] += 1
        return ContactSummaryV2(
            self._source.scene_source.source_id, self._source.source_closure_digest,
            self._provider_materialization_id, self._episode_id, self._reset_sample_id,
            self._control_step, self._state_revision, self.snapshot().simulation_time,
            requested, requested, counts,
            {name: tuple(values) for name, values in groups.items()},
        )

    def step_mixed_actuator_interval(self, command_factory):
        """Apply a fresh public-state mixed command for every native substep.

        The outer Evaluation/Recorder boundary remains one control interval.
        Each command is still checked by the normal named MixedActuatorCommand
        path; this method only owns its admitted MuJoCo 2 ms integration loop.
        """
        from ...controllers.canonical.contracts import (
            AppliedMixedActuatorCommandV1, MixedActuatorCommandV1,
        )

        self._require_reset()
        if self._mixed_actuator_plan is None:
            raise RuntimeError('stepwise mixed commands require the admitted mixed actuator profile')
        if self._mixed_fault is not None:
            raise RuntimeError('mixed actuator MuJoCo session is fault-latched')
        if not callable(command_factory):
            raise TypeError('mixed actuator interval requires a state-to-command factory')
        if self._mixed_pending_target is not None:
            raise RuntimeError('mixed actuator interval cannot start with a pending target')
        if self._inner_interval_active:
            raise RuntimeError('mixed actuator intervals cannot be nested')
        count = int(self._artifact.timebase.control_substeps)
        start_state = self.snapshot()
        start_revision = self._state_revision
        rows = []
        self._inner_interval_active = True
        try:
            for substep_index in range(count):
                before = self.snapshot()
                before_revision = self._state_revision
                target = command_factory(before, substep_index, count, before_revision)
                if type(target) is not MixedActuatorCommandV1:
                    raise TypeError('stepwise mixed Controller must return MixedActuatorCommandV1')
                applied = self.apply_mixed_actuator_command(target)
                if type(applied) is not AppliedMixedActuatorCommandV1:
                    raise TypeError('RuntimeSession returned an untyped mixed-control acknowledgement')
                pending = self._mixed_pending_target
                if pending is not target:
                    raise RuntimeError('mixed actuator substep lost its consumed target identity')
                self._mj.mj_step(self._model, self._data)
                self._native_steps += 1
                # mj_step integrates qpos after its forward pass, so named
                # transforms/contact geometry can still describe the previous
                # position until mj_forward refreshes derived state.
                self._mj.mj_forward(self._model, self._data)
                self._forward_calls += 1
                self._observe_physical_state(
                    phase='native_step', control_boundary=self._control_step + 1,
                    native_step=self._native_steps,
                )
                self._state_revision += 1
                self._mixed_pending_target = None
                after = self.snapshot()
                rows.append({
                    'substep_index': substep_index,
                    'target': target.to_mapping(),
                    'target_identity_sha256': target.identity_hash,
                    'applied': applied.to_mapping(),
                    'state_revision_before': before_revision,
                    'state_revision_after': self._state_revision,
                    'simulation_time_before_s': float(before.simulation_time),
                    'simulation_time_after_s': float(after.simulation_time),
                })
            self._mj.mj_forward(self._model, self._data)
            self._forward_calls += 1
            self._control_step += 1
            self._inner_interval_active = False
            result_state = self.snapshot()
            if (result_state.control_step != start_state.control_step + 1
                    or self._state_revision != start_revision + count
                    or self._native_steps != self._control_step * count):
                raise ValueError('stepwise mixed interval did not close on its declared outer/native boundary')
            return result_state, {
                'schema_version': 'mixed-actuator-stepwise-interval-receipt-v1',
                'provider_name': 'mujoco',
                'provider_materialization_id': self._provider_materialization_id,
                'episode_id': self._episode_id,
                'reset_sample_id': self._reset_sample_id,
                'start_control_step': int(start_state.control_step),
                'end_control_step': int(result_state.control_step),
                'start_state_revision': int(start_revision),
                'end_state_revision': int(self._state_revision),
                'native_substep_count': count,
                'physics_dt_s': float(self._artifact.timebase.physics_dt),
                'substeps': rows,
            }
        except BaseException as error:
            self._mixed_fault = {
                'phase': 'stepwise_interval',
                'error': f'{type(error).__name__}: {error}',
                'native_steps_completed': int(self._native_steps),
                'control_boundary': int(self._control_step),
                'substeps_completed': len(rows),
            }
            raise

    def stage_position_sequence(self, sequence, lowers):
        """Stage one preflighted Position schedule without touching native controls."""
        from .control_submission import PositionControlSequenceV1, PositionSequenceStagedV1
        receipt = getattr(self, '_last_scene_control_submission', None)
        if (type(sequence) is not PositionControlSequenceV1
                or getattr(self, '_prepared_position_sequence', None) is not sequence
                or type(receipt) is not dict or receipt.get('status') != 'pending'
                or receipt.get('inner_position_command_sha256',
                               receipt.get('inner_command_sha256')) != sequence.identity_hash
                or type(lowers) is not tuple or len(lowers) != len(sequence.slices)
                or any(not callable(lower) for lower in lowers)
                or getattr(self, '_pending_position_sequence', None) is not None):
            raise ValueError('Position schedule requires the pending common submission')
        sequence.validate()
        self._pending_position_sequence = (sequence, lowers, sequence.identity_hash)
        self._last_position_sequence_applied = None
        self._last_position_sequence_progress = {
            'schema_version': 'position-sequence-native-progress-v1',
            'sequence_sha256': sequence.identity_hash, 'status': 'staged',
            'attempted_target_sha256': [], 'acknowledged_target_sha256': [],
            'native_steps_attempted': 0, 'native_steps_completed': 0,
            'native_step_result_unknown': False,
        }
        return PositionSequenceStagedV1(sequence.identity_hash)

    def _apply_position_sequence_substep(self, pending, index, applied_results):
        sequence, lowers, admitted_hash = pending
        if sequence.identity_hash != admitted_hash:
            raise RuntimeError('Position sequence changed after submission')
        if not np.array_equal(self._data.ctrl, self._current_ctrl):
            raise RuntimeError('Position native control changed during sequence')
        for (start, _end, target), lower in zip(sequence.slices, lowers, strict=True):
            if index == start:
                progress = self._last_position_sequence_progress
                progress['attempted_target_sha256'].append(target.identity_hash)
                applied = lower()
                if applied.target_hash != target.target.identity_hash:
                    raise ValueError('Position sequence native acknowledgement differs')
                applied_results.append(applied)
                progress['acknowledged_target_sha256'].append(target.identity_hash)

    def step(self):
        self._require_reset()
        external = getattr(self, '_external_com_port', None)
        if external is not None and not external.authorized:
            raise RuntimeError('caller wrench requires an acknowledged interval submission')
        physical_port = getattr(self, '_physical_port', None)
        if physical_port is not None:
            if physical_port.pending is None:
                raise RuntimeError('physical interval requires exactly one fresh batch')
            pending_position = getattr(self, '_pending_position_sequence', None)
            position_applied = []
            try:
                for index in range(self._artifact.timebase.control_substeps):
                    if pending_position is not None:
                        self._apply_position_sequence_substep(pending_position, index, position_applied)
                    physical_port.refresh_substep()
                    if pending_position is not None:
                        self._last_position_sequence_progress['native_steps_attempted'] += 1
                    self._mj.mj_step(self._model, self._data)
                    if pending_position is not None:
                        self._last_position_sequence_progress['native_steps_completed'] += 1
                    self._native_steps += 1
                self._mj.mj_forward(self._model, self._data)
                self._control_step += 1
                self._state_revision += 1
                if pending_position is not None:
                    self._last_position_sequence_applied = tuple(position_applied)
                    self._last_position_sequence_progress['status'] = 'completed'
                return self.snapshot()
            except BaseException:
                if pending_position is not None:
                    progress = self._last_position_sequence_progress
                    progress['status'] = 'failed_partial'
                    progress['native_step_result_unknown'] = (
                        progress['native_steps_attempted'] > progress['native_steps_completed'])
                raise
            finally:
                self._pending_position_sequence = None
                physical_port.finish_interval()
        if self._mixed_actuator_plan is not None:
            if self._mixed_fault is not None:
                raise RuntimeError('mixed actuator MuJoCo session is fault-latched')
            if self._mixed_pending_target is None:
                raise RuntimeError('mixed actuator outer step requires exactly one fresh mixed target')
            try:
                for _ in range(self._artifact.timebase.control_substeps):
                    self._mj.mj_step(self._model, self._data)
                    self._native_steps += 1
                    self._observe_physical_state(
                        phase='native_step', control_boundary=self._control_step + 1,
                        native_step=self._native_steps,
                    )
                self._mj.mj_forward(self._model, self._data)
                self._forward_calls += 1
                self._control_step += 1
                self._state_revision += 1
                self._mixed_pending_target = None
                return self.snapshot()
            except BaseException as error:
                self._mixed_fault = {
                    'phase': 'outer_advance', 'error': f'{type(error).__name__}: {error}',
                    'native_steps_completed': int(self._native_steps),
                    'control_boundary': int(self._control_step),
                }
                raise
        pending_position = getattr(self, '_pending_position_sequence', None)
        position_applied = []
        try:
            for index in range(self._artifact.timebase.control_substeps):
                if pending_position is not None:
                    self._apply_position_sequence_substep(pending_position, index, position_applied)
                if external is not None:
                    external.refresh_substep()
                if pending_position is not None:
                    self._last_position_sequence_progress['native_steps_attempted'] += 1
                self._mj.mj_step(self._model, self._data)
                if pending_position is not None:
                    self._last_position_sequence_progress['native_steps_completed'] += 1
                self._native_steps += 1
                self._record_gravity_force_sample()
                self._cache_completed_actuator_force()
            self._mj.mj_forward(self._model, self._data)
            if self._source.fixed_attachment_plan is not None:
                self._fixed_forward_calls += 1
            self._control_step += 1
            self._state_revision += 1
            if pending_position is not None:
                self._last_position_sequence_applied = tuple(position_applied)
                self._last_position_sequence_progress['status'] = 'completed'
            return self.snapshot()
        except BaseException:
            if pending_position is not None:
                progress = self._last_position_sequence_progress
                progress['status'] = 'failed_partial'
                progress['native_step_result_unknown'] = (
                    progress['native_steps_attempted'] > progress['native_steps_completed'])
            raise
        finally:
            self._pending_position_sequence = None
            if external is not None:
                external.finish()

    def _step_physics_once(self):
        self._require_reset()
        self._mj.mj_step(self._model, self._data)
        self._native_steps += 1
        self._record_gravity_force_sample()
        self._cache_completed_actuator_force()
        self._mj.mj_forward(self._model, self._data)

    def _warning_counts(self):
        warnings = getattr(self._data, 'warning', ())
        counts = [int(item.number) for item in warnings]
        # The pinned 3.8.1 mjtWarning enum has seven entries (mjNWARNING).
        if len(counts) != 7 or any(value < 0 for value in counts):
            raise RuntimeError('pinned MuJoCo runtime must publish all seven warning counters')
        return counts

    def _initialize_physical_monitor(self):
        ranges = {}
        for semantic, (qpos, _dof) in self._joint_addresses.items():
            joint_id = int(self._mj.mj_name2id(
                self._model, self._mj.mjtObj.mjOBJ_JOINT, self._source.joints[semantic],
            ))
            if bool(self._model.jnt_limited[joint_id]):
                low, high = (float(value) for value in self._model.jnt_range[joint_id])
                ranges[semantic] = {
                    'joint_name': self._source.joints[semantic],
                    'qpos_address': int(qpos), 'range': [low, high],
                    'minimum_observed': float(self._data.qpos[qpos]),
                    'maximum_observed': float(self._data.qpos[qpos]),
                }
        if not ranges:
            raise ValueError('physical monitor requires at least one source-limited scalar joint')
        self._physical_monitor_tolerance = 1.0e-8
        tolerance_overrides = dict(getattr(
            self._source, 'task_local_joint_limit_tolerance_overrides', {},
        ))
        unknown_tolerances = set(tolerance_overrides) - set(ranges)
        if unknown_tolerances:
            raise ValueError(
                'task-local joint limit tolerances reference joints unavailable to the physical monitor: '
                f'{sorted(unknown_tolerances)}'
            )
        for semantic, row in ranges.items():
            row['tolerance'] = float(tolerance_overrides.get(semantic, self._physical_monitor_tolerance))
        self._physical_monitor = {
            'schema_version': 'physical-state-monitor-v1',
            'source_id': self._source.scene_source.source_id,
            'source_closure_digest': self._source.source_closure_digest,
            'canonical_xml_sha256': self._source.execution_source_receipt.canonical_xml_sha256,
            'provider_materialization_id': self._provider_materialization_id,
            'episode_id': self._episode_id,
            'reset_sample_id': self._reset_sample_id,
            'compiled_model_identity_sha256': hashlib.sha256(json.dumps(
                self._compiled_layout_receipt, sort_keys=True, separators=(',', ':'),
            ).encode()).hexdigest(),
            'joint_ranges': ranges,
            'maximum_excursion': 0.0,
            'maximum_excursion_by_semantic_id': {semantic: 0.0 for semantic in ranges},
            'joint_limit_excursions': [],
            'joint_limit_excursion_count': 0,
            'tolerance': self._physical_monitor_tolerance,
            'task_local_tolerance_overrides': tolerance_overrides,
            'first_violation': None,
            'warning_counts': self._warning_counts(),
            'samples_including_reset': 0,
            'status': 'pending',
        }
        self._observe_physical_state(phase='reset', control_boundary=0, native_step=0)

    def _observe_physical_state(self, *, phase, control_boundary, native_step):
        monitor = self._physical_monitor
        qpos = np.asarray(self._data.qpos)
        qvel = np.asarray(self._data.qvel)
        warning_counts = self._warning_counts()
        finite = bool(np.isfinite(qpos).all() and np.isfinite(qvel).all()
                      and math.isfinite(float(self._data.time)))
        if not finite and monitor['first_violation'] is None:
            monitor['first_violation'] = {
                'kind': 'non_finite_state', 'phase': phase,
                'control_boundary': int(control_boundary), 'native_step': int(native_step),
            }
        maximum_excursion = float(monitor['maximum_excursion'])
        maximum_by_semantic = monitor['maximum_excursion_by_semantic_id']
        raw_excursions = monitor['joint_limit_excursions']
        if finite:
            for semantic, row in monitor['joint_ranges'].items():
                value = float(qpos[row['qpos_address']])
                low, high = row['range']
                row['minimum_observed'] = min(float(row['minimum_observed']), value)
                row['maximum_observed'] = max(float(row['maximum_observed']), value)
                excursion = max(0.0, float(low) - value, value - float(high))
                maximum_excursion = max(maximum_excursion, excursion)
                maximum_by_semantic[semantic] = max(float(maximum_by_semantic[semantic]), excursion)
                tolerance = float(row['tolerance'])
                if excursion > 0.0:
                    raw_excursions.append({
                        'semantic_id': semantic, 'joint_name': row['joint_name'],
                        'position': value, 'range': list(row['range']), 'excursion': excursion,
                        'tolerance': tolerance, 'phase': phase,
                        'control_boundary': int(control_boundary), 'native_step': int(native_step),
                    })
                if excursion > tolerance and monitor['first_violation'] is None:
                    monitor['first_violation'] = {
                        'kind': 'joint_limit_exceeded', 'semantic_id': semantic,
                        'joint_name': row['joint_name'], 'position': value,
                        'range': list(row['range']), 'excursion': excursion,
                        'tolerance': tolerance,
                        'phase': phase, 'control_boundary': int(control_boundary),
                        'native_step': int(native_step),
                    }
        monitor['maximum_excursion'] = maximum_excursion
        monitor['joint_limit_excursion_count'] = len(raw_excursions)
        monitor['warning_counts'] = warning_counts
        monitor['samples_including_reset'] = int(monitor['samples_including_reset']) + 1
        any_warning = any(warning_counts)
        monitor['status'] = 'failed' if (monitor['first_violation'] is not None or any_warning) else 'passed'
        monitor['last_control_boundary'] = int(control_boundary)
        monitor['native_step_count'] = int(native_step)
        monitor['simulation_time_s'] = float(self._data.time)
        if not finite or monitor['first_violation'] is not None or any_warning:
            raise RuntimeError('physical state monitor found non-finite state, a joint limit excursion, or a MuJoCo warning')

    def _assert_physical_monitor_clean_at_reset(self):
        if self._physical_monitor['status'] != 'passed':
            raise RuntimeError('physical state monitor rejected the reset boundary')

    @property
    def physical_state_monitor_receipt(self):
        if self._mixed_actuator_plan is None or not hasattr(self, '_physical_monitor'):
            raise RuntimeError('physical state monitor is unavailable for this session')
        return json.loads(json.dumps(self._physical_monitor, sort_keys=True))

    def close(self):
        if not self._closed:
            external = getattr(self, '_external_com_port', None)
            if external is not None:
                external.finish()
            physical_port = getattr(self, '_physical_port', None)
            if physical_port is not None and physical_port.pending is not None:
                physical_port.finish_interval()
            if self._mixed_actuator_plan is not None:
                self._last_close_receipt = {
                    'schema_version': 'runtime-close-v1',
                    'provider_materialization_id': self._provider_materialization_id,
                    'episode_id': self._episode_id,
                    'reset_sample_id': self._reset_sample_id,
                    'session_closed': True,
                    'model_released': getattr(self, '_model', None) is not None,
                    'data_released': getattr(self, '_data', None) is not None,
                    'reset_count': int(getattr(self, '_reset_count', 0)),
                    'control_step': int(getattr(self, '_control_step', 0)),
                    'native_step_count': int(getattr(self, '_native_steps', 0)),
                    'preprocess_call_count': int(getattr(self, '_preprocess_calls', 0)),
                    'forward_call_count': int(getattr(self, '_forward_calls', 0)),
                    'source_id': self._source.scene_source.source_id,
                    'source_closure_digest': self._source.source_closure_digest,
                    'physical_state_monitor': (
                        self.physical_state_monitor_receipt
                        if hasattr(self, '_physical_monitor') else None
                    ),
                }
            if getattr(self._source, 'fixed_attachment_plan', None) is not None:
                model, data = getattr(self, '_model', None), getattr(self, '_data', None)
                self._fixed_attachment_close_receipt = {
                    "provider_materialization_id": self._provider_materialization_id,
                    "session_closed": True,
                    "model_released": model is not None,
                    "data_released": data is not None,
                    "native_step_count": getattr(self, '_native_steps', 0),
                    "forward_call_count": getattr(self, '_fixed_forward_calls', 0),
                    "native_time_s": None if data is None else float(data.time),
                }
            self._data, self._model = None, None
            self._closed = True
