'use client';

import { useState, FormEvent } from 'react';
import Input from '@/components/ui/Input';
import Textarea from '@/components/ui/Textarea';
import Button from '@/components/ui/Button';
import type { Blog } from '@/lib/types';

interface CategoriesTabProps {
  blog: Blog;
  onSave: (data: Partial<Blog>) => Promise<void>;
}

/**
 * Converts a Record<string, string[]> to a display-friendly textarea string.
 * Format: Category Name = keyword1, keyword2, keyword3
 */
function categoryKeywordsToString(
  data: Record<string, string[]> | undefined
): string {
  if (!data || Object.keys(data).length === 0) return '';
  return Object.entries(data)
    .map(([category, keywords]) => `${category} = ${keywords.join(', ')}`)
    .join('\n');
}

/**
 * Parses a textarea string into a Record<string, string[]>.
 */
function stringToCategoryKeywords(
  text: string
): Record<string, string[]> | undefined {
  if (!text.trim()) return undefined;
  const result: Record<string, string[]> = {};
  text.split('\n').forEach((line) => {
    const [category, keywords] = line.split('=').map((s) => s.trim());
    if (category && keywords) {
      result[category] = keywords
        .split(',')
        .map((k) => k.trim())
        .filter(Boolean);
    }
  });
  return Object.keys(result).length > 0 ? result : undefined;
}

export default function CategoriesTab({ blog, onSave }: CategoriesTabProps) {
  const [fallbackCategory, setFallbackCategory] = useState(
    blog.fallback_category || ''
  );
  const [deprioritizedCategory, setDeprioritizedCategory] = useState(
    blog.deprioritized_category || ''
  );
  const [categoryKeywords, setCategoryKeywords] = useState(
    categoryKeywordsToString(blog.category_keywords)
  );
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      const parsedCategoryKeywords = stringToCategoryKeywords(categoryKeywords);
      await onSave({
        fallback_category: fallbackCategory.trim() || undefined,
        deprioritized_category: deprioritizedCategory.trim() || undefined,
        ...(parsedCategoryKeywords && {
          category_keywords: parsedCategoryKeywords,
        }),
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : 'Failed to save changes.'
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h2 className="text-lg font-black uppercase tracking-widest mb-6">
        Categories
      </h2>

      <div className="max-w-xl space-y-5">
        <Input
          label="Fallback Category"
          value={fallbackCategory}
          onChange={(e) => setFallbackCategory(e.target.value)}
          placeholder="Uncategorized"
        />
        <Input
          label="Deprioritized Category"
          value={deprioritizedCategory}
          onChange={(e) => setDeprioritizedCategory(e.target.value)}
          placeholder="Uncategorized"
        />
        <Textarea
          label="Category Keywords"
          value={categoryKeywords}
          onChange={(e) => setCategoryKeywords(e.target.value)}
          placeholder={
            'Category Name = keyword1, keyword2, keyword3\nAnother Category = keyword4, keyword5'
          }
          rows={6}
        />
      </div>

      {/* Feedback */}
      {saveError && (
        <div className="mt-4 border-[3px] border-error bg-error/5 p-4">
          <p className="text-sm font-bold text-error uppercase tracking-widest">
            {saveError}
          </p>
        </div>
      )}
      {saveSuccess && (
        <div className="mt-4 border-[3px] border-accent bg-accent/10 p-4">
          <p className="text-sm font-bold text-base uppercase tracking-widest">
            Changes saved successfully
          </p>
        </div>
      )}

      <div className="mt-6 flex items-center gap-4">
        <Button type="submit" variant="primary" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>
    </form>
  );
}
