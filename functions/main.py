import os
import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore

# Inicializar firebase_admin una sola vez (las Cloud Functions reutilizan instancias)
if not firebase_admin._apps:
    firebase_admin.initialize_app()

from scraper import get_new_articles, fetch_article_content, load_posted, save_posted
from agent import generate_post
from publisher import publish_post


@functions_framework.http
def run_bot(request):
    """
    HTTP Cloud Function (1st gen) que:
    1. Obtiene artículos nuevos no procesados
    2. Toma el primero, genera un post con Claude Haiku
    3. Lo publica en WordPress
    4. Guarda la URL en Firestore para no reprocesarla
    """
    print("=== Bot ETIAS iniciado ===")

    # 1. Obtener artículos nuevos
    try:
        new_articles = get_new_articles()
    except Exception as e:
        msg = f"Error en scraping: {e}"
        print(msg)
        return (msg, 500)

    if not new_articles:
        msg = "No hay artículos nuevos. Nada que hacer."
        print(msg)
        return (msg, 200)

    print(f"Artículos nuevos encontrados: {len(new_articles)}")

    # 2. Tomar solo el primero para esta ejecución
    article = new_articles[0]
    url = article["url"]
    print(f"Procesando: {url}")

    # 3. Obtener contenido completo del artículo
    try:
        article_data = fetch_article_content(url)
    except Exception as e:
        msg = f"Error al obtener contenido de {url}: {e}"
        print(msg)
        return (msg, 500)

    source_title = article_data.get("title") or article.get("title", "")
    source_content = article_data.get("content", "")
    image_url = article_data.get("image_url")

    if not source_content:
        msg = f"Contenido vacío para {url}, saltando."
        print(msg)
        return (msg, 200)

    # 4. Generar post con Claude
    try:
        post_data = generate_post(source_title, source_content, url)
    except Exception as e:
        msg = f"Error al generar post con Claude: {e}"
        print(msg)
        return (msg, 500)

    title = post_data["title"]
    content = post_data["content"]
    categories = post_data["categories"]

    # 5. Determinar status desde variable de entorno (por defecto "draft" para seguridad)
    post_status = os.getenv("POST_STATUS", "draft")

    # 6. Publicar en WordPress
    try:
        post_id = publish_post(
            title=title,
            content=content,
            categories=categories,
            image_url=image_url,
            status=post_status,
        )
    except Exception as e:
        msg = f"Error al publicar en WordPress: {e}"
        print(msg)
        return (msg, 500)

    if post_id is None:
        msg = "WordPress rechazó el post (ver logs de publisher)."
        print(msg)
        return (msg, 500)

    # 7. Guardar URL procesada en Firestore para no repetirla
    try:
        posted = load_posted()
        posted_set = set(posted)
        posted_set.add(url)
        save_posted(list(posted_set))
        print(f"URL guardada en estado: {url}")
    except Exception as e:
        # No es fatal: el post ya se publicó; solo logueamos el error
        print(f"Advertencia: no se pudo guardar el estado ({e})")

    msg = f"OK: post '{title}' publicado con ID {post_id} (status={post_status})"
    print(f"=== {msg} ===")
    return (msg, 200)
