"""Public MuJoCo Renderer translation; native models/IDs remain adapter-private."""
import math
import os
import threading
import uuid
import xml.etree.ElementTree as ET
import numpy as np
from .api import CameraSessionValues
from ...observations.canonical_camera.images import (
    CanonicalEntityLabelV1,
    CanonicalEntityLabelMapV1,
    CanonicalEntityInstanceSegmentationV1,
)
from .source import (
    DynamicCameraRenderSourceV1,
    RenderStateProjectionV1,
    RenderStateSyncReceiptV1, RenderStateSyncReceiptV2,
    RenderVisualInstanceBindingV1,
    project_render_state_v1,
)


D03_FRAME_POSITION_ATOL_M = 5.0e-4
D03_FRAME_QUATERNION_SIGN_INVARIANT_L2_ATOL = 1.0e-3


def _resolve_canonical_entity_geometry_labels(
    geom_body_ids,
    frame_body_bindings,
    declared_entity_ids,
):
    """Translate private geom IDs to dense labels backed by canonical Entities.

    Geometries on MuJoCo world body 0 are treated as unlabeled background.
    Every other rendered geometry must resolve through exactly one Entity ID.
    """

    declared = set(declared_entity_ids)
    if not declared or any(not isinstance(value, str) or not value for value in declared):
        raise ValueError('Entity segmentation requires declared canonical Scene Entity IDs')
    body_entities = {}
    for entity_id, body_id in frame_body_bindings:
        if entity_id == 'world':
            if type(body_id) is not int or body_id != 0:
                raise ValueError('canonical world Frame must bind MuJoCo world Body 0')
            continue
        if entity_id not in declared:
            raise ValueError(f'Entity segmentation Frame binding references undeclared Entity {entity_id!r}')
        if type(body_id) is not int or body_id < 0:
            raise ValueError('Entity segmentation Frame binding contains an invalid renderer Body')
        if body_id == 0:
            if entity_id == 'world':
                continue
            raise ValueError('only the canonical world Frame may bind MuJoCo world Body 0')
        body_entities.setdefault(body_id, set()).add(entity_id)

    geom_entities = {}
    used_entities = set()
    for geom_id, body_id in enumerate(geom_body_ids):
        body_id = int(body_id)
        if body_id == 0:
            geom_entities[geom_id] = None
            continue
        owners = body_entities.get(body_id, set())
        if not owners:
            raise ValueError(f'Entity segmentation has no Canonical Frame mapping for renderer geometry {geom_id}')
        if len(owners) != 1:
            raise ValueError(f'Entity segmentation has ambiguous Canonical Entity mapping for renderer geometry {geom_id}')
        entity_id = next(iter(owners))
        geom_entities[geom_id] = entity_id
        used_entities.add(entity_id)

    ordered_entities = tuple(sorted(used_entities))
    if not ordered_entities:
        raise ValueError('Entity segmentation source contains no Entity-bound renderer geometry')
    labels = {
        entity_id: index
        for index, entity_id in enumerate(ordered_entities, start=1)
    }
    geom_labels = {
        geom_id: 0 if entity_id is None else labels[entity_id]
        for geom_id, entity_id in geom_entities.items()
    }
    label_entries = tuple(
        CanonicalEntityLabelV1(labels[entity_id], entity_id)
        for entity_id in ordered_entities
    )
    return geom_labels, label_entries


def _numbers(values):
    return ' '.join(str(v) for v in np.asarray(values).reshape(-1))


class MuJoCoCameraSession(CameraSessionValues):
    native_depth_convention = 'optical_z_m'

    def __init__(self, camera, source):
        import mujoco
        self._initialize(camera)
        self._mj = mujoco
        root = ET.Element('mujoco', model='canonical_camera')
        ET.SubElement(root,'compiler',angle='radian')
        ET.SubElement(root,'statistic',extent='1')
        visual = ET.SubElement(root,'visual')
        ET.SubElement(visual,'map',znear=str(camera.near),zfar=str(camera.far))
        ET.SubElement(visual,'global',offwidth=str(camera.width),offheight=str(camera.height))
        assets = ET.SubElement(root,'asset')
        world = ET.SubElement(root,'worldbody')
        for index,mesh in enumerate(source.meshes):
            native = f'mesh_{index}'
            ET.SubElement(assets,'mesh',name=native,vertex=_numbers(mesh.vertices_world),face=_numbers(mesh.faces))
            ET.SubElement(world,'geom',name=f'geom_{index}',type='mesh',mesh=native,
                contype='0',conaffinity='0',rgba=_numbers((*mesh.color_rgb,1)))
        ET.SubElement(world,'camera',name='canonical',pos='0 0 2',quat='1 0 0 0',fovy=str(math.degrees(camera.fov_y)))
        self._model = mujoco.MjModel.from_xml_string(ET.tostring(root,encoding='unicode'))
        self._data = mujoco.MjData(self._model)
        self._camera_index = self._model.camera('canonical').id
        self._renderer = mujoco.Renderer(self._model,height=camera.height,width=camera.width)

    def _render(self, metadata):
        transform = np.array(metadata.T_world_from_camera)
        # MuJoCo local camera +X right,+Y up,-Z forward; optical +X,+Y down,+Z forward.
        native_rotation = transform[:3,:3] @ np.diag([1.,-1.,-1.])
        quaternion = np.zeros(4)
        self._mj.mju_mat2Quat(quaternion,native_rotation.reshape(-1))
        self._model.cam_pos[self._camera_index] = transform[:3,3]
        self._model.cam_quat[self._camera_index] = quaternion
        self._mj.mj_forward(self._model,self._data)
        self._renderer.update_scene(self._data,camera='canonical')
        self._renderer.disable_depth_rendering()
        rgb = self._renderer.render().copy()
        self._renderer.enable_depth_rendering()
        depth = self._renderer.render().copy()
        self._renderer.disable_depth_rendering()
        return rgb, depth

    def close(self):
        if not self._closed:
            self._renderer.close()
            self._renderer = self._model = self._data = None
            self._closed = True


class MuJoCoDynamicCameraSession(CameraSessionValues):
    """D03 renderer-only MuJoCo model synchronized from canonical public state.

    This adapter compiles the existing Scene/source once, writes only scalar
    positions from CanonicalStateViewV1, and calls mj_kinematics for transforms.
    It never steps or evaluates the renderer model's dynamics.
    """

    native_depth_convention = 'optical_z_m_far_invalid_v1'

    def __init__(
        self,
        camera,
        source: DynamicCameraRenderSourceV1,
        initial_projection: RenderStateProjectionV1,
        *,
        execution,
        manifest,
        entity_segmentation: bool = False,
        task_camera=None,
    ):
        import mujoco

        self._initialize(camera)
        self._task_camera = task_camera
        if task_camera is not None:
            task_camera.validate()
            if (task_camera.parent_frame != 'world' or task_camera.task_artifact_hash != camera.task_artifact_hash
                    or task_camera.camera_id == camera.camera_id or task_camera.near != camera.near
                    or task_camera.far != camera.far or (task_camera.width, task_camera.height) != (camera.width, camera.height)):
                raise ValueError('MuJoCo task camera requires a distinct world camera with shared clip and resolution')
        self._mj = mujoco
        self._source = source
        self._execution = execution
        self._manifest = manifest
        if type(entity_segmentation) is not bool:
            raise TypeError('Entity segmentation selection must be bool')
        self._entity_segmentation_enabled = entity_segmentation
        self._native_geom_entity_labels = {}
        self._entity_label_entries = ()
        if entity_segmentation and not callable(
            getattr(mujoco.Renderer, 'enable_segmentation_rendering', None)
        ):
            raise RuntimeError('installed MuJoCo Renderer does not expose public segmentation rendering')
        self._consumer_id = f'mujoco-render-consumer-{uuid.uuid4().hex}'
        self._geometry_build_count = 0
        self._renderer = None
        self._last_projection = None
        self._last_sync = None
        self._faulted = False
        self._close_status = 'open'
        self._close_error = None
        self._has_rendered = False
        self._last_render_thread_id = None
        initial_boundary = initial_projection.state_boundary
        self._active_episode_key = (initial_boundary.episode_id, initial_boundary.reset_sample_id)
        self._seen_episode_keys = {self._active_episode_key}
        self._materialization_identity = (
            initial_boundary.scene_instance_id,
            initial_boundary.provider_materialization_id,
        )
        try:
            from ...runtime.sessions.source import lower_mujoco_scene_source

            source_xml, assets = lower_mujoco_scene_source(
                source.scene_source, source.scene_definition, source.source_closure_digest,
            )
            root = ET.fromstring(source_xml)
            visual = root.find('visual')
            if visual is None:
                visual = ET.SubElement(root, 'visual')
            global_visual = visual.find('global')
            if global_visual is None:
                global_visual = ET.SubElement(visual, 'global')
            global_visual.set('offwidth', str(camera.width))
            global_visual.set('offheight', str(camera.height))
            world = root.find('worldbody')
            if world is None:
                raise ValueError('D03 render source lacks the existing MJCF worldbody')
            if source.schema_version == 'camera-dynamic-source-v2':
                # Generate stable names at lowering time, before native IDs exist.
                # They are scoped by the source/geometry identity, not inferred
                # from physics ordinals. Existing authored names remain intact.
                if any(node.tag in {'flex', 'flexcomp', 'composite', 'skin'} for node in root.iter()):
                    raise ValueError('deformable visual representations are unsupported')
                existing = {node.get('name') for node in root.iter('geom') if node.get('name')}
                for index, geom in enumerate(world.iter('geom')):
                    if geom.get('name') is None:
                        name = f'geochora_v211_geom_{index}'
                        if name in existing:
                            raise ValueError('generated visual geometry name collides with source')
                        geom.set('name', name)
                        existing.add(name)
            self._source_camera_names = tuple(node.get('name') or 'unnamed' for node in world.iter('camera'))
            self._source_light_names = tuple(node.get('name') or 'unnamed' for node in world.iter('light'))
            self._native_camera_name = 'geochora_d03_camera'
            if any(node.get('name') == self._native_camera_name for node in root.iter('camera')):
                raise ValueError('D03 renderer camera name collides with the materialized source')
            ET.SubElement(
                world, 'camera', name=self._native_camera_name, pos='0 0 1',
                quat='1 0 0 0', fovy=str(math.degrees(camera.fov_y)),
            )
            if task_camera is not None:
                name = 'geochora_task_camera'
                if any(node.get('name') == name for node in root.iter('camera')):
                    raise ValueError('task camera name collides with source')
                transform = np.asarray(task_camera.T_parent_from_mount) @ np.asarray(task_camera.T_mount_from_camera)
                rotation = transform[:3, :3] @ np.diag([1., -1., -1.])
                quaternion = np.zeros(4)
                mujoco.mju_mat2Quat(quaternion, rotation.reshape(-1))
                ET.SubElement(world, 'camera', name=name, pos=_numbers(transform[:3, 3]),
                              quat=_numbers(quaternion), fovy=str(math.degrees(task_camera.fov_y)))
            if not any(node.tag == 'light' for node in world.iter()):
                ET.SubElement(
                    world, 'light', name='geochora_d03_key', pos='1 -1 2',
                    dir='-1 1 -2', directional='true', diffuse='0.8 0.8 0.8',
                    ambient='0.25 0.25 0.25',
                )
            self._model = mujoco.MjModel.from_xml_string(
                ET.tostring(root, encoding='unicode'), assets=assets,
            )
            from .api import V211_RGB_PROFILE
            if camera.depth or getattr(manifest, 'render_profile', None) == V211_RGB_PROFILE:
                extent = float(self._model.stat.extent)
                if not math.isfinite(extent) or extent <= 0:
                    raise ValueError('camera clipping requires a finite positive MuJoCo model extent')
                # MuJoCo scales these visual clipping distances by model extent.
                self._model.vis.map.znear = camera.near / extent
                self._model.vis.map.zfar = camera.far / extent
            self._data = mujoco.MjData(self._model)
            self._camera_index = self._model.camera(self._native_camera_name).id
            self._joint_qpos_addresses = self._resolve_joint_addresses()
            self._body_ids = self._resolve_body_ids()
            self._free_qpos_addresses = self._resolve_free_addresses()
            self._visual_instance_bindings = self._resolve_visual_instances()
            if self._entity_segmentation_enabled:
                frame_body_bindings = tuple(
                    (
                        binding.entity_id,
                        self._body_ids[(binding.entity_id, binding.frame_id)],
                    )
                    for binding in source.frame_bindings
                )
                self._native_geom_entity_labels, self._entity_label_entries = (
                    _resolve_canonical_entity_geometry_labels(
                        self._model.geom_bodyid,
                        frame_body_bindings,
                        (entity.entity_id for entity in source.scene_definition.entities),
                    )
                )
            self._renderer = mujoco.Renderer(self._model, height=camera.height, width=camera.width)
            self._geometry_build_count = 1
            if initial_projection.geometry_version != source.geometry_version:
                raise ValueError('initial render projection uses another geometry version')
            self._consume_projection(initial_projection)
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f'renderer cleanup also failed: {cleanup_error!r}')
            raise

    @property
    def consumer_id(self):
        return self._consumer_id

    def _require_trustworthy(self):
        if getattr(self, '_faulted', False):
            raise RuntimeError('camera session is faulted; visual state and receipts are invalid')
        if self._closed:
            raise RuntimeError('camera session is closed; visual state and receipts are invalid')

    @property
    def close_status(self):
        """Actual renderer cleanup outcome, including an unsuccessful close."""
        return {'status': getattr(self, '_close_status', 'open'),
                'error': getattr(self, '_close_error', None)}

    @property
    def last_sync(self):
        self._require_trustworthy()
        return self._last_sync

    @property
    def last_consumed_publication_version(self):
        self._require_trustworthy()
        return None if self._last_projection is None else self._last_projection.publication_version

    @property
    def last_consumed_transform_version(self):
        self._require_trustworthy()
        return None if self._last_projection is None else self._last_projection.transform_version

    @property
    def static_geometry_build_count(self):
        return self._geometry_build_count

    @property
    def visual_instance_bindings(self):
        return self._visual_instance_bindings

    def _resolve_joint_addresses(self):
        addresses = {}
        joint_kinds = {
            (joint.parent_frame.entity_id, joint.joint_id): joint.kind
            for articulation in self._source.scene_definition.articulations or ()
            for joint in articulation.joints
        }
        for binding in self._source.joint_bindings:
            joint_id = self._model.joint(binding.native_joint_name).id
            joint_type = int(self._model.jnt_type[joint_id])
            supported = {
                'revolute': self._mj.mjtJoint.mjJNT_HINGE,
                'continuous': self._mj.mjtJoint.mjJNT_HINGE,
                'prismatic': self._mj.mjtJoint.mjJNT_SLIDE,
            }
            expected = supported.get(joint_kinds.get((binding.entity_id, binding.joint_id)))
            if expected is None or joint_type != expected:
                raise ValueError(
                    f'D03 render source Joint kind does not match MuJoCo scalar joint {binding.native_joint_name!r}'
                )
            addresses[(binding.entity_id, binding.joint_id)] = int(self._model.jnt_qposadr[joint_id])
        return addresses

    def _resolve_free_addresses(self):
        result = {}
        for entity, joint, native, frame_entity, frame_id in getattr(self._source, 'free_bindings', ()):
            joint_id = int(self._model.joint(native).id)
            body_id = self._body_ids[(frame_entity, frame_id)]
            if (int(self._model.jnt_type[joint_id]) != int(self._mj.mjtJoint.mjJNT_FREE)
                    or int(self._model.jnt_bodyid[joint_id]) != body_id
                    or int(self._model.body_parentid[body_id]) != 0):
                raise ValueError('free Joint must bind its named world-child body origin')
            result[(frame_entity, frame_id)] = int(self._model.jnt_qposadr[joint_id])
        if len(result) != len(getattr(self._source, 'free_bindings', ())):
            raise ValueError('multiple free Joints cannot own the same render body')
        return result

    def _resolve_body_ids(self):
        return {
            (binding.entity_id, binding.frame_id): int(self._model.body(binding.native_body_name).id)
            for binding in self._source.frame_bindings
        }

    def _resolve_visual_instances(self):
        by_body = {body_id: key for key, body_id in self._body_ids.items()}
        geom_names_by_body = {body_id: [] for body_id in self._body_ids.values()}
        geom_names_by_body.setdefault(0, [])
        for geom_id, body_id_value in enumerate(self._model.geom_bodyid):
            body_id = int(body_id_value)
            if body_id not in by_body and body_id != 0:
                raise ValueError(f'D03 renderer geometry {geom_id} has no Canonical Frame binding')
            name = self._mj.mj_id2name(self._model, self._mj.mjtObj.mjOBJ_GEOM, geom_id)
            geom_names_by_body[body_id].append(str(name) if name else f'geom#{geom_id}')
        result = []
        for binding in self._source.frame_bindings:
            key = (binding.entity_id, binding.frame_id)
            body_id = self._body_ids[key]
            result.append(RenderVisualInstanceBindingV1(
                binding.entity_id, binding.frame_id, binding.native_body_name,
                tuple(geom_names_by_body[body_id]),
            ))
        if geom_names_by_body.get(0):
            result.append(RenderVisualInstanceBindingV1(
                'world', 'world', 'world', tuple(geom_names_by_body[0]),
            ))
        return tuple(result)

    def capture(self, state):
        self._require_trustworthy()
        from .api import V211_DYNAMIC_PROFILE, V211_RGB_PROFILE
        if self._manifest.render_profile == V211_DYNAMIC_PROFILE:
            raise RuntimeError('v211 visual binding does not admit RGB capture')
        try:
            result = super().capture(state)
            if self._manifest.render_profile == V211_RGB_PROFILE:
                self._verify_linear_framebuffer()
            return result
        except BaseException as error:
            # Capture may have changed native camera/context state.  Never
            # expose an old receipt or continue using the affected owner.
            if self._source.schema_version == 'camera-dynamic-source-v2':
                self._faulted = True
                self._last_projection = self._last_sync = None
                try:
                    self.close()
                except BaseException as cleanup_error:
                    error.add_note(f'renderer close after capture failure also failed: {cleanup_error!r}')
            raise

    @staticmethod
    def _verify_linear_framebuffer():
        """Reject an unknown GL write encoding before exposing this RGB profile."""
        import ctypes
        import ctypes.util

        library = ctypes.util.find_library('GL')
        if not library:
            raise RuntimeError('MuJoCo RGB framebuffer encoding cannot be checked')
        gl = ctypes.CDLL(library)
        gl.glIsEnabled.argtypes = [ctypes.c_uint]
        gl.glIsEnabled.restype = ctypes.c_ubyte
        gl.glGetIntegerv.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]
        gl.glGetFramebufferAttachmentParameteriv.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]
        gl.glGetError.restype = ctypes.c_uint
        binding, encoding = ctypes.c_int(), ctypes.c_int()
        gl.glGetIntegerv(0x8CA6, ctypes.byref(binding))  # GL_FRAMEBUFFER_BINDING
        gl.glGetFramebufferAttachmentParameteriv(0x8D40, 0x8CE0, 0x8210, ctypes.byref(encoding))
        srgb = bool(gl.glIsEnabled(0x8DB9))  # GL_FRAMEBUFFER_SRGB
        error = gl.glGetError()
        if error or binding.value == 0 or encoding.value != 0x2601 or srgb:  # GL_LINEAR
            raise RuntimeError('MuJoCo RGB requires a linear-encoded offscreen GL framebuffer '
                               f'(binding={binding.value}, encoding={encoding.value}, '
                               f'srgb={srgb}, gl_error={error})')

    @property
    def camera_geometry_identity(self):
        self._require_trustworthy()
        return self._geometry.identity_hash

    def set_observer_camera(self, camera):
        self._require_trustworthy()
        if self._task_camera is None:
            raise RuntimeError('persistent observer camera requires a task camera')
        if (camera.near, camera.far) != (self._task_camera.near, self._task_camera.far):
            raise ValueError('MuJoCo task and observer cameras must share clip interval')
        self._model.cam_fovy[self._camera_index] = math.degrees(camera.fov_y)
        self._geometry = camera

    def task_camera_binding(self, state):
        self._require_trustworthy()
        if self._task_camera is None:
            raise RuntimeError('no task camera is bound')
        self.sync_state(state)
        self._mj.mj_kinematics(self._model, self._data)
        self._mj.mj_camlight(self._model, self._data)
        index = self._model.camera('geochora_task_camera').id
        native = np.eye(4)
        native[:3, :3] = np.asarray(self._data.cam_xmat[index]).reshape(3, 3) @ np.diag([1., -1., -1.])
        native[:3, 3] = self._data.cam_xpos[index]
        expected = np.asarray(self._task_camera.T_parent_from_mount) @ np.asarray(self._task_camera.T_mount_from_camera)
        fov = float(self._model.cam_fovy[index])
        clip = [float(self._model.vis.map.znear * self._model.stat.extent),
                float(self._model.vis.map.zfar * self._model.stat.extent)]
        resolution = [int(self._renderer.width), int(self._renderer.height)]
        if (not np.allclose(native, expected, atol=1e-6, rtol=0)
                or not math.isclose(fov, math.degrees(self._task_camera.fov_y), abs_tol=1e-6)
                or not np.allclose(clip, (self._task_camera.near, self._task_camera.far), atol=2e-6, rtol=0)
                or resolution != [self._task_camera.width, self._task_camera.height]):
            raise RuntimeError('native task camera differs from declaration')
        return {'camera': self._task_camera.to_mapping(), 'camera_identity': self._task_camera.identity_hash,
                'owner': self._consumer_id, 'native_camera': 'geochora_task_camera',
                'native_world_transform': native.tolist(), 'native_fov_y_degrees': fov,
                'native_clip': clip, 'native_resolution': resolution,
                'state_boundary': state.boundary.to_mapping(), 'source_closure': self._source.source_closure_digest}

    def visual_model_info(self):
        """Describe renderer-owned model resources without exposing native handles."""
        if self._closed:
            raise RuntimeError('camera session is closed')
        def names(kind, count):
            return tuple(self._mj.mj_id2name(self._model, kind, i) or f'unnamed#{i}' for i in range(count))
        return {
            'ownership': 'renderer-only model/data/context; physics not borrowed',
            'device_policy': 'CPU state copied to renderer-owned qpos; synchronous kinematics',
            'geometry_version': self._source.geometry_version,
            'source_closure_digest': self._source.source_closure_digest,
            'geometries': names(self._mj.mjtObj.mjOBJ_GEOM, self._model.ngeom),
            'materials': names(self._mj.mjtObj.mjOBJ_MATERIAL, self._model.nmat),
            'cameras': names(self._mj.mjtObj.mjOBJ_CAMERA, self._model.ncam),
            'lights': names(self._mj.mjtObj.mjOBJ_LIGHT, self._model.nlight),
            'source_camera_names': self._source_camera_names,
            'source_light_names': self._source_light_names,
            'added_camera': self._native_camera_name,
            'added_fallback_light': not self._source_light_names,
            'geometry_materials': tuple({
                'geometry': self._mj.mj_id2name(self._model, self._mj.mjtObj.mjOBJ_GEOM, i) or f'unnamed#{i}',
                'material': (None if int(self._model.geom_matid[i]) < 0 else
                             self._mj.mj_id2name(self._model, self._mj.mjtObj.mjOBJ_MATERIAL,
                                                 int(self._model.geom_matid[i]))),
                'rgba': tuple(float(x) for x in self._model.geom_rgba[i]),
            } for i in range(self._model.ngeom)),
            'visual_bindings': tuple(item.to_mapping() for item in self._visual_instance_bindings),
            'limitations': ('rigid bodies only', 'no solver step', 'no async/shared state',
                            'camera output not qualified by visual binding'),
        }

    def visual_body_pose(self, entity_id, frame_id):
        """Return an owned world body-origin pose from renderer-only kinematics."""
        if self._closed:
            raise RuntimeError('camera session is closed')
        body_id = self._body_ids[(entity_id, frame_id)]
        return (tuple(float(x) for x in self._data.xpos[body_id]),
                tuple(float(x) for x in self._data.xquat[body_id]))

    def sync_state(self, state):
        if self._closed:
            raise RuntimeError('camera session is closed')
        projection = project_render_state_v1(self._source, state)
        return self._consume_projection(projection)

    def _consume_projection(self, projection: RenderStateProjectionV1):
        if projection.source_identity_hash != self._source.identity_hash:
            raise ValueError('render projection source identity changed after materialization')
        if projection.geometry_version != self._source.geometry_version:
            raise ValueError('render projection geometry version changed after materialization')
        previous = self._last_projection
        boundary = projection.state_boundary
        materialization = (boundary.scene_instance_id, boundary.provider_materialization_id)
        episode_key = (boundary.episode_id, boundary.reset_sample_id)
        episode_transition = episode_key != self._active_episode_key
        if not episode_transition and materialization != self._materialization_identity:
            raise ValueError('dynamic camera refused state from another provider materialization')
        if previous is not None and self._source.schema_version == 'camera-dynamic-source-v2':
            if materialization != self._materialization_identity:
                raise ValueError('visual binding refused another provider materialization')
            if not episode_transition and projection.publication_version != previous.publication_version:
                if (boundary.state_revision <= previous.state_boundary.state_revision
                        or projection.sample_clock.simulation_time_s < previous.sample_clock.simulation_time_s):
                    raise ValueError('visual binding refused stale state revision or clock')
        if previous is not None:
            if episode_transition:
                if episode_key in self._seen_episode_keys:
                    raise ValueError('dynamic camera refused a Canonical State from a previous episode')
                if boundary.control_step != 0:
                    raise ValueError('dynamic camera requires a new episode publication to begin at reset step zero')
            elif (
                boundary.control_step < previous.state_boundary.control_step
                or (boundary.control_step == previous.state_boundary.control_step
                    and boundary.state_revision < previous.state_boundary.state_revision)
            ):
                raise ValueError('dynamic camera refused a stale Canonical State publication')
            if projection.publication_version == previous.publication_version and (
                projection.transform_version != previous.transform_version
                or projection.sample_clock != previous.sample_clock
            ):
                raise ValueError('dynamic camera state changed without a new publication version')
        publication_updated = previous is None or projection.publication_version != previous.publication_version
        transforms_updated = previous is None or projection.transform_version != previous.transform_version
        old_qpos = self._data.qpos.copy() if transforms_updated else None
        old_time = float(self._data.time) if transforms_updated else None
        try:
            if transforms_updated:
                for entity_id, joint_id, _native_name, position in projection.joint_positions:
                    address = self._joint_qpos_addresses[(entity_id, joint_id)]
                    self._data.qpos[address] = position
                poses = {(entity, frame): (position, quaternion)
                         for entity, frame, _native, position, quaternion in projection.frame_poses}
                for key, address in self._free_qpos_addresses.items():
                    position, quaternion = poses[key]
                    self._data.qpos[address:address + 7] = (*position, *quaternion)
                self._data.time = float(projection.sample_clock.simulation_time_s)
                self._mj.mj_kinematics(self._model, self._data)
            position_error, quaternion_error = self._validate_frame_poses(projection)
        except BaseException as error:
            restored = False
            if transforms_updated and previous is not None:
                try:
                    self._data.qpos[:] = old_qpos
                    self._data.time = old_time
                    self._mj.mj_kinematics(self._model, self._data)
                    # Restoring qpos alone does not establish derived transforms.
                    self._validate_frame_poses(previous)
                    restored = True
                except BaseException as cleanup_error:
                    error.add_note(f'renderer state restoration also failed: {cleanup_error!r}')
            # Pose checks do not prove every renderer-derived field was restored.
            # A failed post-effect update therefore always requires rebuilding.
            if restored:
                error.add_note('previous frame poses restored; renderer binding still requires rebuild')
            self._faulted = True
            self._last_projection = self._last_sync = None
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f'renderer close after fault also failed: {cleanup_error!r}')
            raise
        if episode_transition:
            self._seen_episode_keys.add(episode_key)
            self._active_episode_key = episode_key
            self._materialization_identity = materialization
        self._last_projection = projection
        receipt_type = RenderStateSyncReceiptV2 if self._source.schema_version == 'camera-dynamic-source-v2' else RenderStateSyncReceiptV1
        receipt_version = 'render-state-sync-receipt-v2' if receipt_type is RenderStateSyncReceiptV2 else 'render-state-sync-receipt-v1'
        self._last_sync = receipt_type(
            receipt_version, self._consumer_id,
            projection.source_identity_hash, projection.geometry_version,
            projection.publication_version, projection.transform_version,
            projection.state_boundary, projection.sample_clock,
            publication_updated, transforms_updated, self._geometry_build_count,
            position_error, quaternion_error, self._visual_instance_bindings,
        )
        return self._last_sync

    def _validate_frame_poses(self, projection):
        maximum_position_error = 0.0
        maximum_quaternion_error = 0.0
        for entity_id, frame_id, native_body, position, quaternion in projection.frame_poses:
            body_id = self._body_ids[(entity_id, frame_id)]
            native_position = np.asarray(self._data.xpos[body_id], dtype=np.float64)
            native_quaternion = np.asarray(self._data.xquat[body_id], dtype=np.float64)
            expected_position = np.asarray(position, dtype=np.float64)
            expected_quaternion = np.asarray(quaternion, dtype=np.float64)
            position_error = float(np.linalg.norm(native_position - expected_position))
            quaternion_error = min(
                float(np.linalg.norm(native_quaternion - expected_quaternion)),
                float(np.linalg.norm(native_quaternion + expected_quaternion)),
            )
            maximum_position_error = max(maximum_position_error, position_error)
            maximum_quaternion_error = max(maximum_quaternion_error, quaternion_error)
            position_limit = 1e-5 if self._source.schema_version == 'camera-dynamic-source-v2' else D03_FRAME_POSITION_ATOL_M
            quaternion_limit = 1e-5 if self._source.schema_version == 'camera-dynamic-source-v2' else D03_FRAME_QUATERNION_SIGN_INVARIANT_L2_ATOL
            if position_error > position_limit or quaternion_error > quaternion_limit:
                raise ValueError(
                    f'D03 renderer Frame pose disagrees with Canonical State for '
                    f'{entity_id}/{frame_id} -> {native_body}: '
                    f'{position_error:g} m, {quaternion_error:g} quaternion L2'
                )
        return maximum_position_error, maximum_quaternion_error

    def _before_capture(self, state):
        self.sync_state(state)

    def _capture_identity(self, state):
        if self._last_projection is None:
            raise RuntimeError('dynamic camera has no consumed Canonical State publication')
        if (
            state.boundary.boundary_id != self._last_projection.state_boundary.boundary_id
            or state.sample_clock != self._last_projection.sample_clock
        ):
            raise RuntimeError('camera capture identity does not match the consumed Canonical State publication')
        return self._source.capture_identity(
            self._geometry, self._execution, self._manifest, state,
            additional_modalities=(
                ('entity_instance_segmentation',) if self._entity_segmentation_enabled else ()
            ),
        )

    def _canonical_segmentation(self, native, state, capture_identity):
        if not self._entity_segmentation_enabled:
            if native is not None:
                raise RuntimeError('MuJoCo returned Entity segmentation outside the admitted profile')
            return None
        if native is None:
            raise RuntimeError('admitted Entity segmentation profile produced no native segmentation image')
        values = np.asarray(native)
        if values.shape != (self._geometry.height, self._geometry.width, 2) or values.dtype != np.dtype(np.int32):
            raise ValueError('MuJoCo segmentation output must be H×W×2 int32 object ID/type pairs')

        object_ids = values[:, :, 0]
        object_types = values[:, :, 1]
        background = (object_ids == -1) & (object_types == -1)
        partial_background = (object_ids == -1) ^ (object_types == -1)
        if np.any(partial_background):
            raise ValueError('MuJoCo segmentation returned a malformed partial background pair')
        geometry_type = int(self._mj.mjtObj.mjOBJ_GEOM)
        foreground = ~background
        if np.any(object_types[foreground] != geometry_type):
            raise ValueError('Entity segmentation only supports MuJoCo geom objects in this profile')
        visible_geom_ids = tuple(int(value) for value in np.unique(object_ids[foreground]))
        unknown_geom_ids = set(visible_geom_ids).difference(self._native_geom_entity_labels)
        if unknown_geom_ids:
            raise ValueError(
                f'MuJoCo segmentation exposed geometries without canonical Entity mapping: {sorted(unknown_geom_ids)}'
            )

        mask = np.zeros((self._geometry.height, self._geometry.width), dtype=np.uint32)
        for geom_id in visible_geom_ids:
            mask[object_ids == geom_id] = np.uint32(self._native_geom_entity_labels[geom_id])
        boundary = capture_identity.state_boundary
        label_map = CanonicalEntityLabelMapV1(
            schema_version='canonical-entity-label-map-v1',
            task_artifact_hash=capture_identity.task_artifact_hash,
            scene_identity_hash=boundary.scene_identity_hash,
            render_source_identity_hash=capture_identity.render_source_identity_hash,
            camera_id=capture_identity.camera_id,
            scene_instance_id=boundary.scene_instance_id,
            provider_materialization_id=boundary.provider_materialization_id,
            episode_id=boundary.episode_id,
            reset_sample_id=boundary.reset_sample_id,
            state_boundary_id=boundary.boundary_id,
            state_revision=boundary.state_revision,
            control_step=boundary.control_step,
            simulation_time_s=capture_identity.sample_clock.simulation_time_s,
            capture_identity_hash=capture_identity.identity_hash,
            labels=self._entity_label_entries,
        )
        return CanonicalEntityInstanceSegmentationV1(
            schema_version='canonical-entity-instance-segmentation-v1',
            mask=mask,
            background_label=0,
            label_map=label_map,
        )

    def _render(self, metadata):
        if self._last_projection is None:
            raise RuntimeError('dynamic camera has no consumed Canonical State publication')
        self._has_rendered = False
        self._last_render_thread_id = None
        transform = np.asarray(metadata.T_world_from_camera, dtype=np.float64)
        native_rotation = transform[:3, :3] @ np.diag([1.0, -1.0, -1.0])
        quaternion = np.zeros(4, dtype=np.float64)
        self._mj.mju_mat2Quat(quaternion, native_rotation.reshape(-1))
        self._model.cam_pos[self._camera_index] = transform[:3, 3]
        self._model.cam_quat[self._camera_index] = quaternion
        self._data.time = float(metadata.capture_simulation_time)
        # These update renderer transforms/cameras only. No mj_forward, mj_step
        # or Controller call; mj_kinematics alone does not refresh camera poses.
        self._mj.mj_kinematics(self._model, self._data)
        self._mj.mj_camlight(self._model, self._data)
        self._renderer.update_scene(self._data, camera=self._native_camera_name)
        rgb = depth = segmentation = None
        self._renderer.disable_depth_rendering()
        try:
            if self._geometry.rgb:
                rgb = self._renderer.render().copy()
            if self._geometry.depth:
                self._renderer.enable_depth_rendering()
                depth = self._renderer.render().copy()
            if self._entity_segmentation_enabled:
                self._renderer.disable_depth_rendering()
                self._renderer.enable_segmentation_rendering()
                segmentation = self._renderer.render().copy()
        finally:
            self._renderer.disable_depth_rendering()
            if self._entity_segmentation_enabled:
                self._renderer.disable_segmentation_rendering()
        self._has_rendered = True
        self._last_render_thread_id = threading.get_ident()
        if self._entity_segmentation_enabled:
            return rgb, depth, segmentation
        return rgb, depth

    def graphics_device_info(self):
        """Observe the current GL context after this session has rendered.

        MuJoCo does not expose a public Renderer context handle or a public
        make-current method. Call this synchronously on the rendering thread
        immediately after capture. This is diagnostic observation only; it is
        not device-pinning or pairing admission evidence.
        """

        if self._closed:
            raise RuntimeError('camera session is closed')
        if not self._has_rendered or threading.get_ident() != self._last_render_thread_id:
            raise RuntimeError('graphics device info requires the current rendering thread after capture')
        from OpenGL import GL

        def decode(value):
            return None if value is None else value.decode('utf-8', errors='replace')

        values = {
            'render_api': 'MuJoCo native OpenGL Renderer',
            'mujoco_gl_selection': os.environ.get('MUJOCO_GL', 'MuJoCo default GL selection'),
            'display': os.environ.get('DISPLAY'),
            'vendor': decode(GL.glGetString(GL.GL_VENDOR)),
            'renderer': decode(GL.glGetString(GL.GL_RENDERER)),
            'version': decode(GL.glGetString(GL.GL_VERSION)),
            'observation_scope': 'current OpenGL context immediately after successful MuJoCo capture; diagnostic only',
        }
        if values['vendor'] is None or values['renderer'] is None or values['version'] is None:
            raise RuntimeError('current OpenGL context did not expose vendor, renderer, and version strings')
        return values

    def close(self):
        if not self._closed:
            renderer, self._renderer = getattr(self, '_renderer', None), None
            self._model = self._data = None
            self._closed = True
            self._close_status = 'not_allocated' if renderer is None else 'close_attempted'
            if renderer is not None:
                try:
                    renderer.close()
                except BaseException as error:
                    self._close_status = 'close_failed_unknown_release'
                    self._close_error = f'{type(error).__name__}: {error}'
                    raise
                self._close_status = 'closed'
