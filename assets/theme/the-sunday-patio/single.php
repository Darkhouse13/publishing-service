<?php
/**
 * Single post template.
 *
 * @package The_Sunday_Patio
 */

get_header();
?>

<main class="flex-grow w-full max-w-7xl mx-auto px-6 py-12">
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-12">
        <div class="lg:col-span-8 lg:col-start-1">
            <?php if (have_posts()) : ?>
                <?php while (have_posts()) : ?>
                    <?php
                    the_post();
                    $category = tsp_get_primary_term_name(get_the_ID());
                    ?>
                    <article class="max-w-none">
                        <header class="max-w-4xl mx-auto text-center mb-12">
                            <?php if (!empty($category)) : ?>
                                <span class="inline-block text-terracotta border border-terracotta rounded-full px-4 py-1 text-xs font-bold uppercase tracking-widest mb-6">
                                    <?php echo esc_html($category); ?>
                                </span>
                            <?php endif; ?>
                            <h1 class="font-serif text-4xl md:text-6xl text-charcoal leading-tight mb-6"><?php the_title(); ?></h1>
                            <div class="flex items-center justify-center space-x-4 text-sm font-medium text-gray-500">
                                <span><?php the_author_posts_link(); ?></span>
                                <span class="w-1 h-1 bg-gray-300 rounded-full"></span>
                                <time datetime="<?php echo esc_attr(get_the_date('c')); ?>"><?php echo esc_html(get_the_date()); ?></time>
                            </div>
                        </header>

                        <?php if (has_post_thumbnail()) : ?>
                            <div class="w-full h-[500px] md:h-[700px] mb-12 rounded-xl overflow-hidden">
                                <?php the_post_thumbnail('full', array('class' => 'w-full h-full object-cover')); ?>
                            </div>
                        <?php endif; ?>

                        <div class="prose prose-lg prose-stone max-w-none font-serif text-charcoal">
                            <?php the_content(); ?>
                            <?php
                            wp_link_pages(
                                array(
                                    'before' => '<div class="mt-8">' . esc_html__('Pages:', 'the-sunday-patio'),
                                    'after'  => '</div>',
                                )
                            );
                            ?>
                        </div>
                    </article>
                <?php endwhile; ?>
            <?php else : ?>
                <p class="text-gray-600"><?php esc_html_e('Post not found.', 'the-sunday-patio'); ?></p>
            <?php endif; ?>
        </div>

        <?php get_sidebar(); ?>
    </div>
</main>

<?php get_footer(); ?>
