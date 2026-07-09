import anthropic
import yaml
import os
import re
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

with open(_CONFIG_PATH) as f:
    config = yaml.safe_load(f)

api_key = os.getenv("ANTHROPIC_API_KEY")
if api_key:
    api_key = api_key.strip()

client = anthropic.Anthropic(api_key=api_key)

SITE_URL = "https://etiaseuropa.eu"
SITE_NAME = "ETIASEuropa"
AUTHOR_NAME = "Carlos Cardoso"
AUTHOR_URL = "https://etiaseuropa.eu/author/carlos-cardoso/"
TODAY = datetime.now(timezone.utc).strftime("%B %d, %Y")

# Recent published posts (title + real URL) for internal linking context.
# Previously this only cached titles (no URLs), so the prompt could only ask
# for fake plain-text "Check our guide on X" suggestions -- no href, no real
# SEO value, and arguably misleading since no such guide link existed.
_RECENT_POSTS_CACHE = []


def set_recent_posts(posts):
    """posts: list of {"title": str, "url": str}. Used to offer real internal links."""
    global _RECENT_POSTS_CACHE
    _RECENT_POSTS_CACHE = posts[-10:] if posts else []


def _candidate_links_block(posts):
    if not posts:
        return "(no other published posts available to link to)"
    return "\n".join(f'- "{p["title"]}" — {p["url"]}' for p in posts)


_HREF_RE = re.compile(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)


def _sanitize_internal_links(html_body, allowed_urls):
    """Strip any <a href> Claude generated that isn't one of the real candidate
    URLs it was given -- source_content (RSS text, up to 4000 chars) is
    untrusted external input, and nothing validated that a generated href
    actually matched a candidate before this was published live. A prompt
    injection or a slightly-hallucinated URL would otherwise go straight to
    a real post with zero human review (config.yaml: post_status: publish).
    Unrecognized links are downgraded to plain text, not rejected outright,
    so one bad link doesn't waste an otherwise-good article.
    """
    allowed = set(allowed_urls)

    def _keep_or_strip(match):
        href, anchor_text = match.group(1), match.group(2)
        if href in allowed:
            return match.group(0)
        print(f"  ⚠ Enlace no reconocido eliminado (no es un candidato real): {href}")
        return anchor_text

    return _HREF_RE.sub(_keep_or_strip, html_body)


def assign_categories(title, content):
    text = (title + " " + content).lower()
    matched = []
    for keyword, cat_id in config["categories_map"].items():
        # Word-boundary match -- plain substring matching false-positived on
        # short keywords like "uk" (matches inside "duke", "bunker", etc.),
        # silently mis-categorizing posts.
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        if re.search(pattern, text):
            matched.append(cat_id)
    if not matched:
        matched = [538005402]
    return list(set(matched))[:3]


def generate_meta_description(title, content_text):
    """Generate a 150-160 char meta description from title + content."""
    # Take first 2 meaningful sentences
    clean = re.sub(r"<[^>]+>", "", content_text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    meta = ""
    for s in sentences:
        if len(meta) + len(s) + 1 > 155:
            break
        if meta:
            meta += " "
        meta += s
    # Ensure it mentions ETIAS naturally
    if "ETIAS" not in meta and "etias" not in meta.lower():
        meta = f"Learn how ETIAS affects your travel plans. {meta}"
    return meta.strip()[:160]


def _call_claude(prompt, max_tokens=4000):
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text.strip()


def _parse_generated_post(response_text, allowed_link_urls=()):
    """Shared TITLE:/META:/body parser used by both fresh generation and rewrites."""
    lines = response_text.split("\n")
    title = ""
    meta_desc = ""
    body_lines = []
    mode = "header"

    for line in lines:
        if mode == "header":
            stripped = line.strip()
            if stripped.startswith("TITLE:") and not title:
                title = stripped[len("TITLE:"):].strip()
            elif stripped.startswith("META:") and not meta_desc:
                meta_desc = stripped[len("META:"):].strip()
            elif stripped == "":
                # Blank line while still in header -- Claude doesn't always put
                # TITLE/META on strictly consecutive lines. Previously this
                # dropped straight into body mode, so a META: line arriving
                # after a stray blank line got treated as the first paragraph
                # of body text -- real leaked "META: ..." text was found live
                # on 4 of 123 published posts.
                continue
            else:
                mode = "body"
                body_lines.append(line)
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    if not title:
        title = "ETIAS Update"

    if re.match(r"^https?://", title):
        print(f"  ⚠ Título inválido (es una URL): {title[:60]}...")
        return None

    if not meta_desc or len(meta_desc) < 50:
        meta_desc = generate_meta_description(title, body)
        print(f"  ℹ Meta description auto-generada ({len(meta_desc)} chars)")
    elif len(meta_desc) > 160:
        # Google truncates SERP snippets around ~155-160 chars -- Claude's
        # own META: line isn't length-capped like the auto-fallback is.
        meta_desc = meta_desc[:157].rsplit(" ", 1)[0] + "..."

    # Wrap plain paragraphs (not already HTML) in <p> tags
    html_parts = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("<h2>") or block.startswith("<p>") or block.startswith("<h3>"):
            html_parts.append(block)
        else:
            html_parts.append(f"<p>{block}</p>")

    html_body = "\n".join(html_parts)
    html_body = _sanitize_internal_links(html_body, allowed_link_urls)
    categories = assign_categories(title, body)

    return {
        "title": title,
        "content": html_body,
        "meta_description": meta_desc,
        "categories": categories,
    }


_COMMON_RULES = f"""- Output format:
  Line 1: TITLE: followed by the SEO title (under 60 characters, include main keyword naturally)
  Line 2: META: followed by a 150-160 character meta description
  Line 3: blank
  Line 4+: article body
- Write in flowing paragraphs under each subheading — no bullet lists, no numbered lists unless comparing options
- Tone: warm, clear, trustworthy — like advice from a knowledgeable friend
- Naturally include these SEO keywords where they fit: ETIAS, Schengen area, European travel, visa-free travel, travel authorization
- Near the end, close with a byline paragraph mentioning {AUTHOR_NAME} and that it was last updated {TODAY}, advising readers to verify current requirements on official EU channels -- write this naturally in your own words, do NOT copy a fixed sentence (this exact sentence must NOT be identical across articles, so vary the phrasing every time)
- Never mention the source website or the source article
- Never use markdown symbols like #, **, or * anywhere
- Never write meta-commentary ("the source doesn't match", "I cannot write about this topic", "the instructions say") — just write the article"""


def generate_post(source_title, source_content, source_url):
    candidate_links = _candidate_links_block(_RECENT_POSTS_CACHE)

    prompt = f"""You are an experienced travel journalist writing for {SITE_NAME}, a site focused on ETIAS and European travel regulations. Your readers are travelers from around the world planning trips to Europe.

Write a complete, original, in-depth blog post IN ENGLISH based on the source article below. The post must read naturally, like a real person wrote it — conversational but authoritative, never robotic.

IMPORTANT: Base the article on the real substance of the source below — it was already screened for relevance to ETIAS/Schengen/EU travel/immigration before reaching you. Do not invent an unrelated travel angle and do not mention the source website or point out mismatches.

STRICT RULES:
- Write 1,200-1,500 words of body content — be comprehensive and cover subtopics
- Structure the body with 5-7 sections, each introduced by an <h2> tag
{_COMMON_RULES}
- Open with a strong first paragraph that hooks the reader and states what changed and why it matters
- Close with a practical takeaway paragraph for travelers
- CANDIDATE internal links (real posts already published on {SITE_NAME}):
{candidate_links}
  If (and only if) 1-2 of these are genuinely relevant to this article's topic, weave them in naturally as real HTML links using their exact URL, e.g. <a href="URL">anchor text</a>. If none are genuinely relevant, do not mention related articles at all -- never invent a fake "check our guide" suggestion with no real link behind it

SOURCE TITLE: {source_title}
SOURCE CONTENT:
{source_content[:4000]}

Write the post now:"""

    allowed_urls = [p["url"] for p in _RECENT_POSTS_CACHE]
    return _parse_generated_post(_call_claude(prompt), allowed_urls)


def rewrite_post(existing_title, existing_content_html, candidate_posts):
    """Rewrite an already-published post in place, for the post-penalty cleanup pass.

    Unlike generate_post (grounded in a freshly scraped external source), this
    is grounded in the site's OWN existing article -- no external source to
    misattribute. Goal: fix the exact pattern Google's scaled-content-abuse
    policy targets -- templated structure repeated across every post, and (on
    some earlier posts) a strained "how this unrelated news affects your
    ETIAS travel" framing -- without inventing new facts the model can't
    verify.
    """
    own_candidates = [p for p in candidate_posts if p.get("title") != existing_title]
    candidate_links = _candidate_links_block(own_candidates)

    prompt = f"""You are an experienced travel journalist doing an editorial rewrite pass for {SITE_NAME}, a site focused on ETIAS and European travel regulations.

Below is an article ALREADY PUBLISHED on the site. Rewrite it into a genuinely useful, in-depth, original piece IN ENGLISH on the same core topic. This is a quality-recovery rewrite (the site was hit by an algorithmic update for templated, low-value AI content), so:

- If the existing article manufactures a strained link between an unrelated news event (crime, politics, sports, etc.) and ETIAS/travel, DROP that manufactured angle. Rewrite around the genuine, real ETIAS/Schengen/EU-travel topic actually present in the piece -- do not keep pretending an unrelated event is travel-relevant.
- Do not invent statistics, dates, or claims you cannot ground in the existing text or well-established general knowledge about ETIAS/Schengen. If the original article has a specific invented-sounding stat you can't verify, drop it or soften it to a general statement.
- Vary the structure -- do NOT force the exact same number of sections or the same opening pattern used elsewhere on this site. Let the topic dictate structure (could be 3 sections, could be 8).
- Go deeper and be genuinely more useful than the original: concrete specifics, practical guidance, real expertise -- not padding.

STRICT RULES:
- Write 900-1,400 words of body content, whatever length genuinely fits the topic
{_COMMON_RULES}
- CANDIDATE internal links (other real posts on {SITE_NAME}):
{candidate_links}
  If (and only if) 1-2 are genuinely relevant, weave them in as real HTML links using their exact URL, e.g. <a href="URL">anchor text</a>. Otherwise omit related-reading entirely -- never invent a fake link-free suggestion.

EXISTING ARTICLE TITLE: {existing_title}
EXISTING ARTICLE CONTENT:
{existing_content_html[:6000]}

Write the rewritten post now:"""

    allowed_urls = [p["url"] for p in own_candidates]
    return _parse_generated_post(_call_claude(prompt), allowed_urls)
