"""Public MuJoCo Renderer translation; native models/IDs remain adapter-private."""
import math
import xml.etree.ElementTree as ET
import numpy as np
from .api import CameraSessionValues


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
