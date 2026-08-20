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
