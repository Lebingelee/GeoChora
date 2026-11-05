"""Read exact USD preparation bindings through OpenUSD's public schemas.

This validator deliberately runs before native materialization. Physics QA and
task execution remain separate gates, and a bound report is not their substitute.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET


def mesh_content_sha256(mesh):
    """Hash local mesh geometry/topology actually consumed by USD/PhysX."""
    points = mesh.GetPointsAttr().Get()
    counts = mesh.GetFaceVertexCountsAttr().Get()
    indices = mesh.GetFaceVertexIndicesAttr().Get()
    if points is None or counts is None or indices is None:
        raise ValueError("declared mesh has incomplete geometry")
    values = [[float(v) for v in point] for point in points]
    if (not values or not counts or any(len(point) != 3 for point in values)
            or any(not math.isfinite(v) for point in values for v in point)
            or any(int(c) < 3 for c in counts)
            or sum(int(c) for c in counts) != len(indices)
            or any(not 0 <= int(index) < len(values) for index in indices)):
        raise ValueError("declared mesh topology/points are invalid")
    payload = {"schema_version": "usd-mesh-content-v1", "points": values,
               "face_vertex_counts": [int(v) for v in counts],
               "face_vertex_indices": [int(v) for v in indices],
               "subdivision_scheme": str(mesh.GetSubdivisionSchemeAttr().Get()),
               "orientation": str(mesh.GetOrientationAttr().Get())}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _world_aabb_in_body_frame(stage, body, mesh):
    from pxr import UsdGeom

    cache = UsdGeom.XformCache()
    body_to_world = cache.GetLocalToWorldTransform(body)
    mesh_to_world = cache.GetLocalToWorldTransform(mesh.GetPrim())
    mesh_to_body = mesh_to_world * body_to_world.GetInverse()
    points = mesh.GetPointsAttr().Get()
    transformed = [mesh_to_body.Transform(point) for point in points]
    values = [[float(component) for component in point] for point in transformed]
    return (
        tuple(min(point[index] for point in values) for index in range(3)),
        tuple(max(point[index] for point in values) for index in range(3)),
    )


def _assert_aabb_matches(actual_min, actual_max, declared_min, declared_max):
    scale = max(
        1.0,
        *(abs(value) for value in (*declared_min, *declared_max)),
        *(abs(value) for value in (*actual_min, *actual_max)),
    )
    tolerance = 1.0e-6 * scale
    if any(abs(actual - declared) > tolerance
           for actual, declared in zip(actual_min, declared_min, strict=True)):
        raise ValueError("target mesh minimum bounds differ from the handoff")
    if any(abs(actual - declared) > tolerance
           for actual, declared in zip(actual_max, declared_max, strict=True)):
        raise ValueError("target mesh maximum bounds differ from the handoff")


def _assert_source_mesh_matches(preparation, stage):
    """Bind this profile's composed meshes to its preserved Robosuite source bytes."""
    from pxr import UsdGeom

    source = preparation.loaded_delivery.source_input_bytes
    xml_raw = source.get("source/objects/lemon.xml")
    obj_raw = source.get("source/objects/meshes/lemon.obj")
    if type(xml_raw) is not bytes or type(obj_raw) is not bytes:
        raise ValueError("asset scene source inventory lacks the Robosuite lemon XML/OBJ")
    document = ET.fromstring(xml_raw)
    meshes = document.findall("./asset/mesh")
    geoms = document.findall("./worldbody/body/body/geom")
    if (len(meshes) != 1 or len(geoms) != 1
            or meshes[0].get("file") != "meshes/lemon.msh"
            or geoms[0].get("mesh") != meshes[0].get("name")):
        raise ValueError("Robosuite source mesh/geom binding differs from the lemon profile")
    try:
        scale = tuple(float(value) for value in meshes[0].attrib["scale"].split())
    except (KeyError, ValueError) as exc:
        raise ValueError("Robosuite source mesh scale is invalid") from exc
    if len(scale) != 3 or any(not math.isfinite(value) or value <= 0 for value in scale):
        raise ValueError("Robosuite source mesh scale is invalid")
    vertices = []
    faces = []
    for line in obj_raw.decode("utf-8").splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] == "v":
            if len(fields) < 4:
                raise ValueError("source OBJ vertex is incomplete")
            vertices.append(tuple(float(value) * scale[index]
                                  for index, value in enumerate(fields[1:4])))
        elif fields[0] == "f":
            indices = []
            for token in fields[1:]:
                raw = int(token.split("/", 1)[0])
                index = raw - 1 if raw > 0 else len(vertices) + raw
                if not 0 <= index < len(vertices):
                    raise ValueError("source OBJ face index is invalid")
                indices.append(index)
            if len(indices) < 3:
                raise ValueError("source OBJ face has fewer than three vertices")
            faces.extend((indices[0], indices[index], indices[index + 1])
                         for index in range(1, len(indices) - 1))
    if (not vertices or not faces
            or any(not math.isfinite(value) for point in vertices for value in point)):
        raise ValueError("source OBJ has no valid finite geometry")
    geometry = preparation.preparation.geometry
    expected_indices = [index for face in faces for index in face]
    for path in set(geometry.visual_mesh_prims) | set(geometry.collision_mesh_prims):
        mesh = UsdGeom.Mesh(stage.GetPrimAtPath(path))
        points = mesh.GetPointsAttr().Get()
        counts = mesh.GetFaceVertexCountsAttr().Get()
        indices = mesh.GetFaceVertexIndicesAttr().Get()
        if (points is None or len(points) != len(vertices)
                or [int(value) for value in counts] != [3] * len(faces)
                or [int(value) for value in indices] != expected_indices
                or any(not math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=1e-7)
                       for actual_point, source_point in zip(points, vertices, strict=True)
                       for actual, expected in zip(actual_point, source_point, strict=True))):
            raise ValueError("composed target mesh differs from scaled source OBJ geometry")


def validate_asset_scene_structure(preparation, loaded_delivery=None):
    """Check declared actual meshes, body/support ownership and Panda paths."""
    from pxr import Gf, Usd, UsdGeom, UsdPhysics
    import tempfile

    from .asset_scene import LoadedAssetScenePreparationV1
    if type(preparation) is not LoadedAssetScenePreparationV1:
        raise TypeError("structure inspection requires the Core-loaded preparation receipt")
    if loaded_delivery is not None and loaded_delivery is not preparation.loaded_delivery:
        raise ValueError("structure inspection cannot substitute another USD delivery")
    preparation.assert_fresh()
    loaded_delivery = preparation.loaded_delivery
    # Inspect the loader-owned immutable bytes, never a separately resolved stage.
    with tempfile.TemporaryDirectory(prefix="geochora-asset-structure-") as folder:
        root = Path(folder)
        for relative, raw in loaded_delivery.file_bytes.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        stage = Usd.Stage.Open(str(root / loaded_delivery.delivery.entry_file), load=Usd.Stage.LoadAll)
        if stage is None:
            raise ValueError("asset-scene USD failed to reopen")
        if (UsdGeom.GetStageMetersPerUnit(stage) != 1.0
                or str(UsdGeom.GetStageUpAxis(stage)) != "Z"):
            raise ValueError("asset-scene profile requires SI meters and Z up")
        if loaded_delivery.delivery.variant_selections:
            raise ValueError("first asset-scene profile requires a frozen selected stage without variants")
        if any(prim.GetVariantSets().GetNames() for prim in stage.Traverse()):
            raise ValueError("first asset-scene profile does not admit authored USD variants")
        bindings = preparation.preparation.bindings
        geometry = preparation.preparation.geometry
        _assert_source_mesh_matches(preparation, stage)
        for role in ("scene_root", "robot_root", "articulation_root", "robot_base",
                     "tcp_frame", "target_body", "support_body", "support_top"):
            if not stage.GetPrimAtPath(getattr(bindings, role)).IsValid():
                raise ValueError(f"required asset-scene prim absent: {role}")
        physics = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
        articulations = [str(p.GetPath()) for p in stage.Traverse()
                         if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
        if len(physics) != 1 or articulations != [bindings.articulation_root]:
            raise ValueError("asset scene requires one physics scene and the exact single Panda root")
        articulation = stage.GetPrimAtPath(bindings.articulation_root)
        if not articulation.HasAPI(UsdPhysics.ArticulationRootAPI):
            raise ValueError("declared articulation root lacks ArticulationRootAPI")
        robot_base = stage.GetPrimAtPath(bindings.robot_base)
        tcp_frame = stage.GetPrimAtPath(bindings.tcp_frame)
        if not robot_base.HasAPI(UsdPhysics.RigidBodyAPI):
            raise ValueError("declared Panda base must be a rigid body")
        if (str(robot_base.GetPath()) != bindings.articulation_root
                and not str(robot_base.GetPath()).startswith(bindings.articulation_root + "/")
                or not str(tcp_frame.GetPath()).startswith(bindings.robot_base + "/")):
            raise ValueError("Panda base and TCP must be bound inside the articulation chain")
        if tcp_frame.HasAPI(UsdPhysics.RigidBodyAPI):
            raise ValueError("Panda TCP must be a fixed frame, not another rigid body")
        for cursor in (robot_base, tcp_frame):
            while cursor and str(cursor.GetPath()) != bindings.robot_root:
                if any(attr.GetNumTimeSamples() for attr in cursor.GetAttributes()):
                    raise ValueError("Panda base/TCP frame transforms must be static")
                cursor = cursor.GetParent()
        movable_joint_types = (UsdPhysics.RevoluteJoint, UsdPhysics.PrismaticJoint)
        actual_movable_joints = {
            str(prim.GetPath()) for prim in Usd.PrimRange(stage.GetPrimAtPath(bindings.robot_root))
            if any(prim.IsA(kind) for kind in movable_joint_types)
        }
        if actual_movable_joints != set(bindings.joint_paths.values()):
            raise ValueError("Panda movable joint topology must equal the nine declared DOFs")
        for name, path in bindings.joint_paths.items():
            prim = stage.GetPrimAtPath(path)
            kind = UsdPhysics.PrismaticJoint if name.startswith("finger_") else UsdPhysics.RevoluteJoint
            if not prim.IsValid() or not prim.IsA(kind) or str(prim.GetName()) != name:
                raise ValueError(f"Panda joint binding/type differs: {name}")
            joint = UsdPhysics.Joint(prim)
            body0 = joint.GetBody0Rel().GetTargets()
            body1 = joint.GetBody1Rel().GetTargets()
            expected_body0, expected_body1 = bindings.joint_body_paths[name]
            if tuple(str(path) for path in body0) != (expected_body0,) or (
                    tuple(str(path) for path in body1) != (expected_body1,)):
                raise ValueError(f"Panda joint body mapping differs: {name}")
            if (not stage.GetPrimAtPath(expected_body0).IsValid()
                    or not stage.GetPrimAtPath(expected_body1).IsValid()):
                raise ValueError(f"Panda joint body target is invalid: {name}")
            lower = prim.GetAttribute("physics:lowerLimit").Get()
            upper = prim.GetAttribute("physics:upperLimit").Get()
            if lower is None or upper is None or not float(lower) < float(upper):
                raise ValueError(f"Panda joint requires ordered authored limits: {name}")
            if name == "finger_joint2":
                schemas = prim.GetMetadata("apiSchemas")
                mimic = schemas is not None and "PhysxMimicJointAPI:transX" in schemas.GetAppliedItems()
                reference = prim.GetRelationship("physxMimicJoint:transX:referenceJoint")
                if (not mimic or not reference
                        or len(reference.GetTargets()) != 1
                        or str(reference.GetTargets()[0]) != bindings.joint_paths["finger_joint1"]):
                    raise ValueError("Panda follower finger must reference the leader through PhysX mimic")
                for attribute, expected in (("gearing", 1.0), ("offset", 0.0),
                                            ("naturalFrequency", 25.0), ("dampingRatio", 1.0)):
                    value = prim.GetAttribute(f"physxMimicJoint:transX:{attribute}").Get()
                    if value is None or not math.isclose(float(value), expected, rel_tol=0.0, abs_tol=1e-6):
                        raise ValueError(f"Panda follower mimic {attribute} differs from its source profile")
                if UsdPhysics.DriveAPI(prim, "linear"):
                    raise ValueError("Panda follower finger cannot have a duplicate articulation drive")
            else:
                drive_name = "linear" if name == "finger_joint1" else "angular"
                if not UsdPhysics.DriveAPI(prim, drive_name):
                    raise ValueError(f"Panda joint requires its authored position drive: {name}")
        target = stage.GetPrimAtPath(bindings.target_body)
        if not target.HasAPI(UsdPhysics.RigidBodyAPI):
            raise ValueError("target prim must be a real rigid body")
        rigid = UsdPhysics.RigidBodyAPI(target)
        if not rigid.GetRigidBodyEnabledAttr().Get() or rigid.GetKinematicEnabledAttr().Get():
            raise ValueError("target must be dynamic, enabled, and not kinematic")
        mass = UsdPhysics.MassAPI(target).GetMassAttr().Get()
        if mass is None or not math.isclose(float(mass), geometry.mass_kg, rel_tol=1e-6, abs_tol=1e-8):
            raise ValueError("target mass differs from its geometry handoff")
        meshes = set(geometry.visual_mesh_prims) | set(geometry.collision_mesh_prims)
        target_world = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(target)
        target_origin_world = target_world.Transform(Gf.Vec3d(0.0, 0.0, 0.0))
        support_collision = next(
            (prim for prim in Usd.PrimRange(stage.GetPrimAtPath(bindings.support_body))
             if prim.HasAPI(UsdPhysics.CollisionAPI)
             and UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()),
            None,
        )
        if support_collision is None:
            raise ValueError("support subtree has no enabled collision surface")
        support_bbox = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]
        ).ComputeWorldBound(support_collision).ComputeAlignedBox()
        support_plane_z = float(support_bbox.GetMax()[2])
        actual_target_min_z = math.inf
        for path in geometry.collision_mesh_prims:
            mesh = UsdGeom.Mesh(stage.GetPrimAtPath(path))
            world = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(mesh.GetPrim())
            for point in mesh.GetPointsAttr().Get():
                actual_target_min_z = min(
                    actual_target_min_z,
                    float(world.Transform(Gf.Vec3d(point))[2]),
                )
        if not math.isfinite(actual_target_min_z) or abs(actual_target_min_z - support_plane_z) > 1e-5:
            raise ValueError("target collision support height is not composed flush with the support top")
        for path in meshes:
            prim = stage.GetPrimAtPath(path)
            if not prim.IsValid() or not prim.IsA(UsdGeom.Mesh):
                raise ValueError(f"declared target mesh is not an actual USD Mesh: {path}")
            if path in geometry.visual_mesh_prims:
                actual_mesh = UsdGeom.Mesh(prim)
                normals = actual_mesh.GetNormalsAttr().Get()
                if (str(actual_mesh.GetNormalsInterpolation()) != "faceVarying"
                        or normals is None
                        or len(normals) != len(actual_mesh.GetFaceVertexIndicesAttr().Get())
                        or any(not math.isfinite(float(value)) for normal in normals for value in normal)
                        or any(abs(math.sqrt(sum(float(value) ** 2 for value in normal)) - 1.0) > 1e-3
                               for normal in normals)):
                    raise ValueError("visual mesh must preserve finite unit source face-varying normals")
            if mesh_content_sha256(UsdGeom.Mesh(prim)) != geometry.mesh_content_sha256[path]:
                raise ValueError(f"target mesh content differs from its source-bound handoff: {path}")
            actual_min, actual_max = _world_aabb_in_body_frame(stage, target, UsdGeom.Mesh(prim))
            _assert_aabb_matches(
                actual_min, actual_max,
                geometry.local_aabb_min_m, geometry.local_aabb_max_m,
            )
            cursor = prim
            while cursor and str(cursor.GetPath()) != bindings.target_body:
                if cursor.HasAPI(UsdPhysics.RigidBodyAPI):
                    raise ValueError("target mesh cannot belong to another nested rigid body")
                if any(attr.GetNumTimeSamples() for attr in cursor.GetAttributes()):
                    raise ValueError("first rigid-object profile does not admit animated target meshes")
                cursor = cursor.GetParent()
        actual_collisions = set()
        actual_meshes = set()
        for prim in Usd.PrimRange(target):
            if prim.IsA(UsdGeom.Mesh):
                actual_meshes.add(str(prim.GetPath()))
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                actual_collisions.add(str(prim.GetPath()))
        if actual_meshes != meshes:
            raise ValueError("target mesh set must equal the declared visual and collision meshes")
        if actual_collisions != set(geometry.collision_mesh_prims):
            raise ValueError("target collision set must equal its declared actual mesh colliders")
        for path in geometry.collision_mesh_prims:
            prim = stage.GetPrimAtPath(path)
            if (not UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()) or (
                    not prim.HasAPI(UsdPhysics.MeshCollisionAPI)
                    or str(UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get())
                    != geometry.collision_approximation):
                raise ValueError("target collider approximation differs from the geometry handoff")
        support = stage.GetPrimAtPath(bindings.support_body)
        support_colliders = [p for p in Usd.PrimRange(support)
                             if p.HasAPI(UsdPhysics.CollisionAPI)
                             and UsdPhysics.CollisionAPI(p).GetCollisionEnabledAttr().Get()]
        if not support_colliders:
            raise ValueError("support must contain fixed collision geometry without dynamic bodies")
        for prim in Usd.PrimRange(support):
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                raise ValueError("support subtree cannot contain dynamic rigid bodies")
            if any(attr.GetNumTimeSamples() for attr in prim.GetAttributes()):
                raise ValueError("support subtree cannot contain animated transforms")
        cursor = support
        while cursor and str(cursor.GetPath()) != bindings.scene_root:
            if cursor.HasAPI(UsdPhysics.RigidBodyAPI):
                raise ValueError("support cannot be parented beneath a movable rigid body")
            cursor = cursor.GetParent()
        return {"schema_version": "asset-scene-structure-inspection-v1",
                "physics_scenes": 1, "articulation_roots": articulations,
                "target_body": bindings.target_body, "mesh_count": len(meshes),
                "collision_meshes": sorted(actual_collisions), "mass_kg": float(mass),
                "target_origin_world_m": [float(value) for value in target_origin_world],
                "target_collision_min_z_world_m": actual_target_min_z,
                "support_top_world_z_m": support_plane_z,
                "runtime_admitted": False, "native_physics_checked": False}
