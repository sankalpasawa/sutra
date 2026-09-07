"""urls.py — the two URL forms and the "is this even a page" filters.

The STORED url is minimally normalised (faithful to what the site published); the MATCH KEY is
aggressive (tracking-param blocklist, host without www, no trailing slash, https). Two fields,
never conflated: the key groups, the stored form is what the catalogue shows.
"""
import re
import urllib.parse as _up

# Tracking params dropped from the MATCH KEY only (blocklist — real params like WP's ?p= survive)
# A BLOCKLIST, never an allowlist: an allowlist would discard the query parameters some CMSs use
# for real permalinks. Each entry below identifies a campaign/affiliate/session tag that cannot
# change what page you land on. Measured 2026-07-19 on a competitor's site: without the affiliate
# (`fpr`) and Google/Bing ad (`hsa_*`, `_bta_*`) tags, one homepage entered the catalogue dozens of
# times over and 92% of that site's rows were duplicates.
TRACKING_PARAMS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                   "utm_id", "utm_source_platform", "utm_creative_format",
                   "gclid", "gclsrc", "gbraid", "wbraid", "dclid",          # Google Ads
                   "fbclid", "igshid", "ttclid", "twclid", "li_fat_id",     # social
                   "msclkid", "hsa_acc", "hsa_cam", "hsa_grp", "hsa_ad",    # Bing / Google ads
                   "hsa_src", "hsa_tgt", "hsa_kw", "hsa_mt", "hsa_net", "hsa_ver",
                   "mc_cid", "mc_eid", "_bta_c", "_bta_tid", "vero_id",     # email platforms
                   "fpr", "irclickid", "aff_id", "affiliate", "partner_id", # affiliate
                   "ref", "source", "srsltid", "gad_source", "campaignid", "adgroupid"]
_TRACKING = frozenset(TRACKING_PARAMS)

# Standard non-content / protocol files (not site PAGES): RFC 8615 well-known URIs + root machine files.
_NON_CONTENT_RE = re.compile(
    r"(/\.well-known/|/(robots\.txt|security\.txt|ads\.txt|humans\.txt|favicon\.ico|"
    r"manifest\.json|browserconfig\.xml|sitemap[\w-]*\.xml|sitemap[\w-]*\.xml\.gz)$)", re.I)

# A binary/static asset is never a page, on any platform. Extension-based, so it needs no
# knowledge of the CMS. (.html/.htm/.php/.asp are deliberately ABSENT — those ARE pages.)
_ASSET_EXT_RE = re.compile(
    r"\.(?:png|jpe?g|gif|webp|avif|svg|ico|bmp|tiff?|"           # images
    r"woff2?|ttf|otf|eot|"                                        # fonts
    r"css|js|mjs|cjs|map|"                                        # styling / scripts
    r"mp4|webm|mov|avi|wmv|mp3|wav|ogg|m4a|"                      # media
    r"zip|gz|tgz|tar|rar|7z|dmg|exe|pkg)$", re.I)                 # archives / installers

# A CMS's API surface and internal directories are MACHINERY, not pages. This is platform-shape
# awareness (the same kind the sitemap probe list already uses), never company knowledge:
# no domain, brand or slug appears here, and it holds for every site on these platforms.
# Measured 2026-07-19: 164 /wp-json/ endpoints and 12 /wp-content/ assets entered the catalogue
# via the archive layer and failed the coverage gate with 0% bodies — correctly, they are not pages.
_MACHINE_PATH_RE = re.compile(
    r"^/(?:wp-json|wp-admin|wp-includes|wp-content|xmlrpc\.php|"   # WordPress
    r"_next/static|_nuxt|_vercel|cdn-cgi|"                         # Next.js / Nuxt / Cloudflare
    r"ghost/api|admin/api|api/v\d+|graphql)(?:/|$)", re.I)         # Ghost / generic API roots

_DEFAULT_PORTS = {"http": "80", "https": "443"}
_UNRESERVED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def is_non_content(url):
    """True when the URL addresses machinery or a static asset rather than a PAGE."""
    path = _up.urlsplit(url).path
    return bool(_NON_CONTENT_RE.search(path) or _ASSET_EXT_RE.search(path)
                or _MACHINE_PATH_RE.match(path))


def _upper_escapes(s):
    """RFC 3986 §6.2.2.1: percent-encoding hex digits are CASE-INSENSITIVE and uppercase is the
    canonical form. Decodes an escaped UNRESERVED character back to itself while at it."""
    def fix(m):
        try:
            ch = chr(int(m.group(1), 16))
        except ValueError:
            return m.group(0)
        return ch if ch in _UNRESERVED else "%" + m.group(1).upper()
    return re.sub(r"%([0-9a-fA-F]{2})", fix, s)


def _remove_dot_segments(path):
    out = []
    for seg in path.split("/"):
        if seg == "..":
            if len(out) > 1:
                out.pop()
        elif seg != ".":
            out.append(seg)
    return "/".join(out)


def store_norm(u):
    """The STORED form: safe RFC-3986 normalisation + fragment stripped. Faithful to the site:
    scheme and host lowercased, default port dropped, escapes uppercased, dot segments resolved,
    an empty path becomes "/". Nothing else changes."""
    u = (u or "").strip()
    try:
        parts = _up.urlsplit(u)
    except ValueError:
        return u.split("#", 1)[0]
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    if not scheme or not host:
        return u.split("#", 1)[0]
    port = parts.port
    netloc = host if (port is None or str(port) == _DEFAULT_PORTS.get(scheme)) else "%s:%d" % (host, port)
    if parts.username:
        cred = parts.username + ((":" + parts.password) if parts.password else "")
        netloc = cred + "@" + netloc
    path = _remove_dot_segments(_upper_escapes(parts.path)) or "/"
    query = _upper_escapes(parts.query)
    return _up.urlunsplit((scheme, netloc, path, query, ""))


def clean_query(query):
    """Drop the tracking parameters from a query string, keeping order and the rest verbatim."""
    if not query:
        return ""
    kept = []
    for part in query.split("&"):
        if not part:
            continue
        name = part.split("=", 1)[0]
        if name in _TRACKING:
            continue
        kept.append(part)
    return "&".join(kept)


def match_key(u):
    """The aggressive GROUPING key — never stored as the record's URL."""
    try:
        parts = _up.urlsplit((u or "").strip())
    except ValueError:
        return (u or "").strip()
    host = (parts.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = parts.path.rstrip("/") or "/"
    # A sitemap may declare /%e3%83%96... where the site serves /%E3%83%96... — the same page.
    # Measured 2026-07-19: 7 non-Latin URLs (Japanese, Arabic, Chinese) were in the catalogue AND
    # reported as lost, purely because the two spellings keyed differently.
    path = re.sub(r"%([0-9a-fA-F]{2})", lambda m: "%" + m.group(1).upper(), path)
    return _up.urlunsplit(("https", host, path, clean_query(parts.query), ""))


def host_of(url):
    try:
        return (_up.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def own_host(url_or_host, domain_host):
    """Is this URL/host the company's own site (apex or www)? Port- and case-safe: urlsplit's
    .hostname strips ports and lowercases, so compare hostname to hostname."""
    h = host_of(url_or_host if "//" in url_or_host else "//" + url_or_host)
    own = host_of("//" + domain_host)
    own = own[4:] if own.startswith("www.") else own
    return h in (own, "www." + own)


def bare_host(domain):
    """example.com out of https://www.example.com/pricing."""
    d = (domain or "").strip().lower()
    if "//" in d:
        d = host_of(d)
    d = d.split("/")[0].split("?")[0]
    return d[4:] if d.startswith("www.") else d
