<?php
/**
 * Page template.
 *
 * @package The_Sunday_Patio
 */

get_header();
?>

<main class="flex-grow w-full max-w-5xl mx-auto px-6 py-12">
    <?php if (have_posts()) : ?>
        <?php while (have_posts()) : ?>
            <?php the_post(); ?>
            <article <?php post_class('max-w-none'); ?>>
                <header class="max-w-4xl mx-auto text-center mb-12">
                    <h1 class="font-serif text-4xl md:text-5xl text-charcoal leading-tight mb-6"><?php the_title(); ?></h1>
                </header>

                <?php if (has_post_thumbnail()) : ?>
                    <div class="w-full h-[400px] md:h-[550px] mb-10 rounded-xl overflow-hidden">
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
        <p class="text-gray-600"><?php esc_html_e('Page not found.', 'the-sunday-patio'); ?></p>
    <?php endif; ?>
</main>

<?php get_footer(); ?>
