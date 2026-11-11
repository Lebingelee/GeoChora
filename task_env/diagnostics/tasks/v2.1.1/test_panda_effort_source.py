"""Pure admission checks for the Panda transmission used by formal PickCube."""

import xml.etree.ElementTree as ET

import pytest

from task_env.runtime.sessions.mujoco_composition import panda_effort_source_limits


def test_panda_source_preserves_paired_transmission_and_signed_limits():
    actuators = ''.join(
        f'<general name="actuator{i}" class="panda" joint="joint{i}" '
        'gainprm="1" biasprm="0 -1 0"/>' for i in range(1, 8)
    ) + ('<general name="actuator8" class="panda" tendon="split" '
         'gainprm="1" biasprm="0 -1 0"/>')
    root = ET.fromstring(
        '<mujoco><default><default class="panda"><general biastype="affine" '
        'forcerange="-5 5"/></default></default>'
        '<tendon><fixed name="split"><joint joint="finger_joint1" coef="0.5"/>'
        '<joint joint="finger_joint2" coef="0.5"/></fixed></tendon>'
        '<equality><joint joint1="finger_joint1" joint2="finger_joint2"/></equality>'
        f'<actuator>{actuators}</actuator></mujoco>'
    )
    assert panda_effort_source_limits(root) == [(-5., 5.)] * 8
    root.find('./tendon/fixed/joint').set('coef', '1')
    with pytest.raises(ValueError, match='tendon/equality'):
        panda_effort_source_limits(root)
