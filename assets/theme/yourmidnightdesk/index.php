<?php
/**
 * Index template.
 *
 * @package YourMidnightDesk
 */

get_header();
?>
<main class="site-main">
    <section class="listing-shell">
        <div class="container">
            <div class="listing-head">
                <h1 class="listing-head__title"><?php esc_html_e('Latest Recipes', 'yourmidnightdesk'); ?></h1>
                <p class="listing-head__description"><?php esc_html_e('An editorial collection of fresh recipes, slow cooking rituals, and approachable dishes from the Your Midnight Desk kitchen.', 'yourmidnightdesk'); ?></p>
            </div>

            <?php if (have_posts()) : ?>
                <div class="listing-grid">
                    <?php
                    while (have_posts()) {
                        the_post();
                        echo ymd_render_listing_card(get_the_ID(), 'feed_1'); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
                    }
                    ?>
                </div>

                <div class="listing-pagination">
                    <?php the_posts_pagination(); ?>
                </div>
            <?php else : ?>
                <div class="empty-state">
                    <h2 class="empty-state__title"><?php esc_html_e('Nothing has been plated yet.', 'yourmidnightdesk'); ?></h2>
                    <p class="empty-state__body"><?php esc_html_e('Publish a few posts and the editorial recipe archive will appear here.', 'yourmidnightdesk'); ?></p>
                </div>
            <?php endif; ?>
        </div>
    </section>
</main>

<?php
get_footer();
