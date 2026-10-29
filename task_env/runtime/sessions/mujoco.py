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


def _lower_libero_mjcf_assets(receipt):
    """Give every receipt-bound asset a unique flat MuJoCo VFS name.

    MuJoCo's in-memory VFS rejects distinct source files that share a
    basename.  The source receipt remains byte-for-byte authoritative; only
    this compiler input copy receives deterministic aliases.
    """
    root = ET.fromstring(receipt.importer_xml)
    compiler = root.find('compiler')
    if compiler is not None and any(compiler.get(key) for key in ('meshdir', 'texturedir')):
        raise ValueError('LIBERO receipt MJCF must use explicit source asset paths without compiler directories')
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
            raise ValueError('LIBERO mixed source does not admit nested MJCF includes')
        if (not raw_path or raw_path.startswith('/') or '\\' in raw_path
                or any(part in {'', '.', '..'} for part in raw_path.split('/'))):
            raise ValueError(f'LIBERO source asset path is not canonical: {raw_path!r}')
        if raw_path not in payloads:
            raise ValueError(f'LIBERO source asset is missing from its immutable receipt: {raw_path!r}')
        referenced.add(raw_path)
        alias = aliases.get(raw_path)
        if alias is None:
            suffix = PurePosixPath(raw_path).suffix
            alias = f'gch_{hashlib.sha256(raw_path.encode("utf-8")).hexdigest()}{suffix}'
            if alias in alias_payloads:
                raise ValueError('LIBERO deterministic MuJoCo asset alias collision')
            aliases[raw_path] = alias
            alias_payloads[alias] = payloads[raw_path]
        node.set('file', alias)
    if referenced != set(payloads):
        raise ValueError(
            'LIBERO source asset references differ from the immutable receipt: '
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


class _MuJoCoSession(_SessionValues):
    def __init__(self, artifact, source, *, materialization_profile=None):
        self._initialize_values(artifact, source, 'mujoco')
        self._materialization_profile = materialization_profile
        if source.fixed_attachment_plan is not None:
            try:
                self._initialize_fixed_attachment(artifact, source)
            except Exception:
                # The existing adapter owns every partially-created native value.
                self.close()
                raise
            return
        if materialization_profile is not None:
            if materialization_profile != 'libero-spatial-bowl-to-plate-mixed-v1':
                raise ValueError('unsupported MuJoCo RuntimeSession materialization profile')
            try:
                self._initialize_libero_mixed(artifact, source)
            except BaseException as error:
                try:
                    self.close()
                except BaseException as cleanup_error:
                    error.add_note(
                        'LIBERO RuntimeSession constructor cleanup also failed: '
                        f'{type(cleanup_error).__name__}: {cleanup_error}'
                    )
                raise
            return
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
        self._fixed_forward_calls = 0
        self._fixed_attachment_close_receipt = None
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

    def _initialize_libero_mixed(self, artifact, source):
        """Compile one receipt-bound LIBERO model and preflight every named slot."""
        from .provenance import provider_build_identity
        from ...assembly.assets import _source_closure_manifest

        receipt = source.execution_source_receipt
        if receipt is None:
            raise ValueError('LIBERO materialization requires its immutable source receipt')
        receipt.validate_snapshot()
        import mujoco

        self._mj = mujoco
        self._runtime_identity = self._fixed_runtime_identity(mujoco)
        self._provider_build_identity = provider_build_identity('mujoco')
        compile_xml, assets, asset_aliases = _lower_libero_mjcf_assets(receipt)
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
        if (int(self._model.nq), int(self._model.nv), int(self._model.na), int(self._model.nu)) != (48, 43, 0, 9):
            raise ValueError('compiled LIBERO nq/nv/na/nu differs from the fixed source layout')
        if float(self._model.opt.timestep) != artifact.timebase.physics_dt:
            raise ValueError('compiled LIBERO MuJoCo timestep differs from TaskArtifact')
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
        expected_dims = {
            **{f'joint{i}': (i - 1, i - 1) for i in range(1, 8)},
            'finger_joint1': (7, 7), 'finger_joint2': (8, 8),
            'wooden_cabinet_1.top_level': (44, 39),
            'wooden_cabinet_1.middle_level': (45, 40),
            'wooden_cabinet_1.bottom_level': (46, 41),
            'flat_stove_1.button': (47, 42),
        }
        for semantic, (qpos, dof) in expected_dims.items():
            if self._joint_addresses.get(semantic) != (qpos, dof):
                raise ValueError(f'compiled scalar joint order differs from .pruned_init layout: {semantic}')
        expected_free_order = (
            'akita_black_bowl_1', 'akita_black_bowl_2', 'cookies_1',
            'glazed_rim_porcelain_ramekin_1', 'plate_1',
        )
        for offset, semantic in enumerate(expected_free_order):
            if self._free_addresses.get(semantic) != (9 + 7 * offset, 9 + 6 * offset):
                raise ValueError(f'compiled free-joint order differs from .pruned_init layout: {semantic}')
        for semantic, aid in self._torque_actuators.items():
            joint_name = f'robot0_{semantic}'
            joint_id = int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_JOINT, joint_name))
            if (joint_id < 0
                    or int(self._model.actuator_trntype[aid]) != int(self._mj.mjtTrn.mjTRN_JOINT)
                    or int(self._model.actuator_trnid[aid, 0]) != joint_id
                    or int(self._model.jnt_type[joint_id]) != int(self._mj.mjtJoint.mjJNT_HINGE)):
                raise ValueError(f'compiled torque actuator does not drive the named hinge: {semantic}')
            low, high = (float(value) for value in self._model.actuator_ctrlrange[aid])
            expected_range = (-80.0, 80.0) if semantic in {f'joint{i}' for i in range(1, 6)} else (-12.0, 12.0)
            if not bool(self._model.actuator_ctrllimited[aid]) or (low, high) != expected_range:
                raise ValueError(f'compiled torque actuator range differs from source: {semantic}')
        expected_position_ranges = {'finger_joint1': (0.0, 0.04), 'finger_joint2': (-0.04, 0.0)}
        for semantic, aid in self._position_actuators.items():
            joint_name = 'gripper0_' + semantic
            joint_id = int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_JOINT, joint_name))
            low, high = (float(value) for value in self._model.actuator_ctrlrange[aid])
            if (joint_id < 0
                    or int(self._model.actuator_trntype[aid]) != int(self._mj.mjtTrn.mjTRN_JOINT)
                    or int(self._model.actuator_trnid[aid, 0]) != joint_id
                    or not bool(self._model.actuator_ctrllimited[aid])
                    or (low, high) != expected_position_ranges[semantic]):
                raise ValueError(f'compiled finger position actuator differs from source contract: {semantic}')
        self._contact_geom_ids = {}
        for semantic, names in source.contact_geom_groups.items():
            ids = tuple(int(self._mj.mj_name2id(self._model, self._mj.mjtObj.mjOBJ_GEOM, name)) for name in names)
            if not ids or any(index < 0 for index in ids):
                raise ValueError(f'compiled geom group is incomplete: {semantic}')
            self._contact_geom_ids[semantic] = frozenset(ids)
        named_torque_actuators = {
            semantic: {
                'name': source.torque_actuators[semantic], 'id': aid,
                'transmission_type': 'joint', 'transmission_target': f'robot0_{semantic}',
                'control_limited': bool(self._model.actuator_ctrllimited[aid]),
                'control_range': [float(value) for value in self._model.actuator_ctrlrange[aid]],
            }
            for semantic, aid in self._torque_actuators.items()
        }
        named_position_actuators = {
            semantic: {
                'name': source.position_actuators[semantic], 'id': aid,
                'transmission_type': 'joint', 'transmission_target': f'gripper0_{semantic}',
                'control_limited': bool(self._model.actuator_ctrllimited[aid]),
                'control_range': [float(value) for value in self._model.actuator_ctrlrange[aid]],
            }
            for semantic, aid in self._position_actuators.items()
        }
        self._current_ctrl = self._data.ctrl.copy()
        self._compiled_layout_receipt = {
            'schema_version': 'r07c-d01-compiled-model-layout-v1',
            'dimensions': {'nq': int(self._model.nq), 'nv': int(self._model.nv),
                           'na': int(self._model.na), 'nu': int(self._model.nu),
                           'njnt': int(self._model.njnt), 'nbody': int(self._model.nbody),
                           'nsite': int(self._model.nsite), 'ngeom': int(self._model.ngeom)},
            'source_closure_digest': source.source_closure_digest,
            'source_id': source.scene_source.source_id,
            'source_files': list(_source_closure_manifest(receipt.closure_files)),
            'compiler_asset_aliases': asset_aliases,
            'named_joint_addresses': {key: list(value) for key, value in self._joint_addresses.items()},
            'named_free_joint_addresses': {key: list(value) for key, value in self._free_addresses.items()},
            'named_body_ids': dict(self._bodies), 'named_frame_ids': dict(self._frames),
            'named_torque_actuator_ids': dict(self._torque_actuators),
            'named_position_actuator_ids': dict(self._position_actuators),
            'named_torque_actuator_layout': named_torque_actuators,
            'named_position_actuator_layout': named_position_actuators,
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

    @property
    def compiled_layout_receipt(self):
        if self._materialization_profile != 'libero-spatial-bowl-to-plate-mixed-v1':
            raise RuntimeError('compiled LIBERO layout is unavailable for this session profile')
        return json.loads(json.dumps(self._compiled_layout_receipt, sort_keys=True))

    @property
    def runtime_identity(self):
        if self._materialization_profile != 'libero-spatial-bowl-to-plate-mixed-v1':
            raise RuntimeError('pinned MuJoCo runtime identity is unavailable for this profile')
        return json.loads(json.dumps({
            'runtime': self._runtime_identity,
            'provider_build': self._provider_build_identity,
        }, sort_keys=True))

    @property
    def runtime_progress_receipt(self):
        if self._materialization_profile != 'libero-spatial-bowl-to-plate-mixed-v1':
            raise RuntimeError('mixed runtime progress is unavailable for this session profile')
        return {
            'schema_version': 'r07c-d01-runtime-progress-v1',
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
        }

    @property
    def close_receipt(self):
        if self._materialization_profile != 'libero-spatial-bowl-to-plate-mixed-v1':
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

        self._mj = mujoco
        runtime_identity = self._fixed_runtime_identity(mujoco)
        lowered = lower_fixed_attachment_sources(
            parent_source=source.scene_source,
            source_by_entity=source.fixed_attachment_sources,
            scene=source.scene_definition,
            plan=source.fixed_attachment_plan,
            assembly=source.fixed_attachment_assembly,
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

    def apply_fixed_attachment_diagnostic_control(
        self, receipt_identity_sha256: str, *, arm_joint1_target_rad: float,
        hand_opening_m: float,
    ):
        """Write the one receipt-owned Arm slot and Hand actuator at a Core boundary."""
        self._require_reset()
        receipt = self.fixed_attachment_receipt
        if receipt_identity_sha256 != receipt["receipt_identity_sha256"]:
            raise ValueError("fixed Attachment diagnostic command is not bound to this model receipt")
        if not math.isfinite(arm_joint1_target_rad) or not math.isfinite(hand_opening_m):
            raise ValueError("fixed Attachment diagnostic commands must be finite")
        if not -2.8973 <= arm_joint1_target_rad <= 2.8973 or not 0.0 <= hand_opening_m <= 0.08:
            raise ValueError("fixed Attachment diagnostic command exceeds its source joint/opening range")
        plan = self._source.fixed_attachment_plan
        arm_slot = receipt["native_actuator_mappings"][f"{plan.parent_entity_id}/actuator1"]["ctrl_slot"]
        hand_slot = receipt["native_actuator_mappings"][f"{plan.child_entity_id}/actuator8"]["ctrl_slot"]
        arm_low, arm_high = self._model.actuator_ctrlrange[arm_slot]
        hand_low, hand_high = self._model.actuator_ctrlrange[hand_slot]
        if (not bool(self._model.actuator_ctrllimited[arm_slot])
                or not bool(self._model.actuator_ctrllimited[hand_slot])
                or (float(arm_low), float(arm_high)) != (-2.8973, 2.8973)
                or (float(hand_low), float(hand_high)) != (0.0, 255.0)):
            raise ValueError("fixed Attachment source actuator ranges differ from the admitted model receipt")
        self._data.ctrl[arm_slot] = arm_joint1_target_rad
        self._data.ctrl[hand_slot] = 255.0 * hand_opening_m / 0.08
        self._current_ctrl = self._data.ctrl.copy()
        return {
            "provider_materialization_id": self._provider_materialization_id,
            "episode_id": self._episode_id,
            "reset_sample_id": self._reset_sample_id,
            "control_step": self._control_step,
            "arm_joint1_target_rad": float(arm_joint1_target_rad),
            "hand_opening_command_m": float(hand_opening_m),
            "arm_ctrl": float(self._data.ctrl[arm_slot]),
            "hand_ctrl": float(self._data.ctrl[hand_slot]),
        }

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
        if plan.fixed_attachment_plan_identity_sha256 is not None:
            return self._admit_attached_leaf_control_plan(plan)
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

    def _admit_attached_leaf_control_plan(self, plan):
        """Resolve canonical leaf resources only through the compiled Attachment receipt."""
        from ...controllers.canonical.leaf_profiles import (
            PANDA_HAND_EQUALITY_IDENTITY, PANDA_HAND_TENDON_IDENTITY,
        )
        from ...runtime.sessions.leaf_control import (
            LeafMaterializationReceiptV1, LeafNativeActuatorMappingV1,
            LeafNativeFrameMappingV1, LeafNativeJointMappingV1,
            LeafNativeTendonMappingV1,
        )
        source_plan = self._source.fixed_attachment_plan
        attached = self.fixed_attachment_receipt
        if (source_plan is None
                or source_plan.identity_hash != plan.fixed_attachment_plan_identity_sha256
                or attached.get('attachment_plan_sha256') != source_plan.identity_hash
                or attached.get('scene_identity_sha256') != plan.scene_identity_sha256
                or attached.get('source_closure_sha256') != plan.source_closure_sha256
                or attached.get('assembly_identity_sha256') != plan.root_logical_content_sha256
                or attached.get('provider_materialization_id') != self._provider_materialization_id):
            raise ValueError('fixed Attachment model receipt does not attest the selected leaf plan/source/runtime')
        if attached.get('provider') != 'mujoco' or attached.get('backend') != 'cpu':
            raise ValueError('attached leaf plan requires the same MuJoCo CPU Attachment model receipt')
        model, mj = self._model, self._mj
        dimensions = attached.get('dimensions', {})
        if ((int(model.nq), int(model.nv), int(model.nu), int(model.njnt), int(model.neq), int(model.ntendon))
                != tuple(dimensions.get(key) for key in ('nq', 'nv', 'nu', 'njnt', 'neq', 'ntendon'))
                or (int(model.nq), int(model.nv), int(model.nu), int(model.njnt), int(model.neq), int(model.ntendon))
                != (9, 9, 8, 9, 1, 1)):
            raise ValueError('attached leaf native dimensions differ from the fixed model receipt')
        if any(int(value) == int(mj.mjtJoint.mjJNT_FREE) for value in model.jnt_type):
            raise ValueError('fixed Attachment model unexpectedly contains a free root joint')

        receipt_joint_maps = attached.get('native_joint_mappings', {})
        receipt_actuator_maps = attached.get('native_actuator_mappings', {})
        receipt_body_maps = attached.get('native_body_mappings', {})
        receipt_tendon_maps = attached.get('native_tendon_mappings', {})
        # The fixed Attachment receipt is keyed by its Entity-scoped source
        # plan (panda-hand/split); the leaf profile has its own logical
        # identity (hand.xml/tendon/split). Resolve through the former and
        # publish the latter only after the native mapping is verified.
        hand_tendon_source_key = f'{source_plan.child_entity_id}/split'
        joint_maps, actuator_maps, frame_maps = [], [], []
        native_joint_ids = {}
        native_actuator_ids = set()
        for entry in plan.leaves:
            binding = entry.binding
            for ref, limits in zip(binding.joint_order, binding.joint_position_limits, strict=True):
                canonical = f'{ref.entity_id}/{ref.joint_id}'
                native = receipt_joint_maps.get(canonical)
                if native is None or source_plan.native_joint_names.get(canonical) != native.get('native_name'):
                    raise ValueError(f'Attachment receipt omits the exact canonical Joint mapping {canonical}')
                name = native['native_name']
                joint_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, name))
                expected_type = mj.mjtJoint.mjJNT_HINGE if binding.joint_position_unit == 'radian' else mj.mjtJoint.mjJNT_SLIDE
                if (joint_id < 0 or joint_id != native['joint_id']
                        or int(model.jnt_type[joint_id]) != int(expected_type)
                        or not bool(model.jnt_limited[joint_id])
                        or not np.allclose(model.jnt_range[joint_id], limits, rtol=0.0, atol=1e-12)
                        or int(model.jnt_qposadr[joint_id]) != native['qpos_address']
                        or int(model.jnt_dofadr[joint_id]) != native['dof_address']):
                    raise ValueError(f'Attachment native Joint mapping differs from the leaf contract: {canonical}')
                native_joint_ids[name] = joint_id
                joint_maps.append(LeafNativeJointMappingV1(
                    'leaf-native-joint-mapping-v1', ref, name, joint_id,
                    int(model.jnt_qposadr[joint_id]), int(model.jnt_dofadr[joint_id]),
                    binding.joint_position_unit,
                ))
            if binding.profile_kind == 'arm_position':
                pairs = binding.joint_actuator_bindings
            else:
                pairs = ()
            if pairs:
                for pair in pairs:
                    actuator_ref = pair.actuator
                    canonical = f'{actuator_ref.entity_id}/{actuator_ref.actuator_id}'
                    native = receipt_actuator_maps.get(canonical)
                    if native is None or source_plan.native_actuator_names.get(canonical) != native.get('native_name'):
                        raise ValueError(f'Attachment receipt omits the exact canonical Actuator mapping {canonical}')
                    actuator_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, native['native_name']))
                    target_id = int(model.actuator_trnid[actuator_id, 0]) if actuator_id >= 0 else -1
                    target_name = mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, target_id) if target_id >= 0 else None
                    if (actuator_id != native['actuator_id'] or actuator_id != native['ctrl_slot']
                            or int(model.actuator_trntype[actuator_id]) != int(mj.mjtTrn.mjTRN_JOINT)
                            or target_name != source_plan.native_joint_names[f'{pair.joint.entity_id}/{pair.joint.joint_id}']):
                        raise ValueError(f'Attachment native Arm transmission differs from its leaf mapping: {canonical}')
                    limits = tuple(float(item) for item in model.actuator_ctrlrange[actuator_id])
                    actuator_maps.append(LeafNativeActuatorMappingV1(
                        'leaf-native-actuator-mapping-v1', actuator_ref, native['native_name'],
                        actuator_id, int(native['ctrl_slot']), limits, 'radian', 'joint', str(target_name),
                    ))
                    native_actuator_ids.add(actuator_id)
            else:
                actuator_ref = binding.actuator_order[0]
                canonical = f'{actuator_ref.entity_id}/{actuator_ref.actuator_id}'
                native = receipt_actuator_maps.get(canonical)
                tendon = receipt_tendon_maps.get(hand_tendon_source_key)
                if (native is None or tendon is None
                        or source_plan.native_actuator_names.get(canonical) != native.get('native_name')
                        or source_plan.native_tendon_names.get(hand_tendon_source_key) != tendon.get('native_name')):
                    raise ValueError('Attachment receipt omits the canonical Hand actuator/tendon mapping')
                actuator_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, native['native_name']))
                target_id = int(model.actuator_trnid[actuator_id, 0]) if actuator_id >= 0 else -1
                target_name = mj.mj_id2name(model, mj.mjtObj.mjOBJ_TENDON, target_id) if target_id >= 0 else None
                limits = tuple(float(item) for item in model.actuator_ctrlrange[actuator_id]) if actuator_id >= 0 else ()
                if (actuator_id != native['actuator_id'] or actuator_id != native['ctrl_slot']
                        or int(model.actuator_trntype[actuator_id]) != int(mj.mjtTrn.mjTRN_TENDON)
                        or target_name != tendon['native_name'] or limits != tuple(binding.native_ctrlrange)
                        or not bool(model.actuator_ctrllimited[actuator_id])):
                    raise ValueError('Attachment Hand actuator differs from its receipt tendon/ctrl contract')
                actuator_maps.append(LeafNativeActuatorMappingV1(
                    'leaf-native-actuator-mapping-v1', actuator_ref, native['native_name'],
                    actuator_id, int(native['ctrl_slot']), limits, 'native_ctrl', 'tendon', str(target_name),
                ))
                native_actuator_ids.add(actuator_id)
                tendon_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_TENDON, tendon['native_name']))
                if tendon_id < 0 or int(model.tendon_num[tendon_id]) != 2:
                    raise ValueError('Attachment Hand tendon must contain exactly two source finger wraps')
                adr = int(model.tendon_adr[tendon_id])
                wraps = tuple({
                    'wrap_type': int(model.wrap_type[index]),
                    'joint_native_name': mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT,
                                                       int(model.wrap_objid[index])),
                    'coefficient': float(model.wrap_prm[index]),
                } for index in range(adr, adr + 2))
                expected_names = tuple(source_plan.native_joint_names[f'panda-hand/{name}']
                                       for name in ('finger_joint1', 'finger_joint2'))
                if tuple(item['joint_native_name'] for item in wraps) != expected_names or tuple(
                        item['coefficient'] for item in wraps) != (0.5, 0.5):
                    raise ValueError('Attachment Hand tendon wraps differ from receipt child-prefix mappings')
                matching = [eq for eq in range(int(model.neq)) if
                            int(model.eq_type[eq]) == int(mj.mjtEq.mjEQ_JOINT)
                            and {int(model.eq_obj1id[eq]), int(model.eq_obj2id[eq])}
                            == {native_joint_ids[name] for name in expected_names}]
                if len(matching) != 1:
                    raise ValueError('Attachment Hand requires exactly the receipt-bound finger equality')
            ref = binding.tcp_frame
            canonical = f'{ref.entity_id}/{ref.frame_id}'
            native = receipt_body_maps.get(canonical)
            if native is None or source_plan.native_body_names.get(canonical) != native.get('native_name'):
                raise ValueError(f'Attachment receipt omits the canonical leaf TCP Body mapping {canonical}')
            body_id = int(mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, native['native_name']))
            if body_id <= 0 or body_id != native['body_id']:
                raise ValueError(f'Attachment native TCP Body differs from its receipt: {canonical}')
            frame_maps.append(LeafNativeFrameMappingV1(
                'leaf-native-frame-mapping-v1', ref, native['native_name'], body_id,
            ))
        if native_actuator_ids != set(range(int(model.nu))):
            raise ValueError('attached leaf writers must own every native ctrl slot exactly once')
        fixed_receipt_hash = attached.get('receipt_identity_sha256')
        receipt = LeafMaterializationReceiptV1(
            'leaf-materialization-receipt-v1', 'provider_materialization',
            plan.scene_identity_sha256, plan.source_closure_sha256, plan.identity_sha256,
            'mujoco', plan.provider_version, plan.provider_build_sha256, 'cpu',
            self._provider_materialization_id, 'leaf-' + plan.identity_sha256[:20],
            int(model.nq), int(model.nv), int(model.nu), int(model.njnt), int(model.nbody),
            int(model.neq), int(model.ntendon), tuple(joint_maps), tuple(actuator_maps),
            tuple(frame_maps), (LeafNativeTendonMappingV1(
                'leaf-native-tendon-mapping-v1', PANDA_HAND_TENDON_IDENTITY,
                receipt_tendon_maps[hand_tendon_source_key]['native_name'],
            ),), (PANDA_HAND_EQUALITY_IDENTITY,), fixed_receipt_hash,
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
        allowed = (self._mj.mjtJoint.mjJNT_FREE,) if free else (self._mj.mjtJoint.mjJNT_HINGE, self._mj.mjtJoint.mjJNT_SLIDE)
        if self._model.jnt_type[joint] not in allowed:
            raise ValueError('unsupported source joint representation')
        return int(self._model.jnt_qposadr[joint]), int(self._model.jnt_dofadr[joint])

    def reset(self, sample):
        if (self._materialization_profile == 'libero-spatial-bowl-to-plate-mixed-v1'
                and getattr(sample, 'schema_version', None) == 'reset-sample-v1'):
            return self._reset_libero_mixed(sample)
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
        if self._source.fixed_attachment_plan is not None:
            self._data.ctrl[self._open_actuators[0]] = (
                255.0 * self._source.fixed_attachment_plan.reset_hand_opening_m / 0.08
            )
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
        if self._source.fixed_attachment_plan is not None:
            self._fixed_forward_calls += 1
        realized = self._realized(sample)
        self._cache_completed_actuator_force()
        return realized

    def _reset_libero_mixed(self, sample):
        """Apply the exact v1 time, qvel, free-root, and fixture reset in one pass."""
        from ...artifacts import ResetReadbackV1, ResetSampleV1

        if type(sample) is not ResetSampleV1:
            raise TypeError('LIBERO mixed materialization requires ResetSampleV1')
        self._validate_sample(sample)
        if self._mixed_fault is not None:
            raise RuntimeError('LIBERO MuJoCo session is fault-latched')
        self._begin_reset()
        model, data, mj = self._model, self._data, self._mj
        # Every name/value/range is checked before the first mutable native write.
        if (set(sample.joint_position) != set(self._joint_addresses)
                or set(sample.joint_velocity) != set(self._joint_addresses)
                or set(sample.poses_world) != set(self._free_addresses)
                or set(sample.free_joint_velocity) != set(self._free_addresses)
                or set(sample.fixture_pose_world) != set(self._source.fixture_bodies)):
            raise ValueError('LIBERO ResetSampleV1 does not cover the compiled source layout')
        for semantic, value in sample.joint_position.items():
            qpos, _ = self._joint_addresses[semantic]
            native_name = self._source.joints[semantic]
            jid = int(model.joint(native_name).id)
            if bool(model.jnt_limited[jid]):
                low, high = (float(item) for item in model.jnt_range[jid])
                if not low <= float(value) <= high:
                    raise ValueError(f'LIBERO reset position exceeds source joint limits: {semantic}')
            if not math.isfinite(float(sample.joint_velocity[semantic])):
                raise ValueError(f'LIBERO reset velocity is non-finite: {semantic}')
        for semantic, pose_value in sample.fixture_pose_world.items():
            body_id = self._bodies[semantic]
            if int(model.body_parentid[body_id]) != 0:
                raise ValueError(f'LIBERO fixture root is not a world child: {semantic}')
            pose_value.validate()
        for semantic, pose_value in sample.poses_world.items():
            pose_value.validate()
            velocity = sample.free_joint_velocity[semantic]
            if len(velocity) != 6 or any(not math.isfinite(float(item)) for item in velocity):
                raise ValueError(f'LIBERO free-body velocity is invalid: {semantic}')
        for semantic, value in sample.joint_position.items():
            if semantic not in {'finger_joint1', 'finger_joint2'}:
                continue
            aid = self._position_actuators[semantic]
            low, high = (float(item) for item in model.actuator_ctrlrange[aid])
            if not low <= float(value) <= high:
                raise ValueError(f'LIBERO initial finger target exceeds source actuator range: {semantic}')

        try:
            mj.mj_resetData(model, data)
            self._native_steps = 0
            self._reset_count += 1
            self._preprocess_calls = 0
            self._forward_calls = 0
            self._reset_time_origin = float(sample.simulation_time_s)
            # LIBERO's normal route runs its non-integrating mj_step1
            # preprocessing before the placement sampler is applied. The
            # selected .pruned_init row is restored after these placements.
            mj.mj_step1(model, data)
            self._preprocess_calls += 1
            for semantic, fixture_pose in sample.fixture_pose_world.items():
                body_id = self._bodies[semantic]
                model.body_pos[body_id, :] = fixture_pose.position
                model.body_quat[body_id, :] = fixture_pose.quaternion_wxyz
            for semantic, sampled_pose in sample.sampled_poses_world.items():
                qpos, dof = self._free_addresses[semantic]
                data.qpos[qpos:qpos + 7] = (*sampled_pose.position, *sampled_pose.quaternion_wxyz)
                data.qvel[dof:dof + 6] = 0.0
            # Restore the complete named .pruned_init state after ordinary
            # BDDL placements; fixture root transforms intentionally remain
            # the current sampler realization because the row has no roots.
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
                raise ValueError('LIBERO reset readback does not match the frozen row receipt')
            for name, expected in sample.fixture_pose_world.items():
                actual = receipt.fixture_pose_world[name]
                if (not np.allclose(actual.position, expected.position, rtol=0.0, atol=1e-12)
                        or not np.allclose(actual.quaternion_wxyz, expected.quaternion_wxyz,
                                           rtol=0.0, atol=1e-12)):
                    raise ValueError(f'LIBERO fixture readback differs from sampled root pose: {name}')
            self._last_reset_readback_v1 = receipt
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
        if self._materialization_profile == 'libero-spatial-bowl-to-plate-mixed-v1':
            elapsed = float(data.time) - self._reset_time_origin
            expected = self._native_steps * self._artifact.timebase.physics_dt
            bound = (self._native_steps + 2) * max(
                math.ulp(float(data.time)), math.ulp(self._reset_time_origin),
                math.ulp(expected), math.ulp(self._artifact.timebase.physics_dt),
            )
            if not math.isfinite(elapsed) or abs(elapsed - expected) > bound:
                raise ValueError('LIBERO native/reset-origin clock or integration count mismatch')
            if self._native_steps != self._control_step * self._artifact.timebase.control_substeps:
                raise ValueError('LIBERO native/canonical step-count mismatch')
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
        if self._materialization_profile == 'libero-spatial-bowl-to-plate-mixed-v1':
            return self.apply_mixed_actuator_target(target)
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

    def bind_mixed_controller(self, controller_identity):
        if self._materialization_profile != 'libero-spatial-bowl-to-plate-mixed-v1':
            raise RuntimeError('mixed Controller binding is restricted to the LIBERO profile')
        if self._reset_done or hasattr(self, '_mixed_controller_identity'):
            raise RuntimeError('mixed Controller can be bound exactly once before reset')
        if type(controller_identity) is not str or not controller_identity.strip():
            raise ValueError('mixed Controller identity must be a nonempty stable value')
        if (controller_identity != self._source.mixed_controller_identity
                or self._source.mixed_controller_profile_id != 'libero-spatial-bowl-to-plate-joint-space-pd-v1'):
            raise ValueError('mixed Controller identity differs from the source-bound admission')
        self._mixed_controller_identity = controller_identity

    def apply_mixed_actuator_target(self, target):
        from ...controllers.canonical.contracts import AppliedMixedActuatorV1, MixedActuatorTargetV1
        self._require_reset()
        if self._mixed_fault is not None:
            raise RuntimeError('LIBERO MuJoCo session is fault-latched')
        if type(target) is not MixedActuatorTargetV1:
            raise TypeError('LIBERO RuntimeSession requires MixedActuatorTargetV1')
        target.validate()
        state = self.snapshot()
        if (not hasattr(self, '_mixed_controller_identity')
                or target.controller_identity != self._mixed_controller_identity
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
        torques, fingers = dict(target.joint_torque_Nm), dict(target.finger_position_m)
        if set(torques) != set(self._torque_actuators) or set(fingers) != set(self._position_actuators):
            raise ValueError('mixed actuator target does not cover the exact named source slots')
        values = {}
        for semantic, aid in self._torque_actuators.items():
            value = float(torques[semantic])
            low, high = (float(item) for item in self._model.actuator_ctrlrange[aid])
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'mixed actuator torque is outside its named source range: {semantic}')
            values[aid] = value
        for semantic, aid in self._position_actuators.items():
            value = float(fingers[semantic])
            low, high = (float(item) for item in self._model.actuator_ctrlrange[aid])
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'mixed finger position is outside its signed source range: {semantic}')
            values[aid] = value
        try:
            for aid, value in values.items():
                self._data.ctrl[aid] = value
            self._current_ctrl = self._data.ctrl.copy()
        except BaseException as error:
            self._mixed_fault = {'phase': 'partial_control_apply', 'error': f'{type(error).__name__}: {error}'}
            raise
        self._mixed_consumed_boundaries.add(boundary)
        self._mixed_pending_target = target
        result = AppliedMixedActuatorV1(
            'applied-mixed-actuator-v1', target.identity_hash, 'mujoco',
            torques, fingers, False,
            'named_joint_torque_and_signed_finger_position_control_zoh_20hz',
        )
        result.validate()
        return result

    def read_contact_summary_v2(self, requested_pairs):
        from ...environment.types import ContactSummaryV2
        self._require_reset()
        if self._materialization_profile != 'libero-spatial-bowl-to-plate-mixed-v1':
            raise RuntimeError('geom-group contact is limited to the admitted LIBERO profile')
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

    def step(self):
        self._require_reset()
        if self._materialization_profile == 'libero-spatial-bowl-to-plate-mixed-v1':
            if self._mixed_fault is not None:
                raise RuntimeError('LIBERO MuJoCo session is fault-latched')
            if self._mixed_pending_target is None:
                raise RuntimeError('LIBERO outer step requires exactly one fresh mixed target')
            try:
                for _ in range(self._artifact.timebase.control_substeps):
                    self._mj.mj_step(self._model, self._data)
                    self._native_steps += 1
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
        for _ in range(self._artifact.timebase.control_substeps):
            self._mj.mj_step(self._model, self._data)
            self._native_steps += 1
            self._cache_completed_actuator_force()
        self._mj.mj_forward(self._model, self._data)
        if self._source.fixed_attachment_plan is not None:
            self._fixed_forward_calls += 1
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
            if self._materialization_profile == 'libero-spatial-bowl-to-plate-mixed-v1':
                self._last_close_receipt = {
                    'schema_version': 'r07c-d01-runtime-close-v1',
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
