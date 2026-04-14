'use client';

import { formatRelativeTime } from '@/lib/utils';
import type { ActivityItem as ActivityItemType } from '@/lib/mock-data';

interface ActivityItemProps {
  item: ActivityItemType;
}

const typeStyles: Record<ActivityItemType['type'], { dot: string; text: string }> = {
  run_started: {
    dot: 'bg-accent',
    text: 'text-base',
  },
  run_completed: {
    dot: 'bg-base',
    text: 'text-base',
  },
  article_published: {
    dot: 'bg-accent',
    text: 'text-base',
  },
  article_failed: {
    dot: 'bg-error',
    text: 'text-error',
  },
  blog_connected: {
    dot: 'bg-accent',
    text: 'text-base',
  },
};

export default function ActivityItem({ item }: ActivityItemProps) {
  const style = typeStyles[item.type] ?? typeStyles.run_started;

  return (
    <div className="flex items-start gap-4 py-4 border-b-[2px] border-base/10 last:border-b-0">
      {/* Status indicator dot */}
      <div className="mt-1.5 flex-shrink-0">
        <span
          className={`inline-block w-3 h-3 ${style.dot}`}
        />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className={`font-black uppercase tracking-widest text-xs ${style.text}`}>
              {item.title}
            </p>
            <p className="mt-1 text-sm text-muted font-bold truncate">
              {item.description}
            </p>
          </div>
          <span className="flex-shrink-0 text-xs font-bold text-muted uppercase tracking-widest">
            {formatRelativeTime(item.timestamp)}
          </span>
        </div>
      </div>
    </div>
  );
}
