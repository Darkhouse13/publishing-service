<?php
/**
 * Sidebar template.
 *
 * @package YourMidnightDesk
 */

$recent_posts = ymd_get_sidebar_posts();
$categories = get_categories(
    array(
        'hide_empty' => true,
        'number'     => 8,
        'orderby'    => 'count',
        'order'      => 'DESC',
    )
);
?>
<aside class="entry-sidebar">
    <section class="sidebar-card">
        <h2 class="sidebar-card__title"><?php esc_html_e('Search the Pantry', 'yourmidnightdesk'); ?></h2>
        <form class="drawer-search" role="search" method="get" action="<?php echo esc_url(home_url('/')); ?>">
            <label class="screen-reader-text" for="ymd-sidebar-search"><?php esc_html_e('Search', 'yourmidnightdesk'); ?></label>
            <input id="ymd-sidebar-search" type="search" name="s" placeholder="<?php echo esc_attr(ymd_get_theme_value('ymd_search_placeholder')); ?>" value="<?php echo esc_attr(get_search_query()); ?>">
        </form>
    </section>

    <?php if (!empty($categories)) : ?>
        <section class="sidebar-card">
            <h2 class="sidebar-card__title"><?php esc_html_e('Popular Categories', 'yourmidnightdesk'); ?></h2>
            <ul class="category-list">
                <?php foreach ($categories as $category) : ?>
                    <li><a href="<?php echo esc_url(get_category_link($category)); ?>"><?php echo esc_html($category->name); ?></a></li>
                <?php endforeach; ?>
            </ul>
        </section>
    <?php endif; ?>

    <?php if (!empty($recent_posts)) : ?>
        <section class="sidebar-card">
            <h2 class="sidebar-card__title"><?php esc_html_e('Fresh Reads', 'yourmidnightdesk'); ?></h2>
            <ul class="post-list">
                <?php foreach ($recent_posts as $post) : ?>
                    <li><a href="<?php echo esc_url(get_permalink($post)); ?>"><?php echo esc_html(get_the_title($post)); ?></a></li>
                <?php endforeach; ?>
            </ul>
        </section>
    <?php endif; ?>
</aside>
