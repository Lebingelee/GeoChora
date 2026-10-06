"""Own public native raytracer objects; never access visualizer._camera."""
import math
import numpy as np
from .api import CameraSessionValues


class GeoPhysCameraSession(CameraSessionValues):
    native_depth_convention = 'ray_distance_m'

    def __init__(self, camera, source):
        from visualization.raytracer import RayCamera, FrameBuffer, EnvironmentPipeline, LightingSystem, MeshPipeline, RayTraceEngine, TonemapPass
        self._initialize(camera)
        self._native_camera = RayCamera()
        self._native_camera.set_fov(math.degrees(camera.fov_y))
        self._framebuffer = FrameBuffer(camera.width,camera.height,max_depth_resolution=(camera.width,camera.height))
        environment = EnvironmentPipeline()
        environment.floor_enabled[None] = 0
        environment.skybox_enabled[None] = 0
        environment.domain_min[None] = [-10,-10,-10]
        environment.domain_max[None] = [10,10,10]
        lighting = LightingSystem()
        lighting.set_ambient([.5,.5,.5])
        lighting.set_shadows_enabled(False)
        vertices,faces,colors = [],[],[]
        for mesh in source.meshes:
            faces.extend([[i+len(vertices) for i in face] for face in mesh.faces])
            vertices.extend(mesh.vertices_world)
            colors.extend([mesh.color_rgb]*len(mesh.faces))
        pipeline = MeshPipeline(np.array(vertices,dtype=np.float32),np.array(faces,dtype=np.int32),
            colors=np.array(colors,dtype=np.float32), environment=environment,lighting=lighting,
            max_pixel_resolution=(camera.width,camera.height))
        self._engine = RayTraceEngine(self._native_camera,environment,self._framebuffer,
            lighting=lighting,mesh_pipeline=pipeline,tonemap=TonemapPass())

    def _render(self, metadata):
        import taichi as ti
        transform = np.array(metadata.T_world_from_camera)
        position = transform[:3,3]
        self._native_camera.set_pose(position,position+transform[:3,2],-transform[:3,1])
        self._engine.render_frame(graph_mode='off')
        ti.sync()
        return (self._framebuffer.read_color(transpose=True,flip_vertical=True),
                self._framebuffer.read_depth(transpose=True,flip_vertical=True))

    def close(self):
        self._closed = True
        self._engine = self._native_camera = self._framebuffer = None
        # Taichi fields are process-owned; native runtime teardown at worker exit.
