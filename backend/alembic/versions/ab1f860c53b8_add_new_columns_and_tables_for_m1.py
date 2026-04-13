"""Add new columns and tables for m1 schema completion

Revision ID: ab1f860c53b8
Revises: ebd467d9f074
Create Date: 2026-04-13 21:00:00.000000

Adds:
- blogs: profile_prompt, fallback_category, deprioritized_category,
         category_keywords, pinterest_board_map, seed_keywords
- pipeline_configs: llm_model, image_model, trends_region, trends_range,
                    trends_top_n, pinclicks_max_records, winners_count,
                    publish_status, csv_cadence_minutes, pin_template_mode,
                    max_concurrent_articles
                  Removes: articles_per_week, content_tone, default_category
- articles: blog_id FK, run_id nullable, seo_title, meta_description,
            focus_keyword, content_markdown, content_html,
            hero_image_prompt, hero_image_url, detail_image_prompt,
            detail_image_url, pin_title, pin_description,
            pin_text_overlay, pin_image_url, category_name,
            generation_attempts, validation_errors, brain_output
- runs: run_code, phase, seed_keywords, config_snapshot,
        results_summary, csv_path

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab1f860c53b8'
down_revision: Union[str, None] = 'ebd467d9f074'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. Add new columns to blogs ---
    op.add_column('blogs', sa.Column('profile_prompt', sa.Text(), nullable=False, server_default=''))
    op.add_column('blogs', sa.Column('fallback_category', sa.String(255), nullable=False, server_default=''))
    op.add_column('blogs', sa.Column('deprioritized_category', sa.String(255), nullable=False, server_default=''))
    op.add_column('blogs', sa.Column('category_keywords', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('blogs', sa.Column('pinterest_board_map', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('blogs', sa.Column('seed_keywords', sa.JSON(), nullable=False, server_default='[]'))

    # --- 2. Add new columns to pipeline_configs ---
    op.add_column('pipeline_configs', sa.Column('llm_model', sa.String(255), nullable=False, server_default='deepseek-chat'))
    op.add_column('pipeline_configs', sa.Column('image_model', sa.String(255), nullable=False, server_default='fal-ai/flux/dev'))
    op.add_column('pipeline_configs', sa.Column('trends_region', sa.String(255), nullable=False, server_default='GLOBAL'))
    op.add_column('pipeline_configs', sa.Column('trends_range', sa.String(255), nullable=False, server_default='12m'))
    op.add_column('pipeline_configs', sa.Column('trends_top_n', sa.Integer(), nullable=False, server_default='20'))
    op.add_column('pipeline_configs', sa.Column('pinclicks_max_records', sa.Integer(), nullable=False, server_default='25'))
    op.add_column('pipeline_configs', sa.Column('winners_count', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('pipeline_configs', sa.Column('publish_status', sa.String(255), nullable=False, server_default='draft'))
    op.add_column('pipeline_configs', sa.Column('csv_cadence_minutes', sa.Integer(), nullable=False, server_default='240'))
    op.add_column('pipeline_configs', sa.Column('pin_template_mode', sa.String(255), nullable=False, server_default='center_strip'))
    op.add_column('pipeline_configs', sa.Column('max_concurrent_articles', sa.Integer(), nullable=False, server_default='3'))

    # --- 3. Remove deprecated columns from pipeline_configs ---
    op.drop_column('pipeline_configs', 'articles_per_week')
    op.drop_column('pipeline_configs', 'content_tone')
    op.drop_column('pipeline_configs', 'default_category')

    # --- 4. Create runs table ---
    op.create_table(
        'runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('blog_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('run_code', sa.String(50), nullable=False),
        sa.Column('phase', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('seed_keywords', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('config_snapshot', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('results_summary', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('csv_path', sa.String(1000), nullable=True),
        sa.Column('articles_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('articles_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('articles_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.String(4096), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['blog_id'], ['blogs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_code'),
    )

    # --- 5. Create articles table ---
    op.create_table(
        'articles',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('blog_id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=True),
        sa.Column('keyword', sa.String(1024), nullable=False),
        sa.Column('title', sa.String(1024), nullable=True),
        sa.Column('slug', sa.String(1024), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('wp_post_id', sa.Integer(), nullable=True),
        sa.Column('wp_permalink', sa.String(2048), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        # Content fields
        sa.Column('seo_title', sa.String(1024), nullable=True),
        sa.Column('meta_description', sa.Text(), nullable=True),
        sa.Column('focus_keyword', sa.String(255), nullable=True),
        sa.Column('content_markdown', sa.Text(), nullable=True),
        sa.Column('content_html', sa.Text(), nullable=True),
        # Image fields
        sa.Column('hero_image_prompt', sa.Text(), nullable=True),
        sa.Column('hero_image_url', sa.String(2048), nullable=True),
        sa.Column('detail_image_prompt', sa.Text(), nullable=True),
        sa.Column('detail_image_url', sa.String(2048), nullable=True),
        # Pinterest fields
        sa.Column('pin_title', sa.String(255), nullable=True),
        sa.Column('pin_description', sa.Text(), nullable=True),
        sa.Column('pin_text_overlay', sa.String(255), nullable=True),
        sa.Column('pin_image_url', sa.String(2048), nullable=True),
        # Metadata fields
        sa.Column('category_name', sa.String(255), nullable=True),
        sa.Column('generation_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('validation_errors', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('brain_output', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['blog_id'], ['blogs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    # Disable FK enforcement for SQLite so drop_table works cleanly
    op.execute('PRAGMA foreign_keys=OFF')

    # --- 5. Drop articles table ---
    op.drop_table('articles')

    # --- 4. Drop runs table ---
    op.drop_table('runs')

    # Re-enable FK enforcement
    op.execute('PRAGMA foreign_keys=ON')

    # --- 3. Restore deprecated columns to pipeline_configs ---
    op.add_column('pipeline_configs', sa.Column('articles_per_week', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('pipeline_configs', sa.Column('content_tone', sa.String(255), nullable=False, server_default='informative'))
    op.add_column('pipeline_configs', sa.Column('default_category', sa.String(255), nullable=False, server_default=''))

    # --- 2. Remove new columns from pipeline_configs ---
    op.drop_column('pipeline_configs', 'max_concurrent_articles')
    op.drop_column('pipeline_configs', 'pin_template_mode')
    op.drop_column('pipeline_configs', 'csv_cadence_minutes')
    op.drop_column('pipeline_configs', 'publish_status')
    op.drop_column('pipeline_configs', 'winners_count')
    op.drop_column('pipeline_configs', 'pinclicks_max_records')
    op.drop_column('pipeline_configs', 'trends_top_n')
    op.drop_column('pipeline_configs', 'trends_range')
    op.drop_column('pipeline_configs', 'trends_region')
    op.drop_column('pipeline_configs', 'image_model')
    op.drop_column('pipeline_configs', 'llm_model')

    # --- 1. Remove new columns from blogs ---
    op.drop_column('blogs', 'seed_keywords')
    op.drop_column('blogs', 'pinterest_board_map')
    op.drop_column('blogs', 'category_keywords')
    op.drop_column('blogs', 'deprioritized_category')
    op.drop_column('blogs', 'fallback_category')
    op.drop_column('blogs', 'profile_prompt')
