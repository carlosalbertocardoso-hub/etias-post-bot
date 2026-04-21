import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET

POSTED_FILE = "posted_articles.json"
ETIAS_ARTICLES = "https://etias.com/articles/"
ETIAS_BASE = "https://etias.com"
MAX_AGE_DAYS = 7

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def _is_cloud():
    """Detecta si el código está corriendo en Firebase Cloud Functions."""
    return bool(os.getenv("K_SERVICE") or os.getenv("FUNCTION_TARGET"))


def load_posted():
    """
    Carga la lista de URLs ya procesadas.
    - En la nube: desde Firestore (colección bot_state, doc posted_articles, campo urls)
    - Local: desde el fichero JSON posted_articles.json
    """
    if _is_cloud():
        from google.cloud import firestore
        db = firestore.Client()
        doc = db.collection("bot_state").document("posted_articles").get()
        if doc.exists:
            return doc.to_dict().get("urls", [])
        return []
    else:
        if os.path.exists(POSTED_FILE):
            with open(POSTED_FILE, "r") as f:
                return json.load(f)
        return []


def save_posted(urls):
    """
    Guarda la lista de URLs procesadas.
    - En la nube: en Firestore
    - Local: en el fichero JSON
    """
    if _is_cloud():
        from google.cloud import firestore
        db = firestore.Client()
        db.collection("bot_state").document("posted_articles").set(
            {"urls": list(urls)}
        )
    else:
        with open(POSTED_FILE, "w") as f:
            json.dump(list(urls), f, indent=2)


def _scrape_etias_articles(posted):
    response = requests.get(ETIAS_ARTICLES, timeout=15, headers=HEADERS)
    soup = BeautifulSoup(response.text, "html.parser")
    articles = []
    seen = set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("http"):
            full_url = href
        else:
            full_url = f"{ETIAS_BASE}/{href.lstrip('/')}"
        if "etias.com/articles/" not in full_url:
            continue
        if "/c/categories/" in full_url:
            continue
        if full_url in posted or full_url in seen:
            continue
        title = link.get_text(strip=True)
        if title and len(title) > 10:
            seen.add(full_url)
            articles.append({"url": full_url, "title": title})
    return articles


def _scrape_rss(rss_url, posted, seen):
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    articles = []
    try:
        r = requests.get(rss_url, timeout=15, headers=HEADERS)
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
        if link in posted or link in seen:
            continue
        if pub_el is not None and pub_el.text:
            try:
                pub_date = datetime.strptime(pub_el.text.strip(), "%a, %d %b %Y %H:%M:%S %Z")
                pub_date = pub_date.replace(tzinfo=timezone.utc)
                if pub_date < cutoff:
                    continue
            except ValueError:
                continue
        seen.add(link)
        articles.append({"url": link, "title": title})
    return articles


EXTRA_RSS = ["https://www.schengenvisainfo.com/news/feed/"]


def get_new_articles(source_url=None):
    posted = set(load_posted())
    seen = set(posted)
    articles = _scrape_etias_articles(posted)
    seen.update(a["url"] for a in articles)
    for rss_url in EXTRA_RSS:
        articles += _scrape_rss(rss_url, posted, seen)
    return articles


def fetch_article_content(url):
    response = requests.get(url, timeout=15, headers=HEADERS)
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
