"""Public selected P1.6 route; legacy UID deliberately not reused."""
from ...registry import register_env
from ..reference_env import SelectedReferenceEnv
from .reference import build_reference, sample_reset

REFERENCE_ENV_ID = 'pick-cube-p16-reference-v1'


@register_env()
class PickCubeReferenceEnv(SelectedReferenceEnv):
    uid = REFERENCE_ENV_ID
    task_kind = 'pick_cube'
    build = staticmethod(lambda provider: build_reference(backend='cpu'))
    reset_sample = staticmethod(sample_reset)
