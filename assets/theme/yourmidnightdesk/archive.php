<?php
/**
 * Archive template.
 *
 * @package YourMidnightDesk
 */

get_header();
?>
<main class="site-main">
    <section class="listing-shell">
        <div class="container">
            <div class="listing-head">
                <?php the_archive_title('<h1 class="listing-head__title">', '</h1>'); ?>
                <?php if (get_the_archive_description()) : ?>
                    <div class="listing-head__description"><?php the_archive_description(); ?></div>
                <?php endif; ?>
            </div>

            <?php if (have_posts()) : ?>
                <div class="listing-grid">
                    <?php
                    while (have_posts()) {
                        the_post();
                        echo ymd_render_listing_card(get_the_ID(), 'feed_2'); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
                    }
                    ?>
                </div>
                <div class="listing-pagination">
                    <?php the_posts_pagination(); ?>
                </div>
            <?php else : ?>
                <div class="empty-state">
                    <h2 class="empty-state__title"><?php esc_html_e('No recipes found.', 'yourmidnightdesk'); ?></h2>
                    <p class="empty-state__body"><?php esc_html_e('This archive is empty for now. Add a few posts or choose another category.', 'yourmidnightdesk'); ?></p>
                </div>
            <?php endif; ?>
        </div>
    </section>
</main>

<?php
get_footer();
