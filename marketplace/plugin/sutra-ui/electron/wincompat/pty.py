"""Windows shim for POSIX pty (Sutra beta). The terminal pane is Stage B."""
def openpty():
    raise OSError("pty is not available on Windows (Sutra beta)")


def fork():
    raise OSError("pty.fork is not available on Windows (Sutra beta)")


def spawn(argv, master_read=None, stdin_read=None):
    raise OSError("pty.spawn is not available on Windows (Sutra beta)")
