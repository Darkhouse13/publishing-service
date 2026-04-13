<?php
/**
 * Front-page template.
 *
 * @package YourMidnightDesk
 */

get_header();

$hero = ymd_get_hero_feature();
$moods = ymd_get_mood_cards();
$trending_cards = ymd_get_trending_cards();
$editor_feature = ymd_get_editor_feature();
$newsletter = ymd_get_newsletter_config();
$quote_social = ymd_get_quote_social_config();
$social_tiles = ymd_get_social_tiles();
$feed_filters = ymd_get_feed_filters();
$feed_query = ymd_get_recipe_feed_query(1, 'all');
$has_dynamic_feed = $feed_query->have_posts();
$feed_cards_markup = $has_dynamic_feed ? ymd_render_feed_query_cards($feed_query) : '';
?>
<main class="site-main">
    <section class="home-hero">
        <div class="container home-hero__grid">
            <div class="home-hero__copy">
                <span class="eyebrow"><?php echo esc_html($hero['eyebrow']); ?></span>
                <h1 class="display-title"><?php echo wp_kses_post($hero['title']); ?></h1>
                <p class="hero-summary"><?php echo esc_html($hero['summary']); ?></p>
                <div class="hero-actions">
                    <a class="button button--accent" href="<?php echo esc_url($hero['url']); ?>">
                        <?php echo esc_html($hero['cta_label']); ?>
                    </a>
                    <div class="hero-meta">
                        <?php if (!empty($hero['time'])) : ?>
                            <span class="pill-meta">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"></path></svg>
                                <?php echo esc_html($hero['time']); ?>
                            </span>
                        <?php endif; ?>
                        <?php if (!empty($hero['difficulty'])) : ?>
                            <span class="pill-meta">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                                <?php echo esc_html($hero['difficulty']); ?>
                            </span>
                        <?php endif; ?>
                    </div>
                </div>
            </div>

            <div class="hero-visual">
                <a class="hero-visual__card" href="<?php echo esc_url($hero['url']); ?>">
                    <img src="<?php echo esc_url($hero['image']); ?>" alt="<?php echo esc_attr(wp_strip_all_tags($hero['title'])); ?>">
                    <?php if (!empty($hero['badge'])) : ?>
                        <span class="hero-visual__badge"><?php echo esc_html($hero['badge']); ?></span>
                    <?php endif; ?>
                </a>
                <div class="hero-visual__orb"></div>
            </div>
        </div>
    </section>

    <section class="section-shell section-shell--border">
        <div class="container">
            <div class="section-heading">
                <h2 class="section-heading__title"><?php esc_html_e('Browse by Mood', 'yourmidnightdesk'); ?></h2>
                <a class="link-inline" href="<?php echo esc_url(home_url('/?s=recipes')); ?>"><?php esc_html_e('View Index', 'yourmidnightdesk'); ?></a>
            </div>
            <div class="mood-grid">
                <?php foreach ($moods as $mood) : ?>
                    <a class="mood-card" href="<?php echo esc_url($mood['url']); ?>">
                        <div class="mood-card__image">
                            <img src="<?php echo esc_url($mood['image']); ?>" alt="<?php echo esc_attr($mood['title']); ?>">
                        </div>
                        <h3 class="mood-card__title"><?php echo esc_html($mood['title']); ?></h3>
                    </a>
                <?php endforeach; ?>
            </div>
        </div>
    </section>

    <section class="section-shell section-shell--alt">
        <div class="container">
            <div class="trending-section__intro">
                <span class="eyebrow"><?php esc_html_e('Community Favorites', 'yourmidnightdesk'); ?></span>
                <h2 class="section-heading__title"><?php esc_html_e('Trending This Week', 'yourmidnightdesk'); ?></h2>
            </div>
            <div class="trending-grid">
                <?php foreach ($trending_cards as $index => $card) : ?>
                    <article class="trending-card">
                        <a class="trending-card__image" href="<?php echo esc_url($card['url']); ?>">
                            <img src="<?php echo esc_url($card['image']); ?>" alt="<?php echo esc_attr($card['title']); ?>">
                            <?php if (!empty($card['badge'])) : ?>
                                <span class="trending-card__badge"><?php echo esc_html($card['badge']); ?></span>
                            <?php endif; ?>
                        </a>
                        <div class="trending-card__body">
                            <span class="trending-card__label">
                                <span class="trending-card__dot"></span>
                                <?php echo esc_html($card['label']); ?>
                            </span>
                            <h3 class="trending-card__title"><a href="<?php echo esc_url($card['url']); ?>"><?php echo esc_html($card['title']); ?></a></h3>
                            <div class="trending-card__meta">
                                <span><?php echo esc_html(!empty($card['time']) ? $card['time'] : __('Fresh pick', 'yourmidnightdesk')); ?></span>
                                <span><?php echo esc_html(!empty($card['rating']) ? $card['rating'] : __('Trending now', 'yourmidnightdesk')); ?></span>
                            </div>
                        </div>
                    </article>
                <?php endforeach; ?>
            </div>
        </div>
    </section>

    <section class="section-shell">
        <div class="container editorial-feature__grid">
            <div class="editorial-feature__media">
                <img class="editorial-feature__main-image" src="<?php echo esc_url($editor_feature['main_image']); ?>" alt="<?php echo esc_attr($editor_feature['title']); ?>">
                <div class="editorial-feature__secondary">
                    <img src="<?php echo esc_url($editor_feature['side_image']); ?>" alt="<?php echo esc_attr($editor_feature['title']); ?>">
                </div>
            </div>

            <div class="editorial-feature__copy">
                <span class="eyebrow"><?php echo esc_html($editor_feature['label']); ?></span>
                <h2 class="section-heading__title"><?php echo esc_html($editor_feature['title']); ?></h2>
                <div class="divider-line"></div>
                <p class="hero-summary"><?php echo esc_html($editor_feature['body']); ?></p>
                <div class="editorial-feature__author">
                    <img src="<?php echo esc_url($editor_feature['author_image']); ?>" alt="<?php echo esc_attr($editor_feature['author_name']); ?>">
                    <div>
                        <p class="editorial-feature__author-name"><?php echo esc_html($editor_feature['author_name']); ?></p>
                        <p class="editorial-feature__author-role"><?php echo esc_html($editor_feature['author_role']); ?></p>
                    </div>
                </div>
                <a class="link-inline" href="<?php echo esc_url($editor_feature['url']); ?>"><?php echo esc_html($editor_feature['cta_label']); ?></a>
            </div>
        </div>
    </section>

    <section class="section-shell section-shell--border" id="fresh-from-the-kitchen">
        <div class="container" data-recipe-feed data-page="1" data-active-filter="all">
            <div class="recipe-feed__header">
                <h2 class="section-heading__title"><?php esc_html_e('Fresh from the Kitchen', 'yourmidnightdesk'); ?></h2>
                <div class="chip-bar">
                    <button class="chip-button is-active" type="button" data-feed-filter="all" aria-pressed="true"><?php esc_html_e('All', 'yourmidnightdesk'); ?></button>
                    <?php foreach ($feed_filters as $filter) : ?>
                        <button class="chip-button" type="button" data-feed-filter="<?php echo esc_attr($filter->slug); ?>" aria-pressed="false"><?php echo esc_html($filter->name); ?></button>
                    <?php endforeach; ?>
                </div>
            </div>

            <div class="recipe-grid" data-recipe-grid>
                <?php
                if ($has_dynamic_feed) {
                    echo $feed_cards_markup; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
                } else {
                    foreach (ymd_get_fallback_feed_cards() as $fallback_card) {
                        echo ymd_render_recipe_card($fallback_card); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
                    }
                }
                ?>
            </div>

            <div class="recipe-grid-controls">
                <button
                    class="button button--ghost load-more"
                    type="button"
                    data-load-more
                    <?php echo (!$has_dynamic_feed || $feed_query->max_num_pages <= 1) ? 'hidden' : ''; ?>
                >
                    <?php esc_html_e('Load More Recipes', 'yourmidnightdesk'); ?>
                </button>
            </div>
        </div>
    </section>

    <section class="section-shell newsletter-section" id="newsletter-signup">
        <div class="container newsletter-section__grid">
            <div>
                <span class="newsletter-section__eyebrow"><?php echo esc_html($newsletter['eyebrow']); ?></span>
                <h2 class="newsletter-section__title"><?php echo esc_html($newsletter['title']); ?></h2>
                <p class="newsletter-section__body"><?php echo esc_html($newsletter['body']); ?></p>
                <form class="newsletter-form" method="<?php echo esc_attr($newsletter['method']); ?>" action="<?php echo esc_url($newsletter['action_url']); ?>">
                    <label class="screen-reader-text" for="ymd-newsletter-email"><?php esc_html_e('Email address', 'yourmidnightdesk'); ?></label>
                    <input id="ymd-newsletter-email" type="email" name="email" placeholder="<?php echo esc_attr($newsletter['placeholder']); ?>">
                    <button class="button" type="<?php echo $newsletter['action_url'] !== '' ? 'submit' : 'button'; ?>" <?php disabled($newsletter['action_url'] === ''); ?>>
                        <?php echo esc_html($newsletter['button_label']); ?>
                    </button>
                </form>
                <p class="newsletter-note"><?php echo esc_html($newsletter['note']); ?></p>
            </div>

            <div class="newsletter-art" aria-hidden="true">
                <img class="newsletter-art__main" src="<?php echo esc_url($newsletter['main_image']); ?>" alt="">
                <img class="newsletter-art__secondary" src="<?php echo esc_url($newsletter['side_image']); ?>" alt="">
            </div>
        </div>
    </section>

    <section class="section-shell quote-section">
        <div class="container">
            <svg class="quote-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M14.017 21V18c0-1.105-.895-2-2-2h-.034v-1c0-1.105.895-2 2-2h2.034c1.105 0 2 .895 2 2v6h4v-6c0-3.314-2.686-6-6-6h-2.034a6.938 6.938 0 0 0-.866.055C12.443 5.093 8.973 2 4.983 2H3v20h11.017V21ZM5 4c2.761 0 5 2.239 5 5s-2.239 5-5 5V4Z"></path></svg>
            <blockquote class="quote-body"><?php echo esc_html($quote_social['quote']); ?></blockquote>
            <p class="quote-credit">&mdash; <?php echo esc_html($quote_social['quote_name'] . ', ' . $quote_social['quote_location']); ?></p>

            <div class="quote-section__divider">
                <div class="social-header">
                    <h3 class="social-title"><?php echo esc_html($quote_social['social_heading']); ?></h3>
                    <a class="link-inline" href="<?php echo esc_url($quote_social['social_url']); ?>"><?php echo esc_html($quote_social['social_label']); ?></a>
                </div>
                <div class="social-grid">
                    <?php foreach ($social_tiles as $tile) : ?>
                        <a href="<?php echo esc_url($tile['url']); ?>" target="_blank" rel="noreferrer">
                            <img src="<?php echo esc_url($tile['image']); ?>" alt="">
                        </a>
                    <?php endforeach; ?>
                </div>
            </div>
        </div>
    </section>
</main>

<?php
get_footer();
