import json

import scheduler
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
