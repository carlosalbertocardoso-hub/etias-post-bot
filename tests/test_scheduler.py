from scheduler import is_valid_post_title


def test_valid_title_accepted():
    assert is_valid_post_title("ETIAS and the Schengen Area Explained")


def test_url_rejected():
    assert not is_valid_post_title("https://example.com/some-article")


def test_empty_rejected():
    assert not is_valid_post_title("")


def test_too_short_rejected():
    assert not is_valid_post_title("ETIAS")
