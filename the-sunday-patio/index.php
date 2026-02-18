<?php
/**
 * Main index template.
 *
 * @package The_Sunday_Patio
 */

get_header();

$paged       = max(1, get_query_var('paged'), get_query_var('page'));
$hero_post_id = 0;
$hero_query   = null;

if (1 === (int) $paged) {
    $sticky_posts = get_option('sticky_posts');
    $hero_args    = array(
        'post_type'           => 'post',
        'post_status'         => 'publish',
        'posts_per_page'      => 1,
        'ignore_sticky_posts' => 1,
    );

    if (!empty($sticky_posts)) {
        $hero_args['post__in'] = array_map('intval', $sticky_posts);
        $hero_args['orderby']  = 'date';
        $hero_args['order']    = 'DESC';
    }

    $hero_query = new WP_Query($hero_args);

    if (!$hero_query->have_posts()) {
        $hero_query = new WP_Query(
            array(
                'post_type'           => 'post',
                'post_status'         => 'publish',
                'posts_per_page'      => 1,
                'ignore_sticky_posts' => 1,
            )
        );
    }
}

$grid_args = array(
    'post_type'           => 'post',
    'post_status'         => 'publish',
    'posts_per_page'      => (int) get_option('posts_per_page'),
    'paged'               => $paged,
    'ignore_sticky_posts' => 1,
);
?>

<main class="flex-grow w-full max-w-7xl mx-auto px-6 py-12">
    <?php if ($hero_query instanceof WP_Query && $hero_query->have_posts()) : ?>
        <?php while ($hero_query->have_posts()) : ?>
            <?php
            $hero_query->the_post();
            $hero_post_id  = get_the_ID();
            $hero_category = tsp_get_primary_term_name($hero_post_id);
            ?>
            <section class="mb-16 relative group cursor-pointer">
                <div class="relative h-[600px] w-full overflow-hidden rounded-lg">
                    <?php if (has_post_thumbnail()) : ?>
                        <a href="<?php the_permalink(); ?>" aria-label="<?php echo esc_attr(get_the_title()); ?>">
                            <?php the_post_thumbnail('large', array('class' => 'w-full h-full object-cover transition-transform duration-700 group-hover:scale-105')); ?>
                        </a>
                    <?php else : ?>
                        <a href="<?php the_permalink(); ?>" class="w-full h-full flex items-center justify-center bg-stone-300 text-stone-600 font-serif text-2xl">
                            <?php esc_html_e('Featured Story', 'the-sunday-patio'); ?>
                        </a>
                    <?php endif; ?>

                    <div class="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent"></div>

                    <div class="absolute bottom-0 left-0 p-8 md:p-12 w-full md:w-2/3">
                        <?php if (!empty($hero_category)) : ?>
                            <span class="inline-block text-white border border-white/50 rounded-full px-4 py-1 text-xs font-bold uppercase tracking-widest mb-4 backdrop-blur-sm">
                                <?php echo esc_html($hero_category); ?>
                            </span>
                        <?php endif; ?>
                        <h2 class="font-serif text-4xl md:text-6xl text-white leading-tight mb-4 drop-shadow-md">
                            <a href="<?php the_permalink(); ?>" class="hover:text-terracotta transition-colors"><?php the_title(); ?></a>
                        </h2>
                        <p class="text-white/90 text-lg md:text-xl font-light max-w-lg mb-6 hidden md:block">
                            <?php echo esc_html(wp_trim_words(get_the_excerpt(), 28)); ?>
                        </p>
                        <a href="<?php the_permalink(); ?>" class="text-white text-sm font-bold uppercase tracking-widest border-b border-terracotta pb-1 inline-block">
                            <?php esc_html_e('Read Full Story', 'the-sunday-patio'); ?>
                        </a>
                    </div>
                </div>
            </section>
        <?php endwhile; ?>
        <?php wp_reset_postdata(); ?>
    <?php endif; ?>

    <?php if ($hero_post_id > 0 && 1 === (int) $paged) : ?>
        <?php $grid_args['post__not_in'] = array($hero_post_id); ?>
    <?php endif; ?>

    <?php $grid_query = new WP_Query($grid_args); ?>

    <div class="grid grid-cols-1 lg:grid-cols-12 gap-12">
        <div class="lg:col-span-8">
            <div class="flex items-center justify-between mb-8 border-b border-stone-200 pb-4">
                <h3 class="font-serif text-2xl text-sage-dark"><?php esc_html_e('Latest Stories', 'the-sunday-patio'); ?></h3>
                <a href="<?php echo esc_url(get_post_type_archive_link('post') ? get_post_type_archive_link('post') : home_url('/')); ?>" class="text-xs font-bold uppercase tracking-widest text-gray-500 hover:text-sage">
                    <?php esc_html_e('View Archive', 'the-sunday-patio'); ?>
                </a>
            </div>

            <?php if ($grid_query->have_posts()) : ?>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-12">
                    <?php while ($grid_query->have_posts()) : ?>
                        <?php
                        $grid_query->the_post();
                        $category = tsp_get_primary_term_name(get_the_ID());
                        ?>
                        <article class="flex flex-col hover-lift group">
                            <a href="<?php the_permalink(); ?>" class="relative aspect-[4/5] rounded-lg overflow-hidden mb-4 block">
                                <?php if (has_post_thumbnail()) : ?>
                                    <?php the_post_thumbnail('medium_large', array('class' => 'w-full h-full object-cover')); ?>
                                <?php else : ?>
                                    <span class="w-full h-full bg-stone-300 text-stone-600 flex items-center justify-center text-sm uppercase tracking-widest">
                                        <?php esc_html_e('No Image', 'the-sunday-patio'); ?>
                                    </span>
                                <?php endif; ?>
                                <?php if (!empty($category)) : ?>
                                    <span class="absolute top-4 left-4 bg-white/90 backdrop-blur text-sage-dark px-3 py-1 text-[10px] font-bold uppercase tracking-widest rounded-full">
                                        <?php echo esc_html($category); ?>
                                    </span>
                                <?php endif; ?>
                            </a>
                            <h4 class="font-serif text-xl leading-snug mb-2 group-hover:text-terracotta transition-colors">
                                <a href="<?php the_permalink(); ?>"><?php the_title(); ?></a>
                            </h4>
                            <p class="text-sm leading-relaxed text-gray-600 mb-3">
                                <?php echo esc_html(wp_trim_words(get_the_excerpt(), 16)); ?>
                            </p>
                            <a href="<?php the_permalink(); ?>" class="text-xs font-bold uppercase tracking-widest text-gray-500 mt-auto">
                                <?php esc_html_e('Read More', 'the-sunday-patio'); ?>
                            </a>
                        </article>
                    <?php endwhile; ?>
                </div>

                <?php
                $big         = 999999999;
                $pagination  = paginate_links(
                    array(
                        'base'      => str_replace($big, '%#%', esc_url(get_pagenum_link($big))),
                        'format'    => '?paged=%#%',
                        'current'   => max(1, (int) $paged),
                        'total'     => (int) $grid_query->max_num_pages,
                        'type'      => 'list',
                        'prev_text' => __('Previous', 'the-sunday-patio'),
                        'next_text' => __('Next', 'the-sunday-patio'),
                    )
                );
                ?>
                <?php if (!empty($pagination)) : ?>
                    <nav class="mt-10 text-sm [&_ul]:flex [&_ul]:flex-wrap [&_ul]:gap-3 [&_li]:list-none [&_a]:px-3 [&_a]:py-2 [&_a]:border [&_a]:border-stone-300 [&_a]:rounded [&_span]:px-3 [&_span]:py-2 [&_span]:border [&_span]:border-stone-300 [&_span]:rounded">
                        <?php echo wp_kses_post($pagination); ?>
                    </nav>
                <?php endif; ?>
            <?php else : ?>
                <p class="text-gray-600"><?php esc_html_e('No posts found.', 'the-sunday-patio'); ?></p>
            <?php endif; ?>
            <?php wp_reset_postdata(); ?>
        </div>

        <div class="hidden lg:block lg:col-span-4">
            <?php get_sidebar(); ?>
        </div>
    </div>
</main>

<?php get_footer(); ?>
