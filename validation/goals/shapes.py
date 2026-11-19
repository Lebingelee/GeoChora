"""Collision-shape model and planar distances for the scene objects (metres, Z up)."""
from __future__ import annotations

import math

import numpy as np

from validation.geometry import hull2, interior_margin2, quat_wxyz_to_matrix


class MissingEvidence(Exception):
    """Raised inside predicate code; becomes an unknown result with this reason."""


class Body:
    """One object posed in the world.

    Balls: sphere about the origin (diameter = size_m[0]).
    Bricks: box with local x/y centred on the origin and local z in [0, size_z]
    (manifest origin sits on the base plane; size_m is the untransformed bound incl. studs,
    stud axis = body +Z). Both facts are inferred from the manifest/trace heights.
    """

    def __init__(self, entry, position, quaternion_wxyz):
        self.name = entry['name']
        self.kind = entry['kind']
        size = [float(x) for x in entry['size_m']]
        self.size = size
        pos = np.asarray(position, float)
        if self.kind == 'ball':
            self.R = np.eye(3) if quaternion_wxyz is None else quat_wxyz_to_matrix(quaternion_wxyz)
            self.radius = size[0] / 2
            self.center = pos
            self.lowest_z = pos[2] - self.radius
            self.top_z = pos[2] + self.radius
            self.footprint = ('disc', pos[:2].copy(), self.radius)
            self.long_ratio = 1.0
            self.long_axis_xy = None
            return
        if quaternion_wxyz is None:
            raise MissingEvidence(f'orientation_missing:{self.name}')
        self.R = quat_wxyz_to_matrix(quaternion_wxyz)
        self.pos = pos
        sx, sy, sz = size
        local = np.array([[x, y, z] for x in (-sx / 2, sx / 2) for y in (-sy / 2, sy / 2) for z in (0.0, sz)])
        self.corners = pos + local @ self.R.T
        self.center = pos + self.R @ np.array([0.0, 0.0, sz / 2])
        self.lowest_z = float(self.corners[:, 2].min())
        self.top_z = float(self.corners[:, 2].max())
        self.footprint = ('poly', hull2(self.corners[:, :2]))
        self.long_ratio = max(sx, sy) / min(sx, sy)
        axis = self.R[:, 0] if sx >= sy else self.R[:, 1]
        self.long_axis_xy = axis[:2].copy()
        self.long_axis_horizontal = float(np.linalg.norm(axis[:2]))

    @property
    def z_axis(self):
        return self.R[:, 2]

    def min_width(self):
        kind, *data = self.footprint
        if kind == 'disc':
            return 2 * data[1]
        poly = data[0]
        edges = np.roll(poly, -1, axis=0) - poly
        normals = np.column_stack((-edges[:, 1], edges[:, 0]))
        normals /= np.linalg.norm(normals, axis=1)[:, None]
        proj = poly @ normals.T
        return float((proj.max(0) - proj.min(0)).min())

    def local_box_distance(self, point):
        """Euclidean distance from a world point to the collision shape (0 inside)."""
        p = np.asarray(point, float)
        if self.kind == 'ball':
            return max(0.0, float(np.linalg.norm(p - self.center)) - self.radius)
        q = self.R.T @ (p - self.pos)
        sx, sy, sz = self.size
        lo, hi = np.array([-sx / 2, -sy / 2, 0.0]), np.array([sx / 2, sy / 2, sz])
        return float(np.linalg.norm(np.maximum(np.maximum(lo - q, q - hi), 0.0)))


def _seg_point(p, a, b):
    ab = b - a
    t = 0.0 if not ab.any() else float(np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0, 1))
    return float(np.linalg.norm(p - (a + t * ab)))


def _poly_poly(P, Q):
    edges = np.concatenate((np.roll(P, -1, axis=0) - P, np.roll(Q, -1, axis=0) - Q))
    axes = np.column_stack((-edges[:, 1], edges[:, 0]))
    axes = axes[np.linalg.norm(axes, axis=1) > 1e-12]
    axes /= np.linalg.norm(axes, axis=1)[:, None]
    pa, pb = P @ axes.T, Q @ axes.T
    if np.max(np.maximum(pa.min(0) - pb.max(0), pb.min(0) - pa.max(0))) < 0:
        return 0.0  # overlapping footprints
    best = math.inf
    for A, B in ((P, Q), (Q, P)):
        for p in A:
            for a, b in zip(B, np.roll(B, -1, axis=0)):
                best = min(best, _seg_point(p, a, b))
    return best


def point_poly_distance(point, poly):
    """Distance from a point to a convex polygon (0 inside)."""
    point = np.asarray(point, float)
    if _inside(point, poly) >= 0:
        return 0.0
    return min(_seg_point(point, a, b) for a, b in zip(poly, np.roll(poly, -1, axis=0)))


def _inside(point, poly):
    """Signed inward margin of a point in a CCW convex polygon (negative outside).

    Shares ``validation.geometry.interior_margin2`` with the terminal review route; the local
    arithmetic below is only reached for degenerate (< 3 vertex) polygons, as before.
    """
    margin = interior_margin2(point, poly)
    if margin is not None:
        return margin
    edge = np.roll(poly, -1, axis=0) - poly
    length = np.linalg.norm(edge, axis=1)
    good = length > 1e-12
    delta = np.asarray(point) - poly
    return float(np.min((edge[good, 0] * delta[good, 1] - edge[good, 1] * delta[good, 0]) / length[good]))


def point_footprint_margin(point, footprint):
    """Signed inward margin of a point w.r.t. a footprint (negative = outside)."""
    kind, *data = footprint
    point = np.asarray(point, float)
    if kind == 'disc':
        return data[1] - float(np.linalg.norm(point - data[0]))
    return _inside(point, data[0])


def footprint_gap(a, b):
    """Horizontal gap between two footprints (0 when they touch or overlap)."""
    (ka, *da), (kb, *db) = a.footprint, b.footprint
    if ka == 'disc' and kb == 'disc':
        return max(0.0, float(np.linalg.norm(da[0] - db[0])) - da[1] - db[1])
    if ka == 'disc':
        return max(0.0, point_poly_distance(da[0], db[0]) - da[1])
    if kb == 'disc':
        return max(0.0, point_poly_distance(db[0], da[0]) - db[1])
    return _poly_poly(da[0], db[0])


def footprint_clearance_in_rect(footprint, x_range, y_range):
    """Smallest inward clearance of a footprint inside an axis-aligned rectangle."""
    kind, *data = footprint
    if kind == 'disc':
        (c, r) = data
        return float(min(c[0] - x_range[0], x_range[1] - c[0], c[1] - y_range[0], y_range[1] - c[1]) - r)
    pts = data[0]
    return float(min((pts[:, 0] - x_range[0]).min(), (x_range[1] - pts[:, 0]).min(),
                     (pts[:, 1] - y_range[0]).min(), (y_range[1] - pts[:, 1]).min()))
