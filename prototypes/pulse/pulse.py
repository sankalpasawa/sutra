"""Sutra Pulse entry point. Usage: python3 pulse.py {check,fetch,find,purge} --help"""
import sys

import cli

if __name__ == "__main__":
    sys.exit(cli.main(sys.argv[1:]))
