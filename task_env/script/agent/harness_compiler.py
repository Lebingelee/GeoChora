"""Deterministic external pick-lift-v0 compiler. No registration or Core writes."""
from dataclasses import asdict, dataclass, replace
import argparse
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from harness_spec_schema import CandidateSpec, CheckFinding, CheckReport, save_json
from catalog_query import build_catalog, core_context, CatalogProvenanceError
from asset_check import check_assets

COMPILER_VERSION='0.1.0'


class CompilationRejected(ValueError):
    def __init__(self,report):
        self.report=report
        super().__init__('candidate rejected: '+', '.join(f.check for f in report.findings))


@dataclass(frozen=True)
class CompiledTask:
    artifact: object
    binding: object
    spec_sha256: str
    artifact_hash: str
    horizon: int
    source_xml_sha256: str

    def env_class(self):
        from task_env.tasks.reference_env import SelectedReferenceEnv
        compiled_horizon=self.horizon
        def initialize(env, *, provider='mujoco', backend='cpu', horizon=None):
            if horizon is not None and horizon != compiled_horizon:
                raise ValueError('horizon override differs from compiled spec')
            SelectedReferenceEnv.__init__(env,provider=provider,backend=backend,horizon=compiled_horizon)
        return type('CompiledCandidateEnv',(SelectedReferenceEnv,),
            {'uid':self.artifact.task_id,'binding':self.binding,'__init__':initialize})


def evaluate_lift(state, semantics):
    """Task-local lift predicate over public canonical state, not Core evaluator override.

    Reach and grasp are diagnostics only; this is not an On/In placement predicate.
    """
    from task_env.environment import TaskEvaluation
    semantics.require_state(state)
    p=semantics.parameters_si
    cube=state.pose_world['cube-v1'].position
    ee=state.pose_world['panda-v1/ee'].position
    opening=sum(state.joint_position[f'panda-v1/finger_joint{i}'] for i in (1,2))
    if not all(math.isfinite(float(x)) for x in (*cube,*ee,opening)):
        raise ValueError('nonfinite task state')
    lift=float(cube[2]-p['rest_height'])
    distance=math.sqrt(sum((a-b)**2 for a,b in zip(ee,cube,strict=True)))
    reached=distance<=p['reach_distance']
    grasped=bool(reached and opening<=p['gripper_closed_opening'])
    success=bool(lift>=p['lift_height'])
    terms={'reach':.1*(1-math.tanh(10*distance)), 'grasp':.25 if grasped else 0.,
           'lift':min(.4,max(0.,lift/p['lift_height'])*.4),'success':1. if success else 0.}
    metrics=dict(reached_cube=bool(reached),grasped_cube=grasped,lifted_cube=success,
        task_success=success,cube_x=float(cube[0]),cube_y=float(cube[1]),cube_z=float(cube[2]),
        cube_lift=lift,eef_to_cube_dist=distance,gripper_opening=float(opening),success_definition=True)
    return TaskEvaluation(float(sum(terms.values())),success,False,metrics,terms)


def compile_candidate(spec,catalog,*,provider='mujoco'):
    # Re-validate/copy caller-owned nested dictionaries before closing over any data.
    spec=CandidateSpec.from_dict(spec.to_dict())
    from task_env.artifacts import (PoseWorld,UniformDimension,RequiredCapabilitySet,
        ExecutionSpec,admit_capabilities)
    from task_env.artifacts.contracts import CapabilityAdmissionError
    from task_env.artifacts.execution import ResetSample
    from task_env.tasks.pick_cube import task as pick_cube
    from task_env.tasks.pick_cube.solution import PickCubeReadinessConfig,PickCubeReadinessSolution
    from task_env.tasks.reference_env import ReferenceTaskBinding
    from task_env.objects.pick_cube import PickCubeSceneComposer,CUBE_HALF_SIZE,CUBE_CONTACT_MARGIN
    from task_env.controllers.canonical import ProductionCanonicalPandaController
    from task_env.planners.completion import ExpertExecutionInfo
    from task_env.runtime.sessions import provider_manifest
    from task_env.runtime.sessions.api import PROFILE
    import numpy as np

    report=check_assets(spec,catalog)
    findings=list(report.findings)
    def reject(check,path,observed,expected,category='spec_invalid',locality='task_local',hint=None):
        findings.append(CheckFinding(check,category,locality,path,observed,expected,{},hint))
    if spec.template!='pick-lift-v0':
        reject('template_supported','template',spec.template,'pick-lift-v0','template_missing','harness')
    if spec.object_config['object_uid'] in catalog['object_uids'] and spec.object_config['object_uid']!='cube-v1':
        reject('template_object','object_config.object_uid',spec.object_config['object_uid'],'cube-v1','template_missing','harness')
    external=catalog.get('external_assets',{}).get(spec.object_config['object_uid'])
    if external is not None and external.get('template_kind')!='pick-lift-box-proxy-v0':
        reject('external_template_kind','object_config.object_uid',external.get('template_kind'),
            'pick-lift-box-proxy-v0','template_missing','harness')
    if spec.scene_config.get('fixtures',[]):
        reject('template_fixtures','scene_config.fixtures',spec.scene_config['fixtures'],[], 'template_missing','harness',
               'The table is implicit; additional fixture composition needs a new template.')
    if not spec.object_config['reset_z_fixed']:
        reject('fixed_z','object_config.reset_z_fixed',False,True)
    if spec.timebase_config!={'physics_dt':.002,'control_substeps':5}:
        reject('template_timebase','timebase_config',spec.timebase_config,{'physics_dt':.002,'control_substeps':5})
    if spec.success_config['lift_height_m']>.105:
        reject('expert_lift_envelope','success_config.lift_height_m',spec.success_config['lift_height_m'],'0 < lift <= 0.105')
    if spec.success_config['gripper_closed_opening_m']>.08:
        reject('gripper_envelope','success_config.gripper_closed_opening_m',spec.success_config['gripper_closed_opening_m'],'<= 0.08')
    scene,obj=spec.scene_config,spec.object_config
    for i,axis in enumerate('xy'):
        if abs(obj['initial_pos_xy'][i]-scene['table_center_xy'][i])+obj['reset_half_extent_m']+CUBE_HALF_SIZE>scene['table_half_size'][i]:
            reject('reset_supported_by_table',f'object_config.initial_pos_xy[{i}]',obj['initial_pos_xy'][i],
                   f'entire {axis} reset envelope including cube lies on table','init_infeasible','task_local',
                   'Move or narrow the reset envelope to fit the declared support surface.')
    base=pick_cube.build_artifact()
    missing=set(base.required_capabilities.names)-set(spec.required_capabilities)
    if missing:reject('template_capabilities','required_capabilities',spec.required_capabilities,sorted(base.required_capabilities.names))
    if findings:
        raise CompilationRejected(replace(report,tool='harness_compiler',status='fail',findings=findings))
    try:
        manifest=provider_manifest(provider)
    except ValueError as error:
        reject('provider_manifest_available','',str(error),f'available {provider} manifest','capability_unsupported','provider')
        raise CompilationRejected(replace(report,tool='harness_compiler',status='fail',findings=findings)) from error
    try:
        admit_capabilities(RequiredCapabilitySet(tuple(spec.required_capabilities)),manifest,
            ExecutionSpec(provider,PROFILE,'none','cpu',0,'strict'))
    except CapabilityAdmissionError as error:
        reject('provider_admission','required_capabilities',str(error),f'capabilities admitted by {provider}',
               'capability_unsupported','provider')
        raise CompilationRejected(replace(report,tool='harness_compiler',status='fail',findings=findings)) from error

    spec_hash=spec.spec_sha256()
    extent=obj['reset_half_extent_m']
    dims=tuple(UniformDimension(f'cube-v1.position_world.{axis}',*((c-extent,c+extent),)*4)
               for axis,c in zip('xy',obj['initial_pos_xy'],strict=True)) if extent else ()
    position=(*obj['initial_pos_xy'],scene['table_top_z']+CUBE_HALF_SIZE+CUBE_CONTACT_MARGIN)
    initial=replace(base.initialization,poses_world={'cube-v1':PoseWorld(position,(1.,0.,0.,0.))},randomization=dims)
    entities=tuple(replace(e,parameters_si={'top_z':scene['table_top_z'],
        **{f'half_size_{axis}':v for axis,v in zip('xyz',scene['table_half_size'],strict=True)},
        'center_x':scene['table_center_xy'][0],'center_y':scene['table_center_xy'][1]})
        if e.semantic_id=='tabletop-v1' else e for e in base.world.entities)
    if external is not None:
        entities=tuple(replace(e,asset_reference=f"external-mock/{external['uid']}/{external['sha256']}") if e.semantic_id=='cube-v1' else e for e in entities)
    world=replace(base.world,entities=entities,randomization_dimensions=tuple(d.name for d in dims))
    semantics=replace(base.semantics,evaluator='harness_pick_lift_v0',parameters_si={
        'rest_height':scene['table_top_z']+CUBE_HALF_SIZE,'lift_height':spec.success_config['lift_height_m'],
        'reach_distance':spec.success_config['reach_distance_m'],
        'gripper_closed_opening':spec.success_config['gripper_closed_opening_m']})
    artifact=replace(base,artifact_id=f'{spec.task_id}/compiler-{COMPILER_VERSION}/spec-{spec_hash}',
        task_id=spec.task_id,artifact_version='ver_001',world=world,initialization=initial,semantics=semantics,
        required_capabilities=RequiredCapabilitySet(tuple(spec.required_capabilities)))
    base_source=pick_cube.build_runtime_source(base,backend='cpu')
    composer=PickCubeSceneComposer(table_half_size=scene['table_half_size'],table_top_z=scene['table_top_z'],
        table_center_xy=scene['table_center_xy'],cube_world_pos=position,cube_world_quat=(1.,0.,0.,0.))
    source=replace(base_source,task_artifact_hash=artifact.identity_hash,scene_source=composer.build_source_description(),
        composition=replace(base_source.composition,task_uid=spec.task_id),
        config=replace(base_source.config,task=replace(base_source.config.task,task_uid=spec.task_id)))

    if external is not None:
        body=ET.fromstring(Path(external['path']).read_text())
        if body.tag!='body' or body.get('name')!='PickCube' or body.find("freejoint[@name='PickCube_joint']") is None:
            raise ValueError('external proxy must implement the template named body/freejoint contract')
        collision=body.find("geom[@name='PickCube_collision']")
        inertial=body.find('inertial')
        if collision is None or collision.get('type')!='box' or [float(v) for v in collision.get('size','').split()]!=[.025]*3:
            raise ValueError('external pick-lift proxy collision must be the declared 0.025 m half-size box')
        if inertial is None or float(inertial.get('mass','0'))!=.08:
            raise ValueError('external pick-lift proxy mass must be 0.08 kg')
        body.set('pos',' '.join(map(str,position)));body.set('quat','1 0 0 0')
        xml=ET.fromstring(source.scene_source.xml)
        replaced=False
        for parent in xml.iter():
            for child in list(parent):
                if child.tag=='body' and child.get('name')=='PickCube':
                    index=list(parent).index(child);parent.remove(child);parent.insert(index,body);replaced=True
        if not replaced:raise ValueError('template cube body missing')
        source=replace(source,scene_source=replace(source.scene_source,xml=ET.tostring(xml,encoding='unicode'),
            source_id=f"harness-mock:{external['sha256']}"))

    def build(requested_provider):
        # Native provider materialization/admission remains owned by Core.
        readiness=PickCubeReadinessConfig.from_source(artifact,source)
        controller=ProductionCanonicalPandaController.from_source(artifact,source)
        solution=PickCubeReadinessSolution(config=readiness)
        source_ids={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
            for name in ('harness_compiler.py','harness_spec_schema.py')}
        for name in ('task_env/tasks/pick_cube/task.py','task_env/tasks/pick_cube/solution.py',
                     'task_env/controllers/canonical/production.py'):
            path=Path(catalog['core_repo'])/name
            if path.is_file():source_ids[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        return dict(construction_id='harness-pick-lift-v0',artifact=artifact,source=source,
            resolved_configuration={'candidate_spec':spec.to_dict(),'spec_sha256':spec_hash,
                'compiler_version':COMPILER_VERSION,'source_xml_sha256':hashlib.sha256(source.scene_source.xml.encode()).hexdigest(),
                'artifact':artifact.to_mapping(),'artifact_sha256':artifact.identity_hash,
                'runtime_config':asdict(source.config),'readiness':asdict(readiness),
                'resolved_controller_action':asdict(controller.config),
                'resolved_controller_gripper':asdict(controller.gripper_config),
                'runtime_source_bindings':{name:dict(getattr(source,name)) for name in
                    ('joints','bodies','frames','free_joints','joint_targets')},
                'runtime_open_actuators':list(source.open_actuators),
                'external_asset':external,'asset_bundle_sha256':catalog.get('asset_bundle_sha256'),
                'source_revision':catalog['core_commit'],'source_sha256':source_ids},
            source_revision=catalog['core_commit'],source_sha256=source_ids,
            controller=controller,solution=solution)

    def sample_reset(requested_artifact,seed):
        if requested_artifact.identity_hash!=artifact.identity_hash:raise ValueError('compiled artifact required')
        if type(seed) is not int or seed<0:raise ValueError('nonnegative integer seed required')
        rng=np.random.Generator(np.random.PCG64(seed))
        pos=list(position)
        for i,dim in enumerate(dims):pos[i]=float(rng.uniform(*dim.training_bounds))
        return ResetSample.create(schema_version='reset-sample-v0',task_artifact_hash=artifact.identity_hash,
            sampler_id='harness/uniform-xy',sampler_version='pcg64-v0',task_seed=seed,
            joint_position=dict(initial.joint_position),poses_world={'cube-v1':PoseWorld(tuple(pos),(1.,0.,0.,0.))},
            velocity_policy='zero_named_joint_and_entity_velocities',
            control_policy='arm_targets_at_initial_joints_gripper_open',settle_steps=initial.settle_steps)

    def execution_info(env):
        return {'execution_info':ExpertExecutionInfo('expert-execution-info-v1',env.state.control_step,
            env.state.simulation_time,env.controller.readiness(env.state,env.feedback))}

    binding=ReferenceTaskBinding(build=build,reset_sample=sample_reset,evaluate=evaluate_lift,
        object_poses=(('cube-v1','cube_v1'),),external_actions=True,interval_mode='grouped',recorder_mode='canonical',
        reset_expert_kwargs=execution_info,observe_expert_kwargs=lambda env,guard:execution_info(env))
    return CompiledTask(artifact,binding,spec_hash,artifact.identity_hash,spec.horizon,
        hashlib.sha256(source.scene_source.xml.encode()).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('spec','core-repo','output'):parser.add_argument('--'+arg,required=True,type=Path)
    parser.add_argument('--catalog',type=Path)
    parser.add_argument('--provider',default='mujoco')
    args=parser.parse_args()
    ctx=core_context(args.core_repo)
    spec=None
    try:
        spec=CandidateSpec.load(args.spec)
    except (ValueError,TypeError,KeyError,OSError) as error:
        report=CheckReport(None,None,ctx['core_commit'],ctx['core_dirty'],'harness_compiler','error',
            [CheckFinding('spec_parse','spec_invalid','task_local','',str(error),'valid CandidateSpec',{})])
    else:
        try:
            catalog=json.loads(args.catalog.read_text()) if args.catalog else build_catalog(args.core_repo)
            if catalog['core_commit']!=ctx['core_commit'] or catalog['core_repo']!=ctx['core_repo']:
                raise CatalogProvenanceError('catalog provenance mismatch')
            compiled=compile_candidate(spec,catalog,provider=args.provider)
            report=CheckReport(compiled.spec_sha256,compiled.artifact_hash,ctx['core_commit'],ctx['core_dirty'],
                'harness_compiler','pass',details={'artifact':compiled.artifact.to_mapping(),
                'source_xml_sha256':compiled.source_xml_sha256,'template':spec.template,'provider':args.provider})
        except CompilationRejected as error:
            report=error.report
        except Exception as error:
            report=CheckReport(spec.spec_sha256(),None,ctx['core_commit'],ctx['core_dirty'],'harness_compiler','error',
                [CheckFinding('compile_execution','execution_fault','harness','',f'{type(error).__name__}: {error}',
                    'successful compiler execution',{'phase':'compile'},'Diagnose Harness; do not revise spec to mask internal errors.')])
    report.save(args.output)
    print(json.dumps({'status':report.status,'output':str(args.output),'artifact_hash':report.artifact_hash}))
    return {'pass':0,'fail':1,'error':2}[report.status]

if __name__=='__main__':raise SystemExit(main())
