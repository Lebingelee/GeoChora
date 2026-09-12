"""Lazy RSL-RL integration."""

from importlib import import_module


_EXPORTS = {
    "TaskEnvRslVecAdapter": (".adapter", "TaskEnvRslVecAdapter"),
    "RslActionTransformSpec": (".action_transform", "RslActionTransformSpec"),
    "RslObservationProfile": (".action_transform", "RslObservationProfile"),
    "RslLearnerProfile": (".action_transform", "RslLearnerProfile"),
    "resolve_action_profile": (".action_transform", "resolve_action_profile"),
    "resolve_learner_profile": (".action_transform", "resolve_learner_profile"),
    "resolve_task_action_profile": (
        ".action_transform",
        "resolve_task_action_profile",
    ),
    "build_runner": (".runner", "build_runner"),
    "RslPpoOptions": (".training", "RslPpoOptions"),
    "RslTrainingBundle": (".training", "RslTrainingBundle"),
    "current5_train_cfg": (".training", "current5_train_cfg"),
    "resolve_resume_checkpoint": (".training", "resolve_resume_checkpoint"),
    "train": (".training", "train"),
    "check_nan": (".nan_check", "check_nan"),
    "install_runner_nan_check": (".nan_check", "install_runner_nan_check"),
    "RolloutNanChecker": (".nan_check", "RolloutNanChecker"),
    "dispatch_check_nan": (".nan_check", "dispatch_check_nan"),
}


def __getattr__(name: str):
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value


__all__ = sorted(_EXPORTS)
