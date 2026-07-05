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

# Recent published titles for internal linking context
_RECENT_TITLES_CACHE = []


def set_recent_titles(titles):
    """Set recent post titles so the prompt can suggest related reads."""
    global _RECENT_TITLES_CACHE
    _RECENT_TITLES_CACHE = titles[-10:] if titles else []


def assign_categories(title, content):
    text = (title + " " + content).lower()
    matched = []
    for keyword, cat_id in config["categories_map"].items():
        if keyword.lower() in text:
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


def generate_post(source_title, source_content, source_url):
    recent_links = ""
    if _RECENT_TITLES_CACHE:
        recent_items = _RECENT_TITLES_CACHE[-3:]
        recent_links = "\nRecent articles on the same site (for reference, suggest as related reads):\n"
        for rt in recent_items:
            slug = rt.lower().replace(" ", "-").replace("—", "").replace("'", "")[:60]
            recent_links += f"- {rt}\n"

    prompt = f"""You are an experienced travel journalist writing for {SITE_NAME}, a site focused on ETIAS and European travel regulations. Your readers are travelers from around the world planning trips to Europe.

Write a complete, original, in-depth blog post IN ENGLISH based on the source article below. The post must read naturally, like a real person wrote it — conversational but authoritative, never robotic.

IMPORTANT: Do NOT write about the source article itself or point out mismatches. You MUST write an article relevant to ETIAS and European travel. If the source seems unrelated, use it as loose inspiration for a general European travel topic.

STRICT RULES:
- Write 1,200-1,500 words of body content — be comprehensive and cover subtopics
- Output format:
  Line 1: TITLE: followed by the SEO title (under 60 characters, include main keyword naturally)
  Line 2: META: followed by a 150-160 character meta description
  Line 3: blank
  Line 4+: article body
- Structure the body with 5-7 sections, each introduced by an <h2> tag
- Write in flowing paragraphs under each subheading — no bullet lists, no numbered lists unless comparing options
- Tone: warm, clear, trustworthy — like advice from a knowledgeable friend
- Naturally include these SEO keywords where they fit: ETIAS, Schengen area, European travel, visa-free travel, travel authorization
- Open with a strong first paragraph that hooks the reader and states what changed and why it matters
- Close with a practical takeaway paragraph for travelers
- At the very end, add this exact line as a separate paragraph:
  <p><em>Article by {AUTHOR_NAME} — updated {TODAY}. Always verify current requirements on official EU channels before traveling.</em></p>
- Then add a "Related reading" section with an <h2>Related Articles on {SITE_NAME}</h2> and mention up to 2 related topics the reader might find useful (as plain text suggestions like "Check our guide on [topic]" or "Read more about [topic]")
- Never mention the source website or the source article
- Never use markdown symbols like #, **, or * anywhere
- Never write meta-commentary ("the source doesn't match", "I cannot write about this topic", "the instructions say") — just write the article
{recent_links}
SOURCE TITLE: {source_title}
SOURCE CONTENT:
{source_content[:4000]}

Write the post now:"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()
    lines = response_text.split("\n")
    title = ""
    meta_desc = ""
    body_lines = []
    mode = "header"

    for line in lines:
        if mode == "header":
            if line.startswith("TITLE:") and not title:
                title = line.replace("TITLE:", "").strip()
            elif line.startswith("META:") and not meta_desc:
                meta_desc = line.replace("META:", "").strip()
            elif line.strip() == "":
                mode = "body"
            else:
                mode = "body"
                body_lines.append(line)
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    if not title:
        title = "ETIAS Update"

    # Sanity: if title is a URL, reject it
    if re.match(r"^https?://", title):
        print(f"  ⚠ Título inválido (es una URL): {title[:60]}...")
        return None

    # Auto-generate meta description if Claude didn't provide one
    if not meta_desc or len(meta_desc) < 50:
        meta_desc = generate_meta_description(title, body)
        print(f"  ℹ Meta description auto-generada ({len(meta_desc)} chars)")

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
    categories = assign_categories(title, body)

    return {
        "title": title,
        "content": html_body,
        "meta_description": meta_desc,
        "categories": categories,
    }
