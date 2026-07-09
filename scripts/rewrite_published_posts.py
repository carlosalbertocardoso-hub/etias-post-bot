"""
One-off maintenance tool: rewrite already-published WordPress posts.

Context: the daily bot force-fit unrelated news (crime, politics) into fake
ETIAS "inspiration" angles and repeated an identical template across every
post -- the exact pattern Google's scaled-content-abuse policy targets. Real
traffic loss was confirmed. This script re-runs each live post through
agent.rewrite_post() (grounded in the post's own existing content, not a new
external source) to de-templatize it and drop any manufactured angle.

Usage:
  python scripts/rewrite_published_posts.py --dry-run              # preview only, no writes
  python scripts/rewrite_published_posts.py --post-id 1480         # rewrite just one post (test)
  python scripts/rewrite_published_posts.py --limit 5              # rewrite first 5
  python scripts/rewrite_published_posts.py                        # rewrite ALL published posts
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from dotenv import load_dotenv

load_dotenv()

from agent import rewrite_post

WP_URL = os.getenv("WP_URL")
WP_USER = os.getenv("WP_USER")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
AUTH = (WP_USER, WP_APP_PASSWORD)
SLEEP_BETWEEN_POSTS = 3  # be gentle with the WP + Anthropic APIs


def fetch_all_published_posts():
    """Fetch id, title, content (raw, needs edit context) and link for every published post."""
    posts = []
    page = 1
    while True:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/posts",
            params={"status": "publish", "per_page": 100, "page": page, "context": "edit"},
            auth=AUTH,
            timeout=30,
        )
        if resp.status_code == 400 and page > 1:
            break  # WP returns 400 "invalid page number" past the last page
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for p in batch:
            posts.append({
                "id": p["id"],
                "title": p["title"]["raw"],
                "content": p["content"]["raw"],
                "link": p["link"],
            })
        page += 1
    return posts


def update_post(post_id, title, content, meta_description, categories):
    payload = {"title": title, "content": content, "categories": categories}
    if meta_description:
        payload["meta"] = {"rank_math_description": meta_description}
    resp = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        json=payload,
        auth=AUTH,
        timeout=30,
    )
    return resp.status_code in (200, 201), resp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Generate and print, but never write to WordPress")
    parser.add_argument("--post-id", type=int, help="Rewrite only this post ID")
    parser.add_argument("--limit", type=int, help="Rewrite at most N posts")
    parser.add_argument("--skip", type=int, default=0, help="Skip the first N posts (already rewritten in a prior run)")
    parser.add_argument("--exclude-ids", type=str, help="Comma-separated post IDs to skip regardless of position")
    args = parser.parse_args()

    print("Descargando posts publicados...")
    all_posts = fetch_all_published_posts()
    print(f"  {len(all_posts)} posts publicados encontrados.")

    candidates = [{"title": p["title"], "url": p["link"]} for p in all_posts]

    targets = all_posts
    if args.exclude_ids:
        excluded = {int(x) for x in args.exclude_ids.split(",")}
        targets = [p for p in targets if p["id"] not in excluded]
    if args.skip:
        targets = targets[args.skip:]
    if args.post_id:
        targets = [p for p in all_posts if p["id"] == args.post_id]
        if not targets:
            print(f"⛔ No se encontró post con ID {args.post_id}")
            return
    if args.limit:
        targets = targets[: args.limit]

    print(f"Reescribiendo {len(targets)} post(s){' (DRY RUN, sin escribir)' if args.dry_run else ''}...\n")

    ok, failed = 0, 0
    for i, post in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] ID {post['id']}: {post['title']}")
        own_candidates = [c for c in candidates if c["url"] != post["link"]]
        try:
            rewritten = rewrite_post(post["title"], post["content"], own_candidates)
        except Exception as e:
            print(f"  ⚠ Error generando reescritura: {e}")
            failed += 1
            continue

        if rewritten is None:
            print("  ⛔ Claude no devolvió un post válido, se deja el original intacto.")
            failed += 1
            continue

        print(f"  Nuevo título: {rewritten['title']}")
        print(f"  Palabras: ~{len(rewritten['content'].split())}")

        if args.dry_run:
            print("  (dry-run: no se escribió en WordPress)\n")
            ok += 1
            continue

        success, resp = update_post(
            post["id"], rewritten["title"], rewritten["content"],
            rewritten.get("meta_description"), rewritten["categories"],
        )
        if success:
            print(f"  ✅ Actualizado en WordPress (ID {post['id']})\n")
            ok += 1
        else:
            print(f"  ⛔ Error al actualizar: {resp.status_code} - {resp.text[:200]}\n")
            failed += 1

        time.sleep(SLEEP_BETWEEN_POSTS)

    print(f"=== Terminado: {ok} ok, {failed} fallidos, {len(targets)} total ===")


if __name__ == "__main__":
    main()
