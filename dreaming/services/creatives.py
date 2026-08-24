"""Creative pipeline helpers: who makes them, what a render is, and what is
checkably wrong with a drafted campaign.

Generic helpers are imported from `articles` rather than copied — the git-root
derivation, the publish gate, the venue resolution and the publish-mode
normalisation are about pipelines, not about prose, and two copies would drift.

Spec: docs/superpowers/specs/2026-08-22-creative-pipeline-design.md
"""
from __future__ import annotations
import hashlib
import re
import struct
from pathlib import Path

from dreaming.services.articles import (  # noqa: F401  (re-exported on purpose)
    can_publish,
    normalize_publish_mode,
    publish_label,
    resolve_article_root as resolve_repo_root,
    resolve_venue_id,
    slugify,
)

# The house formats, taken from accounting-ai-agent's own
# creatives/captions/README.md, which documents them as the target sizes.
# A venue names the ones it produces in `creative_formats`; anything it does
# not name is never expected of it.
FORMAT_SIZES: dict[str, tuple[int, int]] = {
    "post-4x5": (1080, 1350),
    "story": (1080, 1920),
    "reel-4x5": (1080, 1350),
    "reel": (1080, 1920),
}

# What the preview may serve out of a project repository, and as what. Nothing
# outside this map is served at all: the route is reading files from a
# directory an operator configured, so the answer to "what else could be in
# there" must be "it does not matter".
#
# No `.svg`, deliberately. An SVG is a script container, and this route serves
# from the center's own origin with the operator's cookies attached — a
# `draft_ref` is self-reported by a Claude session over unauthenticated
# localhost HTTP, so a session that wrote an SVG could get script executed in
# the center simply by reporting it. UPLOAD_EXTS below excluded svg for exactly
# this reason and serving it here would have undone that. A social render is
# png/jpg/mp4 anyway; an svg in a campaign shows up in the preview's
# "problems" list instead of rendering, which is the honest outcome.
MEDIA_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}

# What a human may attach as source material. Deliberately narrower than
# MEDIA_TYPES: svg is a script container in a browser, and nothing about a
# screen recording needs it.
UPLOAD_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm")

# Text a maker writes beside the renders — the post copy.
COPY_EXTS = (".md", ".txt")

_UNSAFE = re.compile(r"[^a-z0-9._-]+")
_MULTI_DASH = re.compile(r"-{2,}")


def media_type(path: str | Path) -> str | None:
    """Content type for a render, or None if this is not something we serve."""
    return MEDIA_TYPES.get(Path(str(path)).suffix.lower())


def is_copy(path: str | Path) -> bool:
    return Path(str(path)).suffix.lower() in COPY_EXTS


def safe_upload_name(name: str, *, max_len: int = 80) -> str:
    """A filename that cannot mean anything but a filename.

    Only the basename survives, so a browser sending `../../etc/passwd` or a
    Windows `C:\\x.png` contributes nothing but `passwd` / `x.png`. Everything
    outside `[a-z0-9._-]` becomes a dash, leading dots go (no `.gitignore`, no
    `.env`), and the extension is preserved so the allow-list check below is
    checking the real one. Returns "" for anything that leaves nothing usable,
    which callers must treat as a refusal rather than inventing a name.
    """
    base = Path(str(name).replace("\\", "/")).name.strip().lower()
    base = _UNSAFE.sub("-", base)
    base = _MULTI_DASH.sub("-", base).strip("-.")
    if not base or "." not in base:
        return ""
    stem, _, ext = base.rpartition(".")
    stem = stem.strip("-.")[: max(1, max_len - len(ext) - 1)]
    if not stem:
        return ""
    return f"{stem}.{ext}"


def upload_allowed(name: str) -> bool:
    return Path(name).suffix.lower() in UPLOAD_EXTS


def image_size(path: str | Path) -> tuple[int, int] | None:
    """Pixel size of a PNG, JPEG or GIF, read from its header.

    No image library: the three headers that matter here are a few bytes each,
    and a dependency to read them would be a dependency to keep. Returns None
    for a video or anything unparseable — a size that cannot be measured is
    reported as unmeasured, never guessed.
    """
    p = Path(str(path))
    try:
        with p.open("rb") as fh:
            head = fh.read(32)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                # IHDR is always the first chunk: length, type, then w/h.
                if head[12:16] == b"IHDR":
                    w, h = struct.unpack(">II", head[16:24])
                    return int(w), int(h)
                return None
            if head[:6] in (b"GIF87a", b"GIF89a"):
                w, h = struct.unpack("<HH", head[6:10])
                return int(w), int(h)
            if head[:2] == b"\xff\xd8":
                fh.seek(2)
                while True:
                    marker = fh.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    code = marker[1]
                    if code in (0xD8, 0x01) or 0xD0 <= code <= 0xD7:
                        continue
                    size_bytes = fh.read(2)
                    if len(size_bytes) < 2:
                        return None
                    seg_len = struct.unpack(">H", size_bytes)[0]
                    # SOF0..SOF15 except the DHT/DAC/DNL codes in between.
                    if code in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        body = fh.read(5)
                        if len(body) < 5:
                            return None
                        h, w = struct.unpack(">HH", body[1:5])
                        return int(w), int(h)
                    fh.seek(seg_len - 2, 1)
    except OSError:
        return None
    return None


def split_list(raw: str) -> list[str]:
    """Comma- or newline-separated setting into a clean list."""
    return [p.strip() for p in re.split(r"[,\n]+", raw or "") if p.strip()]


_PAGE_SUFFIX = re.compile(r"-\d{1,3}$")


def classify_render(path: str, formats: list[str], locales: list[str]) -> tuple[str, str]:
    """(format_id, locale) a render filename declares, or ("", "").

    The venue's convention is `<something>-<format>-<locale>.<ext>`, e.g.
    `ai-memory-post-4x5-pl.png`. Longest format id first, so `reel-4x5` is not
    read as `reel` with a locale of `4x5`. Matched against the formats and
    locales the venue actually declared, so an unrelated filename cannot invent
    a format that does not exist.
    """
    pure = Path(path)
    stem = pure.stem.lower()
    loc = next(
        (l for l in sorted(locales, key=len, reverse=True)
         if stem.endswith(f"-{l.lower()}")), "",
    )
    # A venue may put the locale in a directory instead of the filename --
    # `renders/pl/reel.mp4` rather than `...-reel-pl.mp4`. Both are real
    # conventions, and without this the two languages collapse into one bucket
    # and the preview shows them as if they were the same render. Only a
    # directory matching a *declared* locale counts, so an unrelated folder
    # cannot invent one.
    if not loc:
        lower = {l.lower(): l for l in locales}
        loc = next(
            (lower[part.lower()] for part in reversed(pure.parts[:-1])
             if part.lower() in lower), "",
        )
        rest = stem
    else:
        rest = stem[: -(len(loc) + 1)]
    fmt = next(
        (f for f in sorted(formats, key=len, reverse=True)
         if rest.endswith(f"-{f.lower()}") or rest == f.lower()), "",
    )
    # Multi-page formats ship as numbered sequences -- `carousel-01.png`,
    # `story-9x16-03.png`. Strip a trailing page number and try once more, but
    # only keep the result if what remains is a format the venue declared, so
    # a filename ending in digits for any other reason still falls through.
    if not fmt:
        trimmed = _PAGE_SUFFIX.sub("", rest)
        if trimmed != rest:
            fmt = next(
                (f for f in sorted(formats, key=len, reverse=True)
                 if trimmed.endswith(f"-{f.lower()}") or trimmed == f.lower()),
                "",
            )
    return fmt, loc


def group_renders(
    paths: list[str], formats: list[str], locales: list[str],
) -> tuple[dict[tuple[str, str], list[str]], list[str]]:
    """Renders keyed by (format, locale), plus everything unclassified.

    Unclassified is not a failure: a venue may ship a poster or a thumbnail
    that belongs to no format. It is shown separately rather than dropped.
    """
    grouped: dict[tuple[str, str], list[str]] = {}
    other: list[str] = []
    for p in paths:
        fmt, loc = classify_render(p, formats, locales)
        if fmt:
            grouped.setdefault((fmt, loc), []).append(p)
        else:
            other.append(p)
    return grouped, other


def list_attachments(root: Path, camp_rel: str) -> list[str]:
    """Source material a human attached, as paths relative to `root`.

    Only files sitting directly in `<campaign>/src/`, only types this pipeline
    serves, sorted. Not recursive: `src/` is where the upload route writes and
    nothing else should be inventing subtrees there, so a recursive walk would
    only widen what the media route has to vouch for.

    This listing is also the allow-list the media route checks an attachment
    path against — membership in a directory listing, never arithmetic on the
    caller's string.
    """
    src = root / camp_rel / "src"
    try:
        names = sorted(
            p.name for p in src.iterdir()
            if p.is_file() and media_type(p.name)
        )
    except OSError:
        return []
    return [f"{camp_rel}/src/{n}" for n in names]


def draft_findings(
    root: Path, draft_paths: list[str], *, formats: list[str],
    locales: list[str],
) -> list[dict]:
    """What is checkably wrong with a drafted campaign, as proposed revisions.

    Every check is computable without knowing how the venue builds anything:
    which formats produced a file, whether a render's pixels match the size its
    format declares, whether each locale got something, and whether any post
    copy exists at all. A video's dimensions are not measured — the header
    parse covers stills only — so a reel is reported as present or absent, and
    never as the wrong size on a guess.
    """
    findings: list[dict] = []
    media = [p for p in draft_paths if media_type(p)]
    copy = [p for p in draft_paths if is_copy(p)]
    grouped, _other = group_renders(media, formats, locales)

    for fmt in formats:
        produced = [p for (f, _l), ps in grouped.items() if f == fmt for p in ps]
        if not produced:
            findings.append({
                "kind": "format_missing",
                "format": fmt,
                "note": (
                    f"No render for the `{fmt}` format, which this venue is "
                    f"configured to produce. Build it the way the neighbouring "
                    f"campaigns build theirs, or say in your report why this "
                    f"campaign cannot have one."
                ),
            })

    for loc in locales:
        produced = [p for (_f, l), ps in grouped.items() if l == loc for p in ps]
        if not produced:
            findings.append({
                "kind": "locale_missing",
                "locale": loc,
                "note": (
                    f"Nothing was rendered for the `{loc}` locale. Every "
                    f"format this campaign ships needs its own `{loc}` file — "
                    f"a shared image with foreign text on it is not a "
                    f"localisation."
                ),
            })

    for (fmt, loc), paths in sorted(grouped.items()):
        want = FORMAT_SIZES.get(fmt)
        if not want:
            continue
        for rel in sorted(paths):
            got = image_size(root / rel)
            if got is None or got == want:
                continue
            findings.append({
                "kind": "wrong_size",
                "format": fmt,
                "locale": loc,
                "path": rel,
                "got": f"{got[0]}x{got[1]}",
                "want": f"{want[0]}x{want[1]}",
                "note": (
                    f"`{rel}` is {got[0]}x{got[1]}, but the `{fmt}` format is "
                    f"{want[0]}x{want[1]}. Re-render it at the declared size "
                    f"rather than letting the platform crop it."
                ),
            })

    if not copy:
        findings.append({
            "kind": "copy_missing",
            "note": (
                "The campaign has renders but no post copy. Write the text "
                "that ships with them, where the neighbouring campaigns keep "
                "theirs, in every locale this campaign targets."
            ),
        })
    return findings


# Ordered most specific first. Deliberately no bare "writer": the venues here
# have `blog-writer` agents, and a prose writer is not a campaign maker — the
# autodetect picked one before this list was narrowed, which would have handed
# reel production to an article agent. A venue with nothing marketing-shaped
# gets "self", and the session does the work itself, which is the honest answer
# rather than the nearest-sounding one.
_AGENT_HINTS = ("creative", "designer", "design", "marketing", "copywriter",
                "social", "brand")


def resolve_agent(working_dir: str | Path, configured: str = "") -> str:
    """The agent that makes creatives here, or "self".

    An explicit setting always wins. Otherwise the venue's own agent files are
    searched for a marketing-ish name, most specific hint first, so a project
    with both a `blog-writer` and a `landing-copywriter` does not get whichever
    the filesystem happened to list first.
    """
    if configured.strip():
        return configured.strip()
    agents_dir = Path(str(working_dir)) / ".claude" / "agents"
    try:
        names = sorted(p.stem for p in agents_dir.glob("*.md"))
    except OSError:
        return "self"
    for hint in _AGENT_HINTS:
        for name in names:
            if hint in name.lower():
                return name
    return "self"


# Cyrillic -> Latin, enough for the locales this center actually runs (ru, ua,
# be). Multi-character results are intentional: `щ` -> `shch` reads back, and a
# campaign slug is a directory name a human will be looking at.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g", "д": "d", "е": "e",
    "ё": "e", "є": "ie", "ж": "zh", "з": "z", "и": "i", "і": "i", "ї": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ў": "u", "ф": "f", "х": "kh",
    "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y",
    "ь": "", "э": "e", "ю": "iu", "я": "ia", "'": "", "’": "",
}
_SLUG_KEEP = re.compile(r"[^a-z0-9]+")


def campaign_slug(title: str, *, max_words: int = 6) -> str:
    """A campaign's directory name, derived from its title. Never empty.

    This is deliberately NOT `articles.slugify`. That one documents dropping
    Cyrillic on purpose, because an article's `slug_hint` is only a seed and
    the writer picks the published slug afterwards. A campaign slug is not a
    seed: it is the directory attachments land in, before any session runs, and
    it never changes. An empty one would put a human's footage in the shared
    creatives root and make the next same-shaped title collide with it on the
    unique index — silently, as a "duplicate" it never was.

    So Cyrillic is transliterated rather than dropped (`Дашборды и отчёты` ->
    `dashbordy-i-otchety`, a name an operator can recognise in a directory
    listing), and a title that still leaves nothing usable — punctuation only,
    emoji only, a script not in the table — falls back to a digest of the
    title, which keeps identical titles colliding and distinct ones apart.
    """
    low = (title or "").strip().lower()
    latin = "".join(_TRANSLIT.get(ch, ch) for ch in low)
    words = [w for w in _SLUG_KEEP.sub(" ", latin).split() if w]
    if not words:
        digest = hashlib.sha1(low.encode("utf-8")).hexdigest()[:10]
        return f"campaign-{digest}"
    if len(words) > max_words:
        digest = hashlib.sha1(low.encode("utf-8")).hexdigest()[:6]
        return "-".join(words[:max_words] + [digest])
    return "-".join(words)


def build_message(row: dict, label: str, *, formats: list[str] | None = None) -> str:
    """Commit subject and body for a published campaign.

    Its own function rather than the article one: a reader of `git log` should
    be able to tell a campaign from an article without opening the diff, and
    the formats are the thing they will want to know. The verification claim is
    the same contract — whatever it says here must be what actually happened.
    """
    title = (row.get("title") or "creative").strip()
    slug = (row.get("slug_hint") or "").strip()
    body = [f"campaign: {slug}" if slug else ""]
    if formats:
        body.append(f"formats: {', '.join(formats)}")
    if row.get("locales"):
        body.append(f"locales: {row['locales']}")
    body.append(f"verification: {label}")
    if row.get("source") and row.get("source_ref"):
        body.append(f"proposed from {row['source']} {row['source_ref']}")
    return (f"creative: publish “{title}”\n\n"
            + "\n".join(b for b in body if b) + "\n")


def campaign_dir(creative_dir: str, slug: str) -> str:
    """The campaign's directory, relative to the venue's repository root.

    Kept as a plain relative path (not resolved here) because it is what the
    publish validator and the media route both check, and both need it in the
    same shape the operator typed.
    """
    base = (creative_dir or "").strip().strip("/\\").replace("\\", "/")
    return f"{base}/{slug}" if base else slug
