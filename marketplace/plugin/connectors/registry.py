"""Provider registry.

One place that knows which providers exist and how to build a service for each.
Everything above this is provider-agnostic; everything provider-specific is
behind a ProviderSpec. Adding Gmail is adding a row here plus a package.

The display fields live here too, because the panel must be able to render a
tile for a provider that is NOT connected -- and therefore has no connector row
to read a name or an icon from.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple


@dataclass(frozen=True)
class ProviderSpec:
    provider: str
    display_name: str
    #: One-line description shown on an unconnected tile.
    tagline: str
    #: How the user proves identity: "device" or "redirect". The tile explains
    #: the flow before the user starts it, because a device code and a browser
    #: redirect are very different experiences.
    auth_mode: str
    build_config: Callable
    build_client: Callable
    build_strategy: Callable
    #: Extra credential slots beyond the default. Disconnect erases all of them.
    credential_slots: Tuple[str, ...] = ()
    #: Set when the provider needs a secret on this machine. The tile says so,
    #: rather than failing at connect time with a confusing error.
    needs_local_secret: bool = False
    #: Honest note rendered on the tile. Not marketing.
    caveat: Optional[str] = None


def _github_spec():
    from .config import ProviderConfig
    from .github.client import GitHubClient
    from .oauth.strategies import DeviceFlowStrategy

    def build_strategy(config, client):
        return DeviceFlowStrategy(client, config)

    return ProviderSpec(
        provider="github",
        display_name="GitHub",
        tagline="Repositories, pull requests and issues.",
        auth_mode="device",
        build_config=ProviderConfig.from_env,
        build_client=GitHubClient,
        build_strategy=build_strategy,
        needs_local_secret=False,
        caveat=None,
    )


def _slack_spec():
    from .config import SlackConfig
    from .slack.client import SlackClient
    from .slack.strategy import SlackLoopbackStrategy

    def build_strategy(config, client):
        return SlackLoopbackStrategy(client, config)

    return ProviderSpec(
        provider="slack",
        display_name="Slack",
        tagline="Channels, messages and search.",
        auth_mode="redirect",
        build_config=SlackConfig.from_env,
        build_client=SlackClient,
        build_strategy=build_strategy,
        credential_slots=("user",),
        needs_local_secret=True,
        # Stated on the tile rather than discovered later. Slack offers no
        # device flow and no PKCE, so this connection is genuinely weaker than
        # GitHub's and the operator should know before starting.
        caveat="Uses a browser redirect to a local port. Slack offers no PKCE, "
               "so this is a weaker flow than GitHub's.",
    )


_SPECS: Dict[str, Callable[[], ProviderSpec]] = {
    "github": _github_spec,
    "slack": _slack_spec,
}


def provider_ids():
    return tuple(_SPECS)


def get_spec(provider: str) -> ProviderSpec:
    try:
        return _SPECS[provider]()
    except KeyError:
        raise ValueError("unknown provider: %r" % provider)


def build_service(provider: str, db, credential_store):
    """Assemble a ConnectorService for one provider."""
    from .service import ConnectorService
    spec = get_spec(provider)
    config = spec.build_config()
    client = spec.build_client(config)
    strategy = spec.build_strategy(config, client)
    return ConnectorService(db, credential_store, strategy, client, config)


def secret_available(spec: ProviderSpec) -> bool:
    """Can this provider actually complete a connection on this machine?

    Answering on the TILE means the operator learns a secret is missing before
    a browser opens, not from an error afterwards.
    """
    if not spec.needs_local_secret:
        return True
    try:
        return bool(getattr(spec.build_config(), "client_secret", None))
    except Exception:
        return False
