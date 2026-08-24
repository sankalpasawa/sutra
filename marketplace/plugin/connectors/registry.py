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
    #: RETIRED: Sutra no longer mints or uses this provider's credentials, but
    #: it can still DESTROY one. The spec stays registered on purpose -- pulling
    #: it out of _SPECS makes every /api/connectors/{provider}/... route 404,
    #: including DELETE, which would strand an existing connector's tokens in
    #: the Keychain with no way to remove them. Verified by execution, not
    #: assumed. `retired_note` is rendered on the tile in place of Connect.
    retired: bool = False
    retired_note: Optional[str] = None


_RETIRED_MSG = ("{p} is retired in Sutra: it is observed through Claude, not "
                "authorised here. An existing connection can only be disconnected.")


class RetiredStrategy:
    """A strategy that can be BUILT but not USED.

    The first attempt raised from the builder instead, which 500s the entire
    /api/connectors/providers endpoint -- build_service() constructs the
    strategy eagerly (see build_service below), so a provider that cannot build
    takes down the tile list for every provider, GitHub included. Found by
    running it, not by reading it.

    So the object exists and only its ACTIONS refuse. list_connectors() and
    disconnect() never touch a strategy, which is exactly why they keep working
    -- and disconnect is the one capability a retired provider must retain.
    """

    #: Read by ConnectorService.credential_for as the choke point. It is an
    #: ATTRIBUTE, not a method that raises, because the caller must be able to
    #: ask "is this retired?" without triggering the refusal.
    retired = True

    def __init__(self, provider: str):
        self.provider = provider

    def _refuse(self, *_a, **_k):
        raise RuntimeError(_RETIRED_MSG.format(p=self.provider.title()))

    begin = poll = identity = refresh = _refuse

    def can_resume(self, handle):
        """Not a refusal: this is a QUESTION, and the honest answer is no.
        Raising here would turn a resumable-transaction check into a 500."""
        return False

    def cancel(self, handle):
        return None

    def close_all(self):
        return None


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
    """RETIRED in 2.220.0 (founder direction 2026-08-24: "let's not use app").

    Slack is now observed through Claude like Gmail and Drive -- see ADR-035 and
    mediated_connectors.py. Sutra no longer runs a Slack OAuth app and holds no
    Slack token.

    The spec is NOT deleted. An operator upgrading with an ACTIVE Slack
    connection still has two live tokens in the Keychain, and removing "slack"
    from _SPECS makes every /api/connectors/slack/... route return 404 --
    including DELETE. That does not delete their tokens, it stops them from
    ever deleting their tokens. So the spec survives with exactly one remaining
    capability: destroy.

    build_strategy raises, so no NEW connection can be minted and no existing
    credential can be refreshed into a usable one. credential_slots is kept
    verbatim: disconnect erases the slots the spec declares, and dropping the
    "user" slot here would leave the user token behind on every machine that
    still has one.
    """
    from .config import SlackConfig
    from .slack.client import SlackClient

    def build_strategy(config, client):
        return RetiredStrategy("slack")

    return ProviderSpec(
        provider="slack",
        display_name="Slack",
        tagline="Now connected inside Claude, not in Sutra.",
        auth_mode="redirect",
        build_config=SlackConfig.from_env,
        build_client=SlackClient,
        build_strategy=build_strategy,
        # Verbatim from the un-retired spec. Disconnect erases the slots the
        # spec declares; dropping "user" would orphan the user token.
        credential_slots=("user",),
        needs_local_secret=False,       # nothing is minted, so nothing is needed
        retired=True,
        retired_note="Sutra no longer manages Slack. It is connected inside "
                     "Claude instead — see the Claude connections below. Any "
                     "Slack connection still stored here can be disconnected, "
                     "and nothing else.",
        caveat=None,
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
