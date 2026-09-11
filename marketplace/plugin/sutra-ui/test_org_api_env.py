"""test_org_api_env.py -- importing the app never rewrites the process environment.

RCA 2026-09-11 fix row 4: org_api used to write the resolved registry path back
into os.environ["SUTRA_NATIVE_HOME"] at import. The first importer therefore
decided the registry for every module imported later in the same process. The
contract now: org_api computes and exposes registry_root(); the environment is
left alone; MCP children still receive the root explicitly from app.py.

The check runs in a child interpreter with SUTRA_NATIVE_HOME and
PYTEST_CURRENT_TEST removed and HOME pointed at a throwaway dir, so it proves
the real runtime default path (not conftest's temp home) is what stays
un-exported, without touching the operator's registry.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = r"""
import json, os, sys
sys.path.insert(0, %r)
import org_api
after = os.environ.get("SUTRA_NATIVE_HOME")
root = org_api.registry_root()
import app
cfg = json.loads(app._sutra_mcp_config() or "{}")
acp = app._sutra_acp_mcp_servers()
print(json.dumps({"after": after, "root": root,
                  "mcp": (cfg.get("mcpServers") or {}).get("sutra", {}).get("env", {}),
                  "acp": (acp[0]["env"] if acp else [])}))
"""


class TestOrgApiEnv(unittest.TestCase):

    def test_import_leaves_the_environment_alone_and_children_get_an_explicit_root(self):
        fake_home = tempfile.mkdtemp(prefix="org-api-env-home-")
        env = {k: v for k, v in os.environ.items()
               if k not in ("SUTRA_NATIVE_HOME", "PYTEST_CURRENT_TEST", "PYTEST_ADDOPTS")}
        env["HOME"] = fake_home
        env["SEO_AGENT_NO_CLI"] = "1"
        proc = subprocess.run([sys.executable, "-c", PROBE % str(HERE)], cwd=str(HERE),
                              env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertIsNone(out["after"], "org_api still exports SUTRA_NATIVE_HOME into os.environ")
        expected = os.path.join(fake_home, ".sutra-native", "user-kit")
        self.assertEqual(os.path.realpath(out["root"]), os.path.realpath(expected))
        self.assertEqual(out["mcp"].get("SUTRA_NATIVE_HOME"), out["root"],
                         "Claude-shaped MCP config must carry the explicit root")
        acp_env = {e["name"]: e["value"] for e in out["acp"]}
        self.assertEqual(acp_env.get("SUTRA_NATIVE_HOME"), out["root"],
                         "ACP-shaped MCP config must carry the explicit root")

    def test_registry_root_is_the_engine_binding(self):
        sys.path.insert(0, str(HERE))
        import org_api  # noqa: E402  (conftest already bound a temp home)
        self.assertEqual(org_api.registry_root(), org_api.E.HOME)
        self.assertTrue(org_api.registry_root())


if __name__ == "__main__":
    unittest.main()
