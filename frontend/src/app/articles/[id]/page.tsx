'use client';

import { useState, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import { useArticle } from '@/hooks/useArticles';
import { useBlogs } from '@/hooks/useBlogs';
import { getMockBlogName } from '@/lib/mock-data';
import type { ArticleStatus } from '@/lib/types';

/* ----------------------------------------------------------------
   /articles/[id] page — Article Detail with two-column layout
   - Left (60%): rendered HTML article content with large serif title
   - Right (40%): SEO sidebar with 4 panels
     1. SEO Health: score badge, keyword density bar, word/H2 count grid
     2. Meta Tags: seo_title with XX/60 counter, meta_description with XX/160 counter
     3. Article Images: hero + detail thumbnails (120x120, black border)
     4. Pinterest Pin: 2:3 preview card
   - Footer: Delete Draft (text, left), Edit Article (secondary, right),
     Republish (primary black with refresh icon, right)
   - Responsive stack on mobile
   ---------------------------------------------------------------- */

/* --- Status Badge Map ----------------------------------------- */

const STATUS_BADGE_MAP: Record<
  ArticleStatus,
  { variant: 'configured' | 'missing' | 'running' | 'error'; label: string }
> = {
  pending: { variant: 'missing', label: 'Pending' },
  generating: { variant: 'running', label: 'Generating' },
  validating: { variant: 'running', label: 'Validating' },
  images: { variant: 'running', label: 'Images' },
  publishing: { variant: 'running', label: 'Publishing' },
  published: { variant: 'configured', label: 'Published' },
  failed: { variant: 'error', label: 'Failed' },
};

/* --- Delete Confirmation Dialog ------------------------------- */

function DeleteConfirmDialog({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white border-[3px] border-base shadow-solid-lg p-8 max-w-md w-full mx-4">
        <h3 className="font-black uppercase tracking-widest text-lg text-error mb-4">
          Delete Draft?
        </h3>
        <p className="font-bold text-sm text-base mb-6">
          This action cannot be undone. The article and all its data will be permanently deleted.
        </p>
        <div className="flex items-center gap-4 justify-end">
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm}>
            Delete Permanently
          </Button>
        </div>
      </div>
    </div>
  );
}

/* --- SEO Score Badge ------------------------------------------ */

function ScoreBadge({ score }: { score: number }) {
  let color = 'bg-error text-white';
  let label = 'Poor';
  if (score >= 80) {
    color = 'bg-green-600 text-white';
    label = 'Good';
  } else if (score >= 50) {
    color = 'bg-accent text-base';
    label = 'Fair';
  }

  return (
    <div className="flex items-center gap-3">
      <span
        className={`inline-flex items-center justify-center w-12 h-12 font-black text-xl border-[3px] border-base ${color}`}
      >
        {score}
      </span>
      <span className="font-black uppercase tracking-widest text-xs text-muted">
        {label}
      </span>
    </div>
  );
}

/* --- Keyword Density Bar -------------------------------------- */

function KeywordDensityBar({ density }: { density: number }) {
  const isInOptimalRange = density >= 1 && density <= 3;
  const barWidth = Math.min(density * 25, 100);
  const barColor = isInOptimalRange ? 'bg-accent' : 'bg-error';

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="font-black uppercase tracking-widest text-[10px] text-muted">
          Keyword Density
        </span>
        <span className="font-bold text-xs text-base">{density.toFixed(1)}%</span>
      </div>
      <div className="h-3 bg-panel border-[2px] border-base w-full">
        <div
          className={`h-full ${barColor} transition-all duration-300`}
          style={{ width: `${barWidth}%` }}
        />
      </div>
      <p className="text-[10px] font-bold text-muted mt-1 uppercase tracking-widest">
        Optimal range: 1–3%
      </p>
    </div>
  );
}

/* --- Metric Grid Cell ----------------------------------------- */

function MetricCell({
  label,
  current,
  target,
}: {
  label: string;
  current: number | string;
  target?: number | string;
}) {
  return (
    <div className="bg-panel border-[2px] border-base p-3">
      <p className="font-black uppercase tracking-widest text-[10px] text-muted mb-1">
        {label}
      </p>
      <p className="font-black text-xl text-base">
        {current}
        {target !== undefined && (
          <span className="text-muted font-bold text-sm">/{target}</span>
        )}
      </p>
    </div>
  );
}

/* --- Character Counter ---------------------------------------- */

function CharCounter({
  label,
  value,
  max,
}: {
  label: string;
  value: string;
  max: number;
}) {
  const len = value.length;
  const isInOptimalRange =
    max === 60 ? len >= 50 && len <= 60 : len >= 140 && len <= 160;
  const isOver = len > max;
  const counterColor = isOver
    ? 'text-error'
    : isInOptimalRange
    ? 'text-green-600'
    : 'text-muted';

  return (
    <div className="mb-4 last:mb-0">
      <div className="flex items-center justify-between mb-1">
        <span className="font-black uppercase tracking-widest text-[10px] text-muted">
          {label}
        </span>
        <span className={`font-black text-xs ${counterColor}`}>
          {len}/{max}
        </span>
      </div>
      <div className="bg-white border-[2px] border-base p-3">
        <p className="font-bold text-sm text-base leading-relaxed">{value}</p>
      </div>
    </div>
  );
}

/* --- Image Thumbnail ------------------------------------------ */

function ImageThumbnail({
  src,
  alt,
  label,
}: {
  src: string | null;
  alt: string;
  label: string;
}) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <div className="inline-block">
        <p className="font-black uppercase tracking-widest text-[10px] text-muted mb-2">
          {label}
        </p>
        <button
          type="button"
          onClick={() => src && setIsOpen(true)}
          className="block w-[120px] h-[120px] border-[3px] border-base bg-panel overflow-hidden hover:shadow-solid-sm transition-shadow duration-150"
        >
          {src ? (
            <img
              src={src}
              alt={alt}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <span className="text-[10px] font-black uppercase tracking-widest text-muted">
                No image
              </span>
            </div>
          )}
        </button>
      </div>

      {/* Lightbox */}
      {isOpen && src && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-8"
          onClick={() => setIsOpen(false)}
        >
          <div className="relative max-w-3xl max-h-[80vh] border-[3px] border-base shadow-solid-lg bg-white">
            <img
              src={src}
              alt={alt}
              className="max-w-full max-h-[80vh] object-contain"
            />
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="absolute top-2 right-2 w-8 h-8 bg-base text-white font-black flex items-center justify-center hover:bg-error transition-colors"
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </>
  );
}

/* --- Pinterest Pin Preview Card ------------------------------- */

function PinPreviewCard({
  imageUrl,
  title,
  blogUrl,
}: {
  imageUrl: string | null;
  title: string | null;
  blogUrl: string;
}) {
  return (
    <div className="border-[3px] border-base bg-panel overflow-hidden">
      {/* Pin Image - 2:3 aspect ratio */}
      <div className="w-full" style={{ aspectRatio: '2/3' }}>
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={title ?? 'Pinterest Pin'}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full bg-panel flex items-center justify-center">
            <span className="text-xs font-black uppercase tracking-widest text-muted">
              No Pin Image
            </span>
          </div>
        )}
      </div>

      {/* Pin Info */}
      <div className="p-4 border-t-[3px] border-base bg-white">
        <p className="font-black text-sm text-base line-clamp-2 leading-tight">
          {title ?? 'Untitled Pin'}
        </p>
        <p className="font-bold text-[10px] text-muted mt-2 uppercase tracking-widest truncate">
          {blogUrl}
        </p>
      </div>
    </div>
  );
}

/* --- SEO Sidebar Panel ---------------------------------------- */

function SidebarPanel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white border-[3px] border-base shadow-solid-sm p-4">
      <h3 className="font-black uppercase tracking-widest text-xs text-base mb-4 border-b-[2px] border-base pb-2">
        {title}
      </h3>
      {children}
    </div>
  );
}

/* --- Rendered HTML Content ------------------------------------ */

function ArticleContent({ html, title }: { html: string | null; title: string | null }) {
  // Compute word count and H2 count from HTML
  const wordCount = useMemo(() => {
    if (!html) return 0;
    const text = html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    return text.split(' ').filter(Boolean).length;
  }, [html]);

  const h2Count = useMemo(() => {
    if (!html) return 0;
    const matches = html.match(/<h2[^>]*>/gi);
    return matches ? matches.length : 0;
  }, [html]);

  return (
    <div>
      {/* Article Title — large serif styling */}
      {title && (
        <h1
          className="font-serif text-[40px] font-bold leading-tight text-base mb-8"
          style={{ fontFamily: 'Georgia, "Times New Roman", Times, serif' }}
        >
          {title}
        </h1>
      )}

      {/* Rendered HTML content with H2 border-bottom styling */}
      {html ? (
        <div
          className="article-content prose max-w-none font-bold text-base leading-relaxed"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <div className="bg-panel border-[2px] border-base p-8 text-center">
          <p className="font-black uppercase tracking-widest text-muted text-sm">
            Content not yet generated
          </p>
        </div>
      )}
    </div>
  );
}

/* --- Compute mock SEO metrics --------------------------------- */

function computeMetrics(article: {
  content_html: string | null;
  seo_title: string | null;
  meta_description: string | null;
  focus_keyword: string | null;
  title: string | null;
}) {
  const text = article.content_html
    ? article.content_html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
    : '';
  const wordCount = text.split(' ').filter(Boolean).length;

  const h2Count = article.content_html
    ? (article.content_html.match(/<h2[^>]*>/gi) || []).length
    : 0;

  const imageCount = article.content_html
    ? (article.content_html.match(/<img[^>]*>/gi) || []).length
    : 0;

  const internalLinks = article.content_html
    ? (article.content_html.match(/<a[^>]*href[^>]*>/gi) || []).length
    : 0;

  // Keyword density
  let keywordDensity = 0;
  if (article.focus_keyword && text.length > 0) {
    const regex = new RegExp(article.focus_keyword, 'gi');
    const matches = text.match(regex);
    const count = matches ? matches.length : 0;
    keywordDensity = wordCount > 0 ? (count / wordCount) * 100 : 0;
  }

  // SEO score (simplified heuristic)
  let score = 0;
  if (article.seo_title) score += 20;
  if (article.meta_description) score += 20;
  if (wordCount >= 800) score += 20;
  if (h2Count >= 3) score += 15;
  if (keywordDensity >= 1 && keywordDensity <= 3) score += 15;
  if (imageCount >= 1) score += 10;

  return {
    wordCount,
    h2Count,
    imageCount,
    internalLinks,
    keywordDensity,
    score: Math.min(score, 100),
  };
}

/* --- Main Page Component -------------------------------------- */

export default function ArticleDetailPage() {
  const params = useParams();
  const router = useRouter();
  const articleId = params.id as string;

  const { article, isLoading } = useArticle(articleId);
  const { blogs } = useBlogs();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Blog name and URL lookup
  const blogName = article
    ? blogs.find((b) => b.id === article.blog_id)?.name ?? getMockBlogName(article.blog_id)
    : '';
  const blogUrl = article
    ? blogs.find((b) => b.id === article.blog_id)?.url ?? ''
    : '';

  // Status badge
  const status: ArticleStatus = article?.status ?? 'pending';
  const badgeInfo = STATUS_BADGE_MAP[status] ?? {
    variant: 'missing' as const,
    label: status,
  };

  // Compute SEO metrics
  const metrics = article ? computeMetrics(article) : null;

  // Loading state
  if (isLoading && !article) {
    return (
      <div>
        <PageHeader title="Article Detail" />
        <div className="p-8">
          <div className="flex items-center justify-center py-24">
            <div className="inline-block w-8 h-8 border-[3px] border-base border-t-transparent animate-spin rounded-none" />
            <p className="ml-4 text-muted font-bold uppercase tracking-widest text-sm">
              Loading article...
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Not found state
  if (!article && !isLoading) {
    return (
      <div>
        <PageHeader title="Article Detail" />
        <div className="p-8">
          <div className="bg-white border-[3px] border-error shadow-solid-md p-8 text-center">
            <h2 className="font-black uppercase tracking-widest text-xl text-error mb-4">
              Article Not Found
            </h2>
            <p className="text-muted font-bold text-sm mb-6">
              The article you are looking for does not exist or has been removed.
            </p>
            <Link href="/articles">
              <Button variant="secondary">← Back to Articles</Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!article) return null;

  return (
    <div className="flex flex-col min-h-full">
      {/* Header */}
      <PageHeader title={article.title ?? 'Article Detail'}>
        <div className="flex items-center gap-4">
          <Badge variant={badgeInfo.variant} label={badgeInfo.label} />
          <Link href="/articles">
            <Button variant="secondary">← Back to Articles</Button>
          </Link>
        </div>
      </PageHeader>

      {/* Content Area */}
      <div className="flex-1 p-8">
        {/* Error message for failed articles */}
        {article.status === 'failed' && article.error_message && (
          <div className="mb-6 border-[3px] border-error bg-error/5 p-4">
            <p className="text-xs font-black uppercase tracking-widest text-error mb-1">
              Error
            </p>
            <p className="text-sm font-bold text-error">
              {article.error_message}
            </p>
          </div>
        )}

        {/* Two-Column Layout */}
        <div className="flex flex-col lg:flex-row gap-8">
          {/* Left Column — Article Content (60%) */}
          <div className="w-full lg:w-[60%]">
            <div className="bg-white border-[3px] border-base shadow-solid-md p-8">
              <ArticleContent
                html={article.content_html}
                title={article.title}
              />
            </div>
          </div>

          {/* Right Column — SEO Sidebar (40%) */}
          <div className="w-full lg:w-[40%] space-y-6">
            {/* Panel 1: SEO Health */}
            <SidebarPanel title="SEO Health">
              <div className="space-y-4">
                {/* Score badge */}
                <ScoreBadge score={metrics?.score ?? 0} />

                {/* Keyword density bar */}
                <KeywordDensityBar density={metrics?.keywordDensity ?? 0} />

                {/* Word / H2 / Image / Links grid */}
                <div className="grid grid-cols-2 gap-3">
                  <MetricCell
                    label="Word Count"
                    current={metrics?.wordCount ?? 0}
                    target={1200}
                  />
                  <MetricCell
                    label="H2 Count"
                    current={metrics?.h2Count ?? 0}
                    target={5}
                  />
                  <MetricCell
                    label="Images"
                    current={metrics?.imageCount ?? 0}
                  />
                  <MetricCell
                    label="Internal Links"
                    current={metrics?.internalLinks ?? 0}
                  />
                </div>
              </div>
            </SidebarPanel>

            {/* Panel 2: Meta Tags */}
            <SidebarPanel title="Meta Tags">
              <CharCounter
                label="SEO Title"
                value={article.seo_title ?? ''}
                max={60}
              />
              <CharCounter
                label="Meta Description"
                value={article.meta_description ?? ''}
                max={160}
              />
            </SidebarPanel>

            {/* Panel 3: Article Images */}
            <SidebarPanel title="Article Images">
              <div className="flex items-start gap-4">
                <ImageThumbnail
                  src={article.hero_image_url}
                  alt="Hero image"
                  label="Hero"
                />
                <ImageThumbnail
                  src={article.detail_image_url}
                  alt="Detail image"
                  label="Detail"
                />
              </div>
            </SidebarPanel>

            {/* Panel 4: Pinterest Pin Preview */}
            <SidebarPanel title="Pinterest Pin">
              <PinPreviewCard
                imageUrl={article.pin_image_url}
                title={article.pin_title ?? article.title}
                blogUrl={blogUrl}
              />
            </SidebarPanel>
          </div>
        </div>
      </div>

      {/* Footer Actions */}
      <footer className="border-t-[3px] border-base bg-white px-8 py-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          {/* Left: Delete Draft */}
          <button
            type="button"
            onClick={() => setShowDeleteConfirm(true)}
            className="font-black uppercase tracking-widest text-xs text-muted hover:text-error transition-colors duration-150 py-2"
          >
            Delete Draft
          </button>

          {/* Right: Edit Article + Republish */}
          <div className="flex items-center gap-4">
            <Button variant="secondary" className="hover:!bg-accent">
              Edit Article
            </Button>
            <Button variant="primary" className="flex items-center gap-2">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="square"
                strokeLinejoin="miter"
              >
                <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
              </svg>
              Republish
            </Button>
          </div>
        </div>
      </footer>

      {/* Delete Confirmation Dialog */}
      {showDeleteConfirm && (
        <DeleteConfirmDialog
          onConfirm={() => {
            setShowDeleteConfirm(false);
            router.push('/articles');
          }}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}

      {/* Inline styles for article content rendering */}
      <style jsx global>{`
        .article-content h2 {
          font-weight: 900;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          font-size: 1.25rem;
          margin-top: 2rem;
          margin-bottom: 1rem;
          padding-bottom: 0.5rem;
          border-bottom: 2px solid #000000;
        }
        .article-content h1 {
          display: none;
        }
        .article-content p {
          font-weight: 700;
          margin-bottom: 1rem;
          line-height: 1.75;
        }
        .article-content ul, .article-content ol {
          margin-bottom: 1rem;
          padding-left: 1.5rem;
        }
        .article-content li {
          font-weight: 700;
          margin-bottom: 0.25rem;
        }
        .article-content img {
          border: 3px solid #000000;
          margin: 1.5rem 0;
        }
        .article-content a {
          color: #000000;
          text-decoration: underline;
          font-weight: 700;
        }
        .article-content blockquote {
          border-left: 3px solid #000000;
          padding-left: 1rem;
          margin: 1rem 0;
          font-style: italic;
        }
      `}</style>
    </div>
  );
}
