<?php
/**
 * Sidebar template.
 *
 * @package The_Sunday_Patio
 */
?>
<aside class="lg:col-span-4 space-y-8">
    <?php if (is_active_sidebar('primary-sidebar')) : ?>
        <?php dynamic_sidebar('primary-sidebar'); ?>
    <?php else : ?>
        <?php
        the_widget(
            'WP_Widget_Search',
            array(),
            array(
                'before_widget' => '<section class="widget bg-sand border border-stone-200 rounded-lg p-6">',
                'after_widget'  => '</section>',
            )
        );

        the_widget(
            'WP_Widget_Categories',
            array(
                'count'        => 1,
                'hierarchical' => 0,
                'dropdown'     => 0,
            ),
            array(
                'before_widget' => '<section class="widget bg-sand border border-stone-200 rounded-lg p-6">',
                'after_widget'  => '</section>',
                'before_title'  => '<h3 class="font-serif text-xl mb-4 border-b border-stone-300 pb-2">',
                'after_title'   => '</h3>',
            )
        );
        ?>
    <?php endif; ?>
</aside>
