"""Public selected V2/V5/R3 route; one default Outcome Completion Policy V1."""
from ...registry import register_env
from ..reference_env import ReferenceTaskBinding, SelectedReferenceEnv
from .reference import build_reference
from .canonical_reset import sample_reset
from .canonical_semantics import evaluate

REFERENCE_ENV_ID = 'nut-assembly-outcome-reference-v1'


def _reset_seed(seed):
    if seed not in (19, None):
        raise ValueError('selected NutAssembly NA-S0 has fixed provenance seed19')
    return 19 if seed is None else seed


def _schedule(env):
    from .reference_execution import ReferenceArmSchedule
    return ReferenceArmSchedule(env.solution, env.value['_arm_schedule_memory'])


def _observe_kwargs(env, guard_samples):
    return {
        'readiness': env.controller.readiness(env.state, env.feedback),
        'transition_samples': guard_samples,
    }


@register_env()
class NutAssemblyReferenceEnv(SelectedReferenceEnv):
    uid = REFERENCE_ENV_ID
    binding = ReferenceTaskBinding(
        build=lambda provider: build_reference(provider=provider),
        reset_sample=sample_reset, evaluate=evaluate,
        object_poses=(('square-nut-v1', 'square_nut_v1'), ('square-peg-v1', 'square_peg_v1')),
        external_actions=False, interval_mode='native', recorder_mode='execution',
        external_action_error='selected NutAssembly requires step_expert; unguarded external actions are not admitted',
        reset_seed=_reset_seed, observe_expert_kwargs=_observe_kwargs,
        schedule_factory=_schedule, capture_guard_samples=True,
        record_native_substeps=True, abort_solution_on_runtime_error=True,
    )
