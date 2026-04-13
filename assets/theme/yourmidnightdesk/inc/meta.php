<?php
/**
 * Native post meta boxes for recipe-specific fields.
 *
 * @package YourMidnightDesk
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Register post meta for recipe cards.
 */
function ymd_register_post_meta() {
    $keys = array(
        'ymd_recipe_time',
        'ymd_recipe_difficulty',
        'ymd_recipe_badge',
        'ymd_recipe_rating_text',
        'ymd_recipe_rating_value',
        'ymd_recipe_card_excerpt',
        'ymd_recipe_featured_label',
    );

    foreach ($keys as $key) {
        register_post_meta(
            'post',
            $key,
            array(
                'type'              => 'string',
                'single'            => true,
                'show_in_rest'      => false,
                'sanitize_callback' => 'sanitize_text_field',
                'auth_callback'     => function () {
                    return current_user_can('edit_posts');
                },
            )
        );
    }
}
add_action('init', 'ymd_register_post_meta');

/**
 * Add the recipe meta box.
 */
function ymd_add_recipe_meta_box() {
    add_meta_box(
        'ymd_recipe_meta',
        __('Recipe Display Details', 'yourmidnightdesk'),
        'ymd_render_recipe_meta_box',
        'post',
        'side',
        'default'
    );
}
add_action('add_meta_boxes', 'ymd_add_recipe_meta_box');

/**
 * Render recipe meta fields.
 *
 * @param WP_Post $post Post object.
 */
function ymd_render_recipe_meta_box($post) {
    wp_nonce_field('ymd_save_recipe_meta', 'ymd_recipe_meta_nonce');

    $fields = array(
        'ymd_recipe_time'          => __('Cook time', 'yourmidnightdesk'),
        'ymd_recipe_difficulty'    => __('Difficulty', 'yourmidnightdesk'),
        'ymd_recipe_badge'         => __('Dietary badge', 'yourmidnightdesk'),
        'ymd_recipe_rating_text'   => __('Rating text', 'yourmidnightdesk'),
        'ymd_recipe_rating_value'  => __('Rating value', 'yourmidnightdesk'),
        'ymd_recipe_featured_label'=> __('Featured label', 'yourmidnightdesk'),
    );
    ?>
    <div class="ymd-meta-fields">
        <?php foreach ($fields as $key => $label) : ?>
            <p>
                <label for="<?php echo esc_attr($key); ?>"><strong><?php echo esc_html($label); ?></strong></label><br>
                <input
                    class="widefat"
                    type="text"
                    id="<?php echo esc_attr($key); ?>"
                    name="<?php echo esc_attr($key); ?>"
                    value="<?php echo esc_attr((string) get_post_meta($post->ID, $key, true)); ?>"
                >
            </p>
        <?php endforeach; ?>
        <p>
            <label for="ymd_recipe_card_excerpt"><strong><?php esc_html_e('Card excerpt override', 'yourmidnightdesk'); ?></strong></label><br>
            <textarea
                class="widefat"
                rows="4"
                id="ymd_recipe_card_excerpt"
                name="ymd_recipe_card_excerpt"
            ><?php echo esc_textarea((string) get_post_meta($post->ID, 'ymd_recipe_card_excerpt', true)); ?></textarea>
        </p>
    </div>
    <?php
}

/**
 * Persist recipe meta fields.
 *
 * @param int $post_id Post ID.
 */
function ymd_save_recipe_meta($post_id) {
    if (!isset($_POST['ymd_recipe_meta_nonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['ymd_recipe_meta_nonce'])), 'ymd_save_recipe_meta')) {
        return;
    }

    if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) {
        return;
    }

    if (!current_user_can('edit_post', $post_id)) {
        return;
    }

    $fields = array(
        'ymd_recipe_time',
        'ymd_recipe_difficulty',
        'ymd_recipe_badge',
        'ymd_recipe_rating_text',
        'ymd_recipe_rating_value',
        'ymd_recipe_card_excerpt',
        'ymd_recipe_featured_label',
    );

    foreach ($fields as $field) {
        if (!isset($_POST[$field])) {
            delete_post_meta($post_id, $field);
            continue;
        }
        $value = wp_unslash($_POST[$field]);
        $clean = 'ymd_recipe_card_excerpt' === $field
            ? sanitize_textarea_field($value)
            : sanitize_text_field($value);
        if ($clean === '') {
            delete_post_meta($post_id, $field);
            continue;
        }
        update_post_meta($post_id, $field, $clean);
    }
}
add_action('save_post_post', 'ymd_save_recipe_meta');
