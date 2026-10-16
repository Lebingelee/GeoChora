"""Public selected V2/V5/R3 route; one default Outcome Completion Policy V1."""
from ...registry import register_env
from ..reference_env import SelectedReferenceEnv
from .reference import build_reference
from .canonical_reset import sample_reset

REFERENCE_ENV_ID = 'nut-assembly-outcome-reference-v1'


@register_env()
class NutAssemblyReferenceEnv(SelectedReferenceEnv):
    uid = REFERENCE_ENV_ID
    task_kind = 'nut_assembly'
    build = staticmethod(lambda provider: build_reference(provider=provider))
    reset_sample = staticmethod(sample_reset)
