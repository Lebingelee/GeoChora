"""Bounded P1.8 prerequisite/golden/D0 worker. No policy route or fallback."""
import argparse
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--route',choices=['collect','d0','D1','D2'],required=True)
    p.add_argument('--provider',choices=['geophys','mujoco'],default='geophys')
    p.add_argument('--seed',choices=[31,73],type=int,required=True)
    a=p.parse_args()
    from .multi_backend_replay.golden import collect,d0
    if a.route=='collect':result=collect(a.root,a.seed,a.provider)
    elif a.route=='d0':result=d0(a.root,a.seed)
    else:
        from .multi_backend_replay.replay import run
        result=run(a.root,a.route,a.provider,a.seed)
        result['pass']=result['execution_valid'] and result['task_valid']
    print(result)
    raise SystemExit(0 if result['pass'] else 1)


if __name__=='__main__':main()
