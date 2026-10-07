"""Reusable isolated additive NutAssembly expert and symmetric replay worker."""
import argparse
import json
from pathlib import Path
from .nutassembly.worker import expert, d0, replay


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--profile',choices=['NA-TB500','NA-TB100','NA-TB50'],required=True)
    parser.add_argument('--route',choices=['expert','D0','D1','D2'],required=True)
    parser.add_argument('--provider',choices=['geophys','mujoco'],default='geophys')
    parser.add_argument('--source-provider',choices=['geophys','mujoco'],default='geophys')
    args=parser.parse_args()
    if args.route=='expert':report=expert(args.root,args.profile,args.provider);passed=report['success']
    elif args.route=='D0':report=d0(args.root,args.profile,args.source_provider);passed=report['pass']
    else:report=replay(args.root,args.profile,args.source_provider,args.provider,args.route);passed=report['execution_valid'] and report['task_valid']
    print(json.dumps(report),flush=True)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
