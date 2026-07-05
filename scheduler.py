import os
import schedule
import time
import yaml
import re
from scraper import get_new_articles, fetch_article_content, load_posted, save_posted
from agent import generate_post
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


def run_daily_job():
    print("=== ETIAS Bot - Iniciando ejecución diaria ===")
    print("Buscando artículos nuevos en etias.com y fuentes RSS...")
    new_articles = get_new_articles(config["source_url"])

    if not new_articles:
        print("No hay artículos nuevos hoy.")
        return

    article = new_articles[0]
    print(f"Procesando: {article['title']}")
    print(f"  URL: {article['url']}")

    # Fetch full content with validation
    source_data = fetch_article_content(article["url"])

    # Validate source data
    if not source_data.get("valid"):
        print(f"  ⛔ Artículo inválido (no se pudo extraer contenido de la fuente), saltando.")
        # Mark URL as posted so we don't retry it forever
        posted_urls, posted_titles = load_posted()
        posted_urls.add(article["url"])
        save_posted(posted_urls, posted_titles)
        return

    if not source_data.get("content") or len(source_data["content"]) < 100:
        print(f"  ⛔ Contenido extraído demasiado corto ({len(source_data.get('content', ''))} chars), saltando.")
        posted_urls, posted_titles = load_posted()
        posted_urls.add(article["url"])
        save_posted(posted_urls, posted_titles)
        return

    if not is_valid_post_title(source_data["title"]):
        print(f"  ⛔ Título fuente inválido, saltando.")
        posted_urls, posted_titles = load_posted()
        posted_urls.add(article["url"])
        save_posted(posted_urls, posted_titles)
        return

    # Generate post via AI
    print("  Generando post con Claude Haiku...")
    # Load recent titles for internal linking context
    _, recent_titles = load_posted()
    from agent import set_recent_titles
    set_recent_titles(recent_titles)
    
    post_data = generate_post(
        source_data["title"],
        source_data["content"],
        source_data["url"]
    )

    # Validate generated post
    if post_data is None:
        print(f"  ⛔ Claude no generó un post válido, saltando.")
        posted_urls, posted_titles = load_posted()
        posted_urls.add(article["url"])
        save_posted(posted_urls, posted_titles)
        return

    if not is_valid_post_title(post_data["title"]):
        print(f"  ⛔ El título generado no es válido: '{post_data['title'][:60]}', saltando.")
        posted_urls, posted_titles = load_posted()
        posted_urls.add(article["url"])
        save_posted(posted_urls, posted_titles)
        return

    # Check for meta-commentary in content
    meta_phrases = [
        "the source doesn't match",
        "i cannot write",
        "the instructions",
        "the source article you've provided",
        "there's a significant mismatch",
        "you've shared is from",
        "material you've provided",
    ]
    content_lower = (post_data.get("content") or "").lower()
    for phrase in meta_phrases:
        if phrase in content_lower:
            print(f"  ⛔ Contenido generado contiene meta-comentario ('{phrase}'), saltando.")
            posted_urls, posted_titles = load_posted()
            posted_urls.add(article["url"])
            save_posted(posted_urls, posted_titles)
            return

    # Publish
    print(f"  Publicando: '{post_data['title']}'...")
    post_id = publish_post(
        title=post_data["title"],
        content=post_data["content"],
        categories=post_data["categories"],
        image_url=source_data.get("image_url"),
        status=config["post_status"],
        meta_description=post_data.get("meta_description"),
    )

    if post_id:
        posted_urls, posted_titles = load_posted()
        posted_urls.add(article["url"])
        posted_titles.append(post_data["title"])
        save_posted(posted_urls, posted_titles)
        print(f"  ✅ Post publicado correctamente (ID: {post_id})")
    else:
        print(f"  ⛔ Error al publicar en WordPress")

    print("=== ETIAS Bot - Ejecución completada ===")


if __name__ == "__main__":
    print(f"Agente iniciado. Publicara 1 borrador/dia a las {config['schedule_time']}")
    run_daily_job()
    schedule.every().day.at(config["schedule_time"]).do(run_daily_job)
    while True:
        schedule.run_pending()
        time.sleep(60)
