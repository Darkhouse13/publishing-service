'use client';

import { useState, useMemo, FormEvent, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import Select from '@/components/ui/Select';
import Input from '@/components/ui/Input';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import ProgressRing from '@/components/ui/ProgressRing';
import LiveDot from '@/components/ui/LiveDot';
import { useBlogs } from '@/hooks/useBlogs';
import { useArticle } from '@/hooks/useArticles';
import { articlesApi } from '@/lib/api';
import { VIBE_OPTIONS, mockArticles } from '@/lib/mock-data';
import type { ArticleStatus } from '@/lib/types';

/* ----------------------------------------------------------------
   /articles/new page — Create new article
   - Form: blog selector, topic input, vibe chips (single select),
     focus keyword input
   - Submit → POST /api/v1/articles with { blog_id, topic, vibe, focus_keyword }
   - Redirect to /articles/{id} and show live phase progress
   - Polls GET /api/v1/articles/{id} every 3s until terminal state
   ---------------------------------------------------------------- */

interface FormErrors {
  blog_id?: string;
  topic?: string;
}

/* --- Article Phases ------------------------------------------- */

const ARTICLE_PHASES: { key: ArticleStatus; label: string }[] = [
  { key: 'pending', label: 'Pending' },
  { key: 'generating', label: 'Generating' },
  { key: 'validating', label: 'Validating' },
  { key: 'publishing', label: 'Publishing' },
  { key: 'published', label: 'Published' },
];

function getPhaseIndex(status: ArticleStatus): number {
  const idx = ARTICLE_PHASES.findIndex((p) => p.key === status);
  return idx >= 0 ? idx : 0;
}

function isTerminalStatus(status: ArticleStatus): boolean {
  return status === 'published' || status === 'failed';
}

function getProgressPercentage(status: ArticleStatus): number {
  const idx = getPhaseIndex(status);
  // Map to percentage: 0->0, 1->25, 2->50, 3->75, 4->100
  if (status === 'published') return 100;
  if (status === 'failed') return 0;
  return Math.min(idx * 25, 100);
}

/* --- Vibe Chip Component -------------------------------------- */

function VibeChip({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2 border-[3px] border-base font-black uppercase tracking-widest text-xs transition-all duration-150 ${
        selected
          ? 'bg-accent text-base'
          : 'bg-white text-base hover:bg-panel'
      }`}
    >
      {label}
    </button>
  );
}

/* --- Phase Progress Component --------------------------------- */

function PhaseProgress({ status }: { status: ArticleStatus }) {
  const currentIdx = getPhaseIndex(status);
  const percentage = getProgressPercentage(status);

  return (
    <div className="bg-white border-[3px] border-base shadow-solid-md p-6">
      <h3 className="font-black uppercase tracking-widest text-xs text-base mb-4">
        Article Progress
      </h3>

      <div className="flex items-center justify-center mb-6">
        <ProgressRing progress={percentage} size={120} strokeWidth={10} />
      </div>

      {/* Phase steps */}
      <div className="space-y-2">
        {ARTICLE_PHASES.map((phase, idx) => {
          const isComplete = idx < currentIdx || status === 'published';
          const isCurrent = idx === currentIdx && !isTerminalStatus(status);
          const isFailed = status === 'failed' && idx === currentIdx;

          return (
            <div
              key={phase.key}
              className={`flex items-center gap-3 px-3 py-2 border-[2px] ${
                isFailed
                  ? 'border-error bg-error/5'
                  : isCurrent
                  ? 'border-accent bg-accent/10'
                  : isComplete
                  ? 'border-base bg-accent/5'
                  : 'border-muted/30 bg-panel'
              }`}
            >
              {/* Status indicator */}
              {isCurrent && !isFailed && <LiveDot />}
              {isComplete && !isCurrent && (
                <span className="text-sm font-black text-base">✓</span>
              )}
              {isFailed && (
                <span className="text-sm font-black text-error">✗</span>
              )}
              {!isComplete && !isCurrent && !isFailed && (
                <span className="w-2 h-2 bg-muted/40 inline-block" />
              )}

              <span
                className={`text-xs font-black uppercase tracking-widest ${
                  isFailed
                    ? 'text-error'
                    : isCurrent
                    ? 'text-base'
                    : isComplete
                    ? 'text-base'
                    : 'text-muted'
                }`}
              >
                {phase.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* --- Main Page Component -------------------------------------- */

export default function NewArticlePage() {
  const router = useRouter();
  const { blogs } = useBlogs();

  // Form state
  const [selectedBlogId, setSelectedBlogId] = useState('');
  const [topic, setTopic] = useState('');
  const [selectedVibe, setSelectedVibe] = useState('');
  const [focusKeyword, setFocusKeyword] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Post-creation polling state
  const [createdArticleId, setCreatedArticleId] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Use SWR hook for polling the created article
  const { article, mutate: mutateArticle } = useArticle(createdArticleId);

  // Determine if we're in the polling/progress phase
  const showProgress = createdArticleId !== null;
  const articleStatus: ArticleStatus = article?.status ?? 'pending';
  const isTerminal = article ? isTerminalStatus(articleStatus) : false;

  // Blog options for dropdown
  const blogOptions = useMemo(
    () => [
      { value: '', label: 'Select a blog...' },
      ...blogs.map((blog) => ({ value: blog.id, label: blog.name })),
    ],
    [blogs],
  );

  // Poll every 3s when article is created and not in terminal state
  useEffect(() => {
    if (!createdArticleId) return;

    // Clear any existing timer
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    if (!isTerminal) {
      pollTimerRef.current = setInterval(() => {
        mutateArticle();
      }, 3000);
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [createdArticleId, isTerminal, mutateArticle]);

  // Redirect to article detail page when terminal state reached
  useEffect(() => {
    if (createdArticleId && isTerminal) {
      // Small delay so user can see the final state
      const timeout = setTimeout(() => {
        router.push(`/articles/${createdArticleId}`);
      }, 1500);

      return () => clearTimeout(timeout);
    }
  }, [createdArticleId, isTerminal, router]);

  function validate(): FormErrors {
    const newErrors: FormErrors = {};

    if (!selectedBlogId) {
      newErrors.blog_id = 'Please select a blog';
    }

    if (!topic.trim()) {
      newErrors.topic = 'Topic is required';
    }

    return newErrors;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitError(null);

    const validationErrors = validate();
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    setIsSubmitting(true);
    try {
      const newArticle = await articlesApi.create({
        blog_id: selectedBlogId,
        topic: topic.trim(),
        vibe: selectedVibe || undefined,
        focus_keyword: focusKeyword.trim() || undefined,
      });

      setCreatedArticleId(newArticle.id);

      // For demo with mock data: simulate progress by adding to mock articles
      // In production, the backend will handle status transitions
    } catch (err) {
      setIsSubmitting(false);
      setSubmitError(
        err instanceof Error ? err.message : 'Failed to create article. Please try again.',
      );
    }
  }

  /* --- Progress View (after article creation) ----------------- */
  if (showProgress) {
    return (
      <div>
        <PageHeader title="Creating Article">
          <Link href="/articles">
            <Button type="button" variant="secondary">
              ← Back
            </Button>
          </Link>
        </PageHeader>

        <div className="p-8">
          <div className="max-w-lg mx-auto space-y-6">
            {/* Article info */}
            <div className="bg-white border-[3px] border-base shadow-solid-md p-6">
              <h3 className="font-black uppercase tracking-widest text-xs text-muted mb-2">
                Topic
              </h3>
              <p className="font-bold text-base text-lg">{topic}</p>

              {focusKeyword && (
                <>
                  <h3 className="font-black uppercase tracking-widest text-xs text-muted mb-1 mt-4">
                    Focus Keyword
                  </h3>
                  <p className="font-bold text-base">{focusKeyword}</p>
                </>
              )}

              {selectedVibe && (
                <>
                  <h3 className="font-black uppercase tracking-widest text-xs text-muted mb-1 mt-4">
                    Vibe
                  </h3>
                  <Badge variant="configured" label={selectedVibe} />
                </>
              )}
            </div>

            {/* Phase progress */}
            <PhaseProgress status={articleStatus} />

            {/* Failed state */}
            {articleStatus === 'failed' && article?.error_message && (
              <div className="border-[3px] border-error bg-error/5 p-4">
                <p className="text-xs font-black uppercase tracking-widest text-error mb-1">
                  Error
                </p>
                <p className="text-sm font-bold text-error">
                  {article.error_message}
                </p>
              </div>
            )}

            {/* Redirect notice */}
            {isTerminal && articleStatus === 'published' && (
              <div className="text-center">
                <p className="text-sm font-bold text-muted uppercase tracking-widest">
                  Redirecting to article...
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  /* --- Form View (initial state) ------------------------------ */
  return (
    <div>
      <PageHeader title="New Article">
        <Link href="/articles">
          <Button type="button" variant="secondary">
            ← Back
          </Button>
        </Link>
      </PageHeader>

      <div className="p-8">
        <form onSubmit={handleSubmit} className="max-w-2xl">
          {/* Server error */}
          {submitError && (
            <div className="mb-6 border-[3px] border-error bg-error/5 p-4">
              <p className="text-sm font-bold text-error uppercase tracking-widest">
                {submitError}
              </p>
            </div>
          )}

          {/* Blog Selector */}
          <div className="mb-6">
            <Select
              label="Blog"
              options={blogOptions}
              value={selectedBlogId}
              onChange={(e) => {
                setSelectedBlogId(e.target.value);
                if (errors.blog_id) {
                  setErrors((prev) => ({ ...prev, blog_id: undefined }));
                }
              }}
              error={errors.blog_id}
            />
          </div>

          {/* Topic Input */}
          <div className="mb-6">
            <Input
              label="Topic / Title"
              placeholder="e.g., 10 Weekend Brunch Ideas for a Relaxing Sunday"
              value={topic}
              onChange={(e) => {
                setTopic(e.target.value);
                if (errors.topic) {
                  setErrors((prev) => ({ ...prev, topic: undefined }));
                }
              }}
              error={errors.topic}
            />
          </div>

          {/* Vibe Selector (chips, single select) */}
          <div className="mb-6">
            <label className="block font-black uppercase tracking-widest text-xs text-base mb-2">
              Vibe
            </label>
            <div className="flex flex-wrap gap-2">
              {VIBE_OPTIONS.map((vibe) => (
                <VibeChip
                  key={vibe}
                  label={vibe}
                  selected={selectedVibe === vibe}
                  onClick={() => {
                    setSelectedVibe(selectedVibe === vibe ? '' : vibe);
                  }}
                />
              ))}
            </div>
            <p className="mt-2 text-xs font-bold text-muted uppercase tracking-widest">
              Optional — select the tone for your article
            </p>
          </div>

          {/* Focus Keyword Input */}
          <div className="mb-8">
            <Input
              label="Focus Keyword"
              placeholder="e.g., weekend brunch ideas"
              value={focusKeyword}
              onChange={(e) => setFocusKeyword(e.target.value)}
            />
            <p className="mt-2 text-xs font-bold text-muted uppercase tracking-widest">
              Optional — primary keyword for SEO optimization
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-4 border-t-[3px] border-base pt-6">
            <Button type="submit" variant="primary" disabled={isSubmitting}>
              {isSubmitting ? 'Creating Article...' : 'Create Article'}
            </Button>
            <Link href="/articles">
              <Button type="button" variant="secondary">
                Cancel
              </Button>
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
