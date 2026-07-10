import requests

import publisher


class _FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = {}
        self.content = b""

    def json(self):
        if self._json_data is None:
            raise ValueError("no JSON object could be decoded")
        return self._json_data


def test_publish_post_success(monkeypatch):
    monkeypatch.setattr(
        publisher.SESSION, "post",
        lambda *a, **kw: _FakeResponse(201, {"id": 42, "link": "https://etiaseuropa.eu/p/42"}),
    )
    result = publisher.publish_post("Title", "<p>body</p>", categories=[1])
    assert result == {"id": 42, "link": "https://etiaseuropa.eu/p/42"}


def test_publish_post_non_2xx_returns_none(monkeypatch):
    monkeypatch.setattr(publisher.SESSION, "post", lambda *a, **kw: _FakeResponse(500, text="server error"))
    assert publisher.publish_post("Title", "<p>body</p>", categories=[1]) is None


def test_publish_post_malformed_2xx_body_does_not_crash(monkeypatch):
    # Regression: WP returning 201 with an unexpected body used to raise an
    # uncaught KeyError/ValueError from outside publish_post's old try/except
    # boundary, which scheduler.py then mislabeled as a network error.
    monkeypatch.setattr(publisher.SESSION, "post", lambda *a, **kw: _FakeResponse(201, json_data=None, text="not json"))
    assert publisher.publish_post("Title", "<p>body</p>", categories=[1]) is None


def test_publish_post_2xx_missing_id_does_not_crash(monkeypatch):
    monkeypatch.setattr(publisher.SESSION, "post", lambda *a, **kw: _FakeResponse(201, {"link": "https://x"}))
    assert publisher.publish_post("Title", "<p>body</p>", categories=[1]) is None


def test_publish_post_network_error_returns_none(monkeypatch):
    def _raise(*a, **kw):
        raise requests.exceptions.ConnectionError("boom")
    monkeypatch.setattr(publisher.SESSION, "post", _raise)
    assert publisher.publish_post("Title", "<p>body</p>", categories=[1]) is None


def test_upload_image_download_failure_returns_none(monkeypatch):
    monkeypatch.setattr(publisher.SESSION, "get", lambda *a, **kw: _FakeResponse(404))
    assert publisher.upload_image("https://example.invalid/img.jpg") is None


def test_upload_image_success(monkeypatch):
    def _fake_get(*a, **kw):
        r = _FakeResponse(200)
        r.headers = {"Content-Type": "image/jpeg"}
        r.content = b"fake-bytes"
        return r

    monkeypatch.setattr(publisher.SESSION, "get", _fake_get)
    monkeypatch.setattr(publisher.SESSION, "post", lambda *a, **kw: _FakeResponse(201, {"id": 7}))
    assert publisher.upload_image("https://example.invalid/img.jpg", alt_text="alt") == 7


def test_upload_image_media_upload_missing_id_does_not_crash(monkeypatch):
    def _fake_get(*a, **kw):
        r = _FakeResponse(200)
        r.headers = {"Content-Type": "image/jpeg"}
        r.content = b"fake-bytes"
        return r

    monkeypatch.setattr(publisher.SESSION, "get", _fake_get)
    monkeypatch.setattr(publisher.SESSION, "post", lambda *a, **kw: _FakeResponse(201, {}))
    assert publisher.upload_image("https://example.invalid/img.jpg") is None
