"""Frozen success-conditioned candidate streams, independent of spatial statistics."""
POOLS = {'train': list(range(1100, 1150)), 'validation': list(range(1200, 1220))}
INITIAL = {'train': list(range(1000, 1080)), 'validation': list(range(1080, 1100))}
TARGETS = {'train': 80, 'validation': 20}


def successful(row):
    return all(row.get(key) is True for key in ('pass', 'endpoint', 'success', 'roundtrip'))


def select(attempts):
    """Validate ascending stream prefixes and stop-at-target, then select successes."""
    if len({r['seed'] for r in attempts}) != len(attempts):
        raise ValueError('duplicate attempted seed')
    result = {}
    for role in TARGETS:
        rows = [r for r in attempts if r['role'] == role]
        seeds = [r['seed'] for r in rows]
        initial = INITIAL[role]
        if seeds[:len(initial)] != initial:
            raise ValueError('original attempted split changed')
        extra = seeds[len(initial):]
        if extra != POOLS[role][:len(extra)]:
            raise ValueError('supplement must be ascending frozen candidate prefix')
        chosen = [r for r in rows[:len(initial)] if successful(r)]
        for row in rows[len(initial):]:
            if len(chosen) >= TARGETS[role]:
                raise ValueError('collection continued after success target')
            if successful(row):
                chosen.append(row)
        if len(chosen) > TARGETS[role]:
            raise ValueError('success target exceeded')
        result[role] = chosen
    if any(r['role'] not in TARGETS for r in attempts):
        raise ValueError('unknown sample role')
    return result


def authorized(selected):
    return all(len(selected[role]) == count and all(successful(r) for r in selected[role])
               for role, count in TARGETS.items())


def validate_manifest(manifest):
    chosen = select(manifest['attempts'])
    for role in TARGETS:
        rows = [r for r in manifest['trajectories'] if r['role'] == role]
        if rows != chosen[role] or manifest['selected_' + role + '_seeds'] != [r['seed'] for r in rows]:
            raise ValueError('learner corpus is not frozen first-success selection')
        for label, subset in (('attempted', [r for r in manifest['attempts'] if r['role'] == role]),
                              ('successful', [r for r in manifest['attempts'] if r['role'] == role and successful(r)]),
                              ('failed', [r for r in manifest['attempts'] if r['role'] == role and not successful(r)])):
            if manifest[label + '_' + role + '_seeds'] != [r['seed'] for r in subset]:
                raise ValueError('attempt classification mismatch')
        if manifest['selected_' + role + '_trajectory_hashes'] != [r['logical_hash'] for r in rows]:
            raise ValueError('selected trajectory identity mismatch')
        if manifest['target_' + role + '_success_count'] != TARGETS[role]:
            raise ValueError('success count target changed')
    if manifest['full_training_authorized'] != authorized(chosen) or not authorized(chosen):
        raise ValueError('expert_dataset_feasibility: bounded stream insufficient')
    return chosen
