<?php
/**
 * Header template.
 *
 * @package YourMidnightDesk
 */

$announcement_enabled = (bool) ymd_get_theme_value('ymd_announcement_enabled');
$announcement_text = wp_strip_all_tags((string) ymd_get_theme_value('ymd_announcement_text'));
$announcement_url = esc_url((string) ymd_get_theme_value('ymd_announcement_url'));
$subscribe_label = wp_strip_all_tags((string) ymd_get_theme_value('ymd_subscribe_label'));
$subscribe_url = esc_url((string) ymd_get_theme_value('ymd_subscribe_url'));
$search_placeholder = wp_strip_all_tags((string) ymd_get_theme_value('ymd_search_placeholder'));
$recipe_groups = ymd_get_recipe_groups();
$featured_recipe_title = wp_strip_all_tags((string) ymd_get_theme_value('ymd_recipe_featured_title'));
$featured_recipe_url = esc_url((string) ymd_get_theme_value('ymd_recipe_featured_url'));
$featured_recipe_image = ymd_resolve_media_url(ymd_get_theme_value('ymd_recipe_featured_image'), 'featured_recipe');
?><!doctype html>
<html <?php language_attributes(); ?>>
<head>
    <meta charset="<?php bloginfo('charset'); ?>">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <?php wp_head(); ?>
</head>
<body <?php body_class('site-shell'); ?>>
<?php wp_body_open(); ?>

<?php if ($announcement_enabled && $announcement_text !== '') : ?>
    <div class="announcement-bar">
        <a href="<?php echo esc_url($announcement_url !== '' ? $announcement_url : home_url('/')); ?>">
            <?php echo esc_html($announcement_text); ?> &rarr;
        </a>
    </div>
<?php endif; ?>

<header class="site-header">
    <div class="container site-header__inner">
        <button class="menu-toggle" type="button" aria-controls="ymd-mobile-drawer" aria-expanded="false" data-drawer-open>
            <span class="screen-reader-text"><?php esc_html_e('Open menu', 'yourmidnightdesk'); ?></span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M4 6h16M4 12h16M4 18h16"></path>
            </svg>
        </button>

        <a class="brand" href="<?php echo esc_url(home_url('/')); ?>" rel="home">
            <span class="brand__mark"><?php echo esc_html(ymd_get_brand_mark()); ?></span>
            <span class="brand__wordmark"><?php bloginfo('name'); ?>.</span>
        </a>

        <div class="desktop-nav" aria-label="<?php esc_attr_e('Primary Navigation', 'yourmidnightdesk'); ?>">
            <div class="mega-nav">
                <button class="mega-nav__trigger" type="button">
                    <?php esc_html_e('Recipes', 'yourmidnightdesk'); ?>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                    </svg>
                </button>
                <div class="mega-menu">
                    <div class="mega-menu__grid">
                        <?php foreach ($recipe_groups as $group) : ?>
                            <div>
                                <h4 class="mega-menu__title"><?php echo esc_html($group['title']); ?></h4>
                                <ul class="mega-menu__links">
                                    <?php foreach ($group['links'] as $link) : ?>
                                        <li><a href="<?php echo esc_url($link['url']); ?>"><?php echo esc_html($link['label']); ?></a></li>
                                    <?php endforeach; ?>
                                </ul>
                            </div>
                        <?php endforeach; ?>
                        <a class="mega-menu__featured" href="<?php echo esc_url($featured_recipe_url !== '' ? $featured_recipe_url : home_url('/')); ?>">
                            <span class="mega-menu__eyebrow"><?php esc_html_e('Featured', 'yourmidnightdesk'); ?></span>
                            <div class="mega-menu__featured-image">
                                <img src="<?php echo esc_url($featured_recipe_image); ?>" alt="<?php echo esc_attr($featured_recipe_title); ?>">
                            </div>
                            <p class="mega-menu__featured-title"><?php echo esc_html($featured_recipe_title); ?></p>
                        </a>
                    </div>
                </div>
            </div>

            <?php
            if (has_nav_menu('primary')) {
                wp_nav_menu(
                    array(
                        'theme_location' => 'primary',
                        'container'      => false,
                        'menu_class'     => 'desktop-nav__list',
                        'fallback_cb'    => false,
                        'depth'          => 1,
                    )
                );
            } else {
                ?>
                <ul class="desktop-nav__list">
                    <li class="desktop-nav__item"><a href="<?php echo esc_url(home_url('/?s=tutorials')); ?>"><?php esc_html_e('Tutorials', 'yourmidnightdesk'); ?></a></li>
                    <li class="desktop-nav__item"><a href="<?php echo esc_url(home_url('/about')); ?>"><?php esc_html_e('About', 'yourmidnightdesk'); ?></a></li>
                    <li class="desktop-nav__item"><a href="<?php echo esc_url(home_url('/?s=shop')); ?>"><?php esc_html_e('Shop', 'yourmidnightdesk'); ?></a></li>
                </ul>
                <?php
            }
            ?>
        </div>

        <div class="header-actions">
            <form class="search-shell header-search" role="search" method="get" action="<?php echo esc_url(home_url('/')); ?>">
                <label class="screen-reader-text" for="ymd-desktop-search"><?php esc_html_e('Search recipes', 'yourmidnightdesk'); ?></label>
                <input id="ymd-desktop-search" type="search" name="s" placeholder="<?php echo esc_attr($search_placeholder); ?>" value="<?php echo esc_attr(get_search_query()); ?>">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0z"></path>
                </svg>
            </form>
            <a class="button button--dark" href="<?php echo esc_url($subscribe_url !== '' ? $subscribe_url : '#newsletter-signup'); ?>">
                <?php echo esc_html($subscribe_label); ?>
            </a>
        </div>
    </div>
</header>

<div class="mobile-drawer" id="ymd-mobile-drawer" data-mobile-drawer>
    <div class="mobile-drawer__panel">
        <div class="mobile-drawer__top">
            <span class="brand__wordmark"><?php bloginfo('name'); ?>.</span>
            <button class="drawer-close" type="button" data-drawer-close>
                <span class="screen-reader-text"><?php esc_html_e('Close menu', 'yourmidnightdesk'); ?></span>
                &times;
            </button>
        </div>

        <form class="drawer-search" role="search" method="get" action="<?php echo esc_url(home_url('/')); ?>">
            <label class="screen-reader-text" for="ymd-mobile-search"><?php esc_html_e('Search recipes', 'yourmidnightdesk'); ?></label>
            <input id="ymd-mobile-search" type="search" name="s" placeholder="<?php echo esc_attr($search_placeholder); ?>" value="<?php echo esc_attr(get_search_query()); ?>">
        </form>

        <div class="mobile-drawer__groups">
            <?php foreach ($recipe_groups as $group_index => $group) : ?>
                <section class="drawer-group" data-drawer-group>
                    <button class="drawer-group__toggle" type="button" aria-expanded="false" data-drawer-toggle>
                        <span><?php echo esc_html($group['title']); ?></span>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                        </svg>
                    </button>
                    <div class="drawer-group__panel">
                        <h4 class="drawer-group__title"><?php echo esc_html($group['title']); ?></h4>
                        <ul class="drawer-links">
                            <?php foreach ($group['links'] as $link) : ?>
                                <li><a href="<?php echo esc_url($link['url']); ?>"><?php echo esc_html($link['label']); ?></a></li>
                            <?php endforeach; ?>
                        </ul>
                    </div>
                </section>
            <?php endforeach; ?>

            <div class="drawer-group is-open" data-drawer-group>
                <button class="drawer-group__toggle" type="button" aria-expanded="true" data-drawer-toggle>
                    <span><?php esc_html_e('Explore', 'yourmidnightdesk'); ?></span>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                    </svg>
                </button>
                <div class="drawer-group__panel">
                    <?php
                    if (has_nav_menu('primary')) {
                        wp_nav_menu(
                            array(
                                'theme_location' => 'primary',
                                'container'      => false,
                                'menu_class'     => 'mobile-links',
                                'fallback_cb'    => false,
                                'depth'          => 1,
                            )
                        );
                    } else {
                        ?>
                        <ul class="mobile-links">
                            <li><a href="<?php echo esc_url(home_url('/?s=tutorials')); ?>"><?php esc_html_e('Tutorials', 'yourmidnightdesk'); ?></a></li>
                            <li><a href="<?php echo esc_url(home_url('/about')); ?>"><?php esc_html_e('About', 'yourmidnightdesk'); ?></a></li>
                            <li><a href="<?php echo esc_url(home_url('/?s=shop')); ?>"><?php esc_html_e('Shop', 'yourmidnightdesk'); ?></a></li>
                        </ul>
                        <?php
                    }
                    ?>
                </div>
            </div>
        </div>

        <div class="drawer-actions">
            <a class="button button--dark" href="<?php echo esc_url($subscribe_url !== '' ? $subscribe_url : '#newsletter-signup'); ?>">
                <?php echo esc_html($subscribe_label); ?>
            </a>
        </div>
    </div>
</div>
