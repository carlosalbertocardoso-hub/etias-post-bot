import os
import requests
import sys

WP_URL = os.environ.get("WP_URL", "https://etiaseuropa.eu")
WP_USER = os.environ.get("WP_USER")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
POST_ID = 1425

if not WP_USER or not WP_APP_PASSWORD:
    print("ERROR: WP_USER and WP_APP_PASSWORD must be set")
    sys.exit(1)

# Trash the corrupt post
resp = requests.post(
    f"{WP_URL}/wp-json/wp/v2/posts/{POST_ID}",
    json={"status": "trash"},
    auth=(WP_USER, WP_APP_PASSWORD),
    timeout=15,
)

if resp.status_code in (200, 201):
    data = resp.json()
    print(f"Post {POST_ID} movido a trash: '{data.get('title', {}).get('rendered', '')}'")
else:
    print(f"Error al trastear post: {resp.status_code} - {resp.text[:300]}")
    sys.exit(1)
