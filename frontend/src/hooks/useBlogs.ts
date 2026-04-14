'use client';

import { useCallback } from 'react';
import useSWR from 'swr';
import { blogsApi } from '@/lib/api';
import type { Blog, BlogCreate, BlogUpdate } from '@/lib/types';
import { mockBlogs } from '@/lib/mock-data';

export function useBlogs(fallback?: Blog[]) {
  const { data, error, isLoading, mutate } = useSWR<Blog[]>(
    '/blogs',
    () => blogsApi.list(),
    {
      fallbackData: fallback ?? mockBlogs,
      revalidateOnFocus: false,
    },
  );

  const createBlog = useCallback(
    async (blogData: BlogCreate) => {
      const newBlog = await blogsApi.create(blogData);
      await mutate((current) => [...(current ?? []), newBlog], false);
      return newBlog;
    },
    [mutate],
  );

  const updateBlog = useCallback(
    async (id: string, blogData: BlogUpdate) => {
      const updatedBlog = await blogsApi.update(id, blogData);
      await mutate(
        (current) =>
          current?.map((b) => (b.id === id ? updatedBlog : b)),
        false,
      );
      return updatedBlog;
    },
    [mutate],
  );

  const toggleBlog = useCallback(
    async (id: string, isActive: boolean) => {
      // Optimistic update
      await mutate(
        (current) =>
          current?.map((b) =>
            b.id === id ? { ...b, is_active: isActive } : b,
          ),
        false,
      );

      try {
        await blogsApi.patch(id, { is_active: isActive });
      } catch {
        // Revert on error
        await mutate();
      }
    },
    [mutate],
  );

  return {
    blogs: data ?? [],
    error,
    isLoading,
    mutate,
    createBlog,
    updateBlog,
    toggleBlog,
  };
}

export function useBlog(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Blog>(
    id ? `/blogs/${id}` : null,
    () => (id ? blogsApi.get(id) : Promise.resolve(null as unknown as Blog)),
    {
      revalidateOnFocus: false,
    },
  );

  return {
    blog: data,
    error,
    isLoading,
    mutate,
  };
}
