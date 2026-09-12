"""TaskEnv-owned RayTracer visualizer extensions.

The low-level GeoPhys RayTracer remains the renderer implementation.  This
module owns the TaskEnv-specific lowering rule used by hard parallel render:
one canonical rigid mesh payload may be referenced by many body transforms.
Keeping that policy here prevents the TaskEnv asset contract from becoming a
public ``src.visualization`` scene-source requirement.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from visualization.raytracer.scene_visualizer import (
    SceneVisualizer as _GeoPhysRaytracerSceneVisualizer,
)
from visualization.materials import (
    RayMaterialFlags,
    triangle_material_arrays_from_surface,
)
from visualization.rigid_transform_provider import (
    RigidRenderTransformBinding,
    resolve_rigid_render_transform_binding,
)


class RaytracerSceneVisualizer(_GeoPhysRaytracerSceneVisualizer):
    """RayTracer visualizer with TaskEnv shared-asset lowering."""

    @staticmethod
    def _shared_asset_budget_topology(
        render_scene,
        *,
        backend: str,
        material_flags=None,
        mpm_source=None,
    ):
        """Estimate shared geometry once while retaining instance metadata."""

        from visualization.render_budget import topology_from_render_scene
        from visualization.render_scene import RenderMeshPayload
        from visualization.render_source import RenderRepresentation

        baseline = topology_from_render_scene(
            render_scene,
            backend=backend,
            material_flags=material_flags,
            mpm_source=mpm_source,
        )
        mesh_instances = render_scene.selected_instances(RenderRepresentation.MESH)
        seen_asset_materials: set[tuple[str, str]] = set()
        seen_materials: set[str] = set()
        vertices = 0
        triangles = 0
        texture_bytes = 0
        for instance in mesh_instances:
            asset_id = str(getattr(instance, "asset_id", ""))
            material_id = str(getattr(instance, "material_id", ""))
            identity = (asset_id, material_id)
            if identity not in seen_asset_materials:
                seen_asset_materials.add(identity)
                asset = render_scene.asset_table.get(instance.asset_id)
                payload = asset.payload
                if isinstance(payload, RenderMeshPayload):
                    vertices += int(
                        np.asarray(payload.vertices).reshape(-1, 3).shape[0]
                    )
                    triangles += int(
                        np.asarray(payload.indices).reshape(-1, 3).shape[0]
                    )
            if material_id and material_id not in seen_materials:
                seen_materials.add(material_id)
                material = render_scene.material_table.get(instance.material_id)
                for value in material.runtime_payload.values():
                    if isinstance(value, np.ndarray):
                        texture_bytes += int(value.nbytes)
        return replace(
            baseline,
            mesh_instances=len(mesh_instances),
            mesh_vertices=vertices,
            mesh_triangles=triangles,
            texture_bytes=texture_bytes,
        )

    def _apply_render_budget_plan(
        self,
        render_scene,
        *,
        backend: str,
        material_flags=None,
    ):
        """Use the RayTracer shared-asset topology for preflight budgeting."""

        from visualization.render_budget import plan_render_budget

        if self._render_config is None:
            return None
        topology = self._shared_asset_budget_topology(
            render_scene,
            backend=backend,
            material_flags=material_flags,
            mpm_source=getattr(self.source, "mpm_source", None),
        )
        config, plan = plan_render_budget(self._render_config, topology)
        self._render_config = config
        self._render_budget_plan = plan
        self._initial_width = int(config.effective_resolution[0])
        self._initial_height = int(config.effective_resolution[1])
        self._max_framebuffer_resolution = tuple(config.max_resolution)
        return config

    @classmethod
    def _append_surface_geometries_as_meshes(
        cls,
        all_mesh_data,
        surface_geos,
        rigid_source,
        material_flags: RayMaterialFlags | None = None,
        transform_binding: RigidRenderTransformBinding | None = None,
    ):
        """Lower rigid visual parts into one mesh table plus instance records.

        ``surface_geos`` contains one record per selected world/body/link.  A
        canonical local geometry is appended to ``all_mesh_data`` once; every
        selected body still receives its own ``rigid_entries`` record and
        therefore its own TLAS transform.  Asset identity is checked against
        the local geometry, not just a token, so a stale or malformed token
        cannot silently alias unrelated meshes.
        """

        from utils.math import quaternion_to_matrix

        dynamic_geos = [
            surface
            for surface in surface_geos
            if int(getattr(surface, "body_id", -1)) >= 0
        ]
        static_geos = [
            surface
            for surface in surface_geos
            if int(getattr(surface, "body_id", -1)) < 0
        ]
        ordered_geos = dynamic_geos + static_geos
        if not ordered_geos:
            return []

        vert_offset = sum(
            int(np.asarray(mesh["vertices"]).shape[0])
            for mesh in all_mesh_data
        )
        transform_binding = transform_binding or resolve_rigid_render_transform_binding(
            rigid_source
        )
        if dynamic_geos and transform_binding is None:
            raise ValueError(
                "dynamic rigid mesh rendering requires a transform provider"
            )
        pose_positions = (
            transform_binding.positions if transform_binding is not None else None
        )
        pose_orientations = (
            transform_binding.orientations
            if transform_binding is not None
            else None
        )
        read_slot = 0
        if (
            transform_binding is not None
            and transform_binding.slot_indexed
            and transform_binding.snapshot_read_slot is not None
        ):
            read_slot = int(transform_binding.snapshot_read_slot[None])
        world_major = bool(
            transform_binding is not None and transform_binding.world_major
        )
        init_pos = (
            cls._pose_field_numpy(
                pose_positions,
                read_slot,
                world_major=world_major,
            )
            if dynamic_geos
            else None
        )
        init_quat = (
            cls._pose_field_numpy(
                pose_orientations,
                read_slot,
                world_major=world_major,
            )
            if dynamic_geos
            else None
        )
        texture_cache: dict[str, np.ndarray] = {}
        shared_mesh_cache: dict[
            tuple[str, str, int, int],
            list[tuple[int, int, np.ndarray, np.ndarray]],
        ] = {}
        rigid_entries = []

        for surface in ordered_geos:
            body_id = int(getattr(surface, "body_id", -1))
            local_vertices = np.asarray(surface.vertices, dtype=np.float32)
            indices = np.asarray(surface.indices, dtype=np.int32).reshape(-1, 3)
            vertex_count = int(local_vertices.shape[0])
            asset_token = str(getattr(surface, "mesh_asset_key", "")).strip()

            # Do the identity lookup before material/texture lowering.  A
            # repeated world instance contributes only a transform record;
            # it must not rebuild the CPU material arrays for the same asset.
            canonical = None
            cache_key = None
            if body_id >= 0:
                material_key = str(
                    getattr(surface, "material_key", "")
                ).strip()
                cache_key = (
                    asset_token,
                    material_key,
                    vertex_count,
                    int(indices.shape[0]),
                )
                for candidate in shared_mesh_cache.get(cache_key, ()):
                    (
                        candidate_start,
                        candidate_count,
                        candidate_vertices,
                        candidate_indices,
                    ) = candidate
                    if candidate_count != vertex_count:
                        continue
                    same_vertices = (
                        candidate_vertices is local_vertices
                        or np.array_equal(candidate_vertices, local_vertices)
                    )
                    same_indices = (
                        candidate_indices is indices
                        or np.shares_memory(candidate_indices, indices)
                        or np.array_equal(candidate_indices, indices)
                    )
                    if same_vertices and same_indices:
                        canonical = candidate
                        break
                if canonical is not None:
                    rigid_entries.append(
                        (
                            body_id,
                            int(canonical[0]),
                            vertex_count,
                            local_vertices,
                            asset_token,
                            str(getattr(surface, "render_instance_id", "")),
                        )
                    )
                    continue

            normals = (
                np.asarray(surface.normals, dtype=np.float32)
                if getattr(surface, "normals", None) is not None
                else None
            )

            world_vertices = local_vertices
            world_normals = normals
            if body_id >= 0:
                rotation = quaternion_to_matrix(init_quat[body_id])
                world_vertices = (
                    init_pos[body_id]
                    + (rotation @ local_vertices.T).T
                ).astype(np.float32)
                if normals is not None:
                    world_normals = (rotation @ normals.T).T.astype(np.float32)

            material_arrays = triangle_material_arrays_from_surface(
                surface,
                indices,
                vertex_count,
            )
            mesh_entry = {
                "vertices": world_vertices.astype(np.float32),
                "indices": indices,
                "normals": (
                    world_normals.astype(np.float32)
                    if world_normals is not None
                    else None
                ),
                "colors": material_arrays.colors,
                "roughness": material_arrays.roughness,
                "metallic": material_arrays.metallic,
                "specular": material_arrays.specular,
                "alpha": material_arrays.alpha,
                "emission": material_arrays.emission,
                "alpha_modes": material_arrays.alpha_modes,
                "alpha_cutoffs": material_arrays.alpha_cutoffs,
                "base_color_texture_srgb": (
                    material_arrays.base_color_texture_srgb
                ),
                "deformation_binding": getattr(
                    surface,
                    "deformation_binding",
                    None,
                ),
                "__render_instance_id": str(
                    getattr(surface, "render_instance_id", "")
                ),
                "__render_entity_id": str(
                    getattr(surface, "render_entity_id", "")
                ),
                "__source_kind": str(getattr(surface, "source_kind", "")),
                "__body_id": body_id,
            }
            mesh_entry.update(
                cls._surface_texture_payload(
                    surface,
                    indices.shape[0],
                    material_flags,
                    texture_cache,
                )
            )

            if body_id >= 0:
                canonical = (
                    int(vert_offset),
                    vertex_count,
                    local_vertices,
                    indices,
                )
                shared_mesh_cache.setdefault(cache_key, []).append(canonical)
                all_mesh_data.append(mesh_entry)
                vert_offset += vertex_count
                rigid_entries.append(
                    (
                        body_id,
                        int(canonical[0]),
                        vertex_count,
                        local_vertices,
                        asset_token,
                        str(getattr(surface, "render_instance_id", "")),
                    )
                )
                continue

            all_mesh_data.append(mesh_entry)
            vert_offset += vertex_count

        return rigid_entries


__all__ = ["RaytracerSceneVisualizer"]
