'use client';

import { useCallback, useMemo } from 'react';
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

export function useRunArticles(runId: string | null) {
  // Build fallback: mock articles filtered by run_id
  const fallbackData = runId
    ? mockArticles.filter((a) => a.run_id === runId)
    : [];

  const { data, error, isLoading, mutate } = useSWR<Article[]>(
    runId ? `/articles?run_id=${runId}` : null,
    () =>
      runId
        ? articlesApi.list({ run_id: runId })
        : Promise.resolve([]),
    {
      fallbackData,
      revalidateOnFocus: false,
    },
  );

  return {
    articles: data ?? [],
    error,
    isLoading,
    mutate,
  };
}

export function useArticle(id: string | null) {
  // Build fallback: find matching mock article by ID
  const fallbackArticle = useMemo(
    () => (id ? mockArticles.find((a) => a.id === id) ?? undefined : undefined),
    [id],
  );

  const { data, error, isLoading, mutate } = useSWR<Article>(
    id ? `/articles/${id}` : null,
    () => (id ? articlesApi.get(id) : Promise.resolve(null as unknown as Article)),
    {
      fallbackData: fallbackArticle,
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
