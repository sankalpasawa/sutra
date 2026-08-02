#!/usr/bin/env python3
# thin wrapper — canonical generator lives in the plugin (lib/domains_page.py)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "marketplace", "plugin", "lib"))
from domains_page import build
print(build(os.path.join(os.path.dirname(os.path.abspath(__file__)), "domains.html"), label="Departments"))
