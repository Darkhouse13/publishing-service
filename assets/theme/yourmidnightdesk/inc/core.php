<?php
/**
 * Core theme functions.
 *
 * @package YourMidnightDesk
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Set up theme defaults and supported features.
 */
function ymd_theme_setup() {
    add_theme_support('title-tag');
    add_theme_support('post-thumbnails');
    add_theme_support(
        'html5',
        array(
            'search-form',
            'comment-form',
            'comment-list',
            'gallery',
            'caption',
            'style',
            'script',
        )
    );
    add_theme_support(
        'custom-logo',
        array(
            'height'      => 140,
            'width'       => 640,
            'flex-height' => true,
            'flex-width'  => true,
        )
    );

    register_nav_menus(
        array(
            'primary' => __('Primary Menu', 'yourmidnightdesk'),
            'footer'  => __('Footer Menu', 'yourmidnightdesk'),
        )
    );

    add_image_size('ymd-hero', 1440, 1080, true);
    add_image_size('ymd-card', 720, 900, true);
    add_image_size('ymd-square', 720, 720, true);
}
add_action('after_setup_theme', 'ymd_theme_setup');

/**
 * Enqueue front-end assets.
 */
function ymd_enqueue_assets() {
    wp_enqueue_style(
        'ymd-google-fonts',
        'https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;400;500;600;700&family=Fraunces:opsz,wght@9..144,300;400;500;600&display=swap',
        array(),
        null
    );

    wp_enqueue_style(
        'ymd-theme',
        get_stylesheet_uri(),
        array('ymd-google-fonts'),
        YMD_THEME_VERSION
    );

    wp_enqueue_script(
        'ymd-theme',
        ymd_asset_uri('assets/js/theme.js'),
        array(),
        YMD_THEME_VERSION,
        true
    );

    wp_localize_script(
        'ymd-theme',
        'ymdTheme',
        array(
            'ajaxUrl'       => admin_url('admin-ajax.php'),
            'nonce'         => wp_create_nonce('ymd_recipe_feed'),
            'loadMoreLabel' => __('Load More Recipes', 'yourmidnightdesk'),
            'loadingLabel'  => __('Loading...', 'yourmidnightdesk'),
        )
    );
}
add_action('wp_enqueue_scripts', 'ymd_enqueue_assets');

/**
 * Return asset URI for bundled theme files.
 *
 * @param string $path Relative file path.
 * @return string
 */
function ymd_asset_uri($path) {
    return trailingslashit(YMD_THEME_URI) . ltrim($path, '/');
}

/**
 * Get default theme mods.
 *
 * @return array<string, mixed>
 */
function ymd_theme_defaults() {
    static $defaults;

    if (is_array($defaults)) {
        return $defaults;
    }

    $defaults = array(
        'ymd_announcement_enabled'    => 1,
        'ymd_announcement_text'       => __('Join the seasonal cooking challenge: Spring Greens Edition', 'yourmidnightdesk'),
        'ymd_announcement_url'        => home_url('/?s=spring+greens'),
        'ymd_subscribe_label'         => __('Subscribe', 'yourmidnightdesk'),
        'ymd_subscribe_url'           => '#newsletter-signup',
        'ymd_search_placeholder'      => __('Search recipes...', 'yourmidnightdesk'),
        'ymd_recipe_featured_title'   => __('Miso Glazed Salmon Bowl', 'yourmidnightdesk'),
        'ymd_recipe_featured_url'     => home_url('/?s=salmon+bowl'),
        'ymd_hero_cta_label'          => __('View Recipe', 'yourmidnightdesk'),
        'ymd_hero_fallback_title'     => __('Roasted Figs with <em>Thyme</em> & Honey.', 'yourmidnightdesk'),
        'ymd_hero_fallback_excerpt'   => __('A simple yet elegant appetizer that balances sweetness with earthiness. Ready in just 20 minutes and perfect for your next gathering.', 'yourmidnightdesk'),
        'ymd_hero_fallback_badge'     => __('Vegetarian', 'yourmidnightdesk'),
        'ymd_hero_fallback_url'       => '#fresh-from-the-kitchen',
        'ymd_editor_label'            => __("Editor's Letter", 'yourmidnightdesk'),
        'ymd_editor_title'            => __('Why we are loving slow Sundays.', 'yourmidnightdesk'),
        'ymd_editor_body'             => __('There is something deeply restorative about reclaiming the kitchen on a Sunday afternoon. No rush, no timers, just the rhythmic chopping of vegetables and the slow simmer of a broth. This month, we have curated a collection of recipes designed not just to be eaten, but to be experienced.', 'yourmidnightdesk'),
        'ymd_editor_cta_label'        => __('Read full story', 'yourmidnightdesk'),
        'ymd_editor_author_name'      => __('Elena Rossi', 'yourmidnightdesk'),
        'ymd_editor_author_role'      => __('Head Editor', 'yourmidnightdesk'),
        'ymd_newsletter_eyebrow'      => __('Weekly inspiration', 'yourmidnightdesk'),
        'ymd_newsletter_title'        => __('Table Talk.', 'yourmidnightdesk'),
        'ymd_newsletter_body'         => __('Join 45,000+ food lovers. Receive seasonal recipes, curated kitchen finds, and cooking tips directly to your inbox every Friday.', 'yourmidnightdesk'),
        'ymd_newsletter_button_label' => __('Sign Up', 'yourmidnightdesk'),
        'ymd_newsletter_placeholder'  => __('Your email address', 'yourmidnightdesk'),
        'ymd_newsletter_note'         => __('No spam, ever. Unsubscribe anytime.', 'yourmidnightdesk'),
        'ymd_newsletter_method'       => 'post',
        'ymd_quote_text'              => __('"Your Midnight Desk has completely changed how I approach weeknight dinners. The recipes are sophisticated but approachable, and the results are consistently restaurant-quality."', 'yourmidnightdesk'),
        'ymd_quote_name'              => __('Sarah Jenkins', 'yourmidnightdesk'),
        'ymd_quote_location'          => __('New York', 'yourmidnightdesk'),
        'ymd_social_heading'          => __('@YourMidnightDesk', 'yourmidnightdesk'),
        'ymd_social_cta_label'        => __('Follow us on Instagram', 'yourmidnightdesk'),
        'ymd_social_cta_url'          => 'https://instagram.com',
        'ymd_footer_description'      => __('Celebrating the art of home cooking with seasonal ingredients and stories from the table.', 'yourmidnightdesk'),
        'ymd_footer_explore_1_label'  => __('Recipe Index', 'yourmidnightdesk'),
        'ymd_footer_explore_1_url'    => home_url('/?s=recipes'),
        'ymd_footer_explore_2_label'  => __('Collections', 'yourmidnightdesk'),
        'ymd_footer_explore_2_url'    => home_url('/?s=collections'),
        'ymd_footer_explore_3_label'  => __('Video Tutorials', 'yourmidnightdesk'),
        'ymd_footer_explore_3_url'    => home_url('/?s=tutorials'),
        'ymd_footer_explore_4_label'  => __('Shop Kitchenware', 'yourmidnightdesk'),
        'ymd_footer_explore_4_url'    => home_url('/?s=shop'),
        'ymd_footer_company_1_label'  => __('About Us', 'yourmidnightdesk'),
        'ymd_footer_company_1_url'    => home_url('/about'),
        'ymd_footer_company_2_label'  => __('Careers', 'yourmidnightdesk'),
        'ymd_footer_company_2_url'    => home_url('/careers'),
        'ymd_footer_company_3_label'  => __('Contact', 'yourmidnightdesk'),
        'ymd_footer_company_3_url'    => home_url('/contact'),
        'ymd_footer_company_4_label'  => __('Advertising', 'yourmidnightdesk'),
        'ymd_footer_company_4_url'    => home_url('/advertising'),
        'ymd_footer_social_fb_url'    => 'https://facebook.com',
        'ymd_footer_social_ig_url'    => 'https://instagram.com',
        'ymd_footer_social_pt_url'    => 'https://pinterest.com',
        'ymd_copyright_text'          => __('All rights reserved.', 'yourmidnightdesk'),
    );

    $recipe_groups = array(
        1 => array(
            'title' => __('By Meal', 'yourmidnightdesk'),
            'links' => array(
                __('Breakfast & Brunch', 'yourmidnightdesk'),
                __('Quick Lunches', 'yourmidnightdesk'),
                __('Weeknight Dinner', 'yourmidnightdesk'),
                __('Sunday Supper', 'yourmidnightdesk'),
            ),
        ),
        2 => array(
            'title' => __('Dietary', 'yourmidnightdesk'),
            'links' => array(
                __('Vegetarian', 'yourmidnightdesk'),
                __('Vegan', 'yourmidnightdesk'),
                __('Gluten-Free', 'yourmidnightdesk'),
                __('Low Carb', 'yourmidnightdesk'),
            ),
        ),
        3 => array(
            'title' => __('Season', 'yourmidnightdesk'),
            'links' => array(
                __('Spring Produce', 'yourmidnightdesk'),
                __('Summer Grilling', 'yourmidnightdesk'),
                __('Autumn Baking', 'yourmidnightdesk'),
                __('Winter Comfort', 'yourmidnightdesk'),
            ),
        ),
    );

    foreach ($recipe_groups as $group_index => $group_defaults) {
        $defaults["ymd_recipe_group_{$group_index}_title"] = $group_defaults['title'];
        foreach ($group_defaults['links'] as $link_index => $label) {
            $human_index = $link_index + 1;
            $defaults["ymd_recipe_group_{$group_index}_link_{$human_index}_label"] = $label;
            $defaults["ymd_recipe_group_{$group_index}_link_{$human_index}_url"] = home_url('/?s=' . rawurlencode(wp_strip_all_tags($label)));
        }
    }

    $moods = array(
        1 => __('Breakfast', 'yourmidnightdesk'),
        2 => __('Healthy', 'yourmidnightdesk'),
        3 => __('Dessert', 'yourmidnightdesk'),
        4 => __('Greens', 'yourmidnightdesk'),
        5 => __('Quick', 'yourmidnightdesk'),
        6 => __('Seasonal', 'yourmidnightdesk'),
    );
    foreach ($moods as $index => $label) {
        $defaults["ymd_mood_{$index}_title"] = $label;
        $defaults["ymd_mood_{$index}_url"] = home_url('/?s=' . rawurlencode(wp_strip_all_tags($label)));
    }

    $trending_labels = array(
        1 => __('Comfort Food', 'yourmidnightdesk'),
        2 => __('Weeknight', 'yourmidnightdesk'),
        3 => __('Fresh', 'yourmidnightdesk'),
    );
    $trending_badges = array(1 => 'GF', 2 => '', 3 => 'V');
    foreach ($trending_labels as $index => $label) {
        $defaults["ymd_trending_{$index}_label"] = $label;
        $defaults["ymd_trending_{$index}_badge"] = $trending_badges[$index];
    }

    for ($index = 1; $index <= 4; $index++) {
        $defaults["ymd_social_tile_{$index}_url"] = 'https://instagram.com';
    }

    return $defaults;
}

/**
 * Return bundled fallback image map.
 *
 * @return array<string, string>
 */
function ymd_fallback_images() {
    return array(
        'featured_recipe'    => 'assets/images/featured-salmon.jpg',
        'hero'               => 'assets/images/hero-roasted-figs.jpg',
        'mood_1'             => 'assets/images/mood-breakfast.jpg',
        'mood_2'             => 'assets/images/mood-healthy.jpg',
        'mood_3'             => 'assets/images/mood-dessert.jpg',
        'mood_4'             => 'assets/images/mood-greens.jpg',
        'mood_5'             => 'assets/images/mood-quick.jpg',
        'mood_6'             => 'assets/images/mood-seasonal.jpg',
        'trending_1'         => 'assets/images/trending-risotto.jpg',
        'trending_2'         => 'assets/images/trending-cornbread.jpg',
        'trending_3'         => 'assets/images/trending-galette.jpg',
        'editor_main'        => 'assets/images/editor-main.jpg',
        'editor_secondary'   => 'assets/images/editor-secondary.jpg',
        'editor_author'      => 'assets/images/editor-author.jpg',
        'feed_1'             => 'assets/images/feed-poached-eggs.jpg',
        'feed_2'             => 'assets/images/feed-salad.jpg',
        'feed_3'             => 'assets/images/feed-curry-noodles.jpg',
        'feed_4'             => 'assets/images/feed-ice-cream.jpg',
        'newsletter_main'    => 'assets/images/newsletter-main.jpg',
        'newsletter_side'    => 'assets/images/newsletter-secondary.jpg',
        'social_1'           => 'assets/images/social-1.jpg',
        'social_2'           => 'assets/images/social-2.jpg',
        'social_3'           => 'assets/images/social-3.jpg',
        'social_4'           => 'assets/images/social-4.jpg',
    );
}

/**
 * Resolve a default theme mod value.
 *
 * @param string $key Theme mod key.
 * @return mixed
 */
function ymd_get_default($key) {
    $defaults = ymd_theme_defaults();
    return isset($defaults[$key]) ? $defaults[$key] : '';
}

/**
 * Retrieve a theme mod with a project default.
 *
 * @param string $key Theme mod key.
 * @return mixed
 */
function ymd_get_theme_value($key) {
    return get_theme_mod($key, ymd_get_default($key));
}

/**
 * Resolve a media control value into a URL.
 *
 * @param mixed  $value        Theme mod value.
 * @param string $fallback_key Fallback image identifier.
 * @return string
 */
function ymd_resolve_media_url($value, $fallback_key) {
    if (is_numeric($value)) {
        $url = wp_get_attachment_image_url((int) $value, 'full');
        if ($url) {
            return $url;
        }
    } elseif (is_string($value) && preg_match('#^https?://#', $value)) {
        return esc_url_raw($value);
    }

    $fallbacks = ymd_fallback_images();
    $path = isset($fallbacks[$fallback_key]) ? $fallbacks[$fallback_key] : '';
    return $path ? ymd_asset_uri($path) : '';
}

/**
 * Get the brand monogram.
 *
 * @return string
 */
function ymd_get_brand_mark() {
    $site_title = wp_strip_all_tags(get_bloginfo('name'));
    if ($site_title === '') {
        return 'Y';
    }

    return strtoupper(substr($site_title, 0, 1));
}

/**
 * Build choices for recent posts in the Customizer.
 *
 * @return array<int|string, string>
 */
function ymd_get_post_choices() {
    $choices = array(0 => __('Select a post', 'yourmidnightdesk'));
    $posts = get_posts(
        array(
            'post_type'           => 'post',
            'post_status'         => 'publish',
            'posts_per_page'      => 50,
            'ignore_sticky_posts' => true,
        )
    );

    foreach ($posts as $post) {
        $choices[$post->ID] = $post->post_title;
    }

    return $choices;
}

/**
 * Build choices for published pages.
 *
 * @return array<int|string, string>
 */
function ymd_get_page_choices() {
    $choices = array(0 => __('Select a page', 'yourmidnightdesk'));
    $pages = get_pages(
        array(
            'sort_column' => 'post_title',
            'post_status' => 'publish',
        )
    );

    foreach ($pages as $page) {
        $choices[$page->ID] = $page->post_title;
    }

    return $choices;
}

/**
 * Build choices for categories.
 *
 * @return array<int|string, string>
 */
function ymd_get_category_choices() {
    $choices = array(0 => __('Auto', 'yourmidnightdesk'));
    $terms = get_categories(
        array(
            'hide_empty' => false,
            'orderby'    => 'name',
            'order'      => 'ASC',
        )
    );

    foreach ($terms as $term) {
        $choices[$term->term_id] = $term->name;
    }

    return $choices;
}

/**
 * Sanitize a select value.
 *
 * @param string $value Incoming value.
 * @param array  $allowed Allowed option values.
 * @param string $fallback Fallback value.
 * @return string
 */
function ymd_sanitize_select($value, $allowed, $fallback) {
    $value = is_string($value) ? $value : '';
    return in_array($value, $allowed, true) ? $value : $fallback;
}

/**
 * Return a post's primary category object.
 *
 * @param int $post_id Post ID.
 * @return WP_Term|null
 */
function ymd_get_primary_category($post_id) {
    $terms = get_the_category($post_id);
    if (empty($terms) || is_wp_error($terms)) {
        return null;
    }

    return $terms[0];
}

/**
 * Get recipe meta for a post.
 *
 * @param int $post_id Post ID.
 * @return array<string, string>
 */
function ymd_get_recipe_meta($post_id) {
    $meta = array(
        'time'         => wp_strip_all_tags((string) get_post_meta($post_id, 'ymd_recipe_time', true)),
        'difficulty'   => wp_strip_all_tags((string) get_post_meta($post_id, 'ymd_recipe_difficulty', true)),
        'badge'        => wp_strip_all_tags((string) get_post_meta($post_id, 'ymd_recipe_badge', true)),
        'rating_text'  => wp_strip_all_tags((string) get_post_meta($post_id, 'ymd_recipe_rating_text', true)),
        'rating_value' => wp_strip_all_tags((string) get_post_meta($post_id, 'ymd_recipe_rating_value', true)),
        'card_excerpt' => wp_strip_all_tags((string) get_post_meta($post_id, 'ymd_recipe_card_excerpt', true)),
        'feature_label'=> wp_strip_all_tags((string) get_post_meta($post_id, 'ymd_recipe_featured_label', true)),
    );

    if ($meta['rating_text'] === '' && $meta['rating_value'] !== '') {
        $meta['rating_text'] = sprintf(
            /* translators: %s rating value. */
            __('Rating %s', 'yourmidnightdesk'),
            $meta['rating_value']
        );
    }

    return $meta;
}

/**
 * Build a short summary for cards.
 *
 * @param int $post_id Post ID.
 * @param int $length Word count.
 * @return string
 */
function ymd_get_post_summary($post_id, $length) {
    $meta = ymd_get_recipe_meta($post_id);
    if ($meta['card_excerpt'] !== '') {
        return $meta['card_excerpt'];
    }

    $excerpt = get_the_excerpt($post_id);
    if ($excerpt !== '') {
        return wp_trim_words(wp_strip_all_tags($excerpt), $length);
    }

    $post = get_post($post_id);
    if (!$post instanceof WP_Post) {
        return '';
    }

    return wp_trim_words(wp_strip_all_tags(strip_shortcodes($post->post_content)), $length);
}

/**
 * Build a generic card payload from a post.
 *
 * @param int    $post_id Post ID.
 * @param string $fallback_key Fallback image key.
 * @return array<string, string>
 */
function ymd_get_post_card_data($post_id, $fallback_key) {
    $post = get_post($post_id);
    if (!$post instanceof WP_Post) {
        return array();
    }

    $category = ymd_get_primary_category($post_id);
    $meta = ymd_get_recipe_meta($post_id);
    $image = get_the_post_thumbnail_url($post_id, 'large');

    return array(
        'title'       => get_the_title($post_id),
        'url'         => get_permalink($post_id),
        'image'       => $image ? $image : ymd_resolve_media_url('', $fallback_key),
        'label'       => $category ? $category->name : __('Recipes', 'yourmidnightdesk'),
        'summary'     => ymd_get_post_summary($post_id, 18),
        'time'        => $meta['time'],
        'difficulty'  => $meta['difficulty'],
        'badge'       => $meta['badge'],
        'rating'      => $meta['rating_text'],
        'feature'     => $meta['feature_label'],
        'date'        => get_the_date('', $post_id),
        'author'      => get_the_author_meta('display_name', (int) $post->post_author),
    );
}

/**
 * Get recipe mega menu groups.
 *
 * @return array<int, array<string, mixed>>
 */
function ymd_get_recipe_groups() {
    $groups = array();

    for ($group_index = 1; $group_index <= 3; $group_index++) {
        $links = array();
        for ($link_index = 1; $link_index <= 4; $link_index++) {
            $label = wp_strip_all_tags((string) ymd_get_theme_value("ymd_recipe_group_{$group_index}_link_{$link_index}_label"));
            $url = esc_url((string) ymd_get_theme_value("ymd_recipe_group_{$group_index}_link_{$link_index}_url"));
            if ($label === '') {
                continue;
            }
            $links[] = array(
                'label' => $label,
                'url'   => $url !== '' ? $url : home_url('/?s=' . rawurlencode($label)),
            );
        }

        $groups[] = array(
            'title' => wp_strip_all_tags((string) ymd_get_theme_value("ymd_recipe_group_{$group_index}_title")),
            'links' => $links,
        );
    }

    return $groups;
}

/**
 * Get homepage mood cards.
 *
 * @return array<int, array<string, string>>
 */
function ymd_get_mood_cards() {
    $cards = array();

    for ($index = 1; $index <= 6; $index++) {
        $title = wp_strip_all_tags((string) ymd_get_theme_value("ymd_mood_{$index}_title"));
        if ($title === '') {
            continue;
        }

        $cards[] = array(
            'title' => $title,
            'url'   => esc_url((string) ymd_get_theme_value("ymd_mood_{$index}_url")),
            'image' => ymd_resolve_media_url(
                ymd_get_theme_value("ymd_mood_{$index}_image"),
                "mood_{$index}"
            ),
        );
    }

    return $cards;
}

/**
 * Get the hero payload.
 *
 * @return array<string, string>
 */
function ymd_get_hero_feature() {
    $selected_post_id = absint(ymd_get_theme_value('ymd_hero_post_id'));
    if ($selected_post_id > 0) {
        $data = ymd_get_post_card_data($selected_post_id, 'hero');
        if (!empty($data)) {
            $meta = ymd_get_recipe_meta($selected_post_id);
            $data['eyebrow'] = __('Recipe of the day', 'yourmidnightdesk');
            $data['cta_label'] = wp_strip_all_tags((string) ymd_get_theme_value('ymd_hero_cta_label'));
            $data['badge'] = $meta['badge'] !== '' ? $meta['badge'] : $data['label'];
            return $data;
        }
    }

    $sticky_posts = get_option('sticky_posts');
    if (!empty($sticky_posts)) {
        $sticky_post = get_post((int) $sticky_posts[0]);
        if ($sticky_post instanceof WP_Post) {
            $data = ymd_get_post_card_data($sticky_post->ID, 'hero');
            if (!empty($data)) {
                $meta = ymd_get_recipe_meta($sticky_post->ID);
                $data['eyebrow'] = __('Recipe of the day', 'yourmidnightdesk');
                $data['cta_label'] = wp_strip_all_tags((string) ymd_get_theme_value('ymd_hero_cta_label'));
                $data['badge'] = $meta['badge'] !== '' ? $meta['badge'] : $data['label'];
                return $data;
            }
        }
    }

    $latest = get_posts(
        array(
            'post_type'      => 'post',
            'post_status'    => 'publish',
            'posts_per_page' => 1,
        )
    );
    if (!empty($latest)) {
        $data = ymd_get_post_card_data($latest[0]->ID, 'hero');
        if (!empty($data)) {
            $meta = ymd_get_recipe_meta($latest[0]->ID);
            $data['eyebrow'] = __('Recipe of the day', 'yourmidnightdesk');
            $data['cta_label'] = wp_strip_all_tags((string) ymd_get_theme_value('ymd_hero_cta_label'));
            $data['badge'] = $meta['badge'] !== '' ? $meta['badge'] : $data['label'];
            return $data;
        }
    }

    return array(
        'eyebrow'     => __('Recipe of the day', 'yourmidnightdesk'),
        'title'       => (string) ymd_get_theme_value('ymd_hero_fallback_title'),
        'summary'     => (string) ymd_get_theme_value('ymd_hero_fallback_excerpt'),
        'url'         => esc_url((string) ymd_get_theme_value('ymd_hero_fallback_url')),
        'cta_label'   => wp_strip_all_tags((string) ymd_get_theme_value('ymd_hero_cta_label')),
        'badge'       => wp_strip_all_tags((string) ymd_get_theme_value('ymd_hero_fallback_badge')),
        'time'        => __('20 min', 'yourmidnightdesk'),
        'difficulty'  => __('Easy', 'yourmidnightdesk'),
        'image'       => ymd_resolve_media_url('', 'hero'),
    );
}

/**
 * Get trending cards.
 *
 * @return array<int, array<string, string>>
 */
function ymd_get_trending_cards() {
    $cards = array();

    for ($index = 1; $index <= 3; $index++) {
        $post_id = absint(ymd_get_theme_value("ymd_trending_{$index}_post_id"));
        if ($post_id > 0) {
            $data = ymd_get_post_card_data($post_id, "trending_{$index}");
            if (!empty($data)) {
                $data['label'] = wp_strip_all_tags((string) ymd_get_theme_value("ymd_trending_{$index}_label"));
                $data['badge'] = wp_strip_all_tags((string) ymd_get_theme_value("ymd_trending_{$index}_badge"));
                $cards[] = $data;
                continue;
            }
        }
    }

    if (!empty($cards)) {
        return $cards;
    }

    return array(
        array(
            'title'   => __('Creamy Wild Mushroom Risotto', 'yourmidnightdesk'),
            'url'     => home_url('/?s=wild+mushroom+risotto'),
            'image'   => ymd_resolve_media_url('', 'trending_1'),
            'label'   => wp_strip_all_tags((string) ymd_get_theme_value('ymd_trending_1_label')),
            'badge'   => wp_strip_all_tags((string) ymd_get_theme_value('ymd_trending_1_badge')),
            'time'    => __('45 min', 'yourmidnightdesk'),
            'rating'  => __('Rating 4.9 (128)', 'yourmidnightdesk'),
        ),
        array(
            'title'   => __('Rustic Skillet Cornbread', 'yourmidnightdesk'),
            'url'     => home_url('/?s=rustic+skillet+cornbread'),
            'image'   => ymd_resolve_media_url('', 'trending_2'),
            'label'   => wp_strip_all_tags((string) ymd_get_theme_value('ymd_trending_2_label')),
            'badge'   => wp_strip_all_tags((string) ymd_get_theme_value('ymd_trending_2_badge')),
            'time'    => __('35 min', 'yourmidnightdesk'),
            'rating'  => __('Rating 4.8 (84)', 'yourmidnightdesk'),
        ),
        array(
            'title'   => __('Heirloom Tomato Galette', 'yourmidnightdesk'),
            'url'     => home_url('/?s=heirloom+tomato+galette'),
            'image'   => ymd_resolve_media_url('', 'trending_3'),
            'label'   => wp_strip_all_tags((string) ymd_get_theme_value('ymd_trending_3_label')),
            'badge'   => wp_strip_all_tags((string) ymd_get_theme_value('ymd_trending_3_badge')),
            'time'    => __('50 min', 'yourmidnightdesk'),
            'rating'  => __('Rating 5.0 (42)', 'yourmidnightdesk'),
        ),
    );
}

/**
 * Get editor feature data.
 *
 * @return array<string, string>
 */
function ymd_get_editor_feature() {
    $source_type = ymd_sanitize_select(
        (string) ymd_get_theme_value('ymd_editor_source_type'),
        array('none', 'post', 'page'),
        'none'
    );
    $source_id = 'post' === $source_type
        ? absint(ymd_get_theme_value('ymd_editor_post_id'))
        : absint(ymd_get_theme_value('ymd_editor_page_id'));

    $title = (string) ymd_get_theme_value('ymd_editor_title');
    $body = (string) ymd_get_theme_value('ymd_editor_body');
    $url = home_url('/');
    if ($source_id > 0) {
        $source = get_post($source_id);
        if ($source instanceof WP_Post) {
            $title = $source->post_title;
            $body = wp_trim_words(wp_strip_all_tags(strip_shortcodes($source->post_content)), 55);
            $url = get_permalink($source_id);
        }
    }

    return array(
        'label'        => (string) ymd_get_theme_value('ymd_editor_label'),
        'title'        => $title,
        'body'         => $body,
        'url'          => $url,
        'cta_label'    => (string) ymd_get_theme_value('ymd_editor_cta_label'),
        'author_name'  => (string) ymd_get_theme_value('ymd_editor_author_name'),
        'author_role'  => (string) ymd_get_theme_value('ymd_editor_author_role'),
        'author_image' => ymd_resolve_media_url(ymd_get_theme_value('ymd_editor_author_image'), 'editor_author'),
        'main_image'   => ymd_resolve_media_url(ymd_get_theme_value('ymd_editor_main_image'), 'editor_main'),
        'side_image'   => ymd_resolve_media_url(ymd_get_theme_value('ymd_editor_side_image'), 'editor_secondary'),
    );
}

/**
 * Get the recipe feed categories.
 *
 * @return array<int, WP_Term>
 */
function ymd_get_feed_filters() {
    $filters = array();
    for ($index = 1; $index <= 3; $index++) {
        $term_id = absint(ymd_get_theme_value("ymd_feed_filter_{$index}_category_id"));
        if ($term_id > 0) {
            $term = get_term($term_id, 'category');
            if ($term instanceof WP_Term && !is_wp_error($term)) {
                $filters[$term->term_id] = $term;
            }
        }
    }

    if (!empty($filters)) {
        return array_values($filters);
    }

    $auto_terms = get_categories(
        array(
            'hide_empty' => true,
            'number'     => 3,
            'orderby'    => 'count',
            'order'      => 'DESC',
        )
    );

    return is_array($auto_terms) ? $auto_terms : array();
}

/**
 * Get the newsletter configuration.
 *
 * @return array<string, string>
 */
function ymd_get_newsletter_config() {
    return array(
        'eyebrow'      => (string) ymd_get_theme_value('ymd_newsletter_eyebrow'),
        'title'        => (string) ymd_get_theme_value('ymd_newsletter_title'),
        'body'         => (string) ymd_get_theme_value('ymd_newsletter_body'),
        'button_label' => (string) ymd_get_theme_value('ymd_newsletter_button_label'),
        'placeholder'  => (string) ymd_get_theme_value('ymd_newsletter_placeholder'),
        'note'         => (string) ymd_get_theme_value('ymd_newsletter_note'),
        'action_url'   => esc_url((string) ymd_get_theme_value('ymd_newsletter_action_url')),
        'method'       => ymd_sanitize_select(
            (string) ymd_get_theme_value('ymd_newsletter_method'),
            array('get', 'post'),
            'post'
        ),
        'main_image'   => ymd_resolve_media_url(ymd_get_theme_value('ymd_newsletter_main_image'), 'newsletter_main'),
        'side_image'   => ymd_resolve_media_url(ymd_get_theme_value('ymd_newsletter_side_image'), 'newsletter_side'),
    );
}

/**
 * Get quote and social data.
 *
 * @return array<string, string>
 */
function ymd_get_quote_social_config() {
    return array(
        'quote'          => (string) ymd_get_theme_value('ymd_quote_text'),
        'quote_name'     => (string) ymd_get_theme_value('ymd_quote_name'),
        'quote_location' => (string) ymd_get_theme_value('ymd_quote_location'),
        'social_heading' => (string) ymd_get_theme_value('ymd_social_heading'),
        'social_label'   => (string) ymd_get_theme_value('ymd_social_cta_label'),
        'social_url'     => esc_url((string) ymd_get_theme_value('ymd_social_cta_url')),
    );
}

/**
 * Get curated social tiles.
 *
 * @return array<int, array<string, string>>
 */
function ymd_get_social_tiles() {
    $tiles = array();

    for ($index = 1; $index <= 4; $index++) {
        $tiles[] = array(
            'url'   => esc_url((string) ymd_get_theme_value("ymd_social_tile_{$index}_url")),
            'image' => ymd_resolve_media_url(ymd_get_theme_value("ymd_social_tile_{$index}_image"), "social_{$index}"),
        );
    }

    return $tiles;
}

/**
 * Get footer link columns.
 *
 * @return array<string, array<int, array<string, string>>>
 */
function ymd_get_footer_columns() {
    $columns = array(
        'explore' => array(),
        'company' => array(),
    );

    foreach (array('explore', 'company') as $section) {
        for ($index = 1; $index <= 4; $index++) {
            $label = wp_strip_all_tags((string) ymd_get_theme_value("ymd_footer_{$section}_{$index}_label"));
            $url = esc_url((string) ymd_get_theme_value("ymd_footer_{$section}_{$index}_url"));
            if ($label === '') {
                continue;
            }
            $columns[$section][] = array(
                'label' => $label,
                'url'   => $url,
            );
        }
    }

    return $columns;
}

/**
 * Get social links for the footer.
 *
 * @return array<int, array<string, string>>
 */
function ymd_get_footer_socials() {
    return array(
        array(
            'label' => 'FB',
            'url'   => esc_url((string) ymd_get_theme_value('ymd_footer_social_fb_url')),
        ),
        array(
            'label' => 'IG',
            'url'   => esc_url((string) ymd_get_theme_value('ymd_footer_social_ig_url')),
        ),
        array(
            'label' => 'PT',
            'url'   => esc_url((string) ymd_get_theme_value('ymd_footer_social_pt_url')),
        ),
    );
}

/**
 * Get fallback feed cards.
 *
 * @return array<int, array<string, string>>
 */
function ymd_get_fallback_feed_cards() {
    return array(
        array(
            'title'   => __('Poached Eggs on Sourdough with Avocado', 'yourmidnightdesk'),
            'url'     => home_url('/?s=poached+eggs'),
            'image'   => ymd_resolve_media_url('', 'feed_1'),
            'label'   => __('Breakfast', 'yourmidnightdesk'),
            'summary' => __('A classic breakfast staple elevated with chili flakes and high-quality olive oil.', 'yourmidnightdesk'),
        ),
        array(
            'title'   => __('Spinach & Walnut Salad', 'yourmidnightdesk'),
            'url'     => home_url('/?s=spinach+walnut+salad'),
            'image'   => ymd_resolve_media_url('', 'feed_2'),
            'label'   => __('Lunch', 'yourmidnightdesk'),
            'summary' => __('Crunchy walnuts meet tender baby spinach in this nutrient-dense powerhouse.', 'yourmidnightdesk'),
        ),
        array(
            'title'   => __('Spicy Curry Noodles', 'yourmidnightdesk'),
            'url'     => home_url('/?s=spicy+curry+noodles'),
            'image'   => ymd_resolve_media_url('', 'feed_3'),
            'label'   => __('Dinner', 'yourmidnightdesk'),
            'summary' => __('Warm, comforting, and packed with spices. The perfect remedy for a cold evening.', 'yourmidnightdesk'),
        ),
        array(
            'title'   => __('Vanilla Bean Ice Cream', 'yourmidnightdesk'),
            'url'     => home_url('/?s=vanilla+bean+ice+cream'),
            'image'   => ymd_resolve_media_url('', 'feed_4'),
            'label'   => __('Dessert', 'yourmidnightdesk'),
            'summary' => __('Homemade ice cream without the machine. Creamy, sweet, and incredibly simple.', 'yourmidnightdesk'),
        ),
    );
}

/**
 * Build a recipe feed query.
 *
 * @param int    $page Page number.
 * @param string $filter_slug Category slug or "all".
 * @return WP_Query
 */
function ymd_get_recipe_feed_query($page = 1, $filter_slug = 'all') {
    $args = array(
        'post_type'           => 'post',
        'post_status'         => 'publish',
        'posts_per_page'      => 4,
        'paged'               => max(1, (int) $page),
        'ignore_sticky_posts' => true,
    );

    $filter_slug = sanitize_title($filter_slug);
    if ($filter_slug !== '' && $filter_slug !== 'all') {
        $term = get_term_by('slug', $filter_slug, 'category');
        if ($term instanceof WP_Term) {
            $args['cat'] = (int) $term->term_id;
        }
    }

    return new WP_Query($args);
}

/**
 * Render a recipe feed card.
 *
 * @param array<string, string> $item Card data.
 * @return string
 */
function ymd_render_recipe_card($item) {
    $title = isset($item['title']) ? $item['title'] : '';
    $url = isset($item['url']) ? $item['url'] : '#';
    $image = isset($item['image']) ? $item['image'] : '';
    $label = isset($item['label']) ? $item['label'] : '';
    $summary = isset($item['summary']) ? $item['summary'] : '';

    ob_start();
    ?>
    <article class="recipe-card">
        <a class="recipe-card__image" href="<?php echo esc_url($url); ?>">
            <?php if ($image !== '') : ?>
                <img src="<?php echo esc_url($image); ?>" alt="<?php echo esc_attr($title); ?>">
            <?php endif; ?>
        </a>
        <div class="recipe-card__content">
            <span class="recipe-card__label"><?php echo esc_html($label); ?></span>
            <h3 class="recipe-card__title"><a href="<?php echo esc_url($url); ?>"><?php echo esc_html($title); ?></a></h3>
            <p class="recipe-card__summary"><?php echo esc_html($summary); ?></p>
        </div>
    </article>
    <?php
    return (string) ob_get_clean();
}

/**
 * Render a listing card.
 *
 * @param int    $post_id Post ID.
 * @param string $fallback_key Fallback image key.
 * @return string
 */
function ymd_render_listing_card($post_id, $fallback_key) {
    $item = ymd_get_post_card_data($post_id, $fallback_key);
    if (empty($item)) {
        return '';
    }

    ob_start();
    ?>
    <article class="listing-card">
        <a class="listing-card__image" href="<?php echo esc_url($item['url']); ?>">
            <img src="<?php echo esc_url($item['image']); ?>" alt="<?php echo esc_attr($item['title']); ?>">
        </a>
        <div class="listing-card__content">
            <div class="listing-card__meta">
                <span><?php echo esc_html($item['label']); ?></span>
                <span>&bull;</span>
                <span><?php echo esc_html($item['date']); ?></span>
            </div>
            <h2 class="listing-card__title"><a href="<?php echo esc_url($item['url']); ?>"><?php echo esc_html($item['title']); ?></a></h2>
            <p class="listing-card__summary"><?php echo esc_html($item['summary']); ?></p>
        </div>
    </article>
    <?php
    return (string) ob_get_clean();
}

/**
 * Render feed query cards.
 *
 * @param WP_Query $query Query object.
 * @return string
 */
function ymd_render_feed_query_cards($query) {
    if (!$query instanceof WP_Query || !$query->have_posts()) {
        return '<div class="empty-state"><h3 class="empty-state__title">' .
            esc_html__('No recipes found.', 'yourmidnightdesk') .
            '</h3><p class="empty-state__body">' .
            esc_html__('Try another category or add more recipe posts to the site.', 'yourmidnightdesk') .
            '</p></div>';
    }

    ob_start();
    while ($query->have_posts()) {
        $query->the_post();
        echo ymd_render_recipe_card(ymd_get_post_card_data(get_the_ID(), 'feed_1')); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
    }
    wp_reset_postdata();

    return (string) ob_get_clean();
}

/**
 * Return recent posts for the sidebar.
 *
 * @return array<int, WP_Post>
 */
function ymd_get_sidebar_posts() {
    return get_posts(
        array(
            'post_type'           => 'post',
            'post_status'         => 'publish',
            'posts_per_page'      => 5,
            'ignore_sticky_posts' => true,
        )
    );
}

/**
 * AJAX endpoint for the recipe feed.
 */
function ymd_ajax_recipe_feed() {
    check_ajax_referer('ymd_recipe_feed', 'nonce');

    $page = isset($_POST['page']) ? absint(wp_unslash($_POST['page'])) : 1;
    $filter = isset($_POST['filter']) ? sanitize_title(wp_unslash($_POST['filter'])) : 'all';
    $query = ymd_get_recipe_feed_query($page, $filter);

    wp_send_json_success(
        array(
            'html'     => ymd_render_feed_query_cards($query),
            'has_more' => $query->max_num_pages > max(1, $page),
        )
    );
}
add_action('wp_ajax_ymd_recipe_feed', 'ymd_ajax_recipe_feed');
add_action('wp_ajax_nopriv_ymd_recipe_feed', 'ymd_ajax_recipe_feed');

/**
 * Clean archive title prefixes.
 *
 * @param string $title Raw title.
 * @return string
 */
function ymd_clean_archive_title($title) {
    if (is_category()) {
        return single_cat_title('', false);
    }
    if (is_tag()) {
        return single_tag_title('', false);
    }
    if (is_tax()) {
        return single_term_title('', false);
    }
    return wp_strip_all_tags((string) $title);
}
add_filter('get_the_archive_title', 'ymd_clean_archive_title');
