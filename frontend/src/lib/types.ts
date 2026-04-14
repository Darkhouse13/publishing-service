// ---------------------------------------------------------------------------
// TypeScript interfaces matching backend Pydantic schemas
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Blog
// ---------------------------------------------------------------------------

export interface Blog {
  id: string;
  name: string;
  slug: string;
  url: string;
  wp_username: string;
  wp_application_password: string; // always masked as "********" in responses
  is_active: boolean;
  created_at: string;
  updated_at: string;
  profile_prompt: string;
  fallback_category: string;
  deprioritized_category: string;
  category_keywords: Record<string, string[]>;
  pinterest_board_map: Record<string, string>;
  seed_keywords: string[];
}

export interface BlogCreate {
  name: string;
  url: string;
  wp_username: string;
  wp_application_password: string;
  profile_prompt?: string;
  fallback_category?: string;
  deprioritized_category?: string;
  category_keywords?: Record<string, string[]>;
  pinterest_board_map?: Record<string, string>;
  seed_keywords?: string[];
}

export interface BlogUpdate {
  name?: string;
  url?: string;
  wp_username?: string;
  wp_application_password?: string;
  is_active?: boolean;
  profile_prompt?: string;
  fallback_category?: string;
  deprioritized_category?: string;
  category_keywords?: Record<string, string[]>;
  pinterest_board_map?: Record<string, string>;
  seed_keywords?: string[];
}

// ---------------------------------------------------------------------------
// PipelineConfig
// ---------------------------------------------------------------------------

export interface PipelineConfig {
  id: string;
  blog_id: string;
  llm_provider: string;
  image_provider: string;
  llm_model: string;
  image_model: string;
  trends_region: string;
  trends_range: string;
  trends_top_n: number;
  pinclicks_max_records: number;
  winners_count: number;
  publish_status: string;
  csv_cadence_minutes: number;
  pin_template_mode: string;
  max_concurrent_articles: number;
  created_at: string;
  updated_at: string;
}

export interface PipelineConfigUpdate {
  llm_provider?: string;
  image_provider?: string;
  llm_model?: string;
  image_model?: string;
  trends_region?: string;
  trends_range?: string;
  trends_top_n?: number;
  pinclicks_max_records?: number;
  winners_count?: number;
  publish_status?: string;
  csv_cadence_minutes?: number;
  pin_template_mode?: string;
  max_concurrent_articles?: number;
}

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------

export type RunStatus =
  | 'pending'
  | 'running'
  | 'generating'
  | 'completed'
  | 'failed';

export type RunPhase =
  | 'pending'
  | 'trends'
  | 'pinclicks'
  | 'analysis'
  | 'generating'
  | 'publishing'
  | 'completed'
  | 'failed';

export interface Run {
  id: string;
  blog_id: string;
  status: RunStatus;
  run_code: string;
  phase: RunPhase;
  seed_keywords: string[];
  config_snapshot: Record<string, unknown>;
  results_summary: Record<string, unknown>;
  csv_path: string | null;
  articles_total: number;
  articles_completed: number;
  articles_failed: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface RunCreate {
  blog_id: string;
  keywords: string[];
}

// ---------------------------------------------------------------------------
// Article
// ---------------------------------------------------------------------------

export type ArticleStatus =
  | 'pending'
  | 'generating'
  | 'validating'
  | 'images'
  | 'publishing'
  | 'published'
  | 'failed';

export interface Article {
  id: string;
  blog_id: string;
  run_id: string | null;
  keyword: string;
  title: string | null;
  slug: string | null;
  status: ArticleStatus;
  wp_post_id: number | null;
  wp_permalink: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  // Content fields
  seo_title: string | null;
  meta_description: string | null;
  focus_keyword: string | null;
  content_markdown: string | null;
  content_html: string | null;
  // Image fields
  hero_image_prompt: string | null;
  hero_image_url: string | null;
  detail_image_prompt: string | null;
  detail_image_url: string | null;
  // Pinterest fields
  pin_title: string | null;
  pin_description: string | null;
  pin_text_overlay: string | null;
  pin_image_url: string | null;
  // Metadata fields
  category_name: string | null;
  generation_attempts: number;
  validation_errors: string[];
  brain_output: unknown;
}

export interface ArticleCreate {
  blog_id: string;
  topic: string;
  vibe?: string;
  focus_keyword?: string;
}

// ---------------------------------------------------------------------------
// Credential
// ---------------------------------------------------------------------------

export interface Credential {
  id: string;
  provider: string;
  key_name: string;
  created_at: string;
  updated_at: string;
}

export interface CredentialCreate {
  provider: string;
  key_name: string;
  value: string;
}

// ---------------------------------------------------------------------------
// API Response wrappers
// ---------------------------------------------------------------------------

export interface ApiListResponse<T> {
  items: T[];
  total: number;
}

export interface ApiError {
  detail: string;
}
