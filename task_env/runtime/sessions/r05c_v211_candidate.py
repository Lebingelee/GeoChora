"""Exact, diagnostic-only identity for a v2.1.1 R05c revalidation.

This is a new CPU/100 Hz candidate, not a change to the historical admission
or a claim that the candidate has passed a native run.
"""

PROFILE_ID = 'nutassembly-native-feedback-v211-cpu100-diagnostic-v1'
PROVIDER_REVISION = 'c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7'
CONTROLLER_IDENTITY = 'ea357a92bf10d7989d8e43ac566b15af9f5096ba5bed836570f83ce9f62b5468'


def admit_request(provider, backend, gripper_control_hz):
    """Admit only the explicit, separately identified scalar CPU candidate."""
    if (provider != 'geophys' or backend != 'cpu'
            or type(gripper_control_hz) is not int or gripper_control_hz != 100):
        raise ValueError('v2.1.1 R05c diagnostic candidate requires GeoPhys CPU and 100 Hz')
    return PROFILE_ID
