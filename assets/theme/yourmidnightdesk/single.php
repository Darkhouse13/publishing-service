<?php
/**
 * Single post template.
 *
 * @package YourMidnightDesk
 */

get_header();
?>
<main class="site-main">
    <section class="entry-shell">
        <div class="container">
            <div class="entry-layout">
                <div>
                    <?php if (have_posts()) : ?>
                        <?php while (have_posts()) : the_post(); ?>
                            <?php
                            $meta = ymd_get_recipe_meta(get_the_ID());
                            $category = ymd_get_primary_category(get_the_ID());
                            ?>
                            <article <?php post_class(); ?>>
                                <header class="entry-header">
                                    <?php if ($category) : ?>
                                        <div class="entry-header__eyebrow"><?php echo esc_html($category->name); ?></div>
                                    <?php endif; ?>
                                    <h1 class="entry-header__title"><?php the_title(); ?></h1>
                                    <div class="entry-meta">
                                        <span><?php echo esc_html(get_the_date()); ?></span>
                                        <span>&bull;</span>
                                        <span><?php the_author(); ?></span>
                                        <?php if ($meta['time'] !== '') : ?>
                                            <span>&bull;</span>
                                            <span><?php echo esc_html($meta['time']); ?></span>
                                        <?php endif; ?>
                                        <?php if ($meta['difficulty'] !== '') : ?>
                                            <span>&bull;</span>
                                            <span><?php echo esc_html($meta['difficulty']); ?></span>
                                        <?php endif; ?>
                                        <?php if ($meta['rating_text'] !== '') : ?>
                                            <span>&bull;</span>
                                            <span><?php echo esc_html($meta['rating_text']); ?></span>
                                        <?php endif; ?>
                                    </div>
                                </header>

                                <?php if (has_post_thumbnail()) : ?>
                                    <div class="entry-featured-image">
                                        <?php the_post_thumbnail('large'); ?>
                                    </div>
                                <?php endif; ?>

                                <div class="entry-content">
                                    <?php
                                    the_content();
                                    wp_link_pages(
                                        array(
                                            'before' => '<div class="navigation pagination"><div class="nav-links">',
                                            'after'  => '</div></div>',
                                        )
                                    );
                                    ?>
                                </div>
                            </article>
                        <?php endwhile; ?>
                    <?php else : ?>
                        <div class="empty-state">
                            <h1 class="empty-state__title"><?php esc_html_e('Recipe not found.', 'yourmidnightdesk'); ?></h1>
                            <p class="empty-state__body"><?php esc_html_e('The requested recipe could not be plated. Please head back to the archive.', 'yourmidnightdesk'); ?></p>
                        </div>
                    <?php endif; ?>
                </div>

                <?php get_sidebar(); ?>
            </div>
        </div>
    </section>
</main>

<?php
get_footer();
