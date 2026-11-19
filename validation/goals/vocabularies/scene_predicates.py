"""scene-predicates/1.0.0 (SimDataKit) as a vocabulary plugin.

Owns everything specific to this vocabulary: predicate algorithms and thresholds (`predicates.py`,
`Bands`/`Fallbacks`), the settled-final-state rule, the implicit `AllReleased` term, the `Scene`
state adapter, bind filter fields and the process predicates `Never` and `WhileGrasped`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from validation.goals import predicates as P
from validation.goals.predicates import Bands, Fallbacks, Scene
from validation.goals.tri import Tri, unknown
from validation.goals.vocabulary import VocabularyPlugin, WhenOutcome, register

BIND_FIELDS = ('kind', 'color', 'size_class', 'initially_on', 'initial_orientation')


@dataclass(frozen=True)
class EvalPolicy:
    bands: Bands = field(default_factory=Bands)
    fallbacks: Fallbacks = field(default_factory=Fallbacks)
    settle_speed_mps: float = 0.02       # vocabulary: terminal_state
    settle_window_s: float = 0.5         # vocabulary: terminal_state
    max_sample_gap_s: float = 0.1        # engine: trace gaps beyond this make Sequence unknown (sampling.py semantics)
    max_assignments: int = 200000        # engine: bind enumeration limit


def scene_adapter(manifest, state, initial, policy):
    return Scene(manifest, state, initial, policy.bands, policy.fallbacks)


def settled_final_state(trace, final_state, objects, policy):
    """vocabulary evaluation.terminal_state: terminal predicates hold only on the settled final state."""
    settle = {'settled': None, 'reason': 'not_checked'}
    if trace is not None:
        settle = trace.settle_report(sorted(objects), speed_mps=policy.settle_speed_mps,
                                     window_s=policy.settle_window_s)
    elif final_state.settled is not None:
        settle = {'settled': final_state.settled, 'reason': 'declared_by_state'}
    if settle['settled'] is False:
        return WhenOutcome(settle, 'not_settled',
                           ('terminal predicates unknown: final state never settled (vocabulary evaluation.terminal_state)',))
    if settle['settled'] is None:
        return WhenOutcome(settle, 'settled_terminal_unverified',
                           (f"settledness not verified ({settle.get('reason')}); endpoint predicates are conditional",))
    return WhenOutcome(settle)


def never(view, args, policy):
    name = args[0]
    if len(view) == 0:
        return unknown('trace_empty')
    contacts = [P.robot_contact(view.state(i), name) for i in range(len(view))]
    hits = [float(view.times[i]) for i, c in enumerate(contacts) if c.value is True]
    if hits:
        return Tri(False, None, {'first_contact_time_s': hits[0], 'contact_samples': len(hits)}, 'contact')
    if any(c.value is None for c in contacts):
        return unknown(contacts[0].reason or 'contacts_unavailable')
    if not view.trace.recording_complete:
        return unknown('recording_incomplete')
    return Tri(True, None, {'samples': len(contacts)}, 'contact')


def while_grasped(view, args, policy):
    name, orientation = args[0], args[1]
    if orientation not in ('Upright', 'Inverted'):
        raise ValueError(f'WhileGrasped orientation must be Upright or Inverted, got {orientation!r}')
    if len(view) == 0:
        return unknown('trace_empty')
    fn = P.TERMINAL_PREDICATES[orientation][0]
    bad, unsure, held, grasp_unknown, bases = [], [], 0, 0, set()
    for i in range(len(view)):
        s = view.state(i)
        g = P.grasped(s, name, policy.fallbacks)
        if g.basis:
            bases.add(g.basis)
        if g.value is False:
            continue
        grasp_unknown += g.value is None
        o = fn(s, name)
        if g.value is True:
            held += 1
            if o.value is False:
                bad.append(float(view.times[i]))
            elif o.value is None:
                unsure.append(float(view.times[i]))
        elif o.value is not True:  # grasp uncertain and orientation not clearly satisfied
            unsure.append(float(view.times[i]))
    measurements = {'grasped_samples': held, 'violating_samples': len(bad), 'unresolved_samples': len(unsure)}
    if bad:
        return Tri(False, None, {**measurements, 'first_violation_time_s': bad[0]}, ' / '.join(sorted(bases)) or None)
    if held == 0 and grasp_unknown == 0:
        # vocabulary: the object must be grasped on at least one sample (pushing is not a grasp)
        if not view.trace.recording_complete:
            return Tri(None, 'recording_incomplete', measurements, ' / '.join(sorted(bases)) or None)
        return Tri(False, 'never_grasped', measurements, ' / '.join(sorted(bases)) or None)
    if unsure or held == 0:
        return Tri(None, 'grasp_or_orientation_unresolved', measurements, ' / '.join(sorted(bases)) or None)
    if not view.trace.recording_complete:
        return Tri(None, 'recording_incomplete', measurements, ' / '.join(sorted(bases)) or None)
    return Tri(True, None, measurements, ' / '.join(sorted(bases)) or None)


PLUGIN = register(VocabularyPlugin(
    version=P.VOCABULARY_VERSION,
    predicates=P.TERMINAL_PREDICATES,
    process_predicates={'Never': never, 'WhileGrasped': while_grasped},
    when='settled_final_state',
    evaluate_when=settled_final_state,
    implicit_terms=(('all_released', 'AllReleased'),),
    state_adapter=scene_adapter,
    default_policy=EvalPolicy,
    bind_fields=BIND_FIELDS,
))
