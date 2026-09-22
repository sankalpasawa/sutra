"""Windows shim for POSIX termios (Sutra beta). Terminal features are Stage B."""
TCSANOW = 0
TCSADRAIN = 1
TCSAFLUSH = 2


class error(Exception):
    pass


def tcgetattr(fd):
    return [0, 0, 0, 0, 0, 0, []]


def tcsetattr(fd, when, attributes):
    return None
