"""Authority and oracle immutability checks, no native construction."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import yaml
from ....runtime.sessions.provenance import provider_build_identity
from .fixtures import specification

BASELINE = '4db06e6f740a70b51cbf2eec87771321ba02d864'
GEOPHYS = 'c665ce5028a12bb4d2afe49f05e015fa9b684a39'


def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()


def identities():
    path = Path('workspace/qualification/phase1/p1_3_conformance/phase_decision.yaml')
    decision = yaml.safe_load(path.read_text())
    link = git('ls-tree','HEAD','GeoPhys').split()[2]
    versions = {p:provider_build_identity(p) for p in ('geophys','mujoco')}
    if (decision.get('decision') != 'approve' or decision.get('judge',{}).get('type') != 'human'
        or decision.get('implementation_commit',{}).get('geochora') != BASELINE
        or decision.get('provider_baseline') != {'geophys':GEOPHYS,'mujoco':'3.8.1'}
        or link != GEOPHYS or git('-C','GeoPhys','rev-parse','HEAD') != GEOPHYS
        or git('-C','GeoPhys','status','--porcelain')
        or versions['geophys']['repository_revision'] != GEOPHYS or versions['geophys']['dirty_build_sha256']
        or versions['mujoco']['package_version'] != '3.8.1'
        or subprocess.run(['git','merge-base','--is-ancestor',BASELINE,'HEAD']).returncode):
        raise ValueError('approved P1.3 provenance mismatch')
    return {'geochora_head':git('rev-parse','HEAD'),'geophys_gitlink':link,'geophys_checkout_head':git('-C','GeoPhys','rev-parse','HEAD'),
        'providers':versions,'phase_decision_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'public_main':git('rev-parse','public/main'),
        'public_main_contains_approved':subprocess.run(['git','merge-base','--is-ancestor',BASELINE,'public/main']).returncode==0}


def prepare(root):
    root = Path(root)
    path = root/'camera_oracle.yaml'
    if path.exists() or (root/'camera_oracle_lock.json').exists():
        raise ValueError('Evidence collision: oracle exists')
    identity = identities()
    spec = specification()
    path.write_text(yaml.safe_dump(spec,sort_keys=False))
    lock = {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'recipe_sha256':spec['recipe_sha256'],
            'timestamp':datetime.now(timezone.utc).isoformat(),'provenance':identity}
    (root/'camera_oracle_lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    return lock


def verify(path):
    path = Path(path)
    lock = json.loads((path.parent/'camera_oracle_lock.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != lock['sha256']:
        raise ValueError('camera oracle lock mismatch')
    spec = yaml.safe_load(path.read_text())
    # JSON-normalize tuples so implementation/source changes also fail closed.
    if spec != json.loads(json.dumps(specification())):
        raise ValueError('camera fixture/convention differs from locked oracle')
    return spec,lock
