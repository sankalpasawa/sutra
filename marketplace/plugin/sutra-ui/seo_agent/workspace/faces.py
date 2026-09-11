"""faces.py -- the one list of faces a person can pick from, and the rules for picking.

WHY A CURATED LIST AND NOT "ANY EMOJI". A free text field gives you three problems on day one:
somebody picks the same one as somebody else, somebody picks a flag or a skin tone and it reads
as a statement about them rather than a name, and somebody picks a glyph that is a grey box on
another machine. A fixed list solves all three at once and costs nothing.

HOW THIS LIST WAS CHOSEN. Every entry had to pass four tests:
  1. Legible at 24px. Anything whose detail collapses into a blob was cut.
  2. Distinct in silhouette from every other entry. No two cats, no two birds of the same shape.
  3. Nothing about a person. No faces, no body parts, no skin tones, no flags, no religion.
     A face-emoji avatar invites "why did you pick the angry one"; a heron does not.
  4. Nothing that reads as status. No crowns, no money, no trophies. Everybody is an animal.

WHY ANIMALS. They carry personality without carrying a claim, they are the one category people
already accept as an identity (every team tool does this), and there are enough visually distinct
ones to cover a workspace many times over without repeats.
"""

# 32 faces. A workspace would have to reach 33 people before anybody must share one, and the
# picker offers what is still free first, so early members always get a unique face.
FACES = [
    "🦊", "🦉", "🐙", "🦁", "🐝", "🦋", "🐬", "🦅",
    "🐢", "🦈", "🐺", "🦚", "🦭", "🦩", "🐆", "🦌",
    "🦔", "🦇", "🐊", "🦖", "🐧", "🦜", "🐌", "🦑",
    "🕊️", "🦡", "🦥", "🐘", "🦏", "🐫", "🦒", "🐿️",
]

# What each one is called, for the tooltip and for anyone reading the code. Kept beside the list
# so adding a face without naming it is an obvious omission rather than a silent blank.
NAMES = {
    "🦊": "Fox", "🦉": "Owl", "🐙": "Octopus", "🦁": "Lion",
    "🐝": "Bee", "🦋": "Butterfly", "🐬": "Dolphin", "🦅": "Eagle",
    "🐢": "Turtle", "🦈": "Shark", "🐺": "Wolf", "🦚": "Peacock",
    "🦭": "Seal", "🦩": "Flamingo", "🐆": "Leopard", "🦌": "Deer",
    "🦔": "Hedgehog", "🦇": "Bat", "🐊": "Crocodile", "🦖": "T-rex",
    "🐧": "Penguin", "🦜": "Parrot", "🐌": "Snail", "🦑": "Squid",
    "🕊️": "Dove", "🦡": "Badger", "🦥": "Sloth", "🐘": "Elephant",
    "🦏": "Rhino", "🐫": "Camel", "🦒": "Giraffe", "🐿️": "Squirrel",
}

DEFAULT = "🦊"


def name_of(emoji):
    """What to call a face. An unknown one is not an error: a teammate on a newer Sutra may have
    picked from a longer list than this build knows about, and their face should still draw."""
    return NAMES.get(emoji or "", "")


def is_known(emoji):
    return (emoji or "") in NAMES


def free(taken):
    """The faces nobody in this workspace has yet, in pack order.

    `taken` is whatever the members table currently holds. Unknown values in it are ignored
    rather than trusted, so a garbage row cannot make a face look unavailable for everybody.
    """
    used = {e for e in (taken or []) if e in NAMES}
    return [e for e in FACES if e not in used]


def suggest(taken, name=""):
    """One face to pre-select in the picker.

    Free faces first, so a workspace of five people has five different ones without anybody
    thinking about it. Past 32 members they start repeating, which is the honest outcome and
    better than refusing to let a 33rd person join.

    The pick is derived from their NAME, not from a counter or a clock: the same person opening
    the picker twice is offered the same face both times, which is what makes it feel chosen
    rather than dealt.
    """
    pool = free(taken) or FACES
    if not name:
        return pool[0]
    h = 0
    for ch in name.strip().lower():
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return pool[h % len(pool)]
