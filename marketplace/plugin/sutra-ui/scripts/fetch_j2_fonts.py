#!/usr/bin/env python3
"""fetch_j2_fonts.py -- vendor the three font families the J2 page asks Google Fonts for (substitution S3).

The prototype's page links one external stylesheet. A local-first desktop app would call out on every open and, offline,
fall back to Arial and Menlo, so the screen would not look like the prototype's. This script reads the page's exact
family list from j2ui_assets/PINNED.json (external[0], the prototype's own href), asks Google Fonts for its CSS with a
current browser User-Agent (so it answers woff2), keeps the `latin` and `latin-ext` subsets, downloads the files and
writes, under j2ui_assets/fonts/:

    fonts.css      the @font-face rules with relative url(...) to the files below
    <family>-<subset>-<hash>.woff2
    LICENSE.txt    the SIL Open Font License 1.1 and where each family came from

Bricolage Grotesque, IBM Plex Sans and IBM Plex Mono are all SIL Open Font License. Then run scripts/sync_j2_ui.py:
it turns S3 on when fonts/fonts.css exists (unless --no-local-fonts), swaps the href in the copy and pins every file's
hash. Without a network, or when a download is not wanted, nothing is written, the script exits 3 and the page keeps the
prototype's own link ("fonts not vendored: no network").

    python3 scripts/fetch_j2_fonts.py [--css-url URL] [--root DIR]
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

UI = Path(__file__).resolve().parent.parent
#: a current browser, so Google Fonts answers woff2 and one @font-face per subset
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
KEEP = ("latin", "latin-ext")
BUDGET = 600 * 1024
FACE = re.compile(r"(?:/\*\s*([\w-]+)\s*\*/\s*)?@font-face\s*\{(.*?)\}", re.S)
SRC = re.compile(r"src:\s*url\(\s*['\"]?([^)'\"\s]+)['\"]?\s*\)\s*format\(\s*['\"]woff2['\"]\s*\)\s*;?")

OFL = """This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
https://openfontlicense.org

-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded,
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting -- in part or in whole -- any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.
"""


class FetchError(Exception):
    """The network or Google Fonts did not give what the page needs; nothing is written."""


def http(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except (urllib.error.URLError, OSError) as e:
        raise FetchError("fonts not vendored: no network (%s)" % getattr(e, "reason", e)) from e


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def vendor(css_url, fetch=http):
    """({file name: bytes}, [family names]) for the `latin` and `latin-ext` faces of the stylesheet at css_url. The
    stylesheet is rewritten so each face names its file relative to fonts.css. Nothing touches the disk here."""
    css = fetch(css_url).decode("utf-8")
    files, faces, families, got = {}, [], [], {}
    for m in FACE.finditer(css):
        subset, body = m.group(1), m.group(2)
        if subset not in KEEP:
            continue
        src = SRC.search(body)
        fam = re.search(r"font-family:\s*['\"]?([^;'\"]+)", body)
        if not src or not fam:
            raise FetchError("a face of the stylesheet has no woff2 url or no family; the answer is not what was expected")
        family = fam.group(1).strip()
        if family not in families:
            families.append(family)
        url = src.group(1)
        if url not in got:
            data = fetch(url)
            name = "%s-%s-%s.woff2" % (slug(family), subset, hashlib.sha256(data).hexdigest()[:8])
            got[url] = name
            files[name] = data
        faces.append("@font-face{%s}" % re.sub(r"\s+", " ", SRC.sub("src:url(%s) format('woff2');" % got[url], body)).strip())
    if not faces:
        raise FetchError("the stylesheet holds no latin or latin-ext face")
    head = ("/* fonts.css -- vendored by scripts/fetch_j2_fonts.py from Google Fonts (%s); SIL Open Font License, see LICENSE.txt */\n"
            % ", ".join(families))
    files["fonts.css"] = (head + "\n".join(faces) + "\n").encode("utf-8")
    files["LICENSE.txt"] = ("Fonts in this folder: %s\nSource: %s\n\n%s" % (", ".join(families), css_url, OFL)).encode("utf-8")
    total = sum(len(v) for v in files.values())
    if total > BUDGET:
        raise FetchError("the fonts are %d KB, over the %d KB budget; nothing written" % (total // 1024, BUDGET // 1024))
    return files, families


def main(argv=None, out=print, fetch=http):
    ap = argparse.ArgumentParser(prog="fetch_j2_fonts.py", description="Vendor the J2 page's Google Fonts (S3).")
    ap.add_argument("--css-url", help="the Google Fonts stylesheet (default: the external href in j2ui_assets/PINNED.json)")
    ap.add_argument("--root", help="the app folder to write under (default: the folder above scripts/)")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve() if a.root else UI
    url = a.css_url
    if not url:
        try:
            url = json.loads((root / "j2ui_assets" / "PINNED.json").read_text())["external"][0]
        except (OSError, ValueError, KeyError, IndexError):
            out("no j2ui_assets/PINNED.json with an external stylesheet: run scripts/sync_j2_ui.py first, or give --css-url")
            return 2
    try:
        files, families = vendor(url, fetch)
    except FetchError as e:
        out(str(e))
        return 3
    folder = root / "j2ui_assets" / "fonts"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.woff2"):
        old.unlink()
    for name, data in sorted(files.items()):
        (folder / name).write_bytes(data)
    out("vendored %s: %d files, %d KB; now run scripts/sync_j2_ui.py" % (", ".join(families), len(files), sum(map(len, files.values())) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
