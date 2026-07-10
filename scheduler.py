import json
import logging
import os
import schedule
import time
import yaml
import re
from datetime import datetime, timezone
from scraper import (
    get_new_articles, fetch_article_content, load_posted, save_posted,
    load_post_links, _is_duplicate_topic,
)
from agent import generate_post, set_recent_posts
from publisher import publish_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
_HEARTBEAT_PATH = os.path.join(os.path.dirname(__file__), "last_run.json")

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
    logger.info("%s, saltando: %s", reason, article["url"])
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
    logger.info("Procesando: %s", article["title"])
    logger.info("  URL: %s", article["url"])

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

    logger.info("  Generando post con Claude Haiku...")
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
        # remaining candidates untried for the day. _call_claude() now retries
        # transient errors itself; this catch is the last-resort backstop.
        logger.warning("Error llamando a Claude: %s", e)
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

    # get_new_articles() only dedupes the *source* headline against past
    # generated titles -- two source articles worded differently enough to
    # pass that filter can still make Claude converge on nearly the same
    # blog title/angle for the same underlying event (confirmed live: post
    # 1269/1274 "ETIAS for Sea Travel...", 1 day apart; 1185/1379 "EES and
    # Border Delays...", 2 months apart -- see audit 2026-07-10). Re-check
    # the actual generated title, which is what really collides, before
    # publishing it.
    _, posted_titles = load_posted()
    if _is_duplicate_topic(post_data["title"], posted_titles):
        _skip(article, f"Título generado duplica tema ya publicado: '{post_data['title'][:60]}'")
        return False

    logger.info("  Publicando: '%s'...", post_data["title"])
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
        # publish_post() already catches requests.exceptions.RequestException
        # internally and returns None -- this is a true last-resort backstop,
        # not the expected path, so treat it as an error, not a network log line.
        logger.error("Error inesperado publicando en WordPress: %s", e)
        return False

    if not result:
        logger.warning("Error al publicar en WordPress (ver logs de publisher.py arriba)")
        return False

    posted_urls, posted_titles = load_posted()
    posted_urls.add(article["url"])
    posted_titles.append(post_data["title"])
    post_links = load_post_links()
    if result.get("link"):
        post_links.append({"title": post_data["title"], "url": result["link"]})
    save_posted(posted_urls, posted_titles, post_links=post_links)
    logger.info("Post publicado correctamente (ID: %s)", result["id"])
    return True


def _write_heartbeat(outcome, detail=""):
    """Always touch last_run.json so the daily workflow always has a diff to
    commit -- even on a 'no new articles today' day. Without this, a run of
    empty-candidate days in a row produces zero commits, and GitHub disables
    scheduled workflows after 60 days with no repository activity (see
    audit 2026-07-10). This also gives us a queryable history of outcomes
    distinct from "did a post happen", which run_daily_job's return value
    alone didn't provide to the workflow layer before.
    """
    with open(_HEARTBEAT_PATH, "w") as f:
        json.dump({
            "last_run_utc": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome,
            "detail": detail,
        }, f, indent=2)


def run_daily_job():
    """Returns one of: 'published', 'no_candidates', 'all_failed'.

    Distinguishing these (instead of just returning/printing) lets CI-level
    alerting (see .github/workflows/run_bot.yml) tell a real "nothing new to
    publish today" apart from "every candidate failed" -- previously both
    looked identical (job exits 0, nothing published) from the outside.
    """
    logger.info("=== ETIAS Bot - Iniciando ejecución diaria ===")
    logger.info("Buscando artículos nuevos en etias.com y fuentes RSS...")
    new_articles = get_new_articles(config["source_url"])

    if not new_articles:
        logger.info("No hay artículos nuevos hoy.")
        _write_heartbeat("no_candidates")
        return "no_candidates"

    # Try candidates in order until one publishes successfully -- previously
    # only new_articles[0] was ever attempted, so a single bad candidate (dead
    # link, thin content, Claude hiccup) meant zero posts for the whole day
    # even when other valid candidates were sitting right behind it.
    outcome = "all_failed"
    for article in new_articles:
        if _try_publish_article(article):
            outcome = "published"
            break
    else:
        logger.warning("Ningún candidato de hoy pudo publicarse (%d intentados).", len(new_articles))

    _write_heartbeat(outcome, detail=f"{len(new_articles)} candidatos evaluados")
    logger.info("=== ETIAS Bot - Ejecución completada (%s) ===", outcome)
    return outcome


if __name__ == "__main__":
    logger.info("Agente iniciado. Publicara 1 borrador/dia a las %s", config["schedule_time"])
    outcome = run_daily_job()
    if outcome == "all_failed":
        # Non-zero exit on a real failure (as opposed to "no candidates",
        # which is a normal day) so CI can flag it distinctly if desired.
        import sys
        sys.exit(1)
    schedule.every().day.at(config["schedule_time"]).do(run_daily_job)
    while True:
        schedule.run_pending()
        time.sleep(60)
