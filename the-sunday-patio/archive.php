<?php
/**
 * Archive template.
 *
 * @package The_Sunday_Patio
 */

get_header();
?>

<main class="flex-grow w-full max-w-7xl mx-auto px-6 py-12">
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-12">
        <div class="lg:col-span-8">
            <?php the_archive_title('<h1 class="text-3xl font-serif font-bold mb-8">', '</h1>'); ?>
            <?php if (get_the_archive_description()) : ?>
                <div class="text-gray-600 mb-8 prose max-w-none">
                    <?php the_archive_description(); ?>
                </div>
            <?php endif; ?>

            <?php if (have_posts()) : ?>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-12">
                    <?php while (have_posts()) : ?>
                        <?php
                        the_post();
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

                            <h2 class="font-serif text-xl leading-snug mb-2 group-hover:text-terracotta transition-colors">
                                <a href="<?php the_permalink(); ?>"><?php the_title(); ?></a>
                            </h2>

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
                $big        = 999999999;
                $paged      = max(1, get_query_var('paged'), get_query_var('page'));
                $pagination = paginate_links(
                    array(
                        'base'      => str_replace($big, '%#%', esc_url(get_pagenum_link($big))),
                        'format'    => '?paged=%#%',
                        'current'   => max(1, (int) $paged),
                        'total'     => (int) $wp_query->max_num_pages,
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
        </div>

        <div class="hidden lg:block lg:col-span-4">
            <?php get_sidebar(); ?>
        </div>
    </div>
</main>

<?php get_footer(); ?>
