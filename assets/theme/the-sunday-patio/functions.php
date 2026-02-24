<?php
/**
 * Theme functions for The Sunday Patio.
 *
 * @package The_Sunday_Patio
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Set up theme defaults and supports.
 */
function tsp_theme_setup() {
    add_theme_support('post-thumbnails');
    add_theme_support('title-tag');
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
            'height'      => 120,
            'width'       => 500,
            'flex-width'  => true,
            'flex-height' => true,
        )
    );

    register_nav_menus(
        array(
            'primary' => __('Primary Menu', 'the-sunday-patio'),
            'footer'  => __('Footer Menu', 'the-sunday-patio'),
        )
    );
}
add_action('after_setup_theme', 'tsp_theme_setup');

/**
 * Register widget areas.
 */
function tsp_register_sidebars() {
    register_sidebar(
        array(
            'name'          => __('Primary Sidebar', 'the-sunday-patio'),
            'id'            => 'primary-sidebar',
            'description'   => __('Sidebar for about content and ad widgets.', 'the-sunday-patio'),
            'before_widget' => '<section id="%1$s" class="widget %2$s bg-sand border border-stone-200 rounded-lg p-6">',
            'after_widget'  => '</section>',
            'before_title'  => '<h3 class="font-serif text-xl mb-4 border-b border-stone-300 pb-2">',
            'after_title'   => '</h3>',
        )
    );
}
add_action('widgets_init', 'tsp_register_sidebars');

/**
 * Enqueue scripts and styles.
 */
function tsp_enqueue_assets() {
    wp_enqueue_script(
        'tsp-tailwind-cdn',
        'https://cdn.tailwindcss.com',
        array(),
        null,
        false
    );

    $tailwind_config = <<<'JS'
tailwind.config = {
    theme: {
        extend: {
            colors: {
                linen: "#F9F8F6",
                charcoal: "#2D2D2D",
                sage: "#3A5A40",
                "sage-dark": "#2A402E",
                terracotta: "#E07A5F",
                sand: "#EFECE5"
            },
            fontFamily: {
                serif: ['"Playfair Display"', "serif"],
                sans: ['"Inter"', "sans-serif"]
            },
            spacing: {
                128: "32rem"
            }
        }
    }
};
JS;
    wp_add_inline_script('tsp-tailwind-cdn', $tailwind_config, 'before');

    wp_enqueue_style(
        'tsp-google-fonts',
        'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400;1,600&display=swap',
        array(),
        null
    );

    wp_enqueue_style(
        'tsp-style',
        get_stylesheet_uri(),
        array('tsp-google-fonts'),
        wp_get_theme()->get('Version')
    );
}
add_action('wp_enqueue_scripts', 'tsp_enqueue_assets');

/**
 * Normalize archive titles by removing taxonomy/date/author prefixes.
 *
 * @param string $title Archive title.
 * @return string
 */
function tsp_clean_archive_title($title) {
    if (is_category()) {
        $clean = single_cat_title('', false);
        if (!empty($clean)) {
            return $clean;
        }
    } elseif (is_tag()) {
        $clean = single_tag_title('', false);
        if (!empty($clean)) {
            return $clean;
        }
    } elseif (is_tax()) {
        $clean = single_term_title('', false);
        if (!empty($clean)) {
            return $clean;
        }
    } elseif (is_author()) {
        $author = get_queried_object();
        if (isset($author->display_name) && is_string($author->display_name)) {
            return $author->display_name;
        }
    } elseif (is_year()) {
        return get_the_date(_x('Y', 'yearly archives date format', 'the-sunday-patio'));
    } elseif (is_month()) {
        return get_the_date(_x('F Y', 'monthly archives date format', 'the-sunday-patio'));
    } elseif (is_day()) {
        return get_the_date(_x('F j, Y', 'daily archives date format', 'the-sunday-patio'));
    } elseif (is_post_type_archive()) {
        $clean = post_type_archive_title('', false);
        if (!empty($clean)) {
            return $clean;
        }
    }

    $fallback = wp_strip_all_tags((string) $title);
    if (strpos($fallback, ':') !== false) {
        $parts = explode(':', $fallback, 2);
        $candidate = trim((string) $parts[1]);
        if (!empty($candidate)) {
            return $candidate;
        }
    }
    return $fallback;
}
add_filter('get_the_archive_title', 'tsp_clean_archive_title');

/**
 * Get first category name for a post.
 *
 * @param int $post_id Post ID.
 * @return string
 */
function tsp_get_primary_term_name($post_id) {
    $categories = get_the_category($post_id);
    if (empty($categories) || is_wp_error($categories)) {
        return '';
    }

    return wp_strip_all_tags($categories[0]->name);
}
