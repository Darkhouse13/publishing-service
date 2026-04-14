'use client';

import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import BlogCard from '@/components/connections/BlogCard';
import Button from '@/components/ui/Button';
import { useBlogs } from '@/hooks/useBlogs';
import { useArticles } from '@/hooks/useArticles';

export default function ConnectionsPage() {
  const { blogs, toggleBlog } = useBlogs();
  const { articles } = useArticles();

  return (
    <div>
      <PageHeader title="Connections">
        <Link href="/connections/new">
          <Button variant="primary">+ Add New Blog</Button>
        </Link>
      </PageHeader>

      <div className="p-8">
        {blogs.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {blogs.map((blog) => (
              <BlogCard
                key={blog.id}
                blog={blog}
                articles={articles}
                onToggle={toggleBlog}
              />
            ))}
          </div>
        ) : (
          <div className="bg-white border-[3px] border-base shadow-solid-md p-12 text-center">
            <p className="text-muted font-black uppercase tracking-widest text-lg">
              No Blogs Connected
            </p>
            <p className="text-muted font-bold text-sm mt-2">
              Add your first blog to get started.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
