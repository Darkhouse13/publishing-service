'use client';

import useSWR from 'swr';
import { articlesApi } from '@/lib/api';
import type { Article } from '@/lib/types';
import { mockArticles } from '@/lib/mock-data';

export function useArticles(fallback?: Article[]) {
  const { data, error, isLoading, mutate } = useSWR<Article[]>(
    '/articles',
    () => articlesApi.list(),
    {
      fallbackData: fallback ?? mockArticles,
      revalidateOnFocus: false,
    }
  );

  return {
    articles: data ?? [],
    error,
    isLoading,
    mutate,
  };
}

export function useArticle(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Article>(
    id ? `/articles/${id}` : null,
    () => (id ? articlesApi.get(id) : Promise.resolve(null as unknown as Article)),
    {
      revalidateOnFocus: false,
    }
  );

  return {
    article: data,
    error,
    isLoading,
    mutate,
  };
}
