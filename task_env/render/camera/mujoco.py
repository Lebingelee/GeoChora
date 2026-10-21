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
    RenderStateSyncReceiptV1,
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
    ):
        import mujoco

        self._initialize(camera)
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
            self._native_camera_name = 'geochora_d03_camera'
            if any(node.get('name') == self._native_camera_name for node in root.iter('camera')):
                raise ValueError('D03 renderer camera name collides with the materialized source')
            ET.SubElement(
                world, 'camera', name=self._native_camera_name, pos='0 0 1',
                quat='1 0 0 0', fovy=str(math.degrees(camera.fov_y)),
            )
            if not any(node.tag == 'light' for node in world.iter()):
                ET.SubElement(
                    world, 'light', name='geochora_d03_key', pos='1 -1 2',
                    dir='-1 1 -2', directional='true', diffuse='0.8 0.8 0.8',
                    ambient='0.25 0.25 0.25',
                )
            self._model = mujoco.MjModel.from_xml_string(
                ET.tostring(root, encoding='unicode'), assets=assets,
            )
            if camera.depth:
                extent = float(self._model.stat.extent)
                if not math.isfinite(extent) or extent <= 0:
                    raise ValueError('D04 optical-Z depth requires a finite positive MuJoCo model extent')
                # MuJoCo scales these visual clipping distances by model extent.
                self._model.vis.map.znear = camera.near / extent
                self._model.vis.map.zfar = camera.far / extent
            self._data = mujoco.MjData(self._model)
            self._camera_index = self._model.camera(self._native_camera_name).id
            self._joint_qpos_addresses = self._resolve_joint_addresses()
            self._body_ids = self._resolve_body_ids()
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
        except Exception:
            if self._renderer is not None:
                self._renderer.close()
            self._renderer = self._model = self._data = None
            self._closed = True
            raise

    @property
    def consumer_id(self):
        return self._consumer_id

    @property
    def last_sync(self):
        return self._last_sync

    @property
    def last_consumed_publication_version(self):
        return None if self._last_projection is None else self._last_projection.publication_version

    @property
    def last_consumed_transform_version(self):
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
        if transforms_updated:
            for entity_id, joint_id, _native_name, position in projection.joint_positions:
                address = self._joint_qpos_addresses[(entity_id, joint_id)]
                self._data.qpos[address] = position
            self._data.time = float(projection.sample_clock.simulation_time_s)
            self._mj.mj_kinematics(self._model, self._data)
        try:
            position_error, quaternion_error = self._validate_frame_poses(projection)
        except Exception:
            if transforms_updated:
                self._data.qpos[:] = old_qpos
                self._data.time = old_time
                self._mj.mj_kinematics(self._model, self._data)
            raise
        if episode_transition:
            self._seen_episode_keys.add(episode_key)
            self._active_episode_key = episode_key
            self._materialization_identity = materialization
        self._last_projection = projection
        self._last_sync = RenderStateSyncReceiptV1(
            'render-state-sync-receipt-v1', self._consumer_id,
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
            if (position_error > D03_FRAME_POSITION_ATOL_M
                    or quaternion_error > D03_FRAME_QUATERNION_SIGN_INVARIANT_L2_ATOL):
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
            self._renderer.close()
            self._renderer = self._model = self._data = None
            self._closed = True
