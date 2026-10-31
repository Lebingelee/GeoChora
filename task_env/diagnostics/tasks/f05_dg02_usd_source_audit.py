"""Reproducibly compare a DG02 USD delivery with its frozen Panda MJCF source.

This is a static asset audit. It imports OpenUSD only to inspect serialized
stage values; it does not import GeoPhys, construct a solver, or advance time.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import numpy as np


GEOMETRY_TOLERANCE_M = 1.0e-6
FRAME_TOLERANCE_M = 2.0e-7
MASS_FLOAT32_ULPS = 4
COM_FLOAT32_ULPS = 4
INERTIA_FLOAT32_ULPS = 12


def _numbers(value: str | None, default: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(float(part) for part in value.split()) if value else default


def _quat_matrix(value: tuple[float, ...]) -> np.ndarray:
    w, x, y, z = value
    norm = math.sqrt(w*w + x*x + y*y + z*z)
    if norm == 0 or not math.isfinite(norm):
        raise ValueError("source quaternion must be finite and nonzero")
    w, x, y, z = (v / norm for v in (w, x, y, z))
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
    ], dtype=np.float64)


def _obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        fields = raw.split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] == "v":
            vertices.append(tuple(float(value) for value in fields[1:4]))
        elif fields[0] == "f":
            face = []
            for token in fields[1:]:
                index = int(token.split("/", 1)[0])
                face.append(index - 1 if index > 0 else len(vertices) + index)
            for index in range(1, len(face) - 1):
                triangles.append((face[0], face[index], face[index + 1]))
    return np.asarray(vertices, dtype=np.float64), np.asarray(triangles, dtype=np.int64)


def _stl(path: Path) -> tuple[np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    if len(raw) >= 84:
        count = struct.unpack_from("<I", raw, 80)[0]
        if len(raw) == 84 + 50 * count:
            triangles = []
            for index in range(count):
                values = struct.unpack_from("<12fH", raw, 84 + index * 50)
                triangles.append(values[3:12])
            points = np.asarray(triangles, dtype=np.float64).reshape((-1, 3))
            faces = np.arange(len(points), dtype=np.int64).reshape((-1, 3))
            return points, faces
    points = []
    for raw_line in raw.decode("ascii").splitlines():
        fields = raw_line.split()
        if fields and fields[0].lower() == "vertex":
            points.append(tuple(float(value) for value in fields[1:4]))
    if len(points) % 3:
        raise ValueError(f"invalid STL triangle stream: {path}")
    vertices = np.asarray(points, dtype=np.float64)
    return vertices, np.arange(len(vertices), dtype=np.int64).reshape((-1, 3))


def _mesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    return _obj(path) if path.suffix.lower() == ".obj" else _stl(path)


def _sorted_rows(values: np.ndarray) -> np.ndarray:
    if len(values) == 0:
        return values
    return values[np.lexsort(tuple(values[:, index] for index in reversed(range(values.shape[1]))))]


def _triangle_coordinates(points: np.ndarray, faces: np.ndarray) -> np.ndarray:
    triangles = points[faces]
    ordered = []
    for triangle in triangles:
        order = np.lexsort((triangle[:, 2], triangle[:, 1], triangle[:, 0]))
        ordered.append(triangle[order].reshape(-1))
    return _sorted_rows(np.asarray(ordered, dtype=np.float64).reshape((-1, 9)))


def _usd_local_transform(prim) -> tuple[np.ndarray, np.ndarray]:
    from pxr import Gf, UsdGeom

    result = UsdGeom.Xformable(prim).GetLocalTransformation()
    matrix = result[0] if isinstance(result, tuple) else result
    origin = matrix.Transform(Gf.Vec3d(0, 0, 0))
    basis = [matrix.TransformDir(Gf.Vec3d(*axis)) for axis in (
        (1, 0, 0), (0, 1, 0), (0, 0, 1),
    )]
    rotation = np.asarray(basis, dtype=np.float64).T
    return np.asarray(origin, dtype=np.float64), rotation


def _body_paths(root, parent_path="/panda/Geometry"):
    children = [node for node in root.findall("body")]
    result = {}
    for body in children:
        name = body.attrib["name"]
        path = f"{parent_path}/{name}"
        result[name] = path
        result.update(_body_paths(body, path))
    return result


def _defaults(root, element_name: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}

    def visit(node, inherited):
        current = dict(inherited)
        for element in node.findall(element_name):
            current.update(element.attrib)
        class_name = node.get("class")
        if class_name:
            result[class_name] = current
        for child in node.findall("default"):
            visit(child, current)

    top = root.find("default")
    if top is not None:
        visit(top, {})
    return result


def _vec4_rotation(quaternion) -> np.ndarray:
    return _quat_matrix((float(quaternion.GetReal()), *tuple(float(v) for v in quaternion.GetImaginary())))


def audit(source_root: Path, stage_path: Path, *, require_v2: bool = False) -> dict:
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade

    xml_path = source_root / "panda.xml"
    root = ET.parse(xml_path).getroot()
    stage = Usd.Stage.Open(str(stage_path), load=Usd.Stage.LoadAll)
    if stage is None:
        raise ValueError(f"cannot open USD stage: {stage_path}")
    worldbody = root.find("worldbody")
    if worldbody is None:
        raise ValueError("source MJCF has no worldbody")
    body_paths = _body_paths(worldbody)
    body_source = {node.attrib["name"]: node for node in root.iter("body")}
    body_prims = {name: stage.GetPrimAtPath(path) for name, path in body_paths.items()}
    if any(not prim for prim in body_prims.values()):
        raise ValueError("one or more MJCF body frames have no USD body prim")

    mesh_assets = {}
    for mesh in root.findall("asset/mesh"):
        file_name = mesh.get("file")
        if not file_name:
            raise ValueError("frozen source contains an unnamed mesh asset file")
        asset_name = mesh.get("name") or Path(file_name).stem
        mesh_assets[asset_name] = mesh
    source_visual_materials = {
        node.attrib["name"]: _numbers(node.attrib["rgba"], (1, 1, 1, 1))
        for node in root.findall("asset/material") if node.get("name") and node.get("rgba")
    }

    geom_defaults = _defaults(root, "geom")
    source_geoms = []
    source_boxes = []
    parent_bodies: dict[str, str | None] = {}
    body_childclasses: dict[str, str] = {}

    def collect_bodies(parent, parent_name=None, inherited_childclass=""):
        for body in parent.findall("body"):
            name = body.attrib["name"]
            parent_bodies[name] = parent_name
            childclass = body.get("childclass", inherited_childclass)
            body_childclasses[name] = childclass
            for ordinal, geom in enumerate(body.findall("geom")):
                effective = dict(geom_defaults.get(geom.get("class", childclass), {}))
                effective.update(geom.attrib)
                if effective.get("type") == "box":
                    source_boxes.append((name, ordinal, effective))
                elif effective.get("mesh"):
                    source_geoms.append((name, ordinal, geom, mesh_assets[effective["mesh"]]))
                else:
                    raise ValueError(f"unsupported Panda source geom at {name}[{ordinal}]")
            collect_bodies(body, name, childclass)

    collect_bodies(worldbody)
    source_mesh_count = len(source_geoms)
    target_mesh_prims = [prim for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)]
    matched_meshes = []
    visual_roles = Counter()
    max_vertex_error = 0.0
    max_triangle_error = 0.0
    total_vertices = 0
    total_triangles = 0
    for body_name, ordinal, geom, asset in source_geoms:
        body_path = body_paths[body_name]
        mesh_name = geom.attrib["mesh"]
        effective_geom = dict(geom_defaults.get(geom.get("class", ""), {}))
        effective_geom.update(geom.attrib)
        is_collision = effective_geom.get("contype", "1") != "0" or effective_geom.get("conaffinity", "1") != "0"
        candidates = [
            prim for prim in target_mesh_prims
            if str(prim.GetParent().GetPath()) == body_path
            and (str(prim.GetName()) == mesh_name or str(prim.GetName()).startswith(mesh_name + "_"))
            and prim.HasAPI(UsdPhysics.CollisionAPI) == is_collision
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"expected one USD mesh for source {body_name}/{mesh_name} "
                f"(collision={is_collision}), found {[str(item.GetPath()) for item in candidates]}"
            )
        prim = candidates[0]
        source_vertices, source_faces = _mesh(source_root / "assets" / asset.attrib["file"])
        scale = np.asarray(_numbers(asset.get("scale"), (1.0, 1.0, 1.0)), dtype=np.float64)
        source_vertices = source_vertices * scale
        target_vertices = np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(), dtype=np.float64)
        target_mesh = UsdGeom.Mesh(prim)
        counts = tuple(int(item) for item in target_mesh.GetFaceVertexCountsAttr().Get())
        indices = tuple(int(item) for item in target_mesh.GetFaceVertexIndicesAttr().Get())
        target_faces = []
        offset = 0
        for count in counts:
            face = indices[offset:offset + count]
            if count < 3:
                raise ValueError(f"degenerate USD face on {prim.GetPath()}")
            for index in range(1, count - 1):
                target_faces.append((face[0], face[index], face[index + 1]))
            offset += count
        target_faces = np.asarray(target_faces, dtype=np.int64)
        # USD may weld STL facet-local vertices while MJCF source STL repeats
        # all three coordinates per facet. Compare unique coordinate sets.
        sorted_source_vertices = _sorted_rows(np.unique(source_vertices, axis=0))
        sorted_target_vertices = _sorted_rows(np.unique(target_vertices, axis=0))
        if sorted_source_vertices.shape != sorted_target_vertices.shape:
            raise ValueError(f"vertex count mismatch at {prim.GetPath()}")
        vertex_error = float(np.max(np.abs(sorted_source_vertices - sorted_target_vertices))) if len(source_vertices) else 0.0
        if vertex_error > GEOMETRY_TOLERANCE_M:
            raise ValueError(f"mesh vertices differ by {vertex_error:g} m at {prim.GetPath()}")
        source_triangles = _triangle_coordinates(source_vertices, source_faces)
        target_triangles = _triangle_coordinates(target_vertices, target_faces)
        if source_triangles.shape != target_triangles.shape:
            raise ValueError(f"triangulated surface count mismatch at {prim.GetPath()}")
        triangle_error = float(np.max(np.abs(source_triangles - target_triangles))) if len(source_triangles) else 0.0
        if triangle_error > GEOMETRY_TOLERANCE_M:
            raise ValueError(f"triangle surface differs by {triangle_error:g} m at {prim.GetPath()}")
        geom_pos = np.asarray(_numbers(effective_geom.get("pos"), (0.0, 0.0, 0.0)), dtype=np.float64)
        geom_rot = _quat_matrix(_numbers(effective_geom.get("quat"), (1.0, 0.0, 0.0, 0.0)))
        target_pos, target_rot = _usd_local_transform(prim)
        local_frame_error = max(
            float(np.max(np.abs(target_pos - geom_pos))),
            float(np.max(np.abs(target_rot - geom_rot))),
        )
        if local_frame_error > FRAME_TOLERANCE_M:
            raise ValueError(f"source geom frame differs by {local_frame_error:g} at {prim.GetPath()}")
        visual_roles["collision_mesh" if is_collision else "visual_mesh"] += 1
        total_vertices += len(source_vertices)
        total_triangles += len(source_faces)
        max_vertex_error = max(max_vertex_error, vertex_error)
        max_triangle_error = max(max_triangle_error, triangle_error)
        color_receipt = None
        if not is_collision:
            material_name = effective_geom.get("material")
            if material_name not in source_visual_materials:
                raise ValueError(f"source visual geom {body_name}/{mesh_name} has no RGBA material")
            expected_rgba = source_visual_materials[material_name]
            display_color = target_mesh.GetDisplayColorAttr().Get()
            display_opacity = target_mesh.GetDisplayOpacityAttr().Get()
            if require_v2:
                actual_color = tuple(float(value) for value in display_color[0]) if display_color else ()
                actual_opacity = float(display_opacity[0]) if display_opacity else None
                color_error = max(
                    max(abs(actual_color[index] - expected_rgba[index]) for index in range(3))
                    if len(actual_color) == 3 else math.inf,
                    abs(actual_opacity - expected_rgba[3]) if actual_opacity is not None else math.inf,
                )
                if color_error > 2.0e-6:
                    raise ValueError(f"source visual color differs by {color_error:g} at {prim.GetPath()}")
            else:
                color_error = None
            color_receipt = {"source_material": material_name, "source_rgba": list(expected_rgba),
                             "max_color_error": color_error}
        matched_meshes.append({
            "source_body": body_name,
            "source_mesh": mesh_name,
            "usd_path": str(prim.GetPath()),
            "role": "collision" if is_collision else "visual",
            "vertex_count": len(source_vertices),
            "triangle_count": len(source_faces),
            "max_vertex_error_m": vertex_error,
            "max_triangle_coordinate_error_m": triangle_error,
            "local_frame_error": local_frame_error,
            "visual_color": color_receipt,
        })

    target_boxes = [
        prim for prim in stage.Traverse()
        if prim.IsA(UsdGeom.Cube) and prim.HasAPI(UsdPhysics.CollisionAPI)
        and str(prim.GetPath()).startswith("/panda/Geometry/")
    ]
    matched_boxes = []
    if len(target_boxes) != len(source_boxes):
        raise ValueError(f"source/USDA finger pad box counts differ: {len(source_boxes)} / {len(target_boxes)}")
    boxes_by_body = {}
    for prim in target_boxes:
        boxes_by_body.setdefault(str(prim.GetParent().GetPath()), []).append(prim)
    max_box_error = 0.0
    for body_name, ordinal, effective in source_boxes:
        body_path = body_paths[body_name]
        candidates = sorted(boxes_by_body.get(body_path, ()), key=lambda item: str(item.GetPath()))
        body_boxes = [row for row in source_boxes if row[0] == body_name]
        local_ordinal = body_boxes.index((body_name, ordinal, effective))
        if local_ordinal >= len(candidates):
            raise ValueError(f"missing USD pad box for {body_name} source geom {ordinal}")
        prim = candidates[local_ordinal]
        size = np.asarray(_numbers(effective.get("size"), ()), dtype=np.float64)
        source_pos = np.asarray(_numbers(effective.get("pos"), (0, 0, 0)), dtype=np.float64)
        target_pos, target_basis = _usd_local_transform(prim)
        target_half_extents = np.linalg.norm(target_basis, axis=0)
        error = max(float(np.max(np.abs(source_pos - target_pos))),
                    float(np.max(np.abs(size - target_half_extents))))
        if error > GEOMETRY_TOLERANCE_M:
            raise ValueError(f"finger pad box mismatch at {prim.GetPath()}: {error:g} m")
        max_box_error = max(max_box_error, error)
        matched_boxes.append({
            "source_body": body_name,
            "source_geom_ordinal": ordinal,
            "usd_path": str(prim.GetPath()),
            "half_extents_m": size.tolist(),
            "position_m": source_pos.tolist(),
            "max_error_m": error,
        })

    body_frame_rows = []
    world_frames = {}

    def visit(body, parent_pos, parent_rot):
        name = body.attrib["name"]
        local_pos = np.asarray(_numbers(body.get("pos"), (0.0, 0.0, 0.0)), dtype=np.float64)
        local_rot = _quat_matrix(_numbers(body.get("quat"), (1.0, 0.0, 0.0, 0.0)))
        world_pos = parent_pos + parent_rot @ local_pos
        world_rot = parent_rot @ local_rot
        world_frames[name] = (world_pos, world_rot)
        prim = body_prims[name]
        usd_pos, usd_rot = _usd_local_transform(prim)
        # The stage's nested Xforms provide the same world transform; use cache below.
        body_frame_rows.append((name, world_pos, world_rot))
        for child in body.findall("body"):
            visit(child, world_pos, world_rot)

    for top in root.findall("worldbody/body"):
        visit(top, np.zeros(3), np.eye(3))
    cache = UsdGeom.XformCache()
    max_body_pos_error = 0.0
    max_body_rot_error = 0.0
    for name, source_pos, source_rot in body_frame_rows:
        matrix = cache.GetLocalToWorldTransform(body_prims[name])
        from pxr import Gf
        usd_pos = np.asarray(matrix.Transform(Gf.Vec3d(0, 0, 0)), dtype=np.float64)
        usd_basis = [matrix.TransformDir(Gf.Vec3d(*axis)) for axis in (
            (1, 0, 0), (0, 1, 0), (0, 0, 1),
        )]
        usd_rot = np.asarray(usd_basis, dtype=np.float64).T
        pos_error = float(np.max(np.abs(source_pos - usd_pos)))
        rot_error = float(np.max(np.abs(source_rot - usd_rot)))
        if pos_error > FRAME_TOLERANCE_M or rot_error > FRAME_TOLERANCE_M:
            raise ValueError(f"body frame mismatch for {name}: position={pos_error:g}, rotation={rot_error:g}")
        max_body_pos_error = max(max_body_pos_error, pos_error)
        max_body_rot_error = max(max_body_rot_error, rot_error)

    joint_defaults = _defaults(root, "joint")
    source_joints = []
    for body in root.iter("body"):
        body_name = body.attrib["name"]
        for joint in body.findall("joint"):
            effective = dict(joint_defaults.get(joint.get("class", body_childclasses[body_name]), {}))
            effective.update(joint.attrib)
            source_joints.append((body_name, joint, effective))
    usd_joints = {
        str(prim.GetName()): prim for prim in stage.Traverse()
        if prim.IsA(UsdPhysics.Joint) and str(prim.GetPath()).startswith("/panda/")
        and str(prim.GetName()) in {row[1].get("name") for row in source_joints}
    }
    if len(source_joints) != 9 or set(usd_joints) != {row[1].get("name") for row in source_joints}:
        raise ValueError("USD must preserve all nine named scalar MJCF joints")
    max_joint_axis_error = 0.0
    max_joint_anchor_error = 0.0
    max_joint_limit_error = 0.0
    joint_rows = []
    for child_name, joint, effective in source_joints:
        name = joint.attrib["name"]
        prim = usd_joints[name]
        usd = UsdPhysics.Joint(prim)
        expected_parent = parent_bodies[child_name]
        expected_body0 = "/panda" if expected_parent is None else body_paths[expected_parent]
        expected_body1 = body_paths[child_name]
        body0 = tuple(str(path) for path in usd.GetBody0Rel().GetTargets())
        body1 = tuple(str(path) for path in usd.GetBody1Rel().GetTargets())
        if body0 != (expected_body0,) or body1 != (expected_body1,):
            raise ValueError(f"joint body mapping differs for {name}: {body0}/{body1}")
        source_axis = np.asarray(_numbers(effective.get("axis"), (0, 0, 1)), dtype=np.float64)
        source_axis /= np.linalg.norm(source_axis)
        axis_token = str(prim.GetAttribute("physics:axis").Get())
        usd_axis = np.asarray({"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis_token], dtype=np.float64)
        rot1 = _vec4_rotation(prim.GetAttribute("physics:localRot1").Get())
        mapped_axis = rot1 @ usd_axis
        axis_error = float(np.max(np.abs(source_axis - mapped_axis)))
        source_joint_pos = np.asarray(_numbers(effective.get("pos"), (0, 0, 0)), dtype=np.float64)
        child_pos = np.asarray(_numbers(body_source[child_name].get("pos"), (0, 0, 0)), dtype=np.float64)
        child_rot = _quat_matrix(_numbers(body_source[child_name].get("quat"), (1, 0, 0, 0)))
        expected_anchor0 = child_pos + child_rot @ source_joint_pos
        expected_anchor1 = source_joint_pos
        anchor0 = np.asarray(prim.GetAttribute("physics:localPos0").Get(), dtype=np.float64)
        anchor1 = np.asarray(prim.GetAttribute("physics:localPos1").Get(), dtype=np.float64)
        anchor_error = max(float(np.max(np.abs(expected_anchor0 - anchor0))),
                           float(np.max(np.abs(expected_anchor1 - anchor1))))
        range_values = _numbers(effective.get("range"), ())
        lower = float(prim.GetAttribute("physics:lowerLimit").Get())
        upper = float(prim.GetAttribute("physics:upperLimit").Get())
        if effective.get("type", "hinge") == "hinge":
            source_lower, source_upper = map(math.degrees, range_values)
        else:
            source_lower, source_upper = range_values
        limit_error = max(abs(source_lower - lower), abs(source_upper - upper))
        if axis_error > FRAME_TOLERANCE_M or anchor_error > FRAME_TOLERANCE_M or limit_error > 2.0e-4:
            raise ValueError(f"joint source mapping differs for {name}: axis={axis_error:g}, anchor={anchor_error:g}, limits={limit_error:g}")
        max_joint_axis_error = max(max_joint_axis_error, axis_error)
        max_joint_anchor_error = max(max_joint_anchor_error, anchor_error)
        max_joint_limit_error = max(max_joint_limit_error, limit_error)
        joint_rows.append({
            "name": name,
            "kind": "revolute" if effective.get("type", "hinge") == "hinge" else "prismatic",
            "body0": expected_body0,
            "body1": expected_body1,
            "axis_child_local": source_axis.tolist(),
            "source_range": list(range_values),
            "max_axis_error": axis_error,
            "max_anchor_error_m": anchor_error,
            "max_limit_error": limit_error,
        })

    inertia_rows = []
    max_mass_error = 0.0
    max_com_error = 0.0
    max_inertia_error = 0.0
    for name, body in body_source.items():
        inertial = body.find("inertial")
        if inertial is None:
            continue
        prim = body_prims[name]
        api = UsdPhysics.MassAPI(prim)
        mass = float(inertial.attrib["mass"])
        com = np.asarray(_numbers(inertial.get("pos"), (0.0, 0.0, 0.0)), dtype=np.float64)
        if inertial.get("fullinertia"):
            ixx, iyy, izz, ixy, ixz, iyz = _numbers(inertial.get("fullinertia"), ())
            source_tensor = np.asarray([
                [ixx, ixy, ixz], [ixy, iyy, iyz], [ixz, iyz, izz],
            ], dtype=np.float64)
        else:
            inertia = np.asarray(_numbers(inertial.get("diaginertia"), ()), dtype=np.float64)
            quat = _numbers(inertial.get("quat"), (1.0, 0.0, 0.0, 0.0))
            source_rotation = _quat_matrix(quat)
            source_tensor = source_rotation @ np.diag(inertia) @ source_rotation.T
        usd_mass = float(api.GetMassAttr().Get())
        usd_com = np.asarray(api.GetCenterOfMassAttr().Get(), dtype=np.float64)
        usd_diag = np.asarray(api.GetDiagonalInertiaAttr().Get(), dtype=np.float64)
        usd_quat = api.GetPrincipalAxesAttr().Get()
        usd_wxyz = (float(usd_quat.GetReal()), *tuple(float(value) for value in usd_quat.GetImaginary()))
        usd_rot = _quat_matrix(usd_wxyz)
        usd_tensor = usd_rot @ np.diag(usd_diag) @ usd_rot.T
        mass_error = abs(mass - usd_mass)
        com_error = float(np.max(np.abs(com - usd_com)))
        inertia_error = float(np.max(np.abs(source_tensor - usd_tensor)))
        mass_ulp = float(np.spacing(np.float32(max(abs(mass), abs(usd_mass)))))
        com_ulp = float(np.max(np.spacing(np.asarray(np.maximum(np.abs(com), np.abs(usd_com)), dtype=np.float32))))
        inertia_scale = max(float(np.max(np.abs(source_tensor))), float(np.max(np.abs(usd_diag))))
        inertia_ulp = float(np.spacing(np.float32(inertia_scale)))
        mass_tolerance = MASS_FLOAT32_ULPS * mass_ulp
        com_tolerance = COM_FLOAT32_ULPS * com_ulp
        inertia_tolerance = INERTIA_FLOAT32_ULPS * inertia_ulp
        if mass_error > mass_tolerance or com_error > com_tolerance or inertia_error > inertia_tolerance:
            raise ValueError(
                f"mass/COM/full inertia mismatch for {name}: "
                f"{mass_error:g}>{mass_tolerance:g}/{com_error:g}>{com_tolerance:g}/"
                f"{inertia_error:g}>{inertia_tolerance:g}"
            )
        max_mass_error = max(max_mass_error, mass_error)
        max_com_error = max(max_com_error, com_error)
        max_inertia_error = max(max_inertia_error, inertia_error)
        inertia_rows.append({
            "body": name,
            "mass_kg": mass,
            "center_of_mass_m": com.tolist(),
            "source_inertia_tensor_kg_m2": source_tensor.tolist(),
            "max_mass_error_kg": mass_error,
            "mass_tolerance_kg": mass_tolerance,
            "max_com_error_m": com_error,
            "com_tolerance_m": com_tolerance,
            "max_full_inertia_error_kg_m2": inertia_error,
            "full_inertia_tolerance_kg_m2": inertia_tolerance,
        })

    collision_shapes = [
        prim for prim in stage.Traverse()
        if prim.HasAPI(UsdPhysics.CollisionAPI) and str(prim.GetPath()).startswith("/panda/Geometry/")
    ]
    collision_meshes = [prim for prim in collision_shapes if prim.IsA(UsdGeom.Mesh)]
    bound_material_rows = []
    for prim in collision_shapes:
        bound, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial("physics")
        if bound:
            row = {"shape": str(prim.GetPath()), "material": str(bound.GetPath())}
            if bound.GetPrim().HasAPI(UsdPhysics.MaterialAPI):
                api = UsdPhysics.MaterialAPI(bound.GetPrim())
                row["static_friction"] = api.GetStaticFrictionAttr().Get()
                row["dynamic_friction"] = api.GetDynamicFrictionAttr().Get()
                row["restitution"] = api.GetRestitutionAttr().Get()
            bound_material_rows.append(row)
    if require_v2:
        if len(collision_shapes) != len(collision_meshes) + len(source_boxes) or len(bound_material_rows) != len(collision_shapes):
            raise ValueError("DG02 v2 must bind source material to every Panda collision shape and no other Panda prim")
        if any((row.get("static_friction"), row.get("dynamic_friction"), row.get("restitution")) != (1.0, 1.0, 0.0)
               for row in bound_material_rows):
            raise ValueError("DG02 v2 Panda collision MaterialAPI values differ from source-effective defaults")
    joint_prims = [prim for prim in stage.Traverse() if prim.IsA(UsdPhysics.Joint)
                   and str(prim.GetPath()).startswith("/panda/")]
    explicit_excludes = root.find("contact")
    source_excludes = [] if explicit_excludes is None else [
        tuple(sorted((node.attrib["body1"], node.attrib["body2"])))
        for node in explicit_excludes.findall("exclude")
    ]
    filtered_pairs = []
    for prim in stage.Traverse():
        relation = prim.GetRelationship("physics:filteredPairs")
        if relation:
            for target in relation.GetTargets():
                filtered_pairs.append((str(prim.GetPath()), str(target)))
    expected_filtered_pairs = [
        ("/panda/Geometry/link0", "/panda/Geometry/link0/link1")
        for pair in source_excludes if set(pair) == {"link0", "link1"}
    ]
    if source_excludes and filtered_pairs != expected_filtered_pairs:
        raise ValueError(f"MJCF/USDA explicit contact filters differ: {source_excludes}/{filtered_pairs}")
    if len(source_excludes) != 1 or len(filtered_pairs) != 1:
        raise ValueError("frozen Panda MJCF/USD must preserve its single explicit link0-link1 contact exclusion")
    free_cube = stage.GetPrimAtPath("/F04Scene/free_cube")
    support = stage.GetPrimAtPath("/F04Scene/support")
    if not free_cube or not support:
        raise ValueError("task free cube/support prims are missing")
    scene_material_bindings = {}
    for prim in (free_cube, support):
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial("physics")
        scene_material_bindings[str(prim.GetPath())] = str(material.GetPath()) if material else None
    if scene_material_bindings != {"/F04Scene/free_cube": None, "/F04Scene/support": None}:
        raise ValueError("DG02 USD changed the accepted task scene's unbound material recipe")
    return {
        "schema_version": "f05-dg02-usd-source-audit-v1",
        "source_xml": str(xml_path),
        "source_xml_sha256": __import__("hashlib").sha256(xml_path.read_bytes()).hexdigest(),
        "usd_stage": str(stage_path),
        "usd_stage_sha256": __import__("hashlib").sha256(stage_path.read_bytes()).hexdigest(),
        "tolerances": {
            "geometry_coordinate_m": GEOMETRY_TOLERANCE_M,
            "body_and_geom_frame": FRAME_TOLERANCE_M,
            "mass_float32_ulps": MASS_FLOAT32_ULPS,
            "com_float32_ulps": COM_FLOAT32_ULPS,
            "full_inertia_float32_ulps": INERTIA_FLOAT32_ULPS,
        },
        "panda": {
            "source_mesh_geometry_count": source_mesh_count,
            "matched_mesh_geometry_count": len(matched_meshes),
            "source_total_vertices": total_vertices,
            "source_total_triangles": total_triangles,
            "max_vertex_error_m": max_vertex_error,
            "max_triangle_coordinate_error_m": max_triangle_error,
            "roles": dict(visual_roles),
            "meshes": matched_meshes,
            "source_box_geometry_count": len(source_boxes),
            "matched_box_geometry_count": len(matched_boxes),
            "max_box_geometry_error_m": max_box_error,
            "boxes": matched_boxes,
            "body_frame_count": len(body_frame_rows),
            "max_body_position_error_m": max_body_pos_error,
            "max_body_rotation_matrix_error": max_body_rot_error,
            "inertial_body_count": len(inertia_rows),
            "max_mass_error_kg": max_mass_error,
            "max_com_error_m": max_com_error,
            "max_full_inertia_tensor_error_kg_m2": max_inertia_error,
            "inertial_bodies": inertia_rows,
            "collision_mesh_count": len(collision_meshes),
            "collision_shape_count": len(collision_shapes),
            "collision_shapes_with_physics_material_binding": len(bound_material_rows),
            "collision_material_bindings": bound_material_rows,
            "source_explicit_contact_excludes": source_excludes,
            "usd_filtered_pair_relations": filtered_pairs,
            "panda_joint_count": len(joint_prims),
            "joint_collision_disabled_count": sum(
                1 for prim in joint_prims
                if prim.GetAttribute("physics:collisionEnabled")
                and prim.GetAttribute("physics:collisionEnabled").Get() is False
            ),
            "source_scalar_joint_count": len(source_joints),
            "max_joint_axis_error": max_joint_axis_error,
            "max_joint_anchor_error_m": max_joint_anchor_error,
            "max_joint_limit_error": max_joint_limit_error,
            "joints": joint_rows,
        },
        "task_scene": {
            "free_cube_prim_exists": bool(free_cube),
            "support_prim_exists": bool(support),
            "physics_material_bindings": scene_material_bindings,
        },
        "passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-v2", action="store_true")
    args = parser.parse_args()
    result = audit(args.source_root, args.stage, require_v2=args.require_v2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": result["passed"],
        "source_mesh_geometry_count": result["panda"]["source_mesh_geometry_count"],
        "source_total_vertices": result["panda"]["source_total_vertices"],
        "source_total_triangles": result["panda"]["source_total_triangles"],
        "body_frame_count": result["panda"]["body_frame_count"],
        "inertial_body_count": result["panda"]["inertial_body_count"],
        "max_vertex_error_m": result["panda"]["max_vertex_error_m"],
        "max_triangle_coordinate_error_m": result["panda"]["max_triangle_coordinate_error_m"],
        "max_full_inertia_tensor_error_kg_m2": result["panda"]["max_full_inertia_tensor_error_kg_m2"],
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
