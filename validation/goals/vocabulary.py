"""Vocabulary plugin interface and registry (the boundary between the goal engine and predicate meaning).

The engine (`validation.goals.evaluate`) owns goal grammar, Kleene combination, bind enumeration,
the generic `Sequence` process combinator, best-assignment choice and result assembly. Everything a
predicate *means* lives in a `VocabularyPlugin`, selected by the exact version string the goal declares.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from validation.goals.tri import Tri

# Process combinators the engine itself provides for every vocabulary (composition over vocabulary atoms).
ENGINE_PROCESS_PREDICATES = ('Sequence',)


@dataclass(frozen=True)
class WhenOutcome:
    """Result of a vocabulary's `when` rule for the terminal evaluation point.

    report          JSON-ready dict, emitted as the result's `settle` field.
    blocked_reason  when set, terminal predicates are unknown with this reason (the goal computed
                    anyway is reported as `goal_if_settled`).
    notes           human-readable notes, appended first to the result's `basis.notes`.
    """
    report: dict
    blocked_reason: str | None = None
    notes: tuple = ()


@dataclass(frozen=True)
class VocabularyPlugin:
    """One predicate vocabulary at one exact version.

    predicates          name -> (fn(state_view, *args) -> Tri, arity or None for variadic)
    process_predicates  vocabulary-owned process predicates: name -> fn(view, resolved_args, policy) -> Tri,
                        where `view` exposes `len()`, `times`, `trace` and `state(i)` (adapted sample i)
    when                name of the evaluation-time rule (e.g. 'settled_final_state')
    evaluate_when       (trace|None, final_state, object_names, policy) -> WhenOutcome
    implicit_terms      ((result_key, zero-arity predicate), ...) conjoined with every goal
    state_adapter       (manifest, state, initial_state, policy) -> state_view consumed by the predicates
    default_policy      () -> policy object; the engine reads only `max_assignments` and `max_sample_gap_s`
    bind_fields         manifest object fields usable as bind filters
    """
    version: str
    predicates: Mapping[str, tuple]
    when: str
    evaluate_when: Callable[..., WhenOutcome]
    state_adapter: Callable[..., Any]
    default_policy: Callable[[], Any]
    process_predicates: Mapping[str, Callable[..., Tri]] = field(default_factory=dict)
    implicit_terms: tuple = ()
    bind_fields: tuple = ()


_REGISTRY: dict[str, VocabularyPlugin] = {}
_BUILTINS_LOADED = False


def register(plugin: VocabularyPlugin) -> VocabularyPlugin:
    existing = _REGISTRY.get(plugin.version)
    if existing is not None and existing is not plugin:
        raise ValueError(f'vocabulary {plugin.version!r} is already registered')
    _REGISTRY[plugin.version] = plugin
    return plugin


def _load_builtins():
    global _BUILTINS_LOADED
    if not _BUILTINS_LOADED:
        _BUILTINS_LOADED = True
        import validation.goals.vocabularies.scene_predicates  # noqa: F401  (registers itself)


def registered() -> list[str]:
    _load_builtins()
    return sorted(_REGISTRY)


def resolve(declared) -> VocabularyPlugin:
    """Plugin for a declared vocabulary document ({'version': ..., 'predicates': ..., 'process_predicates': ...}).

    Refuses an undeclared or unregistered version, and a declaration naming predicates the plugin
    (plus the engine's own process combinators) does not implement.
    """
    _load_builtins()
    version = (declared or {}).get('version')
    plugin = _REGISTRY.get(version) if isinstance(version, str) else None
    if plugin is None:
        raise ValueError(f'unsupported vocabulary {version!r}; registered vocabularies: {sorted(_REGISTRY)}')
    names = set(declared.get('predicates') or {}) | set(declared.get('process_predicates') or {})
    missing = names - set(plugin.predicates) - set(plugin.process_predicates) - set(ENGINE_PROCESS_PREDICATES)
    if missing:
        raise ValueError(f'vocabulary predicates not implemented: {sorted(missing)}')
    return plugin
