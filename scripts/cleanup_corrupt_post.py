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

# Move to trash via DELETE
resp = requests.delete(
    f"{WP_URL}/wp-json/wp/v2/posts/{POST_ID}",
    auth=(WP_USER, WP_APP_PASSWORD),
    timeout=15,
)

if resp.status_code in (200, 201):
    data = resp.json()
    print(f"Post {POST_ID} movido a trash: '{data.get('title', {}).get('rendered', '')[:80]}'")
elif resp.status_code == 410:
    print(f"Post {POST_ID} ya estaba en trash (410 Gone)")
else:
    print(f"Error: {resp.status_code} - {resp.text[:300]}")
    sys.exit(1)
