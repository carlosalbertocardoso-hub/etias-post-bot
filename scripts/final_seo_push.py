#!/usr/bin/env python3
"""
ETIASEuropa Final SEO Push — applies all remaining WP-side fixes:
1. Installs schema code into child theme functions.php (via theme editor API)
2. Publishes the pillar article as a page
3. Adds breadcrumb nav to site
4. Adds internal links to old posts
"""
import os, requests, json, sys, time, re

WP_URL = os.environ.get("WP_URL", "https://etiaseuropa.eu")
WP_USER = os.environ.get("WP_USER")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
AUTH = (WP_USER, WP_APP_PASSWORD)
H = {"User-Agent": "Mozilla/5.0"}
TODAY = time.strftime("%B %d, %Y")

if not WP_USER or not WP_APP_PASSWORD:
    print("FATAL: credentials missing")
    sys.exit(1)

success = []
fail = []

def ok(msg):
    success.append(msg); print(f"  ✅ {msg}")

def no(msg):
    fail.append(msg); print(f"  ❌ {msg}")

def api(method, ep, data=None):
    url = f"{WP_URL}/wp-json/wp/v2/{ep}"
    r = getattr(requests, method)(url, auth=AUTH, headers=H, json=data, timeout=20)
    return r

# ===== 1. Inject schema into child theme functions.php =====
print("\n--- 1. Child Theme Schema Injection ---")
# Try WP theme file editor endpoint
schema_code = r"""<?php
/**
 * ETIASEuropa SEO Schema — injected by upgrade script
 */
add_action('wp_head', function() {
    $schema = [
        '@context' => 'https://schema.org',
        '@graph'   => [
            [
                '@type' => 'Organization',
                '@id'   => home_url('/#organization'),
                'name'  => 'ETIASEuropa',
                'url'   => home_url(),
                'description' => 'Independent guide to the European Travel Information and Authorization System (ETIAS).',
            ],
            [
                '@type' => 'WebSite',
                '@id'   => home_url('/#website'),
                'url'   => home_url(),
                'name'  => 'ETIASEuropa',
                'publisher' => ['@id' => home_url('/#organization')],
            ],
        ],
    ];
    if (!is_front_page()) {
        $schema['@graph'][] = [
            '@type' => 'BreadcrumbList',
            '@id' => home_url('/#breadcrumb'),
            'itemListElement' => [
                ['@type' => 'ListItem', 'position' => 1, 'name' => 'Home', 'item' => home_url()],
                ['@type' => 'ListItem', 'position' => 2, 'name' => get_the_title(), 'item' => get_permalink()],
            ],
        ];
    }
    echo '<script type="application/ld+json">' . wp_json_encode($schema, JSON_UNESCAPED_SLASHES) . '</script>' . "\n";
    if (is_single()) {
        global $post;
        $article = [
            '@context' => 'https://schema.org',
            '@type' => 'Article',
            'headline' => get_the_title(),
            'datePublished' => get_the_date('c'),
            'dateModified' => get_the_modified_date('c'),
            'author' => ['@type' => 'Person', 'name' => get_the_author_meta('display_name') ?: 'Carlos Cardoso'],
            'publisher' => ['@id' => home_url('/#organization')],
        ];
        if (has_post_thumbnail()) {
            $article['image'] = get_the_post_thumbnail_url();
        }
        echo '<script type="application/ld+json">' . wp_json_encode($article, JSON_UNESCAPED_SLASHES) . '</script>' . "\n";
    }
    if (is_page('faq')) {
        $faqs = [
            ['q' => 'What is ETIAS?', 'a' => 'ETIAS (European Travel Information and Authorization System) is an electronic system that allows visa-exempt travelers to visit the Schengen Area for short stays.'],
            ['q' => 'When will ETIAS be implemented?', 'a' => 'ETIAS is expected to be fully operational by Q4 2026.'],
            ['q' => 'Is ETIAS a visa?', 'a' => 'No, ETIAS is a travel authorization, not a visa.'],
            ['q' => 'How long is ETIAS valid?', 'a' => 'ETIAS is valid for three years or until the passport expires, whichever comes first.'],
            ['q' => 'Do children need ETIAS?', 'a' => 'Yes, every traveler including minors must have an individual ETIAS authorization.'],
        ];
        $items = [];
        foreach ($faqs as $f) {
            $items[] = ['@type' => 'Question', 'name' => $f['q'], 'acceptedAnswer' => ['@type' => 'Answer', 'text' => $f['a']]];
        }
        echo '<script type="application/ld+json">' . wp_json_encode(['@context' => 'https://schema.org', '@type' => 'FAQPage', 'mainEntity' => $items], JSON_UNESCAPED_SLASHES) . '</script>' . "\n";
    }
});

// Last Updated on posts
add_filter('the_content', function($content) {
    if (is_single() && in_the_loop() && is_main_query()) {
        $mod = get_the_modified_date('F j, Y');
        $content .= '<p style="font-size:0.85em;color:#666;margin-top:2em;border-top:1px solid #eee;padding-top:1em;">📅 <strong>Last updated:</strong> ' . $mod . '</p>';
    }
    return $content;
});

// Author bio box
add_filter('the_content', function($content) {
    if (is_single() && in_the_loop() && is_main_query()) {
        $name = get_the_author_meta('display_name') ?: 'Carlos Cardoso';
        $desc = get_the_author_meta('description') ?: 'Travel and immigration writer at ETIASEuropa, helping travelers navigate European entry requirements.';
        $avatar = get_avatar_url(get_the_author_meta('ID'), ['size' => 80]);
        $bio = '<div style="display:flex;gap:1em;padding:1.5em;background:#f8f9fa;border-radius:8px;margin-top:2em;">';
        if ($avatar) $bio .= '<img src="' . esc_url($avatar) . '" alt="' . esc_attr($name) . '" style="width:80px;height:80px;border-radius:50%;" loading="lazy" />';
        $bio .= '<div><strong>' . esc_html($name) . '</strong><p style="margin:0.5em 0 0;font-size:0.9em;color:#555;">' . esc_html($desc) . '</p></div></div>';
        $content .= $bio;
    }
    return $content;
});

// Related posts
add_filter('the_content', function($content) {
    if (is_single() && in_the_loop() && is_main_query()) {
        $related = get_posts(['category__in' => wp_get_post_categories(get_the_ID()), 'post__not_in' => [get_the_ID()], 'posts_per_page' => 3, 'orderby' => 'rand']);
        if ($related) {
            $html = '<div style="margin-top:2em;padding:1.5em;background:#f0f4f8;border-radius:8px;"><h3 style="margin-top:0;">📖 Related Articles</h3><ul>';
            foreach ($related as $rp) $html .= '<li><a href="' . get_permalink($rp->ID) . '">' . get_the_title($rp->ID) . '</a></li>';
            $html .= '</ul></div>';
            $content .= $html;
        }
    }
    return $content;
});
"""

# Try theme edit API
try:
    r = api("put", f"themes/etiaseuropa-child?file=functions.php&content={requests.utils.quote(schema_code)}")
    if r.status_code in (200, 201):
        ok("Schema code injected into child theme functions.php")
    else:
        # Fallback: try the WordPress.com theme editor
        no(f"Theme edit API failed ({r.status_code}), trying alternative...")
        # Some WordPress.com sites use a different endpoint
        r2 = requests.post(
            f"{WP_URL}/wp-json/wpcom/v2/theme/etiaseuropa-child/functions.php",
            auth=AUTH, json={"content": schema_code}, timeout=20
        )
        if r2.status_code in (200, 201):
            ok("Schema injected via wpcom API")
        else:
            no(f"Could not inject schema via API. Install manually.")
except Exception as e:
    no(f"Schema injection error: {e}")

# ===== 2. Create breadcrumb nav visual =====
print("\n--- 2. Visual Breadcrumbs ---")
# Try adding breadcrumbs via Rank Math's built-in breadcrumb shortcode in the theme
try:
    # Many themes support breadcrumb position via filter
    r = api("get", "settings")
    if r.status_code == 200:
        ok("Site settings accessible")
        
    # Add breadcrumb support via filter in existing Rank Math settings
    r = api("post", "settings", {
        "rank_math_breadcrumb_show_home": True,
        "rank_math_breadcrumb_separator": " / ",
        "rank_math_breadcrumb_home_label": "Home",
    })
    if r.status_code in (200, 201):
        ok("Breadcrumb settings configured in Rank Math")
    else:
        no(f"Breadcrumb config returned {r.status_code}")
except Exception as e:
    no(f"Breadcrumb error: {e}")

# ===== 3. Publish pillar article as page =====
print("\n--- 3. Publishing Pillar Article ---")
pillar_title = "ETIAS 2026: The Complete Guide to Europe's New Travel Authorization System"
pillar_content = """<p>ETIAS is launching in Q4 2026, and it will change how millions of travelers enter Europe. If you're from a visa-exempt country like the United States, Canada, the United Kingdom, or Australia, you'll need this travel authorization before boarding your flight to the Schengen Area.</p>
<p>This is the most comprehensive guide available. We cover everything: what ETIAS is, who needs it, the application process, costs, validity, special cases, and how it differs from a visa.</p>
<h2>What Is ETIAS?</h2>
<p>ETIAS stands for the European Travel Information and Authorization System. It is an electronic system designed to pre-screen travelers from visa-exempt countries before they enter the Schengen Area.</p>
<p>Think of it as similar to the US ESTA or the UK ETA — it is not a visa, but a travel authorization that you apply for online before your trip.</p>
<h2>When Does ETIAS Launch?</h2>
<p>ETIAS is scheduled to launch in Q4 2026. This date has been confirmed by the European Union after several delays. The system was originally planned for 2023, then 2024, and then 2025, but technical complexities and the parallel rollout of the Entry/Exit System (EES) pushed the timeline.</p>
<p><strong>Important:</strong> ETIAS is not yet operational. Any website claiming you can apply for ETIAS today is misleading.</p>
<h2>Who Needs ETIAS?</h2>
<p>ETIAS is required for citizens of visa-exempt countries visiting the Schengen Area for short stays (up to 90 days within any 180-day period). This includes travelers from the United States, Canada, UK, Australia, Japan, South Korea, Brazil, and over 60 other countries.</p>
<h2>How to Apply for ETIAS</h2>
<ol>
<li>Complete the online form with personal details, passport info, and travel plans</li>
<li>Pay the ~€7 processing fee</li>
<li>Submit — most approved within minutes</li>
<li>ETIAS is electronically linked to your passport</li>
</ol>
<h2>ETIAS vs Visa: Key Differences</h2>
<p>ETIAS is NOT a visa. It is cheaper (~€7 vs €80+), faster (minutes vs weeks), and requires no embassy visit or biometrics. Unlike a visa, it does not guarantee entry — border authorities make the final decision.</p>
<h2>ETIAS and EES: How They Work Together</h2>
<p>The Entry/Exit System (EES) tracks your entries and exits, replacing passport stamping. ETIAS pre-screens you before travel. Together, they create a complete EU border management system launching in Q4 2026.</p>
<h2>How to Prepare Now</h2>
<p>Check your passport validity (needs 3+ months beyond your trip), monitor the official EU site, and bookmark this guide. Once ETIAS launches, apply well before your trip.</p>
<p><em>Article by Carlos Cardoso — updated """ + TODAY + """. Always verify current requirements on official EU channels before traveling.</em></p>"""

try:
    r = api("post", "pages", {
        "title": pillar_title,
        "content": pillar_content,
        "status": "publish",
        "meta": {"rank_math_description": "Everything you need to know about ETIAS 2026 — who needs it, how to apply, costs, validity, and how it affects your travel to Europe. Complete guide for US, UK, Canadian, and Australian travelers."}
    })
    if r.status_code in (200, 201):
        page_id = r.json().get("id")
        ok(f"Pillar article published as page (ID: {page_id})")
    else:
        no(f"Pillar publish failed: {r.status_code} - {r.text[:200]}")
except Exception as e:
    no(f"Pillar publish error: {e}")

# ===== 4. Add internal links to 10 most recent posts =====
print("\n--- 4. Internal Links to Recent Posts ---")
try:
    r = api("get", "posts?per_page=20&_fields=id,title,content,link")
    if r.status_code == 200:
        posts = r.json()
        pillar_link = f'<p>For a complete overview, read our <a href="{WP_URL}/etias-2026-complete-guide/">ETIAS 2026 Complete Guide</a>.</p>'
        linked = 0
        for post in posts:
            content = post["content"]["rendered"]
            # Skip if already has internal link to pillar
            if "ETIAS 2026 Complete Guide" in content:
                continue
            new_content = content + pillar_link
            r2 = api("post", f"posts/{post['id']}", {"content": new_content})
            if r2.status_code in (200, 201):
                linked += 1
        ok(f"Internal pillar link added to {linked} posts")
    else:
        no(f"Could not fetch posts for internal linking")
except Exception as e:
    no(f"Internal link error: {e}")

# ===== SUMMARY =====
print("\n" + "=" * 50)
print(f"RESULTS: {len(success)} OK, {len(fail)} FAIL")
for s in success: print(f"  ✅ {s}")
for f in fail: print(f"  ❌ {f}")
if fail:
    print("\n⚠️ Some items need manual attention")
    sys.exit(1)
else:
    print("\n✅ ALL COMPLETE")
