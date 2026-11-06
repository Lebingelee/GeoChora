"""Production construction and fake terminal; no provider or physics.

Requires authorized dual-lock pure source parsing.
"""

import pytest


@pytest.mark.parametrize(('physical_profile', 'expected_body'), [
    ('panda-direct-effort-v1', 'single'),
    ('panda-direct-effort-wrench-v1', ('panda-main', 'hand')),
    ('panda-direct-effort-object-wrench-v1', ('square-peg-instance', 'peg1')),
    ('panda-split-direct-effort-v1', None),
])
@pytest.mark.parametrize('stale_after', [False, True])
def test_configured_physical_effort_and_wrench_with_fake_terminal(tmp_path, physical_profile, expected_body, stale_after):
    from dataclasses import replace
    import shutil
    from task_env import make_env
    from task_env.artifacts import CanonicalStateView, PoseWorld
    from task_env.artifacts.contracts import CapabilityAssessmentRowV1, CapabilityAssessmentV1
    from task_env.artifacts.state import (StateBoundaryIdentity, StateSampleClock, StateViewLifetime,
        CanonicalStateViewV1, CanonicalStateViewV2, CanonicalStatePublicationV1,
        CanonicalStatePublicationV2, TypedJointStateValue, TypedFrameStateValue)
    from task_env.controllers.canonical.physical_commands import PhysicalJointBuildReceiptV1, PhysicalBodyBuildReceiptV1, PhysicalControlReceiptV1
    env=make_env('panda-position-servo-candidate-v1',config={'provider':'geophys','backend':'cpu',
        'horizon':8,'physical_profile':physical_profile,
        'source_workspace':str(tmp_path / 'candidate-source')})
    try:
        execution=env.binding.physical_control_profile(env); scene=execution.scene
        assert env.value['resolved_configuration']['physical_profile'] == physical_profile
        assert env.value['resolved_configuration']['physical_binding'] == execution.compiled.binding.identity_hash
        channels = {item.joint_id: item for item in execution.compiled.binding.channels}
        assert channels['joint1'].native_range == (-87., 87.)
        assert channels['joint7'].native_range == (-12., 12.)
        assert channels['finger_joint1'].effort_range == (-50., 50.)
        assert channels['finger_joint2'].transmission_coefficient == .5
        from task_env.tasks.position_candidate.physical_profile import build_panda_direct_effort_execution
        source = env.value['source']
        xml = source.scene_source.xml
        assert 'coef="0.5"' in xml
        changed = replace(source, scene_source=replace(source.scene_source,
                          xml=xml.replace('coef="0.5"', 'coef="0.4"', 1)))
        with pytest.raises(ValueError, match='source closure differs'):
            build_panda_direct_effort_execution(scene, env.artifact, changed)
        from task_env.assembly.assets import _source_closure_digest
        from task_env.runtime.sessions.source import project_scene_definition_v3_to_mjcf, source_asset_bytes
        projected = project_scene_definition_v3_to_mjcf(changed.scene_source.xml, scene)
        changed = replace(changed, source_closure_digest=_source_closure_digest({
            'scene.xml': projected.encode('utf-8'),
            **source_asset_bytes(changed.scene_source.base_dir, projected)}))
        with pytest.raises(ValueError, match='tendon/equality'):
            build_panda_direct_effort_execution(scene, env.artifact, changed)
        pose=PoseWorld((0.,0.,0.),(1.,0.,0.,0.))
        class FakeTerminal:
            physical_control_generation=1
            step_index=0
            writes=0
            def boundary(self):
                return StateBoundaryIdentity('state-boundary-identity-v1','fake-episode',
                    'reset-'+'d'*64,scene.identity_hash,'fake-scene','fake-material',self.step_index,self.step_index)
            def state_boundary_identity(self): return self.boundary()
            def publication(self, version):
                boundary=self.boundary(); clock=StateSampleClock('state-sample-clock-v1','evaluation_boundary',self.step_index,self.step_index*.01)
                joints=tuple(TypedJointStateValue('typed-joint-state-v1',j.parent_frame.entity_id,j.joint_id,
                    j.kind,j.position_representation,(0.,),j.velocity_representation,(0.,))
                    for j in execution.joint_bindings.values())
                frames=tuple(TypedFrameStateValue('typed-frame-state-v1',f,pose) for f in execution.frame_bindings.values())
                lifetime=StateViewLifetime('state-view-lifetime-v1','fake-material',boundary,self.step_index,'owned_snapshot','retained')
                if version==1:
                    view=CanonicalStateViewV1('canonical-state-v1','SI_right_handed_z_up_wxyz',boundary,clock,joints,frames,())
                    return CanonicalStatePublicationV1('canonical-state-publication-v1',view,lifetime)
                view=CanonicalStateViewV2('canonical-state-v2','SI_right_handed_z_up_wxyz',boundary,clock,joints,frames,(),())
                return CanonicalStatePublicationV2('canonical-state-publication-v2',view,lifetime)
            def snapshot_v2(self, **kwargs): return self.publication(2)
            def snapshot_v1(self, **kwargs):
                return self.initial if stale_after and self.step_index else self.publication(1)
            def assess_physical_control(self, binding):
                return CapabilityAssessmentV1('capability-assessment-v1',binding.identity_hash,'native_build',tuple(
                    CapabilityAssessmentRowV1('capability-assessment-row-v1',name,f'binding:{binding.identity_hash}',
                    'required','supported','implemented','available','none','native_build','fake terminal only',None,None)
                    for name in ('joint_effort','transmission','native_drive_state','body_force','body_torque','body_frame','body_offset_point')))
            def physical_joint_build_receipt(self,binding):
                # A simulated native receipt belongs only to this fake terminal.
                return PhysicalJointBuildReceiptV1('physical-joint-build-receipt-v1',binding.identity_hash,
                    binding.source_closure_sha256,'fake-material',binding.channels,'native_build')
            def physical_body_build_receipt(self,binding):
                return PhysicalBodyBuildReceiptV1('physical-body-build-receipt-v1',binding.identity_hash,
                    binding.source_closure_sha256,'fake-material',binding.bodies,'native_build')
            def apply_physical_command_batch(self,resolved):
                self.writes+=1
                self.values={x.joint_id:x.value for x in resolved.joints}
                self.wrench=resolved.body_wrenches[0] if resolved.body_wrenches else None
                return PhysicalControlReceiptV1('physical-control-receipt-v1',resolved.input_batch.context,
                    resolved.input_batch.identity_hash,'native_write_ack',resolved.accepted_receipt.contribution_ids,
                    'fake-terminal','per-channel')
            def step(self):
                self.step_index+=1
                return CanonicalStateView('canonical-state-v0','SI_right_handed_z_up_wxyz',self.step_index,
                    self.step_index*.01,{}, {}, {'square-peg-instance/peg1':pose})
        fake=FakeTerminal()
        fake.initial = fake.publication(1)
        env.session=fake; env._stopped=False
        env.position_scene=scene; env.position_joint_bindings=execution.joint_bindings
        env.position_frame_bindings=execution.frame_bindings
        env.typed_state=fake.publication(1)
        env.state=CanonicalStateView('canonical-state-v0','SI_right_handed_z_up_wxyz',0,0.,{}, {},
                                     {'square-peg-instance/peg1':pose})
        action = ((1.,2.,3.,4.,5.,6.,7.,8.) if expected_body == 'single' else
                  {execution.controllers[0].identity:(1.,2.,3.,4.,5.,6.,7.),
                   execution.controllers[1].identity:(8.,)} if expected_body is None else
                  {execution.controllers[0].identity:(1.,2.,3.,4.,5.,6.,7.,8.),
                   execution.controllers[1].identity:(0.,0.,1.,0.,-0.01,0.)})
        if stale_after:
            with pytest.raises(ValueError, match='post-step publication is stale'):
                env.step(action)
            assert env.execution_fault is not None
            assert env.typed_state.view.boundary.control_step == 0
            return
        observation,reward,terminated,truncated,info=env.step(action)
        expected={**{f'joint{i}':float(i) for i in range(1,8)},'finger_joint1':4.,'finger_joint2':4.}
        assert fake.values==expected and fake.writes==1 and fake.step_index==1
        if expected_body is None or expected_body == 'single':
            assert fake.wrench is None
        else:
            assert fake.wrench.force_world_N==(0.,0.,1.)
            assert (fake.wrench.entity_id, fake.wrench.body_id) == expected_body
            assert all(abs(a-b)<1e-12 for a,b in zip(fake.wrench.torque_at_body_origin_world_Nm,(0.,-.01,0.)))
        assert info['physical_control_v1']['native_write_ack']['producer_id']=='fake-terminal'
        assert info['physical_control_v1']['submitted']['stage']=='submitted'
        assert info['physical_control_v1']['accepted']['stage']=='accepted'
        assert info['physical_control_v1']['native_write_ack']['stage']=='native_write_ack'
        assert env.typed_state.view.boundary.control_step==1
        assert not terminated and not truncated

    finally:
        env.session=None
        env._stopped=True
        # The fake never performed reset; discard its injected publication before close.
        env._published_position_state=None
        env.close()
        # This test owns this fresh staging copy; source identity and logs are
        # retained separately, while pinned asset bytes remain untouched.
        shutil.rmtree(tmp_path / 'candidate-source')
