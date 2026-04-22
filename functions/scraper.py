import re
import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

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


def _is_cloud():
    return bool(os.getenv("K_SERVICE") or os.getenv("FUNCTION_TARGET"))


def load_posted():
    """Returns (urls: set, titles: list)."""
    if _is_cloud():
        from google.cloud import firestore
        db = firestore.Client()
        doc = db.collection("bot_state").document("posted_articles").get()
        if doc.exists:
            data = doc.to_dict()
            return set(data.get("urls", [])), data.get("titles", [])
        return set(), []
    else:
        if os.path.exists(POSTED_FILE):
            with open(POSTED_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                return set(data), []
            return set(data.get("urls", [])), data.get("titles", [])
        return set(), []


def save_posted(urls, titles):
    if _is_cloud():
        from google.cloud import firestore
        db = firestore.Client()
        db.collection("bot_state").document("posted_articles").set(
            {"urls": sorted(urls), "titles": list(titles)}
        )
    else:
        with open(POSTED_FILE, "w") as f:
            json.dump({"urls": sorted(urls), "titles": list(titles)}, f, indent=2)


def _scrape_etias_articles(posted_urls):
    try:
        response = requests.get(ETIAS_ARTICLES, timeout=15, headers=HEADERS)
    except Exception:
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
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    articles = []
    try:
        r = requests.get(rss_url, timeout=15, headers=HEADERS)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception:
        return []
    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        if title_el is None or link_el is None:
            continue
        title = (title_el.text or "").strip()
        link = (link_el.text or "").strip()
        if not link or not title or len(title) <= 10:
            continue
        if link in posted_urls or link in seen:
            continue
        if pub_el is not None and pub_el.text:
            try:
                pub_date = parsedate_to_datetime(pub_el.text.strip())
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
                if pub_date < cutoff:
                    continue
            except (TypeError, ValueError):
                pass
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

    articles = []
    seen_titles = list(posted_titles)
    for a in raw:
        if not _is_duplicate_topic(a["title"], seen_titles):
            articles.append(a)
            seen_titles.append(a["title"])

    return articles


def fetch_article_content(url):
    try:
        response = requests.get(url, timeout=15, headers=HEADERS)
    except Exception:
        return {"title": url, "content": "", "url": url, "image_url": None}
    soup = BeautifulSoup(response.text, "html.parser")
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
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
    return {"title": title or url, "content": content, "url": url, "image_url": image_url}
