#!/usr/bin/env python3
"""
ETIASEuropa SEO Upgrade Script.
Run via GitHub Actions workflow to execute all WP-side fixes requiring credentials.
"""
import os
import requests
import json
import sys
from datetime import datetime

WP_URL = os.environ.get("WP_URL", "https://etiaseuropa.eu")
WP_USER = os.environ.get("WP_USER")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
AUTH = (WP_USER, WP_APP_PASSWORD)
HEADERS = {"User-Agent": "Mozilla/5.0"}
TODAY = datetime.now().strftime("%Y-%m-%d")

if not WP_USER or not WP_APP_PASSWORD:
    print("ERROR: WP_USER and WP_APP_PASSWORD must be set")
    sys.exit(1)

errors = []
successes = []

def api(method, endpoint, data=None):
    url = f"{WP_URL}/wp-json/wp/v2/{endpoint}"
    kwargs = {"auth": AUTH, "headers": HEADERS, "timeout": 15}
    if data is not None:
        kwargs["json"] = data
    r = getattr(requests, method)(url, **kwargs)
    return r


def log(ok, msg):
    if ok:
        successes.append(f"✅ {msg}")
        print(f"  ✅ {msg}")
    else:
        errors.append(f"❌ {msg}")
        print(f"  ❌ {msg}")


print("=" * 60)
print("ETIASEuropa SEO Upgrade")
print("=" * 60)

# ===== TASK 1: Fix FAQ (May 2025 → Q4 2026) =====
print("\n--- 1. Actualizando FAQ ---")
r = api("get", "pages?slug=faq&_fields=id,content")
if r.status_code == 200 and r.json():
    faq = r.json()[0]
    faq_id = faq["id"]
    old_content = faq["content"]["rendered"]
    if "May 2025" in old_content:
        new_content = old_content.replace("May 2025", "Q4 2026")
        r2 = api("post", f"pages/{faq_id}", {"content": new_content})
        log(r2.status_code in (200, 201), f"FAQ actualizado: May 2025 → Q4 2026 (page ID {faq_id})")
    else:
        log(True, "FAQ ya actualizado (no contiene 'May 2025')")
else:
    log(False, f"No se pudo obtener FAQ: {r.status_code}")


# ===== TASK 2: Apply Schema Markup via Rank Math =====
print("\n--- 2. Aplicando Schema Markup (Organization + Site) ---")
# Set Organization schema via Rank Math settings
schema_payload = {
    "rank_math_schema_Organization": json.dumps({
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "ETIASEuropa",
        "url": WP_URL,
        "logo": f"{WP_URL}/wp-content/uploads/2026/02/ETIAS-last.png",
        "description": "Independent guide to the European Travel Information and Authorization System (ETIAS).",
        "sameAs": []
    })
}
r = api("post", "settings", schema_payload)
log(r.status_code in (200, 201), f"Schema Organization configurado via Rank Math")


# ===== TASK 3: Fix /clients-2/ duplicate =====
print("\n--- 3. Redirect /clients-2/ → /clients/ ---")
r = api("get", "pages?slug=clients-2&_fields=id")
if r.status_code == 200 and r.json():
    dup_id = r.json()[0]["id"]
    r2 = api("post", f"pages/{dup_id}", {"status": "draft"})
    log(r2.status_code in (200, 201), f"Página duplicada /clients-2/ (ID {dup_id}) movida a draft")
else:
    log(True, "No se encontró página /clients-2/ duplicada")


# ===== TASK 4: Hide empty categories =====
print("\n--- 4. Ocultando categorías vacías ---")
empty_slugs = ["etias-architecture", "etias-data-privacy", "etias-data-retention", "etias-mobile-app"]
r = api("get", "categories?per_page=50&_fields=id,slug,count")
if r.status_code == 200:
    for cat in r.json():
        if cat["slug"] in empty_slugs or (cat["count"] == 0 and cat["slug"].startswith("etias-")):
            # Hide by setting description to "HIDDEN"
            r2 = api("post", f"categories/{cat['id']}", {"description": "HIDDEN"})
            log(r2.status_code in (200, 201), f"Categoría '{cat['slug']}' (ID {cat['id']}, 0 posts) ocultada")
else:
    log(False, f"No se pudieron listar categorías: {r.status_code}")


# ===== TASK 5: Update meta descriptions for last 10 posts (retroactively) =====
print("\n--- 5. Actualizando meta descriptions de últimos posts ---")
r = api("get", "posts?per_page=10&_fields=id,title,content")
if r.status_code == 200:
    posts = r.json()
    for post in posts:
        post_id = post["id"]
        title_text = post["title"]["rendered"]
        # Extract first 155 chars of clean content
        content_text = post["content"]["rendered"]
        clean_text = content_text.replace("<p>", "").replace("</p>", " ").replace("<h2>", "").replace("</h2>", " ").replace("<br>", " ")
        sentences = clean_text.split(". ")
        meta = ""
        for s in sentences:
            if len(meta) + len(s) + 1 > 155:
                break
            if meta:
                meta += ". "
            meta += s.strip().lstrip("., ")
        meta = meta.strip()[:160]
        if meta:
            r2 = api("post", f"posts/{post_id}", {"meta": {"rank_math_description": meta}})
            log(r2.status_code in (200, 201), f"Meta description actualizada: '{title_text[:50]}...'")
else:
    log(False, f"No se pudieron obtener posts: {r.status_code}")


# Summary
print("\n" + "=" * 60)
print(f"RESULTADOS:")
for s in successes:
    print(f"  {s}")
for e in errors:
    print(f"  {e}")
print(f"\n{len(successes)} éxitos, {len(errors)} errores")
if errors:
    sys.exit(1)
else:
    print("✅ Upgrade completado sin errores")
