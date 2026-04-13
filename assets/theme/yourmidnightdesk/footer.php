<?php
/**
 * Footer template.
 *
 * @package YourMidnightDesk
 */

$footer_columns = ymd_get_footer_columns();
$footer_socials = ymd_get_footer_socials();
$footer_description = (string) ymd_get_theme_value('ymd_footer_description');
$copyright_note = wp_strip_all_tags((string) ymd_get_theme_value('ymd_copyright_text'));
?>
<footer class="site-footer">
    <div class="container">
        <div class="site-footer__top">
            <div class="site-footer__brand">
                <a class="brand" href="<?php echo esc_url(home_url('/')); ?>">
                    <span class="brand__mark"><?php echo esc_html(ymd_get_brand_mark()); ?></span>
                    <span class="brand__wordmark"><?php bloginfo('name'); ?>.</span>
                </a>
                <p><?php echo esc_html($footer_description); ?></p>
            </div>

            <div>
                <h5 class="footer-title"><?php esc_html_e('Explore', 'yourmidnightdesk'); ?></h5>
                <ul class="footer-link-list">
                    <?php foreach ($footer_columns['explore'] as $link) : ?>
                        <li><a href="<?php echo esc_url($link['url']); ?>"><?php echo esc_html($link['label']); ?></a></li>
                    <?php endforeach; ?>
                </ul>
            </div>

            <div>
                <h5 class="footer-title"><?php esc_html_e('Company', 'yourmidnightdesk'); ?></h5>
                <ul class="footer-link-list">
                    <?php foreach ($footer_columns['company'] as $link) : ?>
                        <li><a href="<?php echo esc_url($link['url']); ?>"><?php echo esc_html($link['label']); ?></a></li>
                    <?php endforeach; ?>
                </ul>
            </div>

            <div>
                <h5 class="footer-title"><?php esc_html_e('Connect', 'yourmidnightdesk'); ?></h5>
                <div class="footer-socials">
                    <?php foreach ($footer_socials as $social) : ?>
                        <a href="<?php echo esc_url($social['url']); ?>" target="_blank" rel="noreferrer">
                            <span class="screen-reader-text"><?php echo esc_html($social['label']); ?></span>
                            <?php echo esc_html($social['label']); ?>
                        </a>
                    <?php endforeach; ?>
                </div>
            </div>
        </div>

        <div class="site-footer__bottom">
            <p>&copy; <?php echo esc_html(wp_date('Y')); ?> <?php bloginfo('name'); ?>. <?php echo esc_html($copyright_note); ?></p>
            <?php
            if (has_nav_menu('footer')) {
                wp_nav_menu(
                    array(
                        'theme_location' => 'footer',
                        'container'      => false,
                        'menu_class'     => 'footer-legal',
                        'fallback_cb'    => false,
                        'depth'          => 1,
                    )
                );
            }
            ?>
        </div>
    </div>
</footer>

<?php wp_footer(); ?>
</body>
</html>
