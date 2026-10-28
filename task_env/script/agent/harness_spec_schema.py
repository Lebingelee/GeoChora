"""Strict JSON/YAML candidate data and shared harness-check-report-v0 contracts."""
from dataclasses import asdict, dataclass, field
from pathlib import Path
import hashlib
import json
import math
import re

CATEGORIES = frozenset(('spec_invalid', 'asset_missing', 'capability_unsupported',
    'semantic_mismatch', 'init_infeasible', 'expert_failed', 'execution_fault', 'template_missing'))
LOCALITIES = frozenset(('task_local', 'harness', 'asset', 'core', 'provider', 'unknown'))


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def save_json(value, path, *, exist_ok=False):
    text = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w' if exist_ok else 'x', encoding='utf-8') as stream:
        stream.write(text)


def keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(f'expected keys {required}, optional {optional}')


def number(value, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('finite number required')
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError('number outside allowed range')
    return float(value)


def vector(value, size, *, positive=False):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f'expected vector of size {size}')
    return [number(v, positive=positive) for v in value]


@dataclass(frozen=True)
class CandidateSpec:
    schema_version: str
    task_id: str
    template: str
    scene_config: dict
    object_config: dict
    success_config: dict
    timebase_config: dict
    required_capabilities: list[str]
    horizon: int

    def __post_init__(self):
        if self.schema_version != 'harness-candidate-spec-v0':
            raise ValueError('unsupported candidate schema_version')
        if not isinstance(self.task_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+-v[0-9]+', self.task_id):
            raise ValueError('task_id must be suite/name-vN')
        if not isinstance(self.template, str) or not self.template:
            raise ValueError('template must be a nonempty string')
        keys(self.scene_config, ('table_top_z', 'table_center_xy', 'table_half_size'), ('fixtures',))
        scene = dict(table_top_z=number(self.scene_config['table_top_z'], positive=True),
                     table_center_xy=vector(self.scene_config['table_center_xy'], 2),
                     table_half_size=vector(self.scene_config['table_half_size'], 3, positive=True))
        if 'fixtures' in self.scene_config:
            fixtures = self.scene_config['fixtures']
            if not isinstance(fixtures, list) or any(not isinstance(x, str) or not x for x in fixtures):
                raise ValueError('fixtures must be a list of catalog object UIDs')
            scene['fixtures'] = list(fixtures)
        keys(self.object_config, ('object_uid','initial_pos_xy','reset_half_extent_m','reset_z_fixed'), ('asset_sha256',))
        obj = self.object_config
        if not isinstance(obj['object_uid'], str) or not obj['object_uid'] or type(obj['reset_z_fixed']) is not bool:
            raise ValueError('object_uid string and reset_z_fixed bool required')
        obj = dict(object_uid=obj['object_uid'], initial_pos_xy=vector(obj['initial_pos_xy'],2),
                   reset_half_extent_m=number(obj['reset_half_extent_m'], nonnegative=True), reset_z_fixed=obj['reset_z_fixed'])
        if 'asset_sha256' in self.object_config:
            digest=self.object_config['asset_sha256']
            if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
                raise ValueError('asset_sha256 must be SHA256 hex')
            obj['asset_sha256']=digest
        keys(self.success_config, ('lift_height_m','reach_distance_m','gripper_closed_opening_m'))
        success = {k:number(v, positive=True) for k,v in self.success_config.items()}
        keys(self.timebase_config, ('physics_dt','control_substeps'))
        substeps = self.timebase_config['control_substeps']
        if type(substeps) is not int or substeps < 1:
            raise ValueError('control_substeps must be a positive int')
        timebase = dict(physics_dt=number(self.timebase_config['physics_dt'],positive=True), control_substeps=substeps)
        if type(self.horizon) is not int or not 1 <= self.horizon <= 6000:
            raise ValueError('horizon must be an integer in [1,6000]')
        caps = self.required_capabilities
        if not isinstance(caps, list) or any(not isinstance(x,str) or not x for x in caps) or len(set(caps)) != len(caps):
            raise ValueError('required_capabilities must be a unique string list')
        for key, value in dict(scene_config=scene, object_config=obj, success_config=success,
                               timebase_config=timebase, required_capabilities=sorted(caps)).items():
            object.__setattr__(self,key,value)

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return canonical_json(self.to_dict())

    def spec_sha256(self):
        return hashlib.sha256(self.to_json().encode('utf-8')).hexdigest()

    @classmethod
    def from_dict(cls, value):
        keys(value, cls.__dataclass_fields__)
        return cls(**value)

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.suffix.lower() in ('.yaml', '.yml'):
            import yaml
            value = yaml.safe_load(path.read_text())
        else:
            value = json.loads(path.read_text())
        return cls.from_dict(value)

    def save(self, path, *, exist_ok=False):
        save_json(self.to_dict(), path, exist_ok=exist_ok)


@dataclass(frozen=True)
class CheckFinding:
    check: str
    category: str
    locality: str
    spec_path: str
    observed: object
    expected: object
    evidence: dict
    revision_hint: str | None = None

    def __post_init__(self):
        if self.category not in CATEGORIES or self.locality not in LOCALITIES:
            raise ValueError('unknown finding category/locality')
        if not isinstance(self.check,str) or not self.check or not isinstance(self.spec_path,str):
            raise ValueError('check and spec_path must be strings')
        if not isinstance(self.evidence,dict) or (self.revision_hint is not None and not isinstance(self.revision_hint,str)):
            raise ValueError('evidence dict and optional revision_hint string required')
        canonical_json(asdict(self))


@dataclass(frozen=True)
class CheckReport:
    spec_sha256: str | None
    artifact_hash: str | None
    core_commit: str | None
    core_dirty: bool | None
    tool: str
    status: str
    findings: list[CheckFinding] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    tool_version: str = '0.1.0'
    schema_version: str = 'harness-check-report-v0'

    def __post_init__(self):
        if self.schema_version != 'harness-check-report-v0' or self.status not in ('pass','fail','error'):
            raise ValueError('invalid report schema/status')
        for value in (self.spec_sha256,self.artifact_hash):
            if value is not None and (not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value)):
                raise ValueError('hash must be sha256 hex or null')
        if self.core_dirty is not None and type(self.core_dirty) is not bool:
            raise ValueError('core_dirty must be bool or null')
        if not isinstance(self.findings,list) or any(not isinstance(x,CheckFinding) for x in self.findings):
            raise ValueError('findings must be CheckFinding list')
        if self.status == 'pass' and self.findings:
            raise ValueError('pass report cannot contain findings')
        canonical_json(asdict(self))

    def to_json(self):
        return canonical_json(asdict(self))

    def save(self,path,*,exist_ok=False):
        save_json(asdict(self),path,exist_ok=exist_ok)

    @classmethod
    def from_dict(cls,value):
        value = dict(value)
        value['findings'] = [CheckFinding(**f) for f in value.get('findings',[])]
        return cls(**value)
