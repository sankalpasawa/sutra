"""Provider configuration. Data, not code -- one record per provider per environment.

Local mode is issued neither a client secret nor a private key, so there is
nothing here for a leak to find. That is a property of ADR-034, not an oversight:

  * the device flow needs no client_secret            (verified fact F3)
  * device-flow refresh needs no client_secret        (verified fact F4)
  * installation tokens need the app's RSA private key, which can never ship
    in a desktop bundle, so local mode does not use them at all (F6)

The client id is public by design -- it appears in every authorization request
a user's browser makes -- so it is safe to check in as a development default.
"""
import os
from dataclasses import dataclass
from typing import Optional

#: Sutra Dev GitHub App, owned by tchandrakar. Public value.
DEV_CLIENT_ID = "Iv23li4V24WX8yjaWoby"

#: Sutra Slack app. Public value -- it appears in every authorization URL a
#: user's browser visits.
SLACK_DEV_CLIENT_ID = "11873373906406.11873418567958"

SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
SLACK_ACCESS_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
SLACK_API_BASE = "https://slack.com/api"

#: Fixed, because Slack matches redirect URLs EXACTLY -- an ephemeral port the
#: way Google's desktop client type permits is not available here. A fixed port
#: is squattable; see design/06 threat T-21.
SLACK_REDIRECT_PORT = 8765
SLACK_REDIRECT_PATH = "/slack/callback"

GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_VERIFICATION_URL = "https://github.com/login/device"
GITHUB_API_BASE = "https://api.github.com"

#: Pinned. An unpinned client inherits GitHub's behaviour changes in production
#: with no deploy of ours to correlate against.
GITHUB_API_VERSION = "2022-11-28"

DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
REFRESH_GRANT_TYPE = "refresh_token"


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "github"
    client_id: str = DEV_CLIENT_ID
    api_base: str = GITHUB_API_BASE
    device_code_url: str = GITHUB_DEVICE_CODE_URL
    access_token_url: str = GITHUB_ACCESS_TOKEN_URL
    verification_url: str = GITHUB_VERIFICATION_URL
    user_agent: str = "Sutra-Connector/0.1"
    #: Present only in a hosted deployment. Local mode must never populate it.
    client_secret: Optional[str] = None

    @classmethod
    def from_env(cls, env=None):
        env = env if env is not None else os.environ
        return cls(
            client_id=env.get("SUTRA_GITHUB_CLIENT_ID") or DEV_CLIENT_ID,
            api_base=env.get("SUTRA_GITHUB_API_BASE") or GITHUB_API_BASE,
            client_secret=env.get("SUTRA_GITHUB_CLIENT_SECRET") or None,
        )

    def __post_init__(self):
        if not self.client_id:
            raise ValueError("client_id is required")


@dataclass(frozen=True)
class SlackConfig:
    """Slack differs from GitHub in three ways that matter, all of them worse:

      no device flow    -> a browser redirect is the only option
      no PKCE           -> `state` is the ONLY binding between our request and
                           the code that comes back
      secret required   -> and it must therefore live on the device

    Each is Slack's constraint, not a choice we made, and each is recorded
    rather than smoothed over.
    """
    provider: str = "slack"
    client_id: str = SLACK_DEV_CLIENT_ID
    api_base: str = SLACK_API_BASE
    authorize_url: str = SLACK_AUTHORIZE_URL
    access_token_url: str = SLACK_ACCESS_TOKEN_URL
    redirect_port: int = SLACK_REDIRECT_PORT
    redirect_path: str = SLACK_REDIRECT_PATH
    user_agent: str = "Sutra-Connector/0.1"
    #: One authorization yields two tokens with different reach and different
    #: attribution, so they live in separate slots.
    credential_slots: tuple = ("user",)
    #: Read from ~/.sutra/provider-secrets.env, never from the repo.
    client_secret: Optional[str] = None

    @property
    def redirect_uri(self) -> str:
        return "http://localhost:%d%s" % (self.redirect_port, self.redirect_path)

    @classmethod
    def from_env(cls, env=None):
        env = env if env is not None else os.environ
        return cls(
            client_id=env.get("SUTRA_SLACK_CLIENT_ID") or SLACK_DEV_CLIENT_ID,
            client_secret=(env.get("SUTRA_SLACK_CLIENT_SECRET")
                           or _read_secret_file(env).get("SUTRA_SLACK_CLIENT_SECRET")),
        )


def _read_secret_file(env=None):
    """~/.sutra/provider-secrets.env, mode 0600.

    A file rather than the repo, and a file rather than a shell profile: an
    exported variable is visible in the environment of every process the user
    launches, which is a wider audience than this needs.
    """
    env = env if env is not None else os.environ
    path = env.get("SUTRA_SECRETS_FILE") or os.path.expanduser("~/.sutra/provider-secrets.env")
    out = {}
    if not os.path.exists(path):
        return out
    mode = os.stat(path).st_mode & 0o777
    if mode & 0o077:
        # Refuse to read a secrets file other users can read. Failing loudly
        # beats silently loading a credential from a world-readable file.
        raise PermissionError(
            "%s is mode %o; secrets must not be group- or world-readable. "
            "Run: chmod 600 %s" % (path, mode, path))
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out
