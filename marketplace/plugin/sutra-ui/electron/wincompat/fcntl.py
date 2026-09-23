"""Windows shim for POSIX fcntl (Sutra beta). Locking is a NO-OP.

Real per-store locking on Windows (msvcrt.locking / portalocker) is Stage B;
for a single-user desktop beta a no-op lets the backend import and run.
"""
LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8
F_GETFD = 1
F_SETFD = 2
F_GETFL = 3
F_SETFL = 4
FD_CLOEXEC = 1


def flock(fd, operation):  # no-op on Windows (beta)
    return None


def lockf(fd, operation, length=0, start=0, whence=0):  # no-op
    return None


def fcntl(fd, op, arg=0):
    return 0


def ioctl(fd, op, arg=0, mutate_flag=True):
    return 0
