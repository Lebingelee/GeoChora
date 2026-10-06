"""Bounded provider-neutral static triangle source; dynamic cameras are separate."""
from dataclasses import dataclass
import hashlib
import json
import numpy as np
from ...artifacts.contracts import Contract, _name


@dataclass(frozen=True)
class TriangleMesh(Contract):
    semantic_id: str
    vertices_world: tuple[tuple[float,float,float], ...]
    faces: tuple[tuple[int,int,int], ...]
    color_rgb: tuple[float,float,float]

    def validate(self):
        _name(self.semantic_id)
        if len(self.vertices_world) < 4 or not self.faces:
            raise ValueError('nonempty volume mesh required by native pairings')
        if any(i < 0 or i >= len(self.vertices_world) for face in self.faces for i in face):
            raise ValueError('mesh face outside vertices')
        if any(not 0 <= v <= 1 for v in self.color_rgb):
            raise ValueError('invalid RGB material')
        points = np.array(self.vertices_world)
        if any(np.linalg.norm(np.cross(points[b]-points[a],points[c]-points[a])) <= 1e-12 for a,b,c in self.faces):
            raise ValueError('degenerate triangle')


@dataclass(frozen=True)
class CameraRenderSource(Contract):
    schema_version: str
    task_artifact_hash: str
    meshes: tuple[TriangleMesh, ...]

    def validate(self):
        if self.schema_version != 'camera-static-triangles-v0' or len(self.task_artifact_hash) != 64:
            raise ValueError('unsupported render source/schema')
        if not self.meshes or len({m.semantic_id for m in self.meshes}) != len(self.meshes):
            raise ValueError('mesh names must be unique and nonempty')

    @property
    def identity_hash(self):
        return hashlib.sha256(json.dumps(self.to_mapping(),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
