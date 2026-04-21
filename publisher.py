import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()

WP_URL = os.getenv("WP_URL")
WP_USER = os.getenv("WP_USER")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

HEADERS = {"User-Agent": "Mozilla/5.0"}


def upload_image(image_url, alt_text=""):
    try:
        r = requests.get(image_url, timeout=10, headers=HEADERS)
        if r.status_code != 200:
            return None

        content_type = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        ext = content_type.split("/")[-1]
        if ext not in ("jpeg", "jpg", "png", "webp"):
            ext = "jpg"
        filename = f"etias-{int(time.time())}.{ext}"

        media_response = requests.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": content_type,
            },
            data=r.content,
            auth=(WP_USER, WP_APP_PASSWORD),
        )

        if media_response.status_code in [200, 201]:
            media = media_response.json()
            media_id = media["id"]
            if alt_text:
                requests.post(
                    f"{WP_URL}/wp-json/wp/v2/media/{media_id}",
                    json={"alt_text": alt_text},
                    auth=(WP_USER, WP_APP_PASSWORD),
                )
            print(f"Imagen subida: ID {media_id}")
            return media_id
        else:
            print(f"Error subiendo imagen: {media_response.status_code}")
            return None
    except Exception as e:
        print(f"Error subiendo imagen: {e}")
        return None


def publish_post(title, content, categories, image_url=None, status="draft"):
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

    response = requests.post(
        endpoint,
        json=payload,
        auth=(WP_USER, WP_APP_PASSWORD),
    )

    if response.status_code in [200, 201]:
        post = response.json()
        print(f"Post creado: '{title}' ID {post['id']} ({status})")
        return post["id"]
    else:
        print(f"Error al publicar: {response.status_code} - {response.text}")
        return None
