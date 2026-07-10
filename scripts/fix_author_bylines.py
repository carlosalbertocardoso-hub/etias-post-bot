"""
One-off maintenance tool: replace the fabricated-author byline paragraph on
already-published WordPress posts.

Context: every post here is 100% AI-generated with zero human editorial
review before publish. Before the 2026-07-10 audit, the closing byline
paragraph attributed each post to "Carlos Cardoso" (the real name of the
site's owner) with invented framing ("a travel and immigration policy
specialist... for over a decade", "last reviewed") -- a real person credited
with expertise/review that never happened. agent.py was fixed to stop doing
this for NEW posts (AUTHOR_NAME = "the ETIASEuropa Editorial Team", no
review/credential claims). This script fixes the ~100 posts already live.

Only the byline paragraph is touched -- the rest of the article is left
alone, unlike scripts/rewrite_published_posts.py which does a full rewrite.

Usage:
  python scripts/fix_author_bylines.py --dry-run              # preview only, no writes
  python scripts/fix_author_bylines.py --post-id 1480         # fix just one post (test)
  python scripts/fix_author_bylines.py --limit 5              # fix first 5
  python scripts/fix_author_bylines.py                        # fix ALL published posts that mention "Carlos Cardoso"
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from dotenv import load_dotenv

load_dotenv()

from agent import _call_claude

WP_URL = (os.getenv("WP_URL") or "").strip().rstrip("/")
WP_USER = (os.getenv("WP_USER") or "").strip()
WP_APP_PASSWORD = (os.getenv("WP_APP_PASSWORD") or "").strip()
AUTH = (WP_USER, WP_APP_PASSWORD)
SLEEP_BETWEEN_POSTS = 2

_PARA_RE = re.compile(r"<p>(.*?)</p>", re.IGNORECASE | re.DOTALL)


def fetch_all_published_posts():
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
            break
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for p in batch:
            posts.append({"id": p["id"], "title": p["title"]["raw"], "content": p["content"]["raw"]})
        page += 1
    return posts


def find_byline_paragraph(content):
    """Return (start, end, text) of the <p> paragraph mentioning Carlos Cardoso, or None."""
    for m in _PARA_RE.finditer(content):
        if "Carlos Cardoso" in m.group(1):
            return m.start(), m.end(), m.group(0)
    return None


def rewrite_byline(old_paragraph_html):
    prompt = f"""Rewrite this single closing paragraph from a travel/immigration article. It currently attributes the article to a named individual ("Carlos Cardoso") with invented professional framing. This site publishes 100% AI-generated content with NO human editorial review before publishing.

Rewrite it to:
- Attribute the article to "the ETIASEuropa Editorial Team" instead of any individual's name
- Preserve the "last updated [DATE]" fact if one is present in the original (keep the same date, don't invent a new one)
- NOT claim the piece was "reviewed," "fact-checked," or "verified" by anyone -- there is no human review step, that would be false
- NOT invent any job title, professional credential, years of experience, or personal biography
- Keep any genuine practical advice (e.g. "verify current requirements on official EU channels") -- that part is fine to keep
- Be a single natural paragraph, plain HTML <p>...</p>, similar length to the original

ORIGINAL PARAGRAPH:
{old_paragraph_html}

Rewritten paragraph (output ONLY the <p>...</p> HTML, nothing else):"""
    result = _call_claude(prompt, max_tokens=300).strip()
    # Defensive: ensure it's wrapped in <p> even if the model forgot.
    if not result.startswith("<p>"):
        result = f"<p>{result}</p>"
    return result


def update_post_content(post_id, new_content):
    resp = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        json={"content": new_content},
        auth=AUTH,
        timeout=30,
    )
    return resp.status_code in (200, 201), resp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print before/after, never write to WordPress")
    parser.add_argument("--post-id", type=int, help="Fix only this post ID")
    parser.add_argument("--limit", type=int, help="Fix at most N posts")
    args = parser.parse_args()

    print("Descargando posts publicados...")
    all_posts = fetch_all_published_posts()
    print(f"  {len(all_posts)} posts publicados encontrados.")

    targets = all_posts
    if args.post_id:
        targets = [p for p in targets if p["id"] == args.post_id]
    if args.limit:
        targets = targets[: args.limit]

    fixed, skipped, failed = 0, 0, 0
    for post in targets:
        match = find_byline_paragraph(post["content"])
        if not match:
            skipped += 1
            continue

        start, end, old_paragraph = match
        print(f"\n=== ID {post['id']}: {post['title']}")
        print(f"  ANTES: {old_paragraph}")

        new_paragraph = rewrite_byline(old_paragraph)
        print(f"  DESPUES: {new_paragraph}")

        if args.dry_run:
            continue

        new_content = post["content"][:start] + new_paragraph + post["content"][end:]
        ok, resp = update_post_content(post["id"], new_content)
        if ok:
            print(f"  Actualizado OK (ID {post['id']})")
            fixed += 1
        else:
            print(f"  ERROR actualizando ID {post['id']}: {resp.status_code} - {resp.text[:200]}")
            failed += 1
        time.sleep(SLEEP_BETWEEN_POSTS)

    print(f"\n=== Resumen: {fixed} actualizados, {skipped} sin byline detectado, {failed} fallidos (de {len(targets)} evaluados) ===")


if __name__ == "__main__":
    main()
