"""Build Flora SceneFile bundles from public render descriptions.

This module is deliberately an offline asset-preparation boundary.  It does
not import Flora during normal TaskEnv imports and it does not put mesh data
in the simulation kernels.  The live backend consumes ``RenderSceneDesc`` or
``RenderAssemblyDesc``; the generic MJCF helper is retained only for explicit
offline diagnostics and is not called by the live backend.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Any, Mapping, Sequence

import numpy as np

from visualization.assembly import RenderAssemblyDesc, RenderPartDesc

from .transforms import matrix_to_flora_scene_fields, pose_matrix


_MATERIAL_RGBA: dict[str, tuple[float, float, float, float]] = {
    "metal": (0.9, 0.95, 0.95, 1.0),
    "black": (0.0, 0.0, 0.0, 1.0),
    "white": (1.0, 1.0, 1.0, 1.0),
    "gray": (0.671705, 0.692426, 0.774270, 1.0),
}

@dataclass(frozen=True)
class FloraSceneBundle:
    """Paths and counts for one generated Flora SceneFile bundle."""

    scene_path: Path
    model_paths: tuple[Path, ...]
    body_node_names: tuple[str, ...]
    visual_node_count: int
    mesh_geom_count: int
    instance_count: int = 1

    def describe(self) -> dict[str, object]:
        return {
            "schema": "task_env.go2_flora_bundle.v1",
            "scene_path": str(self.scene_path),
            "model_paths": [str(path) for path in self.model_paths],
            "unique_model_count": len(self.model_paths),
            "body_node_count": len(self.body_node_names),
            "visual_node_count": int(self.visual_node_count),
            "mesh_geom_count": int(self.mesh_geom_count),
            "instance_count": int(self.instance_count),
        }


def _vector(value: str | None, size: int, *, default: tuple[float, ...]) -> tuple[float, ...]:
    if value is None:
        return default
    result = tuple(float(item) for item in value.split())
    if len(result) != size:
        raise ValueError(f"expected {size} values, got {len(result)} in {value!r}")
    return result


def _quat_xyzw(value: str | None) -> tuple[float, float, float, float]:
    """Convert MuJoCo WXYZ quaternions to Flora's XYZW convention."""

    w, x, y, z = _vector(value, 4, default=(1.0, 0.0, 0.0, 0.0))
    norm = (w * w + x * x + y * y + z * z) ** 0.5
    if norm <= 1.0e-12:
        raise ValueError("MJCF quaternion must be non-zero")
    return (x / norm, y / norm, z / norm, w / norm)


def _mesh_name(mesh: ET.Element) -> str:
    file_name = mesh.get("file")
    if not file_name:
        raise ValueError("MJCF mesh is missing its file attribute")
    return str(mesh.get("name") or Path(file_name).stem)


def _load_obj_as_glb(obj_path: Path, output_path: Path, material_name: str) -> None:
    try:
        import trimesh
        from trimesh.visual.material import PBRMaterial
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise RuntimeError(
            "Flora OBJ asset conversion requires the 'trimesh' package"
        ) from exc

    loaded = trimesh.load_mesh(obj_path, file_type="obj", process=False)
    if isinstance(loaded, trimesh.Scene):
        geometries = tuple(loaded.geometry.values())
        if not geometries:
            raise ValueError(f"OBJ contains no geometry: {obj_path}")
        mesh = trimesh.util.concatenate(geometries)
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        raise TypeError(f"unsupported OBJ result {type(loaded)!r}: {obj_path}")

    rgba = _MATERIAL_RGBA[material_name]
    mesh.visual = trimesh.visual.TextureVisuals(
        material=PBRMaterial(
            name=f"go2_{material_name}",
            baseColorFactor=rgba,
            metallicFactor=0.75 if material_name == "metal" else 0.0,
            roughnessFactor=0.42 if material_name == "metal" else 0.72,
            doubleSided=True,
        )
    )
    # Donut's mesh material path requires an authored NORMAL attribute for
    # lit GLB output.  Replacing ``mesh.visual`` above can otherwise make
    # trimesh omit the computed normals even though the source OBJ is valid.
    mesh.vertex_normals = np.ascontiguousarray(mesh.vertex_normals, dtype=np.float32)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(output_path, file_type="glb")


def _load_render_mesh_as_glb(
    payload: object,
    output_path: Path,
    material: object,
) -> None:
    """Serialize a public ``RenderMeshPayload`` to one Flora model.

    This is the live backend path.  It consumes the already compiled render
    description and therefore does not reopen MJCF/URDF files or infer robot
    semantics in ``task_env/render``.
    """

    try:
        import trimesh
        from trimesh.visual.material import PBRMaterial
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise RuntimeError(
            "Flora render-scene lowering requires the 'trimesh' package"
        ) from exc

    vertices = np.ascontiguousarray(
        np.asarray(getattr(payload, "vertices"), dtype=np.float32).reshape(-1, 3)
    )
    indices = np.ascontiguousarray(
        np.asarray(getattr(payload, "indices"), dtype=np.int64).reshape(-1, 3)
    )
    if vertices.size == 0 or indices.size == 0:
        raise ValueError("Flora RenderMeshPayload must contain vertices and triangles")
    mesh = trimesh.Trimesh(vertices=vertices, faces=indices, process=False)
    normals = getattr(payload, "normals", None)
    if normals is not None:
        normals = np.ascontiguousarray(
            np.asarray(normals, dtype=np.float32).reshape(-1, 3)
        )
        if normals.shape == vertices.shape:
            mesh.vertex_normals = normals

    base_color = tuple(
        float(value)
        for value in getattr(material, "base_color", (0.72, 0.74, 0.76, 1.0))
    )
    pbr = PBRMaterial(
        name=str(getattr(material, "material_id", "flora_material")),
        baseColorFactor=base_color,
        metallicFactor=float(getattr(material, "metallic", 0.0)),
        roughnessFactor=float(getattr(material, "roughness", 0.72)),
        doubleSided=True,
    )
    uvs = getattr(payload, "uvs", None)
    if uvs is not None:
        uvs = np.ascontiguousarray(np.asarray(uvs, dtype=np.float32).reshape(-1, 2))
    if uvs is not None and uvs.shape[0] == vertices.shape[0]:
        mesh.visual = trimesh.visual.TextureVisuals(uv=uvs, material=pbr)
    else:
        mesh.visual = trimesh.visual.TextureVisuals(material=pbr)
    # Keep the explicit NORMAL accessor after replacing visual attributes.
    mesh.vertex_normals = np.ascontiguousarray(mesh.vertex_normals, dtype=np.float32)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(output_path, file_type="glb")


def _load_checker_floor_as_glb(
    output_path: Path,
    *,
    half_extent: float,
    tile_size: float,
) -> None:
    """Build one shared Flora-native checkerboard floor.

    Flora's native scene coordinates are Y-up.  The body/camera adapters keep
    the public GeoPhys Z-up contract, so this static model is authored directly
    in Flora coordinates: ``(x, y=0, z)``.  The two colors are two disconnected
    meshes inside one GLB.  This avoids depending on native texture-repeat
    behavior while keeping the floor to one shared SceneFile model.
    """

    try:
        import trimesh
        from trimesh.visual.material import PBRMaterial
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise RuntimeError(
            "Flora checker-floor generation requires trimesh"
        ) from exc

    extent = float(half_extent)
    size = float(tile_size)
    if not np.isfinite(extent) or extent <= 0.0:
        raise ValueError("Flora checker floor half_extent must be finite and positive")
    if not np.isfinite(size) or size <= 0.0:
        raise ValueError("Flora checker floor tile_size must be finite and positive")

    tile_count = max(1, int(np.ceil(2.0 * extent / size)))

    def build_color_mesh(name: str, color: tuple[float, float, float]):
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        parity = 0 if name == "dark" else 1
        for ix in range(tile_count):
            x0 = -extent + ix * size
            x1 = min(extent, x0 + size)
            for iz in range(tile_count):
                if (ix + iz) % 2 != parity:
                    continue
                z0 = -extent + iz * size
                z1 = min(extent, z0 + size)
                start = len(vertices)
                vertices.extend(
                    (
                        (x0, 0.0, z0),
                        (x1, 0.0, z0),
                        (x1, 0.0, z1),
                        (x0, 0.0, z1),
                    )
                )
                # Winding gives the floor an upward Flora-native normal.
                faces.extend(
                    ((start, start + 2, start + 1), (start, start + 3, start + 2))
                )
        mesh = trimesh.Trimesh(
            vertices=np.asarray(vertices, dtype=np.float32),
            faces=np.asarray(faces, dtype=np.int64),
            process=False,
        )
        mesh.visual = trimesh.visual.TextureVisuals(
            material=PBRMaterial(
                name=f"geophys_checker_floor_{name}",
                baseColorFactor=(*color, 1.0),
                metallicFactor=0.0,
                roughnessFactor=0.88,
                doubleSided=True,
            ),
        )
        mesh.vertex_normals = np.tile(
            np.asarray((0.0, 1.0, 0.0), dtype=np.float32),
            (len(vertices), 1),
        )
        return mesh

    # Match the neutral hard-render floor palette while retaining enough
    # contrast after Flora's PBR lighting pass.
    floor_scene = trimesh.Scene(
        {
            "dark": build_color_mesh("dark", (0.18, 0.20, 0.22)),
            "light": build_color_mesh("light", (0.30, 0.32, 0.34)),
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    floor_scene.export(output_path, file_type="glb")


def _append_checker_floor_model(
    *,
    model_dir: Path,
    model_paths: list[Path],
    force: bool,
    half_extent: float,
    tile_size: float,
) -> int:
    """Create/reuse one checker-floor model and return its model-table index."""

    extent_tag = f"{float(half_extent):g}".replace(".", "p")
    tile_tag = f"{float(tile_size):g}".replace(".", "p")
    target = model_dir / f"flora_checker_floor_v2_e{extent_tag}_t{tile_tag}.glb"
    if force or not target.is_file() or not _glb_contains_vertex_normals(target):
        _load_checker_floor_as_glb(
            target,
            half_extent=half_extent,
            tile_size=tile_size,
        )
    model_index = len(model_paths)
    model_paths.append(target)
    return model_index


def _glb_contains_vertex_normals(path: Path) -> bool:
    """Return whether a cached GLB contains a NORMAL vertex attribute."""

    try:
        payload = path.read_bytes()
        if len(payload) < 20 or payload[:4] != b"glTF":
            return False
        json_length = int.from_bytes(payload[12:16], byteorder="little")
        json_chunk = payload[20 : 20 + json_length]
        document = json.loads(json_chunk.rstrip(b" \t\r\n\x00"))
        return any(
            "NORMAL" in primitive.get("attributes", {})
            for mesh in document.get("meshes", ())
            for primitive in mesh.get("primitives", ())
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _material_by_mesh(root: ET.Element) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for geom in root.findall(".//geom"):
        mesh = geom.get("mesh")
        if not mesh:
            continue
        material = str(geom.get("material") or "")
        if material not in _MATERIAL_RGBA:
            raise ValueError(
                f"MJCF mesh {mesh!r} uses unsupported material {material!r}"
            )
        previous = mapping.setdefault(mesh, material)
        if previous != material:
            raise ValueError(
                f"MJCF mesh {mesh!r} is used with multiple materials: "
                f"{previous!r} and {material!r}"
            )
    return mapping


def _body_records(
    worldbody: ET.Element,
):
    records: list[tuple[str, Any, list[tuple[int, str, tuple[float, ...], tuple[float, ...]]]]] = []

    def visit(
        body: ET.Element,
        parent_matrix,
    ) -> None:
        body_name = str(body.get("name") or "unnamed_body")
        local_matrix = pose_matrix(
            _vector(body.get("pos"), 3, default=(0.0, 0.0, 0.0)),
            _vector(body.get("quat"), 4, default=(1.0, 0.0, 0.0, 0.0)),
        )
        world_matrix = parent_matrix @ local_matrix
        visuals: list[tuple[int, str, tuple[float, ...], tuple[float, ...]]] = []

        for geom_index, geom in enumerate(body.findall("geom")):
            mesh_name = geom.get("mesh")
            if not mesh_name:
                continue
            visuals.append(
                (
                    geom_index,
                    str(mesh_name),
                    _vector(geom.get("pos"), 3, default=(0.0, 0.0, 0.0)),
                    _vector(geom.get("quat"), 4, default=(1.0, 0.0, 0.0, 0.0)),
                )
            )

        if visuals:
            records.append(
                (
                    body_name,
                    world_matrix,
                    visuals,
                )
            )
        for child in body.findall("body"):
            visit(child, world_matrix)

    identity = pose_matrix((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    for body in worldbody.findall("body"):
        visit(body, identity)
    return records


def _scene_graph(
    worldbody: ET.Element,
    mesh_indices: dict[str, int],
    *,
    instance_count: int,
    body_node_names: list[str],
    body_order: Sequence[str] = (),
) -> tuple[list[dict[str, Any]], int, int]:
    records = _body_records(worldbody)
    record_by_name = {record[0]: record for record in records}
    ordered_records = [
        record_by_name[name]
        for name in body_order
        if name in record_by_name
    ]
    ordered_records.extend(
        record
        for record in records
        if record[0] not in set(body_order)
    )
    graph: list[dict[str, Any]] = []
    visual_count = 0
    mesh_geom_count = 0
    for instance_id in range(int(instance_count)):
        env_name = f"env_{instance_id:04d}"
        env_children: list[dict[str, Any]] = []
        for body_name, world_matrix, visuals in ordered_records:
            body_node_name = f"{env_name}__body__{body_name}"
            body_node_names.append(body_node_name)
            body_translation, body_rotation, body_scale = matrix_to_flora_scene_fields(
                world_matrix
            )
            body_node: dict[str, Any] = {
                "name": body_node_name,
                "translation": body_translation,
                "rotation": body_rotation,
                "scaling": body_scale,
            }
            children: list[dict[str, Any]] = []
            for geom_index, mesh_name, position, quat in visuals:
                if mesh_name not in mesh_indices:
                    raise KeyError(f"visual geom references unknown mesh {mesh_name!r}")
                visual_translation, visual_rotation, visual_scale = matrix_to_flora_scene_fields(
                    pose_matrix(position, quat)
                )
                children.append(
                    {
                        "name": f"{body_node_name}__visual_{geom_index}_{mesh_name}",
                        "model": mesh_indices[mesh_name],
                        "translation": visual_translation,
                        "rotation": visual_rotation,
                        "scaling": visual_scale,
                    }
                )
                visual_count += 1
                mesh_geom_count += 1
            if children:
                body_node["children"] = children
            env_children.append(body_node)
        graph.append({"name": env_name, "children": env_children})
    return graph, visual_count, mesh_geom_count


def build_scene_file_from_mjcf(
    *,
    output_dir: str | Path,
    mjcf_path: str | Path,
    asset_root: str | Path,
    instance_count: int = 1,
    body_order: Sequence[str] = (),
    scene_name: str = "scene",
    force: bool = False,
) -> FloraSceneBundle:
    """Convert an explicit MJCF asset bundle to one Flora SceneFile.

    ``force=False`` still rewrites only missing/incomplete artifacts.  The
    function is intended for deterministic offline preparation, not for a
    per-frame render path.  Robot-specific paths and ordering are supplied by
    the task/robot adapter rather than stored in this module.
    """

    output = Path(output_dir).resolve()
    mjcf = Path(mjcf_path).resolve()
    assets = Path(asset_root).resolve()
    if isinstance(instance_count, bool) or int(instance_count) < 1:
        raise ValueError("instance_count must be a positive integer")
    if not mjcf.is_file():
        raise FileNotFoundError(f"MJCF was not found: {mjcf}")
    if not assets.is_dir():
        raise FileNotFoundError(f"MJCF asset directory was not found: {assets}")

    root = ET.parse(mjcf).getroot()
    asset_section = root.find("asset")
    worldbody = root.find("worldbody")
    if asset_section is None or worldbody is None:
        raise ValueError("MJCF must contain asset and worldbody sections")

    mesh_files: dict[str, Path] = {}
    for mesh in asset_section.findall("mesh"):
        name = _mesh_name(mesh)
        file_name = mesh.get("file")
        assert file_name is not None
        source = (assets / file_name).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"MJCF mesh was not found: {source}")
        mesh_files[name] = source

    material_by_mesh = _material_by_mesh(root)
    missing_materials = sorted(set(mesh_files) - set(material_by_mesh))
    if missing_materials:
        raise ValueError(f"MJCF meshes have no visual material mapping: {missing_materials}")

    model_dir = output / "models"
    model_paths: list[Path] = []
    mesh_indices: dict[str, int] = {}
    for mesh_name, source in mesh_files.items():
        target = model_dir / f"{mesh_name}.glb"
        if force or not target.is_file() or not _glb_contains_vertex_normals(target):
            _load_obj_as_glb(source, target, material_by_mesh[mesh_name])
        mesh_indices[mesh_name] = len(model_paths)
        model_paths.append(target)

    body_node_names: list[str] = []
    graph, visual_count, mesh_geom_count = _scene_graph(
        worldbody,
        mesh_indices,
        instance_count=int(instance_count),
        body_node_names=body_node_names,
        body_order=tuple(str(name) for name in body_order),
    )
    normalized_scene_name = str(scene_name).strip() or "scene"
    scene_path = output / f"{normalized_scene_name}.scene.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_payload = {
        "models": [f"models/{path.name}" for path in model_paths],
        "graph": graph,
    }
    scene_path.write_text(
        json.dumps(scene_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return FloraSceneBundle(
        scene_path=scene_path,
        model_paths=tuple(model_paths),
        body_node_names=tuple(body_node_names),
        visual_node_count=visual_count,
        mesh_geom_count=mesh_geom_count,
        instance_count=int(instance_count),
    )


def build_scene_file_from_assemblies(
    *,
    assemblies: Sequence[RenderAssemblyDesc],
    output_path: str | Path,
    instance_count: int = 1,
    force: bool = False,
    include_checker_floor: bool = False,
    floor_half_extent: float = 128.0,
    floor_tile_size: float = 0.5,
) -> FloraSceneBundle:
    """Lower existing ``src.visualization`` assemblies to one shared SceneFile.

    Mesh assets are keyed by their resolved source path, so environment
    instances only add graph nodes.  OBJ conversion is performed once per
    unique source asset and never in a frame update.
    """

    if isinstance(instance_count, bool) or int(instance_count) < 1:
        raise ValueError("instance_count must be a positive integer")
    from ..base.contracts import RenderBackendBuildError

    output = Path(output_path).resolve()
    model_dir = output.parent / f"{output.stem}.models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_paths: list[Path] = []
    model_indices: dict[Path, int] = {}
    graph: list[dict[str, Any]] = []
    body_names: list[str] = []
    visual_count = 0

    floor_model_index: int | None = None
    if include_checker_floor:
        floor_model_index = _append_checker_floor_model(
            model_dir=model_dir,
            model_paths=model_paths,
            force=force,
            half_extent=float(floor_half_extent),
            tile_size=float(floor_tile_size),
        )

    def model_for(path_value: str | Path) -> int:
        source = Path(path_value).expanduser().resolve()
        if not source.is_file():
            raise RenderBackendBuildError(f"Flora mesh asset does not exist: {source}")
        if source not in model_indices:
            target = model_dir / f"{len(model_paths):04d}_{source.stem}.glb"
            if force or not target.is_file():
                if source.suffix.lower() == ".obj":
                    _load_obj_as_glb(source, target, "gray")
                elif source.suffix.lower() in {".glb", ".gltf"}:
                    target.write_bytes(source.read_bytes())
                else:
                    raise RenderBackendBuildError(
                        f"Flora only supports OBJ/GLB/GLTF mesh assets: {source}"
                    )
            model_indices[source] = len(model_paths)
            model_paths.append(target)
        return model_indices[source]

    def part_asset_path(
        assembly: RenderAssemblyDesc,
        part: RenderPartDesc,
    ) -> str:
        mesh_file = str(part.mesh_file or "")
        if not mesh_file and part.mesh_asset_key:
            asset = assembly.mesh_assets.get(part.mesh_asset_key)
            if asset is not None:
                mesh_file = str(asset.file or "")
        if not mesh_file:
            return ""
        candidate = Path(mesh_file).expanduser()
        if candidate.is_absolute():
            return str(candidate)
        source_path = Path(assembly.source_path).expanduser()
        base = source_path.parent if source_path.suffix else source_path
        return str((base / candidate).resolve())

    if floor_model_index is not None:
        graph.append(
            {
                "name": "flora_checker_floor",
                "model": floor_model_index,
                "translation": [0.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 0.0, 1.0],
                "scaling": [1.0, 1.0, 1.0],
            }
        )

    for instance_id in range(int(instance_count)):
        for assembly in assemblies:
            assembly_id = str(getattr(assembly, "assembly_id", "assembly"))
            root_name = f"env_{instance_id:04d}__assembly__{assembly_id}"
            body_nodes: dict[int, dict[str, Any]] = {}
            for part_index, part in enumerate(assembly.visible_parts()):
                mesh_file = part_asset_path(assembly, part)
                if not mesh_file:
                    continue
                body_id = int(getattr(part, "body_id", -1))
                if body_id not in body_nodes:
                    node_name = f"{root_name}__body__{body_id}"
                    body_names.append(node_name)
                    body_nodes[body_id] = {"name": node_name, "children": []}
                child = body_nodes[body_id]["children"]
                local_matrix = pose_matrix(part.local_pos, part.local_quat)
                local_matrix[:3, :3] = local_matrix[:3, :3] @ np.diag(
                    np.asarray(part.local_scale, dtype=np.float32)
                )
                translation, rotation, scaling = matrix_to_flora_scene_fields(
                    local_matrix
                )
                child.append(
                    {
                        "name": f"{body_nodes[body_id]['name']}__part_{part_index}",
                        "model": model_for(mesh_file),
                        "translation": translation,
                        "rotation": rotation,
                        "scaling": scaling,
                    }
                )
                visual_count += 1
            graph.append(
                {
                    "name": root_name,
                    "children": [
                        body_nodes[body_id]
                        for body_id in sorted(body_nodes)
                        if body_nodes[body_id]["children"]
                    ],
                }
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "models": [path.name if path.parent == output.parent else str(path.relative_to(output.parent)) for path in model_paths],
        "graph": graph,
    }
    if force or include_checker_floor or not output.is_file():
        output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return FloraSceneBundle(
        scene_path=output,
        model_paths=tuple(model_paths),
        body_node_names=tuple(body_names),
        visual_node_count=visual_count,
        mesh_geom_count=visual_count,
        instance_count=int(instance_count),
    )


def build_scene_file_from_render_scene(
    *,
    render_scene: object,
    body_names: Mapping[int, str] | Sequence[str],
    output_path: str | Path,
    instance_count: int = 1,
    force: bool = False,
    include_checker_floor: bool = False,
    floor_half_extent: float = 128.0,
    floor_tile_size: float = 0.5,
) -> FloraSceneBundle:
    """Lower a compiled public ``RenderSceneDesc`` to one Flora SceneFile.

    ``RenderSceneDesc`` owns the static mesh/material/instance tables.  The
    resulting SceneFile keeps that table shared and creates only graph/body
    nodes for each requested render world.  ``body_names`` is supplied by the
    compiled scene model, so this generic function never invents a robot body
    ordering.  A mapping preserves explicit public ``object_id`` bindings;
    a sequence remains a convenient ``body_id -> object_key`` view.
    """

    if isinstance(instance_count, bool) or int(instance_count) < 1:
        raise ValueError("instance_count must be a positive integer")
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    model_dir = output.parent / f"{output.stem}.models"
    model_paths: list[Path] = []
    model_indices: dict[tuple[str, str], int] = {}

    asset_table = getattr(render_scene, "asset_table", None)
    material_table = getattr(render_scene, "material_table", None)
    instance_table = getattr(render_scene, "instance_table", None)
    if asset_table is None or material_table is None or instance_table is None:
        raise ValueError(
            "Flora render-scene lowering requires asset, material, and instance tables"
        )

    def model_for(asset_id: str, material_id: str) -> int:
        key = (str(asset_id), str(material_id))
        if key in model_indices:
            return model_indices[key]
        asset = asset_table.get(str(asset_id))
        payload = getattr(asset, "payload", None)
        if payload is None or not hasattr(payload, "vertices"):
            raise ValueError(
                f"Flora only supports mesh payloads; asset={asset_id!r}"
            )
        material = material_table.get(str(material_id))
        target = model_dir / f"{len(model_paths):04d}_{asset_id[-12:]}_{material_id[-12:]}.glb"
        if force or not target.is_file() or not _glb_contains_vertex_normals(target):
            _load_render_mesh_as_glb(payload, target, material)
        model_indices[key] = len(model_paths)
        model_paths.append(target)
        return model_indices[key]

    if isinstance(body_names, Mapping):
        body_name_map = {
            int(body_id): str(name)
            for body_id, name in body_names.items()
            if str(name)
        }
    else:
        body_name_map = {
            body_id: str(name)
            for body_id, name in enumerate(body_names)
            if str(name)
        }
    if not body_name_map:
        raise ValueError("Flora render-scene lowering requires body names")
    body_ids = tuple(sorted(body_name_map))
    graph: list[dict[str, Any]] = []
    body_node_names: list[str] = []
    visual_count = 0
    floor_model_index: int | None = None
    if include_checker_floor:
        floor_model_index = _append_checker_floor_model(
            model_dir=model_dir,
            model_paths=model_paths,
            force=force,
            half_extent=float(floor_half_extent),
            tile_size=float(floor_tile_size),
        )

    for instance_id in range(int(instance_count)):
        env_name = f"env_{instance_id:04d}"
        body_nodes: dict[int, dict[str, Any]] = {}
        for body_id in body_ids:
            body_name = body_name_map[body_id]
            node_name = f"{env_name}__body__{body_name}"
            body_nodes[body_id] = {
                "name": node_name,
                "translation": [0.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 0.0, 1.0],
                "scaling": [1.0, 1.0, 1.0],
                "children": [],
            }
            body_node_names.append(node_name)

        for part_index, instance in enumerate(instance_table.records):
            body_id = int(getattr(instance, "body_id", -1))
            if body_id < 0:
                continue
            if body_id not in body_nodes:
                raise ValueError(
                    "Flora render-scene body id is outside the compiled body-name table: "
                    f"body_id={body_id}, body_count={len(body_ids)}"
                )
            model_index = model_for(
                str(getattr(instance, "asset_id", "")),
                str(getattr(instance, "material_id", "")),
            )
            body_nodes[body_id]["children"].append(
                {
                    "name": (
                        f"{body_nodes[body_id]['name']}__visual_"
                        f"{part_index}"
                    ),
                    "model": model_index,
                    "translation": [0.0, 0.0, 0.0],
                    "rotation": [0.0, 0.0, 0.0, 1.0],
                    "scaling": [1.0, 1.0, 1.0],
                }
            )
            visual_count += 1
        graph.append(
            {
                "name": env_name,
                "children": [body_nodes[body_id] for body_id in body_ids],
            }
        )

    if floor_model_index is not None:
        graph.insert(
            0,
            {
                "name": "flora_checker_floor",
                "model": floor_model_index,
                "translation": [0.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 0.0, 1.0],
                "scaling": [1.0, 1.0, 1.0],
            },
        )

    payload = {
        "models": [
            str(path.relative_to(output.parent))
            for path in model_paths
        ],
        "graph": graph,
    }
    # SceneFile generation is an explicit renderer-build boundary.  Rewrite
    # the small graph descriptor each build so a changed compiled scene cannot
    # silently reuse a stale topology file.
    del force
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return FloraSceneBundle(
        scene_path=output,
        model_paths=tuple(model_paths),
        body_node_names=tuple(body_node_names),
        visual_node_count=visual_count,
        mesh_geom_count=visual_count,
        instance_count=int(instance_count),
    )


__all__ = [
    "FloraSceneBundle",
    "build_scene_file_from_mjcf",
    "build_scene_file_from_assemblies",
    "build_scene_file_from_render_scene",
]
