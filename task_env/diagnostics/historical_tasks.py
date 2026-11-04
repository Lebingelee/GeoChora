"""Explicit recovery-only legacy construction; never imported by active factory.

v1.0.0 is the canonical recovery source. Running current historical modules is
not exact historical source reconstruction and cannot grant old qualification.
Rendering/camera probes and legacy H5 replay use this boundary deliberately.
"""
def make_historical_env(uid, *, config=None, render_mode=None, **kwargs):
    from task_env.environment._historical import make_replay_env

    return make_replay_env(uid, config=config, render_mode=render_mode, **kwargs)
