'use client';

import useSWR from 'swr';
import { blogsApi } from '@/lib/api';
import type { Blog } from '@/lib/types';
import { mockBlogs } from '@/lib/mock-data';

export function useBlogs(fallback?: Blog[]) {
  const { data, error, isLoading, mutate } = useSWR<Blog[]>(
    '/blogs',
    () => blogsApi.list(),
    {
      fallbackData: fallback ?? mockBlogs,
      revalidateOnFocus: false,
    }
  );

  return {
    blogs: data ?? [],
    error,
    isLoading,
    mutate,
  };
}

export function useBlog(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Blog>(
    id ? `/blogs/${id}` : null,
    () => (id ? blogsApi.get(id) : Promise.resolve(null as unknown as Blog)),
    {
      revalidateOnFocus: false,
    }
  );

  return {
    blog: data,
    error,
    isLoading,
    mutate,
  };
}
