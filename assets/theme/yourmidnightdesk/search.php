<?php
/**
 * Search results template.
 *
 * @package YourMidnightDesk
 */

get_header();
?>
<main class="site-main">
    <section class="listing-shell">
        <div class="container">
            <div class="listing-head">
                <p class="search-result-count">
                    <?php
                    printf(
                        /* translators: %s search query. */
                        esc_html__('Results for "%s"', 'yourmidnightdesk'),
                        esc_html(get_search_query())
                    );
                    ?>
                </p>
                <h1 class="listing-head__title"><?php esc_html_e('Search Results', 'yourmidnightdesk'); ?></h1>
            </div>

            <?php if (have_posts()) : ?>
                <div class="search-grid">
                    <?php
                    while (have_posts()) {
                        the_post();
                        echo ymd_render_listing_card(get_the_ID(), 'feed_3'); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
                    }
                    ?>
                </div>
                <div class="listing-pagination">
                    <?php the_posts_pagination(); ?>
                </div>
            <?php else : ?>
                <div class="empty-state">
                    <h2 class="empty-state__title"><?php esc_html_e('No matching recipes.', 'yourmidnightdesk'); ?></h2>
                    <p class="empty-state__body"><?php esc_html_e('Try a different ingredient, dish, or cooking style.', 'yourmidnightdesk'); ?></p>
                </div>
            <?php endif; ?>
        </div>
    </section>
</main>

<?php
get_footer();
