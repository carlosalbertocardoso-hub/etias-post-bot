from email.utils import format_datetime
from datetime import datetime, timezone, timedelta

import scraper


class _FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


def _rss_feed(items):
    entries = "\n".join(
        f"""<item>
              <title>{title}</title>
              <link>{link}</link>
              <pubDate>{format_datetime(pub_date)}</pubDate>
            </item>"""
        for title, link, pub_date in items
    )
    return f"""<?xml version="1.0"?>
    <rss version="2.0"><channel>{entries}</channel></rss>""".encode("utf-8")


def test_scrape_rss_filters_irrelevant_and_stale(monkeypatch):
    now = datetime.now(timezone.utc)
    feed = _rss_feed([
        ("New ETIAS requirements for 2026 travelers", "https://example.com/etias-2026", now),
        ("Local football team wins championship", "https://example.com/football", now),
        ("Old Schengen visa update", "https://example.com/old-schengen", now - timedelta(days=30)),
    ])
    monkeypatch.setattr(scraper.SESSION, "get", lambda *a, **k: _FakeResponse(feed))

    articles = scraper._scrape_rss("https://fake.feed/rss", posted_urls=set(), seen=set())

    urls = {a["url"] for a in articles}
    assert urls == {"https://example.com/etias-2026"}


def test_scrape_rss_returns_empty_on_bad_status(monkeypatch):
    monkeypatch.setattr(scraper.SESSION, "get", lambda *a, **k: _FakeResponse(b"", status_code=503))
    assert scraper._scrape_rss("https://fake.feed/rss", posted_urls=set(), seen=set()) == []
