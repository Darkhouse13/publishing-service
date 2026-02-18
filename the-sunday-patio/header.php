<?php
/**
 * Header template.
 *
 * @package The_Sunday_Patio
 */
?><!doctype html>
<html <?php language_attributes(); ?>>
<head>
    <meta charset="<?php bloginfo('charset'); ?>">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <?php wp_head(); ?>
</head>
<body <?php body_class('font-sans antialiased min-h-screen flex flex-col'); ?>>
<?php wp_body_open(); ?>

<header class="w-full bg-linen border-b border-stone-200">
    <div class="max-w-7xl mx-auto px-6 py-6 flex flex-col items-center justify-center">
        <div class="mb-6 text-center">
            <?php if (has_custom_logo()) : ?>
                <?php the_custom_logo(); ?>
            <?php else : ?>
                <a
                    href="<?php echo esc_url(home_url('/')); ?>"
                    class="font-serif text-4xl md:text-5xl font-bold text-sage-dark tracking-tight"
                    rel="home"
                >
                    <?php bloginfo('name'); ?>
                </a>
            <?php endif; ?>
        </div>

        <nav class="w-full overflow-x-auto" aria-label="<?php esc_attr_e('Primary Menu', 'the-sunday-patio'); ?>">
            <?php
            wp_nav_menu(
                array(
                    'theme_location' => 'primary',
                    'container'      => false,
                    'menu_class'     => 'primary-menu flex justify-center space-x-8 md:space-x-12 min-w-max px-4 pb-2',
                    'fallback_cb'    => 'wp_page_menu',
                    'depth'          => 1,
                )
            );
            ?>
        </nav>
    </div>
</header>
