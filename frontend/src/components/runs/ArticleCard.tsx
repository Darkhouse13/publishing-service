'use client';

import Link from 'next/link';
import ProgressBar, { type ProgressBarStep } from '@/components/ui/ProgressBar';
import Button from '@/components/ui/Button';
import type { Article, ArticleStatus } from '@/lib/types';

/* ----------------------------------------------------------------
   ArticleCard — Card for a single article in the run detail page
   - Keyword tag at top
   - Title (bold) — or placeholder if still pending
   - 6-segment step progress bar
   - Status text
   - Action button: View Post / Processing / Retry
   - Error state: border-error, keyword tag bg-error text-white, error message box
   ---------------------------------------------------------------- */

interface ArticleCardProps {
  article: Article;
}

/**
 * Map article status to 6-segment step progress bar.
 * Steps: pending, generating, validating, images, publishing, done
 */
function getSteps(status: ArticleStatus): ProgressBarStep[] {
  const stepOrder: ArticleStatus[] = [
    'pending',
    'generating',
    'validating',
    'images',
    'publishing',
    'published',
  ];

  const labels = ['Pending', 'Generating', 'Validating', 'Images', 'Publishing', 'Done'];

  // Find which step index the current status maps to
  // 'failed' maps to whichever step it failed at (we'll mark the current step as failed)
  const isFailed = status === 'failed';

  // Determine the "current" step index based on status
  let currentStepIndex = stepOrder.indexOf(status);
  if (currentStepIndex === -1) {
    // 'failed' — map to step based on what was completed
    // We'll guess generating step since most failures happen there
    currentStepIndex = 1;
  }

  return labels.map((label, index) => {
    if (isFailed) {
      if (index < currentStepIndex) {
        return { label, status: 'completed' as const };
      }
      if (index === currentStepIndex) {
        return { label, status: 'failed' as const };
      }
      return { label, status: 'pending' as const };
    }

    if (index < currentStepIndex) {
      return { label, status: 'completed' as const };
    }
    if (index === currentStepIndex) {
      return { label, status: 'current' as const };
    }
    return { label, status: 'pending' as const };
  });
}

/** Get the action button based on article status */
function getActionButton(article: Article) {
  switch (article.status) {
    case 'published':
      return article.wp_permalink ? (
        <Link href={article.wp_permalink} target="_blank" rel="noopener noreferrer">
          <Button variant="secondary" className="text-[10px] px-3 py-1.5">
            View Post
          </Button>
        </Link>
      ) : (
        <Button variant="secondary" className="text-[10px] px-3 py-1.5" disabled>
          View Post
        </Button>
      );

    case 'failed':
      return (
        <Button variant="danger" className="text-[10px] px-3 py-1.5">
          Retry
        </Button>
      );

    default:
      return (
        <Button variant="secondary" className="text-[10px] px-3 py-1.5" disabled>
          Processing...
        </Button>
      );
  }
}

/** Get status display text */
function getStatusText(article: Article): string {
  switch (article.status) {
    case 'pending':
      return 'Waiting to start...';
    case 'generating':
      return 'Generating content...';
    case 'validating':
      return 'Validating content...';
    case 'images':
      return 'Generating images...';
    case 'publishing':
      return 'Publishing to WordPress...';
    case 'published':
      return 'Published successfully';
    case 'failed':
      return 'Failed';
    default:
      return article.status;
  }
}

export default function ArticleCard({ article }: ArticleCardProps) {
  const isFailed = article.status === 'failed';
  const steps = getSteps(article.status);
  const statusText = getStatusText(article);

  return (
    <div
      className={`bg-white border-[3px] shadow-solid-sm transition-all duration-150 ${
        isFailed
          ? 'border-error'
          : 'border-base hover:-translate-y-1 hover:shadow-solid-lg'
      }`}
    >
      {/* Keyword Tag */}
      <div className="px-4 pt-4">
        <span
          className={`inline-block font-black uppercase tracking-widest text-[10px] px-2 py-1 rounded-none ${
            isFailed
              ? 'bg-error text-white'
              : 'bg-panel text-base'
          }`}
        >
          {article.keyword}
        </span>
      </div>

      {/* Title */}
      <div className="px-4 pt-3 pb-2">
        <h3 className="font-black text-base leading-snug">
          {article.title ?? 'Generating title...'}
        </h3>
      </div>

      {/* Step Progress Bar */}
      <div className="px-4 py-3">
        <ProgressBar steps={steps} />
      </div>

      {/* Status Text */}
      <div className="px-4 pb-2">
        <p
          className={`text-xs font-bold uppercase tracking-widest ${
            isFailed ? 'text-error' : 'text-muted'
          }`}
        >
          {statusText}
        </p>
      </div>

      {/* Error Message */}
      {isFailed && article.error_message && (
        <div className="mx-4 mb-3 border-[2px] border-error bg-error/5 p-3">
          <p className="text-xs font-bold text-error leading-relaxed">
            {article.error_message}
          </p>
        </div>
      )}

      {/* Action Button */}
      <div className="px-4 pb-4 pt-2 flex items-center justify-end">
        {getActionButton(article)}
      </div>
    </div>
  );
}
