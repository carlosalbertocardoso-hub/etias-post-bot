import logging
import requests
import os
import time
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

logger = logging.getLogger(__name__)

# .strip(): a GH Actions secret pasted with a trailing newline broke Anthropic
# auth silently once already (see agent.py's ANTHROPIC_API_KEY handling) --
# apply the same defensive strip here so the same copy-paste mistake against
# WP_APP_PASSWORD can't reintroduce a silent 401.
WP_URL = (os.getenv("WP_URL") or "").strip().rstrip("/")
WP_USER = (os.getenv("WP_USER") or "").strip()
WP_APP_PASSWORD = (os.getenv("WP_APP_PASSWORD") or "").strip()

HEADERS = {"User-Agent": "Mozilla/5.0"}


def _make_session():
    session = requests.Session()
    retry = Retry(
        total=2, backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = _make_session()


def upload_image(image_url, alt_text=""):
    try:
        r = SESSION.get(image_url, timeout=10, headers=HEADERS)
    except requests.exceptions.RequestException as e:
        logger.warning("Error de red descargando imagen fuente %s: %s", image_url, e)
        return None
    if r.status_code != 200:
        logger.warning("Imagen fuente devolvió status %s: %s", r.status_code, image_url)
        return None

    content_type = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    ext = content_type.split("/")[-1]
    if ext not in ("jpeg", "jpg", "png", "webp"):
        ext = "jpg"
    filename = f"etias-{int(time.time())}.{ext}"

    try:
        media_response = SESSION.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": content_type,
            },
            data=r.content,
            auth=(WP_USER, WP_APP_PASSWORD),
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        logger.warning("Error de red subiendo imagen a WordPress: %s", e)
        return None

    if media_response.status_code not in (200, 201):
        logger.warning("Error subiendo imagen: %s - %s", media_response.status_code, media_response.text[:300])
        return None

    try:
        media_id = media_response.json()["id"]
    except (ValueError, KeyError) as e:
        logger.warning("Respuesta de WordPress al subir imagen sin 'id' (%s): %s", e, media_response.text[:300])
        return None

    if alt_text:
        try:
            SESSION.post(
                f"{WP_URL}/wp-json/wp/v2/media/{media_id}",
                json={"alt_text": alt_text},
                auth=(WP_USER, WP_APP_PASSWORD),
                timeout=15,
            )
        except requests.exceptions.RequestException as e:
            # Non-fatal: the media upload itself succeeded, only the alt-text
            # follow-up failed -- keep the image rather than discard it.
            logger.warning("Error de red asignando alt text a media %s: %s", media_id, e)

    logger.info("Imagen subida: ID %s", media_id)
    return media_id


def publish_post(title, content, categories, image_url=None, status="draft", meta_description=None):
    featured_media_id = None
    if image_url:
        featured_media_id = upload_image(image_url, alt_text=title)

    endpoint = f"{WP_URL}/wp-json/wp/v2/posts"
    payload = {
        "title": title,
        "content": content,
        "status": status,
        "categories": categories,
    }
    if featured_media_id:
        payload["featured_media"] = featured_media_id

    # Set meta_description via Rank Math custom field
    if meta_description:
        payload["meta"] = {
            "rank_math_description": meta_description,
        }

    try:
        response = SESSION.post(
            endpoint,
            json=payload,
            auth=(WP_USER, WP_APP_PASSWORD),
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        logger.warning("Error de red al publicar: %s", e)
        return None

    if response.status_code not in (200, 201):
        logger.warning("Error al publicar: %s - %s", response.status_code, response.text[:300])
        return None

    try:
        post = response.json()
        post_id = post["id"]
    except (ValueError, KeyError) as e:
        # WP returned 200/201 but with an unexpected body shape -- distinct
        # failure mode from a network error, must not be reported as one
        # (scheduler.py used to catch this under "Error de red publicando",
        # which is simply false and hides the real cause from logs).
        logger.error("WordPress respondió %s pero sin 'id' válido (%s): %s", response.status_code, e, response.text[:300])
        return None

    logger.info("Post creado: '%s' ID %s (%s)", title, post_id, status)
    if meta_description:
        logger.info("  Meta description: %s...", meta_description[:80])
    return {"id": post_id, "link": post.get("link")}
