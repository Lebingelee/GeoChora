"""Private MuJoCo peer adapter. No comparison/oracle or controller implementation."""
import xml.etree.ElementTree as ET
import math
import numpy as np

from .common import _SessionValues, pose
from .source import lower_mujoco_scene_source, source_asset_bytes


def _source_asset_bytes(base_dir, source_xml):
    """Backward-compatible private spelling for the shared source owner."""

    return source_asset_bytes(base_dir, source_xml)


class _MuJoCoSession(_SessionValues):
    def __init__(self, artifact, source):
        self._initialize_values(artifact, source, 'mujoco')
        import mujoco
        self._mj = mujoco
        assets = None
        if source.scene_definition is not None:
            source_xml, assets = lower_mujoco_scene_source(
                source.scene_source,
                source.scene_definition,
                source.source_closure_digest,
            )
        else:
            source_xml = source.scene_source.xml
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
        self._force_sample_sequence = 0
        self._force_configuration_revision = 0
        self._last_force_limit_N = None
        self._completed_actuator_ctrl = None
        self._completed_force_measurement = None
        if self._model.opt.timestep != artifact.timebase.physics_dt:
            raise ValueError('MuJoCo native timestep mismatch')
        self._joint_addresses = {
            semantic: self._addresses(native, free=False) for semantic, native in source.joints.items()
        }
        self._free_addresses = {semantic: self._addresses(native, free=True)
                                for semantic, native in source.free_joints.items()}
        self._bodies = {semantic: self._model.body(native).id for semantic, native in source.bodies.items()}
        self._frames = {semantic: self._model.site(native).id for semantic, native in source.frames.items()}
        self._target_actuators = {semantic: self._model.actuator(native).id for semantic, native in source.joint_targets.items()}
        self._open_actuators = tuple(self._model.actuator(native).id for native in source.open_actuators)
        self._leaf_plan = None
        self._leaf_materialization_receipt = None
        self._leaf_configuration_revision = None
        self._leaf_active_plan_identity = None
        self._leaf_fault = None
        self._leaf_interval_active = False
        self._leaf_interval_boundary_id = None
        self._leaf_interval_source_boundary = None
        self._leaf_interval_source_sample_clock = None
        self._leaf_interval_source_configuration_revision = None
        self._leaf_interval_writers = set()
        self._leaf_consumed_boundaries = set()
        self._validate_canonical_scene_model()

    @property
    def leaf_materialization_receipt(self):
        if self._leaf_materialization_receipt is None:
            raise RuntimeError('MuJoCo RuntimeSession has no admitted leaf materialization')
        return self._leaf_materialization_receipt

    @property
    def leaf_configuration_revision(self):
        if self._leaf_configuration_revision is None:
            raise RuntimeError('MuJoCo RuntimeSession has no admitted leaf configuration')
        return self._leaf_configuration_revision

    @property
    def leaf_control_fault(self):
        return self._leaf_fault

    @property
    def active_leaf_plan_identity(self):
        return self._leaf_active_plan_identity

    def admit_leaf_control_plan(self, plan):
        """Bind the public R02b receipt to this compiled MuJoCo model."""
        from ...controllers.canonical.leaf_plan import EffectiveLeafPlanV1
        from ...runtime.sessions.leaf_control import (
            LeafMaterializationReceiptV1, LeafNativeActuatorMappingV1,
            LeafNativeFrameMappingV1, LeafNativeJointMappingV1,
            LeafNativeTendonMappingV1,
        )
        if type(plan) is not EffectiveLeafPlanV1 or not plan._compiled:
            raise TypeError('MuJoCo leaf admission requires a compiled EffectiveLeafPlanV1')
        if (plan.scene_identity_sha256 != self._source.scene_definition.identity_hash
                or plan.source_closure_sha256 != self._source.source_closure_digest
                or plan.provider_name != 'mujoco' or plan.backend != 'cpu'
                or plan.physics_dt_s != self._artifact.timebase.physics_dt
                or plan.control_substeps != self._artifact.timebase.control_substeps):
            raise ValueError('MuJoCo model/source differs from the exact leaf plan')
        model, mj = self._model, self._mj
        dimensions = (int(model.nq), int(model.nv), int(model.nu), int(model.njnt),
                      int(model.nbody), int(model.neq), int(model.ntendon))
        if dimensions != (9, 9, 8, 9, dimensions[4], 1, 1):
            raise ValueError(f'R02c full-Panda native dimensions are not the fixed 9/9/8/9/1/1 route: {dimensions}')
        if any(int(value) == int(mj.mjtJoint.mjJNT_FREE) for value in model.jnt_type):
            raise ValueError('R02c source unexpectedly contains an additional free root')
        joint_maps = []
        native_joint_id_by_name = {}
        for entry in plan.leaves:
            binding = entry.binding
            for ref, limits in zip(binding.joint_order, binding.joint_position_limits, strict=True):
                native_name = ref.joint_id
                joint_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, native_name))
                if joint_id < 0:
                    raise ValueError(f'planned native Joint {native_name!r} is absent')
                unit = binding.joint_position_unit
                expected_type = mj.mjtJoint.mjJNT_HINGE if unit == 'radian' else mj.mjtJoint.mjJNT_SLIDE
                if int(model.jnt_type[joint_id]) != int(expected_type):
                    raise ValueError(f'native Joint {native_name!r} has the wrong MuJoCo type')
                if not bool(model.jnt_limited[joint_id]) or not np.allclose(
                    model.jnt_range[joint_id], limits, rtol=0.0, atol=1.0e-12,
                ):
                    raise ValueError(f'native Joint {native_name!r} limits differ from the leaf contract')
                qadr, dadr = int(model.jnt_qposadr[joint_id]), int(model.jnt_dofadr[joint_id])
                native_joint_id_by_name[native_name] = joint_id
                joint_maps.append(LeafNativeJointMappingV1(
                    'leaf-native-joint-mapping-v1', ref, native_name, joint_id,
                    qadr, dadr, unit,
                ))
        actuator_maps = []
        native_actuator_ids = set()
        for entry in plan.leaves:
            binding = entry.binding
            if binding.profile_kind == 'arm_position':
                pairs = binding.joint_actuator_bindings
            else:
                pairs = ()
            if pairs:
                for pair in pairs:
                    actuator_ref = pair.actuator
                    native_name = actuator_ref.actuator_id
                    actuator_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, native_name))
                    if actuator_id < 0:
                        raise ValueError(f'planned native Actuator {native_name!r} is absent')
                    trn_type = int(model.actuator_trntype[actuator_id])
                    trn_id = int(model.actuator_trnid[actuator_id, 0])
                    target_name = mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, trn_id)
                    if (trn_type != int(mj.mjtTrn.mjTRN_JOINT)
                            or target_name != pair.joint.joint_id):
                        raise ValueError(f'Arm actuator {native_name!r} transmission differs from its Joint binding')
                    limits = tuple(float(item) for item in model.actuator_ctrlrange[actuator_id])
                    if not bool(model.actuator_ctrllimited[actuator_id]):
                        raise ValueError(f'Arm actuator {native_name!r} must preserve its source ctrlrange')
                    actuator_maps.append(LeafNativeActuatorMappingV1(
                        'leaf-native-actuator-mapping-v1', actuator_ref, native_name,
                        actuator_id, actuator_id, limits,
                        'radian', 'joint', str(target_name),
                    ))
                    native_actuator_ids.add(actuator_id)
            else:
                actuator_ref = binding.actuator_order[0]
                native_name = actuator_ref.actuator_id
                actuator_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, native_name))
                if actuator_id < 0:
                    raise ValueError(f'planned native Hand actuator {native_name!r} is absent')
                trn_type = int(model.actuator_trntype[actuator_id])
                trn_id = int(model.actuator_trnid[actuator_id, 0])
                target_name = mj.mj_id2name(model, mj.mjtObj.mjOBJ_TENDON, trn_id)
                if trn_type != int(mj.mjtTrn.mjTRN_TENDON) or target_name != 'split':
                    raise ValueError('Hand actuator8 is not connected to the exact split tendon')
                limits = tuple(float(item) for item in model.actuator_ctrlrange[actuator_id])
                if (not bool(model.actuator_ctrllimited[actuator_id])
                        or limits != tuple(binding.native_ctrlrange)):
                    raise ValueError('Hand actuator ctrlrange differs from the bound 0..255 range')
                actuator_maps.append(LeafNativeActuatorMappingV1(
                    'leaf-native-actuator-mapping-v1', actuator_ref, native_name,
                    actuator_id, actuator_id, limits,
                    'native_ctrl', 'tendon', str(target_name),
                ))
                native_actuator_ids.add(actuator_id)
        if native_actuator_ids != set(range(int(model.nu))):
            raise ValueError('R02c leaf writers do not own every native MuJoCo ctrl slot exactly once')
        frame_maps = []
        for entry in plan.leaves:
            ref = entry.binding.tcp_frame
            body_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, ref.frame_id))
            if body_id <= 0:
                raise ValueError(f'leaf TCP Body {ref.frame_id!r} is missing or is world')
            frame_maps.append(LeafNativeFrameMappingV1(
                'leaf-native-frame-mapping-v1', ref, ref.frame_id, body_id,
            ))
        tendon_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_TENDON, 'split'))
        if tendon_id < 0 or int(model.tendon_num[tendon_id]) != 2:
            raise ValueError('R02c native Hand split tendon must contain exactly two wraps')
        tendon_adr = int(model.tendon_adr[tendon_id])
        wrap_joint_ids = tuple(int(value) for value in model.wrap_objid[tendon_adr:tendon_adr + 2])
        wrap_types = tuple(int(value) for value in model.wrap_type[tendon_adr:tendon_adr + 2])
        wrap_coefficients = tuple(float(value) for value in model.wrap_prm[tendon_adr:tendon_adr + 2])
        expected_fingers = tuple(native_joint_id_by_name[name] for name in ('finger_joint1', 'finger_joint2'))
        if (wrap_joint_ids != expected_fingers
                or any(value != int(mj.mjtWrap.mjWRAP_JOINT) for value in wrap_types)
                or wrap_coefficients != (0.5, 0.5)):
            raise ValueError('R02c native split tendon finger order/coefficients differ from source')
        equality_matches = []
        for eq_id in range(int(model.neq)):
            if (int(model.eq_type[eq_id]) == int(mj.mjtEq.mjEQ_JOINT)
                    and {int(model.eq_obj1id[eq_id]), int(model.eq_obj2id[eq_id])} == set(expected_fingers)):
                equality_matches.append(eq_id)
        if len(equality_matches) != 1:
            raise ValueError('R02c requires the exact one native finger-joint equality')
        receipt = LeafMaterializationReceiptV1(
            'leaf-materialization-receipt-v1', 'provider_materialization',
            plan.scene_identity_sha256, plan.source_closure_sha256, plan.identity_sha256,
            'mujoco', plan.provider_version, plan.provider_build_sha256, 'cpu',
            self._provider_materialization_id, 'leaf-' + plan.identity_sha256[:20],
            int(model.nq), int(model.nv), int(model.nu), int(model.njnt), int(model.nbody),
            int(model.neq), int(model.ntendon), tuple(joint_maps), tuple(actuator_maps),
            tuple(frame_maps), (LeafNativeTendonMappingV1(
                'leaf-native-tendon-mapping-v1', 'hand.xml/tendon/split', 'split',
            ),), ('hand.xml/equality/finger_joint1=finger_joint2',),
        )
        receipt.validate_against_plan(plan)
        self._leaf_plan = plan
        self._leaf_materialization_receipt = receipt
        self._leaf_configuration_revision = receipt.configuration_revision
        self._leaf_fault = None
        self._leaf_consumed_boundaries.clear()

    def read_leaf_runtime_clock(self):
        from ...artifacts.state import StateBoundaryIdentity, StateSampleClock
        from ...runtime.sessions.leaf_control import LeafRuntimeClockV1
        self._require_reset()
        if self._leaf_plan is None:
            raise RuntimeError('MuJoCo session has no admitted leaf plan')
        state = self.snapshot()
        boundary = StateBoundaryIdentity(
            'state-boundary-identity-v1', self._episode_id, self._reset_sample_id,
            self._leaf_plan.scene_identity_sha256, self._scene_instance_id,
            self._provider_materialization_id, self._control_step, self._state_revision,
        )
        clock = StateSampleClock(
            'state-sample-clock-v1', 'evaluation_boundary', self._control_step,
            float(state.simulation_time),
        )
        return LeafRuntimeClockV1(
            'leaf-runtime-clock-v1', boundary, clock, self.leaf_configuration_revision,
        )

    def validate_leaf_materialization(self, receipt, plan):
        if (receipt != self.leaf_materialization_receipt or plan is not self._leaf_plan
                or receipt.provenance_kind != 'provider_materialization'):
            raise ValueError('leaf materialization receipt is not owned by this MuJoCo model')
        receipt.validate_against_plan(plan)

    def validate_leaf_writer_available(self, writer_id, actuator_refs, receipt):
        self.validate_leaf_materialization(receipt, self._leaf_plan)
        if self._leaf_fault is not None:
            raise RuntimeError('MuJoCo leaf RuntimeSession is fault-latched')
        entry = next((item for item in self._leaf_plan.leaves if item.binding.writer_id == writer_id), None)
        if entry is None or tuple(entry.binding.actuator_order) != tuple(actuator_refs):
            raise ValueError('requested leaf writer does not own the exact planned Actuator order')
        if self._leaf_interval_active:
            raise RuntimeError('MuJoCo leaf interval is already active')

    def begin_leaf_control_interval(self, plan_identity, boundary_id):
        clock = self.read_leaf_runtime_clock()
        if (self._leaf_fault is not None or plan_identity != self._leaf_plan.identity_sha256
                or boundary_id != clock.boundary.boundary_id
                or boundary_id in self._leaf_consumed_boundaries):
            raise ValueError('MuJoCo leaf interval is stale, replayed or fault-latched')
        self._leaf_consumed_boundaries.add(boundary_id)
        self._leaf_active_plan_identity = plan_identity
        self._leaf_interval_active = True
        self._leaf_interval_boundary_id = boundary_id
        self._leaf_interval_source_boundary = clock.boundary
        self._leaf_interval_source_sample_clock = clock.sample_clock
        self._leaf_interval_source_configuration_revision = clock.configuration_revision
        self._leaf_interval_writers.clear()

    def apply_leaf_actuator_patch(self, patch):
        from ...runtime.sessions.leaf_control import LeafApplyResultV1
        from ...controllers.canonical.leaf_profiles import LeafApplicationAckV1
        if not self._leaf_interval_active or self._leaf_fault is not None:
            raise RuntimeError('MuJoCo leaf actuator patch requires an active, healthy interval')
        if patch.writer_id in self._leaf_interval_writers:
            raise ValueError('MuJoCo leaf writer attempted a duplicate actuator patch')
        entry = next((item for item in self._leaf_plan.leaves
                      if item.binding.writer_id == patch.writer_id), None)
        if entry is None or (patch.effective_plan_identity_sha256, patch.materialization_identity_sha256) != (
            self._leaf_plan.identity_sha256, self.leaf_materialization_receipt.identity_sha256,
        ):
            raise ValueError('MuJoCo patch is bound to another writer/plan/materialization')
        target = patch.target
        binding = entry.binding
        source_boundary = self._leaf_interval_source_boundary
        source_sample_clock = self._leaf_interval_source_sample_clock
        source_configuration_revision = self._leaf_interval_source_configuration_revision
        if (target.writer_id != binding.writer_id
                or target.binding_identity_hash != binding.identity_hash
                or target.source_closure_sha256 != self._source.source_closure_digest
                or target.scene_identity_hash != self._leaf_plan.scene_identity_sha256
                or target.source_boundary != source_boundary
                or target.sample_clock != source_sample_clock
                or patch.state_configuration_revision != source_configuration_revision
                or tuple(target.joint_order) != tuple(binding.joint_order)
                or tuple(target.actuator_order) != tuple(binding.actuator_order)
                or tuple(item.actuator for item in patch.slot_values) != tuple(binding.actuator_order)):
            raise ValueError('MuJoCo patch Target/slot/source clock differs from the consumed leaf evaluation')
        mapping = {item.canonical_actuator: item for item in self.leaf_materialization_receipt.actuators}
        for item in patch.slot_values:
            native = mapping.get(item.actuator)
            if (native is None or native.ctrl_slot != item.ctrl_slot
                    or not native.ctrlrange[0] <= item.value <= native.ctrlrange[1]):
                raise ValueError('MuJoCo leaf patch exceeds its exact native ctrl slot/range')
        current_clock = self.read_leaf_runtime_clock()
        current_boundary = current_clock.boundary
        same_evaluation = (
            source_boundary is not None
            and source_sample_clock is not None
            and source_configuration_revision is not None
            and current_clock.sample_clock == source_sample_clock
            and current_clock.configuration_revision == source_configuration_revision
            and (current_boundary.episode_id, current_boundary.reset_sample_id,
                 current_boundary.scene_identity_hash, current_boundary.scene_instance_id,
                 current_boundary.provider_materialization_id, current_boundary.control_step)
            == (source_boundary.episode_id, source_boundary.reset_sample_id,
                source_boundary.scene_identity_hash, source_boundary.scene_instance_id,
                source_boundary.provider_materialization_id, source_boundary.control_step)
            and current_boundary.state_revision
            == source_boundary.state_revision + len(self._leaf_interval_writers)
        )
        if not same_evaluation:
            raise ValueError('MuJoCo leaf patch crossed its consumed evaluation boundary')
        for item in patch.slot_values:
            self._data.ctrl[item.ctrl_slot] = item.value
        self._state_revision += 1
        self._current_ctrl = self._data.ctrl.copy()
        self._leaf_interval_writers.add(patch.writer_id)
        application_clock = self.read_leaf_runtime_clock()
        ack = LeafApplicationAckV1(
            'leaf-application-ack-v1', binding.profile_kind, binding.profile_id,
            binding.action_schema_id, target.identity_hash, binding.writer_id,
            binding.identity_hash, binding.source_closure_sha256, binding.scene_identity_hash,
            binding.joint_order, binding.actuator_order, target.source_boundary,
            target.sample_clock, application_clock.boundary, application_clock.sample_clock,
        )
        return LeafApplyResultV1(
            'leaf-apply-result-v1', binding.writer_id, patch.command_identity_sha256,
            patch.materialization_identity_sha256,
            tuple(item.ctrl_slot for item in patch.slot_values), ack,
        )

    def step_leaf_control_interval(self, *, substeps):
        if (not self._leaf_interval_active or self._leaf_fault is not None
                or substeps != self._leaf_plan.control_substeps
                or set(self._leaf_interval_writers) != {entry.binding.writer_id for entry in self._leaf_plan.leaves}):
            raise RuntimeError('MuJoCo leaf outer step requires all planned writer patches exactly once')
        self.step()
        self._leaf_interval_active = False
        self._leaf_interval_boundary_id = None
        self._leaf_interval_source_boundary = None
        self._leaf_interval_source_sample_clock = None
        self._leaf_interval_source_configuration_revision = None
        self._leaf_interval_writers.clear()

    def publish_leaf_state(self, scene, requirements):
        if self._leaf_plan is None or scene.identity_hash != self._leaf_plan.scene_identity_sha256:
            raise ValueError('MuJoCo leaf state publication Scene mismatch')
        return self.snapshot_v1(
            scene=scene,
            joint_bindings={
                f'{art.entity_id}/{joint.joint_id}': joint
                for art in scene.articulations or () for joint in art.joints if joint.kind != 'fixed'
            },
            frame_bindings={
                key: __import__('task_env.artifacts', fromlist=['FrameReference']).FrameReference(*key.split('/', 1))
                for key in (*self._source.bodies, *self._source.frames)
            }, requirements=requirements,
        )

    def latch_leaf_control_fault(self, progress, error):
        if self._leaf_fault is not None:
            raise RuntimeError('MuJoCo leaf fault is already latched')
        self._leaf_fault = progress
        self._leaf_interval_active = False
        self._leaf_interval_source_boundary = None
        self._leaf_interval_source_sample_clock = None
        self._leaf_interval_source_configuration_revision = None

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
                if not np.allclose(
                    self._model.jnt_axis[joint_id], joint.axis, rtol=0.0, atol=1.0e-9,
                ):
                    raise ValueError(
                        f'canonical Joint {joint.joint_id!r} axis differs in MuJoCo'
                    )

    def _addresses(self, name, *, free):
        joint = self._model.joint(name).id
        allowed = (self._mj.mjtJoint.mjJNT_FREE,) if free else (self._mj.mjtJoint.mjJNT_HINGE, self._mj.mjtJoint.mjJNT_SLIDE)
        if self._model.jnt_type[joint] not in allowed:
            raise ValueError('unsupported source joint representation')
        return int(self._model.jnt_qposadr[joint]), int(self._model.jnt_dofadr[joint])

    def reset(self, sample):
        self._begin_reset()
        self._validate_sample(sample)
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
        self._data.act[:] = 0
        for name, actuator in self._target_actuators.items():
            self._data.ctrl[actuator] = sample.joint_position[name]
        for actuator in self._open_actuators:
            self._data.ctrl[actuator] = self._model.actuator_ctrlrange[actuator, 1]
        if getattr(self, '_leaf_plan', None) is not None:
            from ...robots.gripper import position_gripper_ctrl_for_opening
            hand = next(entry for entry in self._leaf_plan.leaves
                        if entry.binding.profile_kind == 'hand_position')
            config = hand.section.values()
            actuator_ref = hand.binding.actuator_order[0]
            native = next(item for item in self._leaf_materialization_receipt.actuators
                          if item.canonical_actuator == actuator_ref)
            self._data.ctrl[native.ctrl_slot] = position_gripper_ctrl_for_opening(
                0.076, config['gripper_opening_range_m'],
                config['gripper_close_ctrl'], config['gripper_open_ctrl'],
            )
            self._leaf_fault = None
            self._leaf_active_plan_identity = None
            self._leaf_interval_active = False
            self._leaf_interval_boundary_id = None
            self._leaf_interval_source_boundary = None
            self._leaf_interval_source_sample_clock = None
            self._leaf_interval_source_configuration_revision = None
            self._leaf_interval_writers.clear()
            self._leaf_consumed_boundaries.clear()
        self._current_ctrl = self._data.ctrl.copy()
        self._mj.mj_forward(self._model, self._data)
        realized = self._realized(sample)
        self._cache_completed_actuator_force()
        return realized

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
        if self._artifact.timebase.control_substeps > 1 and not self._inner_interval_active:
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
        if getattr(self, '_r1_force_admitted', False):
            from ...artifacts import TypedActuatorForceStateValue

            if not isinstance(actuator_force, TypedActuatorForceStateValue):
                raise ValueError('plan-bound R1 feedback requires its current typed force publication')
            if actuator_force != getattr(self, '_last_typed_force_publication', None):
                raise ValueError('typed actuator-force value is not the current RuntimeSession publication')
            actuator_index = self._open_actuators[0]
            if (
                not actuator_force.valid
                or actuator_force.entity_id != 'panda-main'
                or actuator_force.actuator_id != self._source.open_actuators[0]
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
                or actuator_force.episode_id != self._episode_id
                or actuator_force.reset_sample_id != self._reset_sample_id
                or actuator_force.evaluation_control_step != state.control_step
                or actuator_force.evaluation_simulation_time_s != state.simulation_time
                or actuator_force.actuator_control_value != float(self._data.ctrl[actuator_index])
            ):
                raise ValueError('typed actuator-force publication differs from the current MuJoCo cache')
            signed_force = float(actuator_force.signed_value)
        else:
            if actuator_force is not None:
                raise ValueError('typed actuator-force injection is reserved for exact plan-bound R1 admission')
            signed_force = float(measurement.signed_force_N)
        return feedback_value(self, state, signed_force)

    def _snapshot_typed_actuator_force_values(self, boundary, sample_clock, requirements):
        """Project the existing reset/step force cache without running another forward pass."""
        from ...artifacts import TypedActuatorForceStateValue, UnavailableStateValue

        if not getattr(self, '_r1_force_admitted', False):
            return (), tuple(UnavailableStateValue(
                'unavailable-state-value-v1', item.field_name, item.subject_kind,
                item.entity_id, item.subject_id, item.sample_domain,
                'MuJoCo typed actuator force is limited to the exact admitted Panda R1 candidate',
            ) for item in requirements)
        if self._inner_interval_active:
            raise ValueError('MuJoCo typed actuator-force publication requires an evaluation boundary')
        state = self.snapshot()
        if (state.control_step != boundary.control_step
                or float(state.simulation_time) != sample_clock.simulation_time_s
                or sample_clock.clock_domain != 'evaluation_boundary'):
            raise ValueError('MuJoCo typed force readback boundary changed during state publication')

        values = []
        unavailable = []
        for item in requirements:
            if (item.entity_id, item.subject_id, item.unit) != (
                'panda-main', self._source.open_actuators[0], 'N',
            ):
                unavailable.append(UnavailableStateValue(
                    'unavailable-state-value-v1', item.field_name, item.subject_kind,
                    item.entity_id, item.subject_id, item.sample_domain,
                    'MuJoCo bounded R1 force route only maps panda-main/actuator8 in N',
                ))
                continue
            measurement = self._completed_force_measurement
            if (measurement is None or self._completed_actuator_force is None
                    or self._completed_actuator_ctrl is None):
                unavailable.append(UnavailableStateValue(
                    'unavailable-state-value-v1', item.field_name, item.subject_kind,
                    item.entity_id, item.subject_id, item.sample_domain,
                    'MuJoCo completed actuator-force cache is unavailable',
                ))
                continue

            physics_dt = float(self._artifact.timebase.physics_dt)
            native_ratio = float(state.simulation_time) / physics_dt
            expected_native_step = int(round(native_ratio))
            if (not math.isfinite(native_ratio)
                    or abs(native_ratio - expected_native_step) > 1.0e-7):
                raise ValueError('MuJoCo force evaluation boundary is not on the native-step clock')
            expected_control_native = int(state.control_step) * self._artifact.timebase.control_substeps
            if expected_native_step != expected_control_native:
                raise ValueError('MuJoCo force native index differs from the evaluation boundary')
            expected_phase = 'reset_forward' if expected_native_step == 0 else 'native_step_pre_integration'
            expected_sample_time = (
                0.0 if expected_native_step == 0
                else float(expected_native_step - 1) * physics_dt
            )
            if (
                measurement.episode_id != self._episode_id
                or measurement.reset_sample_id != self._reset_sample_id
                or measurement.actuator_id != item.subject_id
                or measurement.sample_sequence != expected_native_step + 1
                or measurement.native_step_index != expected_native_step
                or measurement.state_revision != expected_native_step
                or measurement.configuration_revision != self._force_configuration_revision
                or measurement.phase != expected_phase
                or measurement.native_sample_time_s != expected_sample_time
            ):
                raise ValueError('MuJoCo completed force cache is stale or belongs to another reset/boundary')

            actuator_index = self._open_actuators[0]
            cached_control = float(self._completed_actuator_ctrl[actuator_index])
            current_control = float(self._data.ctrl[actuator_index])
            if not math.isfinite(current_control) or cached_control != current_control:
                raise ValueError('MuJoCo completed force cache does not match the current actuator input')
            force = measurement.signed_force_N
            valid = measurement.valid and force is not None and math.isfinite(float(force))
            if valid and (not math.isfinite(cached_control) or measurement.force_unit != 'N'):
                valid = False
            invalid_reason = measurement.invalid_reason
            if not valid and not invalid_reason:
                invalid_reason = 'MuJoCo required actuator-force cache is non-finite or has an unsupported unit'
            value = TypedActuatorForceStateValue(
                'typed-actuator-force-state-v1', item.entity_id, item.subject_id,
                measurement.force_unit, float(force) if valid else None,
                cached_control if valid else None, valid, invalid_reason,
                measurement.source_generation, measurement.sample_sequence,
                measurement.state_revision, measurement.configuration_revision,
                self._source.source_closure_digest, self._provider_materialization_id,
                measurement.phase, measurement.native_step_index, physics_dt,
                expected_sample_time, str(self._episode_id), str(self._reset_sample_id),
                boundary.boundary_id, int(state.control_step), float(state.simulation_time),
            )
            values.append(value)
            self._last_typed_force_publication = value
        return tuple(values), tuple(unavailable)

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

    def apply_control(self, target):
        from .control import validate_target
        from ...controllers.canonical.contracts import AppliedCanonicalControl
        validate_target(self, target)
        clipped = False
        realized = {}
        for name, requested in target.arm_servo_position.items():
            index = self._target_actuators[name]
            low, high = self._model.actuator_ctrlrange[index]
            value = float(np.clip(requested, low, high)) if self._model.actuator_ctrllimited[index] else requested
            self._data.ctrl[index] = value
            realized[name] = value
            clipped = clipped or value != requested
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
            'named_position_servo_plus_affine_tendon_opening_force_limit_ZOH')

    def step(self):
        self._require_reset()
        for _ in range(self._artifact.timebase.control_substeps):
            self._mj.mj_step(self._model, self._data)
            self._native_steps += 1
            self._cache_completed_actuator_force()
        self._mj.mj_forward(self._model, self._data)
        self._control_step += 1
        self._state_revision += 1
        return self.snapshot()

    def _step_physics_once(self):
        self._require_reset()
        self._mj.mj_step(self._model, self._data)
        self._native_steps += 1
        self._cache_completed_actuator_force()
        self._mj.mj_forward(self._model, self._data)

    def close(self):
        if not self._closed:
            self._data, self._model = None, None
            self._closed = True
