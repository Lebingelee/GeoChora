"""Deterministic external pick-lift-v0 compiler. No registration or Core writes."""
from dataclasses import asdict, dataclass, replace
import argparse
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
if __package__:
    from .harness_spec_schema import CandidateSpec, CheckFinding, CheckReport, save_json
    from .catalog_query import build_catalog, core_context, CatalogProvenanceError
    from .asset_check import check_assets
else:
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


@dataclass(frozen=True)
class CompiledBuiltinPickCubeExampleV1:
    """Harness construction receipt for the selected Core-owned PickCube task."""

    spec: object
    artifact_hash: str
    construction_id: str
    recipe_identity: str
    controller_identity: str
    solution_identity: str
    source_revision: str
    source_sha256: dict
    runtime_source_id: str
    runtime_source_sha256: str
    working_tree_scope: dict
    repo_dirty: bool
    resolved_config: object = None



def _example_working_tree_context(core_repo, scope):
    """Require tracked-clean Core and only the exact byte-pinned untracked set."""
    import hashlib
    import subprocess
    from pathlib import Path

    repo = Path(core_repo).resolve()
    porcelain = subprocess.check_output(
        ['git', '-C', str(repo), 'status', '--porcelain=v1', '--untracked-files=all'],
        text=True,
    )
    rows = []
    for line in porcelain.splitlines():
        if not line.startswith('?? '):
            raise ValueError(f'built-in example requires a tracked-clean Core checkout: {line!r}')
        rows.append(line[3:])
    actual_paths = sorted(rows)
    expected = dict(scope.expected_untracked)
    if actual_paths != sorted(expected):
        raise ValueError(f'untracked paths differ from the versioned example allowlist: {actual_paths!r}')
    measured = []
    for relative in actual_paths:
        path = (repo / relative).resolve(strict=True)
        if not path.is_relative_to(repo):
            raise ValueError('expected untracked path escapes the Core checkout')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected[relative]:
            raise ValueError(f'expected untracked file hash changed: {relative}')
        measured.append({'path': relative, 'sha256': digest})
    return {
        'schema_version': scope.schema_version,
        'tracked_clean': True,
        'repo_dirty': bool(porcelain),
        'expected_untracked': measured,
    }


def resolve_builtin_pickcube_example(spec, catalog, *, working_tree_scope):
    """Compile the F06 versioned example without touching strict CandidateSpec.

    Construction and source identity remain owned by the current Core PickCube
    task. The Isaac branch binds its exact USD closure and F06 profile; compiling
    this route does not itself admit a production provider capability.
    """
    if __package__:
        from .builtin_example_schema import BuiltinPickCubeExampleV1, ExampleWorkingTreeScopeV1
        from .catalog_query import core_context
    else:
        from builtin_example_schema import BuiltinPickCubeExampleV1, ExampleWorkingTreeScopeV1
        from catalog_query import core_context

    if type(spec) is not BuiltinPickCubeExampleV1:
        raise TypeError('compile_builtin_pickcube_example requires the exact versioned F06 example spec')
    if type(working_tree_scope) is not ExampleWorkingTreeScopeV1:
        raise TypeError('built-in example requires an exact versioned working-tree scope')
    if catalog.get('schema_version') != 'harness-catalog-v0':
        raise ValueError('built-in example requires the current Harness catalog schema')
    context = core_context(catalog['core_repo'])
    if context['core_repo'] != str(Path(catalog['core_repo']).resolve()):
        raise ValueError('catalog Core root is not canonical')
    if catalog.get('core_commit') != context['core_commit']:
        raise ValueError('catalog is stale for the currently imported Core commit')
    tree = _example_working_tree_context(context['core_repo'], working_tree_scope)
    actual_dirty = bool(__import__('subprocess').check_output(
        ['git', '-C', context['core_repo'], 'status', '--porcelain'], text=True,
    ))
    if bool(catalog.get('core_dirty')) != actual_dirty:
        raise ValueError('catalog repo_dirty fact differs from the measured checkout')
    record = catalog.get('builtin_examples', {}).get('pickcube-harness-example-v1')
    if not isinstance(record, dict) or record.get('task_uid') != spec.task_uid:
        raise ValueError('catalog does not expose the exact built-in PickCube example')
    if spec.provider not in ('mujoco', 'geophys', 'isaacsim'):
        raise ValueError(f'{spec.provider} is optional and not admitted by the F06 primary route compiler')
    if spec.task_uid not in catalog.get('env_uids', ()):
        raise ValueError('selected public PickCube UID is absent from the current Core registry')
    # The public factory is the sole resolver in the worker. The versioned
    # Harness spec has already validated these route and field domains.
    selected_config = {
        'execution': {'physics_provider': spec.provider, 'physics_backend': spec.backend,
                      'physics_device': spec.device,
                      **({'source_delivery_manifest': spec.source_delivery_manifest}
                         if spec.source_delivery_manifest is not None else {})},
        'episode': {'horizon': spec.horizon_control_ticks},
        'task': {'controller_profile': spec.controller_profile},
    }
    if spec.provider != 'isaacsim':
        provider_row = catalog.get('providers', {}).get(spec.provider)
        if not isinstance(provider_row, dict) or provider_row.get('available') is not True:
            raise ValueError(f'{spec.provider} provider manifest is unavailable in this catalog')
    else:
        route = record.get('provider_routes', {}).get('isaacsim')
        if (not isinstance(route, dict) or route.get('backend') != 'cuda'
                or route.get('device') != 'cuda:0'
                or type(route.get('runtime_tested')) is not bool):
            raise ValueError('catalog does not expose the exact F06 Isaac execution intersection')
    return selected_config, tree, actual_dirty


def compile_builtin_pickcube_example(spec, catalog, *, working_tree_scope):
    """Construct the public environment once and return its facts with its owner."""
    from task_env import make_env
    selected_config, tree, actual_dirty = resolve_builtin_pickcube_example(
        spec, catalog, working_tree_scope=working_tree_scope,
    )
    env = make_env(spec.task_uid, config=selected_config)
    try:
        resolved_config = env.resolved_public_config
        value = env.value
        artifact = value['artifact']
        if artifact.task_id != 'pick-cube-v1' or artifact.timebase.physics_dt != spec.physics_dt_s \
                or artifact.timebase.control_substeps != spec.control_substeps:
            raise ValueError('built-in PickCube recipe or timebase differs from the F06 example contract')
        source = value['source']
        source_digest = (
            source.source_closure_digest if spec.provider == 'isaacsim'
            else hashlib.sha256(source.scene_source.xml.encode()).hexdigest()
        )
        compiled = CompiledBuiltinPickCubeExampleV1(
            spec=spec,
            artifact_hash=artifact.identity_hash,
            construction_id=value['construction_id'],
            recipe_identity=value['recipe_identity'],
            controller_identity=value['controller'].identity,
            solution_identity=value['solution_identity'],
            source_revision=value['source_revision'],
            source_sha256=dict(value['source_sha256']),
            runtime_source_id=source.scene_source.source_id,
            runtime_source_sha256=source_digest,
            working_tree_scope=tree,
            repo_dirty=actual_dirty,
            resolved_config=resolved_config,
        )
        return compiled, env
    except BaseException:
        env.close()
        raise


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
    from task_env.artifacts import (PoseWorld, RequiredCapabilitySet, SemanticDefinition, Timebase,
        ExecutionSpec, admit_capabilities)
    from task_env.artifacts.contracts import CapabilityAdmissionError
    from task_env.artifacts.execution import ResetSample
    from task_env.assembly.panda_box import (PANDA_BOX_CAPABILITIES, PandaBoxDeclaration,
        compile_panda_box_artifact, compile_panda_box_source)
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv
    from task_env.tasks.pick_cube.solution import PickCubeReadinessConfig,PickCubeReadinessSolution
    from task_env.tasks.reference_env import ReferenceTaskBinding
    from task_env.objects.pick_cube import CUBE_HALF_SIZE,CUBE_CONTACT_MARGIN
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
    missing=set(PANDA_BOX_CAPABILITIES)-set(spec.required_capabilities)
    if missing:reject('template_capabilities','required_capabilities',spec.required_capabilities,sorted(PANDA_BOX_CAPABILITIES))
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
    position=(*obj['initial_pos_xy'],scene['table_top_z']+CUBE_HALF_SIZE+CUBE_CONTACT_MARGIN)
    semantics=SemanticDefinition(
        'semantics-v0', 'harness_pick_lift_v0', ('cube-v1', 'panda-v1/ee'),
        ('panda-v1/finger_joint1', 'panda-v1/finger_joint2'), {
            'rest_height': scene['table_top_z']+CUBE_HALF_SIZE,
            'lift_height': spec.success_config['lift_height_m'],
            'reach_distance': spec.success_config['reach_distance_m'],
            'gripper_closed_opening': spec.success_config['gripper_closed_opening_m'],
        }, 'cube_lifted_v1')
    declaration=PandaBoxDeclaration(
        task_id=spec.task_id, artifact_id=f'{spec.task_id}/compiler-{COMPILER_VERSION}/spec-{spec_hash}',
        version='ver_001', object_id='cube-v1', success_definition='cube_lifted_v1',
        table_half_size=tuple(scene['table_half_size']), table_top_z=scene['table_top_z'],
        table_center_xy=tuple(scene['table_center_xy']), source_box_position=position,
        source_box_quaternion_wxyz=(1.,0.,0.,0.), reset_center_xy=tuple(obj['initial_pos_xy']),
        reset_half_extent_m=obj['reset_half_extent_m'], semantics=semantics,
        timebase=Timebase(.002,5,.01), cast_reset_center_float32=False, include_table_center=True,
        object_asset_reference=(f"external-mock/{external['uid']}/{external['sha256']}"
                                if external is not None else 'cube-v1/task-local'),
        capabilities=tuple(spec.required_capabilities),
    )
    artifact=compile_panda_box_artifact(declaration)
    initial=artifact.initialization
    dims=initial.randomization
    default_config=PickCubeReferenceEnv.selected_default_config()
    config=replace(default_config,task=replace(default_config.task,task_uid=spec.task_id))
    source=compile_panda_box_source(declaration,artifact,config)

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
        solution_identity=PickCubeReadinessSolution.identity_for_config(readiness)
        source_ids={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
            for name in ('harness_compiler.py','harness_spec_schema.py')}
        for name in ('task_env/tasks/pick_cube/task.py','task_env/tasks/pick_cube/solution.py',
                     'task_env/assembly/panda_box.py','task_env/assembly/compiler.py',
                     'task_env/environment/task_source.py','task_env/controllers/canonical/production.py'):
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
            controller=controller, solution=None, solution_identity=solution_identity,
            solution_factory=lambda:PickCubeReadinessSolution(config=readiness))

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
