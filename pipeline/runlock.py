"""One pipeline run at a time.

run_weekly.py and run_all.py both write data/interim/ and data/public/; two runs at
once (a timer catching up while someone starts a run by hand) would corrupt them.
The lock is an OS file lock, so it is released automatically if the process dies.
"""
import os
import sys

import config

_handle = None   # kept open for the life of the process


def acquire() -> bool:
    """True if this process now holds the lock (or already did); False if another run holds it."""
    global _handle
    if _handle is not None or os.environ.get("ATLAS_RUN_LOCKED") == "1":   # parent run holds it
        return True
    config.RUN_LOCK.parent.mkdir(parents=True, exist_ok=True)
    f = open(config.RUN_LOCK, "a+")
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _handle = f
    os.environ["ATLAS_RUN_LOCKED"] = "1"   # child processes (run_all.py under run_weekly.py) share it
    return True
