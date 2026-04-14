'use client';

import { useRouter } from 'next/navigation';
import Toggle from '@/components/ui/Toggle';
import { formatDate } from '@/lib/utils';
import type { Blog, Article } from '@/lib/types';

interface BlogCardProps {
  blog: Blog;
  articles: Article[];
  onToggle: (id: string, isActive: boolean) => void;
}

export default function BlogCard({ blog, articles, onToggle }: BlogCardProps) {
  const router = useRouter();

  // Count articles for this blog
  const blogArticles = articles.filter((a) => a.blog_id === blog.id);
  const articlesCount = blogArticles.length;

  // Find the most recent article's created_at
  const lastPublishedArticle = blogArticles
    .filter((a) => a.status === 'published' && a.completed_at)
    .sort(
      (a, b) =>
        new Date(b.completed_at!).getTime() - new Date(a.completed_at!).getTime(),
    )[0];
  const lastPublished = lastPublishedArticle
    ? formatDate(lastPublishedArticle.completed_at)
    : '—';

  const handleCardClick = () => {
    router.push(`/connections/${blog.id}`);
  };

  const handleToggleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggle(blog.id, !blog.is_active);
  };

  return (
    <div
      onClick={handleCardClick}
      className="bg-white border-[3px] border-base shadow-solid-md hover:-translate-y-1 hover:shadow-solid-lg transition-all duration-150 cursor-pointer"
    >
      <div className="p-6">
        {/* Top row: icon + toggle */}
        <div className="flex items-start justify-between mb-4">
          {/* Blog icon */}
          <div className="w-10 h-10 bg-accent border-[3px] border-base flex items-center justify-center">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="square"
              strokeLinejoin="miter"
            >
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
          </div>

          {/* Toggle switch */}
          <div onClick={handleToggleClick}>
            <Toggle
              checked={blog.is_active}
              onCheckedChange={(checked) => {
                onToggle(blog.id, checked);
              }}
            />
          </div>
        </div>

        {/* Blog name */}
        <h3 className="text-lg font-black uppercase tracking-wider mb-1">
          {blog.name}
        </h3>

        {/* Blog URL */}
        <p className="text-sm font-bold text-muted truncate">
          {blog.url}
        </p>
      </div>

      {/* Footer stats */}
      <div className="border-t-[3px] border-base px-6 py-3 flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-widest text-muted">
          {articlesCount} {articlesCount === 1 ? 'article' : 'articles'}
        </span>
        <span className="text-xs font-bold uppercase tracking-widest text-muted">
          {lastPublished === '—' ? 'Never published' : lastPublished}
        </span>
      </div>
    </div>
  );
}
