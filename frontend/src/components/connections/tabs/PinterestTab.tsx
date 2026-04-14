'use client';

import { useState, FormEvent } from 'react';
import Textarea from '@/components/ui/Textarea';
import Button from '@/components/ui/Button';
import type { Blog } from '@/lib/types';

interface PinterestTabProps {
  blog: Blog;
  onSave: (data: Partial<Blog>) => Promise<void>;
}

/**
 * Converts a Record<string, string> to a display-friendly textarea string.
 * Format: Category Name = board-slug
 */
function boardMapToString(
  data: Record<string, string> | undefined
): string {
  if (!data || Object.keys(data).length === 0) return '';
  return Object.entries(data)
    .map(([category, board]) => `${category} = ${board}`)
    .join('\n');
}

/**
 * Parses a textarea string into a Record<string, string>.
 */
function stringToBoardMap(
  text: string
): Record<string, string> | undefined {
  if (!text.trim()) return undefined;
  const result: Record<string, string> = {};
  text.split('\n').forEach((line) => {
    const [key, value] = line.split('=').map((s) => s.trim());
    if (key && value) {
      result[key] = value;
    }
  });
  return Object.keys(result).length > 0 ? result : undefined;
}

export default function PinterestTab({ blog, onSave }: PinterestTabProps) {
  const [seedKeywords, setSeedKeywords] = useState(
    blog.seed_keywords?.join(', ') || ''
  );
  const [pinterestBoardMap, setPinterestBoardMap] = useState(
    boardMapToString(blog.pinterest_board_map)
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
      const parsedSeedKeywords = seedKeywords.trim()
        ? seedKeywords
            .split(',')
            .map((k) => k.trim())
            .filter(Boolean)
        : undefined;
      const parsedBoardMap = stringToBoardMap(pinterestBoardMap);

      await onSave({
        ...(parsedSeedKeywords && { seed_keywords: parsedSeedKeywords }),
        ...(parsedBoardMap && { pinterest_board_map: parsedBoardMap }),
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
        Pinterest
      </h2>

      <div className="max-w-xl space-y-5">
        <Textarea
          label="Seed Keywords"
          value={seedKeywords}
          onChange={(e) => setSeedKeywords(e.target.value)}
          placeholder="keyword1, keyword2, keyword3"
          rows={3}
        />
        <Textarea
          label="Pinterest Board Map"
          value={pinterestBoardMap}
          onChange={(e) => setPinterestBoardMap(e.target.value)}
          placeholder={
            'Category Name = board-slug\nAnother Category = another-board-slug'
          }
          rows={4}
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
