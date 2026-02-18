<?php
/**
 * Footer template.
 *
 * @package The_Sunday_Patio
 */
?>
<footer class="site-footer bg-sage-dark text-linen mt-auto">
    <div class="max-w-7xl mx-auto px-6 py-16 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12">
        <div class="col-span-1 lg:col-span-1">
            <h3 class="font-serif text-2xl mb-6"><?php bloginfo('name'); ?></h3>
            <?php if (get_bloginfo('description')) : ?>
                <p class="text-sm opacity-80 leading-relaxed mb-6"><?php bloginfo('description'); ?></p>
            <?php endif; ?>
        </div>

        <div class="col-span-1 md:col-span-1 lg:col-span-3">
            <h5 class="footer-nav-title text-xs font-bold uppercase tracking-widest mb-6 text-terracotta">
                <?php esc_html_e('Navigation', 'the-sunday-patio'); ?>
            </h5>
            <?php
            wp_nav_menu(
                array(
                    'theme_location' => 'footer',
                    'container'      => false,
                    'menu_class'     => 'footer-menu grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3',
                    'fallback_cb'    => 'wp_page_menu',
                    'depth'          => 1,
                )
            );
            ?>
        </div>
    </div>

    <div class="border-t border-white/10 py-6 text-center text-xs opacity-60 uppercase tracking-widest">
        &copy; <?php echo esc_html(wp_date('Y')); ?> <?php bloginfo('name'); ?>
    </div>
</footer>

<?php wp_footer(); ?>
</body>
</html>
