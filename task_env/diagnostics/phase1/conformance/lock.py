"""Oracle preparation and immutability verification; never executes a provider."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import yaml

from ....runtime.sessions.provenance import provider_build_identity
from .fixtures import fixtures

BASELINE = '22b0a229a741a7e7f11663cd5a0635e3ed6053c4'
GEOPHYS_BASELINE = 'c665ce5028a12bb4d2afe49f05e015fa9b684a39'


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def identities():
    decision = Path('workspace/qualification/phase1/p1_2_runtime/phase_decision.yaml')
    authority = yaml.safe_load(decision.read_text())
    link = git('ls-tree','HEAD','GeoPhys').split()[2]
    if (authority.get('decision') != 'approve' or authority.get('judge',{}).get('type') != 'human'
        or authority.get('implementation_commit',{}).get('geochora') != BASELINE
        or authority.get('provider_baseline',{}).get('geophys') != GEOPHYS_BASELINE
        or link != GEOPHYS_BASELINE or git('-C','GeoPhys','rev-parse','HEAD') != link
        or git('-C','GeoPhys','status','--porcelain')
        or subprocess.run(['git','merge-base','--is-ancestor',BASELINE,'HEAD']).returncode != 0):
        raise ValueError('Human-approved P1.2 provenance mismatch')
    providers = {p:provider_build_identity(p) for p in ('geophys','mujoco')}
    if providers['geophys']['repository_revision'] != link or providers['geophys']['dirty_build_sha256']:
        raise ValueError('running GeoPhys build does not match approved checkout')
    return {'geochora_head':git('rev-parse','HEAD'),'geophys_gitlink':link,
            'geophys_checkout_head':git('-C','GeoPhys','rev-parse','HEAD'),
            'providers':providers,'human_decision_sha256':hashlib.sha256(decision.read_bytes()).hexdigest(),
            'public_main':git('rev-parse','refs/remotes/public/main'),
            'public_main_contains_approved':subprocess.run(['git','merge-base','--is-ancestor',BASELINE,'refs/remotes/public/main']).returncode==0}


def prepare(root):
    root = Path(root)
    if (root/'oracle_lock.json').exists() or (root/'oracle_spec.yaml').exists():
        raise ValueError('oracle already exists; will not overwrite')
    identity = identities()
    spec = {'schema_version':'p1_3-oracle-v0','probes':fixtures(),'pairwise_is_diagnostic_only':True}
    oracle = root/'oracle_spec.yaml'
    oracle.write_text(yaml.safe_dump(spec,sort_keys=False,allow_unicode=True))
    lock = {'oracle_spec_sha256':hashlib.sha256(oracle.read_bytes()).hexdigest(),
            'source_fixture_hashes':{n:v['fixture_hash'] for n,v in spec['probes'].items()},
            'starting_geochora_commit':BASELINE,'provenance':identity,
            'timestamp':datetime.now(timezone.utc).isoformat()}
    (root/'oracle_lock.json').write_text(json.dumps(lock,indent=2,sort_keys=True)+'\n')
    return lock


def verify(oracle):
    oracle=Path(oracle)
    lock=json.loads((oracle.parent/'oracle_lock.json').read_text())
    if hashlib.sha256(oracle.read_bytes()).hexdigest()!=lock['oracle_spec_sha256']:
        raise ValueError('oracle lock mismatch; no provider execution allowed')
    spec=yaml.safe_load(oracle.read_text())
    if spec['probes']!=fixtures():
        raise ValueError('fixture implementation differs from locked oracle/source')
    return spec,lock
