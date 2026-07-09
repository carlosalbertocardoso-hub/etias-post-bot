from scraper import _is_duplicate_topic, _is_relevant


def test_is_relevant_true_for_etias_topic():
    assert _is_relevant("ETIAS delays hit summer travelers")


def test_is_relevant_true_for_schengen_topic():
    assert _is_relevant("Schengen area adds new member state")


def test_is_relevant_false_for_unrelated_news():
    assert not _is_relevant("Far-right leader Bardella says police raided contractors")


def test_is_relevant_false_for_generic_politics():
    assert not _is_relevant("Poll: Americans say they're sick of politics")


def test_duplicate_topic_detects_near_identical_titles():
    posted = ["Poland's Foreign Workers Hit Record High: What It Means for European Travel"]
    assert _is_duplicate_topic(
        "Poland's Foreign Workers Surge: What It Means for European Travel", posted
    )


def test_duplicate_topic_ignores_unrelated_titles():
    posted = ["ETIAS and the Schengen Area: Understanding Europe's New Travel System"]
    assert not _is_duplicate_topic("EU Blue Card 2026: Who Qualifies and How to Apply", posted)
