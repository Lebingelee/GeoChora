"""Internal convex-mesh geometry for offline terminal evidence (metres, Z-up).

Uses the supplied collision pieces, not an enclosing box as a contact surface.
This is a geometric compatibility check, not a dynamics/contact-force solver.
"""
from dataclasses import dataclass
from itertools import product

import numpy as np


def hull2(points):
    points = sorted(set(map(tuple, np.asarray(points, float))))
    if len(points) < 3:
        return np.asarray(points).reshape(-1, 2)

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    halves = []
    for seq in (points, points[::-1]):
        part = []
        for p in seq:
            while len(part) > 1 and cross(part[-2], part[-1], p) <= 1e-14:
                part.pop()
            part.append(p)
        halves.extend(part[:-1])
    return np.asarray(halves)


def intersect2(subject, clip):
    """Intersection of CCW convex polygons; an empty/degenerate patch is valid."""
    result = np.asarray(subject, float)
    for a, b in zip(clip, np.roll(clip, -1, axis=0)):
        if len(result) == 0:
            break
        edge = b - a
        signed = lambda p: edge[0] * (p[1] - a[1]) - edge[1] * (p[0] - a[0])
        out = []
        for p, q in zip(result, np.roll(result, -1, axis=0)):
            dp, dq = signed(p), signed(q)
            if dp >= -1e-14:
                out.append(p)
            if (dp >= 0) != (dq >= 0) and abs(dp - dq) > 1e-16:
                out.append(p + dp / (dp - dq) * (q - p))
        result = np.asarray(out).reshape(-1, 2)
    return result


def interior_margin2(point, polygon):
    if len(polygon) < 3:
        return None
    edge = np.roll(polygon, -1, axis=0) - polygon
    length = np.linalg.norm(edge, axis=1)
    good = length > 1e-12
    delta = np.asarray(point) - polygon
    return float(np.min((edge[good, 0] * delta[good, 1] - edge[good, 1] * delta[good, 0]) / length[good]))


def directions(vectors):
    values = np.asarray(vectors, float).reshape(-1, 3)
    lengths = np.linalg.norm(values, axis=1)
    values = values[lengths > 1e-10] / lengths[lengths > 1e-10, None]
    if not len(values):
        return values
    signs = np.array([1 if v[np.flatnonzero(np.abs(v) > 1e-8)[0]] > 0 else -1 for v in values])
    values *= signs[:, None]
    _, indices = np.unique(np.round(values, 8), axis=0, return_index=True)
    return values[indices]


@dataclass
class ConvexPiece:
    vertices: np.ndarray
    faces: list  # (outward normal, plane offset, face vertices)
    normals: np.ndarray
    edges: np.ndarray

    @classmethod
    def from_mesh(cls, vertices, triangles):
        v, t = np.asarray(vertices, float), np.asarray(triangles)
        if (v.ndim != 2 or v.shape[1] != 3 or len(v) < 4 or not np.isfinite(v).all()
                or t.ndim != 2 or t.shape[1] != 3 or not np.issubdtype(t.dtype, np.integer)
                or len(t) < 4 or t.min() < 0 or t.max() >= len(v)
                or np.linalg.matrix_rank(v - v.mean(0)) < 3):
            raise ValueError("finite closed convex triangular mesh required")
        if len({tuple(sorted(map(int, tri))) for tri in t}) != len(t):
            raise ValueError("duplicate collision triangle")
        if len(set(map(int, t.flat))) != len(v):
            raise ValueError("unused collision vertices")
        counts, directed, adjacent, groups, edge_vectors = {}, {}, {}, {}, []
        center, volume6 = v.mean(0), 0.0
        for tri in t:
            a, b, c = v[tri]
            n = np.cross(b - a, c - a)
            length = np.linalg.norm(n)
            if length < 1e-14:
                raise ValueError("degenerate collision triangle")
            n /= length
            if n @ (a - center) < 0:
                n = -n
                tri = tri[[0, 2, 1]]
                b, c = c, b
            volume6 += float((a - center) @ np.cross(b - center, c - center))
            d = float(n @ a)
            if np.max(v @ n - d) > 1e-7:
                raise ValueError("collision piece is not convex")
            key = tuple(np.round(np.r_[n, d], 7))
            groups.setdefault(key, [n, d, set()])[2].update(map(int, tri))
            for i, j in zip(tri, np.roll(tri, -1)):
                edge = tuple(sorted((int(i), int(j))))
                counts[edge] = counts.get(edge, 0) + 1
                directed[edge] = directed.get(edge, 0) + (1 if i < j else -1)
                adjacent.setdefault(int(i), set()).add(int(j))
                adjacent.setdefault(int(j), set()).add(int(i))
                edge_vectors.append(v[j] - v[i])
        if any(count != 2 for count in counts.values()) or any(directed.values()):
            raise ValueError("collision mesh must be closed without split vertex seams")
        seen, pending = set(), [0]
        while pending:
            index = pending.pop()
            if index not in seen:
                seen.add(index)
                pending.extend(adjacent[index] - seen)
        if len(seen) != len(v) or volume6 <= 1e-12 * float(np.prod(np.ptp(v, axis=0))):
            raise ValueError("collision piece must be one connected positive-volume shell")
        faces = [(n, d, v[sorted(ids)]) for n, d, ids in groups.values()]
        return cls(v, faces, directions([f[0] for f in faces]), directions(edge_vectors))

    def transformed(self, rotation, origin):
        return ConvexPiece(self.vertices @ rotation.T + origin,
            [(rotation @ n, d + (rotation @ n) @ origin, v @ rotation.T + origin) for n, d, v in self.faces],
            self.normals @ rotation.T, self.edges @ rotation.T)


def box_piece(bounds):
    lo, hi = np.asarray(bounds, float)
    if not np.isfinite([lo, hi]).all() or np.any(lo >= hi):
        raise ValueError("invalid box bounds")
    v = np.array(list(product(*zip(lo, hi))))
    # Binary vertex indexing: x=4, y=2, z=1.
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
             (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    t = [[q[0], q[1], q[2]] for q in quads] + [[q[0], q[2], q[3]] for q in quads]
    return ConvexPiece.from_mesh(v, t)


def separation(a, b):
    """Maximum signed SAT gap (negative means overlap); not Euclidean distance."""
    axes = directions(np.concatenate((a.normals, b.normals,
        np.cross(a.edges[:, None, :], b.edges[None, :, :]).reshape(-1, 3))))
    pa, pb = a.vertices @ axes.T, b.vertices @ axes.T
    return float(np.max(np.maximum(pa.min(0) - pb.max(0), pb.min(0) - pa.max(0))))


def horizontal_separation(a, b):
    """Signed SAT gap between the collision pieces' world-XY projections."""
    av, bv = hull2(a.vertices[:, :2]), hull2(b.vertices[:, :2])
    if len(av) < 3 or len(bv) < 3:
        raise ValueError('volumetric collision pieces need nondegenerate XY projections')
    edges = np.concatenate((np.roll(av, -1, axis=0) - av,
                            np.roll(bv, -1, axis=0) - bv))
    axes = np.column_stack((-edges[:, 1], edges[:, 0]))
    axes /= np.linalg.norm(axes, axis=1)[:, None]
    pa, pb = av @ axes.T, bv @ axes.T
    return float(np.max(np.maximum(pa.min(0) - pb.max(0), pb.min(0) - pa.max(0))))


def support_measurements(lower, upper, center_world, tolerance_m, reject_m):
    """Near-contact patches beneath a geometric center, with penetration guard.

    Only upward/downward faces with |normal.z| >= 0.5 are supported. A positive
    result is compatibility with gravity support, not a measured force or COM.
    """
    patches, ambiguous_patches, worst_penetration = [], [], 0.0
    possible_contact = False
    for a, b in product(lower, upper):
        av, bv = a.vertices, b.vertices
        gap = np.maximum(av.min(0) - bv.max(0), bv.min(0) - av.max(0)).max()
        if gap > reject_m:
            continue
        sat = separation(a, b)
        if sat > reject_m:
            continue
        possible_contact = True
        worst_penetration = max(worst_penetration, -sat)
        if sat < -reject_m:
            return False, {"penetration_m": worst_penetration, "reason": "deep_interpenetration"}
        for an, ad, af in a.faces:
            if an[2] < 0.5:
                continue
            ap = hull2(af[:, :2])
            if len(ap) < 3:
                continue
            for bn, bd, bf in b.faces:
                if bn[2] > -0.5:
                    continue
                bp = hull2(bf[:, :2])
                if len(bp) < 3:
                    continue
                patch = intersect2(ap, bp)
                if len(patch) < 3:
                    continue
                dz = (bd - patch @ bn[:2]) / bn[2] - (ad - patch @ an[:2]) / an[2]
                if np.max(np.abs(dz)) <= reject_m:
                    ambiguous_patches.extend(patch)
                    if np.max(np.abs(dz)) <= tolerance_m:
                        patches.extend(patch)
    margin = interior_margin2(center_world[:2], hull2(patches)) if patches else None
    possible_margin = interior_margin2(center_world[:2], hull2(ambiguous_patches)) if ambiguous_patches else None
    metrics = {"penetration_m": worst_penetration, "center_support_margin_m": margin,
               "possible_center_support_margin_m": possible_margin}
    if margin is not None and margin >= tolerance_m and worst_penetration <= tolerance_m:
        return True, metrics
    if not possible_contact:
        return False, {**metrics, "reason": "no_near_contact"}
    # Unsupported face orientation/friction/edge contacts remain unresolved.
    if possible_margin is not None and possible_margin < -reject_m:
        return False, {**metrics, "reason": "center_outside_support_patch"}
    return None, {**metrics, "reason": "support_boundary_or_unsupported_contact"}

_EPSILON = 1.0e-12


def normalize_quat_wxyz(quaternion: np.ndarray) -> np.ndarray:
    """返回单位 WXYZ 四元数；零范数输入无有效旋转语义。"""
    value = np.asarray(quaternion, dtype=np.float64).reshape(4)
    norm = float(np.linalg.norm(value))
    if not np.isfinite(value).all() or norm <= _EPSILON:
        raise ValueError("quaternion must be finite with positive norm")
    return value / norm


def quat_wxyz_to_matrix(quaternion: np.ndarray) -> np.ndarray:
    """将单位化的 WXYZ 四元数转换为 3×3 local-to-world 旋转矩阵。"""
    w, x, y, z = normalize_quat_wxyz(quaternion)
    return np.array((
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
        (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
        (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
    ), dtype=np.float64)
