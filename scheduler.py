import os
import schedule
import time
import yaml
import re
from scraper import get_new_articles, fetch_article_content, load_posted, save_posted, load_post_links
from agent import generate_post, set_recent_posts
from publisher import publish_post

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

with open(_CONFIG_PATH) as f:
    config = yaml.safe_load(f)


def is_valid_post_title(title):
    """Check that title is a real text title, not a URL or empty."""
    if not title or len(title) < 10:
        return False
    if re.match(r"^https?://", title):
        return False
    return True


def _skip(article, reason):
    print(f"  ⛔ {reason}, saltando.")
    posted_urls, posted_titles = load_posted()
    posted_urls.add(article["url"])
    save_posted(posted_urls, posted_titles)


META_PHRASES = [
    "the source doesn't match",
    "i cannot write",
    "the instructions",
    "the source article you've provided",
    "there's a significant mismatch",
    "you've shared is from",
    "material you've provided",
]


def _try_publish_article(article):
    """Attempt one candidate end to end. Returns True on a successful publish."""
    print(f"Procesando: {article['title']}")
    print(f"  URL: {article['url']}")

    source_data = fetch_article_content(article["url"])

    if not source_data.get("valid"):
        _skip(article, "Artículo inválido (no se pudo extraer contenido de la fuente)")
        return False

    if not source_data.get("content") or len(source_data["content"]) < 100:
        _skip(article, f"Contenido extraído demasiado corto ({len(source_data.get('content', ''))} chars)")
        return False

    if not is_valid_post_title(source_data["title"]):
        _skip(article, "Título fuente inválido")
        return False

    print("  Generando post con Claude Haiku...")
    set_recent_posts(load_post_links())

    try:
        post_data = generate_post(
            source_data["title"],
            source_data["content"],
            source_data["url"]
        )
    except Exception as e:
        # Anthropic call can throw (rate limit, timeout, transient API error) --
        # an uncaught exception here used to crash the whole job and leave the
        # remaining candidates untried for the day.
        print(f"  ⚠ Error llamando a Claude: {e}")
        return False

    if post_data is None:
        _skip(article, "Claude no generó un post válido")
        return False

    if not is_valid_post_title(post_data["title"]):
        _skip(article, f"El título generado no es válido: '{post_data['title'][:60]}'")
        return False

    content_lower = (post_data.get("content") or "").lower()
    for phrase in META_PHRASES:
        if phrase in content_lower:
            _skip(article, f"Contenido generado contiene meta-comentario ('{phrase}')")
            return False

    print(f"  Publicando: '{post_data['title']}'...")
    try:
        result = publish_post(
            title=post_data["title"],
            content=post_data["content"],
            categories=post_data["categories"],
            image_url=source_data.get("image_url"),
            status=config["post_status"],
            meta_description=post_data.get("meta_description"),
        )
    except Exception as e:
        print(f"  ⚠ Error de red publicando en WordPress: {e}")
        return False

    if not result:
        print("  ⛔ Error al publicar en WordPress")
        return False

    posted_urls, posted_titles = load_posted()
    posted_urls.add(article["url"])
    posted_titles.append(post_data["title"])
    post_links = load_post_links()
    if result.get("link"):
        post_links.append({"title": post_data["title"], "url": result["link"]})
    save_posted(posted_urls, posted_titles, post_links=post_links)
    print(f"  ✅ Post publicado correctamente (ID: {result['id']})")
    return True


def run_daily_job():
    print("=== ETIAS Bot - Iniciando ejecución diaria ===")
    print("Buscando artículos nuevos en etias.com y fuentes RSS...")
    new_articles = get_new_articles(config["source_url"])

    if not new_articles:
        print("No hay artículos nuevos hoy.")
        return

    # Try candidates in order until one publishes successfully -- previously
    # only new_articles[0] was ever attempted, so a single bad candidate (dead
    # link, thin content, Claude hiccup) meant zero posts for the whole day
    # even when other valid candidates were sitting right behind it.
    for article in new_articles:
        if _try_publish_article(article):
            break
    else:
        print("  Ningún candidato de hoy pudo publicarse.")

    print("=== ETIAS Bot - Ejecución completada ===")


if __name__ == "__main__":
    print(f"Agente iniciado. Publicara 1 borrador/dia a las {config['schedule_time']}")
    run_daily_job()
    schedule.every().day.at(config["schedule_time"]).do(run_daily_job)
    while True:
        schedule.run_pending()
        time.sleep(60)
