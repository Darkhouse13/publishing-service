'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
} from '@/components/ui/Table';
import { useArticles } from '@/hooks/useArticles';
import { useBlogs } from '@/hooks/useBlogs';
import type { ArticleStatus } from '@/lib/types';
import { formatDate } from '@/lib/utils';
import { getMockBlogName } from '@/lib/mock-data';

/* ----------------------------------------------------------------
   /articles page — Articles list with table
   - Columns: Title, Blog, Status badge, Created date, Actions
   - Status badge colors: pending=muted, generating=accent,
     validating=accent, publishing=accent, published=base, failed=error
   - Click row → /articles/{id}
   - 'New Article' button → /articles/new
   - Empty state: 'No articles yet' with CTA
   - Loading state: skeleton with animate-pulse
   ---------------------------------------------------------------- */

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

function getStatusBadge(status: ArticleStatus) {
  return STATUS_BADGE_MAP[status] ?? { variant: 'missing' as const, label: status };
}

/* --- Article Row Component ------------------------------------ */

function ArticleTableRow({
  article,
  blogName,
  onClick,
}: {
  article: {
    id: string;
    title: string | null;
    keyword: string;
    status: ArticleStatus;
    created_at: string;
  };
  blogName: string;
  onClick: () => void;
}) {
  const { variant, label } = getStatusBadge(article.status);

  return (
    <TableRow
      className="cursor-pointer hover:bg-panel/50 transition-colors"
      onClick={onClick}
    >
      {/* Title */}
      <TableCell className="font-bold text-base max-w-[400px]">
        {article.title ?? (
          <span className="text-muted italic">Untitled — {article.keyword}</span>
        )}
      </TableCell>

      {/* Blog */}
      <TableCell className="text-base">
        {blogName}
      </TableCell>

      {/* Status */}
      <TableCell>
        <Badge variant={variant} label={label} />
      </TableCell>

      {/* Created */}
      <TableCell className="text-muted text-xs">
        {formatDate(article.created_at)}
      </TableCell>

      {/* Actions */}
      <TableCell>
        <span className="text-xs font-black uppercase tracking-widest text-muted hover:text-base transition-colors">
          View →
        </span>
      </TableCell>
    </TableRow>
  );
}

/* --- Skeleton Row Component ----------------------------------- */

function SkeletonRow() {
  return (
    <TableRow>
      <TableCell>
        <div className="h-4 w-64 bg-panel animate-pulse rounded-none" />
      </TableCell>
      <TableCell>
        <div className="h-4 w-32 bg-panel animate-pulse rounded-none" />
      </TableCell>
      <TableCell>
        <div className="h-5 w-20 bg-panel animate-pulse rounded-none" />
      </TableCell>
      <TableCell>
        <div className="h-4 w-24 bg-panel animate-pulse rounded-none" />
      </TableCell>
      <TableCell>
        <div className="h-4 w-12 bg-panel animate-pulse rounded-none" />
      </TableCell>
    </TableRow>
  );
}

/* --- Main Page ------------------------------------------------ */

export default function ArticlesPage() {
  const router = useRouter();
  const { articles, isLoading } = useArticles();
  const { blogs } = useBlogs();

  // Build blog name lookup map
  const blogNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const blog of blogs) {
      map[blog.id] = blog.name;
    }
    return map;
  }, [blogs]);

  return (
    <div>
      <PageHeader title="Articles">
        <Button variant="primary" onClick={() => router.push('/articles/new')}>
          + New Article
        </Button>
      </PageHeader>

      <div className="p-8">
        <div className="bg-white border-[3px] border-base shadow-solid-md overflow-hidden rounded-none">
          {isLoading ? (
            /* Loading skeleton state */
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Title</TableHeaderCell>
                  <TableHeaderCell>Blog</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                  <TableHeaderCell>Created</TableHeaderCell>
                  <TableHeaderCell>Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Array.from({ length: 5 }).map((_, i) => (
                  <SkeletonRow key={i} />
                ))}
              </TableBody>
            </Table>
          ) : articles.length > 0 ? (
            /* Articles table */
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Title</TableHeaderCell>
                  <TableHeaderCell>Blog</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                  <TableHeaderCell>Created</TableHeaderCell>
                  <TableHeaderCell>Actions</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {articles.map((article) => (
                  <ArticleTableRow
                    key={article.id}
                    article={article}
                    blogName={blogNameMap[article.blog_id] ?? getMockBlogName(article.blog_id)}
                    onClick={() => router.push(`/articles/${article.id}`)}
                  />
                ))}
              </TableBody>
            </Table>
          ) : (
            /* Empty state */
            <div className="p-16 text-center">
              <p className="text-muted font-black uppercase tracking-widest text-lg">
                No articles yet
              </p>
              <p className="text-muted font-bold text-sm mt-2 mb-6">
                Create your first article to get started with content generation.
              </p>
              <Button variant="primary" onClick={() => router.push('/articles/new')}>
                + Create First Article
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
