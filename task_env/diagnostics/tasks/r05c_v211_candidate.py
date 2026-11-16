"""Explicit v2.1.1 R05c diagnostic constructor; historical entry stays intact."""
from dataclasses import replace

from ...controllers.canonical.contracts import digest
from ...runtime.sessions.r05c_v211_candidate import PROFILE_ID, admit_request


def make_cpu100_candidate(*, horizon=6000):
    """Construct a separately identified, unqualified GeoPhys CPU candidate.

    This does not run physics, override receipts or assert R05c acceptance.
    Source creation retains the existing production receipt behavior.
    """
    from ...tasks.nut_assembly.specialization import NutAssemblyReferenceEnv

    original = NutAssemblyReferenceEnv.binding

    def build(provider, backend, gripper_control_hz, include_solution):
        admit_request(provider, backend, gripper_control_hz)
        value = original.build_native_feedback_profile(provider, backend, gripper_control_hz, include_solution)
        recipe = {**value['resolved_configuration'], 'native_feedback_profile': PROFILE_ID,
                  'diagnostic_candidate_qualification': 'NOT_REQUALIFIED'}
        return {**value, 'recipe': recipe, 'resolved_configuration': recipe,
                'recipe_identity': digest(recipe)}

    binding = replace(original, admit_native_feedback_profile=admit_request,
                      build_native_feedback_profile=build)
    return NutAssemblyReferenceEnv(provider='geophys', backend='cpu', horizon=horizon,
                                   _binding=binding, _native_feedback_request=100)
