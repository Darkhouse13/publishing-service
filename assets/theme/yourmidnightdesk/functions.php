<?php
/**
 * Theme bootstrap for Your Midnight Desk.
 *
 * @package YourMidnightDesk
 */

if (!defined('ABSPATH')) {
    exit;
}

define('YMD_THEME_VERSION', '1.0.0');
define('YMD_THEME_PATH', get_template_directory());
define('YMD_THEME_URI', get_template_directory_uri());

require_once YMD_THEME_PATH . '/inc/core.php';
require_once YMD_THEME_PATH . '/inc/customizer.php';
require_once YMD_THEME_PATH . '/inc/meta.php';
