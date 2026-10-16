"""Provider-free identity regression on real branches and detached execution."""
import subprocess
from task_env.diagnostics.phase1.integration.provenance import execution_identity


def test_execution_identity_tracks_commit_branch_dirty_paths_and_detachment(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    git('init', '-b', 'review-source')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'user.name', 'Provenance Test')
    (tmp_path/'source').write_text('first')
    git('add', 'source'); git('commit', '-m', 'first')
    first = git('rev-parse', 'HEAD')
    monkeypatch.chdir(tmp_path.parent)
    assert execution_identity(tmp_path) == {
        'head': first, 'branch': 'review-source', 'dirty_status': ['## review-source']}
    (tmp_path/'source').write_text('second')
    assert any(' M source' in p for p in execution_identity(tmp_path)['dirty_status'])
    git('commit', '-am', 'second')
    assert execution_identity(tmp_path)['head'] != first
    git('checkout', '--detach', first)
    detached = execution_identity(tmp_path)
    assert detached['head'] == first and detached['branch'] is None
