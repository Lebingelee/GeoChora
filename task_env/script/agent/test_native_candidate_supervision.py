"""Native supervision failure must override a worker's optimistic row."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_candidate_runner as runner


@pytest.mark.parametrize('status,returncode,retired', [
    ('TIMEOUT', -15, True),
    ('RESOURCE_VIOLATION', -9, True),
    ('WORKER_FAILED', 1, True),
    ('COMPLETED', 0, False),
])
def test_supervision_failure_invalidates_written_solved_row(tmp_path, status, returncode, retired):
    (tmp_path / 'row.json').write_text(json.dumps({
        'seed': 0, 'horizon': 5, 'classification': 'solved',
        'construction_succeeded': True, 'artifact_hash': 'expected',
    }))
    receipt = {'status': status, 'returncode': returncode,
               'process_group_retired': retired, 'reason': 'injected failure'}
    with patch.object(runner, 'launch_worker', return_value=receipt):
        row = runner.run_seed_native(spec=None, catalog={}, provider='isaacsim', seed=0,
                                     horizon=5, output_dir=tmp_path, expected_artifact_hash='expected')
    assert row['classification'] == 'invalid'
    assert row['error_type'] == 'NativeWorkerFailed'
    assert row['worker_row']['classification'] == 'solved'
