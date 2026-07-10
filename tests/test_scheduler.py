import json

import scheduler
import scraper
from scheduler import is_valid_post_title


def test_valid_title_accepted():
    assert is_valid_post_title("ETIAS and the Schengen Area Explained")


def test_url_rejected():
    assert not is_valid_post_title("https://example.com/some-article")


def test_empty_rejected():
    assert not is_valid_post_title("")


def test_too_short_rejected():
    assert not is_valid_post_title("ETIAS")


def _use_tmp_heartbeat(monkeypatch, tmp_path):
    heartbeat_path = tmp_path / "last_run.json"
    monkeypatch.setattr(scheduler, "_HEARTBEAT_PATH", str(heartbeat_path))
    return heartbeat_path


def test_run_daily_job_no_candidates(monkeypatch, tmp_path):
    # Regression: a day with zero new articles used to just print+return with
    # no distinct signal and no committed state, which is indistinguishable
    # from a silent crash from the workflow's perspective.
    heartbeat_path = _use_tmp_heartbeat(monkeypatch, tmp_path)
    monkeypatch.setattr(scheduler, "get_new_articles", lambda *a, **kw: [])

    outcome = scheduler.run_daily_job()

    assert outcome == "no_candidates"
    assert json.loads(heartbeat_path.read_text())["outcome"] == "no_candidates"


def test_run_daily_job_all_candidates_fail(monkeypatch, tmp_path):
    heartbeat_path = _use_tmp_heartbeat(monkeypatch, tmp_path)
    monkeypatch.setattr(
        scheduler, "get_new_articles",
        lambda *a, **kw: [{"url": "https://x/1", "title": "A"}, {"url": "https://x/2", "title": "B"}],
    )
    monkeypatch.setattr(scheduler, "_try_publish_article", lambda article: False)

    outcome = scheduler.run_daily_job()

    assert outcome == "all_failed"
    assert json.loads(heartbeat_path.read_text())["outcome"] == "all_failed"


def test_run_daily_job_publishes_on_first_success(monkeypatch, tmp_path):
    _use_tmp_heartbeat(monkeypatch, tmp_path)
    monkeypatch.setattr(
        scheduler, "get_new_articles",
        lambda *a, **kw: [{"url": "https://x/1", "title": "A"}, {"url": "https://x/2", "title": "B"}],
    )
    calls = []

    def _fake_try(article):
        calls.append(article["url"])
        return True  # first candidate succeeds

    monkeypatch.setattr(scheduler, "_try_publish_article", _fake_try)

    outcome = scheduler.run_daily_job()

    assert outcome == "published"
    assert calls == ["https://x/1"]  # stops after first success, doesn't try the rest


def test_try_publish_article_skips_when_generated_title_duplicates_posted(monkeypatch, tmp_path):
    # Regression for the live incident (audit 2026-07-10): get_new_articles()
    # only dedupes the *source* headline against past generated titles.
    # Two differently-worded source articles about the same event can both
    # pass that filter, then Claude independently converges on the exact
    # same blog title for both (confirmed live: posts 1269/1274, 1 day
    # apart, and 1185/1379, 2 months apart -- identical title.rendered).
    # This asserts the actual generated title is now re-checked before the
    # live WordPress write happens.
    posted_file = tmp_path / "posted_articles.json"
    already_published_title = "ETIAS for Sea Travel: Ferry and Cruise Passengers Need Authorization"
    posted_file.write_text(json.dumps({
        "urls": ["https://source/already-covered"],
        "titles": [already_published_title],
        "post_links": [],
    }))
    monkeypatch.setattr(scraper, "POSTED_FILE", str(posted_file))

    monkeypatch.setattr(
        scheduler, "fetch_article_content",
        lambda url: {
            "title": "Cruise passengers must apply for travel authorization",
            "content": "x" * 200,
            "url": url,
            "image_url": None,
            "valid": True,
        },
    )
    monkeypatch.setattr(scheduler, "set_recent_posts", lambda posts: None)
    monkeypatch.setattr(
        scheduler, "generate_post",
        lambda *a, **kw: {
            "title": already_published_title,  # Claude converges on the same title
            "content": "<p>body</p>",
            "meta_description": "desc",
            "categories": [1],
        },
    )
    publish_calls = []
    monkeypatch.setattr(
        scheduler, "publish_post",
        lambda **kw: publish_calls.append(kw) or {"id": 1, "link": "https://x"},
    )

    article = {"url": "https://source/2", "title": "Cruise passengers must apply for travel authorization"}
    result = scheduler._try_publish_article(article)

    assert result is False
    assert publish_calls == []  # never reaches the live write

    # And the skip is durably recorded, same as any other _skip() path.
    saved = json.loads(posted_file.read_text())
    assert "https://source/2" in saved["urls"]
