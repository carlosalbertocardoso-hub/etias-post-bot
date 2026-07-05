<?php
/**
 * ETIASEuropa Child Theme — SEO Schema & Performance Enhancements
 * Add this to etiaseuropa-child/functions.php
 * 
 * Adds JSON-LD structured data: Organization, BreadcrumbList, Article, FAQ
 */

// ===== 1. Global Organization + Website Schema =====
add_action('wp_head', function () {
    $schema = [
        '@context' => 'https://schema.org',
        '@graph'   => [
            [
                '@type' => 'Organization',
                '@id'   => home_url('/#organization'),
                'name'  => 'ETIASEuropa',
                'url'   => home_url(),
                'logo'  => [
                    '@type' => 'ImageObject',
                    'url'   => get_template_directory_uri() . '/assets/images/logo.png',
                ],
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

    // Add BreadcrumbList if not front page
    if (!is_front_page() && function_exists('rank_math_get_breadcrumbs')) {
        $crumbs = rank_math_get_breadcrumbs();
        $items  = [];
        $pos    = 1;
        foreach ($crumbs as $crumb) {
            $items[] = [
                '@type'    => 'ListItem',
                'position' => $pos++,
                'name'     => $crumb[0] ?? '',
                'item'     => $crumb[1] ?? '',
            ];
        }
        if (!empty($items)) {
            $schema['@graph'][] = [
                '@type'           => 'BreadcrumbList',
                '@id'             => home_url('/#breadcrumb'),
                'itemListElement' => $items,
            ];
        }
    }

    echo '<script type="application/ld+json">' . wp_json_encode($schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . '</script>' . "\n";
});


// ===== 2. Article Schema on Single Posts =====
add_action('wp_head', function () {
    if (!is_single()) return;

    global $post;
    if (!($post instanceof WP_Post)) return;

    $categories = wp_get_post_categories($post->ID, ['fields' => 'names']);
    $image      = get_the_post_thumbnail_url($post->ID, 'full');
    $author_name= get_the_author_meta('display_name', $post->post_author) ?: 'Carlos Cardoso';

    $schema = [
        '@context'       => 'https://schema.org',
        '@type'          => 'Article',
        '@id'            => get_permalink($post->ID) . '#article',
        'headline'       => get_the_title($post->ID),
        'description'    => get_the_excerpt($post->ID) ?: wp_trim_words(strip_tags($post->post_content), 25),
        'datePublished'  => get_the_date('c', $post->ID),
        'dateModified'   => get_the_modified_date('c', $post->ID),
        'author'         => [
            '@type' => 'Person',
            'name'  => $author_name,
            'url'   => home_url('/about/'),
        ],
        'publisher'      => ['@id' => home_url('/#organization')],
        'mainEntityOfPage' => [
            '@type' => 'WebPage',
            '@id'   => get_permalink($post->ID),
        ],
    ];

    if ($image) {
        $schema['image'] = [
            '@type' => 'ImageObject',
            'url'   => $image,
        ];
    }

    if (!empty($categories)) {
        $schema['articleSection'] = implode(', ', $categories);
    }

    echo '<script type="application/ld+json">' . wp_json_encode($schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . '</script>' . "\n";
});


// ===== 3. FAQ Schema on FAQ Page =====
add_action('wp_head', function () {
    if (!is_page('faq')) return;

    // FAQ items — keep in sync with actual page content
    $faqs = [
        ['q' => 'What is ETIAS?', 'a' => 'ETIAS (European Travel Information and Authorization System) is an electronic system that allows visa-exempt travelers to visit the Schengen Area for short stays, enhancing security and streamlining the travel process.'],
        ['q' => 'When will ETIAS be implemented?', 'a' => 'ETIAS is expected to be fully operational by Q4 2026.'],
        ['q' => 'Is ETIAS a visa?', 'a' => 'No. ETIAS is a travel authorization, not a visa.'],
        ['q' => 'Who needs an ETIAS travel authorization?', 'a' => 'Citizens of visa-exempt countries such as the United States, Canada, United Kingdom, Australia, Japan, and many others need ETIAS to enter the Schengen Area.'],
        ['q' => 'How long is ETIAS valid?', 'a' => 'ETIAS is valid for three years or until the passport expires, whichever comes first.'],
        ['q' => 'How many entries does ETIAS allow?', 'a' => 'Multiple entries into the Schengen Area, provided the total stay does not exceed 90 days within any 180-day period.'],
        ['q' => 'Do children need ETIAS?', 'a' => 'Yes, every traveler including minors must have an individual ETIAS authorization.'],
        ['q' => 'What if my ETIAS application is denied?', 'a' => 'You will receive a reason for the denial. You can appeal or reapply with additional information.'],
        ['q' => 'Can I apply for ETIAS at the border?', 'a' => 'No, you must apply online before your trip.'],
        ['q' => 'Does ETIAS guarantee entry?', 'a' => 'No. Border authorities make the final entry decision based on documentation and purpose of visit.'],
    ];

    $items = [];
    foreach ($faqs as $i => $faq) {
        $items[] = [
            '@type' => 'Question',
            'name'  => $faq['q'],
            'acceptedAnswer' => [
                '@type' => 'Answer',
                'text'  => $faq['a'],
            ],
        ];
    }

    $schema = [
        '@context'   => 'https://schema.org',
        '@type'      => 'FAQPage',
        '@id'        => home_url('/faq/') . '#faq',
        'mainEntity' => $items,
    ];

    echo '<script type="application/ld+json">' . wp_json_encode($schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . '</script>' . "\n";
});


// ===== 4. Add "Last Updated" to post content =====
add_filter('the_content', function ($content) {
    if (is_single() && in_the_loop() && is_main_query()) {
        $modified = get_the_modified_date('F j, Y');
        $created  = get_the_date('F j, Y');
        $notice   = '<p class="post-meta-info" style="font-size:0.85em;color:#666;margin-top:2em;border-top:1px solid #eee;padding-top:1em;">';
        $notice  .= '📅 <strong>Last updated:</strong> ' . $modified;
        if ($modified !== $created) {
            $notice .= ' &middot; Originally published: ' . $created;
        }
        $notice .= '</p>';
        $content .= $notice;
    }
    return $content;
});


// ===== 5. Add Author Bio Box to posts =====
add_filter('the_content', function ($content) {
    if (is_single() && in_the_loop() && is_main_query()) {
        $author_name = get_the_author_meta('display_name') ?: 'Carlos Cardoso';
        $author_desc = get_the_author_meta('description') ?: 'Travel and immigration writer at ETIASEuropa, helping travelers navigate European entry requirements.';
        $avatar      = get_avatar_url(get_the_author_meta('ID'), ['size' => 80]);

        $bio = '<div class="author-bio-box" style="display:flex;gap:1em;padding:1.5em;background:#f8f9fa;border-radius:8px;margin-top:2em;">';
        if ($avatar) {
            $bio .= '<img src="' . esc_url($avatar) . '" alt="' . esc_attr($author_name) . '" style="width:80px;height:80px;border-radius:50%;object-fit:cover;" loading="lazy" />';
        }
        $bio .= '<div><strong style="font-size:1.1em;">' . esc_html($author_name) . '</strong>';
        $bio .= '<p style="margin:0.5em 0 0;font-size:0.9em;color:#555;">' . esc_html($author_desc) . '</p></div></div>';
        $content .= $bio;
    }
    return $content;
});


// ===== 6. Add related posts at end of articles =====
add_filter('the_content', function ($content) {
    if (is_single() && in_the_loop() && is_main_query()) {
        $related = get_posts([
            'category__in' => wp_get_post_categories(get_the_ID()),
            'post__not_in' => [get_the_ID()],
            'posts_per_page' => 3,
            'orderby' => 'rand',
        ]);
        if ($related) {
            $html = '<div class="related-posts" style="margin-top:2em;padding:1.5em;background:#f0f4f8;border-radius:8px;">';
            $html .= '<h3 style="margin-top:0;">📖 Related Articles</h3><ul style="margin:0;padding-left:1.2em;">';
            foreach ($related as $rp) {
                $html .= '<li><a href="' . get_permalink($rp->ID) . '">' . get_the_title($rp->ID) . '</a></li>';
            }
            $html .= '</ul></div>';
            $content .= $html;
        }
    }
    return $content;
});
