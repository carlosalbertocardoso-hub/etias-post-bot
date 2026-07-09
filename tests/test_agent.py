from agent import assign_categories, _parse_generated_post, _sanitize_internal_links


def test_assign_categories_matches_whole_word():
    cats = assign_categories("ETIAS news", "content about the uk border checks")
    assert 8199 in cats  # "uk" category


def test_assign_categories_does_not_match_substring_inside_word():
    # "duke" contains the substring "uk" but is not about the UK.
    cats = assign_categories("A Duke's guide to European castles", "no relevant keywords here")
    assert 8199 not in cats


def test_assign_categories_falls_back_when_no_keyword_matches():
    cats = assign_categories("Totally unrelated title", "totally unrelated body text")
    assert cats == [538005402]


def test_parse_handles_blank_line_between_title_and_meta():
    # Regression: a blank line here used to flip the parser into body mode
    # before the META: line was read, leaking "META: ..." as the first
    # paragraph of the published post. Found live on 4 real posts.
    response = (
        "TITLE: A Real Title\n"
        "\n"
        "META: A proper meta description that is long enough to pass the length check easily.\n"
        "\n"
        "<h2>Section</h2>\n"
        "<p>Real body content.</p>"
    )
    result = _parse_generated_post(response)
    assert result["title"] == "A Real Title"
    assert result["meta_description"].startswith("A proper meta description")
    assert "META:" not in result["content"]


def test_sanitize_internal_links_keeps_allowed_href():
    html = '<p>See our <a href="https://etiaseuropa.eu/real-post">real guide</a>.</p>'
    result = _sanitize_internal_links(html, ["https://etiaseuropa.eu/real-post"])
    assert '<a href="https://etiaseuropa.eu/real-post">' in result


def test_sanitize_internal_links_strips_hallucinated_href():
    # Nothing validated that a Claude-generated href matched a real candidate
    # before this existed -- untrusted RSS source text could inject or the
    # model could hallucinate a URL, and it would publish live either way.
    html = '<p>See our <a href="https://evil.example.com/phish">travel guide</a>.</p>'
    result = _sanitize_internal_links(html, ["https://etiaseuropa.eu/real-post"])
    assert "evil.example.com" not in result
    assert "travel guide" in result
