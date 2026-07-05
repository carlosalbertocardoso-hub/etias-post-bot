#!/usr/bin/env python3
import os, requests, json, sys, time, re

W = os.getenv("WP_URL", "https://etiaseuropa.eu")
U = os.getenv("WP_USER")
P = os.getenv("WP_APP_PASSWORD")
K = os.getenv("ANTHROPIC_API_KEY")
A = (U, P)
H = {"User-Agent": "Mozilla/5.0"}
T = time.strftime("%B %d, %Y")

ok = 0; bad = 0
def y(m): global ok; ok+=1; print(f"  ✅ {m}")
def n(m): global bad; bad+=1; print(f"  ❌ {m}")

if not U or not P: print("FATAL: missing credentials"); sys.exit(1)

def api(m, e, d=None):
    r = getattr(requests, m)(f"{W}/wp-json/wp/v2/{e}", auth=A, headers=H, json=d, timeout=25)
    return r

# === 1. Country pages ===
print("\n=== Country Pages ===")
pages = [
    ("etias-for-american-citizens", "ETIAS for US Citizens: Complete 2026 Guide",
     "Complete ETIAS guide for American travelers. Requirements, application, costs.",
     "<p>US citizens need ETIAS from Q4 2026. Apply online in 10 minutes. Valid 3 years.</p><h2>Do US Citizens Need ETIAS?</h2><p>Yes.</p><h2>How to Apply</h2><p>Online form, ~7 EUR fee. Most approved in minutes.</p>"),
    ("etias-for-british-citizens", "ETIAS for UK Citizens: Complete 2026 Guide",
     "ETIAS guide for British citizens post-Brexit. Requirements and application.",
     "<p>UK citizens need ETIAS from Q4 2026. Apply online. Valid 3 years.</p><h2>Do UK Citizens Need ETIAS?</h2><p>Yes.</p>"),
    ("etias-for-canadian-citizens", "ETIAS for Canadian Citizens: Complete 2026 Guide",
     "ETIAS for Canadian travelers. Requirements and application process.",
     "<p>Canadian citizens need ETIAS from Q4 2026.</p>"),
    ("etias-for-australian-citizens", "ETIAS for Australian Citizens: Complete 2026 Guide",
     "ETIAS for Australian travelers. Requirements and application.",
     "<p>Australian citizens need ETIAS from Q4 2026.</p>"),
]
for slug, title, meta, content in pages:
    r = api("get", f"pages?slug={slug}")
    if r.json(): y(f"'{slug}' exists"); continue
    r = api("post", "pages", {"title": title, "content": content, "status": "publish", "slug": slug, "meta": {"rank_math_description": meta}})
    y(f"Created {slug}") if r.status_code in (200,201) else n(f"Fail {slug}: {r.status_code}")

# === 2. Rewrite 10 oldest posts ===
print("\n=== Rewrite Old Posts ===")
if not K: n("No API key, skipping")
else:
    r = api("get", "posts?per_page=10&order=asc&orderby=date&_fields=id,title,date")
    if r.status_code == 200:
        for p in r.json():
            pid = p["id"]; t = p["title"]["rendered"]
            print(f"  {t[:50]}...")
            prompt = f"Rewrite this blog post to 1,200-1,500 words. Use <h2> sections. Title on first line after TITLE:. {t}"
            try:
                r2 = requests.post("https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": K, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]}, timeout=60)
                if r2.status_code == 200:
                    text = r2.json()["content"][0]["text"].strip()
                    lines = text.split("\n"); nt = ""; body = []
                    for l in lines:
                        if l.startswith("TITLE:") and not nt: nt = l[6:].strip()
                        elif l.strip(): body.append(l)
                    html = "\n".join(f"<p>{b}</p>" if not b.startswith("<") else b for b in "\n".join(body).split("\n\n") if b.strip())
                    payload = {"content": html}
                    if nt and len(nt)>10 and not nt.startswith("http"): payload["title"] = nt
                    r3 = api("post", f"posts/{pid}", payload)
                    y(f"Done: {nt or t[:40]}") if r3.status_code in(200,201) else n(f"Update fail {pid}")
                else: n(f"API error {pid}")
            except Exception as e: n(f"Error {pid}: {e}")
            time.sleep(2)
    else: n(f"Fetch fail")

print(f"\nRESULTS: {ok} OK, {bad} FAIL")
sys.exit(1 if bad else 0)
