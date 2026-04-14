'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import ProgressRing from '@/components/ui/ProgressRing';
import LiveDot from '@/components/ui/LiveDot';
import ArticleCard from '@/components/runs/ArticleCard';
import { useRun } from '@/hooks/useRuns';
import { useRunArticles } from '@/hooks/useArticles';
import { useBlogs } from '@/hooks/useBlogs';
import { getMockBlogName } from '@/lib/mock-data';
import type { RunStatus } from '@/lib/types';

/* ----------------------------------------------------------------
   /runs/[id] page — Run Detail with progress ring, article cards
   - Header: back arrow, run code, status badge, "Stop Pipeline" button
   - Summary section: blog name, progress ring, "X of Y articles completed"
   - Article cards grid with 6-segment step progress bars
   - Polling: every 3s while status is generating/pending/running
   - Stop polling on completed/failed
   ---------------------------------------------------------------- */

const STATUS_BADGE_MAP: Record<
  RunStatus,
  { variant: 'configured' | 'running' | 'error' | 'missing'; label: string }
> = {
  pending: { variant: 'missing', label: 'Pending' },
  running: { variant: 'running', label: 'Running' },
  generating: { variant: 'running', label: 'Generating' },
  completed: { variant: 'configured', label: 'Completed' },
  failed: { variant: 'error', label: 'Failed' },
};

const ACTIVE_STATUSES = new Set<string>(['pending', 'running', 'generating']);

export default function RunDetailPage() {
  const params = useParams();
  const runId = params.id as string;

  // Get run data with conditional polling
  const { run, isLoading: runLoading, isActive } = useRun(runId);

  // Get articles for this run
  const { articles, isLoading: articlesLoading } = useRunArticles(runId);

  // Get blogs for name lookup
  const { blogs } = useBlogs();

  // Blog name
  const blogName = run
    ? blogs.find((b) => b.id === run.blog_id)?.name ?? getMockBlogName(run.blog_id)
    : '';

  // Progress calculations
  const totalArticles = run?.articles_total ?? 0;
  const completedArticles = run?.articles_completed ?? 0;
  const failedArticles = run?.articles_failed ?? 0;
  const progressPercent =
    totalArticles > 0 ? Math.round((completedArticles / totalArticles) * 100) : 0;

  // Status badge
  const status = run?.status ?? 'pending';
  const badgeInfo = STATUS_BADGE_MAP[status] ?? {
    variant: 'missing' as const,
    label: status,
  };

  // Loading state
  if (runLoading && !run) {
    return (
      <div>
        <PageHeader title="Run Detail" />
        <div className="p-8">
          <div className="flex items-center justify-center py-24">
            <div className="inline-block w-8 h-8 border-[3px] border-base border-t-transparent animate-spin rounded-none" />
            <p className="ml-4 text-muted font-bold uppercase tracking-widest text-sm">
              Loading run...
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Error / not found state (only show if we don't have fallback data)
  if (!run && !runLoading) {
    return (
      <div>
        <PageHeader title="Run Detail" />
        <div className="p-8">
          <div className="bg-white border-[3px] border-error shadow-solid-md p-8 text-center">
            <h2 className="font-black uppercase tracking-widest text-xl text-error mb-4">
              Run Not Found
            </h2>
            <p className="text-muted font-bold text-sm mb-6">
              The run you are looking for does not exist or has been removed.
            </p>
            <Link href="/runs">
              <Button variant="secondary">← Back to Runs</Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <PageHeader title={run?.run_code ?? 'Run Detail'}>
        <div className="flex items-center gap-4">
          {/* Status badge */}
          <div className="flex items-center gap-2">
            {isActive && <LiveDot active size={8} />}
            <Badge variant={badgeInfo.variant} label={badgeInfo.label} />
          </div>

          {/* Stop Pipeline button — only show for active runs */}
          {isActive && (
            <Button variant="danger" className="text-[10px] px-4 py-2">
              Stop Pipeline
            </Button>
          )}

          {/* Back to runs */}
          <Link href="/runs">
            <Button variant="secondary">← Back</Button>
          </Link>
        </div>
      </PageHeader>

      <div className="p-8">
        {/* Summary Section */}
        <div className="bg-white border-[3px] border-base shadow-solid-md p-6 mb-8">
          <div className="flex items-center gap-8">
            {/* Progress Ring */}
            <ProgressRing progress={progressPercent} size={120} strokeWidth={12} />

            {/* Summary Info */}
            <div className="flex-1">
              {/* Blog Name */}
              <p className="text-xs font-black uppercase tracking-widest text-muted mb-2">
                Blog
              </p>
              <h2 className="font-black text-xl uppercase tracking-wide mb-4">
                {blogName}
              </h2>

              {/* Article count */}
              <p className="font-bold text-base">
                <span className="font-black text-2xl">{completedArticles}</span>
                <span className="text-muted mx-1">of</span>
                <span className="font-black text-2xl">{totalArticles}</span>
                <span className="text-muted ml-2">articles completed</span>
              </p>

              {/* Failed count */}
              {failedArticles > 0 && (
                <p className="font-bold text-error text-sm mt-2 uppercase tracking-widest">
                  {failedArticles} failed
                </p>
              )}
            </div>

            {/* Run metadata */}
            <div className="text-right space-y-2">
              {run?.seed_keywords && run.seed_keywords.length > 0 && (
                <div>
                  <p className="text-[10px] font-black uppercase tracking-widest text-muted mb-1">
                    Keywords
                  </p>
                  <div className="flex flex-wrap gap-1 justify-end">
                    {run.seed_keywords.map((kw, i) => (
                      <span
                        key={i}
                        className="inline-block bg-panel border-[2px] border-base font-black uppercase tracking-widest text-[10px] px-2 py-0.5"
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Error message for failed run */}
              {run?.error_message && (
                <div className="mt-4 border-[2px] border-error bg-error/5 p-3 text-right max-w-xs ml-auto">
                  <p className="text-xs font-bold text-error">{run.error_message}</p>
                </div>
              )}
            </div>
          </div>

          {/* Polling indicator */}
          {isActive && (
            <div className="mt-4 pt-4 border-t-[2px] border-base/10 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-muted">
              <span className="inline-block w-2 h-2 bg-accent animate-sharp-blink rounded-none" />
              Live — Refreshing every 3s
            </div>
          )}
        </div>

        {/* Article Cards Grid */}
        <div className="mb-4">
          <h3 className="font-black uppercase tracking-widest text-lg text-base">
            Articles
          </h3>
        </div>

        {articlesLoading && articles.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <div className="inline-block w-8 h-8 border-[3px] border-base border-t-transparent animate-spin rounded-none" />
            <p className="ml-4 text-muted font-bold uppercase tracking-widest text-sm">
              Loading articles...
            </p>
          </div>
        ) : articles.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            {articles.map((article) => (
              <ArticleCard key={article.id} article={article} />
            ))}
          </div>
        ) : (
          <div className="bg-white border-[3px] border-base shadow-solid-md p-12 text-center">
            <p className="text-muted font-black uppercase tracking-widest text-lg">
              No Articles Yet
            </p>
            <p className="text-muted font-bold text-sm mt-2">
              Articles will appear here once the pipeline starts processing.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
