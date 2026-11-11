"""Derive the versioned PickCube Isaac scene whose graspable object is a generated asset.

The F06 desktop delivery remains the frozen regression input.  This generator
consumes that delivery's Panda source bytes and composition recipe, replaces the
task-owned ``/F06Scene/cube_v1`` box collider with a generated, textured mesh
asset (visual mesh + convex-hull collider under the same rigid body), and writes
a separately versioned local delivery:

* representation ``isaacsim-6.2.0.0-pickcube-asset-object-v1``
* recipe ``pick-cube-isaac-asset-object-scene-v1``
* entry ``pickcube_asset_scene.usda`` / ``/F06Scene``

The task contract (0.08 kg rigid body, ~50 mm extent, initial pose, support,
Panda drives/TCP) is unchanged; only the object's geometry/material source is
the generated asset.  Run with Isaac Sim 6.2 Python, outside SimulationApp:

``isaac/bin/python task_env/diagnostics/tasks/pickcube_isaac_asset_object_delivery.py
  --core-python /path/to/geochora/bin/python
  --base-delivery workspace/maintenance/.../isaac_usd_v2/delivery_manifest.json
  --asset-glb <generated.glb> --asset-source <ref.png> --asset-source <result.json>
  --asset-id toy_block_g --output <dir>``
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import sys

CORE_ROOT = Path(__file__).resolve().parents[3]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import pickcube_isaac_usd_delivery as f06  # noqa: E402  (frozen F06 composition owner)


REPRESENTATION_ID = "isaacsim-6.2.0.0-pickcube-asset-object-v1"
RECIPE_ID = "pick-cube-isaac-asset-object-scene-v1"
ENTRY_FILE = "pickcube_asset_scene.usda"
ENTRY_PRIM = "/F06Scene"
OBJECT_PRIM = "/F06Scene/cube_v1"
OBJECT_MASS_KG = 0.08
TARGET_EXTENT_M = 0.05
EXTENT_TOLERANCE_M = 0.004
LOCAL_CHECKS = (*f06.LOCAL_CHECKS, "rigid-object-geometry", "material-and-texture-binding")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_generated_mesh(glb: Path):
    """Return Z-up vertices (m, centred), faces, UVs and the PBR texture images."""
    import numpy as np
    import trimesh

    scene = trimesh.load(str(glb), force="scene", process=False)
    meshes = [geometry for geometry in scene.dump() if isinstance(geometry, trimesh.Trimesh)]
    if len(meshes) != 1:
        raise ValueError(f"generated asset must contain exactly one textured mesh, got {len(meshes)}")
    mesh = meshes[0]
    visual = mesh.visual
    if not isinstance(visual, trimesh.visual.texture.TextureVisuals) or visual.uv is None:
        raise ValueError("generated asset mesh lacks UV texture coordinates")
    material = visual.material
    if isinstance(material, trimesh.visual.material.SimpleMaterial):
        material = material.to_pbr()
    base_image = getattr(material, "baseColorTexture", None)
    if base_image is None:
        raise ValueError("generated asset material lacks a base-color texture")
    mr_image = getattr(material, "metallicRoughnessTexture", None)
    # glTF is +Y up; GeoChora stages are +Z up: (x, y, z)_gltf -> (x, -z, y)_usd.
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    vertices = np.stack([vertices[:, 0], -vertices[:, 2], vertices[:, 1]], axis=1)
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    native_extent = high - low
    scale = TARGET_EXTENT_M / float(native_extent.max())
    vertices = (vertices - (low + high) / 2.0) * scale
    faces = np.asarray(mesh.faces, dtype=np.int64)
    uv = np.asarray(visual.uv, dtype=np.float64)
    return {
        "vertices": vertices, "faces": faces, "uv": uv,
        "base_image": base_image, "mr_image": mr_image,
        "native_extent": native_extent.tolist(), "uniform_scale": scale,
        "base_color_factor": [float(v) / (255.0 if max(material.baseColorFactor) > 1.0 else 1.0)
                              for v in (material.baseColorFactor if material.baseColorFactor is not None
                                        else (1.0, 1.0, 1.0, 1.0))][:3],
    }


def _png_bytes(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _mass_properties(vertices, faces):
    """Uniform-density convex-hull mass properties scaled to the task mass."""
    import numpy as np
    import trimesh

    hull = trimesh.Trimesh(vertices=vertices, faces=faces, process=True).convex_hull
    if not hull.is_watertight or hull.volume <= 0.0:
        raise ValueError("generated asset convex hull is not a valid closed solid")
    hull.density = OBJECT_MASS_KG / hull.volume
    inertia = np.asarray(hull.moment_inertia)
    principal, axes = np.linalg.eigh(inertia)
    if np.linalg.det(axes) < 0:
        axes[:, 2] *= -1.0
    rotation = trimesh.transformations.quaternion_from_matrix(
        np.vstack([np.hstack([axes, np.zeros((3, 1))]), [0, 0, 0, 1]]))
    return hull, {
        "volume_m3": float(hull.volume),
        "density_kg_m3": float(hull.density),
        "center_of_mass_m": [float(v) for v in hull.center_mass],
        "principal_inertia_kg_m2": [float(v) for v in principal],
        "principal_axes_wxyz": [float(v) for v in rotation],
    }


def _write_asset_layer(output: Path, asset_id: str, generated, hull) -> tuple[str, list[str]]:
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt

    asset_dir = f"assets/{asset_id}"
    base_rel = f"{asset_dir}/textures/base_color.png"
    texture_rels = [base_rel]
    f06._write(output / base_rel, _png_bytes(generated["base_image"]))
    mr_rel = None
    if generated["mr_image"] is not None:
        mr_rel = f"{asset_dir}/textures/metallic_roughness.png"
        f06._write(output / mr_rel, _png_bytes(generated["mr_image"]))
        texture_rels.append(mr_rel)

    layer_rel = f"{asset_dir}/{asset_id}.usdc"
    layer_path = output / layer_rel
    if layer_path.exists():
        raise FileExistsError(f"refusing to overwrite generated asset layer: {layer_path}")
    layer_path.parent.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(layer_path))
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    root = UsdGeom.Xform.Define(stage, "/Asset")
    stage.SetDefaultPrim(root.GetPrim())
    root.GetPrim().SetMetadata("kind", "component")

    vertices, faces, uv = generated["vertices"], generated["faces"], generated["uv"]
    visual = UsdGeom.Mesh.Define(stage, "/Asset/visual")
    visual.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(vertices.astype("float32")))
    visual.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(faces)))
    visual.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(faces.reshape(-1).astype("int32")))
    visual.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    visual.CreateDoubleSidedAttr(False)
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    visual.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*low.tolist()), Gf.Vec3f(*high.tolist())]))
    st = UsdGeom.PrimvarsAPI(visual).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    st.Set(Vt.Vec2fArray.FromNumpy(uv.astype("float32")))

    material = UsdShade.Material.Define(stage, "/Asset/Looks/surface")
    shader = UsdShade.Shader.Define(stage, "/Asset/Looks/surface/preview")
    shader.CreateIdAttr("UsdPreviewSurface")
    reader = UsdShade.Shader.Define(stage, "/Asset/Looks/surface/st_reader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    st_out = reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    base_tex = UsdShade.Shader.Define(stage, "/Asset/Looks/surface/base_color")
    base_tex.CreateIdAttr("UsdUVTexture")
    base_tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("./textures/base_color.png"))
    base_tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    base_tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_out)
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        base_tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3))
    if mr_rel is not None:
        # glTF metallicRoughness: G = roughness, B = metallic (linear data).
        mr_tex = UsdShade.Shader.Define(stage, "/Asset/Looks/surface/metallic_roughness")
        mr_tex.CreateIdAttr("UsdUVTexture")
        mr_tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath("./textures/metallic_roughness.png"))
        mr_tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("raw")
        mr_tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_out)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).ConnectToSource(
            mr_tex.CreateOutput("g", Sdf.ValueTypeNames.Float))
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).ConnectToSource(
            mr_tex.CreateOutput("b", Sdf.ValueTypeNames.Float))
    else:
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.7)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(visual.GetPrim()).Bind(material)

    collision = UsdGeom.Mesh.Define(stage, "/Asset/collision")
    collision.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(hull.vertices.astype("float32")))
    collision.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(hull.faces)))
    collision.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(hull.faces.reshape(-1).astype("int32")))
    hlow, hhigh = hull.vertices.min(axis=0), hull.vertices.max(axis=0)
    collision.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*hlow.tolist()), Gf.Vec3f(*hhigh.tolist())]))
    collision.CreatePurposeAttr(UsdGeom.Tokens.guide)
    UsdPhysics.CollisionAPI.Apply(collision.GetPrim()).CreateCollisionEnabledAttr(True)
    UsdPhysics.MeshCollisionAPI.Apply(collision.GetPrim()).CreateApproximationAttr(
        UsdPhysics.Tokens.convexHull)
    stage.GetRootLayer().Save()
    return layer_rel, texture_rels


def _compose_scene(output: Path, layer_rel: str, mass: dict) -> None:
    from pxr import Gf, Sdf, UsdPhysics

    stage, *_ = f06._read_stage(output, ENTRY_FILE)
    # Replace only the task-owned object's geometry; the rigid body, task mass,
    # pose, support, Panda and drives stay the frozen F06 composition.
    if not stage.RemovePrim(f"{OBJECT_PRIM}/collision"):
        raise ValueError("F06 box collider was not authored where expected")
    body = stage.GetPrimAtPath(OBJECT_PRIM)
    geometry = stage.DefinePrim(f"{OBJECT_PRIM}/geometry", "Xform")
    geometry.GetReferences().AddReference(layer_rel, Sdf.Path("/Asset"))
    mass_api = UsdPhysics.MassAPI(body)
    mass_api.GetMassAttr().Set(OBJECT_MASS_KG)
    mass_api.GetDiagonalInertiaAttr().Set(Gf.Vec3f(*mass["principal_inertia_kg_m2"]))
    w, x, y, z = mass["principal_axes_wxyz"]
    mass_api.CreatePrincipalAxesAttr(Gf.Quatf(w, x, y, z))
    mass_api.CreateCenterOfMassAttr(Gf.Vec3f(*mass["center_of_mass_m"]))
    stage.GetRootLayer().Save()


def _validate_scene(output: Path) -> dict[str, object]:
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade

    stage = Usd.Stage.Open(str(output / ENTRY_FILE), load=Usd.Stage.LoadAll)
    if stage is None:
        raise ValueError("asset-object PickCube USD did not reopen")
    if (float(UsdGeom.GetStageMetersPerUnit(stage)), str(UsdGeom.GetStageUpAxis(stage))) != (1.0, "Z"):
        raise ValueError("asset-object PickCube USD must use SI meters and Z-up")
    body = stage.GetPrimAtPath(OBJECT_PRIM)
    if not body.HasAPI(UsdPhysics.RigidBodyAPI):
        raise ValueError("generated object body lacks RigidBodyAPI")
    if stage.GetPrimAtPath(f"{OBJECT_PRIM}/collision").IsValid():
        raise ValueError("frozen F06 box collider must not survive in the asset-object scene")
    bodies = [p for p in Usd.PrimRange(body) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
    colliders = [p for p in Usd.PrimRange(body) if p.HasAPI(UsdPhysics.CollisionAPI)]
    meshes = [p for p in Usd.PrimRange(body) if p.IsA(UsdGeom.Mesh)]
    if len(bodies) != 1 or len(colliders) != 1 or not colliders[0].IsA(UsdGeom.Mesh):
        raise ValueError("generated object must be one rigid body with one mesh collider")
    collider = colliders[0]
    if UsdPhysics.CollisionAPI(collider).GetCollisionEnabledAttr().Get() is False:
        raise ValueError("generated object collider is disabled")
    if UsdPhysics.MeshCollisionAPI(collider).GetApproximationAttr().Get() != UsdPhysics.Tokens.convexHull:
        raise ValueError("generated object collider must use convexHull approximation")
    visuals = [p for p in meshes if p != collider]
    if len(visuals) != 1:
        raise ValueError("generated object must carry exactly one visual mesh")
    visual = visuals[0]
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    guide_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render", "guide"])
    vis_box = cache.ComputeWorldBound(visual).ComputeAlignedRange()
    col_box = guide_cache.ComputeWorldBound(collider).ComputeAlignedRange()
    vis_size = [float(v) for v in vis_box.GetSize()]
    if not math.isclose(max(vis_size), TARGET_EXTENT_M, abs_tol=1e-4):
        raise ValueError(f"generated object extent {vis_size} differs from the 50 mm task contract")
    if any(abs(v - TARGET_EXTENT_M) > EXTENT_TOLERANCE_M for v in vis_size):
        raise ValueError(f"generated object is not block-like within {EXTENT_TOLERANCE_M} m: {vis_size}")
    for axis in range(3):
        if (col_box.GetMin()[axis] > vis_box.GetMin()[axis] + 1e-6
                or col_box.GetMax()[axis] < vis_box.GetMax()[axis] - 1e-6):
            raise ValueError("generated object collider does not cover its visual bounds")
    bound = UsdShade.MaterialBindingAPI(visual).ComputeBoundMaterial()[0]
    if not bound:
        raise ValueError("generated object visual mesh has no bound material")
    textures = [
        p for p in Usd.PrimRange(bound.GetPrim())
        if p.IsA(UsdShade.Shader) and UsdShade.Shader(p).GetIdAttr().Get() == "UsdUVTexture"
    ]
    if not textures:
        raise ValueError("generated object material carries no texture")
    table_top = stage.GetPrimAtPath("/F06Scene/tabletop_v1/collision")
    table_box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render", "guide"]
                                  ).ComputeWorldBound(table_top).ComputeAlignedRange()
    gap = float(col_box.GetMin()[2] - table_box.GetMax()[2])
    if not 0.0 <= gap <= 0.003:
        raise ValueError(f"generated object must rest on (not in) the support, gap={gap}")
    mass = float(UsdPhysics.MassAPI(body).GetMassAttr().Get())
    if not math.isclose(mass, OBJECT_MASS_KG, abs_tol=1e-6):  # float32 attribute
        raise ValueError("generated object mass differs from the PickCube 0.08 kg contract")
    # Re-run the frozen F06 Panda/support/drive structure checks except the box-only ones.
    panda = {k: v for k, v in _panda_structure(stage).items()}
    return {
        **panda,
        "object_prim": OBJECT_PRIM,
        "object_visual_prim": str(visual.GetPath()),
        "object_collision_prim": str(collider.GetPath()),
        "object_visual_bounds_size_m": vis_size,
        "object_collision_bounds_size_m": [float(v) for v in col_box.GetSize()],
        "object_support_gap_m": gap,
        "object_mass_kg": mass,
        "object_texture_shaders": [str(p.GetPath()) for p in textures],
        "object_visual_face_count": len(UsdGeom.Mesh(visual).GetFaceVertexCountsAttr().Get()),
        "object_collision_face_count": len(UsdGeom.Mesh(collider).GetFaceVertexCountsAttr().Get()),
    }


def _panda_structure(stage) -> dict[str, object]:
    from pxr import UsdGeom, UsdPhysics

    scenes = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
    roots = [p for p in stage.Traverse() if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
    if len(scenes) != 1 or len(roots) != 1:
        raise ValueError("asset-object scene requires one physics scene and one Panda articulation root")
    arm = [p for p in stage.Traverse()
           if p.GetName() in {f"joint{i}" for i in range(1, 8)} and p.IsA(UsdPhysics.RevoluteJoint)]
    leader = [p for p in stage.Traverse()
              if p.GetName() == "finger_joint1" and p.IsA(UsdPhysics.PrismaticJoint)]
    mimic = [p for p in stage.Traverse()
             if p.GetName() == "finger_joint2" and p.IsA(UsdPhysics.PrismaticJoint)]
    if len(arm) != 7 or len(leader) != 1 or len(mimic) != 1:
        raise ValueError("asset-object Panda mapping must expose seven arm and two hand DOFs")
    if "PhysxMimicJointAPI:transX" not in list(mimic[0].GetMetadata("apiSchemas").GetAppliedItems()):
        raise ValueError("asset-object follower finger lacks its PhysX mimic API")
    drive = UsdPhysics.DriveAPI(leader[0], "linear")
    if (float(drive.GetStiffnessAttr().Get()), float(drive.GetDampingAttr().Get()),
            float(drive.GetMaxForceAttr().Get())) != (5000.0, 120.0, 5.0):
        raise ValueError("asset-object gripper drive differs from the PickCube source adapter")
    if any(float(UsdPhysics.DriveAPI(p, "angular").GetMaxForceAttr().Get()) != 250.0 for p in arm):
        raise ValueError("asset-object arm effort differs from PickCube's 250 N source force range")
    ee = stage.GetPrimAtPath("/F06Scene/panda/Geometry/link0/link1/link2/link3/link4/"
                             "link5/link6/link7/hand/ee")
    top = stage.GetPrimAtPath("/F06Scene/tabletop_v1/top")
    if not ee.IsValid() or not top.IsValid():
        raise ValueError("asset-object TCP or support task frame is absent")
    if tuple(UsdGeom.Xformable(ee).GetOrderedXformOps()[0].Get()) != (0.0, 0.0, 0.0584):
        raise ValueError("asset-object TCP offset differs from the PickCube hand-frame contract")
    if not stage.GetPrimAtPath("/F06Scene/tabletop_v1/collision").HasAPI(UsdPhysics.CollisionAPI):
        raise ValueError("asset-object support is missing its collision geometry")
    return {
        "physics_scene_count": 1, "articulation_root_count": 1,
        "arm_dofs": 7, "hand_dofs": 2, "table_top_z_m": 0.462,
        "tcp_hand_offset_m": [0.0, 0.0, 0.0584],
        "arm_effort_limit_N": 250.0, "hand_effort_limit_N": 5.0,
        "gripper_drive_stiffness_N_m": 5000.0, "gripper_drive_damping_N_s_m": 120.0,
    }


def package_delivery(*, base_delivery: Path, asset_glb: Path, asset_sources: list[Path],
                     asset_id: str, output: Path) -> dict[str, object]:
    from task_env.assembly.assets import _source_closure_digest, _source_closure_manifest
    from task_env.assembly.usd_delivery import (
        _canonical_hash, _inspect_snapshot, load_usd_asset_delivery, variant_selection_hash,
    )
    from task_env.artifacts import UsdLocalValidationReportV1
    from task_env.tasks.pick_cube.isaac import (
        ISAAC_DELIVERY_MANIFEST_SHA256_V1, ISAAC_REPRESENTATION_V1,
    )

    if not asset_id.isidentifier():
        raise ValueError("asset_id must be a USD/Python identifier")
    base_delivery = base_delivery.resolve(strict=True)
    output = output.absolute()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"asset-object delivery output must be new or empty: {output}")
    base = load_usd_asset_delivery(base_delivery)
    if (base.manifest_bytes_sha256 != ISAAC_DELIVERY_MANIFEST_SHA256_V1
            or base.delivery.representation_id != ISAAC_REPRESENTATION_V1
            or not base.locally_validated or base.source_verified):
        raise ValueError("asset-object scene must derive from the exact frozen F06 desktop delivery")
    base_root = base_delivery.parent
    source_delivery = base.delivery

    source_files: dict[str, bytes] = {}
    for binding in source_delivery.source_files:
        raw = base.source_input_bytes[binding.path]
        source_files[binding.path] = raw
        f06._write(output.joinpath(*PurePosixPath(binding.path).parts), raw)
    # Derived Panda representation files reused by the F06 composition.
    for binding in source_delivery.files:
        if binding.path == source_delivery.entry_file:
            continue
        raw = base.file_bytes[binding.path]
        f06._write(output.joinpath(*PurePosixPath(binding.path).parts), raw)
    # Generated-asset source bytes: the generator output and its provenance inputs.
    generated_source_rels = []
    for path in (asset_glb, *asset_sources):
        path = path.resolve(strict=True)
        relative = f"sources/{asset_id}/{path.name}"
        if relative in source_files:
            raise ValueError(f"duplicate generated-asset source name: {path.name}")
        raw = path.read_bytes()
        source_files[relative] = raw
        generated_source_rels.append(relative)
        f06._write(output.joinpath(*PurePosixPath(relative).parts), raw)
    source_closure_sha = _source_closure_digest(source_files)

    generated = _load_generated_mesh(asset_glb)
    hull, mass = _mass_properties(generated["vertices"], generated["faces"])
    layer_rel, texture_rels = _write_asset_layer(output, asset_id, generated, hull)
    _compose_scene(output, layer_rel, mass)
    validation = _validate_scene(output)
    required, inspection = _inspect_snapshot(output, output / ENTRY_FILE, ENTRY_PRIM, {})
    if not {layer_rel, *texture_rels}.issubset(required):
        raise ValueError("generated asset layer/textures are not in the composed USD dependency closure")
    output_files = {relative: output.joinpath(*PurePosixPath(relative).parts).read_bytes()
                    for relative in sorted(required)}
    output_closure_sha = _source_closure_digest(output_files)

    inventory = {
        "schema_version": "f04-local-source-inventory-v1",
        "files": list(_source_closure_manifest(source_files)),
        "source_closure_sha256": source_closure_sha,
    }
    inventory_raw = f06._json_bytes(inventory)
    inventory_rel = "metadata/source_inventory_v1.json"
    f06._write(output / inventory_rel, inventory_raw)
    recipe_rel = "metadata/pickcube_isaac_asset_object_recipe_v1.json"
    checker_rel = "metadata/pickcube_isaac_asset_object_checker_v1.py"
    report_rel = "metadata/pickcube_asset_object_local_validation_v1.json"
    recipe = {
        "schema_version": "pick-cube-isaac-asset-object-recipe-v1",
        "recipe_id": RECIPE_ID,
        "recipe_version": "1",
        "base_delivery_manifest_sha256": base.manifest_bytes_sha256,
        "base_representation_id": source_delivery.representation_id,
        "source_delivery_sha256": source_delivery.delivery_sha256,
        "panda_source_closure_sha256": source_delivery.source_closure_sha256,
        "source_entry_sha256": source_delivery.source_entry_sha256,
        "entry_file": ENTRY_FILE,
        "entry_prim": ENTRY_PRIM,
        "generated_object": {
            "asset_id": asset_id,
            "object_prim": OBJECT_PRIM,
            "asset_layer": layer_rel,
            "textures": texture_rels,
            "generator_sources": {rel: _sha(source_files[rel]) for rel in generated_source_rels},
            "generator_route": "TRELLIS.2 whole-asset geometry+texture (asset-creation skill, MCP trellis2)",
            "native_extent_normalized": generated["native_extent"],
            "uniform_scale_to_m": generated["uniform_scale"],
            "axis_conversion": "glTF +Y-up -> USD +Z-up: (x, y, z) -> (x, -z, y); bbox-centred",
            "target_max_extent_m": TARGET_EXTENT_M,
            "collision": "convex hull of the generated mesh, UsdPhysics convexHull approximation",
            "mass_kg": OBJECT_MASS_KG,
            "mass_properties": mass,
        },
        "task_recipe": {
            "object_mass_kg": OBJECT_MASS_KG,
            "table_half_size_m": [0.28, 0.20, 0.01],
            "table_center_world_m": [0.5545, 0.0, 0.452],
            "table_top_z_m": 0.462,
            "initial_object_pose_world_m_wxyz": [0.50, 0.0, 0.488, 1.0, 0.0, 0.0, 0.0],
            "tcp_hand_offset_local_m": [0.0, 0.0, 0.0584],
        },
        "validation": validation,
        "known_losses": [
            "The generated mesh is uniformly rescaled so its largest extent is the task's 50 mm; its other extents are generator output, not measured physical dimensions.",
            "Collision is the convex hull of the generated mesh; concave surface detail is not represented in contact.",
            "Mass is the PickCube 0.08 kg contract; inertia assumes uniform density over the convex hull.",
            "USD default surface friction/restitution is not claimed equivalent to the MJCF contact law.",
            "The task Expert plans with the PickCube 25 mm half-size constant, not the generated geometry.",
        ],
    }
    recipe_raw = f06._json_bytes(recipe)
    checker_raw = Path(__file__).read_bytes()
    f06._write(output / recipe_rel, recipe_raw)
    f06._write(output / checker_rel, checker_raw)
    options = {
        "scene_recipe_sha256": _sha(recipe_raw),
        "base_delivery_manifest_sha256": base.manifest_bytes_sha256,
        "task_profile": "pick-cube-v1/p1_6_experimental_100hz",
        "representation": "local-isaacsim-6.2-desktop-pickcube-asset-object-v1",
    }
    options_sha = _canonical_hash(options)
    report = UsdLocalValidationReportV1(
        "usd-local-validation-report-v1", "pickcube-isaac-asset-object-local-validation-v1",
        "local-validated", source_delivery.asset_identity_hash, source_delivery.source_revision,
        source_closure_sha, _sha(inventory_raw), source_delivery.source_entry_sha256,
        variant_selection_hash({}), _sha(output_files[ENTRY_FILE]), output_closure_sha,
        ENTRY_PRIM, "usd", REPRESENTATION_ID, RECIPE_ID, "1", _sha(recipe_raw), options_sha,
        "pickcube-isaac-asset-object-checker-v1", _sha(checker_raw),
        "Geochora PickCube asset-object owner", LOCAL_CHECKS, tuple(recipe["known_losses"]),
        (
            "native GPU PhysX consumption is established only by the separate Isaac runtime campaign",
            "Isaac render/static-stability evidence lives in the asset-preparation evidence directory",
        ),
        True,
    )
    report_raw = f06._json_bytes(report.to_mapping())
    f06._write(output / report_rel, report_raw)
    manifest = {
        "schema_version": "usd-local-derived-delivery-v1",
        "asset_definition": source_delivery.asset_definition.to_mapping(),
        "source_revision": source_delivery.source_revision,
        "provenance_kind": "local-validated",
        "source_closure_sha256": source_closure_sha,
        "source_manifest_path": inventory_rel,
        "source_manifest_sha256": _sha(inventory_raw),
        "source_files": list(_source_closure_manifest(source_files)),
        "source_entry_file": source_delivery.source_entry_file,
        "source_entry_sha256": source_delivery.source_entry_sha256,
        "source_variant_selections": {},
        "source_variant_selection_sha256": variant_selection_hash({}),
        "entry_file": ENTRY_FILE,
        "entry_prim": ENTRY_PRIM,
        "variant_selections": {},
        "representation_format": "usd",
        "representation_id": REPRESENTATION_ID,
        "closure_policy": "f04-selected-derived-scene-v1",
        "files": list(_source_closure_manifest(output_files)),
        "closure_sha256": output_closure_sha,
        "recipe_path": recipe_rel,
        "recipe_sha256": _sha(recipe_raw),
        "checker_path": checker_rel,
        "checker_sha256": _sha(checker_raw),
        "support_files": [],
        "validation_report_path": report_rel,
        "validation_report_sha256": _sha(report_raw),
        "options_sha256": options_sha,
    }
    manifest_raw = f06._json_bytes(manifest)
    f06._write(output / "delivery_manifest.json", manifest_raw)
    loaded = load_usd_asset_delivery(output / "delivery_manifest.json")
    if (not loaded.locally_validated or loaded.source_verified
            or loaded.delivery.closure_sha256 != output_closure_sha):
        raise ValueError("asset-object loader did not return exact local validation/provenance")
    return {
        "manifest_path": str(output / "delivery_manifest.json"),
        "manifest_sha256": _sha(manifest_raw),
        "delivery_sha256": loaded.delivery_sha256,
        "source_closure_sha256": source_closure_sha,
        "output_closure_sha256": output_closure_sha,
        "representation_id": REPRESENTATION_ID,
        "inspection": dict(inspection),
        "validation": validation,
        "mass_properties": mass,
        "locally_validated": loaded.locally_validated,
        "source_verified": loaded.source_verified,
        "passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--core-python", type=Path,
        default=Path(os.environ["GEOCHORA_CORE_PYTHON"]) if os.environ.get("GEOCHORA_CORE_PYTHON") else None,
    )
    parser.add_argument("--base-delivery", type=Path, required=True)
    parser.add_argument("--asset-glb", type=Path, required=True)
    parser.add_argument("--asset-source", type=Path, action="append", default=[])
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with f06._core_dependency_path(args.core_python):
        result = package_delivery(
            base_delivery=args.base_delivery, asset_glb=args.asset_glb,
            asset_sources=args.asset_source, asset_id=args.asset_id, output=args.output,
        )
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
