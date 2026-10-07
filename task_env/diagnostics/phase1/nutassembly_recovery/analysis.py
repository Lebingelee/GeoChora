"""Provider-free summaries of immutable recovery traces; no physics execution."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def summarize(folder):
    folder = Path(folder)
    report = json.loads((folder / 'report.json').read_text())
    trace = json.loads((folder / 'trace.json').read_text())
    stages = {}
    for name in dict.fromkeys(row['stage'] for row in trace):
        rows = [row for row in trace if row['stage'] == name]
        end = rows[-1]
        relative = []
        for row in rows:
            poses = row['state']['pose_world']
            relative.append((np.asarray(poses['square-nut-v1']['position']) -
                             np.asarray(poses['panda-v1/ee']['position'])).tolist())
        stages[name] = {
            'ticks': len(rows),
            'end_time_s': end['state']['simulation_time'],
            'end_metrics': end['metrics'],
            'end_feedback': end['feedback'],
            'end_target_gripper': end['controller_target']['gripper'],
            'end_controller_memory': end['controller_memory'],
            'nut_minus_ee_world_start_m': relative[0],
            'nut_minus_ee_world_end_m': relative[-1],
            # World-vector change also contains rotation; not a rigid grasp gate.
            'relative_world_vector_change_m': float(np.linalg.norm(
                np.asarray(relative[-1]) - relative[0])),
        }
    return {
        'report': report,
        'valid_recorded_transitions': len(trace),
        'trace_sha256': hashlib.sha256((folder / 'trace.json').read_bytes()).hexdigest(),
        'stages': stages,
        'interpretation': 'grasped/lifted heuristics alone do not prove stable capture',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    root = Path(args.root)
    results = {}
    candidates = root / 'optimization/candidates'
    paths = list(candidates.glob('iteration*/tb*/*/report.json'))
    # The first archived prototype predates profile subdirectories.
    paths += list(candidates.glob('iteration*/*/report.json'))
    for path in sorted(paths):
        results[str(path.parent.relative_to(root))] = summarize(path.parent)
    output = root / 'optimization/trace_summary.json'
    output.write_text(json.dumps(results, indent=2, allow_nan=False) + '\n')
    print(output)


if __name__ == '__main__':
    main()
