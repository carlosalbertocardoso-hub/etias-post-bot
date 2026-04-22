import anthropic
import yaml
import os
from dotenv import load_dotenv

load_dotenv()

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

with open(_CONFIG_PATH) as f:
    config = yaml.safe_load(f)

api_key = os.getenv("ANTHROPIC_API_KEY")
if api_key:
    api_key = api_key.strip()

client = anthropic.Anthropic(api_key=api_key)


def assign_categories(title, content):
    text = (title + " " + content).lower()
    matched = []
    for keyword, cat_id in config["categories_map"].items():
        if keyword.lower() in text:
            matched.append(cat_id)
    if not matched:
        matched = [538005402]
    return list(set(matched))[:3]


def generate_post(source_title, source_content, source_url):
    prompt = f"""You are an experienced travel journalist writing for etiaseuropa.eu, a site focused on ETIAS and European travel regulations. Your readers are travelers from around the world planning trips to Europe.

Write a complete, original blog post IN ENGLISH based on the source article below. The post must read naturally, like a real person wrote it — conversational but authoritative, never robotic.

STRICT RULES:
- Write 500-650 words of body content
- Output format: first line is TITLE: followed by the SEO title, then a blank line, then the article body
- The title must include the main keyword naturally and be under 60 characters
- Structure the body with 4-5 sections, each introduced by a short subheading wrapped in <h2> tags (never use # symbols)
- Write in flowing paragraphs under each subheading — no bullet lists, no numbered lists
- Tone: warm, clear, trustworthy — like advice from a knowledgeable friend
- Naturally include these SEO keywords where they fit: ETIAS, Schengen area, European travel, visa-free travel
- Open with a strong first paragraph that hooks the reader and states what changed and why it matters
- Close with a practical takeaway paragraph for travelers
- Never mention the source website
- Never use markdown symbols like #, **, or * anywhere

SOURCE TITLE: {source_title}
SOURCE CONTENT:
{source_content[:3000]}

Write the post now:"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()
    lines = response_text.split("\n")
    title = ""
    body_lines = []

    for line in lines:
        if line.startswith("TITLE:") and not title:
            title = line.replace("TITLE:", "").strip()
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    if not title:
        title = source_title.strip() or "ETIAS Update"

    # Wrap plain paragraphs (not already HTML) in <p> tags
    html_parts = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("<h2>") or block.startswith("<p>"):
            html_parts.append(block)
        else:
            html_parts.append(f"<p>{block}</p>")

    html_body = "\n".join(html_parts)
    categories = assign_categories(title, body)

    return {"title": title, "content": html_body, "categories": categories}
