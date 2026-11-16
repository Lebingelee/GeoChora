"""Diagnostic native-clock owner; frozen EqualRateGripperServo stays untouched.

Same R3 physical-time law at500Hz independent of arm policy rate. This mode has
its own strict recorder admission; it is never labeled outer-equal-rate.
"""
from ....controllers.canonical.gripper_execution import NativeRateGripperServo


def validate_native_cadence(recording):
    if recording['recipe']['cadence']!='fixed-native-500hz-v1':
        raise ValueError('Incorrect native-clock recording label')
    for transition in recording['transitions']:
        interval=transition['interval']
        if interval['physics_dt']!=.002 or len(interval['substeps'])!=interval['control_substeps']:
            raise ValueError('Native-clock interval mismatch')
        if not all(s['updated'] is True for s in interval['substeps']):
            raise ValueError('Native-clock command update missing')
