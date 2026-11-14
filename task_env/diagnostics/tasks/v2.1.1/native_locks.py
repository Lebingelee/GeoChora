"""Acquire a plan's distinct native locks without locking an inode twice."""
import fcntl
import os
from pathlib import Path
import stat

CANONICAL_LOCK = Path(__file__).resolve().parents[4] / 'workspace/locks/shared_native_execution.lock'


def acquire_plan_locks(paths, handles):
    paths = list(paths)
    if not any(os.path.abspath(path) == str(CANONICAL_LOCK) for path in paths):
        raise ValueError('current native plans must include the canonical shared lock')
    identities = set()
    observed = []
    for path in paths:
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        handle = os.fdopen(fd, 'r+')
        try:
            info = os.fstat(handle.fileno())
            current = os.stat(path, follow_symlinks=False)
            if not (stat.S_ISREG(info.st_mode) and stat.S_ISREG(current.st_mode)
                    and (info.st_dev, info.st_ino) == (current.st_dev, current.st_ino)):
                raise RuntimeError('native lock path changed or is not a regular file')
            identity = (info.st_dev, info.st_ino)
            observed.append((path, identity))
            if identity in identities:
                handle.close()
                continue
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            current = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) or identity != (current.st_dev, current.st_ino):
                raise RuntimeError('native lock path changed while acquiring lock')
            handles.append(handle)
            identities.add(identity)
        except BaseException:
            handle.close()
            raise
    for path, identity in observed:
        current = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(current.st_mode) or identity != (current.st_dev, current.st_ino):
            raise RuntimeError('native lock path changed during plan acquisition')
