"""Flow preparation only: strict datasets, one CUDA update, CPU inference."""
from pathlib import Path
import argparse
from .flow_preparation.prepare import run,write


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('workspace/qualification/phase1/p1_6_flow_preparation'))
    args=parser.parse_args()
    result=run(args.root)
    write(args.root/'preparation_report.json',result)
    print(result['status'])


if __name__=='__main__':main()
