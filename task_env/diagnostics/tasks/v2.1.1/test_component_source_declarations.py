"""Behavior checks for source and initial-control declarations."""

from types import SimpleNamespace

import numpy as np

from task_env.assembly.compiler import _initial_state
from task_env.environment.types import InitialStateSpec
from task_env.robots.panda import PandaAgent


def test_initial_control_uses_subject_declarations_for_any_robot():
    class OtherRobot:
        uid = 'other-robot'

        def initial_state_spec(self):
            return InitialStateSpec(joint_positions=(('hinge', 0.75),))

        def reference_spec(self):
            return SimpleNamespace(joint_names=('hinge',), actuator_names=('motor', 'opening'))

        def component_initial_control(self):
            return ((('motor', 'hinge'),), ('opening',))

    model = SimpleNamespace(joint_data={
        'n_qpos': 1, 'n_dof': 1, 'n_actuators': 2,
        'jnt_qposadr': np.array([0]),
    })
    references = SimpleNamespace(
        agents={'other-robot': SimpleNamespace(ctrl_range=np.array([[-2., 2.], [0., 4.]]))},
        names=SimpleNamespace(joints={'hinge': 0}, actuators={'motor': 0, 'opening': 1}),
    )
    state = _initial_state(model, (OtherRobot(),), references)
    np.testing.assert_array_equal(state.qpos, [0.75])
    np.testing.assert_array_equal(state.ctrl, [0.75, 4.0])
    class ForeignControl(OtherRobot):
        def component_initial_control(self):
            return ((('foreign_motor', 'hinge'),), ())

    import pytest
    with pytest.raises(ValueError, match='owned by the Robot'):
        _initial_state(model, (ForeignControl(),), references)


def test_panda_declares_its_position_and_opening_channels():
    targets, upper_limits = PandaAgent().component_initial_control()
    assert targets == tuple((f'actuator{i}', f'joint{i}') for i in range(1, 8))
    assert upper_limits == ('actuator8',)


def test_tabletop_consumes_declared_robot_source_without_uid_dispatch(tmp_path, monkeypatch):
    import sys
    import xml.etree.ElementTree as ET
    from task_env.tasks.worlds.tabletop import TabletopSceneBuilder

    class SceneSource:
        @staticmethod
        def mjcf_string(xml, **kwargs):
            return SimpleNamespace(xml=xml, **kwargs)

    monkeypatch.setitem(sys.modules, 'scene', SimpleNamespace(SceneSource=SceneSource))
    source = tmp_path / 'robot.xml'
    source.write_text('<mujoco><worldbody><body name="tool"/></worldbody></mujoco>')

    class OtherRobot:
        uid = 'other-robot'

        def single_mjcf_source(self):
            return source

        def component_mjcf_frames(self):
            return (('tool', {'name': 'tool_tip', 'pos': '0 0 0.1'}),)

        def component_scene_identity(self):
            return ('other-tabletop', 'other-tabletop-v1')

    spec = SimpleNamespace(agent_uids=('other-robot',))
    result, adapter = TabletopSceneBuilder().build_scene_source(spec, (OtherRobot(),))
    root = ET.fromstring(result.xml)
    assert adapter == 'other-tabletop-v1'
    assert result.label == 'other-tabletop'
    assert root.find('./worldbody/body[@name="tool"]/site').get('name') == 'tool_tip'
    assert root.find('./worldbody/body[@name="grasp_table"]') is not None
    assert root.find('./option').get('timestep') == '0.002'


def test_fixed_attachment_retains_strict_historical_source_validation():
    import importlib.util
    from pathlib import Path
    from task_env.assembly.panda_source_profiles import fixed_attachment_source_recipe
    from task_env.robots.panda import PANDA_ASSET_ROOT

    path = Path(__file__).with_name('r06b_order_recipe.py')
    spec = importlib.util.spec_from_file_location('r06b_order_recipe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    arm = (PANDA_ASSET_ROOT / 'panda_nohand.xml').read_text()
    hand = (PANDA_ASSET_ROOT / 'hand.xml').read_text()
    assert fixed_attachment_source_recipe(arm, hand) == 'r03b-exact'
    derived_arm, derived_hand = module.derive_r06b_order_sources(arm, hand)
    assert fixed_attachment_source_recipe(derived_arm, derived_hand) == 'r06b-order-v1'
    import pytest
    with pytest.raises(ValueError):
        fixed_attachment_source_recipe(derived_arm + '\n', derived_hand)


def test_tabletop_empty_and_panda_component_source(monkeypatch):
    import sys
    import xml.etree.ElementTree as ET
    from task_env.tasks.worlds.tabletop import TabletopSceneBuilder

    class SceneSource:
        @staticmethod
        def mjcf_string(xml, **kwargs):
            return SimpleNamespace(xml=xml, **kwargs)

    monkeypatch.setitem(sys.modules, 'scene', SimpleNamespace(SceneSource=SceneSource))
    world = TabletopSceneBuilder()
    empty, empty_adapter = world.build_scene_source(SimpleNamespace(agent_uids=()), ())
    assert empty_adapter == 'inline_empty_tabletop_v1'
    assert ET.fromstring(empty.xml).find('./worldbody/body[@name="grasp_table"]') is not None
    robot = PandaAgent()
    source, adapter = world.build_scene_source(SimpleNamespace(agent_uids=(robot.uid,)), (robot,))
    assert adapter == 'task_env_empty_tabletop_panda_v1'
    root = ET.fromstring(source.xml)
    assert root.find('.//body[@name="hand"]/site[@name="nutassembly_ee_site"]') is not None
    assert root.find('./worldbody/body[@name="grasp_table"]') is not None


def test_panda_hand_profile_rejects_changed_transmission():
    import xml.etree.ElementTree as ET
    import pytest
    from task_env.assembly.panda_source_profiles import validate_attachment_plan, validate_child_source
    from task_env.robots.panda import PANDA_ASSET_ROOT

    root = ET.parse(PANDA_ASSET_ROOT / 'hand.xml').getroot()
    plan = SimpleNamespace(child_entity_id='panda-hand', namespace_prefix='probe_hand_',
                           native_tendon_names={'panda-hand/split': 'probe_hand_split'})
    validate_attachment_plan(plan)
    validate_child_source(root, plan)
    root.find('./tendon/fixed/joint').set('coef', '0.6')
    with pytest.raises(ValueError, match='tendon order/coefficients'):
        validate_child_source(root, plan)
    plan.native_tendon_names = {'panda-hand/split': 'foreign_split'}
    with pytest.raises(ValueError, match='exact Hand split tendon'):
        validate_attachment_plan(plan)


def test_attachment_structure_and_panda_transmission_have_separate_owners():
    from dataclasses import replace
    import pytest
    from task_env.assembly.fixed_attachment import validate_fixed_attachment_scene
    from task_env.assembly.panda_fixed_source import declare_panda_fixed_source
    from task_env.assembly.panda_source_profiles import validate_panda_fixed_attachment_scene
    from task_env.robots.assembled_panda import AssembledPandaAgent

    declaration = declare_panda_fixed_source(AssembledPandaAgent().asset_manifest())
    foreign_tendon = replace(declaration.attachment_plan, native_tendon_names={})
    validate_fixed_attachment_scene(foreign_tendon, declaration.assembly, declaration.scene)
    with pytest.raises(ValueError, match='exact Hand split tendon'):
        validate_panda_fixed_attachment_scene(foreign_tendon, declaration.assembly, declaration.scene)


def test_declared_contact_profile_is_lowered_by_selected_provider():
    import xml.etree.ElementTree as ET
    import pytest
    from task_env.runtime.sessions.source_composition_adapters import apply_declared_provider_source_options

    xml = '<mujoco><option timestep="0.002"/><worldbody/></mujoco>'
    declaration = {'mujoco': {'option_overrides': {'noslip_iterations': 2},
                               'native_version_tested': '3.8.1'}}
    actual, profile = apply_declared_provider_source_options(
        xml, provider='mujoco', declarations=declaration)
    assert ET.fromstring(actual).find('option').get('noslip_iterations') == '2'
    assert profile['model_option_overrides'] == {'noslip_iterations': 2}
    assert apply_declared_provider_source_options(xml, provider='geophys',
                                                   declarations=declaration) == (xml, None)
    declaration['mujoco']['option_overrides'] = {'noslip_iterations': 3}
    with pytest.raises(ValueError, match='provider profile changed'):
        apply_declared_provider_source_options(xml, provider='mujoco', declarations=declaration)


def test_declared_usd_paths_follow_scene_and_task_ownership(monkeypatch):
    import pytest
    from task_env.runtime.sessions import source

    joint = SimpleNamespace(parent_frame=SimpleNamespace(frame_id='base'),
                            child_frame=SimpleNamespace(frame_id='hand'))
    scene = SimpleNamespace(articulations=(SimpleNamespace(
        entity_id='robot-x', root_frame_id='base', joints=(joint,)),))
    artifact = SimpleNamespace(legacy_frame_bindings={'robot/base': 1, 'robot/tool': 2,
        'object': 3, 'table': 4}, initialization=SimpleNamespace(poses_world={'object': 0}))
    monkeypatch.setattr(source, 'scalar_joint_source_bindings', lambda *_: {'robot/hinge': 'hinge'})
    kwargs = dict(robot_uid='robot-x', geometry_root='/World/robot', entry_prim='/World',
                  base_semantic='robot/base', robot_frames={'robot/tool': ('hand', 'tip')},
                  world_bodies={'object': 'object'}, world_frames={'table': 'table/top'},
                  free_body_semantics=('object',))
    joints, bodies, frames, free = source.bind_declared_usd_paths(scene, artifact, **kwargs)
    assert joints == {'robot/hinge': 'hinge'}
    assert bodies == {'robot/base': '/World/robot/base', 'object': '/World/object'}
    assert frames['robot/tool'] == '/World/robot/base/hand/tip'
    assert free == {'object': '/World/object'}
    with pytest.raises(ValueError, match='floating bodies'):
        source.bind_declared_usd_paths(scene, artifact, **{**kwargs, 'free_body_semantics': ()})
    with pytest.raises(ValueError, match='distinct semantic owners'):
        source.bind_declared_usd_paths(scene, artifact, **{
            **kwargs, 'world_frames': {'robot/tool': 'table/top'}})


def test_component_scene_compiler_resolves_empty_and_panda_sources():
    from task_env.assembly.compiler import compile_task_scene
    from task_env.environment.types import TaskCompositionSpec
    from task_env.registry import make_scene

    scene = make_scene('tabletop-v1')
    empty = compile_task_scene(composition=TaskCompositionSpec('empty-v1', 'tabletop-v1'),
                               scene=scene, agents=(), objects=())
    assert empty.composition_adapter == 'inline_empty_tabletop_v1'
    robot = PandaAgent()
    compiled = compile_task_scene(
        composition=TaskCompositionSpec('empty-v1', 'tabletop-v1', ('panda-v1',)),
        scene=scene, agents=(robot,), objects=())
    assert compiled.composition_adapter == 'task_env_empty_tabletop_panda_v1'
    refs = compiled.references.agents[robot.uid]
    np.testing.assert_array_equal(compiled.initial_state.ctrl[refs.arm_actuator_ids],
                                  compiled.initial_state.qpos[refs.arm_qpos_ids])
    np.testing.assert_array_equal(compiled.initial_state.ctrl[refs.gripper_actuator_ids],
                                  refs.ctrl_range[refs.gripper_actuator_ids, 1])


def test_compile_releases_owned_snapshot_when_controller_factory_fails():
    import pytest
    from task_env.assembly.compiler import ReferenceTaskDeclarationV1

    receipt = SimpleNamespace(closed=False)
    receipt.close = lambda: setattr(receipt, 'closed', True)
    source = SimpleNamespace(source_snapshot_receipt=receipt)
    declaration = SimpleNamespace(artifact=SimpleNamespace(compile=lambda: object()),
                                  compile_source=lambda *args, **kwargs: source)
    def fail_controller(*_args):
        raise RuntimeError('controller failure')
    with pytest.raises(RuntimeError, match='controller failure'):
        ReferenceTaskDeclarationV1.compile(declaration, scene_source=object(), config=object(),
                                           controller_factory=fail_controller, own_snapshot=True)
    assert receipt.closed
