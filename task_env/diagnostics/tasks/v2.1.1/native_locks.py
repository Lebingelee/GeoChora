"""Acquire a plan's distinct native locks without locking an inode twice."""
import fcntl
import os


def acquire_plan_locks(paths, handles):
    identities = set()
    for path in paths:
        handle = open(path, 'r+')
        try:
            info = os.fstat(handle.fileno())
            identity = (info.st_dev, info.st_ino)
            if identity in identities:
                handle.close()
                continue
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            handles.append(handle)
            identities.add(identity)
        except BaseException:
            handle.close()
            raise
