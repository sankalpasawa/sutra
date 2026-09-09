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


# ── the language prefix, and what a page's TYPE is when the CMS did not say ──────────────────────
# A localised site puts the language first in the path (/de/hr-glossary/x). Read naively, that
# first segment becomes the page's "type". Found 2026-09-09 on the first real site: 2,299 pages
# were typed da/ja/ar/el/es/pl/pt-br/de/fr/no/nl/sv/it, so thirteen of the catalogue's
# thirty-nine "types" were languages and the type filter was unusable. The language belongs in
# the row's own `lang` field, which the extractor already fills from <html lang>; it is never a
# kind of page. An explicit ISO 639-1 list, never a two-letter regex: "it", "no", "is" and "in"
# are real path segments on plenty of sites, and only a known code may steal the first slot.
LANGUAGE_SEGMENTS = frozenset("""
aa ab af ak am ar as ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz
ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie
ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu
lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt
qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn
to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu
""".split())

# The full language names, so a filter reads "German" and not "de". Only the ones a site is
# realistically translated into; anything else falls back to the code itself.
LANGUAGE_NAMES = {
    "ar": "Arabic", "bg": "Bulgarian", "bn": "Bengali", "cs": "Czech", "da": "Danish",
    "de": "German", "el": "Greek", "en": "English", "es": "Spanish", "et": "Estonian",
    "fa": "Persian", "fi": "Finnish", "fr": "French", "he": "Hebrew", "hi": "Hindi",
    "hr": "Croatian", "hu": "Hungarian", "id": "Indonesian", "it": "Italian", "ja": "Japanese",
    "ko": "Korean", "lt": "Lithuanian", "lv": "Latvian", "ms": "Malay", "nb": "Norwegian",
    "nl": "Dutch", "nn": "Norwegian", "no": "Norwegian", "pl": "Polish", "pt": "Portuguese",
    "ro": "Romanian", "ru": "Russian", "sk": "Slovak", "sl": "Slovenian", "sr": "Serbian",
    "sv": "Swedish", "th": "Thai", "tr": "Turkish", "uk": "Ukrainian", "vi": "Vietnamese",
    "zh": "Chinese",
}


def is_language_tag(s):
    """Is this WHOLE string a language tag: "de", "pt-br", "zh-Hant"? The whole string, never a
    prefix. Found 2026-09-09 by running the repair: matching on the part before the first hyphen
    read "hr-glossary" as Croatian and retyped 859 real glossary pages.
    """
    t = (s or "").strip().lower().replace("_", "-")
    if not t:
        return False
    head, _, region = t.partition("-")
    if head not in LANGUAGE_SEGMENTS:
        return False
    return not region or (2 <= len(region) <= 4 and region.isalnum())


def language_name(code):
    """"German" for "de", "de-at" or "DE". The code itself when it is not one we name."""
    c = (code or "").strip().lower().replace("_", "-")
    return LANGUAGE_NAMES.get(c) or LANGUAGE_NAMES.get(c.split("-")[0]) or (c or "")


def path_language(url):
    """The language tag a URL carries in its FIRST path segment, or "". "de" for /de/x, "pt" for
    /pt-br/x. Only the first segment is looked at: /blog/de-vs-en is an article, not German."""
    for seg in _up.urlsplit(url).path.strip("/").split("/"):
        return seg.lower().replace("_", "-").partition("-")[0] if is_language_tag(seg) else ""
    return ""


def content_segments(url):
    """A URL's path segments with any leading language tag removed. This is what a type is read
    from, so /de/hr-glossary/abc types as hr-glossary exactly like /hr-glossary/abc does."""
    parts = [p for p in _up.urlsplit(url).path.strip("/").split("/") if p]
    if parts and path_language(url):
        parts = parts[1:]
    return parts


def type_from_path(url, votes=None, default="pages"):
    """The kind of page a URL looks like, when the content system did not say.

    `votes` is {first-segment: {type: count}} gathered from the pages whose type IS known, so a
    site's own naming wins over the path. The language prefix is stripped first, which is the
    whole point: the German copy of a glossary page is a glossary page.
    """
    parts = content_segments(url)
    seg = parts[0] if parts else ""
    if votes:
        v = votes.get(seg)
        if v:
            return max(v, key=v.get)
    return seg if seg and len(parts) > 1 else default
