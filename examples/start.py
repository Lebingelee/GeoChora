"""Route a single-environment example using explicit existing installations."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = {'empty-v1', 'pendulum-v1', 'two-wheel-balance-v1'}
SELECTED = {'pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1'}


def _file(parser, value, label, *, executable=False):
    path = Path(value).expanduser().resolve()
    if not path.is_file() or (executable and not os.access(path, os.X_OK)):
        parser.error(f'{label} must be an existing' + (' executable' if executable else ' file') + f': {path}')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True, help='Core Python interpreter')
    parser.add_argument('--core', type=Path, default=ROOT, help='this Core checkout')
    parser.add_argument('--geophys-src', type=Path, required=True, help='GeoPhys src directory')
    parser.add_argument('--uid', choices=sorted(CLASSIC | SELECTED), required=True)
    parser.add_argument('--provider', choices=('geophys', 'mujoco', 'isaacsim'), required=True)
    parser.add_argument('--backend', choices=('cpu', 'cuda'), required=True)
    parser.add_argument('--renderer', choices=('none', 'rasterizer'), required=True)
    parser.add_argument('--seed', type=int)
    parser.add_argument('--horizon', type=int)
    parser.add_argument('--isaac-python', type=Path)
    parser.add_argument('--source-delivery-manifest', type=Path)
    args = parser.parse_args(argv)
    core = args.core.expanduser().resolve()
    if core != ROOT:
        parser.error(f'--core must identify the checkout containing this script: {ROOT}')
    python = _file(parser, args.python, '--python', executable=True)
    source = args.geophys_src.expanduser().resolve()
    _file(parser, source / 'scene' / '__init__.py', '--geophys-src/scene/__init__.py')
    if args.uid in CLASSIC and (args.provider, args.backend) != ('geophys', 'cpu'):
        parser.error('classic scalar examples require --provider geophys --backend cpu')
    if args.uid in SELECTED and (args.provider, args.backend) not in (
            ('geophys', 'cpu'), ('mujoco', 'cpu'), ('isaacsim', 'cuda')):
        parser.error('selected examples admit geophys/cpu, mujoco/cpu or the bounded pick-cube isaacsim/cuda route')
    if args.provider == 'isaacsim' and args.uid != 'pick-cube-p16-reference-v1':
        parser.error('the existing Isaac example is restricted to selected PickCube')
    if args.renderer != 'none' and (args.uid, args.provider, args.backend) != ('pendulum-v1', 'geophys', 'cpu'):
        parser.error('rasterizer example is restricted to scalar Pendulum / GeoPhys / CPU')
    if args.provider == 'isaacsim':
        if args.isaac_python is None or args.source_delivery_manifest is None:
            parser.error('Isaac requires --isaac-python and --source-delivery-manifest')
        isaac_python = _file(parser, args.isaac_python, '--isaac-python', executable=True)
        manifest = _file(parser, args.source_delivery_manifest, '--source-delivery-manifest')
    elif args.isaac_python is not None or args.source_delivery_manifest is not None:
        parser.error('Isaac interpreter and delivery manifest require --provider isaacsim')
    if args.horizon is not None and not 1 <= args.horizon <= 6000:
        parser.error('--horizon must be in [1, 6000]')
    if args.provider == 'isaacsim' and (args.horizon not in (None, 1000) or args.seed not in (None, 31, 32, 33)):
        parser.error('the existing Isaac harness requires horizon 1000 and seed 31, 32 or 33')
    if args.uid in CLASSIC and args.horizon is not None:
        parser.error('classic example runs exactly one transition and does not accept --horizon')
    if args.renderer == 'rasterizer':
        command = [str(python), str(ROOT / 'examples/rendering/pendulum_single_rgb.py')]
    elif args.uid in CLASSIC:
        command = [str(python), str(ROOT / 'examples/tasks/scalar_step.py'), '--uid', args.uid]
    elif args.uid == 'pick-cube-p16-reference-v1':
        command = [str(python), str(ROOT / 'examples/tasks/pick_cube.py'), '--provider', args.provider]
    else:
        command = [str(python), str(ROOT / 'examples/tasks/nut_assembly.py'), '--provider', args.provider]
    if args.seed is not None:
        command += ['--seed', str(args.seed)]
    if args.horizon is not None:
        command += ['--horizon', str(args.horizon)]
    if args.provider == 'isaacsim':
        command += ['--execution', 'harness', '--isaac-python', str(isaac_python),
                    '--source-delivery-manifest', str(manifest)]
    environment = os.environ.copy()
    environment['GEOCHORA_GEOPHYS_SRC'] = str(source)
    environment['GEOCHORA_CORE_PYTHON'] = str(python)
    environment['PYTHONPATH'] = os.pathsep.join((str(ROOT), str(source)))
    return subprocess.run(command, cwd=Path.cwd(), env=environment, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
