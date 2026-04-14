'use client';

import { useCallback } from 'react';
import useSWR from 'swr';
import { articlesApi } from '@/lib/api';
import type { Article, ArticleCreate } from '@/lib/types';
import { mockArticles } from '@/lib/mock-data';

export function useArticles(fallback?: Article[]) {
  const { data, error, isLoading, mutate } = useSWR<Article[]>(
    '/articles',
    () => articlesApi.list(),
    {
      fallbackData: fallback ?? mockArticles,
      revalidateOnFocus: false,
    },
  );

  const createArticle = useCallback(
    async (articleData: ArticleCreate) => {
      const newArticle = await articlesApi.create(articleData);
      await mutate((current) => [...(current ?? []), newArticle], false);
      return newArticle;
    },
    [mutate],
  );

  return {
    articles: data ?? [],
    error,
    isLoading,
    mutate,
    createArticle,
  };
}

export function useArticle(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Article>(
    id ? `/articles/${id}` : null,
    () => (id ? articlesApi.get(id) : Promise.resolve(null as unknown as Article)),
    {
      revalidateOnFocus: false,
    },
  );

  return {
    article: data,
    error,
    isLoading,
    mutate,
  };
}
