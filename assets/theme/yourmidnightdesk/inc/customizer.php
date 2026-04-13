<?php
/**
 * Theme Customizer integration.
 *
 * @package YourMidnightDesk
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Register a text setting + control.
 *
 * @param WP_Customize_Manager $wp_customize Customizer manager.
 * @param string               $section Section ID.
 * @param string               $setting Setting ID.
 * @param string               $label Label.
 * @param string               $type Control type.
 */
function ymd_add_text_control($wp_customize, $section, $setting, $label, $type = 'text') {
    $sanitize = 'text' === $type ? 'sanitize_text_field' : 'sanitize_textarea_field';
    $wp_customize->add_setting(
        $setting,
        array(
            'default'           => ymd_get_default($setting),
            'sanitize_callback' => $sanitize,
            'type'              => 'theme_mod',
        )
    );
    $wp_customize->add_control(
        $setting,
        array(
            'section' => $section,
            'label'   => $label,
            'type'    => $type,
        )
    );
}

/**
 * Register a URL setting + control.
 *
 * @param WP_Customize_Manager $wp_customize Customizer manager.
 * @param string               $section Section ID.
 * @param string               $setting Setting ID.
 * @param string               $label Label.
 */
function ymd_add_url_control($wp_customize, $section, $setting, $label) {
    $wp_customize->add_setting(
        $setting,
        array(
            'default'           => ymd_get_default($setting),
            'sanitize_callback' => 'esc_url_raw',
            'type'              => 'theme_mod',
        )
    );
    $wp_customize->add_control(
        $setting,
        array(
            'section' => $section,
            'label'   => $label,
            'type'    => 'url',
        )
    );
}

/**
 * Register a media setting + control.
 *
 * @param WP_Customize_Manager $wp_customize Customizer manager.
 * @param string               $section Section ID.
 * @param string               $setting Setting ID.
 * @param string               $label Label.
 */
function ymd_add_media_control($wp_customize, $section, $setting, $label) {
    $wp_customize->add_setting(
        $setting,
        array(
            'default'           => ymd_get_default($setting),
            'sanitize_callback' => 'absint',
            'type'              => 'theme_mod',
        )
    );
    $wp_customize->add_control(
        new WP_Customize_Media_Control(
            $wp_customize,
            $setting,
            array(
                'section'   => $section,
                'label'     => $label,
                'mime_type' => 'image',
            )
        )
    );
}

/**
 * Register the theme Customizer.
 *
 * @param WP_Customize_Manager $wp_customize Customizer manager.
 */
function ymd_customize_register($wp_customize) {
    $wp_customize->add_panel(
        'ymd_theme_panel',
        array(
            'title'    => __('Your Midnight Desk Theme', 'yourmidnightdesk'),
            'priority' => 30,
        )
    );

    $sections = array(
        'ymd_announcement' => __('Announcement + Header', 'yourmidnightdesk'),
        'ymd_recipe_groups' => __('Recipe Mega Menu', 'yourmidnightdesk'),
        'ymd_home_hero' => __('Homepage Hero', 'yourmidnightdesk'),
        'ymd_home_moods' => __('Browse by Mood', 'yourmidnightdesk'),
        'ymd_home_trending' => __('Trending This Week', 'yourmidnightdesk'),
        'ymd_home_editor' => __('Editor Feature', 'yourmidnightdesk'),
        'ymd_home_feed' => __('Recipe Feed', 'yourmidnightdesk'),
        'ymd_home_newsletter' => __('Newsletter', 'yourmidnightdesk'),
        'ymd_home_social' => __('Quote + Social', 'yourmidnightdesk'),
        'ymd_footer_content' => __('Footer Content', 'yourmidnightdesk'),
    );

    foreach ($sections as $section_id => $title) {
        $wp_customize->add_section(
            $section_id,
            array(
                'title' => $title,
                'panel' => 'ymd_theme_panel',
            )
        );
    }

    $wp_customize->add_setting(
        'ymd_announcement_enabled',
        array(
            'default'           => ymd_get_default('ymd_announcement_enabled'),
            'sanitize_callback' => 'absint',
            'type'              => 'theme_mod',
        )
    );
    $wp_customize->add_control(
        'ymd_announcement_enabled',
        array(
            'section' => 'ymd_announcement',
            'label'   => __('Show announcement bar', 'yourmidnightdesk'),
            'type'    => 'checkbox',
        )
    );
    ymd_add_text_control($wp_customize, 'ymd_announcement', 'ymd_announcement_text', __('Announcement text', 'yourmidnightdesk'));
    ymd_add_url_control($wp_customize, 'ymd_announcement', 'ymd_announcement_url', __('Announcement link', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_announcement', 'ymd_subscribe_label', __('Subscribe button label', 'yourmidnightdesk'));
    ymd_add_url_control($wp_customize, 'ymd_announcement', 'ymd_subscribe_url', __('Subscribe button URL', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_announcement', 'ymd_search_placeholder', __('Search placeholder', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_announcement', 'ymd_recipe_featured_title', __('Mega menu featured title', 'yourmidnightdesk'));
    ymd_add_url_control($wp_customize, 'ymd_announcement', 'ymd_recipe_featured_url', __('Mega menu featured URL', 'yourmidnightdesk'));
    ymd_add_media_control($wp_customize, 'ymd_announcement', 'ymd_recipe_featured_image', __('Mega menu featured image', 'yourmidnightdesk'));

    for ($group_index = 1; $group_index <= 3; $group_index++) {
        ymd_add_text_control(
            $wp_customize,
            'ymd_recipe_groups',
            "ymd_recipe_group_{$group_index}_title",
            sprintf(__('Group %d title', 'yourmidnightdesk'), $group_index)
        );
        for ($link_index = 1; $link_index <= 4; $link_index++) {
            ymd_add_text_control(
                $wp_customize,
                'ymd_recipe_groups',
                "ymd_recipe_group_{$group_index}_link_{$link_index}_label",
                sprintf(__('Group %1$d link %2$d label', 'yourmidnightdesk'), $group_index, $link_index)
            );
            ymd_add_url_control(
                $wp_customize,
                'ymd_recipe_groups',
                "ymd_recipe_group_{$group_index}_link_{$link_index}_url",
                sprintf(__('Group %1$d link %2$d URL', 'yourmidnightdesk'), $group_index, $link_index)
            );
        }
    }

    $wp_customize->add_setting(
        'ymd_hero_post_id',
        array(
            'default'           => 0,
            'sanitize_callback' => 'absint',
            'type'              => 'theme_mod',
        )
    );
    $wp_customize->add_control(
        'ymd_hero_post_id',
        array(
            'section' => 'ymd_home_hero',
            'label'   => __('Hero post', 'yourmidnightdesk'),
            'type'    => 'select',
            'choices' => ymd_get_post_choices(),
        )
    );
    ymd_add_text_control($wp_customize, 'ymd_home_hero', 'ymd_hero_cta_label', __('Hero button label', 'yourmidnightdesk'));
    $wp_customize->add_setting(
        'ymd_hero_fallback_title',
        array(
            'default'           => ymd_get_default('ymd_hero_fallback_title'),
            'sanitize_callback' => 'wp_kses_post',
            'type'              => 'theme_mod',
        )
    );
    $wp_customize->add_control(
        'ymd_hero_fallback_title',
        array(
            'section' => 'ymd_home_hero',
            'label'   => __('Hero fallback title (supports emphasis tags)', 'yourmidnightdesk'),
            'type'    => 'textarea',
        )
    );
    ymd_add_text_control($wp_customize, 'ymd_home_hero', 'ymd_hero_fallback_excerpt', __('Hero fallback excerpt', 'yourmidnightdesk'), 'textarea');
    ymd_add_text_control($wp_customize, 'ymd_home_hero', 'ymd_hero_fallback_badge', __('Hero fallback badge', 'yourmidnightdesk'));
    ymd_add_url_control($wp_customize, 'ymd_home_hero', 'ymd_hero_fallback_url', __('Hero fallback URL', 'yourmidnightdesk'));

    for ($index = 1; $index <= 6; $index++) {
        ymd_add_text_control($wp_customize, 'ymd_home_moods', "ymd_mood_{$index}_title", sprintf(__('Mood %d title', 'yourmidnightdesk'), $index));
        ymd_add_url_control($wp_customize, 'ymd_home_moods', "ymd_mood_{$index}_url", sprintf(__('Mood %d URL', 'yourmidnightdesk'), $index));
        ymd_add_media_control($wp_customize, 'ymd_home_moods', "ymd_mood_{$index}_image", sprintf(__('Mood %d image', 'yourmidnightdesk'), $index));
    }

    for ($index = 1; $index <= 3; $index++) {
        $wp_customize->add_setting(
            "ymd_trending_{$index}_post_id",
            array(
                'default'           => 0,
                'sanitize_callback' => 'absint',
                'type'              => 'theme_mod',
            )
        );
        $wp_customize->add_control(
            "ymd_trending_{$index}_post_id",
            array(
                'section' => 'ymd_home_trending',
                'label'   => sprintf(__('Trending card %d post', 'yourmidnightdesk'), $index),
                'type'    => 'select',
                'choices' => ymd_get_post_choices(),
            )
        );
        ymd_add_text_control($wp_customize, 'ymd_home_trending', "ymd_trending_{$index}_label", sprintf(__('Trending card %d label', 'yourmidnightdesk'), $index));
        ymd_add_text_control($wp_customize, 'ymd_home_trending', "ymd_trending_{$index}_badge", sprintf(__('Trending card %d badge', 'yourmidnightdesk'), $index));
    }

    $wp_customize->add_setting(
        'ymd_editor_source_type',
        array(
            'default'           => 'none',
            'sanitize_callback' => function ($value) {
                return ymd_sanitize_select($value, array('none', 'post', 'page'), 'none');
            },
            'type'              => 'theme_mod',
        )
    );
    $wp_customize->add_control(
        'ymd_editor_source_type',
        array(
            'section' => 'ymd_home_editor',
            'label'   => __('Editor feature source', 'yourmidnightdesk'),
            'type'    => 'select',
            'choices' => array(
                'none' => __('Use fallback copy', 'yourmidnightdesk'),
                'post' => __('Use a post', 'yourmidnightdesk'),
                'page' => __('Use a page', 'yourmidnightdesk'),
            ),
        )
    );
    foreach (array('post' => 'ymd_editor_post_id', 'page' => 'ymd_editor_page_id') as $type => $setting) {
        $wp_customize->add_setting(
            $setting,
            array(
                'default'           => 0,
                'sanitize_callback' => 'absint',
                'type'              => 'theme_mod',
            )
        );
        $wp_customize->add_control(
            $setting,
            array(
                'section' => 'ymd_home_editor',
                'label'   => 'post' === $type ? __('Editor post', 'yourmidnightdesk') : __('Editor page', 'yourmidnightdesk'),
                'type'    => 'select',
                'choices' => 'post' === $type ? ymd_get_post_choices() : ymd_get_page_choices(),
            )
        );
    }
    ymd_add_text_control($wp_customize, 'ymd_home_editor', 'ymd_editor_label', __('Editor section label', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_editor', 'ymd_editor_title', __('Editor fallback title', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_editor', 'ymd_editor_body', __('Editor fallback body', 'yourmidnightdesk'), 'textarea');
    ymd_add_text_control($wp_customize, 'ymd_home_editor', 'ymd_editor_cta_label', __('Editor CTA label', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_editor', 'ymd_editor_author_name', __('Editor author name', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_editor', 'ymd_editor_author_role', __('Editor author role', 'yourmidnightdesk'));
    ymd_add_media_control($wp_customize, 'ymd_home_editor', 'ymd_editor_author_image', __('Editor author image', 'yourmidnightdesk'));
    ymd_add_media_control($wp_customize, 'ymd_home_editor', 'ymd_editor_main_image', __('Editor main image', 'yourmidnightdesk'));
    ymd_add_media_control($wp_customize, 'ymd_home_editor', 'ymd_editor_side_image', __('Editor side image', 'yourmidnightdesk'));

    for ($index = 1; $index <= 3; $index++) {
        $setting = "ymd_feed_filter_{$index}_category_id";
        $wp_customize->add_setting(
            $setting,
            array(
                'default'           => 0,
                'sanitize_callback' => 'absint',
                'type'              => 'theme_mod',
            )
        );
        $wp_customize->add_control(
            $setting,
            array(
                'section' => 'ymd_home_feed',
                'label'   => sprintf(__('Recipe filter %d category', 'yourmidnightdesk'), $index),
                'type'    => 'select',
                'choices' => ymd_get_category_choices(),
            )
        );
    }

    ymd_add_text_control($wp_customize, 'ymd_home_newsletter', 'ymd_newsletter_eyebrow', __('Newsletter eyebrow', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_newsletter', 'ymd_newsletter_title', __('Newsletter title', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_newsletter', 'ymd_newsletter_body', __('Newsletter body', 'yourmidnightdesk'), 'textarea');
    ymd_add_url_control($wp_customize, 'ymd_home_newsletter', 'ymd_newsletter_action_url', __('Newsletter form action URL', 'yourmidnightdesk'));
    $wp_customize->add_setting(
        'ymd_newsletter_method',
        array(
            'default'           => ymd_get_default('ymd_newsletter_method'),
            'sanitize_callback' => function ($value) {
                return ymd_sanitize_select($value, array('get', 'post'), 'post');
            },
            'type'              => 'theme_mod',
        )
    );
    $wp_customize->add_control(
        'ymd_newsletter_method',
        array(
            'section' => 'ymd_home_newsletter',
            'label'   => __('Newsletter method', 'yourmidnightdesk'),
            'type'    => 'select',
            'choices' => array(
                'post' => 'POST',
                'get'  => 'GET',
            ),
        )
    );
    ymd_add_text_control($wp_customize, 'ymd_home_newsletter', 'ymd_newsletter_button_label', __('Newsletter button label', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_newsletter', 'ymd_newsletter_placeholder', __('Newsletter placeholder', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_newsletter', 'ymd_newsletter_note', __('Newsletter note', 'yourmidnightdesk'), 'textarea');
    ymd_add_media_control($wp_customize, 'ymd_home_newsletter', 'ymd_newsletter_main_image', __('Newsletter main image', 'yourmidnightdesk'));
    ymd_add_media_control($wp_customize, 'ymd_home_newsletter', 'ymd_newsletter_side_image', __('Newsletter side image', 'yourmidnightdesk'));

    ymd_add_text_control($wp_customize, 'ymd_home_social', 'ymd_quote_text', __('Quote text', 'yourmidnightdesk'), 'textarea');
    ymd_add_text_control($wp_customize, 'ymd_home_social', 'ymd_quote_name', __('Quote name', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_social', 'ymd_quote_location', __('Quote location', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_social', 'ymd_social_heading', __('Social heading', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_home_social', 'ymd_social_cta_label', __('Social CTA label', 'yourmidnightdesk'));
    ymd_add_url_control($wp_customize, 'ymd_home_social', 'ymd_social_cta_url', __('Social CTA URL', 'yourmidnightdesk'));
    for ($index = 1; $index <= 4; $index++) {
        ymd_add_media_control($wp_customize, 'ymd_home_social', "ymd_social_tile_{$index}_image", sprintf(__('Social tile %d image', 'yourmidnightdesk'), $index));
        ymd_add_url_control($wp_customize, 'ymd_home_social', "ymd_social_tile_{$index}_url", sprintf(__('Social tile %d URL', 'yourmidnightdesk'), $index));
    }

    ymd_add_text_control($wp_customize, 'ymd_footer_content', 'ymd_footer_description', __('Footer description', 'yourmidnightdesk'), 'textarea');
    foreach (array('explore', 'company') as $section) {
        for ($index = 1; $index <= 4; $index++) {
            ymd_add_text_control(
                $wp_customize,
                'ymd_footer_content',
                "ymd_footer_{$section}_{$index}_label",
                sprintf(__('%1$s link %2$d label', 'yourmidnightdesk'), ucfirst($section), $index)
            );
            ymd_add_url_control(
                $wp_customize,
                'ymd_footer_content',
                "ymd_footer_{$section}_{$index}_url",
                sprintf(__('%1$s link %2$d URL', 'yourmidnightdesk'), ucfirst($section), $index)
            );
        }
    }
    ymd_add_url_control($wp_customize, 'ymd_footer_content', 'ymd_footer_social_fb_url', __('Facebook URL', 'yourmidnightdesk'));
    ymd_add_url_control($wp_customize, 'ymd_footer_content', 'ymd_footer_social_ig_url', __('Instagram URL', 'yourmidnightdesk'));
    ymd_add_url_control($wp_customize, 'ymd_footer_content', 'ymd_footer_social_pt_url', __('Pinterest URL', 'yourmidnightdesk'));
    ymd_add_text_control($wp_customize, 'ymd_footer_content', 'ymd_copyright_text', __('Copyright note', 'yourmidnightdesk'));
}
add_action('customize_register', 'ymd_customize_register');
