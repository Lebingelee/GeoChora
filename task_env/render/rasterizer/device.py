"""Device-pose adapter from a source-bound batch to the GeoPhys Rasterizer."""
from __future__ import annotations

import numpy as np


class _RigidPoseSource:
    """Renderer-owned Taichi fields populated from public batch snapshots."""

    def __init__(self, count, *, lower, upper):
        import taichi as ti
        from visualization.rigid_transform_provider import build_rigid_render_transform_provider

        self.body_positions = ti.Vector.field(3, ti.f32, shape=count)
        self.body_orientations = ti.Vector.field(4, ti.f32, shape=count)
        self.domain_min_vec = np.asarray(lower, dtype=np.float32)
        self.domain_max_vec = np.asarray(upper, dtype=np.float32)
        self.ground = None
        self._provider = build_rigid_render_transform_provider(
            provider_id='task-env-device-batch', body_count=count,
            positions=self.body_positions, orientations=self.body_orientations, live=True)

    def read_rigid_render_transform_provider(self):
        return self._provider

    def read_surface_geometries(self):
        return ()

    def read_external_render_geometries(self):
        return ()

    def read_static_geometries(self):
        return ()

    def read_debug_geometries(self):
        return ()


class DeviceBatchRasterSource:
    """One visual scene driven by named public device body poses.

    It owns renderer fields and optional window only; physics stays with the
    supplied runtime. The visual asset table is constructed from the verified
    MJCF or USD source, and transforms are remapped by declared body names.
    """

    frame_transport = 'device_rgb8'

    def __init__(self, *, runtime, source, body_names=None, frame_names=None, cameras=()):
        self.runtime, self.source = runtime, source
        self._published_body_names = None if body_names is None else tuple(body_names)
        self._published_frame_names = None if frame_names is None else tuple(frame_names)
        self._cameras = tuple(cameras)
        if len({camera.name for camera in self._cameras}) != len(self._cameras):
            raise ValueError('device camera names must be unique')
        if any(not camera.rgb or camera.depth or camera.rgb_layout != 'HWC' or camera.rgb_dtype != 'uint8'
               for camera in self._cameras):
            raise ValueError('device cameras require RGB-only uint8 HWC output')
        self._visualizer = self._pose_source = self._window = None
        self._canvas = None
        self._world_ids = self._world_transforms = None
        self._body_order = None
        self._source_lease = None
        self._closed = False
        self._window_closed_by_user = False

    def _configure_visualizer(self, scene_source):
        """Bind cameras and retain renderer ownership if setup cleanup fails."""
        try:
            position, look_at, up = scene_source.compute_default_camera()
            self._visualizer.set_camera_pose(position, look_at, up)
            for camera in self._cameras:
                self._visualizer.bind_task_camera(camera_id=camera.name, position=position,
                    look_at=look_at, up=up, fov_degrees=np.degrees(camera.fov_y),
                    near=camera.near, far=camera.far, width=camera.width, height=camera.height)
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f'visualizer cleanup also failed: {cleanup_error!r}')
            raise

    def _build(self, world_ids, transforms, width, height):
        try:
            self._build_owned(world_ids, transforms, width, height)
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f'device renderer cleanup also failed: {cleanup_error!r}')
            raise

    def _build_owned(self, world_ids, transforms, width, height):
        import torch
        import taichi as ti
        from scene import SceneSource, import_scene_source
        from ...assembly.source import UsdTaskSceneSourceV1
        from visualization.scene_source import SceneVisualizationSource
        from ..providers.parallel_source import _replicate_render_scene_for_parallel
        from ...runtime.provider_bootstrap import init_task_env_backend

        init_task_env_backend('cuda', device_memory_GB=1.0, offline_cache=False)
        task_source = self.source.scene_source
        if isinstance(task_source, UsdTaskSceneSourceV1):
            self._source_lease = task_source.acquire_snapshot()
            entry = self._source_lease.root / task_source.loaded_delivery.delivery.entry_file
            imported = import_scene_source(SceneSource.usd_path(str(entry)), cache=False)
        else:
            imported = import_scene_source(SceneSource.mjcf_string(
                task_source.xml, base_dir=task_source.base_dir,
                label=self.source.source_id), cache=False)
        model = imported.build_rigid_scene_model()
        objects = tuple(model.objects)
        if not objects or tuple(int(obj.object_id) for obj in objects) != tuple(range(len(objects))):
            raise ValueError('render scene requires consecutive public body IDs')
        published = (self._published_body_names if self._published_body_names is not None else
                     tuple(self.runtime.resource_summary()['device_transition']['body_names']))
        publication_indices = {name: index for index, name in enumerate(published)}
        articulation_roots = {item.entity_id: item.root_frame_id
                              for item in self.source.scene_definition.articulations}
        native_mapping = {}
        for semantic, native in self.source.bodies.items():
            canonical = semantic
            if (semantic not in publication_indices and '/' not in semantic
                    and semantic in articulation_roots):
                canonical = f'{semantic}/{articulation_roots[semantic]}'
                if canonical not in publication_indices:
                    matches = [name for name in published if name.startswith(semantic + '/')]
                    if len(matches) == 1:
                        canonical = matches[0]
            # USD body bindings are entry-relative paths; the shared MJCF
            # visual source identifies those bodies by their source leaf name.
            # Reject ambiguous leaves rather than silently choosing a row.
            native_key = native.rsplit('/', 1)[-1]
            value = (publication_indices.get(canonical), semantic)
            if native_key in native_mapping and native_mapping[native_key] != value:
                raise ValueError(f'render source body name is ambiguous: {native_key!r}')
            native_mapping[native_key] = value
        order, static_position, static_orientation, static_mask = [], [], [], []
        joint_data = model.joint_data
        for obj in objects:
            index, semantic = native_mapping.get(obj.object_key, (None, None))
            if index is None and semantic is None:
                matches = [(i, name) for name, i in publication_indices.items()
                           if name.rsplit('/', 1)[-1] == obj.object_key]
                if len(matches) > 1:
                    raise ValueError(f'render source body name is ambiguous: {obj.object_key!r}')
                if matches:
                    index, semantic = matches[0]
            if index is None:
                entity = None if semantic is None else semantic.split('/')[0]
                if (entity in articulation_roots
                        or int(joint_data['body_parentid'][obj.object_id]) != -1
                        or int(joint_data['body_jntnum'][obj.object_id]) != 0):
                    raise ValueError(f'render body has no public device pose: {obj.object_key!r}')
                static_mask.append(True)
                static_position.append(joint_data['body_pos'][obj.object_id])
                static_orientation.append(joint_data['body_quat'][obj.object_id])
                order.append(0)
            else:
                static_mask.append(False)
                static_position.append((0., 0., 0.))
                static_orientation.append((1., 0., 0., 0.))
                order.append(index)
        scene = imported.build_render_scene_desc(scene_model=model)
        scene = _replicate_render_scene_for_parallel(scene, render_num=len(world_ids),
                                                      base_body_count=len(objects))
        translations = np.asarray([[transform[3], transform[7], transform[11]]
                                   for transform in transforms], dtype=np.float32)
        lower = translations.min(axis=0) - np.array([1., 1., 1.], dtype=np.float32)
        upper = translations.max(axis=0) + np.array([1., 1., 1.], dtype=np.float32)
        poses = _RigidPoseSource(len(world_ids) * len(objects), lower=lower, upper=upper)
        scene_source = SceneVisualizationSource.from_render_scene(scene, geometry_sources=(poses,))
        capacity = (max([width, *(camera.width for camera in self._cameras)]),
                    max([height, *(camera.height for camera in self._cameras)]))
        visualizer = scene_source.build_visualizer(
            backend='rasterizer', use_render_snapshot=False, width=width, height=height,
            max_framebuffer_resolution=capacity, enable_shadow=False,
            enable_ssao=False, enable_fxaa=False, enable_taa=False, raster_acceleration='compute')
        self._pose_source, self._visualizer = poses, visualizer
        self._configure_visualizer(scene_source)
        self._world_ids, self._world_transforms = tuple(world_ids), tuple(transforms)
        self._width, self._height = width, height
        self._body_order = torch.tensor(order, dtype=torch.int64, device='cuda')
        self._static_mask = torch.tensor(static_mask, dtype=torch.bool, device='cuda')[None, :, None]
        self._static_position = torch.tensor(np.asarray(static_position), dtype=torch.float32, device='cuda')[None, :, :]
        self._static_orientation = torch.tensor(np.asarray(static_orientation), dtype=torch.float32, device='cuda')[None, :, :]
        self._translation = torch.tensor(translations, dtype=torch.float32, device='cuda')
        self._ti = ti
        if self._cameras:
            try:
                from ...assembly.references import SceneNameTable, TaskReferences
                from ...observations.camera import CameraSensor

                frame_names = self._published_frame_names
                if frame_names is None:
                    frame_names = (tuple(self.runtime.resource_summary()['device_transition'].get('frame_names', ()))
                                   if any(camera.frame == 'site' for camera in self._cameras) else ())
                names = SceneNameTable(bodies=publication_indices, joints={},
                                       sites={name: index for index, name in enumerate(frame_names)},
                                       geoms={}, actuators={})
                references = TaskReferences(names, {}, {})
                self._camera_sensors = tuple(CameraSensor(spec=spec, references=references)
                                             for spec in self._cameras)
            except BaseException as error:
                try:
                    self.close()
                except BaseException as cleanup_error:
                    error.add_note(f'device renderer cleanup also failed: {cleanup_error!r}')
                raise

    def render_parallel(self, *, world_ids, world_transforms, snapshot, width, height):
        import torch

        del snapshot
        if self._closed:
            raise RuntimeError('device raster source is closed')
        if self._visualizer is None:
            self._build(world_ids, world_transforms, width, height)
        if (tuple(world_ids), tuple(world_transforms)) != (self._world_ids, self._world_transforms):
            raise ValueError('device raster layout is fixed for the renderer lifetime')
        state = self.runtime.read_device_state(('body_position', 'body_orientation'))
        self._publish_pose(state, world_ids)
        result = torch.empty((height, width, 3), dtype=torch.uint8, device=state.device)
        self._visualizer.write_frame_rgb8(result)
        return result

    def _publish_pose(self, state, world_ids):
        import torch

        selected = torch.tensor(world_ids, dtype=torch.int64, device=state.device)
        positions = state.arrays['body_position'].index_select(0, selected).index_select(1, self._body_order)
        orientations = state.arrays['body_orientation'].index_select(0, selected).index_select(1, self._body_order)
        positions = torch.where(self._static_mask, self._static_position, positions)
        orientations = torch.where(self._static_mask, self._static_orientation, orientations)
        positions = (positions + self._translation[:, None, :]).reshape(-1, 3).contiguous()
        orientations = orientations.reshape(-1, 4).contiguous()
        torch.cuda.current_stream(positions.device).synchronize()
        from .pose_transfer import copy_pose_fields
        copy_pose_fields(positions, orientations, self._pose_source.body_positions,
                         self._pose_source.body_orientations)

    def capture_cameras(self, *, state, world_ids, world_transforms, width, height):
        """Capture configured sensor cameras for each selected device world."""
        import torch

        if not self._cameras:
            return {}
        if self._closed:
            raise RuntimeError('device raster source is closed')
        if self._visualizer is None:
            self._build(world_ids, world_transforms, width, height)
        if (tuple(world_ids), tuple(world_transforms)) != (self._world_ids, self._world_transforms):
            raise ValueError('device raster layout is fixed for the renderer lifetime')
        fields = ('body_position', 'body_orientation')
        if any(camera.frame == 'site' for camera in self._cameras):
            fields += ('frame_position', 'frame_orientation')
        poses = self.runtime.read_device_state(fields)
        if poses.identity != state.identity:
            raise RuntimeError('camera poses do not match the observation boundary')
        self._publish_pose(poses, world_ids)
        from ...runtime.contracts import DeviceBatchState
        selected = torch.tensor(world_ids, dtype=torch.int64, device=poses.device)
        camera_poses = DeviceBatchState(
            {name: value.index_select(0, selected) for name, value in poses.arrays.items()},
            poses.device, len(world_ids), poses.identity, 'owned_snapshot')
        result = {}
        for sensor in self._camera_sensors:
            camera = sensor.spec
            device_poses = sensor.resolve_device_pose(camera_poses, world_offsets=self._translation)
            frames = torch.empty((len(world_ids), camera.height, camera.width, 3),
                                 dtype=torch.uint8, device=poses.device)
            for index in range(len(world_ids)):
                self._visualizer.update_task_camera_pose_from_device(
                    camera_id=camera.name, pose=device_poses[index].contiguous())
                self._visualizer.write_task_camera_rgb8(frames[index], camera_id=camera.name)
            result[camera.name] = {'rgb': frames}
        return result

    def present_parallel(self, *, frame, world_ids, world_transforms):
        del frame, world_ids, world_transforms
        if self._window_closed_by_user:
            return
        if self._visualizer is None:
            raise RuntimeError('device raster has not rendered a frame')
        if self._window is None:
            self._window = self._ti.ui.Window('GeoChora', (self._width, self._height), vsync=False)
            self._canvas = self._window.get_canvas()
        if not self._window.running:
            self.close_window()
            return
        self._visualizer.present_current_frame(self._canvas)
        self._window.show()

    def close_window(self):
        """Release the optional window without closing sensor rendering."""
        self._window_closed_by_user = True
        if self._window is not None:
            self._window.destroy()
            self._window = self._canvas = None

    def close(self):
        if self._closed:
            return
        error = None
        if self._window is not None:
            try:
                self.close_window()
            except BaseException as caught:
                error = caught
        if self._visualizer is not None:
            try:
                self._visualizer.close()
                self._visualizer = None
            except BaseException as caught:
                if error is None:
                    error = caught
                else:
                    error.add_note(f'visualizer cleanup also failed: {caught!r}')
        if self._source_lease is not None and self._visualizer is None:
            try:
                self._source_lease.close()
                self._source_lease = None
            except BaseException as caught:
                if error is None:
                    error = caught
                else:
                    error.add_note(f'USD visual source cleanup also failed: {caught!r}')
        if error is not None:
            raise error
        self._pose_source = self._body_order = self._translation = None
        self._static_mask = self._static_position = self._static_orientation = None
        self._closed = True
