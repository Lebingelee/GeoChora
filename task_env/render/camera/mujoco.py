"""Public MuJoCo Renderer translation; native models/IDs remain adapter-private."""
import math
import os
import uuid
import xml.etree.ElementTree as ET
import numpy as np
from .api import CameraSessionValues
from .source import (
    DynamicCameraRenderSourceV1,
    RenderStateProjectionV1,
    RenderStateSyncReceiptV1,
    RenderVisualInstanceBindingV1,
    project_render_state_v1,
)


D03_FRAME_POSITION_ATOL_M = 5.0e-4
D03_FRAME_QUATERNION_SIGN_INVARIANT_L2_ATOL = 1.0e-3


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

    native_depth_convention = 'optical_z_m'

    def __init__(self, camera, source: DynamicCameraRenderSourceV1, initial_projection: RenderStateProjectionV1):
        import mujoco

        self._initialize(camera)
        self._mj = mujoco
        self._source = source
        self._consumer_id = f'mujoco-render-consumer-{uuid.uuid4().hex}'
        self._geometry_build_count = 0
        self._renderer = None
        self._last_projection = None
        self._last_sync = None
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
            self._data = mujoco.MjData(self._model)
            self._camera_index = self._model.camera(self._native_camera_name).id
            self._joint_qpos_addresses = self._resolve_joint_addresses()
            self._body_ids = self._resolve_body_ids()
            self._visual_instance_bindings = self._resolve_visual_instances()
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
        if previous is not None:
            same_episode = (
                projection.state_boundary.episode_id == previous.state_boundary.episode_id
                and projection.state_boundary.reset_sample_id == previous.state_boundary.reset_sample_id
            )
            if same_episode and (
                projection.state_boundary.control_step < previous.state_boundary.control_step
                or (projection.state_boundary.control_step == previous.state_boundary.control_step
                    and projection.state_boundary.state_revision < previous.state_boundary.state_revision)
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

    def _render(self, metadata):
        if self._last_projection is None:
            raise RuntimeError('dynamic camera has no consumed Canonical State publication')
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
        rgb = depth = None
        if self._geometry.rgb:
            self._renderer.disable_depth_rendering()
            rgb = self._renderer.render().copy()
        if self._geometry.depth:
            self._renderer.enable_depth_rendering()
            depth = self._renderer.render().copy()
            self._renderer.disable_depth_rendering()
        return rgb, depth

    def graphics_device_info(self):
        """Read the current native GL context identity for the bounded receipt."""

        if self._closed:
            raise RuntimeError('camera session is closed')
        self._renderer._gl_context.make_current()
        from OpenGL import GL

        def decode(value):
            return None if value is None else value.decode('utf-8', errors='replace')

        return {
            'render_api': 'MuJoCo native OpenGL Renderer',
            'mujoco_gl_selection': os.environ.get('MUJOCO_GL', 'MuJoCo default GL selection'),
            'display': os.environ.get('DISPLAY'),
            'vendor': decode(GL.glGetString(GL.GL_VENDOR)),
            'renderer': decode(GL.glGetString(GL.GL_RENDERER)),
            'version': decode(GL.glGetString(GL.GL_VERSION)),
        }

    def close(self):
        if not self._closed:
            self._renderer.close()
            self._renderer = self._model = self._data = None
            self._closed = True
