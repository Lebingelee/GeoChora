"""Private GeoPhys projection using the existing scalar bootstrap and boundary."""
from copy import deepcopy
import numpy as np

from ...environment import EpisodePhysicsState, SnapshotRequest
from ..bootstrap import bootstrap_task_runtime
from .common import _SessionValues, pose
from .geophys_source import GeoPhysSourceComposer


def _observer_mjcf_light_declaration(table):
    """Resolve the small MJCF light subset consumed by task RGB rendering."""
    records = () if table is None else tuple(table.records)
    ambient_id = 'mjcf:headlight:ambient'
    headlight_id = 'mjcf:headlight'
    ambient = tuple(item for item in records if item.light_id == ambient_id)
    spots = tuple(
        item for item in records
        if item.runtime_payload.get('mjcf_kind') == 'world_trackcom'
    )
    headlights = tuple(
        item for item in records
        if item.runtime_payload.get('mjcf_kind') == 'headlight'
    )
    supported_ids = {
        ambient_id,
        headlight_id,
        *(item.light_id for item in spots),
    }
    unsupported = tuple(
        item for item in records
        if item.light_type == 'mjcf_unsupported' or item.light_id not in supported_ids
    )
    duplicate_ids = len({item.light_id for item in records}) != len(records)
    malformed_supported_lights = (
        any(item.light_type != 'ambient' for item in ambient)
        or any(
            item.light_id != headlight_id or item.light_type != 'directional'
            for item in headlights
        )
        or any(item.light_type != 'spot' for item in spots)
    )
    missing_or_ambiguous_baseline = table is not None and (
        len(ambient) != 1 or len(headlights) != 1
    )
    if (
        unsupported or duplicate_ids or malformed_supported_lights
        or len(spots) > 1 or missing_or_ambiguous_baseline
    ):
        raise RuntimeError(
            'GeoPhys observer supports zero or one authored trackcom light and '
            'zero or one headlight; ambiguous or unsupported authored lights are rejected'
        )
    return (
        spots[0] if spots else None,
        headlights[0] if headlights else None,
        'no-authored-mjcf-lights' if table is None else 'supported-authored-mjcf-lights',
        len(records),
    )


def _world_center_of_mass(bodies, name_to_id, positions, quaternions):
    """Mass-weighted world COM from public compiled values and owned poses."""
    positions = np.asarray(positions, dtype=np.float64)
    quaternions = np.asarray(quaternions, dtype=np.float64)
    names = [row['name'] for row in bodies]
    if (len(set(names)) != len(names) or set(names) != set(name_to_id) or
            len(set(name_to_id.values())) != len(names)):
        raise ValueError('COM requires one named pose for every compiled body')
    total, weighted = 0., np.zeros(3, dtype=np.float64)
    for row in bodies:
        index = int(name_to_id[row['name']])
        if index < 0 or index >= len(positions) or index >= len(quaternions):
            raise ValueError('COM body ID is outside the owned pose arrays')
        mass = float(row['mass_kg'])
        local = np.asarray(row['com_body_m'], dtype=np.float64)
        q = quaternions[index]
        if (mass < 0 or not np.isfinite(mass) or local.shape != (3,) or
                q.shape != (4,) or not np.isfinite(local).all() or
                not np.isfinite(q).all() or not np.isfinite(positions[index]).all()):
            raise ValueError('COM inputs must be finite and masses nonnegative')
        norm = float(np.linalg.norm(q))
        if norm < 1e-12:
            raise ValueError('COM body quaternion is invalid')
        q = q / norm
        xyz = q[1:]
        rotated = local + 2 * np.cross(xyz, np.cross(xyz, local) + q[0] * local)
        weighted += mass * (positions[index] + rotated)
        total += mass
    if total <= 0 or not np.isfinite(total):
        raise ValueError('COM requires positive finite total mass')
    return weighted / total


def _rest_center_of_mass(bodies, name_to_id, data):
    """Evaluate the bounded zero-scalar-joint source rest pose without stepping."""
    parent = np.asarray(data['body_parentid'], dtype=np.int64)
    local_pos = np.asarray(data['body_pos'], dtype=np.float64)
    local_quat = np.asarray(data['body_quat'], dtype=np.float64)
    qpos = np.asarray(data['initial_qpos'], dtype=np.float64)
    types = np.asarray(data['jnt_type'], dtype=np.int64)
    addresses = np.asarray(data['jnt_qposadr'], dtype=np.int64)
    joint_counts = np.asarray(data['body_jntnum'], dtype=np.int64)
    joint_starts = np.asarray(data['body_jntadr'], dtype=np.int64)
    count = len(bodies)
    if (parent.shape != (count,) or local_pos.shape != (count, 3) or
            local_quat.shape != (count, 4) or not np.isfinite(local_pos).all() or
            not np.isfinite(local_quat).all() or not np.isfinite(qpos).all()):
        raise ValueError('unsupported source rest pose arrays')
    for body in range(count):
        for joint in range(int(joint_starts[body]), int(joint_starts[body] + joint_counts[body])):
            kind, address = int(types[joint]), int(addresses[joint])
            if kind in (2, 3):
                if address < 0 or address >= len(qpos) or abs(qpos[address]) > 1e-9:
                    raise ValueError('source rest COM requires zero scalar joint coordinates')
            elif kind == 0 and parent[body] < 0:
                if (address < 0 or address + 7 > len(qpos) or
                    not np.allclose(qpos[address:address+3], local_pos[body], atol=1e-7, rtol=0) or
                    not np.allclose(qpos[address+3:address+7], local_quat[body], atol=1e-7, rtol=0)):
                    raise ValueError('source free joint does not match its world rest pose')
            else:
                raise ValueError('source rest COM has an unsupported joint')
    def multiply(a, b):
        w, x, y, z = a
        v, s, t, u = b
        return np.asarray((w*v-x*s-y*t-z*u, w*s+x*v+y*u-z*t,
                           w*t-x*u+y*v+z*s, w*u+x*t-y*s+z*v))
    world_pos, world_quat = np.zeros_like(local_pos), np.zeros_like(local_quat)
    for i in range(count):
        norm = np.linalg.norm(local_quat[i])
        if norm < 1e-12 or parent[i] >= i:
            raise ValueError('source rest body hierarchy is invalid')
        local = local_quat[i] / norm
        if parent[i] < 0:
            world_pos[i], world_quat[i] = local_pos[i], local
        else:
            q = world_quat[parent[i]]
            v = local_pos[i]
            world_pos[i] = world_pos[parent[i]] + v + 2 * np.cross(q[1:], np.cross(q[1:], v) + q[0] * v)
            world_quat[i] = multiply(q, local)
    return _world_center_of_mass(bodies, name_to_id, world_pos, world_quat)


def _geophys_model_facts(compiled):
    """Read the public rigid scene passed to GeoPhys materialization.

    These are compiled-model values, not an independent solver-field readback.
    """
    scene = compiled.scene_model
    data = scene.joint_data
    names = compiled.references.names
    bodies = []
    for i, obj in enumerate(scene.objects):
        w, x, y, z = (float(v) for v in data['body_iquat'][i])
        norm = np.linalg.norm([w, x, y, z])
        if not np.isfinite(norm) or norm < 1e-12:
            raise ValueError(f'GeoPhys body has invalid inertial quaternion: {obj.object_key}')
        w, x, y, z = (v / norm for v in (w, x, y, z))
        rotation = np.asarray(((1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)),
                               (2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)),
                               (2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y))))
        tensor = rotation @ np.diag(np.asarray(obj.body_inertia, dtype=np.float64)) @ rotation.T
        bodies.append({'name': obj.object_key, 'mass_kg': float(obj.body_config.mass),
                       'com_body_m': np.asarray(data['body_ipos'][i]).tolist(),
                       'inertia_body_at_com_kg_m2': tensor.tolist(),
                       'inertial_quaternion_body_wxyz': [w, x, y, z]})
    joints = []
    for name, i in sorted(names.joints.items(), key=lambda item: item[1]):
        i = int(i)
        joints.append({'name': name, 'id': i, 'type': int(data['jnt_type'][i]),
                       'axis_child_body': np.asarray(data['jnt_axis_child'][i]).tolist(),
                       'axis_parent_body': np.asarray(data['jnt_axis_parent'][i]).tolist(),
                       'limited': bool(data['jnt_limited'][i]),
                       'range': np.asarray(data['jnt_range'][i]).tolist()})
    actuators = []
    for name, i in sorted(names.actuators.items(), key=lambda item: item[1]):
        i = int(i)
        actuators.append({'name': name, 'id': i, 'transmission_type': int(data['actuator_trntype'][i]),
                          'transmission_id': int(data['actuator_trnid'][i]),
                          'gear': np.asarray(data['actuator_gear'][i]).tolist()})
    eq = data.get('eq_data')
    equality = None if eq is None else {
        'n_eq': int(eq.n_eq), 'n_rows': int(eq.n_rows),
        'joint_id_a': np.asarray(eq.joint_id_a).tolist(),
        'joint_id_b': np.asarray(eq.joint_id_b).tolist(),
        'polycoef': np.asarray(eq.polycoef).tolist(),
        'active': np.asarray(eq.active).tolist(),
    }
    tendon_keys = ('n_tendons', 'tendon_wrap_adr', 'tendon_wrap_num',
                   'tendon_wrap_jntid', 'tendon_wrap_coef')
    tendons = {key: (int(data[key]) if key == 'n_tendons' else np.asarray(data[key]).tolist())
               for key in tendon_keys if key in data}
    tendons['name_to_id'] = {str(k): int(v) for k, v in data.get('name_to_tendon', {}).items()}
    return {'schema_version': 'geophys-public-compiled-model-facts-v1', 'bodies': bodies,
            'joints': joints, 'actuators': actuators, 'inertia_reference': 'center_of_mass',
            'inertia_frame': 'body', 'scope': 'public compiled rigid scene, not solver-field readback',
            'equalities': equality, 'tendons': tendons}


def _geophys_effective_model_facts(snapshot, names):
    """Bind provider-local IDs to the names of the same materialization."""
    if snapshot.get('schema_version') != 'rigid-model-snapshot-v1':
        raise ValueError('unsupported GeoPhys effective model snapshot')
    result = deepcopy(snapshot)
    for group, name_map in (('bodies', names.bodies), ('joints', names.joints),
                            ('actuators', names.actuators)):
        by_id = {int(index): str(name) for name, index in name_map.items()}
        for row in result[group]:
            row['name'] = by_id.get(row['id'])
    return result


def check_geophys_named_layout(names, data, source, boundary):
    """Resolve selected MJCF names and scalar/free addresses in public model data."""
    result = {'joints': {}, 'free_joints': {}, 'bodies': {}, 'frames': {}, 'actuators': {}}
    types, qadr, vadr = (data['jnt_type'], data['jnt_qposadr'], data['jnt_dofadr'])
    for field, free in (('joints', False), ('free_joints', True)):
        for semantic, native in getattr(source, field).items():
            index = int(names.joints[native])
            if index < 0 or index >= min(len(types), len(qadr), len(vadr)):
                raise ValueError(f'public GeoPhys joint index invalid: {semantic}')
            kind = int(types[index])
            # Public GeoPhys JointType IDs: FREE=0, HINGE=2, SLIDE=3.
            if kind not in ((0,) if free else (2, 3)):
                raise ValueError(f'public GeoPhys joint type mismatch: {semantic}')
            q, v = int(qadr[index]), int(vadr[index]); nq, nv = ((7, 6) if free else (1, 1))
            if q < 0 or v < 0 or q+nq > int(data['n_qpos']) or v+nv > int(data['n_dof']):
                raise ValueError(f'public GeoPhys joint addresses exceed dimensions: {semantic}')
            result[field][semantic] = {'native': native, 'id': index, 'type': kind,
                                       'qpos': q, 'dof': v, 'qpos_width': nq, 'dof_width': nv}
    for field, table in (('bodies', names.bodies), ('frames', names.sites)):
        for semantic, native in getattr(source, field).items():
            index = int(table[native])
            if index < 0: raise ValueError(f'public GeoPhys {field} index invalid: {semantic}')
            result[field][semantic] = {'native': native, 'id': index}
    for semantic, native in source.joint_targets.items():
        if semantic not in source.joints: raise ValueError(f'actuator has no bound joint: {semantic}')
        index = int(names.actuators[native])
        if index < 0: raise ValueError(f'public GeoPhys actuator index invalid: {semantic}')
        transmission_types, transmission_joints = data['actuator_trntype'], data['actuator_trnid']
        if index >= min(len(transmission_types), len(transmission_joints)):
            raise ValueError(f'public GeoPhys actuator metadata missing: {semantic}')
        joint_index = result['joints'][semantic]['id']
        if int(transmission_types[index]) != 0 or int(transmission_joints[index]) != joint_index:
            raise ValueError(f'public GeoPhys actuator transmission mismatch: {semantic}')
        result['actuators'][semantic] = {'native': native, 'id': index, 'joint_id': joint_index}
    for native in source.open_actuators:
        index = int(names.actuators[native])
        if index < 0: raise ValueError(f'public GeoPhys actuator index invalid: {native}')
        result['actuators']['open:'+native] = {'native': native, 'id': index}
    for field in ('torque_actuators', 'position_actuators'):
        for semantic, native in getattr(source, field, {}).items():
            index = int(names.actuators[native])
            types, targets = data['actuator_trntype'], data['actuator_trnid']
            joint = result['joints'].get(semantic)
            if (joint is None or index < 0 or index >= min(len(types), len(targets))
                    or int(types[index]) != 0 or int(targets[index]) != joint['id']):
                raise ValueError(f'public GeoPhys mixed actuator transmission mismatch: {semantic}')
            result['actuators'][semantic] = {'native': native, 'id': index, 'joint_id': joint['id']}
    snapshot = boundary.read_snapshot(SnapshotRequest(
        qacc=False, ctrl=True, body_pose=bool(source.bodies), site_pose=bool(source.frames)))
    qpos, qvel, ctrl = (np.asarray(snapshot.qpos), np.asarray(snapshot.qvel), np.asarray(snapshot.ctrl))
    if (qpos.ndim != 1 or qpos.size < int(data['n_qpos'])
            or qvel.ndim != 1 or qvel.size < int(data['n_dof']) or ctrl.ndim != 1):
        raise ValueError('public GeoPhys state or control channel dimensions do not match model')
    if any(item['id'] >= ctrl.size for item in result['actuators'].values()):
        raise ValueError('public GeoPhys control channel lacks a declared actuator')
    for field, position, orientation in (
        ('bodies', snapshot.body_xpos, snapshot.body_xquat),
        ('frames', snapshot.site_xpos, snapshot.site_xquat),
    ):
        if not result[field]:
            continue
        p, q = np.asarray(position), np.asarray(orientation)
        if (p.ndim != 2 or p.shape[1] != 3 or q.ndim != 2 or q.shape[1] != 4
                or any(item['id'] >= min(len(p), len(q)) for item in result[field].values())):
            raise ValueError(f'public GeoPhys {field} pose channel does not cover source mappings')
    return result


class _GeoPhysSession(_SessionValues):
    def __init__(self, artifact, source, *, observer_render_request=None, legacy_observer_requested=False,
                 legacy_camera_observations=False):
        self._initialize_values(artifact, source, 'geophys')
        runtime = bootstrap_task_runtime(
            config=source.config, composition=source.composition, scene=source.scene,
            agents=source.agents, objects=source.objects,
            scene_composer=GeoPhysSourceComposer(
                source.scene_source,
                scene_definition=source.scene_definition,
                source_closure_digest=(
                    source.source_closure_digest
                    if source.scene_definition is not None else None
                ),
                execution_source_receipt=source.execution_source_receipt,
            ),
            create_render_source=observer_render_request is not None or legacy_observer_requested,
        )
        self._observer_render_request = observer_render_request
        self._observer_render_source = runtime.render_source
        self._observer_visualizer = None
        self._legacy_observer_requested = legacy_observer_requested
        self._legacy_observer_visualizer = None
        self._legacy_camera_observations = legacy_camera_observations
        self._legacy_camera_provider = None
        self._observer_fault = False
        self._observer_material_report = None
        self._observer_light_report = None
        self._observer_lighting_resources = None
        self._observer_tracking_light = None
        self._observer_headlight = None
        self._observer_light_source_mode = None
        self._observer_authored_light_count = 0
        if (observer_render_request is not None or legacy_observer_requested
                or legacy_camera_observations) and self._observer_render_source is None:
            error = RuntimeError('GeoPhys observer source could not be materialized')
            try:
                runtime.boundary.close()
            except BaseException as cleanup_error:
                error.add_note(f'GeoPhys boundary cleanup also failed: {cleanup_error!r}')
            raise error
        self._boundary = runtime.boundary
        compiled = runtime.compiled_scene
        self._legacy_camera_references = compiled.references
        names, data = compiled.references.names, compiled.scene_model.joint_data
        try:
            self._body_parentid = np.asarray(data['body_parentid'], dtype=np.int32).reshape(-1)
            self._body_jntnum = np.asarray(data['body_jntnum'], dtype=np.int32).reshape(-1)
            checked = check_geophys_named_layout(names, data, source, self._boundary)
            self._joint_addresses = {k: (v['qpos'], v['dof']) for k, v in checked['joints'].items()}
            self._free_addresses = {k: (v['qpos'], v['dof']) for k, v in checked['free_joints'].items()}
            self._bodies = {k: v['id'] for k, v in checked['bodies'].items()}
            self._frames = {k: v['id'] for k, v in checked['frames'].items()}
            self._fixture_bodies = {name: self._bodies[name] for name in source.fixture_bodies}
            self._target_actuators = {k: checked['actuators'][k]['id'] for k in source.joint_targets}
            self._open_actuators = tuple(checked['actuators']['open:'+n]['id'] for n in source.open_actuators)
            self._build_layout_facts = {'helper': 'task_env.runtime.sessions.geophys:check_geophys_named_layout',
                'provider': 'geophys', 'source_id': source.scene_source.source_id,
                'source_closure': source.source_closure_digest, 'objects': checked,
                'materialization_id': self.provider_materialization_id,
                'physical_model': _geophys_model_facts(compiled),
                'effective_physical_model': _geophys_effective_model_facts(
                    self._boundary.read_model_snapshot(), names)}
            if observer_render_request is not None:
                self._observer_com_bodies = self._build_layout_facts['physical_model']['bodies']
                self._observer_com_ids = {str(name): int(index) for name, index in names.bodies.items()}
                self._observer_rest_com = _rest_center_of_mass(
                    self._observer_com_bodies, self._observer_com_ids, data)
        except BaseException:
            self._boundary.close()
            raise
        self._ctrl_range = data['actuator_ctrlrange']
        self._mixed_actuator_plan = source.mixed_actuator_plan
        self._mixed_controller_identity = None
        self._mixed_pending_target = None
        self._mixed_consumed_boundaries = set()
        self._mixed_fault = None
        self._inner_interval_active = False
        self._reset_count = 0
        self._native_steps = 0
        self._last_close_receipt = None
        self._torque_actuators = {}
        self._position_actuators = {}
        self._mixed_channel_actuators = {}
        self._mixed_channel_records = {}
        self._last_reset_readback_v1 = None
        if self._mixed_actuator_plan is not None:
            try:
                self._initialize_mixed_actuator(source, names, data)
            except BaseException:
                self._boundary.close()
                raise
        self._initial = runtime.boundary.initial_state
        self._reset_force_measurement = None
        self._last_reset_force_sequence = 0
        self._force_source_generation = None
        self._last_actuator_force_measurement = None
        self._last_typed_force_publication = None

    def bind_physical_control(self, execution):
        if getattr(self, '_physical_port', None) is not None or self._reset_done:
            raise ValueError('physical port must be bound once before reset')
        from .geophys_physical import GeoPhysPhysicalPort
        versions = execution.controller_versions()
        self._physical_port = GeoPhysPhysicalPort(self, execution)
        self._physical_controller_versions = versions
        self.physical_control_generation = execution.generation

    def assess_physical_control(self, binding):
        return self._physical_port.assessment(binding)

    def physical_joint_build_receipt(self, binding):
        return self._physical_port.joints(binding)

    def physical_buffer_policy(self, binding):
        return self._physical_port.policy(binding)

    def apply_physical_command_batch(self, resolved):
        return self._physical_port.write(resolved)

    def abort_physical_control(self):
        port = getattr(self, '_physical_port', None)
        if port is not None:
            port.finish_interval()

    def _initialize_mixed_actuator(self, source, names, data):
        """Bind every declared mixed channel to the compiled named GeoPhys model."""
        from ...controllers.canonical.contracts import MixedActuatorPlanV1

        plan = self._mixed_actuator_plan
        if type(plan) is not MixedActuatorPlanV1:
            raise TypeError('GeoPhys mixed actuation requires MixedActuatorPlanV1')
        plan.validate()
        if (plan.task_artifact_hash != self._artifact.identity_hash
                or plan.source_id != source.scene_source.source_id
                or plan.source_closure_digest != source.source_closure_digest):
            raise ValueError('GeoPhys mixed actuator plan differs from its Artifact/source closure')
        if int(data.get('n_actuators', 0)) != len(plan.channels):
            raise ValueError('GeoPhys compiled actuator count differs from the complete mixed plan')
        if set(names.actuators) != {item.actuator_name for item in plan.channels}:
            raise ValueError('GeoPhys compiled actuator names differ from the complete mixed plan')
        torque_names = set(source.torque_actuators.values())
        position_names = set(source.position_actuators.values())
        if torque_names & position_names or torque_names | position_names != set(names.actuators):
            raise ValueError('GeoPhys mixed source must bind every actuator exactly once')
        self._torque_actuators = {
            semantic: names.actuators[native]
            for semantic, native in source.torque_actuators.items()
        }
        self._position_actuators = {
            semantic: names.actuators[native]
            for semantic, native in source.position_actuators.items()
        }
        trntype = np.asarray(data['actuator_trntype'])
        trnid = np.asarray(data['actuator_trnid'])
        limited = np.asarray(data['actuator_ctrllimited'])
        ctrlrange = np.asarray(data['actuator_ctrlrange'])
        joint_types = np.asarray(data['jnt_type'])
        gears = np.asarray(data['actuator_gear'])
        gain_types = np.asarray(data['actuator_gaintype'])
        bias_types = np.asarray(data['actuator_biastype'])
        dynamic_types = np.asarray(data['actuator_dyntype'])
        gain_params = np.asarray(data['actuator_gainprm'])
        bias_params = np.asarray(data['actuator_biasprm'])
        if (trntype.shape[0] < len(plan.channels) or trnid.shape[0] < len(plan.channels)
                or limited.shape[0] < len(plan.channels) or ctrlrange.shape[0] < len(plan.channels)
                or gears.shape[0] < len(plan.channels) or gain_types.shape[0] < len(plan.channels)
                or bias_types.shape[0] < len(plan.channels) or dynamic_types.shape[0] < len(plan.channels)
                or gain_params.shape[0] < len(plan.channels) or bias_params.shape[0] < len(plan.channels)):
            raise ValueError('GeoPhys compiled actuator metadata is incomplete')
        for channel in plan.channels:
            actuator_id = names.actuators.get(channel.actuator_name)
            joint_id = names.joints.get(channel.joint_name)
            if actuator_id is None or joint_id is None:
                raise ValueError(f'GeoPhys mixed channel does not resolve by source name: {channel.semantic_id}')
            actuator_id, joint_id = int(actuator_id), int(joint_id)
            if int(trntype[actuator_id]) != 0 or int(trnid[actuator_id]) != joint_id:
                raise ValueError(f'GeoPhys actuator transmission differs from its named source Joint: {channel.semantic_id}')
            if (int(dynamic_types[actuator_id]) != 0
                    or gears.shape[1] != 6
                    or not np.allclose(gears[actuator_id], (1.0, 0, 0, 0, 0, 0), rtol=0.0, atol=1e-7)):
                raise ValueError(f'GeoPhys mixed actuator must use a unit-gain stateless scalar transmission: {channel.semantic_id}')
            low, high = (float(value) for value in ctrlrange[actuator_id])
            if (not bool(limited[actuator_id])
                    or not np.allclose((low, high), channel.control_range, rtol=0.0, atol=1e-7)):
                raise ValueError(f'GeoPhys actuator range differs from its source-bound plan: {channel.semantic_id}')
            if channel.semantic_id in source.torque_actuators:
                if (channel.drive_mode != 'joint_torque' or channel.unit != 'N*m'
                        or int(joint_types[joint_id]) != 2
                        or int(gain_types[actuator_id]) != 0
                        or int(bias_types[actuator_id]) != 0
                        or float(gain_params[actuator_id, 0]) != 1.0):
                    raise ValueError(f'GeoPhys torque source role differs from its plan: {channel.semantic_id}')
            elif channel.semantic_id in source.position_actuators:
                expected_unit = {2: 'rad', 3: 'm'}.get(int(joint_types[joint_id]))
                if (channel.drive_mode != 'joint_position' or channel.unit != expected_unit
                        or int(gain_types[actuator_id]) != 0
                        or int(bias_types[actuator_id]) != 1
                        or not np.isfinite(gain_params[actuator_id, 0])
                        or float(gain_params[actuator_id, 0]) <= 0.0
                        or float(bias_params[actuator_id, 0]) != 0.0
                        or float(bias_params[actuator_id, 2]) > 0.0
                        or not np.isclose(float(bias_params[actuator_id, 1]),
                                          -float(gain_params[actuator_id, 0]),
                                          rtol=0.0, atol=1e-5)):
                    raise ValueError(f'GeoPhys position source role differs from its plan: {channel.semantic_id}')
            else:
                raise ValueError(f'GeoPhys mixed channel lacks a RuntimeSource role: {channel.semantic_id}')
            self._mixed_channel_actuators[channel.semantic_id] = actuator_id
            self._mixed_channel_records[channel.semantic_id] = {
                'actuator_name': channel.actuator_name,
                'actuator_id': actuator_id,
                'joint_name': channel.joint_name,
                'joint_id': joint_id,
                'drive_mode': channel.drive_mode,
                'unit': channel.unit,
                'control_limited': True,
                'control_range': [low, high],
                'transmission_type': 'joint',
                'gain_type': int(gain_types[actuator_id]),
                'bias_type': int(bias_types[actuator_id]),
                'gainprm': [float(value) for value in gain_params[actuator_id]],
                'biasprm': [float(value) for value in bias_params[actuator_id]],
            }

    @property
    def compiled_layout_receipt(self):
        """Source-bound named layout evidence; native IDs stay in this adapter."""
        if self._mixed_actuator_plan is None:
            raise RuntimeError('compiled mixed actuator layout is unavailable for this session')
        nq = max(
            max((qpos + 1 for qpos, _ in self._joint_addresses.values()), default=0),
            max((qpos + 7 for qpos, _ in self._free_addresses.values()), default=0),
        )
        nv = max(
            max((dof + 1 for _, dof in self._joint_addresses.values()), default=0),
            max((dof + 6 for _, dof in self._free_addresses.values()), default=0),
        )
        return {
            'schema_version': 'compiled-model-layout-v1',
            'provider': 'geophys',
            'dimensions': {
                'nq': int(nq),
                'nv': int(nv),
                'nu': len(self._mixed_channel_actuators),
            },
            'source_id': self._source.scene_source.source_id,
            'source_closure_digest': self._source.source_closure_digest,
            'named_joint_addresses': {
                name: [int(qpos), int(dof)] for name, (qpos, dof) in self._joint_addresses.items()
            },
            'named_free_joint_addresses': {
                name: [int(qpos), int(dof)] for name, (qpos, dof) in self._free_addresses.items()
            },
            'named_torque_actuator_ids': dict(self._torque_actuators),
            'named_position_actuator_ids': dict(self._position_actuators),
            'named_actuator_channels': dict(self._mixed_channel_records),
        }

    @property
    def actuator_force_measurement(self):
        """Last adapter-validated signed sample, bound to this Core boundary."""
        return self._last_actuator_force_measurement

    def reset(self, sample):
        self._validate_sample(sample)
        if getattr(sample, 'control_policy', None) == 'named_physical_effort_by_source_v1':
            self._preflight_physical_reset(sample)
        if getattr(self, '_physical_port', None) is not None and self._physical_port.pending is not None:
            raise RuntimeError('cannot reset with pending physical effort')
        if self._mixed_actuator_plan is not None:
            self._preflight_mixed_reset(sample)
        self._begin_reset()
        # A failed reset must not leave a previous episode's validated sample
        # visible through this adapter's diagnostic property.
        self._reset_force_measurement = None
        self._last_actuator_force_measurement = None
        self._last_typed_force_publication = None
        initial = self._initial
        positions = np.array(initial.qpos, copy=True)
        velocities = np.zeros_like(initial.qvel)
        targets = np.array(initial.ctrl, copy=True)
        # ResetSample v0 deliberately has no velocity or fixture-pose fields:
        # its contract is zero velocities and no sampled fixture transform.
        # ResetSampleV1 is validated above and supplies these fields explicitly.
        joint_velocities = getattr(sample, 'joint_velocity', {})
        free_joint_velocities = getattr(sample, 'free_joint_velocity', {})
        fixture_pose_world = getattr(sample, 'fixture_pose_world', {})
        if self._mixed_actuator_plan is not None:
            targets[:] = 0.0
        for name, value in sample.joint_position.items():
            positions[self._joint_addresses[name][0]] = value
            velocities[self._joint_addresses[name][1]] = joint_velocities.get(name, 0.0)
        for name, requested in sample.poses_world.items():
            address = self._free_addresses[name][0]
            positions[address:address+7] = (*requested.position, *requested.quaternion_wxyz)
            dof = self._free_addresses[name][1]
            velocities[dof:dof + 6] = free_joint_velocities.get(name, (0.0,) * 6)
        for name, actuator in self._target_actuators.items():
            targets[actuator] = sample.joint_position[name]
        for name, actuator in self._position_actuators.items():
            targets[actuator] = sample.joint_position[name]
        for actuator in self._open_actuators:
            targets[actuator] = self._ctrl_range[actuator, 1]
        self._current_ctrl = np.array(targets, copy=True)
        force_measurement = self._boundary.apply_reset_state(EpisodePhysicsState(
            positions, velocities, np.zeros_like(initial.qacc),
            targets, np.zeros_like(initial.act),
        ), refresh_actuator_force=bool(getattr(self, '_force_feedback_required', False)),
            static_world_child_poses={
                self._fixture_bodies[name]: (
                    np.asarray(value.position, dtype=np.float32),
                    np.asarray(value.quaternion_wxyz, dtype=np.float32),
                )
                for name, value in fixture_pose_world.items()
            })
        if force_measurement is not None:
            if not force_measurement.valid or force_measurement.phase != 'reset_forward':
                raise ValueError('GeoPhys reset did not publish a valid reset-forward actuator-force sample')
            if force_measurement.native_step_index != 0:
                raise ValueError('GeoPhys reset-forward force sample must reference native step 0')
            if force_measurement.sample_sequence <= self._last_reset_force_sequence:
                raise ValueError('GeoPhys reset reused a prior actuator-force sample')
            if self._force_source_generation is not None and (
                force_measurement.source_generation != self._force_source_generation
            ):
                raise ValueError('GeoPhys reset actuator-force sample belongs to another solver identity')
            self._force_source_generation = force_measurement.source_generation
        realized = self._realized(sample)
        if self._mixed_actuator_plan is not None:
            self._native_steps = 0
            self._mixed_consumed_boundaries.clear()
            self._mixed_pending_target = None
            self._mixed_fault = None
            state, free_joint_native = self._snapshot_with_native_free_joints()
            self._last_reset_readback_v1 = {
                'schema_version': 'geophys-runtime-reset-readback-v1',
                'source_id': self._source.scene_source.source_id,
                'source_closure_digest': self._source.source_closure_digest,
                'provider_materialization_id': self._provider_materialization_id,
                'episode_id': self._episode_id,
                'reset_sample_id': self._reset_sample_id,
                'simulation_time_s': float(state.simulation_time),
                'joint_position': dict(state.joint_position),
                'joint_velocity': dict(state.joint_velocity),
                'poses_world': {
                    name: {
                        'position_m': list(value.position),
                        'quaternion_wxyz': list(value.quaternion_wxyz),
                    }
                    for name, value in state.pose_world.items()
                    if name in self._source.free_joints
                },
                'free_joint_velocity': {
                    name: list(qvel) for name, (_, qvel) in free_joint_native.items()
                },
                'free_joint_velocity_frame': 'source_sampled_reset_qvel_v1',
                'fixture_pose_world': {
                    name: self._pose_mapping(self._fixture_pose_readback(name))
                    for name in self._source.fixture_bodies
                },
                'native_step_count': 0,
                'state_sync_count': 1,
                'reset_method': 'GeoPhysRuntimeBoundary.apply_reset_state',
            }
        if force_measurement is not None:
            from dataclasses import replace

            force_measurement = replace(
                force_measurement,
                episode_id=str(self._episode_id),
                reset_sample_id=str(self._reset_sample_id),
                evaluation_control_step=0,
                evaluation_simulation_time_s=0.0,
                actuator_id=str(self._source.open_actuators[0]),
            )
        self._reset_force_measurement = force_measurement
        if force_measurement is not None:
            self._last_reset_force_sequence = force_measurement.sample_sequence
        if self._mixed_actuator_plan is not None:
            self._reset_count += 1
        return realized

    def _preflight_physical_reset(self, sample):
        self._validate_sample(sample)
        if sample.control_policy != 'named_physical_effort_by_source_v1':
            raise ValueError('physical reset requires the named effort policy')
        model = self._build_layout_facts['effective_physical_model']
        joints = {row['name']: row for row in model['joints']}
        for name, value in sample.joint_position.items():
            row = joints.get(self._source.joints[name])
            if row is None:
                raise ValueError(f'physical reset joint is absent from source: {name}')
            if bool(row['limited']):
                low, high = row['range']
                if not float(low) <= float(value) <= float(high):
                    raise ValueError(f'physical reset joint position exceeds source limits: {name}')

    @staticmethod
    def _pose_mapping(value):
        return {
            'position_m': list(value.position),
            'quaternion_wxyz': list(value.quaternion_wxyz),
        }

    def _fixture_pose_readback(self, name):
        from ...environment import SnapshotRequest

        readback = self._boundary.read_snapshot(SnapshotRequest(
            qacc=False, ctrl=False, body_pose=True, site_pose=False, simulation_time=False,
        ))
        body_id = self._fixture_bodies[name]
        return pose(readback.body_xpos[body_id], readback.body_xquat[body_id])

    def _preflight_mixed_reset(self, sample):
        """Reject source-bound reset values the public GeoPhys reset cannot realize."""
        if float(sample.simulation_time_s) != 0.0:
            raise ValueError('GeoPhys mixed reset currently supports source time zero only')
        if (set(sample.joint_position) != set(self._joint_addresses)
                or set(sample.poses_world) != set(self._free_addresses)
                or set(sample.free_joint_velocity) != set(self._free_addresses)):
            raise ValueError('GeoPhys mixed reset state names differ from the compiled source layout')
        if set(sample.fixture_pose_world) != set(self._source.fixture_bodies):
            raise ValueError('GeoPhys mixed reset fixture names differ from the compiled source')
        if any(float(value) != 0.0 for value in sample.joint_velocity.values()) or any(
            float(value) != 0.0
            for velocity in sample.free_joint_velocity.values()
            for value in velocity
        ):
            raise ValueError('GeoPhys mixed reset currently supports source zero-velocity samples only')
        for name, expected in sample.fixture_pose_world.items():
            body_id = self._fixture_bodies[name]
            if body_id >= self._body_parentid.size or int(self._body_parentid[body_id]) >= 0:
                raise ValueError(f'GeoPhys mixed reset fixture is not a direct world-root body: {name}')
            if body_id >= self._body_jntnum.size or int(self._body_jntnum[body_id]) != 0:
                raise ValueError(f'GeoPhys mixed reset fixture root must be fixed: {name}')
            expected.validate()

    @property
    def reset_readback_v1(self):
        if self._last_reset_readback_v1 is None:
            raise RuntimeError('GeoPhys reset readback is unavailable before an admitted mixed reset')
        return deepcopy(self._last_reset_readback_v1)

    @property
    def runtime_progress_receipt(self):
        """Return provider-owned progress counters for the selected mixed route."""
        if self._mixed_actuator_plan is None:
            raise RuntimeError('mixed runtime progress is unavailable for this session profile')
        state = self.snapshot()
        return {
            'schema_version': 'runtime-progress-v1',
            'provider_materialization_id': self._provider_materialization_id,
            'episode_id': self._episode_id,
            'reset_sample_id': self._reset_sample_id,
            'reset_count': int(self._reset_count),
            'control_step': int(self._control_step),
            'state_revision': int(self._state_revision),
            'native_step_count': int(self._native_steps),
            'simulation_time_native_s': float(state.simulation_time),
            # Mixed GeoPhys reset admission is source-time-zero only.
            'simulation_time_episode_s': float(state.simulation_time),
            'source_id': self._source.scene_source.source_id,
            'source_closure_digest': self._source.source_closure_digest,
            'plan_identity_hash': self._mixed_actuator_plan.identity_hash,
        }

    @property
    def close_receipt(self):
        if not self._closed or self._last_close_receipt is None:
            raise RuntimeError('GeoPhys RuntimeSession close has not completed')
        return deepcopy(self._last_close_receipt)

    def _snapshot_with_native_free_joints(self):
        self._require_reset()
        readback = self._boundary.read_snapshot(SnapshotRequest(
            qacc=False, ctrl=False, body_pose=True, site_pose=True, simulation_time=True,
        ))
        positions = {name: float(readback.qpos[address[0]]) for name, address in self._joint_addresses.items()}
        velocities = {name: float(readback.qvel[address[1]]) for name, address in self._joint_addresses.items()}
        poses = {name: pose(readback.body_xpos[index], readback.body_xquat[index]) for name, index in self._bodies.items()}
        poses.update({name: pose(readback.site_xpos[index], readback.site_xquat[index]) for name, index in self._frames.items()})
        state = self._state(positions, velocities, poses, readback.simulation_time)
        free_joint_native = {
            name: (
                tuple(float(value) for value in readback.qpos[qpos:qpos + 7]),
                tuple(float(value) for value in readback.qvel[dof:dof + 6]),
            )
            for name, (qpos, dof) in self._free_addresses.items()
        }
        return state, free_joint_native

    def snapshot(self):
        self._require_reset()
        return self._snapshot_with_native_free_joints()[0]

    def render_legacy_rgb(self, config):
        """Capture the source's default offscreen camera without advancing physics."""
        self._require_reset()
        if not self._legacy_observer_requested or self._observer_render_source is None:
            raise ValueError('legacy observer was not requested at materialization')
        if config.backend not in {'raytracer', 'rasterizer'}:
            raise ValueError('legacy observer backend is not admitted')
        before = self._snapshot_with_native_free_joints()
        if self._legacy_observer_visualizer is None:
            self._legacy_observer_visualizer = self._observer_render_source.build_visualizer(
                backend=config.backend, use_render_snapshot=False,
                width=int(config.width), height=int(config.height),
                render_preset=config.render_preset)
        frame = np.asarray(self._legacy_observer_visualizer.read_frame(
            width=int(config.width), height=int(config.height), synchronized=True), dtype=np.float32)
        if (frame.shape != (int(config.height), int(config.width), 3)
                or not np.isfinite(frame).all()):
            raise ValueError('legacy observer returned invalid RGB')
        if before != self._snapshot_with_native_free_joints():
            raise RuntimeError('physics changed during legacy observer capture')
        return np.ascontiguousarray(np.clip(frame, 0., 1.), dtype=np.float32)

    def capture_legacy_camera_metadata(self):
        """Capture the configured component camera sensors at the current boundary."""
        self._require_reset()
        if not self._legacy_camera_observations or self._observer_render_source is None:
            raise ValueError('legacy camera observations were not admitted')
        if self._legacy_camera_provider is None:
            from ...observations import CameraObservationProvider, CameraSensor
            config = self._source.config.render
            sensors = tuple(CameraSensor(spec=spec, references=self._legacy_camera_references)
                            for spec in config.cameras)
            self._legacy_camera_provider = CameraObservationProvider(
                render_source=self._observer_render_source, config=config, camera_sensors=sensors)
        before = self._snapshot_with_native_free_joints()
        snapshot = self._boundary.read_snapshot(SnapshotRequest(
            qacc=False, ctrl=False, body_pose=True, site_pose=True, simulation_time=True))
        sensor_observation = self._legacy_camera_provider.capture(snapshot)
        if before != self._snapshot_with_native_free_joints():
            raise RuntimeError('physics changed during legacy camera observation')
        return sensor_observation.camera_metadata

    def _ensure_observer_visualizer(self, camera):
        if self._observer_visualizer is None:
            desc = self._observer_render_source.read_render_scene(backend='rasterizer')
            (
                self._observer_tracking_light,
                self._observer_headlight,
                self._observer_light_source_mode,
                self._observer_authored_light_count,
            ) = _observer_mjcf_light_declaration(desc.mjcf_light_table)
            self._observer_visualizer = self._observer_render_source.build_visualizer(
                backend='rasterizer', use_render_snapshot=False,
                use_mjcf_lighting=desc.mjcf_light_table is not None, enable_shadow=True,
                width=camera.width, height=camera.height,
                max_framebuffer_resolution=(camera.width, camera.height),
                raster_acceleration='compute', shadow_acceleration='compute',
                raster_material_flags={'enable_texture_sampling': True,
                                       'enable_normal_map': True,
                                       'enable_alpha_blending': True},
                enable_taa=False, enable_fxaa=False, enable_ssao=False)
        return self._observer_visualizer

    def bind_task_camera(self, camera, state):
        import math
        from ...observations.canonical_camera import CameraGeometry, resolve_camera
        self._require_reset()
        if type(camera) is not CameraGeometry:
            raise TypeError('task camera must be CameraGeometry')
        camera.validate()
        if camera.parent_frame != 'world' or camera.task_artifact_hash != self._artifact.identity_hash:
            raise ValueError('GeoPhys task camera requires the declared artifact and world mount')
        if self._observer_render_request is None or state.boundary != self.state_boundary_identity():
            raise ValueError('GeoPhys task camera requires an admitted current observer scene')
        before = self._snapshot_with_native_free_joints()
        world = np.asarray(resolve_camera(camera, state).T_world_from_camera)
        visualizer = self._ensure_observer_visualizer(self._observer_render_request.camera)
        visualizer.bind_task_camera(camera_id=camera.camera_id, position=world[:3, 3],
            look_at=world[:3, 3] + world[:3, 2], up=-world[:3, 1],
            fov_degrees=math.degrees(camera.fov_y), near=camera.near, far=camera.far,
            width=camera.width, height=camera.height)
        self._declared_task_camera = camera
        if before != self._snapshot_with_native_free_joints():
            raise RuntimeError('physics changed during task camera binding')
        return self.task_camera_binding(state)

    def task_camera_binding(self, state):
        import math
        from ...observations.canonical_camera import resolve_camera
        self._require_reset()
        camera = getattr(self, '_declared_task_camera', None)
        if camera is None or self._observer_visualizer is None:
            raise RuntimeError('no GeoPhys task camera is bound')
        if state.boundary != self.state_boundary_identity():
            raise ValueError('task camera requires the current publication')
        before = self._snapshot_with_native_free_joints()
        native = self._observer_visualizer.read_task_camera()
        actual = np.eye(4)
        actual[:3, 0], actual[:3, 1], actual[:3, 2], actual[:3, 3] = native['right'], -np.asarray(native['up']), native['forward'], native['position']
        expected = np.asarray(resolve_camera(camera, state).T_world_from_camera)
        if (not np.allclose(actual, expected, atol=2e-6, rtol=0)
                or not math.isclose(native['fov_degrees'], math.degrees(camera.fov_y), abs_tol=2e-5)
                or not np.allclose([native['near'], native['far']], [camera.near, camera.far], atol=2e-6, rtol=0)):
            raise RuntimeError('native GeoPhys task camera differs from its declaration')
        point = expected[:3, 3] + .3 * expected[:3, 0] + .2 * expected[:3, 1] + 2 * expected[:3, 2]
        projection = self._observer_visualizer.project_task_camera(point)
        scene_frame = next((item for item in state.frames if item.frame.entity_id != 'world'), None)
        if scene_frame is None:
            raise ValueError('task camera requires a published scene frame')
        scene_point = list(scene_frame.pose_world.position)
        scene_projection = self._observer_visualizer.project_task_camera(scene_point)
        if before != self._snapshot_with_native_free_joints():
            raise RuntimeError('physics changed during task camera readback')
        return {'camera': camera.to_mapping(), 'camera_identity': camera.identity_hash,
                'native': native, 'native_world_transform': actual.tolist(),
                'projected_world_point': point.tolist(), 'projected_native_pixel_depth': projection,
                'scene_frame': scene_frame.frame.to_mapping(), 'scene_world_point': scene_point,
                'scene_native_pixel_depth': scene_projection,
                'state_boundary': state.boundary.to_mapping(),
                'source_closure': self._source.source_closure_digest}


    def capture_observer(self, camera, state):
        """Capture the published boundary using the existing GeoPhys scene owner."""
        return self._capture_raster_camera(camera, state, task=False)

    def capture_task_camera(self, camera, state):
        """Capture the separately bound task camera at the current boundary."""
        if camera != getattr(self, '_declared_task_camera', None):
            raise ValueError('GeoPhys task capture camera differs from its binding')
        self.task_camera_binding(state)
        return self._capture_raster_camera(camera, state, task=True)

    def _capture_raster_camera(self, camera, state, *, task):
        import hashlib
        import json
        import math
        from ...artifacts import RendererSelectionV1
        from ...observations.canonical_camera import CanonicalCameraObservation, resolve_camera
        from ...observations.canonical_camera.images import normalize_rgb
        from ...render.camera.source import CameraCaptureIdentityV1
        from ...render.camera.color import gamma22_to_srgb

        self._require_reset()
        if self._observer_render_request is None or self._observer_render_source is None:
            raise RuntimeError('GeoPhys observer was not admitted at materialization')
        if self._observer_fault:
            raise RuntimeError('GeoPhys observer fault requires a new runtime')
        if state.boundary != self.state_boundary_identity():
            raise ValueError('observer request does not match the current state boundary')
        before = self._snapshot_with_native_free_joints()
        metadata = resolve_camera(camera, state)
        try:
            self._ensure_observer_visualizer(camera)
            visualizer = self._observer_visualizer
            resources = visualizer.read_resources()
            material_report = resources.get('material_features')
            if not isinstance(material_report, dict):
                raise RuntimeError('GeoPhys observer cannot verify the material capability report')
            missing = tuple(material_report.get('missing_required', ()))
            unsupported = tuple(material_report.get('unsupported_authored', ()))
            uv_unsupported = tuple(material_report.get('unsupported_texture_uv_transform_channels', ()))
            orientation_unsupported = tuple(material_report.get('unsupported_texture_orientation_channels', ()))
            if missing or unsupported or uv_unsupported or orientation_unsupported:
                raise RuntimeError(f'GeoPhys observer material features are incomplete: '
                                   f'missing={missing!r}, unsupported={unsupported!r}, '
                                   f'uv={uv_unsupported!r}, orientation={orientation_unsupported!r}')
            light_report = resources.get('light_features')
            if not isinstance(light_report, dict):
                raise RuntimeError('GeoPhys observer cannot verify authored lighting')
            if light_report.get('unsupported'):
                raise RuntimeError(f'GeoPhys observer cannot preserve unsupported authored lighting: {light_report!r}')
            uses_default_sun = bool(light_report.get('uses_default_sun'))
            if self._observer_light_source_mode == 'supported-authored-mjcf-lights' and uses_default_sun:
                raise RuntimeError(f'GeoPhys observer substituted a renderer light for authored MJCF lighting: {light_report!r}')
            lighting_resources = resources.get('lighting')
            if (not isinstance(lighting_resources, dict) or
                    'unshadowed_casting_lights' not in lighting_resources or
                    lighting_resources['unshadowed_casting_lights']):
                raise RuntimeError(f'GeoPhys observer cannot preserve authored shadows: {lighting_resources!r}')
            self._observer_material_report = deepcopy(material_report)
            self._observer_light_report = deepcopy(light_report)
            self._observer_light_report['source_mode'] = self._observer_light_source_mode
            self._observer_light_report['authored_record_count'] = self._observer_authored_light_count
            world = np.asarray(metadata.T_world_from_camera, dtype=np.float64)
            position, forward, up = world[:3, 3], world[:3, 2], -world[:3, 1]
            if not task:
                visualizer.set_camera_pose(position, position + forward, up)
            track = self._observer_tracking_light
            if track is not None:
                snapshot = self._boundary.read_snapshot(SnapshotRequest(
                    qacc=False, ctrl=False, body_pose=True, site_pose=False, simulation_time=False))
                current_com = _world_center_of_mass(
                    self._observer_com_bodies,
                    self._observer_com_ids,
                    snapshot.body_xpos,
                    snapshot.body_xquat,
                )
                light_position = (
                    np.asarray(track.runtime_payload['authored_position'])
                    + current_com - self._observer_rest_com
                )
                visualizer.update_mjcf_light_pose(
                    track.light_id, position=light_position, direction=track.direction
                )
            if self._observer_headlight is not None:
                visualizer.update_mjcf_light_pose(
                    self._observer_headlight.light_id,
                    position=position,
                    direction=-forward,
                )
            self._observer_lighting_resources = deepcopy(visualizer.read_resources().get('lighting'))
            if task:
                rgb = np.array(visualizer.read_task_camera_frame(synchronized=True), dtype=np.float32, copy=True)
            else:
                visualizer.set_fov(math.degrees(camera.fov_y))
                visualizer.set_clip_interval(camera.near, camera.far)
                rgb = np.array(visualizer.read_frame(synchronized=True), dtype=np.float32, copy=True)
            after = self._snapshot_with_native_free_joints()
            if before != after or state.boundary != self.state_boundary_identity():
                raise RuntimeError('physics state or boundary changed during GeoPhys observer capture')
            execution_hash = getattr(self, '_observer_execution_identity', None)
            if execution_hash is None:
                raise RuntimeError('GeoPhys observer requires its declared execution identity')
            selection = RendererSelectionV1('renderer-selection-v1', 'geophys', 'rasterizer',
                                            'v211_geophys_cpu_task_rgb_v1' if task else
                                            'v211_geophys_cpu_observer_v1', 'cpu')
            capability = {'schema': 'v211-geophys-raster-observer-v1',
                          'capture': 'CPU raster read_frame synchronized; owned host copy',
                          'color': 'sRGB transfer after ACES; primaries uncalibrated',
                          'lighting_source_mode': self._observer_light_source_mode,
                          'renderer_uses_default_sun': uses_default_sun}
            capability_hash = hashlib.sha256(json.dumps(capability, sort_keys=True,
                                                       separators=(',', ':')).encode()).hexdigest()
            identity = CameraCaptureIdentityV1(
                'camera-capture-identity-v1', camera.task_artifact_hash, camera.camera_id,
                camera.identity_hash, self._source.source_closure_digest, execution_hash,
                selection, capability_hash, state.boundary, state.sample_clock, ('rgb',), camera.capture_phase)
            return CanonicalCameraObservation(normalize_rgb(gamma22_to_srgb(rgb), camera), None, metadata, identity)
        except BaseException as error:
            self._observer_fault = True
            visualizer, self._observer_visualizer = getattr(self, '_observer_visualizer', None), None
            if visualizer is not None:
                try:
                    visualizer.close()
                except BaseException as cleanup_error:
                    error.add_note(f'GeoPhys observer cleanup also failed: {cleanup_error!r}')
            raise

    def observer_render_facts(self):
        """Return the last admitted observer material report as an owned value."""
        if self._closed or self._observer_fault or self._observer_material_report is None:
            raise RuntimeError('GeoPhys observer has no current admitted material report')
        return {'backend': 'geophys-rasterizer',
                'material_features': deepcopy(self._observer_material_report),
                'light_features': deepcopy(self._observer_light_report),
                'lighting_source_mode': self._observer_light_source_mode,
                'lighting': deepcopy(self._observer_lighting_resources),
                'color_transfer': 'sRGB after ACES; primaries uncalibrated'}

    def _capture_actuator_force(self, state):
        self._require_reset()
        native = self._boundary.read_snapshot(SnapshotRequest(qacc=False, ctrl=True,
            body_pose=False, site_pose=False, actuator_force=True, simulation_time=True))
        if float(native.simulation_time) != float(state.simulation_time):
            raise ValueError('GeoPhys actuator-force readback is not at the requested evaluation boundary')
        actuator_index = self._open_actuators[0]
        if native.actuator_force is None or not np.all(np.isfinite(native.actuator_force)):
            raise ValueError('GeoPhys required actuator-force sample is non-finite or missing')
        if native.ctrl is None or not np.isfinite(native.ctrl[actuator_index]):
            raise ValueError('GeoPhys required actuator-force sample has no finite actuator input')
        signed_force_N = float(native.actuator_force[actuator_index])
        measurement = native.actuator_force_measurement
        if measurement is None:
            raise ValueError('GeoPhys required actuator-force sample has no validity contract')
        dt = float(self._artifact.timebase.physics_dt)
        native_sample_time_s = (
            0.0
            if measurement.phase == 'reset_forward'
            else max(0.0, float(measurement.native_step_index - 1) * dt)
        )
        from dataclasses import replace

        measurement = replace(
            measurement,
            episode_id=str(self._episode_id),
            reset_sample_id=str(self._reset_sample_id),
            evaluation_control_step=int(state.control_step),
            evaluation_simulation_time_s=float(state.simulation_time),
            actuator_id=str(self._source.open_actuators[0]),
            actuator_ctrl=float(native.ctrl[actuator_index]),
            signed_force_N=signed_force_N,
            native_sample_time_s=native_sample_time_s,
        )
        if measurement.source_generation != self._force_source_generation:
            raise ValueError('GeoPhys actuator-force sample belongs to another solver identity')
        if measurement.reset_sample_id != self._reset_sample_id:
            raise ValueError('GeoPhys actuator-force sample belongs to another ResetSample')
        if measurement.actuator_id != self._source.open_actuators[0]:
            raise ValueError('GeoPhys actuator-force sample has the wrong actuator identity')
        if measurement.valid:
            self._validate_actuator_force_measurement(state, native, measurement)
        self._last_actuator_force_measurement = measurement
        return native, measurement

    def _snapshot_typed_actuator_force_values(self, boundary, sample_clock, requirements):
        from ...artifacts import TypedActuatorForceStateValue, UnavailableStateValue

        if not getattr(self, '_r1_force_admitted', False):
            return (), tuple(UnavailableStateValue(
                'unavailable-state-value-v1', item.field_name, item.subject_kind,
                item.entity_id, item.subject_id, item.sample_domain,
                'GeoPhys typed actuator force is limited to the admitted Panda R1 source binding',
            ) for item in requirements)
        state = self.snapshot()
        if (state.control_step != boundary.control_step
                or float(state.simulation_time) != sample_clock.simulation_time_s):
            raise ValueError('typed force readback boundary changed during state publication')
        native, measurement = self._capture_actuator_force(state)
        actuator_index = self._open_actuators[0]
        values = []
        for item in requirements:
            if (item.entity_id, item.subject_id, item.unit) != (
                'panda-main', self._source.open_actuators[0], 'N',
            ):
                missing_requirements = requirements[len(values):]
                return tuple(values), tuple(UnavailableStateValue(
                    'unavailable-state-value-v1', requirement.field_name,
                    requirement.subject_kind, requirement.entity_id,
                    requirement.subject_id, requirement.sample_domain,
                    'GeoPhys bounded R1 force route only maps panda-main/actuator8 in N',
                ) for requirement in missing_requirements)
            values.append(TypedActuatorForceStateValue(
                'typed-actuator-force-state-v1',
                item.entity_id,
                item.subject_id,
                measurement.force_unit,
                measurement.signed_force_N if measurement.valid else None,
                measurement.actuator_ctrl if measurement.valid else None,
                measurement.valid,
                measurement.invalid_reason,
                measurement.source_generation,
                measurement.sample_sequence,
                measurement.state_revision,
                measurement.configuration_revision,
                self._source.source_closure_digest,
                self._provider_materialization_id,
                measurement.phase,
                measurement.native_step_index,
                float(self._artifact.timebase.physics_dt),
                float(measurement.native_sample_time_s or 0.0),
                str(self._episode_id),
                str(self._reset_sample_id),
                boundary.boundary_id,
                int(state.control_step),
                float(state.simulation_time),
            ))
            self._last_typed_force_publication = values[-1]
        return tuple(values), ()

    def control_feedback(self, state, *, actuator_force=None):
        from .control import feedback_value
        self._require_reset()
        if not hasattr(self, '_control_binding'):
            raise ValueError('control session admission required')
        if not getattr(self, '_force_feedback_required', False):
            raise ValueError('actuator-force feedback is not admitted for this Controller profile')
        if getattr(self, '_r1_force_admitted', False) and actuator_force is None:
            raise ValueError('plan-bound R1 feedback requires its current typed force publication')
        native, measurement = self._capture_actuator_force(state)
        if not measurement.valid:
            raise ValueError(
                'GeoPhys required actuator-force sample is invalid: '
                f'{measurement.invalid_reason or "unknown reason"}'
            )
        signed_force_N = float(measurement.signed_force_N)
        if actuator_force is not None:
            from ...artifacts import TypedActuatorForceStateValue
            if not isinstance(actuator_force, TypedActuatorForceStateValue):
                raise TypeError('typed Controller feedback requires TypedActuatorForceStateValue')
            if actuator_force != getattr(self, '_last_typed_force_publication', None):
                raise ValueError('typed actuator-force value is not the current RuntimeSession publication')
            if (actuator_force.actuator_id != measurement.actuator_id
                    or actuator_force.entity_id != 'panda-main'
                    or actuator_force.unit != measurement.force_unit
                    or actuator_force.signed_value != measurement.signed_force_N
                    or actuator_force.actuator_control_value != measurement.actuator_ctrl
                    or actuator_force.source_generation != measurement.source_generation
                    or actuator_force.sample_sequence != measurement.sample_sequence
                    or actuator_force.source_state_revision != measurement.state_revision
                    or actuator_force.configuration_revision != measurement.configuration_revision
                    or actuator_force.source_closure_digest != self._source.source_closure_digest
                    or actuator_force.provider_materialization_id != self._provider_materialization_id
                    or actuator_force.native_step_index != measurement.native_step_index
                    or actuator_force.sample_phase != measurement.phase
                    or actuator_force.episode_id != measurement.episode_id
                    or actuator_force.reset_sample_id != measurement.reset_sample_id):
                raise ValueError('typed actuator-force publication differs from the current Provider sample')
            signed_force_N = float(actuator_force.signed_value)
        return feedback_value(self, state, signed_force_N)

    def bind_mixed_controller(self, controller_identity):
        if self._mixed_actuator_plan is None:
            raise RuntimeError('mixed Controller binding is restricted to a mixed actuator source')
        if self._reset_done or self._mixed_controller_identity is not None:
            raise RuntimeError('mixed Controller must bind exactly once before reset')
        if (type(controller_identity) is not str or not controller_identity.strip()
                or controller_identity != self._mixed_actuator_plan.controller_identity):
            raise ValueError('mixed Controller identity differs from the source-bound plan')
        self._mixed_controller_identity = controller_identity

    def apply_mixed_actuator_command(self, target):
        from ...controllers.canonical.contracts import (
            AppliedMixedActuatorCommandV1, MixedActuatorCommandV1,
        )
        from ...environment import ControlCommand

        self._require_reset()
        if self._mixed_actuator_plan is None:
            raise RuntimeError('mixed actuator command requires an admitted source-bound plan')
        if self._mixed_fault is not None:
            raise RuntimeError('mixed actuator GeoPhys session is fault-latched')
        if type(target) is not MixedActuatorCommandV1:
            raise TypeError('GeoPhys mixed actuator route requires MixedActuatorCommandV1')
        target.validate()
        state = self.snapshot()
        if (target.controller_identity != self._mixed_controller_identity
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
            raise ValueError('GeoPhys mixed target identity or boundary is stale/mismatched')
        boundary = (target.episode_id, target.reset_sample_id, target.control_step, target.state_revision)
        if boundary in self._mixed_consumed_boundaries or self._mixed_pending_target is not None:
            raise ValueError('GeoPhys mixed target boundary was already consumed or is still pending')
        channels = {item.semantic_id: item for item in self._mixed_actuator_plan.channels}
        requested = dict(target.channel_values)
        units = dict(target.channel_units)
        if set(requested) != set(channels) or set(units) != set(channels):
            raise ValueError('GeoPhys mixed command does not cover every declared source channel')
        ctrl = np.array(self._current_ctrl, copy=True)
        actual_values = {}
        clipped = False
        for semantic, channel in channels.items():
            value = float(requested[semantic])
            low, high = channel.control_range
            actuator_id = self._mixed_channel_actuators[semantic]
            actual_low, actual_high = (float(item) for item in self._ctrl_range[actuator_id])
            if (units[semantic] != channel.unit or not np.isfinite(value)
                    or not low <= value <= high
                    or not np.allclose((actual_low, actual_high), (low, high), rtol=0.0, atol=1e-7)):
                raise ValueError(f'GeoPhys mixed command differs from its typed source range: {semantic}')
            ctrl[actuator_id] = value
            actual_values[semantic] = value
        try:
            zeros = np.zeros_like(ctrl)
            applied = self._boundary.apply_control(ControlCommand(
                ctrl, zeros, zeros, ctrl, zeros, 'named_mixed_actuator',
            ))
            applied_ctrl = np.asarray(applied.applied_ctrl, dtype=np.float64)
            if applied_ctrl.shape != ctrl.shape or not np.isfinite(applied_ctrl).all():
                raise ValueError('GeoPhys mixed command did not return a finite actuator vector')
            actual_values = {
                semantic: float(applied_ctrl[actuator_id])
                for semantic, actuator_id in self._mixed_channel_actuators.items()
            }
            boundary_ctrl = np.asarray(ctrl, dtype=np.float32)
            represented_values = {
                semantic: float(boundary_ctrl[actuator_id])
                for semantic, actuator_id in self._mixed_channel_actuators.items()
            }
            # GeoPhys control storage is float32. Compare the applied vector to
            # the representable request written into that vector, so ordinary
            # float64-to-float32 rounding is not misreported as provider clipping.
            clipped = any(actual_values[key] != represented_values[key] for key in channels)
            if clipped:
                raise ValueError('GeoPhys clipped a source-range-validated mixed command')
            self._current_ctrl = np.array(applied_ctrl, copy=True)
        except BaseException as error:
            self._mixed_fault = {
                'phase': 'partial_control_apply',
                'error': f'{type(error).__name__}: {error}',
            }
            raise
        self._mixed_consumed_boundaries.add(boundary)
        self._mixed_pending_target = target
        result = AppliedMixedActuatorCommandV1(
            'applied-mixed-actuator-command-v1', target.identity_hash, 'geophys',
            actual_values, units, clipped,
            'source_bound_named_actuator_channels_float32_control_zoh_v1',
        )
        result.validate()
        return result

    def step_mixed_actuator_interval(self, command_factory):
        from ...controllers.canonical.contracts import (
            AppliedMixedActuatorCommandV1, MixedActuatorCommandV1,
        )
        self._require_reset()
        if self._mixed_actuator_plan is None or self._mixed_fault is not None:
            raise RuntimeError('GeoPhys stepwise commands require an admitted, healthy mixed profile')
        if not callable(command_factory) or self._mixed_pending_target is not None:
            raise ValueError('GeoPhys mixed interval requires a callback and no pending command')
        if self._inner_interval_active:
            raise RuntimeError('GeoPhys mixed intervals cannot be nested')
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
                    raise TypeError('GeoPhys stepwise Controller must return MixedActuatorCommandV1')
                applied = self.apply_mixed_actuator_command(target)
                if type(applied) is not AppliedMixedActuatorCommandV1:
                    raise TypeError('GeoPhys returned an untyped mixed-control acknowledgement')
                if self._mixed_pending_target is not target:
                    raise RuntimeError('GeoPhys mixed interval lost the consumed target identity')
                self._boundary.step(substeps=1)
                self._native_steps += 1
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
            self._control_step += 1
            self._inner_interval_active = False
            result_state = self.snapshot()
            if (result_state.control_step != start_state.control_step + 1
                    or self._state_revision != start_revision + count
                    or self._native_steps % count != 0):
                raise ValueError('GeoPhys interval did not close on its declared outer/native boundary')
            return result_state, {
                'schema_version': 'mixed-actuator-stepwise-interval-receipt-v1',
                'provider_name': 'geophys',
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

    def read_contact_summary_v2(self, requested_pairs):
        from ...environment.types import ContactSummaryV2
        self._require_reset()
        normalized = tuple(sorted({tuple(sorted((str(a), str(b)))) for a, b in requested_pairs}))
        if any(len(pair) != 2 or pair[0] == pair[1] for pair in normalized):
            raise ValueError('GeoPhys contact query requires distinct named pairs')
        state = self.snapshot()
        return ContactSummaryV2.unavailable(
            source_id=self._source.scene_source.source_id,
            source_closure_digest=self._source.source_closure_digest,
            provider_materialization_id=self._provider_materialization_id,
            episode_id=self._episode_id,
            reset_sample_id=self._reset_sample_id,
            control_step=self._control_step,
            state_revision=self._state_revision,
            simulation_time_s=state.simulation_time,
            requested_pairs=normalized,
            reason='provider_contact_pair_query_not_implemented',
        )

    def _validate_actuator_force_measurement(self, state, native, measurement=None):
        measurement = measurement or native.actuator_force_measurement
        if measurement is None:
            raise ValueError('GeoPhys required actuator-force sample has no validity contract')
        if not measurement.valid:
            raise ValueError(
                'GeoPhys required actuator-force sample is invalid: '
                f'{measurement.invalid_reason or "unknown reason"}'
            )
        if measurement.force_unit != 'N':
            raise ValueError('GeoPhys required actuator-force sample unit must be N')
        if float(native.simulation_time) != float(state.simulation_time):
            raise ValueError('GeoPhys actuator-force sample time differs from evaluation boundary')
        if measurement.actuator_id != self._source.open_actuators[0]:
            raise ValueError('GeoPhys actuator-force sample has the wrong actuator identity')
        if measurement.reset_sample_id != self._reset_sample_id:
            raise ValueError('GeoPhys actuator-force sample belongs to another ResetSample')
        if self._force_source_generation is None or (
            measurement.source_generation != self._force_source_generation
        ):
            raise ValueError('GeoPhys actuator-force sample belongs to another solver identity')
        if native.actuator_force is None or not np.all(np.isfinite(native.actuator_force)):
            raise ValueError('GeoPhys required actuator-force sample is non-finite or missing')
        dt = float(self._artifact.timebase.physics_dt)
        expected_native_step = int(round(float(state.simulation_time) / dt))
        if abs(float(state.simulation_time) / dt - expected_native_step) > 1.0e-7:
            raise ValueError('GeoPhys actuator-force sample clock is not on a native-step boundary')
        steps_per_control = int(self._artifact.timebase.control_substeps)
        expected_from_control = int(state.control_step) * steps_per_control
        if self._inner_interval_active:
            valid_native_range = range(expected_from_control,
                                       expected_from_control + steps_per_control)
            if expected_native_step not in valid_native_range:
                raise ValueError('GeoPhys actuator-force sample is outside the active native interval')
        elif expected_native_step != expected_from_control:
            raise ValueError('GeoPhys actuator-force sample clock differs from the control boundary')
        if measurement.native_step_index != expected_native_step:
            raise ValueError('GeoPhys actuator-force sample native index does not match the state boundary')
        if (
            measurement.evaluation_control_step != int(state.control_step)
            or measurement.evaluation_simulation_time_s != float(state.simulation_time)
        ):
            raise ValueError('GeoPhys actuator-force sample belongs to another evaluation boundary')
        if expected_native_step == 0:
            reset_measurement = self._reset_force_measurement
            if (
                measurement.phase != 'reset_forward'
                or reset_measurement is None
                or measurement.sample_sequence != reset_measurement.sample_sequence
                or measurement.state_revision != reset_measurement.state_revision
                or measurement.configuration_revision != reset_measurement.configuration_revision
                or measurement.episode_id != reset_measurement.episode_id
                or measurement.reset_sample_id != reset_measurement.reset_sample_id
                or float(state.simulation_time) != 0.0
            ):
                raise ValueError('first R1 feedback is not the current reset-forward force sample')
            if measurement.native_sample_time_s != 0.0:
                raise ValueError('reset-forward force sample must use native time zero')
        else:
            if (
                measurement.phase != 'native_step_pre_integration'
                or measurement.sample_sequence <= self._last_reset_force_sequence
            ):
                raise ValueError('GeoPhys feedback is not from a completed native-step force sample')
            expected_sample_time = float(expected_native_step - 1) * dt
            if measurement.native_sample_time_s != expected_sample_time:
                raise ValueError('GeoPhys force sample phase/time does not match its native-step index')
            previous = self._last_actuator_force_measurement
            if previous is not None:
                if previous.episode_id != measurement.episode_id:
                    raise ValueError('GeoPhys actuator-force sample belongs to another episode')
                if previous.evaluation_simulation_time_s == float(state.simulation_time):
                    if (
                        previous.sample_sequence != measurement.sample_sequence
                        or previous.state_revision != measurement.state_revision
                        or previous.configuration_revision != measurement.configuration_revision
                    ):
                        raise ValueError('GeoPhys force sample changed within one native evaluation state')
                else:
                    elapsed_native_steps = int(round(
                        (float(state.simulation_time) - previous.evaluation_simulation_time_s) / dt
                    ))
                    if elapsed_native_steps <= 0 or abs(
                        (float(state.simulation_time) - previous.evaluation_simulation_time_s)
                        - elapsed_native_steps * dt
                    ) > 1.0e-10:
                        raise ValueError('GeoPhys force evaluation boundaries are not separated by native steps')
                    native_step_advance = measurement.native_step_index - previous.native_step_index
                    sample_sequence_advance = measurement.sample_sequence - previous.sample_sequence
                    if (native_step_advance != elapsed_native_steps
                            or sample_sequence_advance != elapsed_native_steps):
                        raise ValueError(
                            'GeoPhys native force sample does not match the completed native-step gap '
                            f'(expected {elapsed_native_steps}, native index advanced {native_step_advance}, '
                            f'sample sequence advanced {sample_sequence_advance})'
                        )

    def native_control_feedback_sample(self, state, feedback):
        """Return the exact validated force sample consumed by this feedback."""
        from ...controllers.canonical.feedback import NativeControlFeedbackSampleV1

        self._require_reset()
        measurement = self._last_actuator_force_measurement
        if (measurement is None or feedback.control_step != state.control_step
                or feedback.simulation_time != state.simulation_time
                or measurement.evaluation_control_step != state.control_step
                or measurement.evaluation_simulation_time_s != state.simulation_time
                or feedback.gripper.closing_force_N != max(0.0, -float(measurement.signed_force_N))):
            raise ValueError('GeoPhys native feedback sample is not the measured Controller input')
        sample = NativeControlFeedbackSampleV1(
            'native-control-feedback-sample-v1', self._provider,
            self._provider_materialization_id, self._source.scene_source.source_id,
            self._source.source_closure_digest, str(self._episode_id),
            str(self._reset_sample_id), feedback, measurement,
        )
        sample.validate()
        return sample

    def apply_control(self, target):
        if self._mixed_actuator_plan is not None:
            return self.apply_mixed_actuator_command(target)
        from .control import validate_target
        from ...controllers.canonical.contracts import AppliedCanonicalControl
        from ...environment import ControlCommand
        validate_target(self, target)
        ctrl = np.array(self._current_ctrl, copy=True)
        for name, value in target.arm_servo_position.items():
            ctrl[self._target_actuators[name]] = value
        index = getattr(self, '_open_actuators_by_semantic', {}).get(
            target.gripper.semantic_id, self._open_actuators[0],
        )
        control_binding = getattr(self, '_position_control_bindings_by_semantic', {}).get(
            target.gripper.semantic_id, self._control_binding,
        )
        low, high = self._ctrl_range[index]
        ctrl[index] = low + target.gripper.servo_opening_m / control_binding.opening_range_m * (high-low)
        self._boundary.set_actuator_force_limits((index,), target.gripper.force_limit_N)
        zeros = np.zeros_like(ctrl)
        applied = self._boundary.apply_control(ControlCommand(ctrl, zeros, zeros, ctrl, zeros, "canonical_position"))
        self._current_ctrl = np.array(applied.applied_ctrl, copy=True)
        realized = {name: float(applied.applied_ctrl[self._target_actuators[name]])
                    for name in target.arm_joint_order}
        opening = float((applied.applied_ctrl[index]-low)/(high-low)*control_binding.opening_range_m)
        return AppliedCanonicalControl('applied-canonical-control-v0', target.identity_hash, 'geophys',
            realized, opening, target.gripper.force_limit_N, applied.clipped,
            'named_position_servo_plus_affine_tendon_opening_force_limit_ZOH')

    def step(self):
        self._require_reset()
        physical_port = getattr(self, '_physical_port', None)
        if physical_port is not None:
            if physical_port.pending is None:
                raise RuntimeError('physical interval requires exactly one fresh batch')
            try:
                count = int(self._artifact.timebase.control_substeps)
                self._boundary.step(substeps=count)
                self._native_steps += count
                self._control_step += 1
                self._state_revision += 1
                return self.snapshot()
            finally:
                physical_port.finish_interval()
        if self._mixed_actuator_plan is not None:
            if self._mixed_fault is not None:
                raise RuntimeError('mixed actuator GeoPhys session is fault-latched')
            if self._mixed_pending_target is None:
                raise RuntimeError('GeoPhys mixed outer step requires one fresh named target')
            try:
                self._boundary.step(substeps=self._artifact.timebase.control_substeps)
                self._native_steps += int(self._artifact.timebase.control_substeps)
                self._control_step += 1
                self._state_revision += 1
                self._mixed_pending_target = None
                return self.snapshot()
            except BaseException as error:
                self._mixed_fault = {
                    'phase': 'outer_step',
                    'error': f'{type(error).__name__}: {error}',
                    'native_steps_completed': int(self._native_steps),
                }
                raise
        self._boundary.step(
            substeps=self._artifact.timebase.control_substeps,
            track_actuator_force=bool(getattr(self, '_force_feedback_required', False)),
        )
        self._control_step += 1
        self._state_revision += 1
        return self.snapshot()

    def _step_physics_once(self):
        self._require_reset()
        self._boundary.step(substeps=1)

    def close(self):
        if not self._closed:
            port = getattr(self, '_physical_port', None)
            failure = None
            if port is not None and port.pending is not None:
                try:
                    port.finish_interval()
                except BaseException as error:
                    failure = error
            boundary_close_completed = False
            source_receipt_close_completed = None
            visualizer, self._observer_visualizer = getattr(self, '_observer_visualizer', None), None
            camera_provider, self._legacy_camera_provider = getattr(self, '_legacy_camera_provider', None), None
            if camera_provider is not None:
                try:
                    camera_provider.close()
                except BaseException as error:
                    if failure is None:
                        failure = error
                    else:
                        failure.add_note(f'GeoPhys legacy camera cleanup also failed: {error!r}')
            legacy_visualizer, self._legacy_observer_visualizer = getattr(self, '_legacy_observer_visualizer', None), None
            if legacy_visualizer is not None:
                try:
                    legacy_visualizer.close()
                except BaseException as error:
                    if failure is None:
                        failure = error
                    else:
                        failure.add_note(f'GeoPhys legacy observer cleanup also failed: {error!r}')
            if visualizer is not None:
                try:
                    visualizer.close()
                except BaseException as error:
                    if failure is None:
                        failure = error
                    else:
                        failure.add_note(f'GeoPhys observer cleanup also failed: {error!r}')
            try:
                if self._boundary is not None:
                    self._boundary.close()
                boundary_close_completed = True
            except BaseException as error:
                if failure is None:
                    failure = error
                else:
                    failure.add_note(f'GeoPhys boundary cleanup also failed: {error!r}')
            receipt = getattr(self._source, 'execution_source_receipt', None)
            try:
                if receipt is not None:
                    receipt.close()
                    source_receipt_close_completed = True
            except BaseException as error:
                source_receipt_close_completed = False
                if failure is None:
                    failure = error
                else:
                    failure.add_note(
                        f'execution source snapshot cleanup also failed: {type(error).__name__}: {error}'
                    )
            self._boundary = None
            self._closed = True
            self._last_close_receipt = {
                'schema_version': 'geophys-runtime-close-v1',
                'provider_materialization_id': self._provider_materialization_id,
                'episode_id': self._episode_id,
                'reset_sample_id': self._reset_sample_id,
                'session_closed': True,
                'boundary_close_completed': bool(boundary_close_completed),
                'boundary_owner': 'process_owned_taichi_runtime',
                'execution_source_receipt_close_completed': source_receipt_close_completed,
                'cleanup_completed': failure is None,
                'cleanup_error': None if failure is None else {
                    'type': type(failure).__name__, 'message': str(failure),
                },
                'control_step': int(self._control_step),
                'native_step_count': int(self._native_steps),
                'source_id': self._source.scene_source.source_id,
                'source_closure_digest': self._source.source_closure_digest,
            }
            if failure is not None:
                raise failure
