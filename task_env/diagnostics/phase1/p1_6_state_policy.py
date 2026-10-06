"""Reusable P1.6 isolated expert/replay/policy worker entry point."""
import argparse
from pathlib import Path
from .state_policy.spec import prepare,verify


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--oracle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepare',action='store_true');p.add_argument('--provider',choices=['geophys','mujoco']);p.add_argument('--seed',type=int)
    p.add_argument('--role',choices=['train','validation','regression']);p.add_argument('--route',choices=['collect','replay','evaluate','pure'],default='collect');p.add_argument('--input',type=Path)
    a=p.parse_args()
    if a.prepare:print(prepare(a.oracle.parent)[1]);return
    verify(a.oracle)
    if a.route=='pure':
        from .state_policy.pure import run
        result=run(a.output.parent)
    else:
        from .state_policy.worker import collect,replay,evaluate_policy
        if a.route=='collect':result=collect(a.provider,a.seed,a.role,a.oracle,a.output)
        elif a.route=='replay':result=replay(a.provider,a.oracle,a.input,a.output)
        else:result=evaluate_policy(a.provider,a.seed,a.oracle,a.input,a.output)
    print({k:v for k,v in result.items() if k in ('pass','first_boundary','success','T','holds','endpoint','seed','provider','max_cube_lift','steps')})
    raise SystemExit(0 if result['pass'] else 1)


if __name__=='__main__':main()
