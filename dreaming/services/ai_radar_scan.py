"""AI Radar live scanner — fetches real articles from the watchlist via HTTP.

Plan 2026-05-23 deferred a self-written crawler ("Wave R2 uses Claude CLI
WebFetch"). In practice the Claude-CLI route drags in the whole spawn /
permission machinery; a direct RSS/Atom fetcher is self-contained, free, and
reliable for the 80% of sources that publish a feed (arXiv, Substacks, most
GitHub-pages and Jekyll blogs, vendor news feeds). Sources without a feed
(bare X/Twitter handles, JS-only pages) are skipped — they need an API or the
Claude-CLI path, which can come later.

`scan_now(db, sources_path)` is a pure coroutine: load the watchlist, discover
+ fetch each source's feed concurrently, parse items, and `INSERT OR IGNORE`
into `ai_radar_findings` (UNIQUE(source_key, url) dedups across runs).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import httpx

from dreaming.services.ai_radar import load_sources, SourceEntry

log = logging.getLogger(__name__)

_UA = "ai-dreaming-center-radar/1.0 (+https://github.com/micode-ai/ai-dreaming-center)"
_TIMEOUT = httpx.Timeout(15.0, connect=10.0)
_MAX_CONCURRENCY = 6
_MAX_ITEMS_PER_SOURCE = 8

# Field names on a source entry that may point at an HTML page or a feed,
# in priority order. X/Twitter/YouTube handles have no usable RSS → ignored.
_FEEDABLE_FIELDS = ("rss", "feed", "atom", "news", "blog", "research", "url", "org_url")
# Common relative locations of a feed when the field is an HTML page.
_FEED_SUFFIXES = ("feed", "rss", "feed.xml", "rss.xml", "atom.xml", "index.xml")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", s or "")).strip()


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()  # drop XML namespace


def _looks_like_feed(text: str, content_type: str) -> bool:
    ct = (content_type or "").lower()
    if any(x in ct for x in ("xml", "rss", "atom")):
        return True
    head = text[:400].lstrip().lower()
    return head.startswith("<?xml") or "<rss" in head or "<feed" in head


def _parse_dt(raw: str | None) -> str | None:
    """Best-effort → ISO8601 string (UTC). Accepts RFC822 (RSS) and ISO (Atom)."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)  # RFC822
        if dt is not None:
            return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _parse_feed(xml_text: str) -> list[dict]:
    """Parse RSS-2.0 or Atom into [{title, url, published_at, summary}]. Tolerant."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items: list[dict] = []

    # RSS: channel/item ; Atom: feed/entry. Find both regardless of namespace.
    entries = [e for e in root.iter() if _localname(e.tag) in ("item", "entry")]
    for e in entries:
        title = ""
        url = ""
        published = None
        summary = ""
        for child in e:
            name = _localname(child.tag)
            if name == "title" and child.text:
                title = child.text.strip()
            elif name == "link":
                # RSS: <link>text</link>; Atom: <link href="..." rel="alternate"/>
                href = child.get("href")
                rel = (child.get("rel") or "alternate").lower()
                if href and rel in ("alternate", ""):
                    url = url or href
                elif child.text and child.text.strip():
                    url = url or child.text.strip()
            elif name in ("pubdate", "published", "updated", "date") and not published:
                published = _parse_dt(child.text)
            elif name in ("description", "summary", "content") and not summary:
                summary = _strip_html(child.text or "")
        if title and url:
            items.append({
                "title": title[:480],
                "url": url,
                "published_at": published,
                "summary": summary[:600],
            })
    return items


async def _discover_feed(client: httpx.AsyncClient, page_url: str) -> tuple[str, str] | None:
    """Return (feed_url, feed_xml) for an HTML-or-feed URL, or None.

    If the URL already serves a feed, use it. Otherwise look for an
    <link rel=alternate type=.../rss+xml> in the HTML, then try common
    suffixes (/feed, /index.xml, ...).
    """
    try:
        r = await client.get(page_url, follow_redirects=True)
    except (httpx.HTTPError, UnicodeError):
        return None
    if r.status_code != 200:
        # Page itself failed — still try suffixes below against the base.
        body = ""
        ctype = ""
    else:
        body = r.text
        ctype = r.headers.get("content-type", "")
        if _looks_like_feed(body, ctype):
            return (str(r.url), body)

    # 1) <link rel="alternate" type="application/rss+xml" href="...">
    for m in re.finditer(r"<link\b[^>]*>", body, re.IGNORECASE):
        tag = m.group(0)
        if "alternate" in tag.lower() and ("rss+xml" in tag.lower() or "atom+xml" in tag.lower()):
            href_m = re.search(r'href=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            if href_m:
                feed_url = urljoin(str(r.url) if r.status_code == 200 else page_url, href_m.group(1))
                try:
                    fr = await client.get(feed_url, follow_redirects=True)
                    if fr.status_code == 200 and _looks_like_feed(fr.text, fr.headers.get("content-type", "")):
                        return (str(fr.url), fr.text)
                except httpx.HTTPError:
                    pass

    # 2) common suffixes
    base = page_url.rstrip("/")
    for suf in _FEED_SUFFIXES:
        cand = f"{base}/{suf}"
        try:
            fr = await client.get(cand, follow_redirects=True)
        except httpx.HTTPError:
            continue
        if fr.status_code == 200 and _looks_like_feed(fr.text, fr.headers.get("content-type", "")):
            return (str(fr.url), fr.text)
    return None


def _candidate_urls(src: SourceEntry) -> list[str]:
    seen: list[str] = []
    for field in _FEEDABLE_FIELDS:
        u = src.urls.get(field)
        if u and u not in seen and not any(
            host in u for host in ("x.com", "twitter.com", "youtube.com", "youtu.be")
        ):
            seen.append(u)
    return seen


async def _scan_source(
    client: httpx.AsyncClient, src: SourceEntry, cutoff: datetime,
) -> list[dict]:
    """Discover + fetch + parse one source into finding records (pre-insert shape)."""
    candidates = _candidate_urls(src)
    if not candidates:
        return []
    feed_xml = None
    for page in candidates:
        found = await _discover_feed(client, page)
        if found:
            feed_xml = found[1]
            break
    if not feed_xml:
        return []

    items = _parse_feed(feed_xml)
    records: list[dict] = []
    tags_json = json.dumps(src.tags, ensure_ascii=False)
    for it in items[:_MAX_ITEMS_PER_SOURCE]:
        pub = it.get("published_at")
        if pub:
            try:
                if datetime.fromisoformat(pub) < cutoff:
                    continue
            except ValueError:
                pass
        summary = it.get("summary") or ""
        records.append({
            "source_key": src.key,
            "source_kind": src.kind,
            "url": it["url"],
            "title": it["title"],
            # No model in the loop here — show the feed's own summary in both
            # locales; a later pass (or the Claude-CLI scan) can translate.
            "summary_ru": summary,
            "summary_en": summary,
            "published_at": pub,
            "tags_json": tags_json,
            "novelty_score": None,
            "relevance_hint": "",
            "raw_payload": json.dumps(
                {"source_name": src.name, **it}, ensure_ascii=False
            )[:8000],
        })
    return records


async def scan_now(db, sources_path=None, since_days: int = 45) -> dict:
    """Fetch every feedable source and merge new items into ai_radar_findings.

    Returns {sources, sources_with_feed, items, inserted, per_source}.
    """
    from dreaming.services.ai_radar import DEFAULT_SOURCES_PATH
    wl = load_sources(sources_path or DEFAULT_SOURCES_PATH)
    if not wl.sources:
        return {"sources": 0, "sources_with_feed": 0, "items": 0, "inserted": 0, "per_source": {}}

    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)
    per_source: dict[str, int] = {}
    all_records: list[dict] = []

    async with httpx.AsyncClient(
        timeout=_TIMEOUT, headers={"User-Agent": _UA}, follow_redirects=True,
    ) as client:
        async def worker(src: SourceEntry):
            async with sem:
                try:
                    recs = await _scan_source(client, src, cutoff)
                except Exception as e:  # one bad source must not sink the scan
                    log.warning("radar scan: source %s failed: %s", src.key, e)
                    recs = []
                per_source[src.key] = len(recs)
                all_records.extend(recs)

        await asyncio.gather(*(worker(s) for s in wl.sources))

    inserted = await db.insert_radar_findings(all_records) if all_records else 0
    sources_with_feed = sum(1 for n in per_source.values() if n > 0)
    log.info("radar scan: %d sources, %d with items, %d items, %d inserted",
             len(wl.sources), sources_with_feed, len(all_records), inserted)
    return {
        "sources": len(wl.sources),
        "sources_with_feed": sources_with_feed,
        "items": len(all_records),
        "inserted": inserted,
        "per_source": per_source,
    }
