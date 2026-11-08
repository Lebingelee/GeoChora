"""Provider-neutral ownership and receipt for a task/robot source composition.

This contract records identities; it does not parse a source or materialize a
provider model.  A provider must verify the source bytes and its own receipt.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _token(value: str, label: str) -> None:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonempty trimmed string")


def _digest(value: str, label: str) -> None:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")


def _unique(values: tuple[str, ...], label: str) -> None:
    if type(values) is not tuple or not values:
        raise ValueError(f"{label} must be a nonempty tuple")
    for value in values:
        _token(value, label)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must not contain duplicates")


def _unique_allow_empty(values: tuple[str, ...], label: str) -> None:
    if type(values) is not tuple:
        raise TypeError(f"{label} must be an immutable tuple")
    for value in values:
        _token(value, label)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must not contain duplicates")


@dataclass(frozen=True)
class CompositionSourceV1:
    """Immutable source identity and the canonical entities it contributes."""

    source_id: str
    closure_sha256: str
    entity_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _token(self.source_id, 'source_id')
        _digest(self.closure_sha256, 'source closure')
        _unique(self.entity_ids, 'source entities')


@dataclass(frozen=True)
class CompositionSourceV2:
    """Versioned source identity whose Task may legitimately own no entities."""

    source_id: str
    closure_sha256: str
    entity_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _token(self.source_id, 'source_id')
        _digest(self.closure_sha256, 'source closure')
        _unique_allow_empty(self.entity_ids, 'source entities')


@dataclass(frozen=True)
class SourceCompositionPlanV1:
    """Bind one task source to selected robot sources without provider objects.

    The task source contains its existing robot subtree.  A reference plan
    retains that subtree; a replacement plan removes it and adds each selected
    robot entity once.  Passive task entities cannot be replaced by this plan.
    """

    task_source: CompositionSourceV1
    task_entity_ids: tuple[str, ...]
    existing_robot_entity_ids: tuple[str, ...]
    robot_uid: str
    robot_sources: tuple[CompositionSourceV1, ...]
    mode: str
    assembly_identity_sha256: str
    attachment_identity_sha256: str | None = None
    task_site_transfers: tuple[tuple[str, str, str], ...] = ()
    control_binding_identity_sha256: str | None = None
    subject_binding_identity_sha256: str | None = None
    task_entity_source_roots: tuple[tuple[str, str], ...] = ()
    replaced_robot_source_roots: tuple[str, ...] = ()
    task_free_joints: tuple[tuple[str, str], ...] = ()
    position_binding_identity_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.task_source) is not CompositionSourceV1:
            raise TypeError('task_source must be CompositionSourceV1')
        _unique(self.task_entity_ids, 'task entities')
        _unique(self.existing_robot_entity_ids, 'existing robot entities')
        _token(self.robot_uid, 'robot uid')
        _digest(self.assembly_identity_sha256, 'assembly identity')
        if self.attachment_identity_sha256 is not None:
            _digest(self.attachment_identity_sha256, 'attachment identity')
        if self.control_binding_identity_sha256 is not None:
            _digest(self.control_binding_identity_sha256, 'control binding identity')
        if self.subject_binding_identity_sha256 is not None:
            _digest(self.subject_binding_identity_sha256, 'subject binding identity')
        if self.position_binding_identity_sha256 is not None:
            _digest(self.position_binding_identity_sha256, 'position binding identity')
        if type(self.task_site_transfers) is not tuple:
            raise TypeError('task site transfers must be an immutable tuple')
        for item in self.task_site_transfers:
            if type(item) is not tuple or len(item) != 3:
                raise ValueError('task site transfer requires source body, site and target body')
            for value in item:
                _token(value, 'task site transfer')
        if len(set(self.task_site_transfers)) != len(self.task_site_transfers):
            raise ValueError('task site transfers must be unique')
        if type(self.robot_sources) is not tuple or not self.robot_sources or any(
                type(source) is not CompositionSourceV1 for source in self.robot_sources):
            raise TypeError('robot_sources must contain typed source declarations')
        if self.mode not in ('reference', 'replace'):
            raise ValueError('composition mode must be reference or replace')
        if self.mode == 'replace':
            if (type(self.task_entity_source_roots) is not tuple
                    or any(type(x) is not tuple or len(x) != 2 for x in self.task_entity_source_roots)):
                raise TypeError('task source roots require immutable entity/name pairs')
            roots = dict(self.task_entity_source_roots)
            if (len(roots) != len(self.task_entity_source_roots) or set(roots) != set(self.task_entity_ids)
                    or len(set(roots.values())) != len(roots)):
                raise ValueError('task source roots must uniquely cover task entities')
            for name in roots.values(): _token(name, 'task source root')
            _unique(self.replaced_robot_source_roots, 'replaced robot source roots')
            if set(roots.values()) & set(self.replaced_robot_source_roots):
                raise ValueError('task and robot source roots must be disjoint')
            if (type(self.task_free_joints) is not tuple
                    or any(type(x) is not tuple or len(x) != 2 for x in self.task_free_joints)):
                raise TypeError('task free joints require immutable entity/name pairs')
            free = dict(self.task_free_joints)
            if (len(free) != len(self.task_free_joints) or not set(free) <= set(self.task_entity_ids)
                    or len(set(free.values())) != len(free)):
                raise ValueError('free joint names must uniquely belong to declared task entities')
            for name in free.values(): _token(name, 'task free joint')
        task, old_robot = set(self.task_entity_ids), set(self.existing_robot_entity_ids)
        if task & old_robot or task | old_robot != set(self.task_source.entity_ids):
            raise ValueError('task source ownership must partition task and old robot entities')
        source_ids = [source.source_id for source in self.robot_sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError('robot source identities must be unique')
        robot_entities = [entity for source in self.robot_sources for entity in source.entity_ids]
        if len(set(robot_entities)) != len(robot_entities) or task.intersection(robot_entities):
            raise ValueError('robot and task entity owners must be unique and disjoint')
        if self.mode == 'reference':
            if len(self.robot_sources) != 1 or self.robot_sources[0].source_id != self.task_source.source_id:
                raise ValueError('reference requires the existing task source identity')
            if self.robot_sources[0].closure_sha256 != self.task_source.closure_sha256:
                raise ValueError('reference robot source closure differs from task source')
            if set(robot_entities) != old_robot:
                raise ValueError('reference must retain the existing robot entities')
        elif self.task_source.source_id in source_ids:
            raise ValueError('replacement robot sources must differ from task source')

    @property
    def entity_ids(self) -> tuple[str, ...]:
        return self.task_entity_ids + tuple(
            entity for source in self.robot_sources for entity in source.entity_ids)

    @property
    def identity_hash(self) -> str:
        data = {'schema_version': 'source-composition-plan-v1', **asdict(self)}
        payload = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class CompositionAttachmentV2:
    """Provider-neutral attachment intent, pinned to both source closures."""

    parent_entity_id: str
    parent_frame_id: str
    child_entity_id: str
    child_frame_id: str
    rule_id: str
    parent_source_id: str
    parent_closure_sha256: str
    child_source_id: str
    child_closure_sha256: str

    def __post_init__(self) -> None:
        for label in ('parent_entity_id', 'parent_frame_id', 'child_entity_id',
                      'child_frame_id', 'rule_id', 'parent_source_id', 'child_source_id'):
            _token(getattr(self, label), label)
        if self.parent_entity_id == self.child_entity_id:
            raise ValueError('attachment endpoints must be distinct entities')
        _digest(self.parent_closure_sha256, 'parent source closure')
        _digest(self.child_closure_sha256, 'child source closure')


@dataclass(frozen=True)
class CompositionSourceReferenceV1:
    """Pinned Robot source declaration available before provider parsing."""

    source_id: str
    source_reference: str
    source_revision: str
    entity_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for label in ('source_id', 'source_reference', 'source_revision'):
            _token(getattr(self, label), label)
        _unique(self.entity_ids, 'Robot source entities')


@dataclass(frozen=True)
class SourceCompositionIntentV1:
    """Identity-bearing, provider-neutral composition request made pre-parse."""

    schema_version: str
    task_source_id: str
    task_source_closure_sha256: str
    task_entity_ids: tuple[str, ...]
    existing_robot_entity_ids: tuple[str, ...]
    robot_uid: str
    robot_recipe_sha256: str
    robot_sources: tuple[CompositionSourceReferenceV1, ...]
    mode: str
    component_edges: tuple[tuple[str, str, str, str, str], ...]
    task_site_transfers: tuple[tuple[str, str, str], ...]
    controlled_joints: tuple[str, ...]
    control_profiles: tuple[str, ...]
    resource_writers: tuple[tuple[str, str, str], ...]

    def __post_init__(self) -> None:
        if self.schema_version != 'source-composition-intent-v1':
            raise ValueError('unsupported composition intent version')
        _token(self.task_source_id, 'Task source id')
        _digest(self.task_source_closure_sha256, 'Task source closure')
        _unique_allow_empty(self.task_entity_ids, 'Task entities')
        _unique_allow_empty(self.existing_robot_entity_ids, 'existing Robot entities')
        _token(self.robot_uid, 'Robot uid')
        _digest(self.robot_recipe_sha256, 'Robot recipe identity')
        if type(self.robot_sources) is not tuple or not self.robot_sources or any(
                type(item) is not CompositionSourceReferenceV1 for item in self.robot_sources):
            raise TypeError('Robot source intent must contain typed pinned references')
        if self.mode not in {'reference', 'replace', 'add'}:
            raise ValueError('composition intent mode must be reference, replace, or add')
        task, existing = set(self.task_entity_ids), set(self.existing_robot_entity_ids)
        robot_entities = [entity for source in self.robot_sources for entity in source.entity_ids]
        if task & existing or task.intersection(robot_entities) or len(set(robot_entities)) != len(robot_entities):
            raise ValueError('composition intent owners must be unique and disjoint')
        source_ids = [source.source_id for source in self.robot_sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError('Robot source intent identities must be unique')
        if self.mode == 'reference':
            if not existing or set(robot_entities) != existing:
                raise ValueError('reference intent must retain the existing Robot entities')
        elif self.mode == 'replace':
            if not existing or self.task_source_id in source_ids:
                raise ValueError('replacement intent requires an existing Robot and distinct source')
        elif existing or self.task_source_id in source_ids:
            raise ValueError('add intent requires an empty Robot owner and distinct source')
        if type(self.component_edges) is not tuple:
            raise TypeError('component edges must be an immutable tuple')
        edges = []
        for edge in self.component_edges:
            if type(edge) is not tuple or len(edge) != 5:
                raise ValueError('component edges require parent/frame/child/frame/rule')
            parent, parent_frame, child, child_frame, rule = edge
            for value in edge:
                _token(value, 'component edge')
            if parent == child or parent not in robot_entities or child not in robot_entities:
                raise ValueError('component edge must connect declared Robot entities')
            edges.append((parent, child))
        if len(set(edges)) != len(edges) or len({child for _, child in edges}) != len(edges):
            raise ValueError('component edges must have unique parent/child ownership')
        parents = {child: parent for parent, child in edges}
        for child in parents:
            seen, current = set(), child
            while current in parents:
                if current in seen:
                    raise ValueError('component edges must be acyclic')
                seen.add(current)
                current = parents[current]
        if type(self.task_site_transfers) is not tuple:
            raise TypeError('Task site transfers must be an immutable tuple')
        for transfer in self.task_site_transfers:
            if type(transfer) is not tuple or len(transfer) != 3:
                raise ValueError('Task site transfer requires source body, site, and target body')
            for value in transfer:
                _token(value, 'Task site transfer')
        if len(set(self.task_site_transfers)) != len(self.task_site_transfers):
            raise ValueError('Task site transfers must be unique')
        _unique(self.controlled_joints, 'Robot controlled joints')
        _unique(self.control_profiles, 'Robot control profiles')
        if type(self.resource_writers) is not tuple:
            raise TypeError('Robot resource writers must be an immutable tuple')
        resource_keys = []
        allowed = task | existing | set(robot_entities)
        for row in self.resource_writers:
            if type(row) is not tuple or len(row) != 3:
                raise ValueError('resource writer rows require entity, resource, and writer')
            entity, resource, writer = row
            for value in row:
                _token(value, 'resource writer identity')
            if entity not in allowed:
                raise ValueError('resource writer owner is outside the composition intent')
            resource_keys.append((entity, resource))
        if len(set(resource_keys)) != len(resource_keys):
            raise ValueError('composition intent may assign only one writer to a resource')

    @property
    def identity_hash(self) -> str:
        data = asdict(self)
        payload = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def build_source_composition_intent_v1(*, task_source, task_entity_ids,
                                      existing_robot_entity_ids, robot_recipe,
                                      task_site_transfers=()):
    """Build the shared request from source identities and Robot declarations.

    This function consumes no source bytes and does not import a physics provider.
    """
    from ..robots.source_recipe import RobotSourceRecipeV1

    if type(robot_recipe) is not RobotSourceRecipeV1:
        raise TypeError('composition intent requires a RobotSourceRecipeV1')
    task_source_id = getattr(task_source, 'source_id', None)
    task_closure = getattr(task_source, 'source_closure_digest', None)
    mode = {
        'reference-task-source': 'reference',
        'replace-task-subtree': 'replace',
        'add-source': 'add',
    }.get(robot_recipe.mode)
    if mode is None:
        raise ValueError('Robot source recipe has an unsupported composition mode')
    sources = tuple(CompositionSourceReferenceV1(
        item.source_id, item.source_reference, item.source_revision, item.entity_ids)
        for item in robot_recipe.sources)
    return SourceCompositionIntentV1(
        'source-composition-intent-v1', task_source_id, task_closure,
        task_entity_ids, existing_robot_entity_ids, robot_recipe.robot_uid,
        robot_recipe.identity_hash, sources, mode, robot_recipe.component_edges,
        task_site_transfers, robot_recipe.controlled_joints,
        robot_recipe.control_profiles, robot_recipe.resource_writers)


@dataclass(frozen=True)
class SourceCompositionRequestV2:
    """Provider-neutral composition intent with explicit ownership and provenance.

    V1 remains frozen for existing receipts. V2 permits a task with no separately
    owned object entities and a Robot source that is added without a Robot already
    embedded in the Task source. No provider data or native names are accepted.
    """

    schema_version: str
    task_source: CompositionSourceV2
    task_entity_ids: tuple[str, ...]
    existing_robot_entity_ids: tuple[str, ...]
    robot_uid: str
    robot_sources: tuple[CompositionSourceV2, ...]
    mode: str
    assembly_identity_sha256: str
    attachments: tuple[CompositionAttachmentV2, ...] = ()
    resource_writers: tuple[tuple[str, str, str], ...] = ()
    intent_identity_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 'source-composition-request-v2':
            raise ValueError('unsupported composition request version')
        if type(self.task_source) is not CompositionSourceV2:
            raise TypeError('task_source must be CompositionSourceV2')
        _unique_allow_empty(self.task_entity_ids, 'task entities')
        _unique_allow_empty(self.existing_robot_entity_ids, 'existing robot entities')
        _token(self.robot_uid, 'robot uid')
        _digest(self.assembly_identity_sha256, 'assembly identity')
        if self.intent_identity_sha256 is not None:
            _digest(self.intent_identity_sha256, 'composition intent identity')
        if type(self.robot_sources) is not tuple or not self.robot_sources or any(
                type(source) is not CompositionSourceV2 for source in self.robot_sources):
            raise TypeError('robot_sources must contain typed source declarations')
        if any(not source.entity_ids for source in self.robot_sources):
            raise ValueError('Robot sources must own at least one entity')
        if self.mode not in ('reference', 'replace', 'add'):
            raise ValueError('composition mode must be reference, replace, or add')
        task, existing = set(self.task_entity_ids), set(self.existing_robot_entity_ids)
        if task & existing or task | existing != set(self.task_source.entity_ids):
            raise ValueError('task source ownership must partition task and existing Robot entities')
        source_ids = [source.source_id for source in self.robot_sources]
        robot_entities = [entity for source in self.robot_sources for entity in source.entity_ids]
        if len(set(robot_entities)) != len(robot_entities) or task.intersection(robot_entities):
            raise ValueError('Robot and Task entity owners must be unique and disjoint')
        if self.mode == 'reference':
            if not existing or len(self.robot_sources) != 1:
                raise ValueError('reference requires one Robot already owned by the Task source')
            source = self.robot_sources[0]
            if (source.source_id != self.task_source.source_id
                    or source.closure_sha256 != self.task_source.closure_sha256
                    or set(source.entity_ids) != existing):
                raise ValueError('reference Robot provenance differs from the Task source')
        elif self.mode == 'add':
            if existing:
                raise ValueError('add requires a Task source with no preexisting Robot')
            if set(source_ids) & {self.task_source.source_id}:
                raise ValueError('added Robot source must differ from the Task source')
        else:
            if not existing:
                raise ValueError('replace requires an existing Robot owner')
            if set(source_ids) & {self.task_source.source_id}:
                raise ValueError('replacement Robot source must differ from the Task source')
        if len(set(source_ids)) != len(source_ids):
            raise ValueError('Robot source identities must be unique')
        if type(self.attachments) is not tuple or any(
                type(item) is not CompositionAttachmentV2 for item in self.attachments):
            raise TypeError('attachments must contain typed composition attachments')
        allowed = task | set(robot_entities)
        if self.mode == 'reference':
            allowed = task | existing
        if any(item.parent_entity_id not in allowed or item.child_entity_id not in allowed
               for item in self.attachments):
            raise ValueError('attachment refers to an entity outside the composition')
        source_by_id = {self.task_source.source_id: self.task_source}
        source_by_id.update((source.source_id, source) for source in self.robot_sources)
        entity_sources = {entity: self.task_source for entity in task | existing}
        for source in self.robot_sources:
            for entity in source.entity_ids:
                entity_sources[entity] = source
        for item in self.attachments:
            for entity, source_id, closure in (
                    (item.parent_entity_id, item.parent_source_id, item.parent_closure_sha256),
                    (item.child_entity_id, item.child_source_id, item.child_closure_sha256)):
                source = source_by_id.get(source_id)
                owner = entity_sources.get(entity)
                if (source is None or source.closure_sha256 != closure or owner is None
                        or (owner.source_id, owner.closure_sha256) != (source_id, closure)):
                    raise ValueError('attachment provenance differs from a declared source closure')
        attachment_pairs = [(item.parent_entity_id, item.child_entity_id) for item in self.attachments]
        if len(set(attachment_pairs)) != len(attachment_pairs):
            raise ValueError('attachment parent/child pairs must be unique')
        parents = {child: parent for parent, child in attachment_pairs}
        for child in parents:
            seen, current = set(), child
            while current in parents:
                if current in seen:
                    raise ValueError('attachment relationships must be acyclic')
                seen.add(current)
                current = parents[current]
        if type(self.resource_writers) is not tuple:
            raise TypeError('resource writers must be an immutable tuple')
        resource_keys, rows = [], []
        for row in self.resource_writers:
            if type(row) is not tuple or len(row) != 3:
                raise ValueError('resource writer rows require entity, resource, and writer identities')
            entity, resource, writer = row
            for value in row:
                _token(value, 'resource writer identity')
            if entity not in allowed:
                raise ValueError('resource writer owner is outside the composition')
            resource_keys.append((entity, resource))
            rows.append(row)
        if len(set(resource_keys)) != len(resource_keys):
            raise ValueError('a composed resource may have only one writer')
        if len(set(rows)) != len(rows):
            raise ValueError('resource writer declarations must be unique')

    @property
    def entity_ids(self) -> tuple[str, ...]:
        return self.task_entity_ids + tuple(
            entity for source in self.robot_sources for entity in source.entity_ids)

    @property
    def identity_hash(self) -> str:
        data = asdict(self)
        payload = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class CompositionMaterializationReceiptV1:
    """Native entity names and source identities returned by a provider build."""

    plan_sha256: str
    source_closures: tuple[tuple[str, str], ...]
    entity_native_names: tuple[tuple[str, str], ...]
    materialization_id: str

    def validate_against(self, plan: SourceCompositionPlanV1) -> None:
        if type(plan) is not SourceCompositionPlanV1:
            raise TypeError('receipt validation requires a SourceCompositionPlanV1')
        if self.plan_sha256 != plan.identity_hash:
            raise ValueError('materialization receipt belongs to another plan')
        _token(self.materialization_id, 'materialization_id')
        expected = {plan.task_source.source_id: plan.task_source.closure_sha256}
        expected.update((s.source_id, s.closure_sha256) for s in plan.robot_sources)
        if type(self.source_closures) is not tuple or len(dict(self.source_closures)) != len(self.source_closures):
            raise ValueError('receipt source identities must be unique')
        if dict(self.source_closures) != expected:
            raise ValueError('receipt source closure identities differ from the plan')
        if type(self.entity_native_names) is not tuple or len(dict(self.entity_native_names)) != len(self.entity_native_names):
            raise ValueError('receipt entity mappings must be unique')
        mapping = dict(self.entity_native_names)
        if set(mapping) != set(plan.entity_ids):
            raise ValueError('receipt entity coverage differs from the plan')
        for name in mapping.values():
            _token(name, 'native entity name')
        if len(set(mapping.values())) != len(mapping):
            raise ValueError('native entity names must be unique')


@dataclass(frozen=True)
class CompositionRuntimeInputV1:
    """Explicit construction input; a provider still performs its own checks."""

    plan: SourceCompositionPlanV1
    fixed_declaration: object
    retained_roots: tuple[str, ...]
    replaced_robot_roots: tuple[str, ...]
    entity_body_names: tuple[tuple[str, str], ...]
    allowed_free_joints: tuple[str, ...]
    control_binding_plan: object | None = None
    subject_binding_identity_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.plan) is not SourceCompositionPlanV1 or self.plan.mode != 'replace':
            raise TypeError('runtime input requires a replacement SourceCompositionPlanV1')
        if self.control_binding_plan is not None:
            from ..runtime.sessions.control import ControlBindingPlanV1
            if (type(self.control_binding_plan) is not ControlBindingPlanV1
                    or not self.control_binding_plan._compiled
                    or self.control_binding_plan.identity_hash != self.plan.control_binding_identity_sha256):
                raise ValueError('runtime Controller binding differs from the composition plan')
        elif self.plan.control_binding_identity_sha256 is not None:
            raise ValueError('runtime composition is missing its declared Controller binding')
        if self.subject_binding_identity_sha256 != self.plan.subject_binding_identity_sha256:
            raise ValueError('runtime subject binding differs from composition plan')
        if (dict(self.plan.task_entity_source_roots) != {
                entity: native for entity, native in self.entity_body_names
                if entity in self.plan.task_entity_ids}
                or self.replaced_robot_roots != self.plan.replaced_robot_source_roots
                or self.allowed_free_joints != tuple(name for _, name in self.plan.task_free_joints)):
            raise ValueError('runtime task roots or free joints differ from composition plan')
        _unique(self.retained_roots, 'retained roots')
        _unique(self.replaced_robot_roots, 'replaced robot roots')
        if set(self.retained_roots) & set(self.replaced_robot_roots):
            raise ValueError('retained and replaced native roots must be disjoint')
        if type(self.entity_body_names) is not tuple:
            raise TypeError('entity body names must be an immutable tuple')
        if any(type(pair) is not tuple or len(pair) != 2 for pair in self.entity_body_names):
            raise ValueError('entity body mapping requires canonical/native pairs')
        if len(dict(self.entity_body_names)) != len(self.entity_body_names):
            raise ValueError('entity body mapping contains duplicate canonical names')
        if set(dict(self.entity_body_names)) != set(self.plan.entity_ids):
            raise ValueError('entity body mapping differs from planned ownership')
        for canonical, native in self.entity_body_names:
            _token(canonical, 'entity id')
            _token(native, 'native body name')
        if len(set(dict(self.entity_body_names).values())) != len(self.entity_body_names):
            raise ValueError('entity native body names must be unique')
        if type(self.allowed_free_joints) is not tuple:
            raise TypeError('allowed free joints must be an immutable tuple')
        if len(set(self.allowed_free_joints)) != len(self.allowed_free_joints):
            raise ValueError('allowed free joints must be unique')
        for name in self.allowed_free_joints:
            _token(name, 'free joint name')


@dataclass(frozen=True)
class PositionSubjectControlBindingV1:
    """Source-bound position Controller and independently mapped resource owners."""

    plan: object
    subject_identity_sha256: str
    resource_native_names: tuple[tuple[str, str, str], ...]
    joint_native_ownership: tuple[tuple[str, str, str, str, str], ...]

    def __post_init__(self):
        from ..runtime.sessions.control import ControlBindingPlanV1
        if type(self.plan) is not ControlBindingPlanV1 or not self.plan._compiled:
            raise ValueError('position subject binding requires a compiled Controller plan')
        _digest(self.subject_identity_sha256, 'position subject identity')
        if (type(self.resource_native_names) is not tuple
                or any(type(row) is not tuple or len(row) != 3 for row in self.resource_native_names)):
            raise TypeError('position resource mappings require immutable entity/actuator/native triples')
        canonical = [(e, a) for e, a, _ in self.resource_native_names]
        native = [n for _, _, n in self.resource_native_names]
        if (len(set(canonical)) != len(canonical) or len(set(native)) != len(native)
                or set(canonical) != {(e, a) for e, a, _ in self.plan.resource_writers}):
            raise ValueError('position resource mapping must cover the Controller plan injectively')
        for entity, actuator, name in self.resource_native_names:
            _token(entity, 'position entity'); _token(actuator, 'position actuator'); _token(name, 'native actuator')
        if (type(self.joint_native_ownership) is not tuple or not self.joint_native_ownership
                or any(type(row) is not tuple or len(row) != 5 for row in self.joint_native_ownership)):
            raise TypeError('position joint ownership requires immutable semantic/entity/joint/native/actuator rows')
        semantics = [row[0] for row in self.joint_native_ownership]
        joints = [(row[1], row[2]) for row in self.joint_native_ownership]
        native_joints = [row[3] for row in self.joint_native_ownership]
        resources = {(e, a): n for e, a, n in self.resource_native_names}
        if (len(set(semantics)) != len(semantics) or len(set(joints)) != len(joints)
                or len(set(native_joints)) != len(native_joints)
                or any((entity, actuator) not in resources
                       for _, entity, _, _, actuator in self.joint_native_ownership)):
            raise ValueError('position joint semantic and resource ownership must be unique and complete')
        for row in self.joint_native_ownership:
            for value in row: _token(value, 'position joint ownership')

    @property
    def identity_hash(self) -> str:
        payload = {'schema_version': 'position-subject-control-binding-v1',
                   'plan': self.plan.identity_hash, 'subject': self.subject_identity_sha256,
                   'resources': self.resource_native_names, 'joints': self.joint_native_ownership}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                         allow_nan=False).encode('utf-8')).hexdigest()
