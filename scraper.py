import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import feedparser
import json
import os
from datetime import datetime, timezone, timedelta

POSTED_FILE = "posted_articles.json"
ETIAS_ARTICLES = "https://etias.com/articles/"
ETIAS_BASE = "https://etias.com"
MAX_AGE_DAYS = 7

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

EXTRA_RSS = [
    "https://www.schengenvisainfo.com/news/feed/",
    "https://www.euractiv.com/feed/",
    "https://visaguide.world/feed/",
    "https://www.politico.eu/feed/",
    "https://rss.dw.com/rdf/rss-en-eu",
]

# RSS sources beyond etias.com/articles cover general EU news (politics, crime,
# sports...), not just travel. Without a topical filter, the bot was turning
# unrelated stories (e.g. a politician's office being raided, a crime suspect
# sought in Monaco) into invented "how this affects your ETIAS travel" posts --
# real reputational/SEO risk (off-topic EEAT signals, borrows crime/politics
# news to manufacture fake travel angles). Only etias.com/articles is exempt
# from this filter -- it's already 100% on-topic by definition.
_RELEVANT_KEYWORDS = {
    "etias", "schengen", "visa", "border", "passport", "travel", "tourist",
    "tourism", "airport", "flight", "airline", "migration", "immigration",
    "asylum", "refugee", "frontex", "entry-exit", "eu entry", "residency",
    "residence permit", "work permit", "blue card", "digital nomad",
    "eu travel", "european travel", "eea", "customs",
}


_RELEVANT_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in _RELEVANT_KEYWORDS) + r")\b"
)


def _is_relevant(title):
    # Plain substring matching reintroduced the exact bug just fixed in
    # assign_categories() -- "visa" matched inside "improvisation"/"advisable",
    # letting unrelated crime/politics/sports headlines back through the
    # filter this function exists to enforce.
    return bool(_RELEVANT_PATTERN.search(title.lower()))


def _make_session():
    session = requests.Session()
    retry = Retry(
        total=2, backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = _make_session()

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "into", "is", "are", "was", "were",
    "be", "been", "have", "has", "had", "will", "would", "could", "should",
    "it", "its", "this", "that", "which", "new", "says", "said", "how",
    "what", "why", "when", "where", "who",
}


def _title_words(title):
    words = re.sub(r"[^\w\s]", "", title.lower()).split()
    return {w for w in words if w not in _STOP_WORDS and len(w) > 2}


def _is_duplicate_topic(title, posted_titles, threshold=0.45):
    words = _title_words(title)
    if not words:
        return False
    for pt in posted_titles:
        pt_words = _title_words(pt)
        union = words | pt_words
        if union and len(words & pt_words) / len(union) >= threshold:
            return True
    return False


def load_posted():
    """Returns (urls: set, titles: list)."""
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(data), []
        return set(data.get("urls", [])), data.get("titles", [])
    return set(), []


def load_post_links():
    """Returns list of {"title", "url"} for real internal-linking candidates.

    Kept separate from load_posted() (source URLs) -- this tracks the
    resulting WP post permalink, needed to offer real <a href> links instead
    of the old fake plain-text "check our guide on X" suggestions.
    """
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("post_links", [])
    return []


def save_posted(urls, titles, post_links=None):
    if post_links is None:
        post_links = load_post_links()
    with open(POSTED_FILE, "w") as f:
        json.dump(
            {"urls": sorted(urls), "titles": list(titles), "post_links": post_links},
            f, indent=2,
        )


def _scrape_etias_articles(posted_urls):
    try:
        response = SESSION.get(ETIAS_ARTICLES, timeout=15, headers=HEADERS)
    except Exception as e:
        print(f"  ⚠ Error al scrapear {ETIAS_ARTICLES}: {e}")
        return []
    soup = BeautifulSoup(response.text, "html.parser")

    articles = []
    seen = set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        full_url = href if href.startswith("http") else f"{ETIAS_BASE}/{href.lstrip('/')}"

        if "etias.com/articles/" not in full_url:
            continue
        if "/c/categories/" in full_url:
            continue
        if full_url in posted_urls or full_url in seen:
            continue

        title = link.get_text(strip=True)
        if title and len(title) > 10:
            seen.add(full_url)
            articles.append({"url": full_url, "title": title})

    return articles


def _scrape_rss(rss_url, posted_urls, seen):
    # feedparser (not xml.etree) -- handles malformed XML, mixed RSS/Atom/RDF
    # dialects and encoding quirks across these 5 different publishers instead
    # of silently returning [] on the first parse error.
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    articles = []
    try:
        r = SESSION.get(rss_url, timeout=15, headers=HEADERS)
        if r.status_code != 200:
            print(f"  ⚠ RSS {rss_url} devolvió status {r.status_code}")
            return []
        feed = feedparser.parse(r.content)
    except Exception as e:
        print(f"  ⚠ Error al leer RSS {rss_url}: {e}")
        return []

    for entry in feed.entries:
        title = (getattr(entry, "title", "") or "").strip()
        link = (getattr(entry, "link", "") or "").strip()

        if not link or not title or len(title) <= 10:
            continue
        if link in posted_urls or link in seen:
            continue
        if not _is_relevant(title):
            continue

        pub_parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if pub_parsed:
            pub_date = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
            if pub_date < cutoff:
                continue

        seen.add(link)
        articles.append({"url": link, "title": title})

    return articles


def get_new_articles(source_url=None):
    posted_urls, posted_titles = load_posted()
    seen = set(posted_urls)

    raw = _scrape_etias_articles(posted_urls)
    seen.update(a["url"] for a in raw)
    for rss_url in EXTRA_RSS:
        raw += _scrape_rss(rss_url, posted_urls, seen)

    # Deduplicate by topic similarity across sources
    articles = []
    seen_titles = list(posted_titles)
    for a in raw:
        if not _is_duplicate_topic(a["title"], seen_titles):
            articles.append(a)
            seen_titles.append(a["title"])

    return articles


def fetch_article_content(url):
    try:
        response = SESSION.get(url, timeout=15, headers=HEADERS)
    except Exception as e:
        print(f"  ⚠ Error al obtener {url}: {e}")
        return {"title": "", "content": "", "url": url, "image_url": None, "valid": False}
    soup = BeautifulSoup(response.text, "html.parser")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)

    # Fallback: meta og:title
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
    # Fallback: meta twitter:title
    if not title:
        tw_title = soup.find("meta", attrs={"name": "twitter:title"})
        if tw_title and tw_title.get("content"):
            title = tw_title["content"].strip()
    # Fallback: meta title tag
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
    # Extract domain for logging
    from urllib.parse import urlparse
    domain = urlparse(url).netloc

    # If still no title or title is a URL, we can't use this article
    if not title or title.startswith("http"):
        print(f"  ⚠ No se pudo extraer título de {domain}, saltando.")
        return {"title": "", "content": "", "url": url, "image_url": None, "valid": False}

    image_url = None
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        image_url = og_img["content"]
    if not image_url:
        tw_img = soup.find("meta", attrs={"name": "twitter:image"})
        if tw_img and tw_img.get("content"):
            image_url = tw_img["content"]
    if not image_url:
        article_tag = soup.find("article")
        if article_tag:
            img = article_tag.find("img", src=True)
            if img and img["src"].startswith("http"):
                image_url = img["src"]

    content = ""
    article = soup.find("article") or soup.find("div", class_=lambda x: x and "content" in x.lower())
    if article:
        paragraphs = article.find_all("p")
        content = "\n\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30)

    if not content:
        paragraphs = soup.find_all("p")
        content = "\n\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30)

    return {"title": title, "content": content, "url": url, "image_url": image_url, "valid": True}
