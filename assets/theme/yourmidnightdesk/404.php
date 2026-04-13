<?php
/**
 * 404 template.
 *
 * @package YourMidnightDesk
 */

get_header();
?>
<main class="site-main">
    <section class="empty-state">
        <div class="container">
            <h1 class="empty-state__title"><?php esc_html_e('That recipe is off the menu.', 'yourmidnightdesk'); ?></h1>
            <p class="empty-state__body"><?php esc_html_e('The page you were looking for is not available. Return to the homepage or search for another dish.', 'yourmidnightdesk'); ?></p>
            <p>
                <a class="button button--accent" href="<?php echo esc_url(home_url('/')); ?>"><?php esc_html_e('Back to Homepage', 'yourmidnightdesk'); ?></a>
            </p>
        </div>
    </section>
</main>

<?php
get_footer();
