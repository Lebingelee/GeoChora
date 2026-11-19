"""Deterministic goal evaluator: vocabulary-agnostic engine plus vocabulary plugins.

scene-predicates/1.0.0 (SimDataKit) is the first plugin (`vocabularies/scene_predicates.py`).
Consumes normalized scene states (world, metres, Z-up, WXYZ) and optional traces; imports no
TaskEnv or physics runtime. All results are three-valued (True/False/None).
"""
from validation.goals.evaluate import GOAL_BASES, EvalPolicy, evaluate_task, load_vocabulary
from validation.goals.state import SceneState, Trace
from validation.goals.vocabulary import VocabularyPlugin, WhenOutcome, register, registered, resolve

__all__ = ['GOAL_BASES', 'EvalPolicy', 'SceneState', 'Trace', 'VocabularyPlugin', 'WhenOutcome', 'evaluate_task',
           'load_vocabulary', 'register', 'registered', 'resolve']
