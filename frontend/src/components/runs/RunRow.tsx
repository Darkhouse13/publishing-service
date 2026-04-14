'use client';

import Link from 'next/link';
import Badge from '@/components/ui/Badge';
import LiveDot from '@/components/ui/LiveDot';
import { TableCell, TableRow } from '@/components/ui/Table';
import type { Run, RunStatus } from '@/lib/types';
import { formatRelativeTime, formatDuration, calculateDurationSeconds } from '@/lib/utils';
import { getMockBlogName } from '@/lib/mock-data';

/* ----------------------------------------------------------------
   RunRow — Table row for a single generation run
   - Run code (bold), Blog name, Status badge (blinking dot if active),
     Progress bar (segmented), Duration/timestamp
   - Clickable row → /runs/{id}
   ---------------------------------------------------------------- */

interface RunRowProps {
  run: Run;
  blogName?: string;
}

const STATUS_BADGE_MAP: Record<RunStatus, { variant: 'configured' | 'running' | 'error' | 'missing'; label: string }> = {
  pending: { variant: 'missing', label: 'Pending' },
  running: { variant: 'running', label: 'Running' },
  generating: { variant: 'running', label: 'Generating' },
  completed: { variant: 'configured', label: 'Completed' },
  failed: { variant: 'error', label: 'Failed' },
};

const ACTIVE_STATUSES = new Set<string>(['pending', 'running', 'generating']);

function getStatusBadge(status: RunStatus) {
  return STATUS_BADGE_MAP[status] ?? { variant: 'missing' as const, label: status };
}

export default function RunRow({ run, blogName }: RunRowProps) {
  const isActive = ACTIVE_STATUSES.has(run.status);
  const { variant, label } = getStatusBadge(run.status);
  const displayBlogName = blogName ?? getMockBlogName(run.blog_id);

  // Progress calculation
  const total = run.articles_total;
  const completed = run.articles_completed;
  const progressPercent = total > 0 ? (completed / total) * 100 : 0;

  // Duration
  const durationSeconds = calculateDurationSeconds(run.started_at, run.completed_at);
  const duration = formatDuration(durationSeconds);

  return (
    <Link href={`/runs/${run.id}`} className="block">
      <TableRow className="cursor-pointer hover:bg-panel/50 transition-colors">
        {/* Run Code */}
        <TableCell className="font-black uppercase tracking-wider text-base">
          {run.run_code}
        </TableCell>

        {/* Blog Name */}
        <TableCell className="text-base">
          {displayBlogName}
        </TableCell>

        {/* Status */}
        <TableCell>
          <div className="flex items-center gap-2">
            {isActive && <LiveDot active size={8} />}
            <Badge variant={variant} label={label} />
          </div>
        </TableCell>

        {/* Progress */}
        <TableCell>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              {/* Segmented progress bar */}
              <div className="flex gap-0.5 w-24">
                {total > 0 ? (
                  Array.from({ length: total }).map((_, i) => (
                    <div
                      key={i}
                      className={`h-3 flex-1 rounded-none ${
                        i < completed
                          ? 'bg-base'
                          : i === completed && isActive
                            ? 'bg-accent animate-sharp-blink'
                            : 'bg-panel border-[1px] border-base'
                      }`}
                    />
                  ))
                ) : (
                  <div className="h-3 w-24 bg-panel border-[1px] border-base rounded-none" />
                )}
              </div>
              <span className="text-xs font-bold text-muted uppercase tracking-widest whitespace-nowrap">
                {completed}/{total} articles
              </span>
            </div>
          </div>
        </TableCell>

        {/* Duration */}
        <TableCell className="text-muted text-xs">
          {duration !== '—' ? duration : '—'}
        </TableCell>

        {/* Last Updated */}
        <TableCell className="text-muted text-xs">
          {formatRelativeTime(run.completed_at ?? run.started_at ?? run.created_at)}
        </TableCell>
      </TableRow>
    </Link>
  );
}
