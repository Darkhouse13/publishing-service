<?php
/**
 * Page template.
 *
 * @package YourMidnightDesk
 */

get_header();
?>
<main class="site-main">
    <section class="entry-shell">
        <div class="container">
            <?php if (have_posts()) : ?>
                <?php while (have_posts()) : the_post(); ?>
                    <article <?php post_class(); ?>>
                        <header class="entry-header">
                            <h1 class="entry-header__title"><?php the_title(); ?></h1>
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
                    <h1 class="empty-state__title"><?php esc_html_e('Page not found.', 'yourmidnightdesk'); ?></h1>
                    <p class="empty-state__body"><?php esc_html_e('This page has not been published yet.', 'yourmidnightdesk'); ?></p>
                </div>
            <?php endif; ?>
        </div>
    </section>
</main>

<?php
get_footer();
