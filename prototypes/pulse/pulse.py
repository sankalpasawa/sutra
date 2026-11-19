"""Sutra Pulse entry point. Usage: python3 pulse.py {check,fetch,find,purge} --help"""
import sys

if sys.version_info < (3, 11):
    sys.exit("Pulse needs Python 3.11 or newer (this is %d.%d). Try: python3.12 %s" % (sys.version_info[0], sys.version_info[1], " ".join(sys.argv)))

import cli

if __name__ == "__main__":
    sys.exit(cli.main(sys.argv[1:]))
