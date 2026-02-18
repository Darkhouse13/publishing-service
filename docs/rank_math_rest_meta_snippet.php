<?php
/**
 * Expose Rank Math post meta fields to the WordPress REST API.
 * Paste into your active theme's functions.php or a small custom plugin.
 */

add_action('rest_api_init', function () {
    $meta_keys = array(
        'rank_math_title',
        'rank_math_description',
        'rank_math_focus_keyword',
    );

    foreach ($meta_keys as $meta_key) {
        register_post_meta(
            'post',
            $meta_key,
            array(
                'type' => 'string',
                'single' => true,
                'show_in_rest' => true,
                'auth_callback' => function () {
                    return current_user_can('edit_posts');
                },
            )
        );
    }
});
