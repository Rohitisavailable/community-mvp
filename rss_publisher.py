"""Poll project RSS/Atom feeds and publish new items to Telegram channels."""
from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

_LOG = logging.getLogger("community_desk.rss")
_MAX_FEED_BYTES = 2_000_000
_POLL_SECONDS = 300
_MAX_ITEMS_PER_FEED = 10


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, names: set[str]) -> str:
    for child in element:
        if _local_name(child.tag) not in names:
            continue
        if _local_name(child.tag) == "link" and child.attrib.get("href"):
            return child.attrib["href"].strip()
        return " ".join(part.strip() for part in child.itertext() if part.strip())
    return ""


def _plain_text(value: str, limit: int = 700) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit].rstrip()


def _parse_feed(payload: bytes) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise ValueError("The URL did not return valid RSS or Atom XML") from None

    root_name = _local_name(root.tag)
    candidates = [element for element in root.iter() if _local_name(element.tag) in {"item", "entry"}]
    if root_name not in {"rss", "feed", "rdf"} and not candidates:
        raise ValueError("The URL is valid XML but does not appear to be an RSS or Atom feed")
    parsed: list[dict[str, str]] = []
    for element in candidates[:50]:
        title = _plain_text(_child_text(element, {"title"}), 240)
        link = _child_text(element, {"link"}).strip()
        description = _plain_text(_child_text(element, {"description", "summary", "content", "encoded"}))
        guid = _plain_text(_child_text(element, {"guid", "id"}), 500)
        published = _plain_text(_child_text(element, {"pubdate", "published", "updated", "date"}), 100)
        categories = " ".join(_plain_text(child.attrib.get("term", child.text or ""), 80) for child in element if _local_name(child.tag) == "category")
        identity = guid or link or f"{title}|{published}|{description[:120]}"
        if not identity.strip():
            continue
        parsed.append({
            "key": hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest(),
            "title": title or "New feed update",
            "link": link,
            "description": description,
            "published": published,
            "categories": categories,
        })
    return parsed


def fetch_feed(raw_url: str, validate_url) -> tuple[str, list[dict[str, str]]]:
    """Fetch one public HTTPS feed, validating every redirect destination."""
    url = validate_url(raw_url)
    opener = urllib.request.build_opener(_NoRedirectHandler())
    for _ in range(4):
        url = validate_url(url)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CommunityDeskRSS/1.0", "Accept": "application/atom+xml,application/rss+xml,application/xml,text/xml,*/*;q=0.5"},
        )
        try:
            response = opener.open(req, timeout=12)
        except urllib.error.HTTPError as error:
            if error.code in {301, 302, 303, 307, 308}:
                location = error.headers.get("Location", "")
                if not location:
                    raise ValueError("The RSS feed redirected without a destination") from None
                url = urljoin(url, location)
                continue
            raise ValueError(f"The RSS feed returned HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ValueError("Could not reach the RSS feed") from None
        with response:
            payload = response.read(_MAX_FEED_BYTES + 1)
        if len(payload) > _MAX_FEED_BYTES:
            raise ValueError("The RSS feed is larger than 2 MB")
        items = _parse_feed(payload)
        for item in items:
            if item.get("link"):
                item["link"] = urljoin(url, item["link"])
        return url, items
    raise ValueError("The RSS feed redirected too many times")


def _matches_filter(item: dict[str, str], keywords: str) -> bool:
    terms = [term.strip().casefold() for term in keywords.split(",") if term.strip()]
    if not terms:
        return True
    text = " ".join(item.get(key, "") for key in ("title", "description", "categories")).casefold()
    return any(term in text for term in terms)


def _telegram_send(token: str, channel_id: str, text: str) -> None:
    payload = json.dumps({"chat_id": channel_id, "text": text[:3900]}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read(256_000))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError("Telegram could not be reached") from None
    if not result.get("ok"):
        raise ValueError("Telegram rejected the channel post; check the channel ID and bot posting permission")


def _render_item(item: dict[str, str], feed_url: str) -> str:
    link = item.get("link", "").strip() or feed_url
    parts = [f"📰 {item.get('title') or 'New feed update'}"]
    if item.get("description"):
        parts.append(item["description"])
    parts.append(f"🔗 {link}")
    return "\n\n".join(parts)[:3900]


def poll_rss_feeds(store, validate_url, token: str | None = None) -> None:
    token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return
    for feed in store.enabled_rss_feeds():
        feed_id = int(feed["id"])
        try:
            feed_url, items = fetch_feed(feed["feed_url"], validate_url)
            if not feed.get("initialized"):
                store.initialize_rss_feed(feed_id, [item["key"] for item in items])
                store.set_rss_feed_status(feed_id)
                continue

            # Feed readers usually list newest first. Publish oldest-first when
            # catching up, and cap each cycle to keep a busy feed from flooding.
            new_items = [item for item in reversed(items) if store.claim_rss_item(feed_id, item["key"])]
            published = 0
            for item in new_items:
                if not _matches_filter(item, feed.get("keywords", "")):
                    store.finish_rss_item(feed_id, item["key"], sent=False, skipped=True)
                    continue
                if published >= _MAX_ITEMS_PER_FEED:
                    store.finish_rss_item(feed_id, item["key"], sent=False)
                    continue
                try:
                    _telegram_send(token, feed["channel_id"], _render_item(item, feed_url))
                except ValueError:
                    store.finish_rss_item(feed_id, item["key"], sent=False)
                    raise
                store.finish_rss_item(feed_id, item["key"], sent=True)
                published += 1
            store.set_rss_feed_status(feed_id)
        except Exception as error:
            message = str(error)[:400] if isinstance(error, ValueError) else "RSS polling failed; it will retry automatically"
            store.set_rss_feed_status(feed_id, message)
            _LOG.warning("RSS feed %s failed: %s", feed_id, message)


def start_rss_scheduler(store, validate_url, interval: int = _POLL_SECONDS) -> None:
    """Start a single-process polling loop. Render free instances may sleep while idle."""
    if not os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
        return
    lock = getattr(start_rss_scheduler, "_lock", None)
    if lock is None:
        lock = threading.Lock()
        setattr(start_rss_scheduler, "_lock", lock)
    with lock:
        if getattr(start_rss_scheduler, "_started", False):
            return
        setattr(start_rss_scheduler, "_started", True)

    def loop() -> None:
        while True:
            try:
                poll_rss_feeds(store, validate_url)
            except Exception:
                _LOG.exception("RSS polling cycle failed")
            time.sleep(interval)

    threading.Thread(target=loop, name="community-desk-rss", daemon=True).start()
