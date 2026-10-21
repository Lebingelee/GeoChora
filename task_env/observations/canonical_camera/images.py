"""Strict provider-independent image normalization and canonical observation."""
from dataclasses import dataclass
import hashlib
import json
import numpy as np
from .contracts import ResolvedCameraMetadata


def normalize_rgb(native, camera):
    values = np.asarray(native)
    if values.shape != (camera.height,camera.width,3):
        raise ValueError('native RGB must be HWC with declared resolution')
    if values.dtype == np.uint8:
        values = values.astype(np.float32)/np.float32(255)
    elif values.dtype == np.float32:
        if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1):
            raise ValueError('native float32 RGB outside [0,1]')
    else:
        raise ValueError('native RGB must be float32 or uint8')
    if camera.rgb_dtype == 'uint8':
        values = np.rint(values*255).astype(np.uint8)
    if camera.rgb_layout == 'CHW':
        values = values.transpose(2,0,1)
    return np.ascontiguousarray(values)


def _valid_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in '0123456789abcdef' for character in value)
    )


@dataclass(frozen=True)
class CanonicalEntityLabelV1:
    """One positive public label mapped to a canonical Scene Entity ID."""

    label: int
    entity_id: str

    def validate(self):
        if type(self.label) is not int or not 1 <= self.label <= np.iinfo(np.uint32).max:
            raise ValueError('entity segmentation labels must be positive uint32 values; zero is background')
        if not isinstance(self.entity_id, str) or not self.entity_id or self.entity_id.strip() != self.entity_id:
            raise ValueError('entity segmentation labels require a canonical Entity ID')

    def to_mapping(self):
        self.validate()
        return {'label': self.label, 'entity_id': self.entity_id}

    @classmethod
    def from_mapping(cls, values):
        if not isinstance(values, dict) or set(values) != {'label', 'entity_id'}:
            raise ValueError('entity label mapping must contain exactly label and entity_id')
        return cls(**values)


@dataclass(frozen=True)
class CanonicalEntityLabelMapV1:
    """Dense deterministic Entity labels bound to one capture publication."""

    schema_version: str
    task_artifact_hash: str
    scene_identity_hash: str
    render_source_identity_hash: str
    camera_id: str
    scene_instance_id: str
    provider_materialization_id: str
    episode_id: str
    reset_sample_id: str
    state_boundary_id: str
    state_revision: int
    control_step: int
    simulation_time_s: float
    capture_identity_hash: str
    labels: tuple[CanonicalEntityLabelV1, ...]

    def __post_init__(self):
        object.__setattr__(self, 'labels', tuple(self.labels))
        self.validate()

    def validate(self):
        if self.schema_version != 'canonical-entity-label-map-v1':
            raise ValueError(f'unsupported canonical Entity label map schema: {self.schema_version!r}')
        for value in (
            self.task_artifact_hash, self.scene_identity_hash,
            self.render_source_identity_hash, self.capture_identity_hash,
        ):
            if not _valid_sha256(value):
                raise ValueError('Entity label map requires lowercase SHA-256 identities')
        for name in (
            'camera_id', 'scene_instance_id', 'provider_materialization_id',
            'episode_id', 'reset_sample_id', 'state_boundary_id',
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value.strip() != value:
                raise ValueError(f'Entity label map requires a non-empty {name}')
        for name in ('state_revision', 'control_step'):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f'Entity label map {name} must be a non-negative integer')
        if isinstance(self.simulation_time_s, bool) or not isinstance(self.simulation_time_s, (int, float)):
            raise ValueError('Entity label map simulation time must be finite and non-negative')
        if not np.isfinite(self.simulation_time_s) or self.simulation_time_s < 0:
            raise ValueError('Entity label map simulation time must be finite and non-negative')
        if not all(isinstance(item, CanonicalEntityLabelV1) for item in self.labels):
            raise TypeError('Entity label map entries must use canonical-entity-label-v1 values')
        for item in self.labels:
            item.validate()
        expected = tuple(sorted(self.labels, key=lambda item: item.entity_id))
        if self.labels != expected:
            raise ValueError('Entity label map entries must be ordered by canonical Entity ID')
        if tuple(item.label for item in self.labels) != tuple(range(1, len(self.labels) + 1)):
            raise ValueError('Entity labels must be dense positive integers; zero is reserved for background')
        if len({item.entity_id for item in self.labels}) != len(self.labels):
            raise ValueError('Entity label map contains duplicate canonical Entity IDs')

    def to_mapping(self):
        self.validate()
        return {
            'schema_version': self.schema_version,
            'task_artifact_hash': self.task_artifact_hash,
            'scene_identity_hash': self.scene_identity_hash,
            'render_source_identity_hash': self.render_source_identity_hash,
            'camera_id': self.camera_id,
            'scene_instance_id': self.scene_instance_id,
            'provider_materialization_id': self.provider_materialization_id,
            'episode_id': self.episode_id,
            'reset_sample_id': self.reset_sample_id,
            'state_boundary_id': self.state_boundary_id,
            'state_revision': self.state_revision,
            'control_step': self.control_step,
            'simulation_time_s': float(self.simulation_time_s),
            'capture_identity_hash': self.capture_identity_hash,
            'labels': [item.to_mapping() for item in self.labels],
        }

    @classmethod
    def from_mapping(cls, values):
        fields = {
            'schema_version', 'task_artifact_hash', 'scene_identity_hash',
            'render_source_identity_hash', 'camera_id', 'scene_instance_id',
            'provider_materialization_id', 'episode_id', 'reset_sample_id',
            'state_boundary_id', 'state_revision', 'control_step',
            'simulation_time_s', 'capture_identity_hash', 'labels',
        }
        if not isinstance(values, dict) or set(values) != fields:
            raise ValueError('canonical Entity label map contains unknown or missing fields')
        rows = values['labels']
        if not isinstance(rows, list):
            raise ValueError('canonical Entity label map labels must be a list')
        return cls(**{
            **values,
            'labels': tuple(CanonicalEntityLabelV1.from_mapping(item) for item in rows),
        })

    @property
    def identity_hash(self):
        payload = json.dumps(self.to_mapping(), sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class CanonicalEntityInstanceSegmentationV1:
    """Read-only H×W uint32 Entity mask and its capture-bound label map.

    Label 0 is background. Native renderer object/geometry IDs never cross
    this observation boundary.
    """

    schema_version: str
    mask: np.ndarray
    background_label: int
    label_map: CanonicalEntityLabelMapV1

    def __post_init__(self):
        self.validate()

    def validate(self):
        if self.schema_version != 'canonical-entity-instance-segmentation-v1':
            raise ValueError(f'unsupported Entity segmentation schema: {self.schema_version!r}')
        if type(self.background_label) is not int or self.background_label != 0:
            raise ValueError('Entity segmentation background label is fixed at zero')
        if not isinstance(self.label_map, CanonicalEntityLabelMapV1):
            raise TypeError('Entity segmentation requires canonical-entity-label-map-v1')
        self.label_map.validate()
        values = np.asarray(self.mask)
        if values.ndim != 2 or values.dtype != np.dtype(np.uint32) or min(values.shape) < 1:
            raise ValueError('Entity segmentation mask must be H×W uint32')
        allowed = {0, *(item.label for item in self.label_map.labels)}
        if not set(np.unique(values).tolist()).issubset(allowed):
            raise ValueError('Entity segmentation mask contains a label absent from its label map')
        values = np.ascontiguousarray(values).copy()
        values.setflags(write=False)
        object.__setattr__(self, 'mask', values)

    @property
    def mask_sha256(self):
        self.validate()
        return hashlib.sha256(self.mask.tobytes(order='C')).hexdigest()

    @property
    def identity_hash(self):
        payload = {
            'schema_version': self.schema_version,
            'background_label': self.background_label,
            'mask_shape': list(self.mask.shape),
            'mask_dtype': str(self.mask.dtype),
            'mask_sha256': self.mask_sha256,
            'label_map': self.label_map.to_mapping(),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()

    def to_mapping(self):
        self.validate()
        return {
            'schema_version': self.schema_version,
            'background_label': self.background_label,
            'mask_shape': list(self.mask.shape),
            'mask_dtype': str(self.mask.dtype),
            'mask_sha256': self.mask_sha256,
            'label_map': self.label_map.to_mapping(),
            'identity_hash': self.identity_hash,
        }


@dataclass(frozen=True)
class CanonicalCameraObservation:
    rgb: np.ndarray | None
    depth: np.ndarray | None
    metadata: ResolvedCameraMetadata
    capture_identity: object | None = None
    segmentation: CanonicalEntityInstanceSegmentationV1 | None = None

    def __post_init__(self):
        c = self.metadata.camera
        if c.rgb != (self.rgb is not None) or c.depth != (self.depth is not None):
            raise ValueError('requested modalities not honored')
        for name in ('rgb','depth'):
            values = getattr(self,name)
            if values is None:
                continue
            values = np.array(values,copy=True)
            if not np.isfinite(values).all():
                raise ValueError('non-finite image')
            if name == 'rgb':
                shape = (c.height,c.width,3) if c.rgb_layout == 'HWC' else (3,c.height,c.width)
                if values.shape != shape or values.dtype != np.dtype(c.rgb_dtype) or values.min() < 0 or values.max() > (1 if c.rgb_dtype == 'float32' else 255):
                    raise ValueError('RGB schema mismatch')
            elif values.shape != (c.height,c.width) or values.dtype != np.float32 or np.any(values < 0):
                raise ValueError('depth schema mismatch')
            values.setflags(write=False)
            object.__setattr__(self,name,values)
        if self.segmentation is not None:
            if not isinstance(self.segmentation, CanonicalEntityInstanceSegmentationV1):
                raise TypeError('camera segmentation must use canonical-entity-instance-segmentation-v1')
            self.segmentation.validate()
            if self.segmentation.mask.shape != (c.height, c.width):
                raise ValueError('Entity segmentation mask resolution does not match the camera')
        if self.capture_identity is not None:
            from ...render.camera.source import CameraCaptureIdentityV1

            if not isinstance(self.capture_identity, CameraCaptureIdentityV1):
                raise TypeError('camera capture identity must use camera-capture-identity-v1')
            identity = self.capture_identity
            identity.validate()
            expected_modalities = {
                name for name, value in (('rgb', self.rgb), ('depth', self.depth))
                if value is not None
            }
            if self.segmentation is not None:
                expected_modalities.add('entity_instance_segmentation')
                label_map = self.segmentation.label_map
                boundary = identity.state_boundary
                if (
                    label_map.capture_identity_hash != identity.identity_hash
                    or label_map.task_artifact_hash != identity.task_artifact_hash
                    or label_map.scene_identity_hash != boundary.scene_identity_hash
                    or label_map.render_source_identity_hash != identity.render_source_identity_hash
                    or label_map.camera_id != identity.camera_id
                    or label_map.scene_instance_id != boundary.scene_instance_id
                    or label_map.provider_materialization_id != boundary.provider_materialization_id
                    or label_map.episode_id != boundary.episode_id
                    or label_map.reset_sample_id != boundary.reset_sample_id
                    or label_map.state_boundary_id != boundary.boundary_id
                    or label_map.state_revision != boundary.state_revision
                    or label_map.control_step != boundary.control_step
                    or label_map.simulation_time_s != identity.sample_clock.simulation_time_s
                ):
                    raise ValueError('Entity label map and camera capture identity reference different state publications')
            if (
                identity.camera_id != c.camera_id
                or identity.camera_geometry_identity_hash != c.identity_hash
                or identity.state_boundary.control_step != self.metadata.capture_control_step
                or identity.sample_clock.simulation_time_s != self.metadata.capture_simulation_time
                or set(identity.modalities) != expected_modalities
            ):
                raise ValueError('camera observation data and capture identity do not match')
        elif self.segmentation is not None:
            raise ValueError('Entity segmentation requires a capture identity for its state publication')
